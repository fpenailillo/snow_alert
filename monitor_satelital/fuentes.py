"""
Monitor Satelital de Nieve - Selección de Fuentes Satelitales

Lógica para determinar la fuente satelital apropiada según la región
geográfica de cada ubicación, con fallbacks automáticos.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple

from constantes import (
    FUENTES_POR_REGION,
    COLECCION_GOES_18,
    COLECCION_GOES_16,
    COLECCION_MODIS_REFLECTANCIA_TERRA,
    COLECCION_MODIS_REFLECTANCIA_AQUA,
    COLECCION_MODIS_NIEVE_TERRA,
    COLECCION_MODIS_NIEVE_AQUA,
    COLECCION_MODIS_LST,
    COLECCION_ERA5_LAND,
    COLECCION_SENTINEL2,
    COLECCION_VIIRS_REFLECTANCIA,
    RESOLUCIONES,
)


logger = logging.getLogger(__name__)


class ErrorFuenteNoDisponible(Exception):
    """Excepción cuando no hay fuente satelital disponible para la ubicación."""
    pass


def determinar_region_por_coordenadas(longitud: float, latitud: float) -> str:
    """
    Determina la región geográfica basándose en las coordenadas.

    La lógica principal usa longitud para separar Américas del resto:
    - Longitud entre -170° y -30° → Américas (GOES disponible)
    - Resto del mundo → Sin cobertura geoestacionaria en GEE

    Args:
        longitud: Longitud en grados decimales
        latitud: Latitud en grados decimales

    Returns:
        str: Identificador de región ('americas' o 'global')
    """
    # Américas: GOES disponible
    if -170 <= longitud <= -30:
        # Subdividir Américas
        if latitud < -15:
            # Sudamérica sur (Chile, Argentina, etc.)
            return 'americas_sur'
        elif latitud > 25:
            # Norteamérica
            return 'americas_norte'
        else:
            # Centroamérica y norte de Sudamérica
            return 'americas_centro'
    else:
        # Resto del mundo: solo MODIS/VIIRS
        if 35 <= latitud <= 70 and -15 <= longitud <= 45:
            return 'europa'
        elif latitud > 25 and longitud > 60:
            return 'asia'
        elif latitud < -10 and longitud > 100:
            return 'oceania'
        else:
            return 'global'


def obtener_region_ubicacion(nombre_ubicacion: str) -> Optional[str]:
    """
    Obtiene la región configurada para una ubicación específica.

    Args:
        nombre_ubicacion: Nombre de la ubicación a buscar

    Returns:
        str o None: Nombre de la región si se encuentra
    """
    for region, config in FUENTES_POR_REGION.items():
        if nombre_ubicacion in config.get('ubicaciones', []):
            return region
    return None


def obtener_configuracion_fuente(
    nombre_ubicacion: str,
    latitud: float,
    longitud: float
) -> Dict[str, Any]:
    """
    Obtiene la configuración de fuentes satelitales para una ubicación.

    Primero busca en la configuración explícita por nombre, luego
    determina automáticamente por coordenadas si no está configurada.

    Args:
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud en grados decimales
        longitud: Longitud en grados decimales

    Returns:
        dict: Configuración de fuentes con claves:
            - fuente_principal: str
            - fuente_diaria: str
            - fuente_alta_res: str
            - gap_filler: str
            - capturas_dia: int
            - region: str
    """
    # Buscar configuración explícita
    region_configurada = obtener_region_ubicacion(nombre_ubicacion)

    if region_configurada:
        config = FUENTES_POR_REGION[region_configurada].copy()
        config['region'] = region_configurada
        logger.info(f"Configuración encontrada para {nombre_ubicacion}: región {region_configurada}")
        return config

    # Determinar automáticamente por coordenadas
    region_auto = determinar_region_por_coordenadas(longitud, latitud)
    logger.info(f"Región determinada automáticamente para {nombre_ubicacion}: {region_auto}")

    # Configuración por defecto según región detectada
    if region_auto.startswith('americas'):
        # Américas: usar GOES
        goes_satelite = 'GOES-16' if region_auto == 'americas_norte' else 'GOES-18'
        return {
            'fuente_principal': goes_satelite,
            'fuente_diaria': 'MODIS',
            'fuente_alta_res': 'Sentinel-2',
            'gap_filler': 'ERA5-Land',
            'capturas_dia': 3,
            'region': region_auto,
        }
    else:
        # Resto del mundo: solo MODIS
        return {
            'fuente_principal': 'MODIS',
            'fuente_diaria': 'MODIS',
            'fuente_alta_res': 'Sentinel-2',
            'gap_filler': 'ERA5-Land',
            'capturas_dia': 2,
            'region': region_auto,
        }


def obtener_coleccion_gee(fuente: str, producto: str) -> str:
    """
    Obtiene el ID de colección GEE para una fuente y producto específicos.

    Args:
        fuente: Nombre de la fuente ('GOES-18', 'MODIS', etc.)
        producto: Tipo de producto ('visual', 'ndsi', 'lst', 'era5')

    Returns:
        str: ID de colección GEE

    Raises:
        ErrorFuenteNoDisponible: Si la combinación fuente/producto no existe
    """
    mapeo_colecciones = {
        'GOES-18': {
            'visual': COLECCION_GOES_18,
            'termico': COLECCION_GOES_18,
        },
        'GOES-16': {
            'visual': COLECCION_GOES_16,
            'termico': COLECCION_GOES_16,
        },
        'MODIS': {
            'visual_terra': COLECCION_MODIS_REFLECTANCIA_TERRA,
            'visual_aqua': COLECCION_MODIS_REFLECTANCIA_AQUA,
            'visual': COLECCION_MODIS_REFLECTANCIA_TERRA,  # Por defecto Terra
            'ndsi_terra': COLECCION_MODIS_NIEVE_TERRA,
            'ndsi_aqua': COLECCION_MODIS_NIEVE_AQUA,
            'ndsi': COLECCION_MODIS_NIEVE_TERRA,  # Por defecto Terra
            'lst': COLECCION_MODIS_LST,
        },
        'VIIRS': {
            'visual': COLECCION_VIIRS_REFLECTANCIA,
        },
        'ERA5-Land': {
            'nieve': COLECCION_ERA5_LAND,
            'temperatura': COLECCION_ERA5_LAND,
        },
        'Sentinel-2': {
            'visual': COLECCION_SENTINEL2,
            'ndsi': COLECCION_SENTINEL2,
        },
    }

    if fuente not in mapeo_colecciones:
        raise ErrorFuenteNoDisponible(f"Fuente no soportada: {fuente}")

    if producto not in mapeo_colecciones[fuente]:
        raise ErrorFuenteNoDisponible(
            f"Producto '{producto}' no disponible para fuente '{fuente}'"
        )

    return mapeo_colecciones[fuente][producto]


def obtener_resolucion(fuente: str) -> int:
    """
    Obtiene la resolución espacial en metros para una fuente.

    Args:
        fuente: Nombre de la fuente

    Returns:
        int: Resolución en metros
    """
    return RESOLUCIONES.get(fuente, 500)


def obtener_fuentes_ordenadas_por_prioridad(
    config_ubicacion: Dict[str, Any],
    tipo_captura: str
) -> List[Tuple[str, str]]:
    """
    Obtiene lista de fuentes ordenadas por prioridad para una captura.

    Para capturas diurnas: fuente_principal → fuente_diaria → VIIRS
    Para capturas nocturnas: solo térmica (LST, ERA5)

    Args:
        config_ubicacion: Configuración de fuentes de la ubicación
        tipo_captura: 'diurna' o 'nocturna_termica'

    Returns:
        list: Lista de tuplas (fuente, producto) en orden de prioridad
    """
    fuentes = []

    if tipo_captura == 'nocturna_termica':
        # Capturas nocturnas: solo térmico
        fuentes.append(('MODIS', 'lst'))
        fuentes.append(('ERA5-Land', 'temperatura'))
    else:
        # Capturas diurnas
        fuente_principal = config_ubicacion.get('fuente_principal', 'MODIS')

        # Fuente principal para visual
        if fuente_principal.startswith('GOES'):
            fuentes.append((fuente_principal, 'visual'))

        # MODIS siempre como respaldo diario
        fuentes.append(('MODIS', 'visual'))

        # VIIRS como alternativa
        fuentes.append(('VIIRS', 'visual'))

    return fuentes


def hay_cobertura_goes(longitud: float) -> bool:
    """
    Verifica si las coordenadas tienen cobertura GOES.

    GOES-18: centrado en ~137°W (Pacífico/Américas occidental)
    GOES-16: centrado en ~75°W (Atlántico/Américas oriental)

    Args:
        longitud: Longitud en grados decimales

    Returns:
        bool: True si hay cobertura GOES
    """
    return -170 <= longitud <= -30


def seleccionar_satelite_goes(longitud: float) -> str:
    """
    Selecciona el satélite GOES apropiado según la longitud.

    Args:
        longitud: Longitud en grados decimales

    Returns:
        str: 'GOES-18' o 'GOES-16'
    """
    if not hay_cobertura_goes(longitud):
        raise ErrorFuenteNoDisponible(
            f"Sin cobertura GOES para longitud {longitud}"
        )

    # GOES-18 para el Pacífico y costa oeste de Américas
    # GOES-16 para el Atlántico y costa este
    if longitud < -100:
        return 'GOES-18'
    else:
        return 'GOES-16'


def validar_fuente_disponible(fuente: str, producto: str) -> bool:
    """
    Valida si una fuente y producto están disponibles.

    Args:
        fuente: Nombre de la fuente
        producto: Tipo de producto

    Returns:
        bool: True si la combinación es válida
    """
    try:
        obtener_coleccion_gee(fuente, producto)
        return True
    except ErrorFuenteNoDisponible:
        return False


def obtener_todas_las_fuentes_para_ubicacion(
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    tipo_captura: str
) -> Dict[str, Any]:
    """
    Obtiene todas las fuentes a consultar para una ubicación y captura.

    Args:
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud
        longitud: Longitud
        tipo_captura: 'manana', 'tarde', 'noche'

    Returns:
        dict: Información de fuentes con:
            - config: Configuración general
            - fuentes_visual: Lista de fuentes para imagen visual
            - fuentes_ndsi: Lista de fuentes para NDSI
            - fuentes_lst: Lista de fuentes para LST
            - fuentes_era5: Fuente ERA5 siempre incluida
    """
    config = obtener_configuracion_fuente(nombre_ubicacion, latitud, longitud)

    resultado = {
        'config': config,
        'fuentes_visual': [],
        'fuentes_ndsi': [],
        'fuentes_lst': [],
        'fuentes_era5': [('ERA5-Land', 'nieve')],  # Siempre incluido como gap-filler
    }

    tipo = 'nocturna_termica' if tipo_captura == 'noche' else 'diurna'

    if tipo == 'diurna':
        # Fuentes visuales
        fuente_principal = config.get('fuente_principal', 'MODIS')
        if fuente_principal.startswith('GOES'):
            resultado['fuentes_visual'].append((fuente_principal, 'visual'))
        resultado['fuentes_visual'].append(('MODIS', 'visual_terra'))
        resultado['fuentes_visual'].append(('MODIS', 'visual_aqua'))

        # NDSI
        resultado['fuentes_ndsi'].append(('MODIS', 'ndsi_terra'))
        resultado['fuentes_ndsi'].append(('MODIS', 'ndsi_aqua'))

        # LST diurno
        resultado['fuentes_lst'].append(('MODIS', 'lst'))

    else:
        # Captura nocturna: solo LST y ERA5
        resultado['fuentes_lst'].append(('MODIS', 'lst'))

    logger.info(
        f"Fuentes configuradas para {nombre_ubicacion} ({tipo_captura}): "
        f"visual={len(resultado['fuentes_visual'])}, "
        f"ndsi={len(resultado['fuentes_ndsi'])}, "
        f"lst={len(resultado['fuentes_lst'])}"
    )

    return resultado

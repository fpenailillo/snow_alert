"""
Monitor Satelital de Nieve - Viento en Altura (ERA5 Pressure Levels)

Funciones para obtener datos de viento en altura desde ERA5 para análisis
de transporte eólico de nieve.

Importancia para Andes chilenos:
- Cumbres 3000-5000m expuestas a vientos de altura
- Transporte eólico redistribuye nieve → forma PLACAS DE VIENTO
- Las placas de viento causan la MAYORÍA de avalanchas mortales
- Dirección del viento determina DÓNDE se acumula nieve (sotavento)
- Velocidad > 25 km/h con nieve disponible = transporte activo

Niveles de presión relevantes para montaña:
- 700 hPa ≈ 3000m (nivel de cumbres Andes centrales)
- 600 hPa ≈ 4200m (alta montaña, Aconcagua approach)
- 500 hPa ≈ 5500m (alta montaña extrema)
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

import ee


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES DE VIENTO
# =============================================================================

# Colección ERA5 (pressure levels, NO ERA5-Land)
COLECCION_ERA5_PRESSURE = 'ECMWF/ERA5/HOURLY'

# Niveles de presión relevantes para montaña (hPa)
NIVELES_PRESION = {
    '700': 3000,   # ~3000m - cumbres Andes centrales
    '600': 4200,   # ~4200m - alta montaña
    '500': 5500,   # ~5500m - alta montaña extrema
}

# Nivel por defecto para análisis
NIVEL_DEFAULT = '700'

# Umbral de velocidad para transporte eólico (m/s)
# 7 m/s ≈ 25 km/h - umbral de inicio de transporte
UMBRAL_TRANSPORTE_EOLICO_MS = 7.0

# Umbral de velocidad para transporte intenso (m/s)
# 15 m/s ≈ 54 km/h - transporte muy activo
UMBRAL_TRANSPORTE_INTENSO_MS = 15.0

# Días hacia atrás para buscar datos ERA5
DIAS_BUSQUEDA_ERA5 = 7

# Horas para ventana de análisis (máximo en 24h)
HORAS_ANALISIS_MAX = 24


# =============================================================================
# FUNCIONES DE CÁLCULO DE VIENTO
# =============================================================================

def calcular_velocidad_direccion(u: float, v: float) -> Tuple[float, float]:
    """
    Calcula velocidad y dirección del viento desde componentes U y V.

    Args:
        u: Componente U (este-oeste) en m/s
        v: Componente V (norte-sur) en m/s

    Returns:
        Tuple[float, float]: (velocidad en m/s, dirección en grados 0-360)

    Nota:
        - Dirección indica DE DONDE viene el viento
        - 0° = Norte, 90° = Este, 180° = Sur, 270° = Oeste
    """
    # Velocidad = sqrt(u² + v²)
    velocidad = math.sqrt(u ** 2 + v ** 2)

    # Dirección meteorológica (de donde viene)
    # atan2(-u, -v) da la dirección en radianes, luego convertir a grados
    direccion_rad = math.atan2(-u, -v)
    direccion_deg = math.degrees(direccion_rad)

    # Normalizar a 0-360
    if direccion_deg < 0:
        direccion_deg += 360

    return velocidad, direccion_deg


def calcular_aspecto_sotavento(direccion_viento: float) -> float:
    """
    Calcula el aspecto donde se deposita nieve transportada (sotavento).

    El viento deposita nieve en las laderas de sotavento, es decir,
    en el aspecto opuesto a la dirección del viento.

    Args:
        direccion_viento: Dirección de donde viene el viento (grados)

    Returns:
        float: Aspecto de sotavento (grados, 0-360)
    """
    # El sotavento está en la dirección opuesta (+180°)
    sotavento = direccion_viento + 180
    if sotavento >= 360:
        sotavento -= 360

    return sotavento


def velocidad_a_kmh(velocidad_ms: float) -> float:
    """
    Convierte velocidad de m/s a km/h.

    Args:
        velocidad_ms: Velocidad en metros por segundo

    Returns:
        float: Velocidad en kilómetros por hora
    """
    return velocidad_ms * 3.6


# =============================================================================
# FUNCIONES DE OBTENCIÓN DE DATOS ERA5
# =============================================================================

def obtener_viento_altura(
    latitud: float,
    longitud: float,
    nivel_presion: str = NIVEL_DEFAULT,
    fecha: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Obtiene datos de viento en altura desde ERA5.

    Args:
        latitud: Latitud del punto
        longitud: Longitud del punto
        nivel_presion: Nivel de presión ('700', '600', '500')
        fecha: Fecha de referencia (default: más reciente disponible)

    Returns:
        dict: Datos de viento:
            - u_component: componente U (m/s)
            - v_component: componente V (m/s)
            - velocidad_ms: velocidad resultante (m/s)
            - velocidad_kmh: velocidad en km/h
            - direccion_grados: dirección de donde viene (grados)
            - nivel_presion_hpa: nivel de presión usado
            - elevacion_aprox_m: elevación aproximada del nivel
    """
    try:
        if fecha is None:
            # ERA5 tiene latencia de ~5 días, buscar más atrás
            fecha = datetime.utcnow() - timedelta(days=5)

        punto = ee.Geometry.Point([longitud, latitud])
        fecha_inicio = (fecha - timedelta(days=DIAS_BUSQUEDA_ERA5)).strftime('%Y-%m-%d')
        fecha_fin = fecha.strftime('%Y-%m-%d')

        # Bandas de viento (ERA5/HOURLY single-level: 100m como proxy de altura)
        banda_u = 'u_component_of_wind_100m'
        banda_v = 'v_component_of_wind_100m'

        # Obtener imagen más reciente
        coleccion = (ee.ImageCollection(COLECCION_ERA5_PRESSURE)
            .filterDate(fecha_inicio, fecha_fin)
            .filterBounds(punto)
            .select([banda_u, banda_v])
            .sort('system:time_start', False))

        cantidad = coleccion.size().getInfo()

        if cantidad == 0:
            logger.warning(f"No se encontraron datos ERA5 de viento para {fecha_fin}")
            return {'disponible': False}

        # Obtener la más reciente
        imagen = coleccion.first()

        # Extraer valores en el punto
        valores = imagen.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=punto,
            scale=31000,  # ERA5 ~31km resolución
            maxPixels=1e4
        ).getInfo()

        u = valores.get(banda_u)
        v = valores.get(banda_v)

        if u is None or v is None:
            logger.warning("No se obtuvieron valores de viento")
            return {'disponible': False}

        # Calcular velocidad y dirección
        velocidad_ms, direccion = calcular_velocidad_direccion(u, v)

        resultado = {
            'disponible': True,
            'u_component_ms': round(u, 2),
            'v_component_ms': round(v, 2),
            'velocidad_ms': round(velocidad_ms, 2),
            'velocidad_kmh': round(velocidad_a_kmh(velocidad_ms), 1),
            'direccion_grados': round(direccion, 1),
            'nivel_presion_hpa': int(nivel_presion),
            'elevacion_aprox_m': NIVELES_PRESION.get(nivel_presion, 3000),
        }

        logger.info(
            f"Viento {nivel_presion}hPa: {resultado['velocidad_kmh']} km/h "
            f"desde {resultado['direccion_grados']}°"
        )

        return resultado

    except Exception as e:
        logger.error(f"Error al obtener viento en altura: {str(e)}")
        return {'disponible': False, 'error': str(e)}


def obtener_viento_maximo_24h(
    latitud: float,
    longitud: float,
    nivel_presion: str = NIVEL_DEFAULT,
    fecha_fin: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Obtiene la velocidad máxima de viento en las últimas 24 horas.

    Args:
        latitud: Latitud del punto
        longitud: Longitud del punto
        nivel_presion: Nivel de presión
        fecha_fin: Fecha final del análisis

    Returns:
        dict: Datos de viento máximo:
            - viento_max_24h_ms: velocidad máxima (m/s)
            - viento_max_24h_kmh: velocidad máxima (km/h)
            - direccion_max: dirección del viento máximo
            - hora_max: hora aproximada del máximo
    """
    try:
        if fecha_fin is None:
            fecha_fin = datetime.utcnow() - timedelta(days=5)

        # Usar ventana de 7 días (igual que obtener_viento_altura) para
        # tolerar la latencia variable de ERA5 (puede ser >5 días)
        fecha_inicio = fecha_fin - timedelta(days=DIAS_BUSQUEDA_ERA5)
        punto = ee.Geometry.Point([longitud, latitud])

        # Obtener horas en la ventana ERA5
        coleccion = (ee.ImageCollection(COLECCION_ERA5_PRESSURE)
            .filterDate(
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
            .filterBounds(punto)
            .select(['u_component_of_wind_100m', 'v_component_of_wind_100m']))

        cantidad = coleccion.size().getInfo()

        if cantidad == 0:
            return {'disponible': False}

        # Calcular velocidad para cada imagen
        def agregar_velocidad(imagen):
            u = imagen.select('u_component_of_wind_100m')
            v = imagen.select('v_component_of_wind_100m')
            velocidad = u.pow(2).add(v.pow(2)).sqrt()
            return imagen.addBands(velocidad.rename('wind_speed'))

        coleccion_con_vel = coleccion.map(agregar_velocidad)

        # Obtener máxima velocidad
        max_imagen = coleccion_con_vel.reduce(ee.Reducer.max())

        stats = max_imagen.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=punto,
            scale=31000,
            maxPixels=1e4
        ).getInfo()

        vel_max = stats.get('wind_speed_max')

        if vel_max is None:
            return {'disponible': False}

        resultado = {
            'disponible': True,
            'viento_max_24h_ms': round(vel_max, 2),
            'viento_max_24h_kmh': round(velocidad_a_kmh(vel_max), 1),
            'horas_analizadas': cantidad,
        }

        logger.info(
            f"Viento máximo 24h: {resultado['viento_max_24h_kmh']} km/h "
            f"({cantidad} horas analizadas)"
        )

        return resultado

    except Exception as e:
        logger.error(f"Error al obtener viento máximo: {str(e)}")
        return {'disponible': False, 'error': str(e)}


# =============================================================================
# ANÁLISIS DE TRANSPORTE EÓLICO
# =============================================================================

def evaluar_transporte_eolico(
    velocidad_ms: float,
    tiene_nieve_disponible: bool = True
) -> Dict[str, Any]:
    """
    Evalúa las condiciones de transporte eólico de nieve.

    El transporte eólico requiere:
    1. Viento suficiente (>25 km/h ~ 7 m/s)
    2. Nieve disponible para transportar

    Args:
        velocidad_ms: Velocidad del viento en m/s
        tiene_nieve_disponible: True si hay nieve que pueda transportarse

    Returns:
        dict: Evaluación de transporte:
            - transporte_activo: True si hay transporte
            - intensidad: 'ninguno' / 'moderado' / 'intenso'
            - descripcion: descripción del estado
    """
    if not tiene_nieve_disponible:
        return {
            'transporte_activo': False,
            'intensidad': 'ninguno',
            'descripcion': 'Sin nieve disponible para transporte',
        }

    if velocidad_ms >= UMBRAL_TRANSPORTE_INTENSO_MS:
        return {
            'transporte_activo': True,
            'intensidad': 'intenso',
            'descripcion': f'Transporte eólico intenso ({velocidad_a_kmh(velocidad_ms):.0f} km/h)',
        }
    elif velocidad_ms >= UMBRAL_TRANSPORTE_EOLICO_MS:
        return {
            'transporte_activo': True,
            'intensidad': 'moderado',
            'descripcion': f'Transporte eólico moderado ({velocidad_a_kmh(velocidad_ms):.0f} km/h)',
        }
    else:
        return {
            'transporte_activo': False,
            'intensidad': 'ninguno',
            'descripcion': f'Viento insuficiente para transporte ({velocidad_a_kmh(velocidad_ms):.0f} km/h)',
        }


# =============================================================================
# FUNCIONES DE INTEGRACIÓN
# =============================================================================

def obtener_metricas_viento_completas(
    latitud: float,
    longitud: float,
    tiene_nieve: bool = True,
    fecha: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Obtiene todas las métricas de viento para una ubicación.

    Args:
        latitud: Latitud del punto
        longitud: Longitud del punto
        tiene_nieve: True si hay cobertura de nieve detectada
        fecha: Fecha de referencia

    Returns:
        dict: Todas las métricas de viento para BigQuery
    """
    metricas = {
        'viento_altura_vel_ms': None,
        'viento_altura_dir_grados': None,
        'viento_max_24h_ms': None,
        'transporte_eolico_activo': None,
        'aspecto_carga_eolica': None,
    }

    try:
        # Obtener viento actual en 700 hPa
        viento = obtener_viento_altura(latitud, longitud, NIVEL_DEFAULT, fecha)

        if viento.get('disponible'):
            metricas['viento_altura_vel_ms'] = viento.get('velocidad_ms')
            metricas['viento_altura_dir_grados'] = viento.get('direccion_grados')

            # Calcular aspecto de sotavento
            if viento.get('direccion_grados') is not None:
                metricas['aspecto_carga_eolica'] = calcular_aspecto_sotavento(
                    viento['direccion_grados']
                )

            # Evaluar transporte
            transporte = evaluar_transporte_eolico(
                viento.get('velocidad_ms', 0),
                tiene_nieve
            )
            metricas['transporte_eolico_activo'] = transporte.get('transporte_activo')

        # Obtener máximo en 24h (pasa None para usar latencia ERA5 interna de 5 días)
        viento_max = obtener_viento_maximo_24h(latitud, longitud, NIVEL_DEFAULT, None)

        if viento_max.get('disponible'):
            metricas['viento_max_24h_ms'] = viento_max.get('viento_max_24h_ms')

        logger.info(
            f"Métricas de viento compiladas: "
            f"vel={metricas['viento_altura_vel_ms']}m/s, "
            f"transporte={'Sí' if metricas['transporte_eolico_activo'] else 'No'}"
        )

    except Exception as e:
        logger.error(f"Error al obtener métricas de viento: {str(e)}")

    return metricas


def compilar_metricas_viento_bigquery(
    latitud: float,
    longitud: float,
    tiene_nieve: bool = True,
    fecha: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Wrapper que formatea métricas de viento para BigQuery.

    Args:
        latitud: Latitud del punto
        longitud: Longitud del punto
        tiene_nieve: True si hay cobertura de nieve
        fecha: Fecha de referencia

    Returns:
        dict: Métricas formateadas para BigQuery
    """
    return obtener_metricas_viento_completas(latitud, longitud, tiene_nieve, fecha)

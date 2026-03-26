"""
Monitor Satelital de Nieve - Procesamiento de Productos Satelitales

Funciones para obtener y procesar imágenes de cada tipo de producto:
visual (true color, false color), NDSI (cobertura de nieve),
LST (temperatura superficial) y ERA5-Land (gap-filler sin nubes).
"""

import concurrent.futures
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, List

import ee

from constantes import (
    COLECCION_GOES_18,
    COLECCION_GOES_16,
    COLECCION_MODIS_REFLECTANCIA_TERRA,
    COLECCION_MODIS_REFLECTANCIA_AQUA,
    COLECCION_MODIS_NIEVE_TERRA,
    COLECCION_MODIS_NIEVE_AQUA,
    COLECCION_MODIS_LST,
    COLECCION_ERA5_LAND,
    COLECCION_SENTINEL2,
    BANDAS_GOES,
    BANDAS_MODIS_REFLECTANCIA,
    BANDAS_MODIS_NIEVE,
    BANDAS_MODIS_LST,
    BANDAS_ERA5,
    VIS_MODIS_TRUE_COLOR,
    VIS_MODIS_FALSE_COLOR_NIEVE,
    VIS_NDSI_SNOW,
    VIS_LST,
    VIS_GOES_PSEUDO_COLOR,
    VIS_GOES_TERMICO,
    VIS_ERA5_SNOW_DEPTH,
    DIAS_BUSQUEDA_GOES,
    DIAS_BUSQUEDA_MODIS,
    DIAS_BUSQUEDA_ERA5,
    DIAS_BUSQUEDA_SENTINEL2,
    RADIO_TILE_METROS,
    NDSI_VALOR_NUBE,
    LST_FACTOR_ESCALA,
    KELVIN_A_CELSIUS,
    TIMEOUT_DESCARGA_SEGUNDOS,
)


logger = logging.getLogger(__name__)


def _getinfo_con_timeout(objeto_ee, timeout: int = TIMEOUT_DESCARGA_SEGUNDOS):
    """Ejecuta getInfo() de GEE con timeout para evitar bloqueos indefinidos en Cloud Functions."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futuro = executor.submit(objeto_ee.getInfo)
        try:
            return futuro.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"GEE getInfo() timeout después de {timeout}s")


class ErrorProductoNoDisponible(Exception):
    """Excepción cuando el producto satelital no está disponible."""
    pass


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def crear_roi(latitud: float, longitud: float, radio_metros: int = RADIO_TILE_METROS) -> ee.Geometry:
    """
    Crea una región de interés (ROI) como buffer cuadrado alrededor del punto.

    Args:
        latitud: Latitud del punto central
        longitud: Longitud del punto central
        radio_metros: Radio del buffer en metros

    Returns:
        ee.Geometry: Geometría del ROI
    """
    punto = ee.Geometry.Point([longitud, latitud])
    return punto.buffer(radio_metros).bounds()


def obtener_imagen_mas_reciente(
    coleccion_id: str,
    roi: ee.Geometry,
    dias_atras: int = 7,
    filtros_adicionales: Optional[List[ee.Filter]] = None
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Busca la imagen más reciente de una colección GEE para un ROI.

    Args:
        coleccion_id: ID de la colección GEE
        roi: Región de interés
        dias_atras: Días hacia atrás para buscar
        filtros_adicionales: Filtros adicionales a aplicar

    Returns:
        Tuple: (imagen o None, metadatos dict)
    """
    try:
        hoy = datetime.now(timezone.utc)
        desde = (hoy - timedelta(days=dias_atras)).strftime('%Y-%m-%d')
        hasta = (hoy + timedelta(days=1)).strftime('%Y-%m-%d')  # Incluir hoy

        coleccion = (ee.ImageCollection(coleccion_id)
                     .filterDate(desde, hasta)
                     .filterBounds(roi)
                     .sort('system:time_start', False))

        # Aplicar filtros adicionales si existen
        if filtros_adicionales:
            for filtro in filtros_adicionales:
                coleccion = coleccion.filter(filtro)

        cantidad = _getinfo_con_timeout(coleccion.size())

        if cantidad == 0:
            logger.warning(
                f"No se encontraron imágenes en {coleccion_id} "
                f"para los últimos {dias_atras} días"
            )
            return None, {
                'disponible': False,
                'coleccion': coleccion_id,
                'dias_buscados': dias_atras,
            }

        imagen = coleccion.first()
        info = _getinfo_con_timeout(imagen)
        timestamp_ms = info['properties'].get('system:time_start', 0)
        fecha_captura = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        # Calcular antigüedad
        antiguedad_horas = (hoy - fecha_captura).total_seconds() / 3600

        return imagen, {
            'disponible': True,
            'fecha_captura': fecha_captura.isoformat(),
            'timestamp_ms': timestamp_ms,
            'coleccion': coleccion_id,
            'imagenes_encontradas': cantidad,
            'antiguedad_horas': antiguedad_horas,
        }

    except Exception as e:
        logger.error(f"Error al buscar imagen en {coleccion_id}: {str(e)}")
        return None, {
            'disponible': False,
            'coleccion': coleccion_id,
            'error': str(e),
        }


# =============================================================================
# PRODUCTOS GOES
# =============================================================================

def obtener_imagen_goes(
    roi: ee.Geometry,
    satelite: str = 'GOES-18'
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Obtiene la imagen GOES más reciente para el ROI.

    Args:
        roi: Región de interés
        satelite: 'GOES-18' o 'GOES-16'

    Returns:
        Tuple: (imagen, metadatos)
    """
    coleccion = COLECCION_GOES_18 if satelite == 'GOES-18' else COLECCION_GOES_16
    return obtener_imagen_mas_reciente(coleccion, roi, DIAS_BUSQUEDA_GOES)


def procesar_goes_visual(imagen: ee.Image) -> ee.Image:
    """
    Procesa imagen GOES para visualización pseudo-color.

    Args:
        imagen: Imagen GOES

    Returns:
        ee.Image: Imagen RGB procesada
    """
    # Pseudo true color: R=C02, G=C03, B=C01
    return imagen.select([
        BANDAS_GOES['visible_rojo'],
        BANDAS_GOES['near_ir'],
        BANDAS_GOES['visible_azul']
    ]).rename(['R', 'G', 'B'])


def procesar_goes_termico(imagen: ee.Image) -> ee.Image:
    """
    Procesa banda térmica de GOES.

    Args:
        imagen: Imagen GOES

    Returns:
        ee.Image: Banda térmica en Kelvin
    """
    return imagen.select([BANDAS_GOES['ir_termico']]).rename(['LST_Kelvin'])


def obtener_vis_params_goes_visual() -> Dict[str, Any]:
    """Retorna parámetros de visualización para GOES visual."""
    return VIS_GOES_PSEUDO_COLOR


def obtener_vis_params_goes_termico() -> Dict[str, Any]:
    """Retorna parámetros de visualización para GOES térmico."""
    return VIS_GOES_TERMICO


# =============================================================================
# PRODUCTOS MODIS REFLECTANCIA
# =============================================================================

def obtener_imagen_modis_reflectancia(
    roi: ee.Geometry,
    satelite: str = 'terra'
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Obtiene imagen de reflectancia MODIS para el ROI.

    Args:
        roi: Región de interés
        satelite: 'terra' o 'aqua'

    Returns:
        Tuple: (imagen, metadatos)
    """
    coleccion = (COLECCION_MODIS_REFLECTANCIA_TERRA
                 if satelite == 'terra'
                 else COLECCION_MODIS_REFLECTANCIA_AQUA)
    return obtener_imagen_mas_reciente(coleccion, roi, DIAS_BUSQUEDA_MODIS)


def aplicar_mascara_nubes_modis(imagen: ee.Image) -> ee.Image:
    """
    Aplica máscara de nubes usando la banda state_1km de MODIS.

    Bit 10 = flag de nube interno (preferido para reflectancia)
    Bit 13 = adyacencia a nube

    Args:
        imagen: Imagen MODIS con banda state_1km

    Returns:
        ee.Image: Imagen con nubes enmascaradas
    """
    qa = imagen.select(BANDAS_MODIS_REFLECTANCIA['estado'])

    # Bit 10: nube
    mascara_nube = qa.bitwiseAnd(1 << 10).eq(0)
    # Bit 13: adyacencia a nube
    mascara_adyacencia = qa.bitwiseAnd(1 << 13).eq(0)

    mascara_combinada = mascara_nube.And(mascara_adyacencia)

    return imagen.updateMask(mascara_combinada)


def procesar_modis_true_color(imagen: ee.Image) -> ee.Image:
    """
    Procesa imagen MODIS para true color (RGB natural).

    Args:
        imagen: Imagen MODIS MOD09GA/MYD09GA

    Returns:
        ee.Image: Imagen RGB
    """
    return imagen.select([
        BANDAS_MODIS_REFLECTANCIA['rojo'],
        BANDAS_MODIS_REFLECTANCIA['verde'],
        BANDAS_MODIS_REFLECTANCIA['azul']
    ]).rename(['R', 'G', 'B'])


def procesar_modis_false_color_nieve(imagen: ee.Image) -> ee.Image:
    """
    Procesa imagen MODIS para false color nieve.
    Nieve aparece ROJA, nubes blancas, vegetación verde.

    Args:
        imagen: Imagen MODIS MOD09GA/MYD09GA

    Returns:
        ee.Image: Imagen RGB false color
    """
    return imagen.select([
        BANDAS_MODIS_REFLECTANCIA['azul'],
        BANDAS_MODIS_REFLECTANCIA['swir_1'],
        BANDAS_MODIS_REFLECTANCIA['swir_2']
    ]).rename(['R', 'G', 'B'])


def obtener_vis_params_modis_true_color() -> Dict[str, Any]:
    """Retorna parámetros de visualización para MODIS true color."""
    return VIS_MODIS_TRUE_COLOR


def obtener_vis_params_modis_false_color() -> Dict[str, Any]:
    """Retorna parámetros de visualización para MODIS false color nieve."""
    return VIS_MODIS_FALSE_COLOR_NIEVE


# =============================================================================
# PRODUCTOS MODIS NDSI (Nieve)
# =============================================================================

def obtener_imagen_modis_ndsi(
    roi: ee.Geometry,
    satelite: str = 'terra'
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Obtiene imagen de cobertura de nieve NDSI de MODIS.

    Args:
        roi: Región de interés
        satelite: 'terra' o 'aqua'

    Returns:
        Tuple: (imagen, metadatos)
    """
    coleccion = (COLECCION_MODIS_NIEVE_TERRA
                 if satelite == 'terra'
                 else COLECCION_MODIS_NIEVE_AQUA)
    return obtener_imagen_mas_reciente(coleccion, roi, DIAS_BUSQUEDA_MODIS)


def aplicar_mascara_nubes_ndsi(imagen: ee.Image) -> ee.Image:
    """
    Aplica máscara al producto NDSI: retiene solo píxeles con datos válidos (0-100).
    Valores > 100 son fill/nubes/agua/sin-decisión y se enmascaran.

    Args:
        imagen: Imagen MOD10A1/MYD10A1

    Returns:
        ee.Image: Imagen con solo píxeles válidos (0-100)
    """
    ndsi = imagen.select(BANDAS_MODIS_NIEVE['ndsi_snow_cover'])
    # Solo mantener píxeles con valores válidos de cobertura de nieve (0-100)
    mascara = ndsi.lte(100)
    return imagen.updateMask(mascara)


def procesar_modis_ndsi(imagen: ee.Image) -> ee.Image:
    """
    Procesa imagen MODIS para cobertura de nieve NDSI.

    Args:
        imagen: Imagen MOD10A1/MYD10A1

    Returns:
        ee.Image: Banda NDSI_Snow_Cover (0-100%)
    """
    return imagen.select([BANDAS_MODIS_NIEVE['ndsi_snow_cover']]).rename(['NDSI'])


def obtener_vis_params_ndsi() -> Dict[str, Any]:
    """Retorna parámetros de visualización para NDSI."""
    return VIS_NDSI_SNOW


# =============================================================================
# PRODUCTOS MODIS LST (Temperatura Superficial)
# =============================================================================

def obtener_imagen_modis_lst(
    roi: ee.Geometry
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Obtiene imagen de temperatura superficial LST de MODIS.

    Args:
        roi: Región de interés

    Returns:
        Tuple: (imagen, metadatos)
    """
    return obtener_imagen_mas_reciente(COLECCION_MODIS_LST, roi, DIAS_BUSQUEDA_MODIS)


def procesar_modis_lst_celsius(imagen: ee.Image, periodo: str = 'dia') -> ee.Image:
    """
    Procesa imagen MODIS LST y convierte a Celsius.

    Args:
        imagen: Imagen MOD11A1
        periodo: 'dia' o 'noche'

    Returns:
        ee.Image: Temperatura en Celsius
    """
    banda = (BANDAS_MODIS_LST['lst_dia']
             if periodo == 'dia'
             else BANDAS_MODIS_LST['lst_noche'])

    # Enmascarar píxeles de relleno (valor 0 = sin datos en MOD11A1)
    banda_img = imagen.select([banda])
    mascara_fill = banda_img.gt(0)
    lst_kelvin = banda_img.updateMask(mascara_fill).multiply(LST_FACTOR_ESCALA)
    lst_celsius = lst_kelvin.subtract(KELVIN_A_CELSIUS)

    return lst_celsius.rename(['LST_Celsius'])


def obtener_vis_params_lst() -> Dict[str, Any]:
    """Retorna parámetros de visualización para LST."""
    return VIS_LST


# =============================================================================
# PRODUCTOS ERA5-LAND (Gap-Filler)
# =============================================================================

def obtener_imagen_era5(
    roi: ee.Geometry,
    fecha_objetivo: Optional[datetime] = None
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Obtiene datos ERA5-Land para el ROI.
    ERA5 es el gap-filler continuo sin problemas de nubes.

    Args:
        roi: Región de interés
        fecha_objetivo: Fecha específica a buscar (opcional)

    Returns:
        Tuple: (imagen, metadatos)
    """
    return obtener_imagen_mas_reciente(COLECCION_ERA5_LAND, roi, DIAS_BUSQUEDA_ERA5)


def procesar_era5_nieve(imagen: ee.Image) -> ee.Image:
    """
    Procesa datos de nieve de ERA5-Land.

    Args:
        imagen: Imagen ERA5-Land

    Returns:
        ee.Image: Bandas de nieve (profundidad, SWE, cobertura)
    """
    return imagen.select([
        BANDAS_ERA5['snow_depth'],
        BANDAS_ERA5['swe'],
        BANDAS_ERA5['snow_cover']
    ]).rename(['snow_depth_m', 'swe_m', 'snow_cover_frac'])


def procesar_era5_temperatura(imagen: ee.Image) -> ee.Image:
    """
    Procesa temperatura de ERA5-Land y convierte a Celsius.

    Args:
        imagen: Imagen ERA5-Land

    Returns:
        ee.Image: Temperatura a 2m en Celsius
    """
    temp_kelvin = imagen.select([BANDAS_ERA5['temp_2m']])
    temp_celsius = temp_kelvin.subtract(KELVIN_A_CELSIUS)
    return temp_celsius.rename(['temp_2m_celsius'])


def obtener_vis_params_era5_snow() -> Dict[str, Any]:
    """Retorna parámetros de visualización para ERA5 snow depth."""
    return VIS_ERA5_SNOW_DEPTH


# =============================================================================
# PRODUCTOS SENTINEL-2 (Alta Resolución Oportunística)
# =============================================================================

def obtener_imagen_sentinel2(
    roi: ee.Geometry,
    max_nubes: int = 60
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Busca imagen Sentinel-2 reciente de alta resolución.
    Sentinel-2 no es diario pero ofrece 10m de resolución.

    Args:
        roi: Región de interés
        max_nubes: Máximo porcentaje de nubes permitido

    Returns:
        Tuple: (imagen, metadatos)
    """
    filtro_nubes = ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_nubes)
    return obtener_imagen_mas_reciente(
        COLECCION_SENTINEL2,
        roi,
        DIAS_BUSQUEDA_SENTINEL2,
        filtros_adicionales=[filtro_nubes]
    )


def calcular_ndsi_sentinel2(imagen: ee.Image) -> ee.Image:
    """
    Calcula NDSI manualmente para Sentinel-2.
    NDSI = (Green - SWIR1) / (Green + SWIR1)

    Args:
        imagen: Imagen Sentinel-2

    Returns:
        ee.Image: NDSI escalado a 0-100
    """
    green = imagen.select('B3')
    swir1 = imagen.select('B11')

    ndsi = green.subtract(swir1).divide(green.add(swir1))
    # Escalar a 0-100 para compatibilidad con MODIS
    ndsi_scaled = ndsi.add(1).multiply(50)

    return ndsi_scaled.rename(['NDSI_S2'])


def obtener_cobertura_nieve_sentinel2(imagen: ee.Image) -> ee.Image:
    """
    Obtiene cobertura de nieve desde Scene Classification Layer.
    SCL valor 11 = nieve/hielo.

    Args:
        imagen: Imagen Sentinel-2

    Returns:
        ee.Image: Máscara binaria de nieve
    """
    scl = imagen.select('SCL')
    mascara_nieve = scl.eq(11)
    return mascara_nieve.rename(['snow_mask'])


# =============================================================================
# FUNCIÓN PRINCIPAL DE OBTENCIÓN DE PRODUCTOS
# =============================================================================

def obtener_todos_los_productos(
    latitud: float,
    longitud: float,
    tipo_captura: str,
    config_fuentes: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Obtiene todos los productos satelitales para una ubicación y captura.

    Args:
        latitud: Latitud del punto central
        longitud: Longitud del punto central
        tipo_captura: 'manana', 'tarde', 'noche'
        config_fuentes: Configuración de fuentes de la ubicación

    Returns:
        dict: Productos obtenidos con estructura:
            - visual: {imagen, metadatos, vis_params}
            - false_color: {imagen, metadatos, vis_params}
            - ndsi: {imagen, metadatos, vis_params}
            - lst: {imagen, metadatos, vis_params}
            - era5: {imagen, metadatos, vis_params}
            - sentinel2: {disponible, metadatos} (oportunístico)
    """
    roi = crear_roi(latitud, longitud)
    productos = {}
    es_nocturno = tipo_captura == 'noche'

    fuente_principal = config_fuentes.get('fuente_principal', 'MODIS')

    # =========== PRODUCTOS VISUALES (solo diurno) ===========
    if not es_nocturno:
        # Intentar fuente principal primero
        if fuente_principal.startswith('GOES'):
            imagen, meta = obtener_imagen_goes(roi, fuente_principal)
            if imagen:
                productos['visual'] = {
                    'imagen': procesar_goes_visual(imagen),
                    'metadatos': meta,
                    'vis_params': obtener_vis_params_goes_visual(),
                    'fuente': fuente_principal,
                }
                logger.info(f"Visual obtenido de {fuente_principal}")

        # Fallback a MODIS si no hay GOES o no es disponible
        if 'visual' not in productos:
            imagen, meta = obtener_imagen_modis_reflectancia(roi, 'terra')
            if imagen:
                imagen_masked = aplicar_mascara_nubes_modis(imagen)
                productos['visual'] = {
                    'imagen': procesar_modis_true_color(imagen_masked),
                    'metadatos': meta,
                    'vis_params': obtener_vis_params_modis_true_color(),
                    'fuente': 'MODIS_Terra',
                }
                # También generar false color nieve
                productos['false_color'] = {
                    'imagen': procesar_modis_false_color_nieve(imagen_masked),
                    'metadatos': meta,
                    'vis_params': obtener_vis_params_modis_false_color(),
                    'fuente': 'MODIS_Terra',
                }
                logger.info("Visual y false color obtenidos de MODIS Terra")

        # =========== NDSI (solo diurno) ===========
        imagen_ndsi, meta_ndsi = obtener_imagen_modis_ndsi(roi, 'terra')
        if imagen_ndsi:
            imagen_ndsi_masked = aplicar_mascara_nubes_ndsi(imagen_ndsi)
            productos['ndsi'] = {
                'imagen': procesar_modis_ndsi(imagen_ndsi_masked),
                # Banda cruda sin máscara para calcular % nubes (valor 250 = nube)
                'imagen_raw': imagen_ndsi.select([BANDAS_MODIS_NIEVE['ndsi_snow_cover']]),
                'metadatos': meta_ndsi,
                'vis_params': obtener_vis_params_ndsi(),
                'fuente': 'MODIS_Terra',
            }
            logger.info("NDSI obtenido de MODIS Terra")

    # =========== LST (día y noche) ===========
    imagen_lst, meta_lst = obtener_imagen_modis_lst(roi)
    if imagen_lst:
        periodo = 'noche' if es_nocturno else 'dia'
        productos['lst'] = {
            'imagen': procesar_modis_lst_celsius(imagen_lst, periodo),
            'metadatos': meta_lst,
            'vis_params': obtener_vis_params_lst(),
            'fuente': 'MODIS_LST',
            'periodo': periodo,
        }
        logger.info(f"LST {periodo} obtenido de MODIS")

    # =========== ERA5-LAND (siempre, gap-filler) ===========
    imagen_era5, meta_era5 = obtener_imagen_era5(roi)
    if imagen_era5:
        productos['era5'] = {
            'imagen_nieve': procesar_era5_nieve(imagen_era5),
            'imagen_temp': procesar_era5_temperatura(imagen_era5),
            'metadatos': meta_era5,
            'vis_params': obtener_vis_params_era5_snow(),
            'fuente': 'ERA5-Land',
        }
        logger.info("ERA5-Land obtenido como gap-filler")

    # =========== SENTINEL-2 (oportunístico, alta resolución) ===========
    imagen_s2, meta_s2 = obtener_imagen_sentinel2(roi)
    if imagen_s2:
        productos['sentinel2'] = {
            'disponible': True,
            'imagen_ndsi': calcular_ndsi_sentinel2(imagen_s2),
            'imagen_nieve': obtener_cobertura_nieve_sentinel2(imagen_s2),
            'metadatos': meta_s2,
            'fuente': 'Sentinel-2',
        }
        logger.info("Sentinel-2 disponible como imagen de alta resolución")
    else:
        productos['sentinel2'] = {
            'disponible': False,
            'metadatos': meta_s2,
        }

    return productos

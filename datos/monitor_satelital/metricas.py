"""
Monitor Satelital de Nieve - Cálculo de Métricas

Funciones para calcular métricas estadísticas sobre los productos
satelitales que se almacenarán en BigQuery (capa Silver).

Versión 1.1: Incluye indicadores de nieve, SAR y viento en altura.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

import ee

from constantes import (
    UMBRAL_NUBES_NUBLADO,
    UMBRAL_NDSI_NIEVE,
    NDSI_VALOR_NUBE,
    NDSI_VALOR_NOCHE,
    KELVIN_A_CELSIUS,
)

# Importar nuevos módulos de métricas
from indicadores_nieve import compilar_indicadores_nieve
from sentinel1_sar import obtener_productos_sar
from viento_altura import compilar_metricas_viento_bigquery


logger = logging.getLogger(__name__)


# =============================================================================
# MÉTRICAS DE NUBES
# =============================================================================

def calcular_porcentaje_nubes(
    imagen_ndsi: ee.Image,
    roi: ee.Geometry,
    escala: int = 500
) -> float:
    """
    Calcula el porcentaje de cobertura de nubes en el tile.

    Usa el producto NDSI donde valor 250 indica nubes.

    Args:
        imagen_ndsi: Imagen MODIS NDSI (sin máscara aplicada)
        roi: Región de interés
        escala: Escala de reducción en metros

    Returns:
        float: Porcentaje de nubes (0-100)
    """
    try:
        # Contar píxeles nublados (valor 250)
        mascara_nubes = imagen_ndsi.eq(NDSI_VALOR_NUBE)

        # Calcular media de la máscara (proporción de nubes)
        stats = mascara_nubes.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        # La media de una máscara binaria da la proporción
        proporcion = stats.get('NDSI_Snow_Cover', 0) or 0
        porcentaje = proporcion * 100

        logger.info(f"Porcentaje de nubes calculado: {porcentaje:.1f}%")
        return round(porcentaje, 2)

    except Exception as e:
        logger.error(f"Error al calcular porcentaje de nubes: {str(e)}")
        return -1.0


# =============================================================================
# MÉTRICAS NDSI
# =============================================================================

def calcular_metricas_ndsi(
    imagen_ndsi: ee.Image,
    roi: ee.Geometry,
    escala: int = 500
) -> Dict[str, Optional[float]]:
    """
    Calcula métricas de cobertura de nieve NDSI.

    Args:
        imagen_ndsi: Imagen NDSI procesada (0-100)
        roi: Región de interés
        escala: Escala de reducción en metros

    Returns:
        dict: Métricas calculadas:
            - ndsi_medio: NDSI promedio en píxeles válidos
            - ndsi_max: NDSI máximo
            - pct_cobertura_nieve: % del tile con nieve (NDSI >= 40)
            - tiene_nieve: bool
    """
    try:
        # Reducir para obtener estadísticas
        stats = imagen_ndsi.reduceRegion(
            reducer=ee.Reducer.mean().combine(
                ee.Reducer.max(), sharedInputs=True
            ),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        ndsi_medio = stats.get('NDSI_mean')
        ndsi_max = stats.get('NDSI_max')

        # Calcular cobertura de nieve (NDSI >= umbral)
        mascara_nieve = imagen_ndsi.gte(UMBRAL_NDSI_NIEVE)
        stats_nieve = mascara_nieve.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        pct_nieve = (stats_nieve.get('NDSI', 0) or 0) * 100

        metricas = {
            'ndsi_medio': round(ndsi_medio, 2) if ndsi_medio is not None else None,
            'ndsi_max': round(ndsi_max, 2) if ndsi_max is not None else None,
            'pct_cobertura_nieve': round(pct_nieve, 2),
            'tiene_nieve': pct_nieve > 0,
        }

        logger.info(
            f"Métricas NDSI: medio={metricas['ndsi_medio']}, "
            f"max={metricas['ndsi_max']}, cobertura={metricas['pct_cobertura_nieve']}%"
        )

        return metricas

    except Exception as e:
        logger.error(f"Error al calcular métricas NDSI: {str(e)}")
        return {
            'ndsi_medio': None,
            'ndsi_max': None,
            'pct_cobertura_nieve': None,
            'tiene_nieve': None,
        }


# =============================================================================
# MÉTRICAS LST
# =============================================================================

def calcular_metricas_lst(
    imagen_lst: ee.Image,
    roi: ee.Geometry,
    escala: int = 1000
) -> Dict[str, Optional[float]]:
    """
    Calcula métricas de temperatura superficial LST.

    Args:
        imagen_lst: Imagen LST en Celsius
        roi: Región de interés
        escala: Escala de reducción en metros

    Returns:
        dict: Métricas calculadas:
            - lst_media_celsius: Temperatura media
            - lst_min_celsius: Temperatura mínima
            - lst_max_celsius: Temperatura máxima
    """
    try:
        stats = imagen_lst.reduceRegion(
            reducer=ee.Reducer.mean().combine(
                ee.Reducer.min(), sharedInputs=True
            ).combine(
                ee.Reducer.max(), sharedInputs=True
            ),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        metricas = {
            'lst_media_celsius': round(stats.get('LST_Celsius_mean', 0) or 0, 2),
            'lst_min_celsius': round(stats.get('LST_Celsius_min', 0) or 0, 2),
            'lst_max_celsius': round(stats.get('LST_Celsius_max', 0) or 0, 2),
        }

        logger.info(
            f"Métricas LST: media={metricas['lst_media_celsius']}°C, "
            f"min={metricas['lst_min_celsius']}°C, max={metricas['lst_max_celsius']}°C"
        )

        return metricas

    except Exception as e:
        logger.error(f"Error al calcular métricas LST: {str(e)}")
        return {
            'lst_media_celsius': None,
            'lst_min_celsius': None,
            'lst_max_celsius': None,
        }


# =============================================================================
# MÉTRICAS ERA5
# =============================================================================

def calcular_metricas_era5(
    imagen_nieve: ee.Image,
    imagen_temp: ee.Image,
    roi: ee.Geometry,
    escala: int = 11000
) -> Dict[str, Optional[float]]:
    """
    Calcula métricas de ERA5-Land.

    Args:
        imagen_nieve: Imagen ERA5 con bandas de nieve
        imagen_temp: Imagen ERA5 con temperatura
        roi: Región de interés
        escala: Escala de reducción en metros

    Returns:
        dict: Métricas calculadas:
            - era5_snow_depth_m: Profundidad de nieve (metros)
            - era5_swe_m: Snow Water Equivalent (metros)
            - era5_snow_cover: Fracción de cobertura (0-1)
            - era5_temp_2m_celsius: Temperatura a 2m
    """
    try:
        # Métricas de nieve
        stats_nieve = imagen_nieve.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        # Métricas de temperatura
        stats_temp = imagen_temp.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        metricas = {
            'era5_snow_depth_m': round(stats_nieve.get('snow_depth_m', 0) or 0, 4),
            'era5_swe_m': round(stats_nieve.get('swe_m', 0) or 0, 4),
            'era5_snow_cover': round(stats_nieve.get('snow_cover_frac', 0) or 0, 4),
            'era5_temp_2m_celsius': round(stats_temp.get('temp_2m_celsius', 0) or 0, 2),
        }

        logger.info(
            f"Métricas ERA5: snow_depth={metricas['era5_snow_depth_m']}m, "
            f"temp={metricas['era5_temp_2m_celsius']}°C"
        )

        return metricas

    except Exception as e:
        logger.error(f"Error al calcular métricas ERA5: {str(e)}")
        return {
            'era5_snow_depth_m': None,
            'era5_swe_m': None,
            'era5_snow_cover': None,
            'era5_temp_2m_celsius': None,
        }


# =============================================================================
# MÉTRICAS SENTINEL-2
# =============================================================================

def calcular_metricas_sentinel2(
    imagen_ndsi: ee.Image,
    imagen_nieve: ee.Image,
    roi: ee.Geometry,
    escala: int = 20
) -> Dict[str, Optional[float]]:
    """
    Calcula métricas de Sentinel-2 cuando está disponible.

    Args:
        imagen_ndsi: NDSI calculado de Sentinel-2
        imagen_nieve: Máscara de nieve del SCL
        roi: Región de interés
        escala: Escala de reducción en metros

    Returns:
        dict: Métricas calculadas:
            - sentinel2_pct_nieve: % de cobertura de nieve según SCL
    """
    try:
        # Porcentaje de nieve según Scene Classification Layer
        stats_nieve = imagen_nieve.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        pct_nieve = (stats_nieve.get('snow_mask', 0) or 0) * 100

        metricas = {
            'sentinel2_pct_nieve': round(pct_nieve, 2),
        }

        logger.info(f"Métricas Sentinel-2: cobertura_nieve={pct_nieve:.1f}%")

        return metricas

    except Exception as e:
        logger.error(f"Error al calcular métricas Sentinel-2: {str(e)}")
        return {
            'sentinel2_pct_nieve': None,
        }


# =============================================================================
# MÉTRICAS ALBEDO
# =============================================================================

def calcular_albedo_nieve(
    imagen_ndsi: ee.Image,
    imagen_albedo: ee.Image,
    roi: ee.Geometry,
    escala: int = 500
) -> Optional[float]:
    """
    Calcula el albedo promedio en zonas de nieve.

    Args:
        imagen_ndsi: Imagen NDSI para identificar nieve
        imagen_albedo: Imagen con banda Snow_Albedo_Daily_Tile
        roi: Región de interés
        escala: Escala de reducción

    Returns:
        float o None: Albedo promedio en zonas de nieve (1-100%)
    """
    try:
        # Máscara de nieve (NDSI >= umbral)
        mascara_nieve = imagen_ndsi.gte(UMBRAL_NDSI_NIEVE)

        # Aplicar máscara al albedo
        albedo_enmascarado = imagen_albedo.updateMask(mascara_nieve)

        stats = albedo_enmascarado.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e9
        ).getInfo()

        albedo = stats.get('Snow_Albedo_Daily_Tile')

        if albedo is not None:
            logger.info(f"Albedo de nieve promedio: {albedo:.1f}%")
            return round(albedo, 2)

        return None

    except Exception as e:
        logger.error(f"Error al calcular albedo: {str(e)}")
        return None


# =============================================================================
# COMPILACIÓN DE MÉTRICAS
# =============================================================================

def compilar_metricas_completas(
    productos: Dict[str, Any],
    roi: ee.Geometry,
    tipo_captura: str,
    latitud: float,
    longitud: float,
    fecha_captura: datetime
) -> Dict[str, Any]:
    """
    Compila todas las métricas de los productos obtenidos.

    Versión 1.1: Incluye indicadores de nieve, SAR y viento.

    Args:
        productos: Diccionario con productos satelitales
        roi: Región de interés
        tipo_captura: 'manana', 'tarde', 'noche'
        latitud: Latitud del punto
        longitud: Longitud del punto
        fecha_captura: Fecha de la captura

    Returns:
        dict: Todas las métricas para BigQuery
    """
    metricas = {
        # Métricas originales
        'pct_nubes': None,
        'es_nublado': None,
        'tiene_nieve': None,
        'ndsi_medio': None,
        'ndsi_max': None,
        'pct_cobertura_nieve': None,
        'albedo_nieve_medio': None,

        # Snowline y cambio de cobertura
        'snowline_elevacion_m': None,
        'snowline_mediana_m': None,
        'snowline_cambio_24h_m': None,
        'snowline_cambio_72h_m': None,
        'delta_pct_nieve_24h': None,
        'delta_pct_nieve_72h': None,
        'tipo_cambio_nieve': None,
        'tasa_cambio_nieve_dia': None,

        # LST y ciclo diurno
        'lst_dia_celsius': None,
        'lst_noche_celsius': None,
        'lst_min_celsius': None,
        'ciclo_diurno_amplitud': None,

        # AMI (Accumulated Melting Index)
        'ami_3d': None,
        'ami_7d': None,

        # ERA5
        'era5_snow_depth_m': None,
        'era5_swe_m': None,
        'era5_snow_cover': None,
        'era5_temp_2m_celsius': None,
        'era5_snowfall_m': None,
        'era5_swe_anomalia': None,

        # Sentinel-2
        'sentinel2_disponible': False,
        'sentinel2_fecha': None,
        'sentinel2_pct_nieve': None,

        # SAR (Sentinel-1)
        'sar_disponible': False,
        'sar_fecha': None,
        'sar_orbita': None,
        'sar_pct_nieve_humeda': None,
        'sar_pct_nieve_seca': None,
        'sar_vv_medio_db': None,
        'sar_delta_vv_db': None,

        # Viento en altura
        'viento_altura_vel_ms': None,
        'viento_altura_vel_kmh': None,
        'viento_altura_dir_grados': None,
        'viento_max_24h_ms': None,
        'transporte_eolico_activo': None,
        'aspecto_carga_eolica': None,
    }

    es_nocturno = tipo_captura == 'noche'
    imagen_ndsi = None
    lst_dia = None
    lst_noche = None

    # NDSI y nubes (solo diurno)
    if not es_nocturno and 'ndsi' in productos:
        producto_ndsi = productos['ndsi']
        if producto_ndsi.get('imagen'):
            imagen_ndsi = producto_ndsi['imagen']
            metricas_ndsi = calcular_metricas_ndsi(imagen_ndsi, roi)
            metricas.update(metricas_ndsi)

            # Porcentaje de nubes desde banda cruda (valor 250 = nube)
            if producto_ndsi.get('imagen_raw'):
                pct_nubes = calcular_porcentaje_nubes(producto_ndsi['imagen_raw'], roi)
                metricas['pct_nubes'] = pct_nubes if pct_nubes >= 0 else None

    # LST
    if 'lst' in productos:
        producto_lst = productos['lst']
        if producto_lst.get('imagen'):
            metricas_lst = calcular_metricas_lst(producto_lst['imagen'], roi)

            periodo = producto_lst.get('periodo', 'dia')
            if periodo == 'dia':
                metricas['lst_dia_celsius'] = metricas_lst.get('lst_media_celsius')
                lst_dia = metricas['lst_dia_celsius']
            else:
                metricas['lst_noche_celsius'] = metricas_lst.get('lst_media_celsius')
                lst_noche = metricas['lst_noche_celsius']

            metricas['lst_min_celsius'] = metricas_lst.get('lst_min_celsius')

    # Calcular ciclo diurno si tenemos ambas temperaturas
    if lst_dia is not None and lst_noche is not None:
        metricas['ciclo_diurno_amplitud'] = round(lst_dia - lst_noche, 2)

    # ERA5
    if 'era5' in productos:
        producto_era5 = productos['era5']
        if producto_era5.get('imagen_nieve') and producto_era5.get('imagen_temp'):
            metricas_era5 = calcular_metricas_era5(
                producto_era5['imagen_nieve'],
                producto_era5['imagen_temp'],
                roi
            )
            metricas.update(metricas_era5)

    # Sentinel-2
    if 'sentinel2' in productos and productos['sentinel2'].get('disponible'):
        producto_s2 = productos['sentinel2']
        metricas['sentinel2_disponible'] = True

        if producto_s2.get('metadatos', {}).get('fecha_captura'):
            metricas['sentinel2_fecha'] = producto_s2['metadatos']['fecha_captura'][:10]

        if producto_s2.get('imagen_ndsi') and producto_s2.get('imagen_nieve'):
            metricas_s2 = calcular_metricas_sentinel2(
                producto_s2['imagen_ndsi'],
                producto_s2['imagen_nieve'],
                roi
            )
            metricas.update(metricas_s2)

    # Determinar si está nublado
    if metricas['pct_nubes'] is not None:
        metricas['es_nublado'] = metricas['pct_nubes'] >= UMBRAL_NUBES_NUBLADO

    # =========================================================================
    # NUEVOS INDICADORES v1.1
    # =========================================================================

    # Indicadores de nieve (snowline, cambio cobertura, AMI)
    try:
        if imagen_ndsi is not None:
            indicadores_nieve = compilar_indicadores_nieve(
                imagen_ndsi=imagen_ndsi,
                roi=roi,
                latitud=latitud,
                longitud=longitud,
                lst_dia_celsius=lst_dia,
                lst_noche_celsius=lst_noche,
                fecha_captura=fecha_captura
            )
            # Actualizar solo campos que tienen valor
            for campo, valor in indicadores_nieve.items():
                if valor is not None and campo in metricas:
                    metricas[campo] = valor

            logger.info("Indicadores de nieve calculados exitosamente")

    except Exception as e:
        logger.warning(f"No se pudieron calcular indicadores de nieve: {str(e)}")

    # SAR (Sentinel-1) - funciona de noche y con nubes
    try:
        tiene_nieve = metricas.get('tiene_nieve', False)
        if tiene_nieve:
            productos_sar = obtener_productos_sar(
                latitud=latitud,
                longitud=longitud,
                fecha_captura=fecha_captura
            )

            if productos_sar.get('disponible'):
                metricas['sar_disponible'] = True
                metricas['sar_fecha'] = productos_sar.get('fecha_imagen')
                metricas['sar_orbita'] = productos_sar.get('orbita')
                metricas['sar_pct_nieve_humeda'] = productos_sar.get('pct_nieve_humeda')
                metricas['sar_pct_nieve_seca'] = productos_sar.get('pct_nieve_seca')
                metricas['sar_vv_medio_db'] = productos_sar.get('vv_medio_db')
                metricas['sar_delta_vv_db'] = productos_sar.get('delta_vv_db')

                val = metricas['sar_pct_nieve_humeda']
                logger.info(
                    f"SAR: {val:.1f}% nieve húmeda" if val is not None else "SAR: disponible"
                )

    except Exception as e:
        logger.warning(f"No se pudieron obtener productos SAR: {str(e)}")

    # Viento en altura (ERA5 pressure levels)
    try:
        tiene_nieve = metricas.get('tiene_nieve', False)
        metricas_viento = compilar_metricas_viento_bigquery(
            latitud=latitud,
            longitud=longitud,
            tiene_nieve=tiene_nieve,
            fecha=fecha_captura
        )

        # Actualizar métricas de viento
        if metricas_viento.get('viento_altura_vel_ms') is not None:
            metricas['viento_altura_vel_ms'] = metricas_viento.get('viento_altura_vel_ms')
            # Calcular km/h
            metricas['viento_altura_vel_kmh'] = round(
                metricas['viento_altura_vel_ms'] * 3.6, 1
            )
            metricas['viento_altura_dir_grados'] = metricas_viento.get('viento_altura_dir_grados')
            metricas['transporte_eolico_activo'] = metricas_viento.get('transporte_eolico_activo')
            metricas['aspecto_carga_eolica'] = metricas_viento.get('aspecto_carga_eolica')

        if metricas_viento.get('viento_max_24h_ms') is not None:
            metricas['viento_max_24h_ms'] = metricas_viento.get('viento_max_24h_ms')

        logger.info("Métricas de viento en altura calculadas")

    except Exception as e:
        logger.warning(f"No se pudieron calcular métricas de viento: {str(e)}")

    # Log resumen
    campos_con_datos = len([v for v in metricas.values() if v is not None])
    logger.info(f"Métricas compiladas: {campos_con_datos} campos con datos")

    return metricas


# =============================================================================
# CREACIÓN DE FILA BIGQUERY
# =============================================================================

def crear_fila_bigquery(
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    region: str,
    fecha_captura: datetime,
    tipo_captura: str,
    timestamp_imagen: datetime,
    timestamp_descarga: datetime,
    fuente_principal: str,
    coleccion_gee: str,
    resolucion_m: int,
    metricas: Dict[str, Any],
    uris: Dict[str, str]
) -> Dict[str, Any]:
    """
    Crea una fila completa para insertar en BigQuery.

    Versión 1.1: Incluye todos los nuevos campos de indicadores.

    Args:
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud
        longitud: Longitud
        region: Región geográfica
        fecha_captura: Fecha de la captura
        tipo_captura: 'manana', 'tarde', 'noche'
        timestamp_imagen: Timestamp de la imagen satelital
        timestamp_descarga: Momento de la descarga
        fuente_principal: Fuente usada
        coleccion_gee: ID de colección GEE
        resolucion_m: Resolución espacial
        metricas: Métricas calculadas
        uris: URIs de archivos en GCS

    Returns:
        dict: Fila lista para BigQuery
    """
    # Calcular antigüedad
    antiguedad_horas = (timestamp_descarga - timestamp_imagen).total_seconds() / 3600

    fila = {
        # Identificación y ubicación
        'nombre_ubicacion': nombre_ubicacion,
        'latitud': latitud,
        'longitud': longitud,
        'region': region,

        # Temporalidad
        'fecha_captura': fecha_captura.strftime('%Y-%m-%d'),
        'tipo_captura': tipo_captura,
        'timestamp_imagen': timestamp_imagen.isoformat(),
        'timestamp_descarga': timestamp_descarga.isoformat(),
        'antiguedad_horas': round(antiguedad_horas, 2),

        # Fuente
        'fuente_principal': fuente_principal,
        'coleccion_gee': coleccion_gee,
        'resolucion_m': resolucion_m,

        # Métricas de nubes y cobertura básica
        'pct_nubes': metricas.get('pct_nubes'),
        'es_nublado': metricas.get('es_nublado'),
        'tiene_nieve': metricas.get('tiene_nieve'),
        'ndsi_medio': metricas.get('ndsi_medio'),
        'ndsi_max': metricas.get('ndsi_max'),
        'pct_cobertura_nieve': metricas.get('pct_cobertura_nieve'),
        'albedo_nieve_medio': metricas.get('albedo_nieve_medio'),

        # Snowline y cambio de cobertura
        'snowline_elevacion_m': metricas.get('snowline_elevacion_m'),
        'snowline_mediana_m': metricas.get('snowline_mediana_m'),
        'snowline_cambio_24h_m': metricas.get('snowline_cambio_24h_m'),
        'snowline_cambio_72h_m': metricas.get('snowline_cambio_72h_m'),
        'delta_pct_nieve_24h': metricas.get('delta_pct_nieve_24h'),
        'delta_pct_nieve_72h': metricas.get('delta_pct_nieve_72h'),
        'tipo_cambio_nieve': metricas.get('tipo_cambio_nieve'),
        'tasa_cambio_nieve_dia': metricas.get('tasa_cambio_nieve_dia'),

        # Temperatura superficial
        'lst_dia_celsius': metricas.get('lst_dia_celsius'),
        'lst_noche_celsius': metricas.get('lst_noche_celsius'),
        'lst_min_celsius': metricas.get('lst_min_celsius'),
        'ciclo_diurno_amplitud': metricas.get('ciclo_diurno_amplitud'),

        # AMI (Accumulated Melting Index)
        'ami_3d': metricas.get('ami_3d'),
        'ami_7d': metricas.get('ami_7d'),

        # ERA5
        'era5_snow_depth_m': metricas.get('era5_snow_depth_m'),
        'era5_swe_m': metricas.get('era5_swe_m'),
        'era5_snow_cover': metricas.get('era5_snow_cover'),
        'era5_temp_2m_celsius': metricas.get('era5_temp_2m_celsius'),
        'era5_snowfall_m': metricas.get('era5_snowfall_m'),
        'era5_swe_anomalia': metricas.get('era5_swe_anomalia'),

        # Sentinel-2
        'sentinel2_disponible': metricas.get('sentinel2_disponible', False),
        'sentinel2_fecha': metricas.get('sentinel2_fecha'),
        'sentinel2_pct_nieve': metricas.get('sentinel2_pct_nieve'),

        # SAR (Sentinel-1)
        'sar_disponible': metricas.get('sar_disponible', False),
        'sar_fecha': metricas.get('sar_fecha'),
        'sar_orbita': metricas.get('sar_orbita'),
        'sar_pct_nieve_humeda': metricas.get('sar_pct_nieve_humeda'),
        'sar_pct_nieve_seca': metricas.get('sar_pct_nieve_seca'),
        'sar_vv_medio_db': metricas.get('sar_vv_medio_db'),
        'sar_delta_vv_db': metricas.get('sar_delta_vv_db'),

        # Viento en altura
        'viento_altura_vel_ms': metricas.get('viento_altura_vel_ms'),
        'viento_altura_vel_kmh': metricas.get('viento_altura_vel_kmh'),
        'viento_altura_dir_grados': metricas.get('viento_altura_dir_grados'),
        'viento_max_24h_ms': metricas.get('viento_max_24h_ms'),
        'transporte_eolico_activo': metricas.get('transporte_eolico_activo'),
        'aspecto_carga_eolica': metricas.get('aspecto_carga_eolica'),

        # URIs de archivos
        'uri_geotiff_visual': uris.get('geotiff_visual'),
        'uri_geotiff_ndsi': uris.get('geotiff_ndsi'),
        'uri_geotiff_lst': uris.get('geotiff_lst'),
        'uri_geotiff_era5': uris.get('geotiff_era5'),
        'uri_geotiff_sar': uris.get('geotiff_sar'),
        'uri_preview_visual': uris.get('preview_visual'),
        'uri_preview_ndsi': uris.get('preview_ndsi'),
        'uri_preview_lst': uris.get('preview_lst'),
        'uri_preview_sar': uris.get('preview_sar'),
        'uri_thumbnail_visual': uris.get('thumbnail_visual'),
        'uri_thumbnail_ndsi': uris.get('thumbnail_ndsi'),

        # Versión
        'version_metodologia': 'v1.1.0',
    }

    return fila

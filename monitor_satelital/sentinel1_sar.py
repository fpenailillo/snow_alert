"""
Monitor Satelital de Nieve - Procesamiento Sentinel-1 SAR

Funciones para detección de nieve húmeda/seca usando radar SAR de Sentinel-1.

Principio físico:
- Nieve SECA = transparente al radar → retrodispersión del suelo
- Nieve HÚMEDA = absorbe radar → retrodispersión cae drásticamente
- Transición seca→húmeda = caída de 3-6 dB en banda C (VV)

Importancia para Andes chilenos:
- Durante tormentas (cuando más necesitas monitorear) → óptico ciego, SAR funciona
- Ciclo diurno intenso de fusión-recongelamiento → SAR detecta la transición
- Nieve húmeda = indicador directo de riesgo de avalancha por fusión
- 10m resolución permite ver zonas de inicio específicas (vs 500m MODIS)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

import ee

from constantes import RADIO_TILE_METROS


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES SAR
# =============================================================================

# Colección Sentinel-1 GRD
COLECCION_SENTINEL1 = 'COPERNICUS/S1_GRD'

# Modos y polarizaciones
MODO_INTERFEROMETRICO = 'IW'  # Interferometric Wide Swath (modo estándar)
POLARIZACION_VV = 'VV'        # Vertical-Vertical (sensible a humedad)
POLARIZACION_VH = 'VH'        # Vertical-Horizontal (complementaria)

# Umbrales para detección de nieve húmeda
UMBRAL_WET_SNOW_DB = -3.0     # Caída de 3 dB = nieve húmeda
UMBRAL_WET_SNOW_SEVERO = -6.0 # Caída de 6 dB = nieve muy húmeda

# Días hacia atrás para buscar imagen SAR
DIAS_BUSQUEDA_SAR = 12  # Sentinel-1 revisita cada 6-12 días

# Meses para referencia de nieve seca (por hemisferio)
# Hemisferio Sur: enero-febrero (verano seco en altura)
# Hemisferio Norte: diciembre-febrero (invierno frío)
MESES_REFERENCIA_SECA_SUR = [1, 2]
MESES_REFERENCIA_SECA_NORTE = [12, 1, 2]


# =============================================================================
# FUNCIONES DE BÚSQUEDA DE IMÁGENES SAR
# =============================================================================

def buscar_imagen_sar_reciente(
    latitud: float,
    longitud: float,
    fecha_fin: Optional[datetime] = None,
    dias_busqueda: int = DIAS_BUSQUEDA_SAR
) -> Tuple[Optional[ee.Image], Dict[str, Any]]:
    """
    Busca la imagen Sentinel-1 SAR más reciente para una ubicación.

    Args:
        latitud: Latitud del punto
        longitud: Longitud del punto
        fecha_fin: Fecha límite de búsqueda (default: hoy)
        dias_busqueda: Días hacia atrás para buscar

    Returns:
        Tuple[ee.Image, dict]: Imagen SAR y metadatos, o (None, {})
    """
    try:
        if fecha_fin is None:
            fecha_fin = datetime.utcnow()

        fecha_inicio = fecha_fin - timedelta(days=dias_busqueda)
        punto = ee.Geometry.Point([longitud, latitud])

        # Filtrar colección SAR
        coleccion = (ee.ImageCollection(COLECCION_SENTINEL1)
            .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
            .filterBounds(punto)
            .filter(ee.Filter.eq('instrumentMode', MODO_INTERFEROMETRICO))
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', POLARIZACION_VV))
            .sort('system:time_start', False))

        cantidad = coleccion.size().getInfo()

        if cantidad == 0:
            logger.info(f"No se encontraron imágenes SAR en los últimos {dias_busqueda} días")
            return None, {'disponible': False, 'dias_buscados': dias_busqueda}

        # Obtener la más reciente
        imagen = coleccion.first()
        info = imagen.getInfo()

        # Extraer metadatos
        timestamp_ms = info['properties']['system:time_start']
        fecha_captura = datetime.utcfromtimestamp(timestamp_ms / 1000)
        orbita = info['properties'].get('orbitProperties_pass', 'unknown')

        metadatos = {
            'disponible': True,
            'fecha_captura': fecha_captura.isoformat(),
            'fecha_str': fecha_captura.strftime('%Y-%m-%d'),
            'orbita': orbita,
            'modo': MODO_INTERFEROMETRICO,
            'imagenes_encontradas': cantidad,
        }

        logger.info(
            f"Imagen SAR encontrada: {fecha_captura.strftime('%Y-%m-%d')} "
            f"({orbita}, {cantidad} imágenes disponibles)"
        )

        return imagen, metadatos

    except Exception as e:
        logger.error(f"Error al buscar imagen SAR: {str(e)}")
        return None, {'disponible': False, 'error': str(e)}


def obtener_imagen_referencia_seca(
    latitud: float,
    longitud: float,
    anio: Optional[int] = None
) -> Optional[ee.Image]:
    """
    Obtiene una imagen SAR de referencia de período seco (nieve seca).

    La imagen de referencia se usa para comparar la retrodispersión actual
    y detectar cambios que indican nieve húmeda.

    Args:
        latitud: Latitud del punto
        longitud: Longitud del punto
        anio: Año de la referencia (default: año anterior)

    Returns:
        ee.Image o None: Imagen SAR de referencia
    """
    try:
        if anio is None:
            anio = datetime.utcnow().year - 1

        punto = ee.Geometry.Point([longitud, latitud])

        # Determinar meses de referencia según hemisferio
        if latitud < 0:
            meses = MESES_REFERENCIA_SECA_SUR
        else:
            meses = MESES_REFERENCIA_SECA_NORTE

        # Construir filtro de fechas
        # Para meses como [12, 1, 2], necesitamos manejar el cambio de año
        imagenes = []
        for mes in meses:
            if mes == 12 and 1 in meses:
                # Diciembre del año anterior
                fecha_inicio = f"{anio - 1}-{mes:02d}-01"
                fecha_fin = f"{anio}-01-01"
            else:
                fecha_inicio = f"{anio}-{mes:02d}-01"
                if mes == 12:
                    fecha_fin = f"{anio + 1}-01-01"
                else:
                    fecha_fin = f"{anio}-{mes + 1:02d}-01"

            coleccion_mes = (ee.ImageCollection(COLECCION_SENTINEL1)
                .filterDate(fecha_inicio, fecha_fin)
                .filterBounds(punto)
                .filter(ee.Filter.eq('instrumentMode', MODO_INTERFEROMETRICO))
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', POLARIZACION_VV)))

            imagenes.append(coleccion_mes)

        # Combinar colecciones
        coleccion_total = imagenes[0]
        for col in imagenes[1:]:
            coleccion_total = coleccion_total.merge(col)

        # Crear un composite de mediana (más robusto que media)
        referencia = coleccion_total.median()

        # Verificar que tenemos datos
        bandas = referencia.bandNames().getInfo()
        if 'VV' not in bandas:
            logger.warning("No se pudo obtener imagen de referencia seca")
            return None

        logger.info(f"Imagen de referencia seca obtenida para {anio}")
        return referencia

    except Exception as e:
        logger.error(f"Error al obtener referencia seca: {str(e)}")
        return None


# =============================================================================
# CÁLCULO DE NIEVE HÚMEDA
# =============================================================================

def calcular_wet_snow_index(
    imagen_actual: ee.Image,
    imagen_referencia: ee.Image
) -> ee.Image:
    """
    Calcula el índice de nieve húmeda (Wet Snow Index).

    El WSI es la diferencia de retrodispersión entre la imagen actual
    y la referencia de nieve seca. Valores negativos indican nieve húmeda.

    Método:
    - WSI = VV_actual - VV_referencia
    - Si WSI < -3 dB → nieve húmeda
    - Si WSI < -6 dB → nieve muy húmeda (saturada)

    Args:
        imagen_actual: Imagen SAR actual
        imagen_referencia: Imagen de referencia (nieve seca)

    Returns:
        ee.Image: Imagen con banda 'wet_snow_index' en dB
    """
    try:
        vv_actual = imagen_actual.select('VV')
        vv_referencia = imagen_referencia.select('VV')

        # Calcular diferencia (ya están en dB)
        wet_snow_index = vv_actual.subtract(vv_referencia).rename('wet_snow_index')

        return wet_snow_index

    except Exception as e:
        logger.error(f"Error al calcular wet snow index: {str(e)}")
        raise


def crear_mascara_nieve_humeda(
    wet_snow_index: ee.Image,
    umbral_db: float = UMBRAL_WET_SNOW_DB
) -> ee.Image:
    """
    Crea una máscara binaria de nieve húmeda basada en el WSI.

    Args:
        wet_snow_index: Imagen con wet snow index
        umbral_db: Umbral en dB para clasificar como nieve húmeda

    Returns:
        ee.Image: Máscara binaria (1 = nieve húmeda, 0 = no)
    """
    return wet_snow_index.lt(umbral_db).rename('wet_snow_mask')


def calcular_metricas_sar(
    imagen_sar: ee.Image,
    imagen_referencia: Optional[ee.Image],
    roi: ee.Geometry,
    escala: int = 100  # SAR tiene ~10m resolución, usar escala mayor para eficiencia
) -> Dict[str, Any]:
    """
    Calcula métricas SAR para detección de nieve húmeda.

    Args:
        imagen_sar: Imagen SAR actual
        imagen_referencia: Imagen de referencia seca (opcional)
        roi: Región de interés
        escala: Escala de reducción en metros

    Returns:
        dict: Métricas SAR:
            - sar_vv_medio_db: Retrodispersión VV media (dB)
            - sar_delta_vv_db: Cambio VV vs referencia (dB)
            - sar_pct_nieve_humeda: % del tile con nieve húmeda
            - sar_pct_nieve_muy_humeda: % con nieve muy húmeda (>6dB caída)
    """
    try:
        # Estadísticas VV actual
        stats_vv = imagen_sar.select('VV').reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()

        vv_medio = stats_vv.get('VV')

        resultado = {
            'sar_vv_medio_db': round(vv_medio, 2) if vv_medio is not None else None,
            'sar_delta_vv_db': None,
            'sar_pct_nieve_humeda': None,
            'sar_pct_nieve_muy_humeda': None,
        }

        # Si tenemos referencia, calcular métricas de cambio
        if imagen_referencia is not None:
            # Calcular wet snow index
            wsi = calcular_wet_snow_index(imagen_sar, imagen_referencia)

            # Delta medio
            stats_wsi = wsi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=escala,
                maxPixels=1e8
            ).getInfo()

            resultado['sar_delta_vv_db'] = round(
                stats_wsi.get('wet_snow_index', 0) or 0, 2
            )

            # Porcentaje nieve húmeda (WSI < -3 dB)
            mascara_humeda = wsi.lt(UMBRAL_WET_SNOW_DB)
            stats_humeda = mascara_humeda.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=escala,
                maxPixels=1e8
            ).getInfo()

            resultado['sar_pct_nieve_humeda'] = round(
                (stats_humeda.get('wet_snow_index', 0) or 0) * 100, 2
            )

            # Porcentaje nieve muy húmeda (WSI < -6 dB)
            mascara_muy_humeda = wsi.lt(UMBRAL_WET_SNOW_SEVERO)
            stats_muy_humeda = mascara_muy_humeda.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=escala,
                maxPixels=1e8
            ).getInfo()

            resultado['sar_pct_nieve_muy_humeda'] = round(
                (stats_muy_humeda.get('wet_snow_index', 0) or 0) * 100, 2
            )

            logger.info(
                f"Métricas SAR: VV={vv_medio:.1f}dB, delta={resultado['sar_delta_vv_db']}dB, "
                f"nieve_húmeda={resultado['sar_pct_nieve_humeda']}%"
            )
        else:
            logger.info(f"Métricas SAR (sin referencia): VV={vv_medio:.1f}dB")

        return resultado

    except Exception as e:
        logger.error(f"Error al calcular métricas SAR: {str(e)}")
        return {
            'sar_vv_medio_db': None,
            'sar_delta_vv_db': None,
            'sar_pct_nieve_humeda': None,
            'sar_pct_nieve_muy_humeda': None,
        }


# =============================================================================
# FUNCIONES DE INTEGRACIÓN
# =============================================================================

def obtener_productos_sar(
    latitud: float,
    longitud: float,
    fecha_captura: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Obtiene todos los productos SAR para una ubicación.

    Esta función busca la imagen SAR más reciente, obtiene la referencia
    de nieve seca, y calcula todas las métricas.

    Args:
        latitud: Latitud del punto
        longitud: Longitud del punto
        fecha_captura: Fecha de captura (default: hoy)

    Returns:
        dict: Productos SAR:
            - disponible: True si hay imagen SAR reciente
            - imagen: ee.Image con SAR
            - imagen_wsi: ee.Image con wet snow index
            - metadatos: dict con metadatos
            - metricas: dict con métricas calculadas
    """
    resultado = {
        'disponible': False,
        'imagen': None,
        'imagen_wsi': None,
        'metadatos': {},
        'metricas': {},
    }

    try:
        if fecha_captura is None:
            fecha_captura = datetime.utcnow()

        # Buscar imagen SAR reciente
        imagen_sar, metadatos = buscar_imagen_sar_reciente(
            latitud, longitud, fecha_captura
        )

        if imagen_sar is None:
            return resultado

        resultado['disponible'] = True
        resultado['imagen'] = imagen_sar
        resultado['metadatos'] = metadatos

        # Crear ROI
        punto = ee.Geometry.Point([longitud, latitud])
        roi = punto.buffer(RADIO_TILE_METROS).bounds()

        # Obtener referencia seca
        imagen_referencia = obtener_imagen_referencia_seca(latitud, longitud)

        # Calcular métricas
        metricas = calcular_metricas_sar(imagen_sar, imagen_referencia, roi)
        resultado['metricas'] = metricas

        # Calcular wet snow index si tenemos referencia
        if imagen_referencia is not None:
            try:
                wsi = calcular_wet_snow_index(imagen_sar, imagen_referencia)
                resultado['imagen_wsi'] = wsi
            except Exception:
                pass

        logger.info(f"Productos SAR obtenidos: {metadatos.get('fecha_str', 'N/A')}")

        return resultado

    except Exception as e:
        logger.error(f"Error obteniendo productos SAR: {str(e)}")
        return resultado


def compilar_metricas_sar_bigquery(
    productos_sar: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Formatea las métricas SAR para BigQuery.

    Args:
        productos_sar: Resultado de obtener_productos_sar()

    Returns:
        dict: Métricas formateadas para BigQuery
    """
    metricas = {
        'sar_disponible': productos_sar.get('disponible', False),
        'sar_fecha': None,
        'sar_pct_nieve_humeda': None,
        'sar_vv_medio_db': None,
        'sar_delta_vv_db': None,
    }

    if productos_sar.get('disponible'):
        metadatos = productos_sar.get('metadatos', {})
        metricas_sar = productos_sar.get('metricas', {})

        metricas['sar_fecha'] = metadatos.get('fecha_str')
        metricas['sar_pct_nieve_humeda'] = metricas_sar.get('sar_pct_nieve_humeda')
        metricas['sar_vv_medio_db'] = metricas_sar.get('sar_vv_medio_db')
        metricas['sar_delta_vv_db'] = metricas_sar.get('sar_delta_vv_db')

    return metricas

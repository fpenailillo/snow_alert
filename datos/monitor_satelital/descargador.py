"""
Monitor Satelital de Nieve - Descarga y Almacenamiento

Funciones para descargar imágenes desde GEE y subirlas a Cloud Storage.
Incluye GeoTIFF, PNG preview y thumbnails.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import unicodedata
import re

import ee
import requests
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError

from constantes import (
    ID_PROYECTO,
    BUCKET_BRONCE,
    PREFIJO_SATELITAL,
    TIMEOUT_DESCARGA_SEGUNDOS,
    MAX_REINTENTOS,
    ESPERA_ENTRE_REINTENTOS,
    DIMENSION_PREVIEW,
    DIMENSION_THUMBNAIL,
    RADIO_TILE_METROS,
)


logger = logging.getLogger(__name__)


class ErrorDescargaGEE(Exception):
    """Excepción cuando falla la descarga desde GEE."""
    pass


class ErrorSubidaGCS(Exception):
    """Excepción cuando falla la subida a Cloud Storage."""
    pass


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def normalizar_nombre(nombre: str) -> str:
    """
    Normaliza un nombre para uso en rutas de archivo.
    Convierte a snake_case, elimina acentos y caracteres especiales.

    Args:
        nombre: Nombre original

    Returns:
        str: Nombre normalizado (snake_case, sin tildes)
    """
    # Eliminar acentos
    nombre_sin_acentos = unicodedata.normalize('NFKD', nombre)
    nombre_sin_acentos = nombre_sin_acentos.encode('ASCII', 'ignore').decode('ASCII')

    # Convertir a minúsculas
    nombre_lower = nombre_sin_acentos.lower()

    # Reemplazar espacios y guiones por underscore
    nombre_normalizado = re.sub(r'[\s\-]+', '_', nombre_lower)

    # Eliminar caracteres no alfanuméricos excepto underscore
    nombre_normalizado = re.sub(r'[^a-z0-9_]', '', nombre_normalizado)

    # Eliminar underscores múltiples
    nombre_normalizado = re.sub(r'_+', '_', nombre_normalizado)

    # Eliminar underscores al inicio/final
    nombre_normalizado = nombre_normalizado.strip('_')

    return nombre_normalizado


def construir_ruta_gcs(
    nombre_ubicacion: str,
    fecha: datetime,
    tipo_captura: str,
    fuente: str,
    tipo_archivo: str,
    extension: str
) -> str:
    """
    Construye la ruta de almacenamiento en GCS.

    Estructura:
        {nombre_ubicacion}/satelital/{tipo}/{YYYY-MM-DD}/{archivo}

    Args:
        nombre_ubicacion: Nombre de la ubicación
        fecha: Fecha de captura
        tipo_captura: 'manana', 'tarde', 'noche'
        fuente: Nombre de la fuente (goes18, modis_terra, etc.)
        tipo_archivo: 'geotiff', 'preview', 'thumbnail'
        extension: Extensión del archivo (tif, png)

    Returns:
        str: Ruta completa en GCS
    """
    nombre_norm = normalizar_nombre(nombre_ubicacion)
    fecha_str = fecha.strftime('%Y-%m-%d')
    fuente_norm = normalizar_nombre(fuente)

    if tipo_archivo == 'geotiff':
        directorio = 'geotiff'
        nombre_archivo = f"{nombre_norm}_{tipo_captura}_{fuente_norm}.{extension}"
    elif tipo_archivo == 'preview':
        directorio = 'preview'
        nombre_archivo = f"{nombre_norm}_{tipo_captura}_{fuente_norm}_{DIMENSION_PREVIEW}px.{extension}"
    elif tipo_archivo == 'thumbnail':
        directorio = 'thumbnail'
        # Thumbnails se sobrescriben con la más reciente (por producto)
        nombre_archivo = f"{nombre_norm}_{fuente_norm}_ultimo_{DIMENSION_THUMBNAIL}px.{extension}"
        # Para thumbnails, no usamos fecha en la ruta
        return f"{nombre_norm}/satelital/{directorio}/{nombre_archivo}"
    else:
        raise ValueError(f"Tipo de archivo no soportado: {tipo_archivo}")

    return f"{nombre_norm}/satelital/{directorio}/{fecha_str}/{nombre_archivo}"


def crear_roi(latitud: float, longitud: float, radio_metros: int = RADIO_TILE_METROS) -> ee.Geometry:
    """
    Crea una región de interés (ROI) como buffer cuadrado.

    Args:
        latitud: Latitud del punto central
        longitud: Longitud del punto central
        radio_metros: Radio del buffer en metros

    Returns:
        ee.Geometry: Geometría del ROI
    """
    punto = ee.Geometry.Point([longitud, latitud])
    return punto.buffer(radio_metros).bounds()


# =============================================================================
# DESCARGA DESDE GEE
# =============================================================================

def descargar_geotiff(
    imagen: ee.Image,
    roi: ee.Geometry,
    bandas: list,
    escala: int,
    intentos: int = MAX_REINTENTOS
) -> bytes:
    """
    Descarga GeoTIFF desde GEE usando getDownloadURL().
    Óptimo para tiles pequeños (10km × 10km).

    Args:
        imagen: Imagen GEE a descargar
        roi: Región de interés
        bandas: Lista de bandas a incluir
        escala: Resolución en metros
        intentos: Número de reintentos

    Returns:
        bytes: Contenido del GeoTIFF

    Raises:
        ErrorDescargaGEE: Si falla después de todos los reintentos
    """
    ultimo_error = None

    for intento in range(intentos):
        try:
            url = imagen.select(bandas).getDownloadURL({
                'region': roi,
                'scale': escala,
                'format': 'GEO_TIFF',
                'crs': 'EPSG:4326'
            })

            respuesta = requests.get(url, timeout=TIMEOUT_DESCARGA_SEGUNDOS)
            respuesta.raise_for_status()

            logger.info(f"GeoTIFF descargado exitosamente ({len(respuesta.content)} bytes)")
            return respuesta.content

        except requests.exceptions.Timeout as e:
            ultimo_error = e
            logger.warning(f"Timeout en intento {intento + 1}/{intentos}: {str(e)}")

        except requests.exceptions.RequestException as e:
            ultimo_error = e
            logger.warning(f"Error de red en intento {intento + 1}/{intentos}: {str(e)}")

        except Exception as e:
            ultimo_error = e
            logger.warning(f"Error en intento {intento + 1}/{intentos}: {str(e)}")

        # Esperar antes del siguiente intento
        if intento < intentos - 1:
            espera = ESPERA_ENTRE_REINTENTOS[min(intento, len(ESPERA_ENTRE_REINTENTOS) - 1)]
            logger.info(f"Esperando {espera}s antes del siguiente intento...")
            time.sleep(espera)

    raise ErrorDescargaGEE(f"Fallo después de {intentos} intentos: {str(ultimo_error)}")


def generar_preview_png(
    imagen: ee.Image,
    roi: ee.Geometry,
    vis_params: Dict[str, Any],
    dimension: int = DIMENSION_PREVIEW,
    intentos: int = MAX_REINTENTOS
) -> bytes:
    """
    Genera PNG de preview usando getThumbURL().

    Args:
        imagen: Imagen GEE
        roi: Región de interés
        vis_params: Parámetros de visualización
        dimension: Dimensión del lado mayor en píxeles
        intentos: Número de reintentos

    Returns:
        bytes: Contenido del PNG

    Raises:
        ErrorDescargaGEE: Si falla después de todos los reintentos
    """
    ultimo_error = None

    for intento in range(intentos):
        try:
            params = {
                **vis_params,
                'dimensions': dimension,
                'region': roi,
                'format': 'png'
            }

            url = imagen.getThumbURL(params)

            respuesta = requests.get(url, timeout=TIMEOUT_DESCARGA_SEGUNDOS)
            respuesta.raise_for_status()

            logger.info(f"Preview PNG generado ({dimension}px, {len(respuesta.content)} bytes)")
            return respuesta.content

        except requests.exceptions.Timeout as e:
            ultimo_error = e
            logger.warning(f"Timeout en preview, intento {intento + 1}/{intentos}")

        except requests.exceptions.RequestException as e:
            ultimo_error = e
            logger.warning(f"Error de red en preview, intento {intento + 1}/{intentos}: {str(e)}")

        except Exception as e:
            ultimo_error = e
            logger.warning(f"Error en preview, intento {intento + 1}/{intentos}: {str(e)}")

        if intento < intentos - 1:
            espera = ESPERA_ENTRE_REINTENTOS[min(intento, len(ESPERA_ENTRE_REINTENTOS) - 1)]
            time.sleep(espera)

    raise ErrorDescargaGEE(f"Fallo preview después de {intentos} intentos: {str(ultimo_error)}")


def generar_thumbnail(
    imagen: ee.Image,
    roi: ee.Geometry,
    vis_params: Dict[str, Any],
    dimension: int = DIMENSION_THUMBNAIL,
    intentos: int = MAX_REINTENTOS
) -> bytes:
    """
    Genera thumbnail pequeño para landing page.

    Args:
        imagen: Imagen GEE
        roi: Región de interés
        vis_params: Parámetros de visualización
        dimension: Dimensión del thumbnail
        intentos: Número de reintentos

    Returns:
        bytes: Contenido del PNG thumbnail
    """
    return generar_preview_png(imagen, roi, vis_params, dimension, intentos)


# =============================================================================
# SUBIDA A CLOUD STORAGE
# =============================================================================

def subir_a_gcs(
    cliente_gcs: storage.Client,
    bucket_nombre: str,
    ruta_archivo: str,
    contenido: bytes,
    content_type: str,
    metadata: Optional[Dict[str, str]] = None
) -> str:
    """
    Sube un archivo a Cloud Storage.

    Args:
        cliente_gcs: Cliente de Cloud Storage
        bucket_nombre: Nombre del bucket
        ruta_archivo: Ruta del archivo en el bucket
        contenido: Contenido en bytes
        content_type: Tipo MIME del contenido
        metadata: Metadatos opcionales

    Returns:
        str: URI completa del archivo (gs://bucket/ruta)

    Raises:
        ErrorSubidaGCS: Si falla la subida
    """
    try:
        bucket = cliente_gcs.bucket(bucket_nombre)
        blob = bucket.blob(ruta_archivo)

        if metadata:
            blob.metadata = metadata

        blob.upload_from_string(contenido, content_type=content_type)

        uri = f"gs://{bucket_nombre}/{ruta_archivo}"
        logger.info(f"Archivo subido a GCS: {uri}")

        return uri

    except GoogleCloudError as e:
        mensaje = f"Error de Google Cloud al subir {ruta_archivo}: {str(e)}"
        logger.error(mensaje)
        raise ErrorSubidaGCS(mensaje)

    except Exception as e:
        mensaje = f"Error inesperado al subir {ruta_archivo}: {str(e)}"
        logger.error(mensaje)
        raise ErrorSubidaGCS(mensaje)


def guardar_geotiff(
    cliente_gcs: storage.Client,
    bucket_nombre: str,
    nombre_ubicacion: str,
    fecha: datetime,
    tipo_captura: str,
    fuente: str,
    contenido: bytes,
    tipo_producto: str
) -> str:
    """
    Guarda un GeoTIFF en Cloud Storage.

    Args:
        cliente_gcs: Cliente de Cloud Storage
        bucket_nombre: Nombre del bucket
        nombre_ubicacion: Nombre de la ubicación
        fecha: Fecha de captura
        tipo_captura: 'manana', 'tarde', 'noche'
        fuente: Nombre de la fuente
        contenido: Contenido del GeoTIFF
        tipo_producto: 'visual', 'ndsi', 'lst', 'era5'

    Returns:
        str: URI del archivo
    """
    fuente_producto = f"{fuente}_{tipo_producto}"
    ruta = construir_ruta_gcs(
        nombre_ubicacion, fecha, tipo_captura,
        fuente_producto, 'geotiff', 'tif'
    )

    metadata = {
        'ubicacion': nombre_ubicacion,
        'fecha_captura': fecha.isoformat(),
        'tipo_captura': tipo_captura,
        'fuente': fuente,
        'tipo_producto': tipo_producto,
    }

    return subir_a_gcs(
        cliente_gcs, bucket_nombre, ruta, contenido,
        'image/tiff', metadata
    )


def guardar_preview(
    cliente_gcs: storage.Client,
    bucket_nombre: str,
    nombre_ubicacion: str,
    fecha: datetime,
    tipo_captura: str,
    contenido: bytes,
    tipo_producto: str
) -> str:
    """
    Guarda un PNG preview en Cloud Storage.

    Args:
        cliente_gcs: Cliente de Cloud Storage
        bucket_nombre: Nombre del bucket
        nombre_ubicacion: Nombre de la ubicación
        fecha: Fecha de captura
        tipo_captura: 'manana', 'tarde', 'noche'
        contenido: Contenido del PNG
        tipo_producto: 'visual', 'ndsi', 'lst'

    Returns:
        str: URI del archivo
    """
    ruta = construir_ruta_gcs(
        nombre_ubicacion, fecha, tipo_captura,
        tipo_producto, 'preview', 'png'
    )

    metadata = {
        'ubicacion': nombre_ubicacion,
        'fecha_captura': fecha.isoformat(),
        'tipo_captura': tipo_captura,
        'tipo_producto': tipo_producto,
        'dimension': str(DIMENSION_PREVIEW),
    }

    return subir_a_gcs(
        cliente_gcs, bucket_nombre, ruta, contenido,
        'image/png', metadata
    )


def guardar_thumbnail(
    cliente_gcs: storage.Client,
    bucket_nombre: str,
    nombre_ubicacion: str,
    contenido: bytes,
    tipo_producto: str
) -> str:
    """
    Guarda un thumbnail en Cloud Storage.
    Los thumbnails se sobrescriben con la imagen más reciente.

    Args:
        cliente_gcs: Cliente de Cloud Storage
        bucket_nombre: Nombre del bucket
        nombre_ubicacion: Nombre de la ubicación
        contenido: Contenido del PNG
        tipo_producto: 'visual', 'ndsi', 'lst'

    Returns:
        str: URI del archivo
    """
    # Para thumbnails usamos fecha ficticia ya que se sobrescriben
    fecha_dummy = datetime.now(timezone.utc)
    ruta = construir_ruta_gcs(
        nombre_ubicacion, fecha_dummy, 'ultimo',
        tipo_producto, 'thumbnail', 'png'
    )

    metadata = {
        'ubicacion': nombre_ubicacion,
        'ultima_actualizacion': datetime.now(timezone.utc).isoformat(),
        'tipo_producto': tipo_producto,
        'dimension': str(DIMENSION_THUMBNAIL),
    }

    return subir_a_gcs(
        cliente_gcs, bucket_nombre, ruta, contenido,
        'image/png', metadata
    )


# =============================================================================
# FUNCIÓN PRINCIPAL DE DESCARGA Y GUARDADO
# =============================================================================

def descargar_y_guardar_producto(
    cliente_gcs: storage.Client,
    bucket_nombre: str,
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    fecha: datetime,
    tipo_captura: str,
    producto: Dict[str, Any],
    tipo_producto: str,
    bandas_geotiff: list,
    escala: int,
    radio_metros: Optional[int] = None,
) -> Dict[str, str]:
    """
    Descarga un producto completo y lo guarda en GCS.

    Genera GeoTIFF, preview y thumbnail para el producto.

    Args:
        cliente_gcs: Cliente de Cloud Storage
        bucket_nombre: Nombre del bucket
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud
        longitud: Longitud
        fecha: Fecha de captura
        tipo_captura: 'manana', 'tarde', 'noche'
        producto: Diccionario con imagen, metadatos y vis_params
        tipo_producto: 'visual', 'ndsi', 'lst', 'era5'
        bandas_geotiff: Bandas a incluir en el GeoTIFF
        escala: Resolución en metros
        radio_metros: Radio del ROI en metros (default: RADIO_TILE_METROS)

    Returns:
        dict: URIs de los archivos guardados
    """
    uris = {}
    roi = crear_roi(latitud, longitud, radio_metros or RADIO_TILE_METROS)

    imagen = producto.get('imagen')
    vis_params = producto.get('vis_params', {})
    fuente = producto.get('fuente', 'desconocida')

    if imagen is None:
        logger.warning(f"No hay imagen para {tipo_producto}")
        return uris

    try:
        # 1. GeoTIFF
        logger.info(f"Descargando GeoTIFF {tipo_producto}...")
        contenido_tiff = descargar_geotiff(imagen, roi, bandas_geotiff, escala)
        uri_tiff = guardar_geotiff(
            cliente_gcs, bucket_nombre, nombre_ubicacion,
            fecha, tipo_captura, fuente, contenido_tiff, tipo_producto
        )
        uris[f'geotiff_{tipo_producto}'] = uri_tiff

    except (ErrorDescargaGEE, ErrorSubidaGCS) as e:
        logger.error(f"Error en GeoTIFF {tipo_producto}: {str(e)}")

    try:
        # 2. Preview PNG
        logger.info(f"Generando preview {tipo_producto}...")
        contenido_preview = generar_preview_png(imagen, roi, vis_params)
        uri_preview = guardar_preview(
            cliente_gcs, bucket_nombre, nombre_ubicacion,
            fecha, tipo_captura, contenido_preview, tipo_producto
        )
        uris[f'preview_{tipo_producto}'] = uri_preview

    except (ErrorDescargaGEE, ErrorSubidaGCS) as e:
        logger.error(f"Error en preview {tipo_producto}: {str(e)}")

    try:
        # 3. Thumbnail (siempre la más reciente)
        logger.info(f"Generando thumbnail {tipo_producto}...")
        contenido_thumb = generar_thumbnail(imagen, roi, vis_params)
        uri_thumb = guardar_thumbnail(
            cliente_gcs, bucket_nombre, nombre_ubicacion,
            contenido_thumb, tipo_producto
        )
        uris[f'thumbnail_{tipo_producto}'] = uri_thumb

    except (ErrorDescargaGEE, ErrorSubidaGCS) as e:
        logger.error(f"Error en thumbnail {tipo_producto}: {str(e)}")

    return uris


def descargar_y_guardar_todos_los_productos(
    cliente_gcs: storage.Client,
    bucket_nombre: str,
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    fecha: datetime,
    tipo_captura: str,
    productos: Dict[str, Any],
    resoluciones: Dict[str, int]
) -> Dict[str, str]:
    """
    Descarga y guarda todos los productos de una captura.

    Args:
        cliente_gcs: Cliente de Cloud Storage
        bucket_nombre: Nombre del bucket
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud
        longitud: Longitud
        fecha: Fecha de captura
        tipo_captura: 'manana', 'tarde', 'noche'
        productos: Diccionario con todos los productos
        resoluciones: Resoluciones por tipo de producto

    Returns:
        dict: Todas las URIs de archivos guardados
    """
    todas_las_uris = {}

    # Visual
    if 'visual' in productos and productos['visual'].get('imagen'):
        uris = descargar_y_guardar_producto(
            cliente_gcs, bucket_nombre, nombre_ubicacion,
            latitud, longitud, fecha, tipo_captura,
            productos['visual'], 'visual',
            ['R', 'G', 'B'],
            resoluciones.get('visual', 500)
        )
        todas_las_uris.update(uris)

    # NDSI
    if 'ndsi' in productos and productos['ndsi'].get('imagen'):
        uris = descargar_y_guardar_producto(
            cliente_gcs, bucket_nombre, nombre_ubicacion,
            latitud, longitud, fecha, tipo_captura,
            productos['ndsi'], 'ndsi',
            ['NDSI'],
            resoluciones.get('ndsi', 500)
        )
        todas_las_uris.update(uris)

    # LST
    if 'lst' in productos and productos['lst'].get('imagen'):
        uris = descargar_y_guardar_producto(
            cliente_gcs, bucket_nombre, nombre_ubicacion,
            latitud, longitud, fecha, tipo_captura,
            productos['lst'], 'lst',
            ['LST_Celsius'],
            resoluciones.get('lst', 1000)
        )
        todas_las_uris.update(uris)

    # ERA5
    if 'era5' in productos and productos['era5'].get('imagen_nieve'):
        # Crear producto combinado para ERA5
        producto_era5 = {
            'imagen': productos['era5']['imagen_nieve'],
            'vis_params': productos['era5'].get('vis_params', {}),
            'fuente': 'ERA5-Land',
        }
        # ERA5-Land es ~9-11km/pixel. ROI de 5km no captura pixeles → usar 25km
        uris = descargar_y_guardar_producto(
            cliente_gcs, bucket_nombre, nombre_ubicacion,
            latitud, longitud, fecha, tipo_captura,
            producto_era5, 'era5',
            ['snow_depth_m', 'swe_m', 'snow_cover_frac'],
            resoluciones.get('era5', 11000),
            radio_metros=25000,
        )
        todas_las_uris.update(uris)

    logger.info(f"Total de archivos guardados: {len(todas_las_uris)}")

    return todas_las_uris

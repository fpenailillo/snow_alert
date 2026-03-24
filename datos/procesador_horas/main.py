"""
Snow Alert - Procesador de Pronóstico por Horas

Cloud Function que procesa datos de pronóstico horario desde Pub/Sub,
los almacena en Cloud Storage (capa bronce) y BigQuery (capa plata).

Datos: Pronóstico de las próximas 24 horas con temperatura, viento,
precipitación y otras métricas horarias.

Arquitectura: Pub/Sub Topic → Cloud Function (Procesador) → BigQuery + Cloud Storage
"""

import base64
import json
import logging
import os
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import functions_framework
from google.cloud import storage
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError


# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Constantes de configuración
ID_PROYECTO = os.environ.get('GCP_PROJECT', os.environ.get('GOOGLE_CLOUD_PROJECT', ''))
NOMBRE_BUCKET = os.environ.get('BUCKET_CLIMA', 'datos-clima-bronce')
NOMBRE_DATASET = os.environ.get('DATASET_CLIMA', 'clima')
NOMBRE_TABLA = 'pronostico_horas'


class ErrorProcesamientoClima(Exception):
    """Excepción levantada cuando falla el procesamiento de datos climáticos."""
    pass


class ErrorAlmacenamientoGCS(Exception):
    """Excepción levantada cuando falla el almacenamiento en Cloud Storage."""
    pass


class ErrorAlmacenamientoBigQuery(Exception):
    """Excepción levantada cuando falla el almacenamiento en BigQuery."""
    pass


class ErrorValidacionDatos(Exception):
    """Excepción levantada cuando los datos recibidos son inválidos."""
    pass


def decodificar_mensaje_pubsub(mensaje_pubsub: Dict[str, Any]) -> Dict[str, Any]:
    """Decodifica el mensaje de Pub/Sub y extrae los datos."""
    try:
        datos_codificados = mensaje_pubsub.get('data', '')
        if not datos_codificados:
            raise ErrorValidacionDatos("Mensaje Pub/Sub sin datos")

        datos_json = base64.b64decode(datos_codificados).decode('utf-8')
        datos = json.loads(datos_json)

        logger.info(f"Mensaje decodificado para ubicación: {datos.get('nombre_ubicacion', 'desconocida')}")
        return datos

    except json.JSONDecodeError as e:
        raise ErrorValidacionDatos(f"Error al parsear JSON: {str(e)}")
    except Exception as e:
        raise ErrorValidacionDatos(f"Error al decodificar mensaje: {str(e)}")


def validar_datos_pronostico(datos: Dict[str, Any]) -> None:
    """Valida que los datos de pronóstico tengan la estructura esperada."""
    campos_requeridos = ['nombre_ubicacion', 'coordenadas', 'datos_clima_raw', 'marca_tiempo_extraccion']

    for campo in campos_requeridos:
        if campo not in datos:
            raise ErrorValidacionDatos(f"Campo requerido faltante: {campo}")

    # Validar que exista forecastHours
    datos_raw = datos.get('datos_clima_raw', {})
    if 'forecastHours' not in datos_raw:
        raise ErrorValidacionDatos("Datos de pronóstico por horas no encontrados (forecastHours)")

    logger.info("Validación de datos de pronóstico completada")


def construir_ruta_gcs(datos: Dict[str, Any]) -> str:
    """Construye la ruta de almacenamiento en GCS para pronóstico horario."""
    try:
        nombre_ubicacion = unicodedata.normalize('NFKD', datos['nombre_ubicacion']).encode('ASCII', 'ignore').decode('ASCII').lower().replace(' ', '_')
        marca_tiempo = datetime.fromisoformat(datos['marca_tiempo_extraccion'].replace('Z', '+00:00'))

        ruta = (
            f"{nombre_ubicacion}/pronostico_horas/"
            f"{marca_tiempo.year:04d}/"
            f"{marca_tiempo.month:02d}/"
            f"{marca_tiempo.day:02d}/"
            f"{marca_tiempo.strftime('%Y%m%d_%H%M%S')}.json"
        )

        logger.info(f"Ruta GCS construida: {ruta}")
        return ruta

    except Exception as e:
        raise ErrorAlmacenamientoGCS(f"Error al construir ruta GCS: {str(e)}")


def guardar_en_gcs(
    cliente_storage: storage.Client,
    nombre_bucket: str,
    datos: Dict[str, Any]
) -> str:
    """Guarda los datos crudos en Cloud Storage (capa bronce)."""
    try:
        bucket = cliente_storage.bucket(nombre_bucket)
        ruta_archivo = construir_ruta_gcs(datos)
        blob = bucket.blob(ruta_archivo)

        datos_json = json.dumps(datos, ensure_ascii=False, indent=2)

        blob.metadata = {
            'ubicacion': datos.get('nombre_ubicacion', 'desconocida'),
            'marca_tiempo_extraccion': datos.get('marca_tiempo_extraccion', ''),
            'tipo': 'pronostico_horas',
            'version_procesador': '1.0.0'
        }

        blob.upload_from_string(datos_json, content_type='application/json')

        uri_completa = f"gs://{nombre_bucket}/{ruta_archivo}"
        logger.info(f"Datos guardados en GCS: {uri_completa}")

        return uri_completa

    except GoogleCloudError as e:
        raise ErrorAlmacenamientoGCS(f"Error de Google Cloud al guardar en GCS: {str(e)}")
    except Exception as e:
        raise ErrorAlmacenamientoGCS(f"Error al guardar en GCS: {str(e)}")


def extraer_valor_seguro(datos: Dict[str, Any], ruta: List[str], predeterminado: Any = None) -> Any:
    """Extrae un valor de un diccionario anidado de forma segura."""
    actual = datos
    for clave in ruta:
        if isinstance(actual, dict) and clave in actual:
            actual = actual[clave]
        else:
            return predeterminado
    return actual


def transformar_hora_para_bigquery(
    hora_data: Dict[str, Any],
    nombre_ubicacion: str,
    coordenadas: Dict[str, Any],
    marca_tiempo_extraccion: str,
    uri_gcs: str
) -> Dict[str, Any]:
    """Transforma una hora de pronóstico al esquema de BigQuery."""

    # Extraer intervalo de tiempo
    intervalo = hora_data.get('interval', {})
    inicio_hora = intervalo.get('startTime', '')
    fin_hora = intervalo.get('endTime', '')

    # Extraer fecha/hora de visualización
    display_dt = hora_data.get('displayDateTime', {})

    fila = {
        'nombre_ubicacion': nombre_ubicacion,
        'latitud': coordenadas.get('latitud'),
        'longitud': coordenadas.get('longitud'),

        # Tiempo del pronóstico
        'hora_inicio': inicio_hora,
        'hora_fin': fin_hora,
        'anio': display_dt.get('year'),
        'mes': display_dt.get('month'),
        'dia': display_dt.get('day'),
        'hora': display_dt.get('hours'),

        # Condiciones
        'es_dia': hora_data.get('isDaytime'),
        'condicion_clima': extraer_valor_seguro(hora_data, ['weatherCondition', 'type']),
        'descripcion_clima': extraer_valor_seguro(hora_data, ['weatherCondition', 'description', 'text']),
        'icono_url': extraer_valor_seguro(hora_data, ['weatherCondition', 'iconBaseUri']),

        # Temperaturas
        'temperatura': extraer_valor_seguro(hora_data, ['temperature', 'degrees']),
        'sensacion_termica': extraer_valor_seguro(hora_data, ['feelsLikeTemperature', 'degrees']),
        'punto_rocio': extraer_valor_seguro(hora_data, ['dewPoint', 'degrees']),
        'indice_calor': extraer_valor_seguro(hora_data, ['heatIndex', 'degrees']),
        'sensacion_viento': extraer_valor_seguro(hora_data, ['windChill', 'degrees']),
        'temperatura_bulbo_humedo': extraer_valor_seguro(hora_data, ['wetBulbTemperature', 'degrees']),

        # Humedad y presión
        'humedad_relativa': hora_data.get('relativeHumidity'),
        'presion_aire': extraer_valor_seguro(hora_data, ['airPressure', 'meanSeaLevelMillibars']),

        # Viento
        'velocidad_viento': extraer_valor_seguro(hora_data, ['wind', 'speed', 'value']),
        'direccion_viento': extraer_valor_seguro(hora_data, ['wind', 'direction', 'cardinal']),
        'direccion_viento_grados': extraer_valor_seguro(hora_data, ['wind', 'direction', 'degrees']),
        'rafaga_viento': extraer_valor_seguro(hora_data, ['wind', 'gust', 'value']),

        # Precipitación
        'prob_precipitacion': extraer_valor_seguro(hora_data, ['precipitation', 'probability', 'percent']),
        'tipo_precipitacion': extraer_valor_seguro(hora_data, ['precipitation', 'probability', 'type']),
        'cantidad_precipitacion': extraer_valor_seguro(hora_data, ['precipitation', 'qpf', 'quantity']),

        # Otros
        'prob_tormenta': hora_data.get('thunderstormProbability'),
        'indice_uv': hora_data.get('uvIndex'),
        'visibilidad': extraer_valor_seguro(hora_data, ['visibility', 'distance']),
        'cobertura_nubes': hora_data.get('cloudCover'),
        'espesor_hielo': extraer_valor_seguro(hora_data, ['iceThickness', 'thickness']),

        # Metadata
        'marca_tiempo_extraccion': marca_tiempo_extraccion,
        'marca_tiempo_ingestion': datetime.now(timezone.utc).isoformat(),
        'uri_datos_crudos': uri_gcs
    }

    return fila


def transformar_datos_para_bigquery(datos: Dict[str, Any], uri_gcs: str) -> List[Dict[str, Any]]:
    """Transforma los datos de pronóstico horario a filas de BigQuery."""
    try:
        datos_clima_raw = datos.get('datos_clima_raw', {})
        coordenadas = datos.get('coordenadas', {})
        nombre_ubicacion = datos.get('nombre_ubicacion')
        marca_tiempo_extraccion = datos.get('marca_tiempo_extraccion')

        forecast_hours = datos_clima_raw.get('forecastHours', [])

        filas = []
        for hora_data in forecast_hours:
            fila = transformar_hora_para_bigquery(
                hora_data,
                nombre_ubicacion,
                coordenadas,
                marca_tiempo_extraccion,
                uri_gcs
            )
            filas.append(fila)

        logger.info(f"Transformadas {len(filas)} horas de pronóstico para {nombre_ubicacion}")
        return filas

    except Exception as e:
        raise ErrorProcesamientoClima(f"Error al transformar datos: {str(e)}")


def guardar_en_bigquery(
    cliente_bigquery: bigquery.Client,
    nombre_dataset: str,
    nombre_tabla: str,
    filas: List[Dict[str, Any]]
) -> None:
    """Guarda las filas de pronóstico en BigQuery."""
    try:
        tabla_id = f"{ID_PROYECTO}.{nombre_dataset}.{nombre_tabla}"

        errores = cliente_bigquery.insert_rows_json(tabla_id, filas)

        if errores:
            raise ErrorAlmacenamientoBigQuery(f"Errores al insertar en BigQuery: {errores}")

        logger.info(f"Insertadas {len(filas)} filas en BigQuery: {nombre_dataset}.{nombre_tabla}")

    except ErrorAlmacenamientoBigQuery:
        raise
    except GoogleCloudError as e:
        raise ErrorAlmacenamientoBigQuery(f"Error de Google Cloud: {str(e)}")
    except Exception as e:
        raise ErrorAlmacenamientoBigQuery(f"Error al guardar en BigQuery: {str(e)}")


@functions_framework.cloud_event
def procesar_pronostico_horas(evento_nube):
    """
    Cloud Function que procesa mensajes de pronóstico horario desde Pub/Sub.

    Disparada por mensajes en el topic 'clima-pronostico-horas':
    1. Decodifica y valida el mensaje
    2. Guarda datos crudos en GCS (capa bronce)
    3. Transforma cada hora al esquema de BigQuery
    4. Inserta filas en BigQuery (capa plata)
    """
    logger.info("=" * 60)
    logger.info("Procesando pronóstico por horas")
    logger.info("=" * 60)

    cliente_storage = None
    cliente_bigquery = None

    try:
        mensaje_pubsub = evento_nube.data
        datos = decodificar_mensaje_pubsub(mensaje_pubsub.get('message', {}))
        validar_datos_pronostico(datos)

        nombre_ubicacion = datos.get('nombre_ubicacion', 'desconocida')
        logger.info(f"Procesando pronóstico horario para: {nombre_ubicacion}")

        cliente_storage = storage.Client()
        cliente_bigquery = bigquery.Client()

        # Guardar en GCS (capa bronce)
        uri_gcs = guardar_en_gcs(cliente_storage, NOMBRE_BUCKET, datos)

        # Transformar y guardar en BigQuery (capa plata)
        filas_bigquery = transformar_datos_para_bigquery(datos, uri_gcs)
        guardar_en_bigquery(cliente_bigquery, NOMBRE_DATASET, NOMBRE_TABLA, filas_bigquery)

        logger.info("=" * 60)
        logger.info(f"Procesamiento completado: {nombre_ubicacion} ({len(filas_bigquery)} horas)")
        logger.info("=" * 60)

    except ErrorValidacionDatos as e:
        logger.error(f"Error de validación: {str(e)}")
        logger.warning("Mensaje descartado por validación fallida")

    except (ErrorAlmacenamientoGCS, ErrorAlmacenamientoBigQuery, ErrorProcesamientoClima) as e:
        logger.error(f"Error de procesamiento: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}", exc_info=True)
        raise

    finally:
        if cliente_storage:
            try:
                cliente_storage.close()
            except Exception:
                pass
        if cliente_bigquery:
            try:
                cliente_bigquery.close()
            except Exception:
                pass

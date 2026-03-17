"""
Monitor Satelital de Nieve - Orquestador Principal

Cloud Function HTTP que coordina la descarga de imágenes satelitales
para las ubicaciones monitoreadas, procesando visual, NDSI, LST, ERA5,
indicadores de nieve (snowline, AMI), SAR y viento en altura.

Versión 1.1: Incluye indicadores derivados, SAR (Sentinel-1) y viento ERA5.

Ejecuta 3 veces al día (mañana, tarde, noche) via Cloud Scheduler.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple, Optional

import functions_framework
import ee
from flask import Request
from google.cloud import storage
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError

# Agregar directorio actual al path para imports locales
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constantes import (
    ID_PROYECTO,
    GEE_PROYECTO,
    BUCKET_BRONCE,
    DATASET_CLIMA,
    TABLA_IMAGENES,
    VERSION_METODOLOGIA,
    TAMANO_LOTE,
    ESPERA_ENTRE_LOTES_SEGUNDOS,
    RESOLUCIONES,
    RADIO_TILE_METROS,
)
from fuentes import (
    obtener_configuracion_fuente,
    obtener_coleccion_gee,
    obtener_resolucion,
)
from productos import (
    crear_roi,
    obtener_todos_los_productos,
)
from metricas import (
    compilar_metricas_completas,
    crear_fila_bigquery,
)
from descargador import (
    descargar_y_guardar_todos_los_productos,
    normalizar_nombre,
)


# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPCIONES
# =============================================================================

class ErrorMonitorSatelital(Exception):
    """Excepción general del monitor satelital."""
    pass


class ErrorConfiguracionGEE(Exception):
    """Excepción cuando falla la configuración de GEE."""
    pass


class ErrorAlmacenamientoBigQuery(Exception):
    """Excepción cuando falla la inserción en BigQuery."""
    pass


# =============================================================================
# UBICACIONES A MONITOREAR
# =============================================================================

# Importar desde el extractor existente para mantener consistencia
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'extractor'))
    from main import UBICACIONES_MONITOREO
    logger.info(f"Ubicaciones importadas del extractor: {len(UBICACIONES_MONITOREO)}")
except ImportError:
    logger.warning("No se pudo importar UBICACIONES_MONITOREO del extractor, usando lista completa local")
    # Lista completa de respaldo (sincronizada con extractor/main.py)
    UBICACIONES_MONITOREO = [
        # Chile
        {'nombre': 'Portillo', 'latitud': -32.8369, 'longitud': -70.1287, 'descripcion': 'Portillo, Los Andes, Chile'},
        {'nombre': 'Ski Arpa', 'latitud': -32.6000, 'longitud': -70.3900, 'descripcion': 'Ski Arpa, Los Andes, Chile'},
        {'nombre': 'La Parva Sector Bajo', 'latitud': -33.3630, 'longitud': -70.3010, 'descripcion': 'La Parva - Sector Bajo, Chile (2650m)'},
        {'nombre': 'La Parva Sector Medio', 'latitud': -33.3520, 'longitud': -70.2900, 'descripcion': 'La Parva - Sector Medio, Chile (3100m)'},
        {'nombre': 'La Parva Sector Alto', 'latitud': -33.3440, 'longitud': -70.2800, 'descripcion': 'La Parva - Sector Alto, Chile (3574m)'},
        {'nombre': 'El Colorado', 'latitud': -33.3600, 'longitud': -70.3000, 'descripcion': 'El Colorado / Farellones, Chile'},
        {'nombre': 'Valle Nevado', 'latitud': -33.3547, 'longitud': -70.2498, 'descripcion': 'Valle Nevado, Chile'},
        {'nombre': 'Lagunillas', 'latitud': -33.6800, 'longitud': -70.2500, 'descripcion': 'Lagunillas, San José de Maipo, Chile'},
        {'nombre': 'Chapa Verde', 'latitud': -34.1700, 'longitud': -70.3700, 'descripcion': 'Chapa Verde, Rancagua, Chile'},
        {'nombre': 'Nevados de Chillán', 'latitud': -36.8580, 'longitud': -71.3727, 'descripcion': 'Nevados de Chillán, Chile'},
        {'nombre': 'Antuco', 'latitud': -37.4100, 'longitud': -71.4200, 'descripcion': 'Ski Antuco, Los Ángeles, Chile'},
        {'nombre': 'Corralco', 'latitud': -38.3700, 'longitud': -71.5700, 'descripcion': 'Corralco, Volcán Lonquimay, Chile'},
        {'nombre': 'Las Araucarias', 'latitud': -38.7300, 'longitud': -71.7400, 'descripcion': 'Las Araucarias / Llaima, Chile'},
        {'nombre': 'Ski Pucón', 'latitud': -39.5000, 'longitud': -71.9600, 'descripcion': 'Ski Pucón / Pillán, Chile'},
        {'nombre': 'Antillanca', 'latitud': -40.7756, 'longitud': -72.2046, 'descripcion': 'Antillanca, Volcán Casablanca, Chile'},
        {'nombre': 'Volcán Osorno', 'latitud': -41.1000, 'longitud': -72.5000, 'descripcion': 'Volcán Osorno, Puerto Varas, Chile'},
        {'nombre': 'El Fraile', 'latitud': -45.6800, 'longitud': -71.9400, 'descripcion': 'El Fraile, Coyhaique, Chile'},
        {'nombre': 'Cerro Mirador', 'latitud': -53.1300, 'longitud': -70.9800, 'descripcion': 'Cerro Mirador, Punta Arenas, Chile'},
        # Argentina
        {'nombre': 'Cerro Catedral', 'latitud': -41.1667, 'longitud': -71.4500, 'descripcion': 'Cerro Catedral, Bariloche, Argentina'},
        {'nombre': 'Cerro Chapelco', 'latitud': -40.2500, 'longitud': -71.2000, 'descripcion': 'Cerro Chapelco, San Martín de los Andes, Argentina'},
        {'nombre': 'Las Leñas', 'latitud': -35.1553, 'longitud': -70.0986, 'descripcion': 'Las Leñas, Malargüe, Argentina'},
        {'nombre': 'Los Penitentes', 'latitud': -32.8567, 'longitud': -69.8075, 'descripcion': 'Los Penitentes, Mendoza, Argentina'},
        {'nombre': 'Vallecitos', 'latitud': -33.0000, 'longitud': -69.4700, 'descripcion': 'Vallecitos, Mendoza, Argentina'},
        {'nombre': 'Cerro Bayo', 'latitud': -40.7167, 'longitud': -71.5500, 'descripcion': 'Cerro Bayo, Villa La Angostura, Argentina'},
        {'nombre': 'Caviahue', 'latitud': -37.8700, 'longitud': -71.0500, 'descripcion': 'Caviahue, Neuquén, Argentina'},
    ]


# =============================================================================
# INICIALIZACIÓN
# =============================================================================

def inicializar_earth_engine() -> None:
    """
    Inicializa Google Earth Engine con credenciales del proyecto.

    Raises:
        ErrorConfiguracionGEE: Si falla la inicialización
    """
    try:
        # Intentar con credenciales de servicio
        proyecto = GEE_PROYECTO or ID_PROYECTO

        if not proyecto:
            raise ErrorConfiguracionGEE(
                "No se encontró ID de proyecto. "
                "Establecer GEE_PROJECT o GCP_PROJECT"
            )

        ee.Initialize(project=proyecto)
        logger.info(f"Earth Engine inicializado con proyecto: {proyecto}")

    except ee.EEException as e:
        mensaje = f"Error al inicializar Earth Engine: {str(e)}"
        logger.error(mensaje)
        raise ErrorConfiguracionGEE(mensaje)

    except Exception as e:
        mensaje = f"Error inesperado al inicializar Earth Engine: {str(e)}"
        logger.error(mensaje)
        raise ErrorConfiguracionGEE(mensaje)


def determinar_tipo_captura(hora_utc: Optional[int] = None) -> str:
    """
    Determina el tipo de captura basado en la hora UTC.

    Args:
        hora_utc: Hora UTC (0-23), usa la hora actual si no se especifica

    Returns:
        str: 'manana', 'tarde' o 'noche'
    """
    if hora_utc is None:
        hora_utc = datetime.utcnow().hour

    # Horarios aproximados UTC para Chile (UTC-3/-4)
    # Mañana: 08:00 local → ~11-12 UTC
    # Tarde: 14:00 local → ~17-18 UTC
    # Noche: 22:00 local → ~01-02 UTC (+1 día)

    if 10 <= hora_utc < 16:
        return 'manana'
    elif 16 <= hora_utc < 23:
        return 'tarde'
    else:
        return 'noche'


# =============================================================================
# PROCESAMIENTO DE UBICACIÓN
# =============================================================================

def procesar_ubicacion(
    ubicacion: Dict[str, Any],
    tipo_captura: str,
    cliente_gcs: storage.Client,
    cliente_bq: bigquery.Client,
    bucket_nombre: str,
    fecha_proceso: datetime
) -> Dict[str, Any]:
    """
    Procesa una ubicación: obtiene productos, descarga y guarda.

    Args:
        ubicacion: Información de la ubicación
        tipo_captura: 'manana', 'tarde', 'noche'
        cliente_gcs: Cliente de Cloud Storage
        cliente_bq: Cliente de BigQuery
        bucket_nombre: Nombre del bucket
        fecha_proceso: Fecha de procesamiento

    Returns:
        dict: Resultado del procesamiento
    """
    nombre = ubicacion['nombre']
    latitud = ubicacion['latitud']
    longitud = ubicacion['longitud']

    logger.info(f"Procesando {nombre} ({latitud}, {longitud}) - captura {tipo_captura}")

    resultado = {
        'ubicacion': nombre,
        'estado': 'pendiente',
        'productos_obtenidos': 0,
        'archivos_guardados': 0,
        'errores': [],
    }

    try:
        # 1. Obtener configuración de fuentes
        config_fuentes = obtener_configuracion_fuente(nombre, latitud, longitud)
        logger.info(f"  Fuente principal: {config_fuentes.get('fuente_principal')}")

        # 2. Obtener todos los productos satelitales
        productos = obtener_todos_los_productos(
            latitud, longitud, tipo_captura, config_fuentes
        )
        resultado['productos_obtenidos'] = len([p for p in productos.values() if p])

        # 3. Calcular métricas (v1.1: incluye indicadores, SAR y viento)
        roi = crear_roi(latitud, longitud)
        metricas = compilar_metricas_completas(
            productos=productos,
            roi=roi,
            tipo_captura=tipo_captura,
            latitud=latitud,
            longitud=longitud,
            fecha_captura=fecha_proceso
        )

        # 4. Descargar y guardar en GCS
        resoluciones = {
            'visual': obtener_resolucion(config_fuentes.get('fuente_principal', 'MODIS')),
            'ndsi': 500,
            'lst': 1000,
            'era5': 11000,
        }

        uris = descargar_y_guardar_todos_los_productos(
            cliente_gcs, bucket_nombre, nombre,
            latitud, longitud, fecha_proceso, tipo_captura,
            productos, resoluciones
        )
        resultado['archivos_guardados'] = len(uris)

        # 5. Determinar metadatos de imagen
        timestamp_imagen = fecha_proceso
        coleccion_gee = ''
        fuente_principal = config_fuentes.get('fuente_principal', 'MODIS')

        # Obtener timestamp real de la imagen si está disponible
        for tipo_prod in ['visual', 'ndsi', 'lst']:
            if tipo_prod in productos and productos[tipo_prod].get('metadatos'):
                meta = productos[tipo_prod]['metadatos']
                if meta.get('fecha_captura'):
                    try:
                        timestamp_imagen = datetime.fromisoformat(
                            meta['fecha_captura'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        pass
                if meta.get('coleccion'):
                    coleccion_gee = meta['coleccion']
                break

        # 6. Guardar en BigQuery
        fila = crear_fila_bigquery(
            nombre_ubicacion=nombre,
            latitud=latitud,
            longitud=longitud,
            region=config_fuentes.get('region', 'desconocida'),
            fecha_captura=fecha_proceso,
            tipo_captura=tipo_captura,
            timestamp_imagen=timestamp_imagen,
            timestamp_descarga=datetime.utcnow(),
            fuente_principal=fuente_principal,
            coleccion_gee=coleccion_gee,
            resolucion_m=resoluciones['visual'],
            metricas=metricas,
            uris=uris
        )

        guardar_en_bigquery(cliente_bq, fila)

        resultado['estado'] = 'exitoso'
        logger.info(f"  ✓ {nombre} procesado exitosamente")

    except Exception as e:
        resultado['estado'] = 'fallido'
        resultado['errores'].append(str(e))
        logger.error(f"  ✗ Error procesando {nombre}: {str(e)}")

    return resultado


def guardar_en_bigquery(
    cliente_bq: bigquery.Client,
    fila: Dict[str, Any]
) -> None:
    """
    Guarda una fila en BigQuery.

    Args:
        cliente_bq: Cliente de BigQuery
        fila: Fila a insertar

    Raises:
        ErrorAlmacenamientoBigQuery: Si falla la inserción
    """
    try:
        tabla_id = f"{ID_PROYECTO}.{DATASET_CLIMA}.{TABLA_IMAGENES}"

        errores = cliente_bq.insert_rows_json(tabla_id, [fila])

        if errores:
            raise ErrorAlmacenamientoBigQuery(f"Errores BigQuery: {errores}")

        logger.info(f"  Fila insertada en BigQuery: {fila['nombre_ubicacion']}")

    except GoogleCloudError as e:
        raise ErrorAlmacenamientoBigQuery(f"Error de Google Cloud: {str(e)}")


def procesar_lote(
    ubicaciones: List[Dict[str, Any]],
    tipo_captura: str,
    cliente_gcs: storage.Client,
    cliente_bq: bigquery.Client,
    bucket_nombre: str,
    fecha_proceso: datetime
) -> List[Dict[str, Any]]:
    """
    Procesa un lote de ubicaciones con pausa entre cada una.

    Args:
        ubicaciones: Lista de ubicaciones
        tipo_captura: Tipo de captura
        cliente_gcs: Cliente de Cloud Storage
        cliente_bq: Cliente de BigQuery
        bucket_nombre: Nombre del bucket
        fecha_proceso: Fecha de procesamiento

    Returns:
        list: Resultados de cada ubicación
    """
    resultados = []

    for i, ubicacion in enumerate(ubicaciones):
        resultado = procesar_ubicacion(
            ubicacion, tipo_captura,
            cliente_gcs, cliente_bq,
            bucket_nombre, fecha_proceso
        )
        resultados.append(resultado)

        # Pausa entre ubicaciones (excepto la última)
        if i < len(ubicaciones) - 1:
            time.sleep(ESPERA_ENTRE_LOTES_SEGUNDOS)

    return resultados


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

@functions_framework.http
def monitorear_satelital(solicitud: Request) -> Tuple[Dict[str, Any], int]:
    """
    Cloud Function HTTP principal que coordina el monitoreo satelital.

    Esta función es invocada por Cloud Scheduler 3 veces al día:
    1. Inicializa Earth Engine
    2. Determina el tipo de captura (mañana/tarde/noche)
    3. Para cada ubicación, obtiene y procesa productos satelitales
    4. Guarda GeoTIFF, previews y thumbnails en GCS
    5. Registra métricas en BigQuery

    Args:
        solicitud: Objeto HTTP request de Cloud Functions

    Returns:
        Tuple[dict, int]: Respuesta JSON y código de estado HTTP
    """
    logger.info("=" * 70)
    logger.info("Monitor Satelital de Nieve - Iniciando captura")
    logger.info("=" * 70)

    fecha_inicio = datetime.now(timezone.utc)

    resultados = {
        'estado': 'exitoso',
        'version': VERSION_METODOLOGIA,
        'fecha_proceso': fecha_inicio.isoformat(),
        'tipo_captura': '',
        'total_ubicaciones': 0,
        'exitosos': 0,
        'fallidos': 0,
        'detalles': [],
        'errores_generales': [],
    }

    cliente_gcs = None
    cliente_bq = None

    try:
        # Validar configuración
        if not ID_PROYECTO:
            raise ErrorMonitorSatelital(
                "ID_PROYECTO no configurado. "
                "Establecer variable de entorno GCP_PROJECT"
            )

        # Inicializar Earth Engine
        logger.info("Inicializando Google Earth Engine...")
        inicializar_earth_engine()

        # Determinar tipo de captura
        tipo_captura = determinar_tipo_captura()
        resultados['tipo_captura'] = tipo_captura
        logger.info(f"Tipo de captura: {tipo_captura}")

        # Crear clientes
        cliente_gcs = storage.Client()
        cliente_bq = bigquery.Client()

        # Obtener nombre del bucket completo
        bucket_nombre = f"{ID_PROYECTO}-{BUCKET_BRONCE}"
        logger.info(f"Bucket destino: {bucket_nombre}")

        # Obtener ubicaciones
        ubicaciones = UBICACIONES_MONITOREO
        resultados['total_ubicaciones'] = len(ubicaciones)
        logger.info(f"Total ubicaciones a procesar: {len(ubicaciones)}")

        # Procesar en lotes
        for i in range(0, len(ubicaciones), TAMANO_LOTE):
            lote = ubicaciones[i:i + TAMANO_LOTE]
            num_lote = (i // TAMANO_LOTE) + 1
            total_lotes = (len(ubicaciones) + TAMANO_LOTE - 1) // TAMANO_LOTE

            logger.info(f"Procesando lote {num_lote}/{total_lotes} ({len(lote)} ubicaciones)")

            resultados_lote = procesar_lote(
                lote, tipo_captura,
                cliente_gcs, cliente_bq,
                bucket_nombre, fecha_inicio
            )

            for resultado in resultados_lote:
                resultados['detalles'].append(resultado)
                if resultado['estado'] == 'exitoso':
                    resultados['exitosos'] += 1
                else:
                    resultados['fallidos'] += 1

            # Pausa entre lotes
            if i + TAMANO_LOTE < len(ubicaciones):
                logger.info(f"Esperando {ESPERA_ENTRE_LOTES_SEGUNDOS}s antes del siguiente lote...")
                time.sleep(ESPERA_ENTRE_LOTES_SEGUNDOS)

        # Determinar estado final
        if resultados['fallidos'] == resultados['total_ubicaciones']:
            resultados['estado'] = 'fallido'
            codigo = 500
        elif resultados['fallidos'] > 0:
            resultados['estado'] = 'parcial'
            codigo = 207
        else:
            resultados['estado'] = 'exitoso'
            codigo = 200

        # Tiempo de ejecución
        fecha_fin = datetime.now(timezone.utc)
        duracion = (fecha_fin - fecha_inicio).total_seconds()

        logger.info("=" * 70)
        logger.info("Resumen de ejecución:")
        logger.info(f"  Tipo captura: {tipo_captura}")
        logger.info(f"  Ubicaciones procesadas: {resultados['total_ubicaciones']}")
        logger.info(f"  Exitosos: {resultados['exitosos']}")
        logger.info(f"  Fallidos: {resultados['fallidos']}")
        logger.info(f"  Duración: {duracion:.1f} segundos")
        logger.info("=" * 70)

        return resultados, codigo

    except ErrorConfiguracionGEE as e:
        logger.error(f"Error de configuración GEE: {str(e)}")
        resultados['estado'] = 'fallido'
        resultados['errores_generales'].append(str(e))
        return resultados, 500

    except ErrorMonitorSatelital as e:
        logger.error(f"Error de monitor satelital: {str(e)}")
        resultados['estado'] = 'fallido'
        resultados['errores_generales'].append(str(e))
        return resultados, 500

    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}", exc_info=True)
        resultados['estado'] = 'fallido'
        resultados['errores_generales'].append(f"Error inesperado: {str(e)}")
        return resultados, 500

    finally:
        if cliente_gcs:
            try:
                cliente_gcs.close()
            except Exception:
                pass
        if cliente_bq:
            try:
                cliente_bq.close()
            except Exception:
                pass


# =============================================================================
# EJECUCIÓN DESDE LÍNEA DE COMANDOS
# =============================================================================

def main():
    """
    Punto de entrada para ejecución desde línea de comandos.
    Útil para pruebas locales y desarrollo.
    """
    parser = argparse.ArgumentParser(
        description='Monitor Satelital de Nieve - Descarga imágenes satelitales'
    )
    parser.add_argument(
        '--prueba',
        action='store_true',
        help='Modo prueba: procesa solo 1 ubicación'
    )
    parser.add_argument(
        '--ubicacion',
        type=str,
        help='Nombre de ubicación específica a procesar'
    )
    parser.add_argument(
        '--captura',
        type=str,
        choices=['manana', 'tarde', 'noche'],
        help='Tipo de captura a ejecutar'
    )
    parser.add_argument(
        '--proyecto',
        type=str,
        help='ID del proyecto GCP'
    )

    args = parser.parse_args()

    # Configurar proyecto
    if args.proyecto:
        os.environ['GCP_PROJECT'] = args.proyecto
        os.environ['GEE_PROJECT'] = args.proyecto

    print("=" * 70)
    print("Monitor Satelital de Nieve - Modo Local")
    print("=" * 70)

    # Inicializar Earth Engine
    print("Inicializando Earth Engine...")
    inicializar_earth_engine()

    # Crear clientes
    cliente_gcs = storage.Client()
    cliente_bq = bigquery.Client()

    proyecto = os.environ.get('GCP_PROJECT', ID_PROYECTO)
    bucket_nombre = f"{proyecto}-{BUCKET_BRONCE}"

    # Determinar tipo de captura
    tipo_captura = args.captura or determinar_tipo_captura()
    print(f"Tipo de captura: {tipo_captura}")

    # Filtrar ubicaciones
    if args.ubicacion:
        ubicaciones = [u for u in UBICACIONES_MONITOREO if u['nombre'] == args.ubicacion]
        if not ubicaciones:
            print(f"Error: Ubicación '{args.ubicacion}' no encontrada")
            print("Ubicaciones disponibles:")
            for u in UBICACIONES_MONITOREO[:10]:
                print(f"  - {u['nombre']}")
            sys.exit(1)
    elif args.prueba:
        ubicaciones = UBICACIONES_MONITOREO[:1]
    else:
        ubicaciones = UBICACIONES_MONITOREO

    print(f"Ubicaciones a procesar: {len(ubicaciones)}")

    fecha_proceso = datetime.now(timezone.utc)
    exitosos = 0
    fallidos = 0

    for ubicacion in ubicaciones:
        resultado = procesar_ubicacion(
            ubicacion, tipo_captura,
            cliente_gcs, cliente_bq,
            bucket_nombre, fecha_proceso
        )

        if resultado['estado'] == 'exitoso':
            exitosos += 1
            print(f"  ✓ {resultado['ubicacion']}: "
                  f"{resultado['productos_obtenidos']} productos, "
                  f"{resultado['archivos_guardados']} archivos")
        else:
            fallidos += 1
            print(f"  ✗ {resultado['ubicacion']}: {resultado['errores']}")

    print("=" * 70)
    print(f"Completado: {exitosos} exitosos, {fallidos} fallidos")
    print("=" * 70)

    cliente_gcs.close()
    cliente_bq.close()


if __name__ == '__main__':
    main()

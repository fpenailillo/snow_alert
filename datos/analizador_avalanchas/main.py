"""
Snow Alert - Analizador Satelital de Zonas Riesgosas en Avalanchas

Cloud Function que analiza el terreno mediante datos satelitales para identificar,
clasificar y cubicar zonas riesgosas de avalancha usando Google Earth Engine.

Este módulo es el orquestador principal que:
1. Itera sobre las ubicaciones de monitoreo
2. Ejecuta análisis GEE con datos SRTM satelitales para cada ubicación
3. Calcula estadísticas de cubicación de zonas riesgosas
4. Genera índices de riesgo topográfico
5. Almacena resultados en BigQuery y GCS

Arquitectura: Cloud Scheduler → Cloud Function → GEE + BigQuery + GCS

El análisis satelital de zonas riesgosas es estático (no cambia con el tiempo),
por lo que se ejecuta con menor frecuencia que el monitoreo meteorológico.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import functions_framework
from flask import Request
from google.cloud import bigquery
from google.cloud import storage

# Importaciones locales
from zonas import inicializar_gee, analizar_zonas_ubicacion, exportar_mapa_gcs
from cubicacion import cubicar_zonas_completo
from indice_riesgo import (
    calcular_indice_desde_cubicacion,
    convertir_resultado_a_dict
)
from eaws_constantes import RADIO_ANALISIS_DEFAULT
from visualizacion import (
    generar_visualizaciones_completas,
    guardar_visualizaciones_gcs
)


# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Constantes de configuración
ID_PROYECTO = os.environ.get('GCP_PROJECT', os.environ.get('GOOGLE_CLOUD_PROJECT', ''))
PROYECTO_GEE = os.environ.get('GEE_PROJECT', ID_PROYECTO)

# BigQuery
DATASET_BIGQUERY = 'clima'
TABLA_ZONAS = 'zonas_avalancha'

# GCS
BUCKET_BRONCE = f'{ID_PROYECTO}-datos-clima-bronce'
PREFIJO_TOPOGRAFIA = 'topografia/mapas_riesgo'

# Procesamiento por lotes
TAMANO_LOTE = 10
PAUSA_ENTRE_LOTES = 2  # segundos

# Radio de análisis por defecto (metros)
RADIO_ANALISIS = RADIO_ANALISIS_DEFAULT


# ============================================================================
# UBICACIONES A ANALIZAR (importadas del extractor para mantener consistencia)
# ============================================================================

# Ubicaciones con potencial de avalanchas (alta montaña y pendientes)
# Se filtran automáticamente las ubicaciones que no tienen terreno susceptible
UBICACIONES_ANALISIS = [
    # Chile - Centros de Esquí
    {'nombre': 'Portillo', 'latitud': -32.8369, 'longitud': -70.1287},
    {'nombre': 'Ski Arpa', 'latitud': -32.6000, 'longitud': -70.3900},
    {'nombre': 'La Parva Sector Bajo', 'latitud': -33.3630, 'longitud': -70.3010},
    {'nombre': 'La Parva Sector Medio', 'latitud': -33.3520, 'longitud': -70.2900},
    {'nombre': 'La Parva Sector Alto', 'latitud': -33.3440, 'longitud': -70.2800},
    {'nombre': 'El Colorado', 'latitud': -33.3600, 'longitud': -70.3000},
    {'nombre': 'Valle Nevado', 'latitud': -33.3547, 'longitud': -70.2498},
    {'nombre': 'Lagunillas', 'latitud': -33.6800, 'longitud': -70.2500},
    {'nombre': 'Chapa Verde', 'latitud': -34.1700, 'longitud': -70.3700},
    {'nombre': 'Nevados de Chillán', 'latitud': -36.8580, 'longitud': -71.3727},
    {'nombre': 'Antuco', 'latitud': -37.4100, 'longitud': -71.4200},
    {'nombre': 'Corralco', 'latitud': -38.3700, 'longitud': -71.5700},
    {'nombre': 'Las Araucarias', 'latitud': -38.7300, 'longitud': -71.7400},
    {'nombre': 'Pucón', 'latitud': -39.2830, 'longitud': -71.9442},
    {'nombre': 'Volcán Osorno', 'latitud': -41.1040, 'longitud': -72.5120},
    {'nombre': 'Antillanca', 'latitud': -40.7700, 'longitud': -72.2000},
    {'nombre': 'El Fraile', 'latitud': -45.4300, 'longitud': -72.1600},
    {'nombre': 'Cerro Mirador', 'latitud': -53.1400, 'longitud': -71.0600},

    # Argentina - Centros de Esquí
    {'nombre': 'Las Leñas', 'latitud': -35.1636, 'longitud': -70.0670},
    {'nombre': 'Los Penitentes', 'latitud': -32.8374, 'longitud': -69.8606},
    {'nombre': 'Catedral Alta Patagonia', 'latitud': -41.1617, 'longitud': -71.4440},
    {'nombre': 'Chapelco', 'latitud': -40.1281, 'longitud': -71.2420},
    {'nombre': 'Cerro Bayo', 'latitud': -40.7500, 'longitud': -71.6300},
    {'nombre': 'La Hoya', 'latitud': -43.1100, 'longitud': -71.2500},
    {'nombre': 'Cerro Castor', 'latitud': -54.7400, 'longitud': -68.1800},

    # Europa - Alpes
    {'nombre': 'Chamonix Mont Blanc', 'latitud': 45.9237, 'longitud': 6.8694},
    {'nombre': 'Zermatt', 'latitud': 46.0207, 'longitud': 7.7491},
    {'nombre': 'Verbier', 'latitud': 46.0968, 'longitud': 7.2287},
    {'nombre': 'St. Anton am Arlberg', 'latitud': 47.1295, 'longitud': 10.2673},
    {'nombre': 'Val d\'Isère', 'latitud': 45.4485, 'longitud': 6.9806},
    {'nombre': 'Courchevel', 'latitud': 45.4150, 'longitud': 6.6345},

    # Norteamérica
    {'nombre': 'Jackson Hole', 'latitud': 43.5875, 'longitud': -110.8280},
    {'nombre': 'Squaw Valley', 'latitud': 39.1970, 'longitud': -120.2357},
    {'nombre': 'Whistler Blackcomb', 'latitud': 50.1163, 'longitud': -122.9574},
    {'nombre': 'Revelstoke', 'latitud': 51.0447, 'longitud': -118.1956},

    # Bases de Montañismo
    {'nombre': 'Plaza de Mulas Aconcagua', 'latitud': -32.6510, 'longitud': -70.0108},
    {'nombre': 'Plaza Argentina Aconcagua', 'latitud': -32.6370, 'longitud': -69.9480},
]


# ============================================================================
# EXCEPCIONES PERSONALIZADAS
# ============================================================================

class ErrorAnalisisTopografico(Exception):
    """Error durante el análisis topográfico con GEE."""
    pass


class ErrorAlmacenamientoBigQuery(Exception):
    """Error al almacenar datos en BigQuery."""
    pass


class ErrorAlmacenamientoGCS(Exception):
    """Error al almacenar datos en Cloud Storage."""
    pass


# ============================================================================
# FUNCIONES DE ALMACENAMIENTO
# ============================================================================

def crear_cliente_bigquery() -> bigquery.Client:
    """Crea un cliente de BigQuery."""
    return bigquery.Client(project=ID_PROYECTO)


def crear_cliente_storage() -> storage.Client:
    """Crea un cliente de Cloud Storage."""
    return storage.Client(project=ID_PROYECTO)


def preparar_fila_bigquery(
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    cubicacion: Dict[str, Any],
    indice_dict: Dict[str, Any],
    fecha_analisis: datetime
) -> Dict[str, Any]:
    """
    Prepara una fila para insertar en BigQuery.

    Args:
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud
        longitud: Longitud
        cubicacion: Resultado de cubicación
        indice_dict: Resultado de índice de riesgo
        fecha_analisis: Fecha/hora del análisis

    Returns:
        Dict: Fila formateada para BigQuery
    """
    fila = {
        # Identificación
        'nombre_ubicacion': nombre_ubicacion,
        'latitud': latitud,
        'longitud': longitud,
        'fecha_analisis': fecha_analisis.isoformat(),

        # Áreas
        'zona_inicio_ha': cubicacion.get('zona_inicio_ha', 0),
        'zona_transito_ha': cubicacion.get('zona_transito_ha', 0),
        'zona_deposito_ha': cubicacion.get('zona_deposito_ha', 0),
        'area_total_ha': cubicacion.get('area_total_ha', 0),
        'zona_inicio_pct': cubicacion.get('zona_inicio_pct', 0),
        'zona_transito_pct': cubicacion.get('zona_transito_pct', 0),
        'zona_deposito_pct': cubicacion.get('zona_deposito_pct', 0),

        # Pendientes zona inicio
        'pendiente_media_inicio': cubicacion.get('pendiente_media_inicio', 0),
        'pendiente_max_inicio': cubicacion.get('pendiente_max_inicio', 0),
        'pendiente_p90_inicio': cubicacion.get('pendiente_p90_inicio', 0),

        # Aspecto zona inicio
        'aspecto_predominante_inicio': cubicacion.get('aspecto_predominante_inicio', 0),

        # Elevaciones
        'elevacion_max_inicio': cubicacion.get('elevacion_max_inicio', 0),
        'elevacion_min_inicio': cubicacion.get('elevacion_min_inicio', 0),
        'elevacion_min_deposito': cubicacion.get('elevacion_min_deposito', 0),
        'desnivel_inicio_deposito': cubicacion.get('desnivel_inicio_deposito', 0),

        # Sub-zonas de inicio
        'inicio_moderado_ha': cubicacion.get('inicio_moderado_ha', 0),
        'inicio_severo_ha': cubicacion.get('inicio_severo_ha', 0),
        'inicio_extremo_ha': cubicacion.get('inicio_extremo_ha', 0),

        # Índice de riesgo
        'indice_riesgo_topografico': indice_dict.get('indice_riesgo_topografico', 0),
        'clasificacion_riesgo': indice_dict.get('clasificacion_riesgo', 'bajo'),
        'componente_area': indice_dict.get('componente_area', 0),
        'componente_pendiente': indice_dict.get('componente_pendiente', 0),
        'componente_aspecto': indice_dict.get('componente_aspecto', 0),
        'componente_desnivel': indice_dict.get('componente_desnivel', 0),

        # Estimaciones EAWS
        'frecuencia_estimada_eaws': indice_dict.get('frecuencia_estimada_eaws', 'nearly_none'),
        'tamano_estimado_eaws': indice_dict.get('tamano_estimado_eaws', 1),
        'peligro_eaws_base': indice_dict.get('peligro_eaws_base', 1),
        'descripcion_riesgo': indice_dict.get('descripcion_riesgo', ''),

        # Metadatos
        'hemisferio': cubicacion.get('hemisferio', 'sur'),
        'radio_analisis_metros': RADIO_ANALISIS,
        'resolucion_dem_metros': 30,
        'fuente_dem': 'USGS/SRTMGL1_003'
    }

    return fila


def insertar_en_bigquery(
    cliente: bigquery.Client,
    filas: List[Dict[str, Any]]
) -> None:
    """
    Inserta filas en la tabla de BigQuery.

    Args:
        cliente: Cliente de BigQuery
        filas: Lista de filas a insertar

    Raises:
        ErrorAlmacenamientoBigQuery: Si falla la inserción
    """
    tabla_id = f'{ID_PROYECTO}.{DATASET_BIGQUERY}.{TABLA_ZONAS}'

    try:
        errores = cliente.insert_rows_json(tabla_id, filas)

        if errores:
            logger.error(f"Errores al insertar en BigQuery: {errores}")
            raise ErrorAlmacenamientoBigQuery(f"Errores de inserción: {errores}")

        logger.info(f"Insertadas {len(filas)} filas en {tabla_id}")

    except Exception as e:
        logger.error(f"Error al insertar en BigQuery: {e}")
        raise ErrorAlmacenamientoBigQuery(str(e))


def guardar_resultado_json_gcs(
    cliente: storage.Client,
    nombre_ubicacion: str,
    datos: Dict[str, Any],
    fecha_analisis: datetime
) -> str:
    """
    Guarda el resultado del análisis como JSON en GCS (capa Bronce).

    Args:
        cliente: Cliente de Cloud Storage
        nombre_ubicacion: Nombre de la ubicación
        datos: Datos a guardar
        fecha_analisis: Fecha del análisis

    Returns:
        str: URI del archivo guardado
    """
    bucket = cliente.bucket(BUCKET_BRONCE)

    # Normalizar nombre para ruta
    nombre_normalizado = nombre_ubicacion.lower().replace(' ', '_').replace('/', '_')
    fecha_str = fecha_analisis.strftime('%Y/%m/%d')
    timestamp_str = fecha_analisis.strftime('%Y%m%d_%H%M%S')

    ruta_archivo = f'{PREFIJO_TOPOGRAFIA}/{fecha_str}/{nombre_normalizado}_{timestamp_str}.json'

    blob = bucket.blob(ruta_archivo)

    try:
        blob.upload_from_string(
            json.dumps(datos, ensure_ascii=False, indent=2, default=str),
            content_type='application/json'
        )

        uri = f'gs://{BUCKET_BRONCE}/{ruta_archivo}'
        logger.info(f"Resultado guardado en GCS: {uri}")

        return uri

    except Exception as e:
        logger.error(f"Error al guardar en GCS: {e}")
        raise ErrorAlmacenamientoGCS(str(e))


# ============================================================================
# ANÁLISIS PRINCIPAL
# ============================================================================

def analizar_ubicacion(
    ubicacion: Dict[str, Any],
    exportar_geotiff: bool = False,
    generar_mapas: bool = True,
    bucket_exportacion: str = None,
    fecha_analisis: datetime = None
) -> Dict[str, Any]:
    """
    Ejecuta el análisis topográfico completo para una ubicación.

    Args:
        ubicacion: Diccionario con nombre, latitud y longitud
        exportar_geotiff: Si exportar mapa como GeoTIFF a GCS
        generar_mapas: Si generar visualizaciones PNG y GeoJSON
        bucket_exportacion: Bucket para exportación GeoTIFF
        fecha_analisis: Fecha del análisis (para visualizaciones)

    Returns:
        Dict: Resultado completo del análisis incluyendo visualizaciones
    """
    nombre = ubicacion['nombre']
    latitud = ubicacion['latitud']
    longitud = ubicacion['longitud']

    if fecha_analisis is None:
        fecha_analisis = datetime.now(timezone.utc)

    logger.info(f"Analizando ubicación: {nombre} ({latitud}, {longitud})")

    try:
        # 1. Analizar zonas con GEE
        resultado_zonas = analizar_zonas_ubicacion(
            latitud=latitud,
            longitud=longitud,
            radio_metros=RADIO_ANALISIS
        )

        # 2. Cubicar zonas
        cubicacion = cubicar_zonas_completo(
            zonas_analizadas=resultado_zonas,
            latitud=latitud,
            longitud=longitud,
            nombre_ubicacion=nombre,
            radio_metros=RADIO_ANALISIS
        )

        # 3. Calcular índice de riesgo
        indice_resultado = calcular_indice_desde_cubicacion(cubicacion, latitud)
        indice_dict = convertir_resultado_a_dict(indice_resultado)

        # 4. Exportar GeoTIFF si se solicita
        tarea_exportacion = None
        if exportar_geotiff and bucket_exportacion:
            tarea_exportacion = exportar_mapa_gcs(
                imagen=resultado_zonas['mapa_combinado'],
                area_buffer=resultado_zonas['area_buffer'],
                nombre_ubicacion=nombre,
                bucket=bucket_exportacion
            )

        # 5. Generar visualizaciones (mapas PNG y GeoJSON)
        visualizaciones = None
        if generar_mapas:
            try:
                visualizaciones = generar_visualizaciones_completas(
                    nombre_ubicacion=nombre,
                    latitud=latitud,
                    longitud=longitud,
                    radio_metros=RADIO_ANALISIS,
                    cubicacion=cubicacion,
                    indice_dict=indice_dict,
                    fecha_analisis=fecha_analisis
                )
                logger.info(f"Visualizaciones generadas para {nombre}")
            except Exception as e:
                logger.warning(f"No se pudieron generar visualizaciones para {nombre}: {e}")
                visualizaciones = None

        return {
            'exito': True,
            'nombre': nombre,
            'latitud': latitud,
            'longitud': longitud,
            'cubicacion': cubicacion,
            'indice': indice_dict,
            'visualizaciones': visualizaciones,
            'tarea_exportacion': tarea_exportacion
        }

    except Exception as e:
        logger.error(f"Error analizando {nombre}: {e}")
        return {
            'exito': False,
            'nombre': nombre,
            'latitud': latitud,
            'longitud': longitud,
            'error': str(e)
        }


def procesar_lote(
    ubicaciones: List[Dict[str, Any]],
    cliente_bq: bigquery.Client,
    cliente_gcs: storage.Client,
    fecha_analisis: datetime,
    exportar_geotiff: bool = False,
    generar_mapas: bool = True,
    bucket_exportacion: str = None
) -> Dict[str, Any]:
    """
    Procesa un lote de ubicaciones.

    Args:
        ubicaciones: Lista de ubicaciones a procesar
        cliente_bq: Cliente de BigQuery
        cliente_gcs: Cliente de Cloud Storage
        fecha_analisis: Fecha/hora del análisis
        exportar_geotiff: Si exportar mapas GeoTIFF
        generar_mapas: Si generar visualizaciones PNG y GeoJSON
        bucket_exportacion: Bucket para GeoTIFF

    Returns:
        Dict: Resumen de procesamiento del lote
    """
    filas_bigquery = []
    exitosos = 0
    fallidos = 0

    for ubicacion in ubicaciones:
        resultado = analizar_ubicacion(
            ubicacion,
            exportar_geotiff=exportar_geotiff,
            generar_mapas=generar_mapas,
            bucket_exportacion=bucket_exportacion,
            fecha_analisis=fecha_analisis
        )

        if resultado['exito']:
            # Preparar fila para BigQuery
            fila = preparar_fila_bigquery(
                nombre_ubicacion=resultado['nombre'],
                latitud=resultado['latitud'],
                longitud=resultado['longitud'],
                cubicacion=resultado['cubicacion'],
                indice_dict=resultado['indice'],
                fecha_analisis=fecha_analisis
            )
            filas_bigquery.append(fila)

            # Guardar JSON en GCS (capa Bronce)
            datos_completos = {
                'nombre_ubicacion': resultado['nombre'],
                'coordenadas': {
                    'latitud': resultado['latitud'],
                    'longitud': resultado['longitud']
                },
                'fecha_analisis': fecha_analisis.isoformat(),
                'cubicacion': resultado['cubicacion'],
                'indice_riesgo': resultado['indice']
            }

            try:
                guardar_resultado_json_gcs(
                    cliente_gcs,
                    resultado['nombre'],
                    datos_completos,
                    fecha_analisis
                )
            except ErrorAlmacenamientoGCS as e:
                logger.warning(f"No se pudo guardar JSON en GCS para {resultado['nombre']}: {e}")

            # Guardar visualizaciones en GCS (mapas PNG, thumbnails, GeoJSON)
            if resultado.get('visualizaciones'):
                try:
                    uris_vis = guardar_visualizaciones_gcs(
                        cliente_gcs=cliente_gcs,
                        bucket_nombre=BUCKET_BRONCE,
                        nombre_ubicacion=resultado['nombre'],
                        fecha_analisis=fecha_analisis,
                        mapa_png=resultado['visualizaciones'].get('mapa_png'),
                        thumbnail_png=resultado['visualizaciones'].get('thumbnail_png'),
                        geojson_data=resultado['visualizaciones'].get('geojson')
                    )
                    logger.info(f"Visualizaciones guardadas para {resultado['nombre']}: {len(uris_vis)} archivos")
                except Exception as e:
                    logger.warning(f"No se pudieron guardar visualizaciones para {resultado['nombre']}: {e}")

            exitosos += 1
        else:
            fallidos += 1

    # Insertar en BigQuery si hay filas
    if filas_bigquery:
        try:
            insertar_en_bigquery(cliente_bq, filas_bigquery)
        except ErrorAlmacenamientoBigQuery as e:
            logger.error(f"Error al insertar lote en BigQuery: {e}")
            # No reintentamos aquí, el error ya fue logueado

    return {
        'procesados': len(ubicaciones),
        'exitosos': exitosos,
        'fallidos': fallidos
    }


# ============================================================================
# ENTRY POINT DE CLOUD FUNCTION
# ============================================================================

@functions_framework.http
def analizar_topografia(solicitud: Request) -> Dict[str, Any]:
    """
    Entry point HTTP para Cloud Function.

    Analiza todas las ubicaciones de monitoreo y almacena resultados
    en BigQuery (capa Silver) y GCS (capa Bronze).

    Args:
        solicitud: Request HTTP de Cloud Scheduler

    Returns:
        Dict: Resumen de ejecución
    """
    inicio = datetime.now(timezone.utc)
    logger.info(f"Iniciando análisis topográfico: {inicio.isoformat()}")

    # Validar proyecto
    if not ID_PROYECTO:
        logger.error("ID_PROYECTO no configurado")
        return {'error': 'ID_PROYECTO no configurado'}, 500

    try:
        # Inicializar GEE
        inicializar_gee(PROYECTO_GEE)

        # Crear clientes
        cliente_bq = crear_cliente_bigquery()
        cliente_gcs = crear_cliente_storage()

        # Parámetros opcionales de la solicitud
        datos_solicitud = solicitud.get_json(silent=True) or {}
        exportar_geotiff = datos_solicitud.get('exportar_geotiff', False)
        generar_mapas = datos_solicitud.get('generar_mapas', True)  # Activado por defecto
        bucket_exportacion = datos_solicitud.get('bucket_exportacion', BUCKET_BRONCE)

        # Procesar en lotes
        total_exitosos = 0
        total_fallidos = 0

        for i in range(0, len(UBICACIONES_ANALISIS), TAMANO_LOTE):
            lote = UBICACIONES_ANALISIS[i:i + TAMANO_LOTE]
            num_lote = (i // TAMANO_LOTE) + 1
            total_lotes = (len(UBICACIONES_ANALISIS) + TAMANO_LOTE - 1) // TAMANO_LOTE

            logger.info(f"Procesando lote {num_lote}/{total_lotes} ({len(lote)} ubicaciones)")

            resultado_lote = procesar_lote(
                ubicaciones=lote,
                cliente_bq=cliente_bq,
                cliente_gcs=cliente_gcs,
                fecha_analisis=inicio,
                exportar_geotiff=exportar_geotiff,
                generar_mapas=generar_mapas,
                bucket_exportacion=bucket_exportacion
            )

            total_exitosos += resultado_lote['exitosos']
            total_fallidos += resultado_lote['fallidos']

            # Pausa entre lotes
            if i + TAMANO_LOTE < len(UBICACIONES_ANALISIS):
                logger.info(f"Pausa de {PAUSA_ENTRE_LOTES}s entre lotes...")
                time.sleep(PAUSA_ENTRE_LOTES)

        fin = datetime.now(timezone.utc)
        duracion = (fin - inicio).total_seconds()

        resumen = {
            'estado': 'completado',
            'fecha_analisis': inicio.isoformat(),
            'duracion_segundos': duracion,
            'total_ubicaciones': len(UBICACIONES_ANALISIS),
            'exitosos': total_exitosos,
            'fallidos': total_fallidos,
            'exportacion_geotiff': exportar_geotiff,
            'generacion_mapas': generar_mapas
        }

        logger.info(f"Análisis topográfico completado: {resumen}")

        return resumen, 200

    except Exception as e:
        logger.error(f"Error fatal en análisis topográfico: {e}", exc_info=True)
        return {'error': str(e), 'estado': 'fallido'}, 500


# ============================================================================
# EJECUCIÓN LOCAL
# ============================================================================

if __name__ == '__main__':
    """
    Permite ejecutar el análisis localmente para pruebas.

    Uso:
        python main.py [--ubicacion NOMBRE] [--geotiff]
    """
    import argparse

    parser = argparse.ArgumentParser(description='Análisis topográfico de avalanchas')
    parser.add_argument(
        '--ubicacion',
        type=str,
        help='Nombre de ubicación específica a analizar'
    )
    parser.add_argument(
        '--geotiff',
        action='store_true',
        help='Exportar mapas GeoTIFF a GCS'
    )
    parser.add_argument(
        '--proyecto',
        type=str,
        default='',
        help='ID del proyecto GCP/GEE'
    )

    args = parser.parse_args()

    # Configurar proyecto si se proporciona
    if args.proyecto:
        os.environ['GCP_PROJECT'] = args.proyecto
        os.environ['GEE_PROJECT'] = args.proyecto

    # Inicializar GEE
    proyecto = args.proyecto or ID_PROYECTO or 'tu-proyecto-gcp'
    print(f"Inicializando GEE con proyecto: {proyecto}")
    inicializar_gee(proyecto)

    # Filtrar ubicación si se especifica
    if args.ubicacion:
        ubicaciones = [
            u for u in UBICACIONES_ANALISIS
            if args.ubicacion.lower() in u['nombre'].lower()
        ]
        if not ubicaciones:
            print(f"No se encontró ubicación: {args.ubicacion}")
            exit(1)
    else:
        ubicaciones = UBICACIONES_ANALISIS[:3]  # Solo 3 para prueba

    print(f"\nAnalizando {len(ubicaciones)} ubicación(es):")
    for u in ubicaciones:
        print(f"  - {u['nombre']} ({u['latitud']}, {u['longitud']})")

    # Ejecutar análisis
    for ubicacion in ubicaciones:
        print(f"\n{'='*60}")
        resultado = analizar_ubicacion(
            ubicacion,
            exportar_geotiff=args.geotiff,
            bucket_exportacion=BUCKET_BRONCE if args.geotiff else None
        )

        if resultado['exito']:
            print(f"\n✓ {resultado['nombre']}")
            print(f"  Zona Inicio: {resultado['cubicacion']['zona_inicio_ha']:.2f} ha "
                  f"({resultado['cubicacion']['zona_inicio_pct']:.1f}%)")
            print(f"  Zona Tránsito: {resultado['cubicacion']['zona_transito_ha']:.2f} ha")
            print(f"  Zona Depósito: {resultado['cubicacion']['zona_deposito_ha']:.2f} ha")
            print(f"  Índice Riesgo: {resultado['indice']['indice_riesgo_topografico']:.1f} "
                  f"({resultado['indice']['clasificacion_riesgo'].upper()})")
            print(f"  EAWS Base: Peligro {resultado['indice']['peligro_eaws_base']}")
        else:
            print(f"\n✗ {resultado['nombre']}: {resultado['error']}")

    print(f"\n{'='*60}")
    print("Análisis local completado")

"""
Extractor Histórico de Datos Meteorológicos — Open-Meteo Historical API

Cloud Function HTTP que realiza backfill de condiciones meteorológicas históricas
usando la API gratuita de Open-Meteo (archive-api.open-meteo.com).

Diseñado para llenar el gap de datos entre:
- Fechas Snowlab validación H4: jun 2024 – sep 2025
- Fechas SLF Suiza validación H1/H3: temporadas invierno 2023-2025

Los registros se insertan en `clima.condiciones_actuales` con el campo
`fuente='openmeteo_historical'` para distinguirlos de los datos en tiempo real.

Uso (trigger HTTP manual):
    POST https://REGION-PROJECT.cloudfunctions.net/extractor_historico
    Content-Type: application/json
    {
        "ubicaciones": ["La Parva Sector Bajo", "Interlaken"],
        "fecha_inicio": "2024-06-15",
        "fecha_fin": "2025-09-21"
    }

Procesa en chunks de 30 días para evitar timeout de Cloud Functions (max 540s).
Es idempotente: omite registros ya existentes en BQ.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import functions_framework
import requests
from google.cloud import bigquery
from flask import Request

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GCP_PROJECT   = os.environ.get('GCP_PROJECT', os.environ.get('GOOGLE_CLOUD_PROJECT', 'climas-chileno'))
DATASET       = 'clima'
TABLA_DESTINO = 'condiciones_actuales'
FUENTE_TAG    = 'openmeteo_historical'

# Tamaño de chunk para evitar timeout de Cloud Functions (max 540s)
CHUNK_DIAS = 30

# API Open-Meteo Historical (gratuita, sin key, datos desde 1940)
URL_OPEN_METEO_ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'

# Variables horarias a solicitar
VARIABLES_HORARIAS = [
    'temperature_2m',
    'precipitation',
    'snowfall',
    'snow_depth',
    'wind_speed_10m',
    'wind_direction_10m',
    'relative_humidity_2m',
    'surface_pressure',
    'cloud_cover',
    'weather_code',
]

# Catálogo de ubicaciones con coordenadas
UBICACIONES: dict[str, dict[str, float]] = {
    # ── Andes Chile ───────────────────────────────────────────────────────────
    'La Parva Sector Bajo':  {'latitud': -33.363, 'longitud': -70.301},
    'La Parva Sector Medio': {'latitud': -33.352, 'longitud': -70.290},
    'La Parva Sector Alto':  {'latitud': -33.344, 'longitud': -70.280},
    'Valle Nevado':          {'latitud': -33.357, 'longitud': -70.270},
    'El Colorado':           {'latitud': -33.352, 'longitud': -70.268},
    # ── Alpes Suizos ─────────────────────────────────────────────────────────
    'Interlaken':            {'latitud': 46.686,  'longitud':  7.863},
    'Matterhorn Zermatt':    {'latitud': 45.976,  'longitud':  7.659},
    'St Moritz':             {'latitud': 46.491,  'longitud':  9.836},
}

# Mapeo WMO weather code → condición legible
_WMO_CONDICION: dict[int, str] = {
    0: 'despejado', 1: 'principalmente_despejado', 2: 'parcialmente_nublado',
    3: 'nublado', 45: 'niebla', 48: 'niebla_escarcha',
    51: 'llovizna_ligera', 53: 'llovizna_moderada', 55: 'llovizna_densa',
    61: 'lluvia_ligera', 63: 'lluvia_moderada', 65: 'lluvia_intensa',
    71: 'nevada_ligera', 73: 'nevada_moderada', 75: 'nevada_intensa',
    77: 'granos_nieve', 80: 'chubascos_ligeros', 81: 'chubascos_moderados',
    82: 'chubascos_violentos', 85: 'chubascos_nieve', 86: 'chubascos_nieve_intensos',
    95: 'tormenta', 96: 'tormenta_granizo', 99: 'tormenta_granizo_intenso',
}


@functions_framework.http
def extractor_historico(request: Request) -> tuple[str, int]:
    """Punto de entrada HTTP para el backfill histórico."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}

    ubicaciones_solicitadas = payload.get('ubicaciones') or list(UBICACIONES.keys())
    fecha_inicio_str = payload.get('fecha_inicio', '2024-06-15')
    fecha_fin_str    = payload.get('fecha_fin',   '2025-09-21')
    dry_run          = bool(payload.get('dry_run', False))

    try:
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        fecha_fin    = date.fromisoformat(fecha_fin_str)
    except ValueError as e:
        return json.dumps({'error': f'Fecha inválida: {e}'}), 400

    ubicaciones_validas = [u for u in ubicaciones_solicitadas if u in UBICACIONES]
    ubicaciones_invalidas = [u for u in ubicaciones_solicitadas if u not in UBICACIONES]
    if ubicaciones_invalidas:
        logger.warning(f"Ubicaciones desconocidas ignoradas: {ubicaciones_invalidas}")
    if not ubicaciones_validas:
        return json.dumps({'error': 'No hay ubicaciones válidas en el catálogo'}), 400

    logger.info(
        f"Iniciando backfill histórico: {len(ubicaciones_validas)} ubicaciones, "
        f"{fecha_inicio_str} → {fecha_fin_str}, dry_run={dry_run}"
    )

    cliente_bq = bigquery.Client(project=GCP_PROJECT)
    resumen: dict[str, Any] = {}

    for ubicacion in ubicaciones_validas:
        coords = UBICACIONES[ubicacion]
        total_insertadas, total_omitidas, errores = 0, 0, []

        for chunk_inicio, chunk_fin in _generar_chunks(fecha_inicio, fecha_fin, CHUNK_DIAS):
            try:
                datos_raw = _llamar_open_meteo(
                    lat=coords['latitud'],
                    lon=coords['longitud'],
                    fecha_inicio=chunk_inicio,
                    fecha_fin=chunk_fin,
                )
                filas = _parsear_respuesta(datos_raw, ubicacion, coords)
                ins, omit = _insertar_filas(
                    cliente_bq, filas, dry_run=dry_run
                )
                total_insertadas += ins
                total_omitidas   += omit
            except Exception as e:
                msg = f"Error en chunk {chunk_inicio}→{chunk_fin}: {e}"
                logger.error(f"[{ubicacion}] {msg}")
                errores.append(msg)

        resumen[ubicacion] = {
            'insertadas': total_insertadas,
            'omitidas':   total_omitidas,
            'errores':    errores,
        }
        logger.info(
            f"[{ubicacion}] completado: {total_insertadas} insertadas, "
            f"{total_omitidas} omitidas, {len(errores)} errores"
        )

    return json.dumps({'resumen': resumen, 'dry_run': dry_run}, ensure_ascii=False), 200


def _generar_chunks(
    fecha_inicio: date,
    fecha_fin: date,
    chunk_dias: int,
) -> list[tuple[date, date]]:
    """Genera pares (inicio, fin) de chunks de chunk_dias días."""
    chunks = []
    cursor = fecha_inicio
    while cursor <= fecha_fin:
        fin_chunk = min(cursor + timedelta(days=chunk_dias - 1), fecha_fin)
        chunks.append((cursor, fin_chunk))
        cursor = fin_chunk + timedelta(days=1)
    return chunks


def _llamar_open_meteo(
    lat: float,
    lon: float,
    fecha_inicio: date,
    fecha_fin: date,
) -> dict:
    """
    Llama a la Historical API de Open-Meteo para el rango de fechas.
    Retorna el JSON de respuesta.
    """
    params = {
        'latitude':    lat,
        'longitude':   lon,
        'start_date':  fecha_inicio.isoformat(),
        'end_date':    fecha_fin.isoformat(),
        'hourly':      ','.join(VARIABLES_HORARIAS),
        'wind_speed_unit': 'kmh',
        'timezone':    'UTC',
    }
    resp = requests.get(URL_OPEN_METEO_ARCHIVE, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _parsear_respuesta(
    datos: dict,
    ubicacion: str,
    coords: dict[str, float],
) -> list[dict]:
    """
    Parsea la respuesta de Open-Meteo y produce una lista de filas BQ,
    una por hora, en formato compatible con `clima.condiciones_actuales`.
    """
    horario = datos.get('hourly', {})
    tiempos = horario.get('time', [])
    if not tiempos:
        return []

    # Extraer columnas horarias
    temp_2m    = horario.get('temperature_2m',      [None] * len(tiempos))
    precip     = horario.get('precipitation',        [None] * len(tiempos))
    snowfall   = horario.get('snowfall',             [None] * len(tiempos))
    snow_depth = horario.get('snow_depth',           [None] * len(tiempos))
    wind_spd   = horario.get('wind_speed_10m',       [None] * len(tiempos))
    wind_dir   = horario.get('wind_direction_10m',   [None] * len(tiempos))
    humidity   = horario.get('relative_humidity_2m', [None] * len(tiempos))
    pressure   = horario.get('surface_pressure',     [None] * len(tiempos))
    cloud      = horario.get('cloud_cover',          [None] * len(tiempos))
    wmo_code   = horario.get('weather_code',         [None] * len(tiempos))

    filas = []
    for i, tiempo_str in enumerate(tiempos):
        try:
            dt_utc = datetime.fromisoformat(tiempo_str).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        codigo_wmo = wmo_code[i]
        condicion  = _WMO_CONDICION.get(int(codigo_wmo), 'desconocida') if codigo_wmo is not None else None
        es_nevada  = condicion is not None and 'nieve' in condicion or 'nevada' in condicion if condicion else False

        fila: dict[str, Any] = {
            'nombre_ubicacion':      ubicacion,
            'latitud':               coords['latitud'],
            'longitud':              coords['longitud'],
            'hora_actual':           dt_utc.isoformat(),
            'zona_horaria':          'UTC',
            'temperatura':           _redondear(temp_2m[i]),
            'sensacion_termica':     None,
            'punto_rocio':           None,
            'indice_calor':          None,
            'sensacion_viento':      None,
            'condicion_clima':       condicion,
            'descripcion_clima':     condicion,
            'probabilidad_precipitacion': None,
            'precipitacion_acumulada':    _redondear(precip[i]),
            'presion_aire':          _redondear(pressure[i]),
            'velocidad_viento':      _redondear(wind_spd[i]),
            'direccion_viento':      int(wind_dir[i]) if wind_dir[i] is not None else None,
            'visibilidad':           None,
            'humedad_relativa':      int(humidity[i]) if humidity[i] is not None else None,
            'indice_uv':             None,
            'probabilidad_tormenta': None,
            'cobertura_nubes':       int(cloud[i]) if cloud[i] is not None else None,
            'es_dia':                None,
            'marca_tiempo_ingestion': datetime.now(timezone.utc).isoformat(),
            'uri_datos_crudos':      None,
            'datos_json_crudo':      json.dumps({
                'fuente': FUENTE_TAG,
                'snowfall_cm':   _redondear(snowfall[i]),
                'snow_depth_m':  _redondear(snow_depth[i]),
                'wmo_code':      codigo_wmo,
                'es_nevada':     es_nevada,
            }),
            # Campo extra para distinguir backfill de datos tiempo real
            'fuente':                FUENTE_TAG,
        }
        filas.append(fila)

    return filas


def _redondear(valor: Any, decimales: int = 2) -> float | None:
    if valor is None:
        return None
    try:
        return round(float(valor), decimales)
    except (TypeError, ValueError):
        return None


def _insertar_filas(
    cliente_bq: bigquery.Client,
    filas: list[dict],
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Inserta las filas en BigQuery de forma idempotente.

    Retorna (n_insertadas, n_omitidas).
    """
    if not filas:
        return 0, 0

    tabla_ref = f'{GCP_PROJECT}.{DATASET}.{TABLA_DESTINO}'

    # Obtener horas ya existentes para esta ubicación en el rango
    ubicacion = filas[0]['nombre_ubicacion']
    hora_min  = filas[0]['hora_actual']
    hora_max  = filas[-1]['hora_actual']

    try:
        query = f"""
            SELECT hora_actual
            FROM `{tabla_ref}`
            WHERE nombre_ubicacion = @ubicacion
              AND hora_actual BETWEEN @hora_min AND @hora_max
              AND fuente = @fuente
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter('ubicacion', 'STRING',    ubicacion),
            bigquery.ScalarQueryParameter('hora_min',  'TIMESTAMP', hora_min),
            bigquery.ScalarQueryParameter('hora_max',  'TIMESTAMP', hora_max),
            bigquery.ScalarQueryParameter('fuente',    'STRING',    FUENTE_TAG),
        ])
        existentes = {
            row['hora_actual'].isoformat()
            for row in cliente_bq.query(query, job_config=job_config).result()
        }
    except Exception as e:
        logger.warning(f"No se pudo consultar existentes para {ubicacion}: {e} — se inserta todo")
        existentes = set()

    nuevas = [f for f in filas if f['hora_actual'] not in existentes]
    omitidas = len(filas) - len(nuevas)

    if not nuevas or dry_run:
        return 0, len(filas) - len(nuevas)

    errores = cliente_bq.insert_rows_json(tabla_ref, nuevas)
    if errores:
        msgs = [str(e) for e in errores[:5]]
        raise RuntimeError(f"Errores BQ insert_rows_json: {msgs}")

    return len(nuevas), omitidas

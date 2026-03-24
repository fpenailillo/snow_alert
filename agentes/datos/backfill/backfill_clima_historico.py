"""
Backfill de datos climáticos históricos desde ERA5-Land via Google Earth Engine.

Obtiene datos reales de invierno para las ubicaciones de La Parva e inserta
en las tablas condiciones_actuales y pronostico_dias de BigQuery.

El script es idempotente: verifica si ya existe una fila para cada
(fecha, ubicacion) antes de insertar, para evitar duplicados.

Fuente: ECMWF/ERA5_LAND/HOURLY — reanálisis ERA5-Land, disponible desde 1950.
Resolución: ~9 km, cobertura horaria global.

Conversiones de unidades:
    - temperature_2m, dewpoint_temperature_2m : Kelvin → °C (restar 273.15)
    - u/v_component_of_wind_10m              : m/s → km/h (*3.6), dirección via atan2
    - total_precipitation_hourly             : m → mm (*1000)
    - snowfall_hourly                        : m → mm (*1000)
    - snow_depth                             : m → cm (*100)
    - surface_pressure                       : Pa → hPa (/100)

Uso:
    GCP_PROJECT=climas-chileno python agentes/datos/backfill/backfill_clima_historico.py
    GCP_PROJECT=climas-chileno python agentes/datos/backfill/backfill_clima_historico.py \\
        --ubicaciones "La Parva Sector Bajo" \\
        --fechas 2024-06-15 2024-07-01
"""

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import ee
from google.cloud import bigquery

# Agregar raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constantes del proyecto
GCP_PROJECT = os.environ.get('GCP_PROJECT', 'climas-chileno')
DATASET = 'clima'
TABLA_CONDICIONES = 'condiciones_actuales'
TABLA_PRONOSTICO = 'pronostico_dias'

# ID colección ERA5-Land en GEE
ERA5_COLLECTION = 'ECMWF/ERA5_LAND/HOURLY'

# Bandas ERA5 a extraer
BANDAS_ERA5 = [
    'temperature_2m',
    'dewpoint_temperature_2m',
    'u_component_of_wind_10m',
    'v_component_of_wind_10m',
    'total_precipitation_hourly',
    'snowfall_hourly',
    'snow_depth',
    'surface_pressure',
    'snow_cover',
]

# Coordenadas de las ubicaciones de La Parva
UBICACIONES_LA_PARVA = {
    "La Parva Sector Bajo":  {"latitud": -33.363, "longitud": -70.301},
    "La Parva Sector Medio": {"latitud": -33.352, "longitud": -70.290},
    "La Parva Sector Alto":  {"latitud": -33.344, "longitud": -70.280},
}

# Fechas de invierno 2024 y 2025 (hemisferio sur: junio-septiembre)
FECHAS_INVIERNO_DEFAULT = [
    "2024-06-15", "2024-07-01", "2024-07-15",
    "2024-08-01", "2024-08-15", "2024-09-01", "2024-09-15",
    "2025-06-15", "2025-07-01", "2025-07-15",
    "2025-08-01", "2025-08-15", "2025-09-01", "2025-09-15",
]

# Offset UTC para zona horaria Chile invierno (UTC-3)
UTC_OFFSET_CHILE = -3


# ============================================================================
# FUNCIONES DE CONVERSIÓN DE UNIDADES ERA5
# ============================================================================

def kelvin_a_celsius(k: float | None) -> float | None:
    """Convierte Kelvin a Celsius."""
    if k is None:
        return None
    return round(k - 273.15, 2)


def calcular_velocidad_viento_kmh(u: float | None, v: float | None) -> float | None:
    """Calcula velocidad del viento en km/h desde componentes u/v (m/s)."""
    if u is None or v is None:
        return None
    return round(math.sqrt(u**2 + v**2) * 3.6, 2)


def calcular_direccion_viento(u: float | None, v: float | None) -> float | None:
    """
    Calcula dirección meteorológica del viento en grados (0=Norte, 90=Este).

    Convención meteorológica: dirección FROM (de donde viene el viento).
    """
    if u is None or v is None:
        return None
    angulo = math.atan2(-u, -v) * 180 / math.pi
    return round(angulo % 360, 1)


def calcular_humedad_relativa(temp_k: float | None, dewpoint_k: float | None) -> float | None:
    """
    Calcula humedad relativa (%) desde temperatura y punto de rocío (Kelvin).

    Usa aproximación de Magnus (error < 0.3% para -40°C a 60°C).
    """
    if temp_k is None or dewpoint_k is None:
        return None
    t = temp_k - 273.15
    td = dewpoint_k - 273.15
    # Magnus: e_s = 6.112 * exp(17.67*T / (T + 243.5))
    e_t = math.exp(17.67 * t / (t + 243.5))
    e_td = math.exp(17.67 * td / (td + 243.5))
    hr = 100.0 * (e_td / e_t)
    return round(min(100.0, max(0.0, hr)), 1)


def calcular_sensacion_termica(
    temp_c: float | None,
    vel_viento_kmh: float | None
) -> float | None:
    """
    Calcula sensación térmica (wind chill) para condiciones invernales.

    Fórmula Environment Canada (válida para T ≤ 10°C, V ≥ 5 km/h).
    """
    if temp_c is None or vel_viento_kmh is None:
        return None
    if temp_c > 10 or vel_viento_kmh < 5:
        return round(temp_c, 1)
    v016 = vel_viento_kmh ** 0.16
    chill = 13.12 + 0.6215 * temp_c - 11.37 * v016 + 0.3965 * temp_c * v016
    return round(chill, 1)


def derivar_condicion_clima(
    temp_c: float | None,
    precip_mm: float | None,
    snowfall_mm: float | None,
    humedad: float | None,
    snow_cover: float | None,
) -> tuple:
    """
    Deriva condición climática y descripción desde variables ERA5.

    Returns:
        Tupla (condicion_corta: str, descripcion_larga: str)
    """
    if snowfall_mm and snowfall_mm > 0.1:
        if snowfall_mm > 5.0:
            return "Nevada fuerte", "Nevada fuerte — más de 5 mm/h agua equivalente"
        elif snowfall_mm > 1.0:
            return "Nieve", "Nevada moderada — condiciones para acumulación"
        else:
            return "Nieve ligera", "Nevada leve — acumulación mínima"
    elif precip_mm and precip_mm > 0.1:
        if temp_c is not None and temp_c < 2:
            return "Lluvia engelante", "Lluvia engelante — riesgo de hielo en superficie"
        elif precip_mm > 5.0:
            return "Lluvia intensa", "Chubascos fuertes de lluvia"
        else:
            return "Lluvia", "Lluvia moderada"
    elif humedad and humedad > 92:
        return "Niebla", "Alta humedad con probable niebla o nubosidad densa"
    elif snow_cover and snow_cover > 80:
        return "Cubierto con nieve", "Cobertura de nieve alta, cielo nublado"
    else:
        return "Parcialmente nublado", "Condiciones de montaña mixtas"


def mapear_grados_a_direccion(grados: float | None) -> str:
    """Convierte grados azimut a dirección cardinal (N, NE, E, SE, S, SW, W, NW)."""
    if grados is None:
        return "N"
    grados = grados % 360
    direcciones = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return direcciones[int((grados + 22.5) / 45) % 8]


# ============================================================================
# EXTRACCIÓN ERA5 VIA GEE
# ============================================================================

def inicializar_gee() -> None:
    """Inicializa GEE con el proyecto configurado."""
    try:
        ee.Initialize(project=GCP_PROJECT)
        logger.info(f"[BackfillHistorico] GEE inicializado con proyecto: {GCP_PROJECT}")
    except Exception as e:
        logger.warning(f"[BackfillHistorico] GEE ya inicializado o advertencia: {e}")
        try:
            ee.Initialize()
        except Exception:
            pass


def obtener_datos_era5_gee(
    latitud: float,
    longitud: float,
    fecha_inicio: str,
    fecha_fin: str,
) -> dict:
    """
    Extrae serie temporal horaria de ERA5-Land para un punto geográfico.

    Usa getRegion() para obtener todas las horas en una sola llamada a la API GEE,
    minimizando el número de requests.

    Args:
        latitud:     Coordenada latitud del punto
        longitud:    Coordenada longitud del punto
        fecha_inicio: Fecha inicio en formato YYYY-MM-DD
        fecha_fin:   Fecha fin en formato YYYY-MM-DD (inclusive)

    Returns:
        Dict con listas horarias por variable (ya convertidas a unidades finales),
        o {"error": "..."} si falla.
    """
    try:
        punto = ee.Geometry.Point([longitud, latitud])

        # ERA5 tiene resolución ~0.1° (~9 km), usamos scale=11132 (aprox 0.1° en ecuador)
        coleccion = (
            ee.ImageCollection(ERA5_COLLECTION)
            .filterDate(fecha_inicio, fecha_fin + 'T23:59:59')
            .select(BANDAS_ERA5)
        )

        # getRegion devuelve [[header], [id, lon, lat, ts_ms, b1, b2, ...], ...]
        region_raw = coleccion.getRegion(punto, scale=11132).getInfo()

        if not region_raw or len(region_raw) < 2:
            return {"error": f"ERA5 sin datos para lat={latitud}, lon={longitud}, {fecha_inicio}→{fecha_fin}"}

        encabezado = region_raw[0]
        filas = region_raw[1:]

        # Mapear índices de columnas
        idx = {nombre: i for i, nombre in enumerate(encabezado)}

        # Construir dict de series horarias en unidades finales
        datos = {
            'tiempo_utc': [],
            'temperatura': [],       # °C
            'punto_rocio': [],       # °C
            'humedad_relativa': [],  # %
            'velocidad_viento': [],  # km/h
            'direccion_viento': [],  # grados
            'sensacion_termica': [], # °C
            'precipitacion': [],     # mm
            'nevadas': [],           # mm
            'profundidad_nieve': [], # cm
            'presion_aire': [],      # hPa
            'cobertura_nieve': [],   # %
        }

        for fila in filas:
            ts_ms = fila[idx.get('time', 3)]
            dt_utc = datetime.utcfromtimestamp(ts_ms / 1000) if ts_ms else None
            datos['tiempo_utc'].append(dt_utc)

            t2m = fila[idx['temperature_2m']] if 'temperature_2m' in idx else None
            dp2m = fila[idx['dewpoint_temperature_2m']] if 'dewpoint_temperature_2m' in idx else None
            u10 = fila[idx['u_component_of_wind_10m']] if 'u_component_of_wind_10m' in idx else None
            v10 = fila[idx['v_component_of_wind_10m']] if 'v_component_of_wind_10m' in idx else None
            precip = fila[idx['total_precipitation_hourly']] if 'total_precipitation_hourly' in idx else None
            snow_h = fila[idx['snowfall_hourly']] if 'snowfall_hourly' in idx else None
            snow_d = fila[idx['snow_depth']] if 'snow_depth' in idx else None
            pres = fila[idx['surface_pressure']] if 'surface_pressure' in idx else None
            snow_c = fila[idx['snow_cover']] if 'snow_cover' in idx else None

            temp_c = kelvin_a_celsius(t2m)
            dp_c = kelvin_a_celsius(dp2m)
            vel_kmh = calcular_velocidad_viento_kmh(u10, v10)
            dir_deg = calcular_direccion_viento(u10, v10)
            hr = calcular_humedad_relativa(t2m, dp2m)
            sens = calcular_sensacion_termica(temp_c, vel_kmh)

            datos['temperatura'].append(temp_c)
            datos['punto_rocio'].append(dp_c)
            datos['humedad_relativa'].append(hr)
            datos['velocidad_viento'].append(vel_kmh)
            datos['direccion_viento'].append(dir_deg)
            datos['sensacion_termica'].append(sens)
            datos['precipitacion'].append(round(precip * 1000, 2) if precip is not None else None)
            datos['nevadas'].append(round(snow_h * 1000, 2) if snow_h is not None else None)
            datos['profundidad_nieve'].append(round(snow_d * 100, 1) if snow_d is not None else None)
            datos['presion_aire'].append(round(pres / 100, 1) if pres is not None else None)
            datos['cobertura_nieve'].append(round(snow_c, 1) if snow_c is not None else None)

        logger.info(
            f"[BackfillHistorico] ERA5 OK — lat={latitud}, lon={longitud}, "
            f"{fecha_inicio}→{fecha_fin}: {len(filas)} horas extraídas"
        )
        return datos

    except Exception as e:
        logger.error(f"[BackfillHistorico] Error extrayendo ERA5: {e}")
        return {"error": str(e)}


def _filtrar_hora_local(datos: dict, fecha: str, hora_local: int = 15) -> dict:
    """
    Extrae los valores de una hora local específica para una fecha dada.

    Chile está en UTC-3 (invierno), por lo que hora_local=15 → UTC=18.

    Args:
        datos:       Dict con listas horarias de ERA5
        fecha:       Fecha en formato YYYY-MM-DD
        hora_local:  Hora local deseada (default: 15:00)

    Returns:
        Dict con valores escalares para esa hora
    """
    hora_utc = (hora_local - UTC_OFFSET_CHILE) % 24  # 15 local → 18 UTC
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")

    tiempos = datos.get('tiempo_utc', [])
    variables = [k for k in datos if k != 'tiempo_utc']

    # Buscar índice de la hora UTC deseada
    indice_objetivo = None
    for i, t in enumerate(tiempos):
        if t and t.date() == fecha_dt.date() and t.hour == hora_utc:
            indice_objetivo = i
            break

    # Fallback: primera hora disponible del día
    if indice_objetivo is None:
        for i, t in enumerate(tiempos):
            if t and t.date() == fecha_dt.date():
                indice_objetivo = i
                logger.warning(
                    f"[BackfillHistorico] Hora {hora_utc} UTC no encontrada para {fecha}, "
                    f"usando hora {t.hour} UTC como fallback"
                )
                break

    if indice_objetivo is None:
        return {}

    return {var: datos[var][indice_objetivo] for var in variables}


def _agregar_diario(datos: dict, fecha: str) -> dict:
    """
    Calcula estadísticas diarias (max, min, sum) desde la serie horaria.

    Args:
        datos:  Dict con listas horarias de ERA5
        fecha:  Fecha en formato YYYY-MM-DD

    Returns:
        Dict con valores diarios agregados
    """
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
    tiempos = datos.get('tiempo_utc', [])

    # Filtrar índices del día (en UTC, incluyendo horas de días adyacentes que
    # corresponden al día local en UTC-3)
    indices_dia = []
    for i, t in enumerate(tiempos):
        if t:
            # Convertir UTC → local para determinar a qué día local pertenece
            dt_local = t + timedelta(hours=UTC_OFFSET_CHILE)
            if dt_local.date() == fecha_dt.date():
                indices_dia.append(i)

    if not indices_dia:
        return {}

    def _vals(var):
        return [datos[var][i] for i in indices_dia if datos[var][i] is not None]

    temps = _vals('temperatura')
    vientos = _vals('velocidad_viento')
    dirs_viento = _vals('direccion_viento')
    precips = _vals('precipitacion')
    nevadas = _vals('nevadas')
    humedades = _vals('humedad_relativa')
    coberturas = _vals('cobertura_nieve')

    return {
        'temp_max': max(temps) if temps else None,
        'temp_min': min(temps) if temps else None,
        'viento_max': max(vientos) if vientos else None,
        'dir_viento_dom': _direccion_dominante(dirs_viento),
        'precipitacion_total': round(sum(precips), 2) if precips else 0.0,
        'nevada_total': round(sum(nevadas), 2) if nevadas else 0.0,
        'humedad_media': round(sum(humedades) / len(humedades), 1) if humedades else None,
        'cobertura_nieve_media': round(sum(coberturas) / len(coberturas), 1) if coberturas else None,
    }


def _direccion_dominante(dirs: list) -> float | None:
    """Calcula dirección de viento dominante usando media circular."""
    if not dirs:
        return None
    sin_sum = sum(math.sin(math.radians(d)) for d in dirs)
    cos_sum = sum(math.cos(math.radians(d)) for d in dirs)
    return round(math.atan2(sin_sum, cos_sum) * 180 / math.pi % 360, 1)


# ============================================================================
# IDEMPOTENCIA BQ
# ============================================================================

def _existe_condicion_actual(
    cliente_bq: bigquery.Client,
    nombre_ubicacion: str,
    fecha: str
) -> bool:
    sql = f"""
        SELECT COUNT(*) as total
        FROM `{GCP_PROJECT}.{DATASET}.{TABLA_CONDICIONES}`
        WHERE nombre_ubicacion = @ubicacion
          AND DATE(hora_actual) = @fecha
    """
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("ubicacion", "STRING", nombre_ubicacion),
        bigquery.ScalarQueryParameter("fecha", "DATE", fecha),
    ])
    resultado = list(cliente_bq.query(sql, job_config=config).result())
    return resultado[0]["total"] > 0


def _existe_pronostico_dia(
    cliente_bq: bigquery.Client,
    nombre_ubicacion: str,
    fecha: str
) -> bool:
    sql = f"""
        SELECT COUNT(*) as total
        FROM `{GCP_PROJECT}.{DATASET}.{TABLA_PRONOSTICO}`
        WHERE nombre_ubicacion = @ubicacion
          AND DATE(fecha_inicio) = @fecha
    """
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("ubicacion", "STRING", nombre_ubicacion),
        bigquery.ScalarQueryParameter("fecha", "DATE", fecha),
    ])
    resultado = list(cliente_bq.query(sql, job_config=config).result())
    return resultado[0]["total"] > 0


# ============================================================================
# INSERCIÓN EN BIGQUERY
# ============================================================================

def insertar_condicion_actual(
    cliente_bq: bigquery.Client,
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    fecha: str,
    datos_era5: dict,
) -> dict:
    """
    Inserta 1 fila en condiciones_actuales para la fecha dada (ERA5 hora 15:00 local).

    Si ya existe un registro para esa fecha+ubicacion, no inserta (idempotente).
    """
    logger.info(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → insertar condición actual (ERA5)")

    if _existe_condicion_actual(cliente_bq, nombre_ubicacion, fecha):
        logger.info(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → ya existe, se omite")
        return {"insertado": False, "razon": "ya_existe"}

    vals = _filtrar_hora_local(datos_era5, fecha, hora_local=15)
    if not vals:
        return {"insertado": False, "razon": "sin_datos_hora_15", "error": True}

    temp = vals.get('temperatura')
    vel = vals.get('velocidad_viento')
    precip = vals.get('precipitacion', 0.0) or 0.0
    nevada = vals.get('nevadas', 0.0) or 0.0
    condicion, descripcion = derivar_condicion_clima(
        temp_c=temp,
        precip_mm=precip,
        snowfall_mm=nevada,
        humedad=vals.get('humedad_relativa'),
        snow_cover=vals.get('cobertura_nieve'),
    )

    # hora_actual: 15:00 hora local → en timestamp con offset
    hora_actual_str = f"{fecha}T15:00:00-03:00"

    fila = {
        "nombre_ubicacion":          nombre_ubicacion,
        "latitud":                   latitud,
        "longitud":                  longitud,
        "zona_horaria":              "America/Santiago",
        "hora_actual":               hora_actual_str,
        "temperatura":               temp,
        "sensacion_termica":         vals.get('sensacion_termica'),
        "punto_rocio":               vals.get('punto_rocio'),
        "velocidad_viento":          vel,
        "direccion_viento":          vals.get('direccion_viento'),
        "precipitacion_acumulada":   precip,
        "probabilidad_precipitacion": 80.0 if precip > 0 else 10.0,
        "probabilidad_tormenta":     5.0,
        "humedad_relativa":          vals.get('humedad_relativa'),
        "presion_aire":              vals.get('presion_aire'),
        "cobertura_nubes":           vals.get('cobertura_nieve'),  # proxy
        "condicion_clima":           condicion,
        "descripcion_clima":         descripcion,
        "es_dia":                    True,
        "marca_tiempo_ingestion":    datetime.now(timezone.utc).isoformat(),
        "datos_json_crudo":          json.dumps({
            "fuente": "ERA5-Land ECMWF/ERA5_LAND/HOURLY",
            "hora_utc": 18,
            "fecha": fecha,
            **{k: v for k, v in vals.items()},
        }, ensure_ascii=False, default=str),
    }

    tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA_CONDICIONES}"
    errores = cliente_bq.insert_rows_json(tabla_ref, [fila])
    if errores:
        logger.error(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → error BQ: {errores}")
        return {"insertado": False, "razon": str(errores), "error": True}

    logger.info(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → condición actual OK "
                f"(T={temp}°C, V={vel}km/h, precip={precip}mm, nevada={nevada}mm)")
    return {"insertado": True, "razon": "ok"}


def insertar_pronostico_dias(
    cliente_bq: bigquery.Client,
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    fecha: str,
    datos_era5: dict,
) -> dict:
    """
    Inserta 3 filas en pronostico_dias (día 0, +1, +2) para la fecha base.

    Si ya existen registros para esa fecha+ubicacion, no inserta (idempotente).
    """
    logger.info(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → insertar pronóstico días (ERA5)")

    if _existe_pronostico_dia(cliente_bq, nombre_ubicacion, fecha):
        logger.info(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → pronóstico ya existe, se omite")
        return {"insertadas": 0, "razon": "ya_existe"}

    fecha_base = datetime.strptime(fecha, "%Y-%m-%d")
    filas = []

    for delta in range(3):
        fecha_dia = fecha_base + timedelta(days=delta)
        fecha_dia_str = fecha_dia.strftime("%Y-%m-%d")

        agr = _agregar_diario(datos_era5, fecha_dia_str)
        if not agr:
            logger.warning(f"[BackfillHistorico] {nombre_ubicacion} → sin datos diarios para {fecha_dia_str}")
            continue

        precip = agr.get('precipitacion_total', 0.0) or 0.0
        nevada = agr.get('nevada_total', 0.0) or 0.0
        temp_max = agr.get('temp_max')
        temp_min = agr.get('temp_min')
        viento_max = agr.get('viento_max')
        dir_dom = agr.get('dir_viento_dom')
        condicion, _ = derivar_condicion_clima(
            temp_c=temp_min,  # usar temp_min para estimar condición conservadora
            precip_mm=precip,
            snowfall_mm=nevada,
            humedad=agr.get('humedad_media'),
            snow_cover=agr.get('cobertura_nieve_media'),
        )
        dir_cardinal = mapear_grados_a_direccion(dir_dom)
        prob_precip = 80.0 if precip > 0 else 10.0

        fila = {
            "nombre_ubicacion":              nombre_ubicacion,
            "latitud":                       latitud,
            "longitud":                      longitud,
            "fecha_inicio":                  f"{fecha_dia_str}T00:00:00-03:00",
            "fecha_fin":                     f"{fecha_dia_str}T23:59:59-03:00",
            "anio":                          fecha_dia.year,
            "mes":                           fecha_dia.month,
            "dia":                           fecha_dia.day,
            "temp_max_dia":                  temp_max,
            "temp_min_dia":                  temp_min,
            # Diurno
            "diurno_condicion":              condicion,
            "diurno_temp_max":               temp_max,
            "diurno_temp_min":               temp_min,
            "diurno_velocidad_viento":       viento_max,
            "diurno_direccion_viento":       dir_cardinal,
            "diurno_cantidad_precipitacion": precip,
            "diurno_prob_precipitacion":     prob_precip,
            "diurno_humedad":                agr.get('humedad_media'),
            "diurno_cobertura_nubes":        agr.get('cobertura_nieve_media'),
            # Nocturno (mismos valores — ERA5 no distingue día/noche en este agregado)
            "nocturno_condicion":              condicion,
            "nocturno_temp_max":               temp_max,
            "nocturno_temp_min":               temp_min,
            "nocturno_velocidad_viento":       viento_max,
            "nocturno_direccion_viento":       dir_cardinal,
            "nocturno_cantidad_precipitacion": precip,
            "nocturno_prob_precipitacion":     prob_precip,
            "nocturno_humedad":                agr.get('humedad_media'),
            "nocturno_cobertura_nubes":        agr.get('cobertura_nieve_media'),
            # Metadatos
            "marca_tiempo_extraccion":       f"{fecha}T15:00:00-03:00",
            "marca_tiempo_ingestion":        datetime.now(timezone.utc).isoformat(),
        }
        filas.append(fila)

    if not filas:
        return {"insertadas": 0, "razon": "sin_datos_era5", "error": True}

    tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA_PRONOSTICO}"
    errores = cliente_bq.insert_rows_json(tabla_ref, filas)
    if errores:
        logger.error(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → error BQ pronóstico: {errores}")
        return {"insertadas": 0, "razon": str(errores), "error": True}

    logger.info(f"[BackfillHistorico] {nombre_ubicacion} {fecha} → {len(filas)} días de pronóstico insertados OK")
    return {"insertadas": len(filas), "razon": "ok"}


# ============================================================================
# ORQUESTADOR PRINCIPAL
# ============================================================================

def ejecutar_backfill(
    ubicaciones: dict,
    fechas: list,
    solo_condiciones: bool = False,
    solo_pronostico: bool = False,
) -> dict:
    """
    Ejecuta el backfill ERA5 completo para las ubicaciones y fechas dadas.

    Para cada (ubicacion, fecha):
    1. Extrae datos ERA5-Land via GEE (fecha → fecha+2, 72 horas)
    2. Inserta en condiciones_actuales (hora 15:00 local)
    3. Inserta en pronostico_dias (3 filas: día 0, +1, +2)

    Returns:
        Dict con resumen: exitosas, fallidas, omitidas
    """
    inicializar_gee()
    cliente_bq = bigquery.Client(project=GCP_PROJECT)

    exitosas = fallidas = omitidas = 0
    errores_lista = []

    total = len(ubicaciones) * len(fechas)
    logger.info(
        f"[BackfillHistorico] Iniciando: {len(ubicaciones)} ubicaciones × "
        f"{len(fechas)} fechas = {total} operaciones"
    )

    for nombre_ub, coords in ubicaciones.items():
        lat = coords["latitud"]
        lon = coords["longitud"]

        for fecha in fechas:
            logger.info(f"[BackfillHistorico] ── {nombre_ub} | {fecha}")

            # Necesitamos fecha+2 para el pronóstico de 3 días
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_fin_era5 = (fecha_dt + timedelta(days=2)).strftime("%Y-%m-%d")

            # Extraer ERA5 (1 llamada GEE para los 3 días)
            datos = obtener_datos_era5_gee(lat, lon, fecha, fecha_fin_era5)

            if "error" in datos:
                logger.error(f"[BackfillHistorico] {nombre_ub} {fecha} → error ERA5: {datos['error']}")
                fallidas += 1
                errores_lista.append({"ubicacion": nombre_ub, "fecha": fecha, "error": datos["error"]})
                continue

            # Insertar condiciones actuales
            if not solo_pronostico:
                res_c = insertar_condicion_actual(cliente_bq, nombre_ub, lat, lon, fecha, datos)
                if res_c.get("error"):
                    fallidas += 1
                    errores_lista.append({"ubicacion": nombre_ub, "fecha": fecha,
                                          "tabla": TABLA_CONDICIONES, "error": res_c["razon"]})
                    continue
                if res_c.get("razon") == "ya_existe":
                    omitidas += 1

            # Insertar pronóstico de días
            if not solo_condiciones:
                res_p = insertar_pronostico_dias(cliente_bq, nombre_ub, lat, lon, fecha, datos)
                if res_p.get("error"):
                    fallidas += 1
                    errores_lista.append({"ubicacion": nombre_ub, "fecha": fecha,
                                          "tabla": TABLA_PRONOSTICO, "error": res_p["razon"]})
                    continue
                if res_p.get("razon") == "ya_existe":
                    omitidas += 1
                else:
                    exitosas += 1
            else:
                if not res_c.get("error") and res_c.get("razon") != "ya_existe":
                    exitosas += 1

    resumen = {
        "total_operaciones": total,
        "exitosas": exitosas,
        "fallidas": fallidas,
        "omitidas_ya_existian": omitidas,
        "errores": errores_lista,
    }
    logger.info(
        f"[BackfillHistorico] Completado — "
        f"exitosas: {exitosas}, fallidas: {fallidas}, omitidas: {omitidas}"
    )
    return resumen


# ============================================================================
# CLI
# ============================================================================

def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill de datos climáticos históricos desde ERA5-Land (GEE). "
            "Inserta datos reales en condiciones_actuales y pronostico_dias de BigQuery."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Backfill completo La Parva inviernos 2024-2025
  GCP_PROJECT=climas-chileno python agentes/datos/backfill/backfill_clima_historico.py

  # Solo una ubicación y fecha específica
  GCP_PROJECT=climas-chileno python agentes/datos/backfill/backfill_clima_historico.py \\
      --ubicaciones "La Parva Sector Bajo" \\
      --fechas 2024-07-15
        """
    )
    parser.add_argument('--ubicaciones', nargs='+', default=list(UBICACIONES_LA_PARVA.keys()),
                        help='Nombres de ubicaciones. Default: las 3 zonas de La Parva.')
    parser.add_argument('--fechas', nargs='+', default=FECHAS_INVIERNO_DEFAULT,
                        help='Fechas YYYY-MM-DD a procesar. Default: inviernos 2024 y 2025.')
    parser.add_argument('--solo-condiciones', action='store_true',
                        help='Solo insertar condiciones_actuales')
    parser.add_argument('--solo-pronostico', action='store_true',
                        help='Solo insertar pronostico_dias')
    return parser.parse_args()


def main() -> int:
    args = parsear_argumentos()

    ubicaciones_validas = {
        n: UBICACIONES_LA_PARVA[n] for n in args.ubicaciones
        if n in UBICACIONES_LA_PARVA
    }
    fechas_validas = []
    for f in args.fechas:
        try:
            datetime.strptime(f, "%Y-%m-%d")
            fechas_validas.append(f)
        except ValueError:
            logger.warning(f"[BackfillHistorico] Fecha inválida ignorada: '{f}'")

    if not ubicaciones_validas or not fechas_validas:
        logger.error("[BackfillHistorico] Sin ubicaciones o fechas válidas.")
        return 1

    resumen = ejecutar_backfill(
        ubicaciones=ubicaciones_validas,
        fechas=fechas_validas,
        solo_condiciones=args.solo_condiciones,
        solo_pronostico=args.solo_pronostico,
    )

    print("\n=== Resumen del Backfill ERA5 ===")
    print(f"  Total operaciones : {resumen['total_operaciones']}")
    print(f"  Exitosas          : {resumen['exitosas']}")
    print(f"  Fallidas          : {resumen['fallidas']}")
    print(f"  Omitidas (ya existían): {resumen['omitidas_ya_existian']}")
    if resumen['errores']:
        print(f"\n  Errores ({len(resumen['errores'])}):")
        for err in resumen['errores']:
            print(f"    - {err.get('ubicacion')} {err.get('fecha')}: {err.get('error')}")

    return 0 if resumen['fallidas'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

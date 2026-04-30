"""
Backfill satelital multi-fuente desde Google Earth Engine.

Pobla la tabla `clima.imagenes_satelitales` para cualquier ubicación y fecha,
consolidando datos de 4 fuentes en orden de prioridad:

  1. Sentinel-1 SAR (COPERNICUS/S1_GRD)     — cloud-independent, 20m, global 2014-
  2. MODIS MOD10A1  (MODIS/061/MOD10A1)     — diario, global, 500m, 2000-
  3. ERA5-Land snow (ECMWF/ERA5_LAND/HOURLY) — SWE/snow_depth/cover, global, 1950-
  4. Sentinel-2 SR  (COPERNICUS/S2_SR_HARMONIZED) — 10m, cloud-limited, 2017-

Arquitectura preparada para ConsolidadorSatelital (Option C):
  - `fuente_principal` registra qué fuente dominó el registro
  - `sar_disponible`, `sentinel2_disponible` indican fuentes activas
  - Ventanas de búsqueda configurables por fuente (SAR ±3d, MODIS ±1d, S2 ±5d)
  - Idempotente: omite (ubicacion, fecha) que ya existen en BQ

Uso:
    python agentes/datos/backfill/backfill_satelital.py
    python agentes/datos/backfill/backfill_satelital.py \\
        --ubicaciones "Matterhorn Zermatt" "Interlaken" "St Moritz" \\
        --fechas 2023-12-01 2024-01-01 2024-02-01
    python agentes/datos/backfill/backfill_satelital.py --preset validacion_suiza
    python agentes/datos/backfill/backfill_satelital.py --preset laparva

Referencias:
    Nagler et al. (2016) — Sentinel-1 wet snow detection, Remote Sensing.
    Dietz et al. (2012) — MODIS NDSI validation, RSE.
    Muñoz Sabater (2021) — ERA5-Land, ESSD.
"""

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import ee
from google.cloud import bigquery

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GCP_PROJECT  = os.environ.get('GCP_PROJECT', 'climas-chileno')
DATASET      = 'clima'
TABLA        = 'imagenes_satelitales'
TABLA_BQ     = f'{GCP_PROJECT}.{DATASET}.{TABLA}'

# ── Catálogo de ubicaciones (región-agnóstico) ────────────────────────────────

UBICACIONES = {
    # ── Andes Chile ──────────────────────────────────────────────────────────
    "La Parva Sector Bajo":  {"lat": -33.363, "lon": -70.301, "region": "andes_chile", "elev_m": 2300},
    "La Parva Sector Medio": {"lat": -33.352, "lon": -70.290, "region": "andes_chile", "elev_m": 3000},
    "La Parva Sector Alto":  {"lat": -33.344, "lon": -70.280, "region": "andes_chile", "elev_m": 3600},
    "Valle Nevado":          {"lat": -33.357, "lon": -70.270, "region": "andes_chile", "elev_m": 3000},
    # ── Alpes Suizos ─────────────────────────────────────────────────────────
    "Matterhorn Zermatt":    {"lat": 45.977,  "lon":  7.659,  "region": "alpes_swiss", "elev_m": 2600},
    "Interlaken":            {"lat": 46.686,  "lon":  7.863,  "region": "alpes_swiss", "elev_m": 1200},
    "St Moritz":             {"lat": 46.491,  "lon":  9.836,  "region": "alpes_swiss", "elev_m": 1900},
}

# ── Presets de fechas por región ──────────────────────────────────────────────

PRESETS = {
    "laparva": {
        "ubicaciones": ["La Parva Sector Bajo", "La Parva Sector Medio", "La Parva Sector Alto"],
        "fechas": [
            "2024-06-15", "2024-07-01", "2024-07-15",
            "2024-08-01", "2024-08-15", "2024-09-01", "2024-09-15",
            "2025-06-15", "2025-07-01", "2025-07-15",
            "2025-08-01", "2025-08-15", "2025-09-01", "2025-09-15",
        ],
    },
    "validacion_suiza": {
        "ubicaciones": ["Matterhorn Zermatt", "Interlaken", "St Moritz"],
        "fechas": [
            "2023-12-01", "2023-12-15",
            "2024-01-01", "2024-01-15",
            "2024-02-01", "2024-02-15",
            "2024-03-01", "2024-03-15",
            "2024-04-01", "2024-04-15",
        ],
    },
}

# ── Parámetros GEE por fuente ─────────────────────────────────────────────────

BUFFER_GRADOS   = 0.10   # ~11 km, suficiente para capturar zona de análisis
VENTANA_SAR_D   = 3      # ±días para buscar imagen SAR más cercana
VENTANA_MODIS_D = 1      # ±días para MODIS (es diario, 1 día suele ser suficiente)
VENTANA_S2_D    = 5      # ±días para S2 (mayor por nubosidad frecuente)
MAX_NUBES_S2    = 30     # % máximo de nubosidad aceptable en S2
UMBRAL_NIEVE_MODIS = 40  # NDSI × 100 ≥ 40 → pixel de nieve (estándar Hall 2002)
UMBRAL_WET_SAR  = -15.0  # VV < -15 dB → nieve húmeda (Nagler et al. 2016)


# =============================================================================
# FUENTE 1: Sentinel-1 SAR
# =============================================================================

def extraer_sar(lat: float, lon: float, fecha: str) -> dict:
    """
    Extrae estadísticas Sentinel-1 GRD para una ubicación y fecha.

    Detecta nieve húmeda (wet snow) usando umbral VV < -15 dB y
    calcula backscatter medio VV/VH en la región.

    Args:
        lat, lon: coordenadas del punto de análisis
        fecha: "YYYY-MM-DD"

    Returns:
        dict con sar_disponible, sar_vv_medio_db, pct_nieve_humeda, etc.
        o {"sar_disponible": False} si no hay imagen disponible.
    """
    try:
        punto   = ee.Geometry.Point([lon, lat])
        region  = punto.buffer(BUFFER_GRADOS * 111000)  # buffer en metros aprox

        dt      = datetime.strptime(fecha, "%Y-%m-%d")
        inicio  = (dt - timedelta(days=VENTANA_SAR_D)).strftime("%Y-%m-%d")
        fin     = (dt + timedelta(days=VENTANA_SAR_D + 1)).strftime("%Y-%m-%d")

        col = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(region)
            .filterDate(inicio, fin)
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .sort("system:time_start")
        )

        size = col.size().getInfo()
        if size == 0:
            return {"sar_disponible": False, "razon": "sin imagen SAR en ventana ±3d"}

        # Imagen más cercana a la fecha objetivo
        img = _imagen_mas_cercana(col, fecha)
        vv  = img.select("VV")
        vh  = img.select("VH")

        stats_vv = vv.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
            geometry=region, scale=40, maxPixels=1e8
        ).getInfo()

        stats_vh = vh.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region, scale=40, maxPixels=1e8
        ).getInfo()

        vv_medio = stats_vv.get("VV_mean")
        vh_medio = stats_vh.get("VH_mean")

        if vv_medio is None:
            return {"sar_disponible": False, "razon": "stats SAR vacías"}

        # Wet snow: porcentaje de pixels con VV < umbral
        wet_mask  = vv.lt(UMBRAL_WET_SAR)
        pct_wet   = wet_mask.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=40, maxPixels=1e8
        ).getInfo().get("VV")

        # Dry snow proxy: VV entre -15 y -8 dB (C-band típico nieve seca)
        dry_mask  = vv.gte(UMBRAL_WET_SAR).And(vv.lt(-8.0))
        pct_dry   = dry_mask.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=40, maxPixels=1e8
        ).getInfo().get("VV")

        # Fecha real de la imagen
        ts_ms   = img.get("system:time_start").getInfo()
        fecha_r = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        orbita  = img.get("orbitProperties_pass").getInfo() or "UNKNOWN"

        return {
            "sar_disponible":     True,
            "sar_fecha":          fecha_r,
            "sar_orbita":         orbita,
            "sar_vv_medio_db":    round(float(vv_medio), 3),
            "sar_delta_vv_db":    round(float(stats_vv.get("VV_stdDev", 0)), 3),
            "sar_pct_nieve_humeda": round(float(pct_wet or 0) * 100, 2),
            "sar_pct_nieve_seca":  round(float(pct_dry or 0) * 100, 2),
        }
    except Exception as exc:
        logger.warning(f"SAR error ({lat},{lon},{fecha}): {exc}")
        return {"sar_disponible": False, "razon": str(exc)}


# =============================================================================
# FUENTE 2: MODIS MOD10A1 (Snow Cover Daily)
# =============================================================================

def extraer_modis(lat: float, lon: float, fecha: str) -> dict:
    """
    Extrae NDSI y cobertura de nieve de MODIS MOD10A1 y MYD10A1.

    MOD10A1: Terra (am), MYD10A1: Aqua (pm) → combinar mejora cobertura.
    NDSI_Snow_Cover: 0-100 (= NDSI × 100), 111=night, 200+=no-data.
    Pixel de nieve si NDSI_Snow_Cover >= 40 (Hall et al. 2002).

    Args:
        lat, lon: coordenadas
        fecha: "YYYY-MM-DD"

    Returns:
        dict con ndsi_medio, pct_cobertura_nieve, lst_dia_celsius, etc.
    """
    try:
        punto  = ee.Geometry.Point([lon, lat])
        region = punto.buffer(BUFFER_GRADOS * 111000)

        dt     = datetime.strptime(fecha, "%Y-%m-%d")
        inicio = (dt - timedelta(days=VENTANA_MODIS_D)).strftime("%Y-%m-%d")
        fin    = (dt + timedelta(days=VENTANA_MODIS_D + 1)).strftime("%Y-%m-%d")

        def _procesar_coleccion(coleccion_id):
            col = (
                ee.ImageCollection(coleccion_id)
                .filterBounds(region)
                .filterDate(inicio, fin)
                .select(["NDSI_Snow_Cover", "NDSI_Snow_Cover_Basic_QA"])
            )
            if col.size().getInfo() == 0:
                return None
            return _imagen_mas_cercana(col, fecha)

        img_terra = _procesar_coleccion("MODIS/061/MOD10A1")
        img_aqua  = _procesar_coleccion("MODIS/061/MYD10A1")

        # Usar Terra primero, Aqua como fallback
        img = img_terra or img_aqua
        if img is None:
            return {"modis_disponible": False}

        ndsi_band = img.select("NDSI_Snow_Cover")
        # Máscara: valores válidos 0-100
        validos = ndsi_band.gte(0).And(ndsi_band.lte(100))
        ndsi_val = ndsi_band.updateMask(validos)

        stats = ndsi_val.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=500, maxPixels=1e8
        ).getInfo()

        ndsi_raw = stats.get("NDSI_Snow_Cover")  # 0-100

        if ndsi_raw is None:
            return {"modis_disponible": False, "razon": "cobertura nubosa total"}

        # Porcentaje de pixels con nieve (NDSI_SC >= 40)
        snow_mask = ndsi_val.gte(UMBRAL_NIEVE_MODIS)
        pct_nieve = snow_mask.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=500, maxPixels=1e8
        ).getInfo().get("NDSI_Snow_Cover", 0)

        # NDSI normalizado: escala 0-100 → almacenar como 0-100 (schema BQ)
        # La normalización [-1,1] la hace el ConsultorBigQuery al leer
        ndsi_bq = round(float(ndsi_raw), 2)

        # LST desde MOD11A1 (si disponible en la misma ventana)
        lst_dia, lst_noche = _extraer_modis_lst(region, inicio, fin, fecha)

        # Nubosidad en la región
        qa_band = img.select("NDSI_Snow_Cover_Basic_QA")
        nubes = qa_band.eq(3)  # QA=3 → cloudy pixel
        pct_nubes = nubes.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=500, maxPixels=1e8
        ).getInfo().get("NDSI_Snow_Cover_Basic_QA", 0)

        return {
            "modis_disponible":    True,
            "ndsi_medio":          ndsi_bq,
            "ndsi_max":            ndsi_bq,
            "pct_cobertura_nieve": round(float(pct_nieve or 0) * 100, 2),
            "pct_nubes":           round(float(pct_nubes or 0) * 100, 2),
            "es_nublado":          (float(pct_nubes or 0) > 0.50),
            "lst_dia_celsius":     lst_dia,
            "lst_noche_celsius":   lst_noche,
            "ciclo_diurno_amplitud": (
                round(lst_dia - lst_noche, 2)
                if lst_dia is not None and lst_noche is not None
                else None
            ),
            "coleccion_gee":       "MODIS/061/MOD10A1",
            "resolucion_m":        500,
        }
    except Exception as exc:
        logger.warning(f"MODIS error ({lat},{lon},{fecha}): {exc}")
        return {"modis_disponible": False, "razon": str(exc)}


def _extraer_modis_lst(region, inicio, fin, fecha):
    """Extrae LST día/noche desde MOD11A1. Retorna (lst_dia, lst_noche) en °C."""
    try:
        col = (
            ee.ImageCollection("MODIS/061/MOD11A1")
            .filterBounds(region)
            .filterDate(inicio, fin)
            .select(["LST_Day_1km", "LST_Night_1km", "QC_Day"])
        )
        if col.size().getInfo() == 0:
            return None, None

        img = _imagen_mas_cercana(col, fecha)
        stats = img.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=1000, maxPixels=1e8
        ).getInfo()

        lst_d = stats.get("LST_Day_1km")
        lst_n = stats.get("LST_Night_1km")
        # Conversión: LST MOD11A1 en Kelvin × 0.02
        lst_dia    = round(float(lst_d) * 0.02 - 273.15, 2) if lst_d else None
        lst_noche  = round(float(lst_n) * 0.02 - 273.15, 2) if lst_n else None
        return lst_dia, lst_noche
    except Exception:
        return None, None


# =============================================================================
# FUENTE 3: ERA5-Land (campos de nieve)
# =============================================================================

def extraer_era5_nieve(lat: float, lon: float, fecha: str) -> dict:
    """
    Extrae campos de nieve ERA5-Land: snow_depth, SWE, snow_cover, snowfall.

    Promedia las 24 horas del día de análisis (UTC).

    Args:
        lat, lon: coordenadas
        fecha: "YYYY-MM-DD"

    Returns:
        dict con era5_snow_depth_m, era5_swe_m, era5_snow_cover, era5_snowfall_m
    """
    try:
        punto   = ee.Geometry.Point([lon, lat])
        dt      = datetime.strptime(fecha, "%Y-%m-%d")
        inicio  = dt.strftime("%Y-%m-%d")
        fin     = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

        col = (
            ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
            .filterBounds(punto)
            .filterDate(inicio, fin)
            .select([
                "snow_depth",
                "snowfall_hourly",
                "snow_cover",
                "snowfall",
            ])
        )

        if col.size().getInfo() == 0:
            return {"era5_snow_disponible": False}

        img_mean = col.mean()
        stats = img_mean.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=punto.buffer(9000), scale=9000,
            maxPixels=1e8
        ).getInfo()

        snow_depth   = stats.get("snow_depth")          # m
        snow_cover   = stats.get("snow_cover")          # fraction 0-1
        snowfall     = stats.get("snowfall_hourly")     # m/h
        snowfall_acc = stats.get("snowfall")            # m acumulado día

        # Snow Water Equivalent ≈ snow_depth × 0.3 (densidad nieve fresca típica)
        swe = round(float(snow_depth) * 0.3, 4) if snow_depth else None

        return {
            "era5_snow_disponible": True,
            "era5_snow_depth_m":    round(float(snow_depth), 4)  if snow_depth   else None,
            "era5_swe_m":           swe,
            "era5_snow_cover":      round(float(snow_cover) * 100, 2) if snow_cover else None,
            "era5_snowfall_m":      round(float(snowfall_acc), 5)    if snowfall_acc else None,
            "era5_temp_2m_celsius": None,  # ya cubierto por backfill_clima_historico
        }
    except Exception as exc:
        logger.warning(f"ERA5-nieve error ({lat},{lon},{fecha}): {exc}")
        return {"era5_snow_disponible": False, "razon": str(exc)}


# =============================================================================
# FUENTE 4: Sentinel-2 SR (cuando cloud-free)
# =============================================================================

def extraer_sentinel2(lat: float, lon: float, fecha: str) -> dict:
    """
    Extrae NDSI y cobertura de nieve Sentinel-2 cuando hay < MAX_NUBES_S2 %.

    NDSI_S2 = (Green - SWIR) / (Green + SWIR) usando B3 (560nm) y B11 (1610nm).
    Rango [-1,1] → almacenado × 100 en BQ (consistente con MODIS).

    Args:
        lat, lon: coordenadas
        fecha: "YYYY-MM-DD"

    Returns:
        dict con sentinel2_disponible, sentinel2_pct_nieve, etc.
    """
    try:
        punto   = ee.Geometry.Point([lon, lat])
        region  = punto.buffer(BUFFER_GRADOS * 111000)

        dt      = datetime.strptime(fecha, "%Y-%m-%d")
        inicio  = (dt - timedelta(days=VENTANA_S2_D)).strftime("%Y-%m-%d")
        fin     = (dt + timedelta(days=VENTANA_S2_D + 1)).strftime("%Y-%m-%d")

        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(region)
            .filterDate(inicio, fin)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_NUBES_S2))
            .sort("CLOUDY_PIXEL_PERCENTAGE")
        )

        if col.size().getInfo() == 0:
            return {"sentinel2_disponible": False, "razon": f"nubosidad >{MAX_NUBES_S2}% en ventana ±{VENTANA_S2_D}d"}

        img = col.first()  # menos nubosa del período

        # NDSI = (B3 − B11) / (B3 + B11), bandas reflectancia (0-10000)
        b3  = img.select("B3").toFloat()
        b11 = img.select("B11").toFloat()
        ndsi_img = b3.subtract(b11).divide(b3.add(b11)).rename("NDSI")

        stats = ndsi_img.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e8
        ).getInfo()

        ndsi_val = stats.get("NDSI")
        if ndsi_val is None:
            return {"sentinel2_disponible": False, "razon": "región sin píxeles válidos"}

        # Porcentaje de nieve (NDSI >= 0.40 estándar Dozier 1989)
        snow_mask = ndsi_img.gte(0.40)
        pct_s2 = snow_mask.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e8
        ).getInfo().get("NDSI", 0)

        # Fecha real imagen
        ts_ms   = img.get("system:time_start").getInfo()
        fecha_r = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        nubes   = img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()

        return {
            "sentinel2_disponible": True,
            "sentinel2_fecha":      fecha_r,
            "sentinel2_pct_nieve":  round(float(pct_s2 or 0) * 100, 2),
            # NDSI × 100 para consistencia con MODIS en BQ
            "ndsi_s2_x100":         round(float(ndsi_val) * 100, 2),
            "pct_nubes_s2":         round(float(nubes), 2) if nubes else None,
        }
    except Exception as exc:
        logger.warning(f"S2 error ({lat},{lon},{fecha}): {exc}")
        return {"sentinel2_disponible": False, "razon": str(exc)}


# =============================================================================
# CONSOLIDADOR SATELITAL
# =============================================================================

def consolidar(nombre: str, lat: float, lon: float, fecha: str,
               r_sar: dict, r_modis: dict, r_era5: dict, r_s2: dict) -> dict:
    """
    Fusiona resultados de 4 fuentes en un único registro BQ.

    Prioridad para campos principales:
      ndsi_medio:          S2 (10m) > MODIS (500m)
      pct_cobertura_nieve: S2 > MODIS
      lst_dia/noche:       MODIS MOD11A1
      nieve_humeda:        SAR
      fuente_principal:    SAR si disponible, else MODIS, else ERA5, else S2

    Returns:
        dict listo para insert en imagenes_satelitales
    """
    sar_ok   = r_sar.get("sar_disponible", False)
    modis_ok = r_modis.get("modis_disponible", False)
    era5_ok  = r_era5.get("era5_snow_disponible", False)
    s2_ok    = r_s2.get("sentinel2_disponible", False)

    # Fuente principal (para auditoría y ConsolidadorSatelital futuro)
    if sar_ok:
        fuente = "SAR+MODIS" if modis_ok else "SAR"
    elif s2_ok:
        fuente = "S2"
    elif modis_ok:
        fuente = "MODIS"
    elif era5_ok:
        fuente = "ERA5_SNOW"
    else:
        fuente = "DEGRADADO"

    # NDSI y cobertura: preferir S2 (10m) sobre MODIS (500m)
    ndsi_medio = (
        r_s2.get("ndsi_s2_x100") if s2_ok
        else r_modis.get("ndsi_medio")
    )
    pct_nieve = (
        r_s2.get("sentinel2_pct_nieve") if s2_ok
        else r_modis.get("pct_cobertura_nieve")
    )
    tiene_nieve = bool(pct_nieve and pct_nieve >= 10.0)

    # Snowline: estimación empírica si no hay dato directo
    snowline = None
    info     = UBICACIONES.get(nombre, {})
    elev_ref = info.get("elev_m", 2000)
    if pct_nieve is not None:
        if pct_nieve > 80:
            snowline = max(elev_ref - 500, 1500)
        elif pct_nieve > 40:
            snowline = elev_ref
        elif pct_nieve > 10:
            snowline = elev_ref + 200
        else:
            snowline = elev_ref + 600

    ahora = datetime.now(timezone.utc).isoformat()

    return {
        # Identidad
        "nombre_ubicacion":      nombre,
        "latitud":               lat,
        "longitud":              lon,
        "region":                info.get("region", "desconocida"),
        "fecha_captura":         fecha,
        "tipo_captura":          "manana",
        "timestamp_imagen":      f"{fecha}T10:00:00Z",
        "timestamp_descarga":    ahora,
        "antiguedad_horas":      0.0,

        # Metadatos de fuente
        "fuente_principal":      fuente,
        "coleccion_gee":         "MULTI: S1/MOD10A1/ERA5/S2",
        "resolucion_m":          20 if sar_ok else (10 if s2_ok else 500),

        # Nubosidad (MODIS)
        "pct_nubes":             r_modis.get("pct_nubes"),
        "es_nublado":            r_modis.get("es_nublado"),
        "tiene_nieve":           tiene_nieve,

        # Snow indices (S2 > MODIS)
        "ndsi_medio":            ndsi_medio,
        "ndsi_max":              ndsi_medio,
        "pct_cobertura_nieve":   pct_nieve,
        "albedo_nieve_medio":    None,

        # Snowline
        "snowline_elevacion_m":  snowline,
        "snowline_mediana_m":    snowline,
        "snowline_cambio_24h_m": None,
        "snowline_cambio_72h_m": None,

        # Cambios nieve
        "delta_pct_nieve_24h":   None,
        "delta_pct_nieve_72h":   None,
        "tipo_cambio_nieve":     "sin_datos",
        "tasa_cambio_nieve_dia": None,

        # LST (MODIS MOD11A1)
        "lst_dia_celsius":       r_modis.get("lst_dia_celsius"),
        "lst_noche_celsius":     r_modis.get("lst_noche_celsius"),
        "lst_min_celsius":       r_modis.get("lst_noche_celsius"),
        "ciclo_diurno_amplitud": r_modis.get("ciclo_diurno_amplitud"),

        # Índices de fusión
        "ami_3d":                None,
        "ami_7d":                None,

        # ERA5 snow
        "era5_snow_depth_m":     r_era5.get("era5_snow_depth_m"),
        "era5_swe_m":            r_era5.get("era5_swe_m"),
        "era5_snow_cover":       r_era5.get("era5_snow_cover"),
        "era5_temp_2m_celsius":  r_era5.get("era5_temp_2m_celsius"),
        "era5_snowfall_m":       r_era5.get("era5_snowfall_m"),
        "era5_swe_anomalia":     None,

        # Sentinel-2
        "sentinel2_disponible":  s2_ok,
        "sentinel2_fecha":       r_s2.get("sentinel2_fecha"),
        "sentinel2_pct_nieve":   r_s2.get("sentinel2_pct_nieve"),

        # SAR Sentinel-1
        "sar_disponible":        sar_ok,
        "sar_fecha":             r_sar.get("sar_fecha"),
        "sar_orbita":            r_sar.get("sar_orbita"),
        "sar_pct_nieve_humeda":  r_sar.get("sar_pct_nieve_humeda"),
        "sar_pct_nieve_seca":    r_sar.get("sar_pct_nieve_seca"),
        "sar_vv_medio_db":       r_sar.get("sar_vv_medio_db"),
        "sar_delta_vv_db":       r_sar.get("sar_delta_vv_db"),

        # Viento altura (se completa vía backfill_clima_historico)
        "viento_altura_vel_ms":   None,
        "viento_altura_vel_kmh":  None,
        "viento_altura_dir_grados": None,
        "viento_max_24h_ms":      None,
        "transporte_eolico_activo": False,
        "aspecto_carga_eolica":   None,

        # URIs (sin GeoTIFF en backfill básico)
        "uri_geotiff_visual": None,
        "uri_geotiff_ndsi":   None,
        "uri_geotiff_lst":    None,
        "uri_geotiff_era5":   None,
        "uri_geotiff_sar":    None,
        "uri_preview_visual": None,
        "uri_preview_ndsi":   None,
        "uri_preview_lst":    None,
        "uri_preview_sar":    None,
        "uri_thumbnail_visual": None,
        "uri_thumbnail_ndsi":   None,

        "version_metodologia": "backfill_satelital_v1",
    }


# =============================================================================
# BIGQUERY — helpers
# =============================================================================

def obtener_existentes(cliente: bigquery.Client, ubicaciones: list, fechas: list) -> set:
    """Devuelve set de (nombre_ubicacion, fecha_captura) ya en BQ."""
    if not ubicaciones or not fechas:
        return set()
    u_list = ", ".join(f"'{u}'" for u in ubicaciones)
    f_list = ", ".join(f"'{f}'" for f in fechas)
    sql = f"""
        SELECT nombre_ubicacion, CAST(fecha_captura AS STRING) AS fecha
        FROM `{TABLA_BQ}`
        WHERE nombre_ubicacion IN ({u_list})
          AND CAST(fecha_captura AS STRING) IN ({f_list})
    """
    try:
        filas = list(cliente.query(sql).result())
        return {(r.nombre_ubicacion, r.fecha) for r in filas}
    except Exception as e:
        logger.warning(f"No se pudo consultar existentes: {e}")
        return set()


def insertar_fila(cliente: bigquery.Client, fila: dict) -> bool:
    """Inserta una fila en imagenes_satelitales vía streaming insert."""
    errores = cliente.insert_rows_json(TABLA_BQ, [fila])
    if errores:
        logger.error(f"Error BQ insert: {errores}")
        return False
    return True


# =============================================================================
# HELPERS GEE
# =============================================================================

def _imagen_mas_cercana(col: ee.ImageCollection, fecha_objetivo: str) -> ee.Image:
    """Retorna la imagen cuya timestamp es más cercana a fecha_objetivo."""
    dt = datetime.strptime(fecha_objetivo, "%Y-%m-%d")
    ts_obj = dt.timestamp() * 1000  # ms epoch

    col_con_dist = col.map(
        lambda img: img.set(
            "dist_t",
            ee.Number(img.get("system:time_start")).subtract(ts_obj).abs()
        )
    )
    return col_con_dist.sort("dist_t").first()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Backfill satelital multi-fuente (SAR + MODIS + ERA5 + S2)"
    )
    parser.add_argument("--preset", choices=list(PRESETS.keys()),
                        help="Preset predefinido de ubicaciones y fechas")
    parser.add_argument("--ubicaciones", nargs="+",
                        help="Nombres exactos de ubicaciones (deben estar en UBICACIONES)")
    parser.add_argument("--fechas", nargs="+",
                        help="Fechas YYYY-MM-DD a procesar")
    parser.add_argument("--fuentes", nargs="+",
                        choices=["sar", "modis", "era5", "s2"],
                        default=["sar", "modis", "era5", "s2"],
                        help="Fuentes a consultar (default: todas)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostrar plan sin ejecutar ni insertar en BQ")
    args = parser.parse_args()

    # Resolver ubicaciones y fechas
    if args.preset:
        p = PRESETS[args.preset]
        ubicaciones_sel = p["ubicaciones"]
        fechas_sel      = p["fechas"]
    else:
        ubicaciones_sel = args.ubicaciones or list(UBICACIONES.keys())
        fechas_sel      = args.fechas or []

    if not fechas_sel:
        parser.error("Especifica --fechas o --preset")

    # Validar ubicaciones
    invalidas = [u for u in ubicaciones_sel if u not in UBICACIONES]
    if invalidas:
        parser.error(f"Ubicaciones desconocidas: {invalidas}\nDisponibles: {list(UBICACIONES.keys())}")

    total = len(ubicaciones_sel) * len(fechas_sel)
    logger.info(f"[BackfillSatelital] Plan: {len(ubicaciones_sel)} ubicaciones × {len(fechas_sel)} fechas = {total} operaciones")
    logger.info(f"[BackfillSatelital] Fuentes: {args.fuentes}")

    if args.dry_run:
        print(f"\nDRY RUN — {total} operaciones:")
        for u in ubicaciones_sel:
            for f in fechas_sel:
                info = UBICACIONES[u]
                print(f"  {u} | {f} | {info['region']} | lat={info['lat']},lon={info['lon']}")
        return

    # Inicializar GEE y BQ
    logger.info("[BackfillSatelital] Inicializando Earth Engine...")
    ee.Initialize(project=GCP_PROJECT)
    logger.info("[BackfillSatelital] GEE inicializado.")

    cliente = bigquery.Client(project=GCP_PROJECT)
    existentes = obtener_existentes(cliente, ubicaciones_sel, fechas_sel)
    logger.info(f"[BackfillSatelital] Ya en BQ: {len(existentes)} registros (serán omitidos)")

    exitosas = 0
    fallidas  = 0
    omitidas  = 0

    for ubicacion in ubicaciones_sel:
        info = UBICACIONES[ubicacion]
        lat, lon = info["lat"], info["lon"]

        for fecha in fechas_sel:
            clave = (ubicacion, fecha)
            if clave in existentes:
                logger.info(f"[BackfillSatelital] ── OMITIR {ubicacion} | {fecha} (ya existe)")
                omitidas += 1
                continue

            logger.info(f"[BackfillSatelital] ── {ubicacion} | {fecha}")

            # Extraer fuentes en paralelo conceptual (GEE es lazy, cada call es independiente)
            r_sar   = extraer_sar(lat, lon, fecha)    if "sar"   in args.fuentes else {}
            r_modis = extraer_modis(lat, lon, fecha)  if "modis" in args.fuentes else {}
            r_era5  = extraer_era5_nieve(lat, lon, fecha) if "era5" in args.fuentes else {}
            r_s2    = extraer_sentinel2(lat, lon, fecha)  if "s2"   in args.fuentes else {}

            sar_ok   = r_sar.get("sar_disponible", False)
            modis_ok = r_modis.get("modis_disponible", False)
            era5_ok  = r_era5.get("era5_snow_disponible", False)
            s2_ok    = r_s2.get("sentinel2_disponible", False)

            logger.info(
                f"[BackfillSatelital]   SAR={sar_ok} "
                f"MODIS={modis_ok} ERA5={era5_ok} S2={s2_ok}"
            )

            if not any([sar_ok, modis_ok, era5_ok, s2_ok]):
                logger.warning(f"[BackfillSatelital] ✗ Sin datos de ninguna fuente: {ubicacion} {fecha}")
                fallidas += 1
                continue

            fila = consolidar(ubicacion, lat, lon, fecha, r_sar, r_modis, r_era5, r_s2)

            if insertar_fila(cliente, fila):
                logger.info(
                    f"[BackfillSatelital] ✓ {ubicacion} {fecha} — "
                    f"fuente={fila['fuente_principal']} "
                    f"nieve={fila.get('pct_cobertura_nieve')}% "
                    f"SAR_VV={fila.get('sar_vv_medio_db')} dB"
                )
                exitosas += 1
            else:
                fallidas += 1

            # Pausa breve para evitar rate limiting GEE
            time.sleep(1)

    logger.info(
        f"\n[BackfillSatelital] Fin — "
        f"Exitosas: {exitosas} | Fallidas: {fallidas} | Omitidas: {omitidas} | "
        f"Total: {total}"
    )
    if fallidas > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

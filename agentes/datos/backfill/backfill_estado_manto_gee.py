"""
Backfill estado del manto nival desde Google Earth Engine.

Pobla la tabla `clima.estado_manto_gee` con:
  1. MODIS LST (MOD11A1 Terra + MYD11A1 Aqua) — temperatura superficie, 1km, diario
  2. ERA5-Land temperatura del suelo (L1 0-7cm, L2 7-28cm) — proxy manto basal

Estas variables complementan las de `imagenes_satelitales` con señales positivas
de estabilidad del manto: LST < -5°C sostenido → manto frío, metamorfismo lento.

Uso:
    python agentes/datos/backfill/backfill_estado_manto_gee.py --preset laparva
    python agentes/datos/backfill/backfill_estado_manto_gee.py \\
        --ubicaciones "La Parva Sector Bajo" --fechas 2025-07-01 2025-08-01
    python agentes/datos/backfill/backfill_estado_manto_gee.py --dry-run --preset validacion_suiza

Referencias:
    Wan et al. (2004) — MODIS LST validation, JGR Atmospheres.
    Muñoz Sabater (2021) — ERA5-Land technical note, ESSD.
"""

import argparse
import logging
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

GCP_PROJECT = os.environ.get('GCP_PROJECT', 'climas-chileno')
DATASET     = 'clima'
TABLA       = 'estado_manto_gee'
TABLA_BQ    = f'{GCP_PROJECT}.{DATASET}.{TABLA}'

# ── Catálogo de ubicaciones ───────────────────────────────────────────────────

UBICACIONES = {
    "La Parva Sector Bajo":  {"lat": -33.363, "lon": -70.301, "region": "andes_chile", "elev_m": 2300},
    "La Parva Sector Medio": {"lat": -33.352, "lon": -70.290, "region": "andes_chile", "elev_m": 3000},
    "La Parva Sector Alto":  {"lat": -33.344, "lon": -70.280, "region": "andes_chile", "elev_m": 3600},
    "Valle Nevado":          {"lat": -33.357, "lon": -70.270, "region": "andes_chile", "elev_m": 3000},
    "Matterhorn Zermatt":    {"lat": 45.977,  "lon":  7.659,  "region": "alpes_swiss", "elev_m": 2600},
    "Interlaken":            {"lat": 46.686,  "lon":  7.863,  "region": "alpes_swiss", "elev_m": 1200},
    "St Moritz":             {"lat": 46.491,  "lon":  9.836,  "region": "alpes_swiss", "elev_m": 1900},
}

PRESETS = {
    "laparva": {
        "ubicaciones": [
            "La Parva Sector Bajo", "La Parva Sector Medio", "La Parva Sector Alto",
        ],
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

BUFFER_GRADOS = 0.10   # ~11 km, captura zona de análisis
VENTANA_DIAS  = 1       # ±días para buscar imagen MODIS más cercana


# =============================================================================
# FUENTE 1: MODIS LST (MOD11A1 Terra + MYD11A1 Aqua)
# =============================================================================

def extraer_modis_lst(lat: float, lon: float, fecha: str) -> dict:
    """
    Extrae temperatura de superficie MODIS LST para una ubicación y fecha.

    MOD11A1 (Terra, ~10:30 local) y MYD11A1 (Aqua, ~13:30 local).
    Banda LST_Day_1km: escala Kelvin × 0.02 → convertir a °C (Wan et al. 2004).

    Args:
        lat, lon: coordenadas del punto de análisis
        fecha: "YYYY-MM-DD"

    Returns:
        dict con lst_celsius, cobertura_nubosa_pct, fuente_lst
        o {"modis_lst_disponible": False} si sin imagen.
    """
    try:
        punto  = ee.Geometry.Point([lon, lat])
        region = punto.buffer(BUFFER_GRADOS * 111000)

        dt     = datetime.strptime(fecha, "%Y-%m-%d")
        inicio = (dt - timedelta(days=VENTANA_DIAS)).strftime("%Y-%m-%d")
        fin    = (dt + timedelta(days=VENTANA_DIAS + 1)).strftime("%Y-%m-%d")

        def _lst_de_coleccion(col_id):
            col = (
                ee.ImageCollection(col_id)
                .filterBounds(region)
                .filterDate(inicio, fin)
                .select(["LST_Day_1km", "QC_Day"])
            )
            if col.size().getInfo() == 0:
                return None, None
            img   = _imagen_mas_cercana(col, fecha)
            stats = img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=1000,
                maxPixels=1e8,
            ).getInfo()
            lst_raw = stats.get("LST_Day_1km")
            qc_raw  = stats.get("QC_Day")
            lst_c   = round(float(lst_raw) * 0.02 - 273.15, 2) if lst_raw else None
            # QC bits 0-1: 00 = mejor calidad, 01 = buena, 10-11 = nuboso
            pct_nubes = None
            if qc_raw is not None:
                bits_qc = int(qc_raw) & 0b11
                pct_nubes = 100.0 if bits_qc >= 2 else 0.0
            return lst_c, pct_nubes

        lst_terra, nubes_terra = _lst_de_coleccion("MODIS/061/MOD11A1")
        lst_aqua,  nubes_aqua  = _lst_de_coleccion("MODIS/061/MYD11A1")

        if lst_terra is not None:
            return {
                "modis_lst_disponible": True,
                "lst_celsius":          lst_terra,
                "cobertura_nubosa_pct": nubes_terra,
                "fuente_lst":           "MOD11A1",
            }
        if lst_aqua is not None:
            return {
                "modis_lst_disponible": True,
                "lst_celsius":          lst_aqua,
                "cobertura_nubosa_pct": nubes_aqua,
                "fuente_lst":           "MYD11A1",
            }
        return {"modis_lst_disponible": False, "razon": "sin imagen LST en ventana ±1d"}

    except Exception as exc:
        logger.warning(f"MODIS LST error ({lat},{lon},{fecha}): {exc}")
        return {"modis_lst_disponible": False, "razon": str(exc)}


# =============================================================================
# FUENTE 2: ERA5-Land temperatura del suelo
# =============================================================================

def extraer_era5_suelo(lat: float, lon: float, fecha: str) -> dict:
    """
    Extrae temperatura del suelo ERA5-Land capas L1 (0-7cm) y L2 (7-28cm).

    Gradiente térmico L1-L2 negativo sostenido indica que la superficie
    es más fría que la base del manto → metamorfismo cinético activo
    (factor de riesgo para capas frágiles persistentes).

    Args:
        lat, lon: coordenadas
        fecha: "YYYY-MM-DD"

    Returns:
        dict con temp_suelo_l1_celsius, temp_suelo_l2_celsius, gradiente_termico
    """
    try:
        punto  = ee.Geometry.Point([lon, lat])
        dt     = datetime.strptime(fecha, "%Y-%m-%d")
        inicio = dt.strftime("%Y-%m-%d")
        fin    = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

        col = (
            ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
            .filterBounds(punto)
            .filterDate(inicio, fin)
            .select(["soil_temperature_level_1", "soil_temperature_level_2"])
        )

        if col.size().getInfo() == 0:
            return {"era5_suelo_disponible": False, "razon": "sin datos ERA5 para esta fecha"}

        img_mean = col.mean()
        stats    = img_mean.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=punto.buffer(9000),
            scale=9000,
            maxPixels=1e8,
        ).getInfo()

        t_l1_k = stats.get("soil_temperature_level_1")
        t_l2_k = stats.get("soil_temperature_level_2")

        t_l1 = round(float(t_l1_k) - 273.15, 2) if t_l1_k else None
        t_l2 = round(float(t_l2_k) - 273.15, 2) if t_l2_k else None
        grad = round(t_l1 - t_l2, 3) if (t_l1 is not None and t_l2 is not None) else None

        return {
            "era5_suelo_disponible":  True,
            "temp_suelo_l1_celsius":  t_l1,
            "temp_suelo_l2_celsius":  t_l2,
            "gradiente_termico":      grad,
        }

    except Exception as exc:
        logger.warning(f"ERA5 suelo error ({lat},{lon},{fecha}): {exc}")
        return {"era5_suelo_disponible": False, "razon": str(exc)}


# =============================================================================
# BIGQUERY — helpers
# =============================================================================

def obtener_existentes(cliente: bigquery.Client, ubicaciones: list, fechas: list) -> set:
    """Devuelve set de (nombre_ubicacion, fecha) ya en BQ."""
    if not ubicaciones or not fechas:
        return set()
    u_list = ", ".join(f"'{u}'" for u in ubicaciones)
    f_list = ", ".join(f"'{f}'" for f in fechas)
    sql = f"""
        SELECT nombre_ubicacion, CAST(fecha AS STRING) AS fecha
        FROM `{TABLA_BQ}`
        WHERE nombre_ubicacion IN ({u_list})
          AND CAST(fecha AS STRING) IN ({f_list})
    """
    try:
        filas = list(cliente.query(sql).result())
        return {(r.nombre_ubicacion, r.fecha) for r in filas}
    except Exception as e:
        logger.warning(f"No se pudo consultar existentes: {e}")
        return set()


def insertar_fila(cliente: bigquery.Client, fila: dict) -> bool:
    """Inserta una fila en estado_manto_gee vía streaming insert."""
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
    dt     = datetime.strptime(fecha_objetivo, "%Y-%m-%d")
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
        description="Backfill estado del manto nival (MODIS LST + ERA5-Land suelo)"
    )
    parser.add_argument("--preset", choices=list(PRESETS.keys()),
                        help="Preset predefinido de ubicaciones y fechas")
    parser.add_argument("--ubicaciones", nargs="+",
                        help="Nombres exactos de ubicaciones")
    parser.add_argument("--fechas", nargs="+",
                        help="Fechas YYYY-MM-DD a procesar")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostrar plan sin ejecutar ni insertar en BQ")
    args = parser.parse_args()

    if args.preset:
        p               = PRESETS[args.preset]
        ubicaciones_sel = p["ubicaciones"]
        fechas_sel      = p["fechas"]
    else:
        ubicaciones_sel = args.ubicaciones or list(UBICACIONES.keys())
        fechas_sel      = args.fechas or []

    if not fechas_sel:
        parser.error("Especifica --fechas o --preset")

    invalidas = [u for u in ubicaciones_sel if u not in UBICACIONES]
    if invalidas:
        parser.error(
            f"Ubicaciones desconocidas: {invalidas}\nDisponibles: {list(UBICACIONES.keys())}"
        )

    total = len(ubicaciones_sel) * len(fechas_sel)
    logger.info(
        f"[BackfillEstadoManto] Plan: {len(ubicaciones_sel)} ubicaciones × "
        f"{len(fechas_sel)} fechas = {total} operaciones"
    )

    if args.dry_run:
        print(f"\nDRY RUN — {total} operaciones:")
        for u in ubicaciones_sel:
            for f in fechas_sel:
                info = UBICACIONES[u]
                print(f"  {u} | {f} | {info['region']} | lat={info['lat']},lon={info['lon']}")
        return

    logger.info("[BackfillEstadoManto] Inicializando Earth Engine...")
    ee.Initialize(project=GCP_PROJECT)
    logger.info("[BackfillEstadoManto] GEE inicializado.")

    cliente    = bigquery.Client(project=GCP_PROJECT)
    existentes = obtener_existentes(cliente, ubicaciones_sel, fechas_sel)
    logger.info(f"[BackfillEstadoManto] Ya en BQ: {len(existentes)} registros (serán omitidos)")

    exitosas = fallidas = omitidas = 0

    for ubicacion in ubicaciones_sel:
        info     = UBICACIONES[ubicacion]
        lat, lon = info["lat"], info["lon"]

        for fecha in fechas_sel:
            clave = (ubicacion, fecha)
            if clave in existentes:
                logger.info(f"[BackfillEstadoManto] ── OMITIR {ubicacion} | {fecha} (ya existe)")
                omitidas += 1
                continue

            logger.info(f"[BackfillEstadoManto] ── {ubicacion} | {fecha}")

            r_lst   = extraer_modis_lst(lat, lon, fecha)
            r_suelo = extraer_era5_suelo(lat, lon, fecha)

            lst_ok   = r_lst.get("modis_lst_disponible", False)
            suelo_ok = r_suelo.get("era5_suelo_disponible", False)

            logger.info(f"[BackfillEstadoManto]   LST_MODIS={lst_ok} ERA5_SUELO={suelo_ok}")

            if not any([lst_ok, suelo_ok]):
                logger.warning(f"[BackfillEstadoManto] ✗ Sin datos de ninguna fuente: {ubicacion} {fecha}")
                fallidas += 1
                continue

            fila = {
                "nombre_ubicacion":              ubicacion,
                "fecha":                         fecha,
                "lst_celsius":                   r_lst.get("lst_celsius"),
                # lst_positivo_dias_consecutivos: calculado en ConsultorBigQuery al leer
                "lst_positivo_dias_consecutivos": None,
                # sar_vv_db y sar_delta_baseline: vienen de imagenes_satelitales
                "sar_vv_db":                     None,
                "sar_delta_baseline":             None,
                "temp_suelo_l1_celsius":          r_suelo.get("temp_suelo_l1_celsius"),
                "temp_suelo_l2_celsius":          r_suelo.get("temp_suelo_l2_celsius"),
                "gradiente_termico":              r_suelo.get("gradiente_termico"),
                "cobertura_nubosa_pct":           r_lst.get("cobertura_nubosa_pct"),
                "fuente_lst":                     r_lst.get("fuente_lst"),
                "ingested_at":                    datetime.now(timezone.utc).isoformat(),
            }

            if insertar_fila(cliente, fila):
                logger.info(
                    f"[BackfillEstadoManto] ✓ {ubicacion} {fecha} — "
                    f"LST={fila.get('lst_celsius')}°C "
                    f"T_suelo_L1={fila.get('temp_suelo_l1_celsius')}°C "
                    f"grad={fila.get('gradiente_termico')} "
                    f"fuente={fila.get('fuente_lst')}"
                )
                exitosas += 1
            else:
                fallidas += 1

            time.sleep(0.5)

    logger.info(
        f"\n[BackfillEstadoManto] Fin — "
        f"Exitosas: {exitosas} | Fallidas: {fallidas} | Omitidas: {omitidas} | Total: {total}"
    )
    if fallidas > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

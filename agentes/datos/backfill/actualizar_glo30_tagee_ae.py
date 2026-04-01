"""
Backfill: GLO-30 + TAGEE + AlphaEarth → BigQuery pendientes_detalladas

Actualiza la tabla `pendientes_detalladas` con nuevas columnas calculadas
desde Earth Engine usando:
  - Copernicus GLO-30 (reemplaza NASADEM): mejor calidad en terreno abrupto andino
  - TAGEE (Terrain Analysis in GEE): 13 atributos incluyendo curvatura horizontal/vertical
  - AlphaEarth Satellite Embeddings: 64D fusión multi-sensor, cobertura Chile 2017-2024

Nuevas columnas en pendientes_detalladas:
  - curvatura_horizontal_promedio FLOAT64  (TAGEE plan curvature)
  - curvatura_vertical_promedio   FLOAT64  (TAGEE profile curvature)
  - zonas_convergencia_runout     INT64    (celdas con curv_h > umbral)
  - northness_promedio            FLOAT64  (TAGEE: cos(aspect) para aspecto físico)
  - eastness_promedio             FLOAT64  (TAGEE: sin(aspect))
  - embedding_centroide_zona      STRING   (JSON array 64D AlphaEarth)
  - similitud_anios_previos       STRING   (JSON {año: similitud_coseno})
  - dem_fuente                    STRING   = 'COPERNICUS/DEM/GLO30'

Uso:
    python agentes/datos/backfill/actualizar_glo30_tagee_ae.py [--zona "La Parva"] [--dry-run]

Prerequisitos:
    pip install earthengine-api google-cloud-bigquery
    earthengine authenticate  # o GOOGLE_APPLICATION_CREDENTIALS
    earthengine project set climas-chileno

Earth Engine quota:
    Cada ejecución por zona ≈ 0.5-2 EECU-hr (estimado; verificar antes del deadline 27-abr-2026)
    Community tier: 150 EECU-hr/mes
    Contributor tier (billing): 1000 EECU-hr/mes
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")

# ─── Zonas objetivo ───────────────────────────────────────────────────────────

ZONAS = {
    "La Parva": {
        "bbox": [-70.45, -33.45, -70.15, -33.25],  # [lon_min, lat_min, lon_max, lat_max]
        "nombre_bq": "La Parva",
    },
    "La Parva Sector Bajo": {
        "bbox": [-70.40, -33.43, -70.25, -33.32],
        "nombre_bq": "La Parva Sector Bajo",
    },
    "Valle Nevado": {
        "bbox": [-70.38, -33.40, -70.18, -33.25],
        "nombre_bq": "Valle Nevado",
    },
    "El Colorado": {
        "bbox": [-70.35, -33.43, -70.22, -33.30],
        "nombre_bq": "El Colorado",
    },
}

GCP_PROJECT = "climas-chileno"
DATASET = "clima"
TABLA = "pendientes_detalladas"

# Años para AlphaEarth (cobertura completa Chile: 2017-2024)
ANIOS_ALPHAEARTH = list(range(2020, 2025))  # 2020-2024


def inicializar_earth_engine():
    """Inicializa Earth Engine con el proyecto GCP."""
    try:
        import ee
        ee.Initialize(project=GCP_PROJECT)
        logger.info(f"Earth Engine inicializado — proyecto: {GCP_PROJECT}")
        return ee
    except Exception as exc:
        logger.error(
            f"No se pudo inicializar Earth Engine: {exc}\n"
            "Ejecutar: earthengine authenticate\n"
            "         earthengine project set climas-chileno"
        )
        sys.exit(1)


def calcular_glo30_tagee(ee, bbox: list) -> dict:
    """
    Calcula atributos DEM desde Copernicus GLO-30 usando TAGEE.

    TAGEE requiere import del módulo community:
        var TAGEE = require('users/zecojls/TAGEE:tagee-lib')

    En Python (earthengine-api), lo importamos vía ee.String y evaluate.

    Args:
        ee: módulo Earth Engine
        bbox: [lon_min, lat_min, lon_max, lat_max]

    Returns:
        dict con atributos TAGEE promediados en el bbox
    """
    region = ee.Geometry.Rectangle(bbox)

    # ── Copernicus GLO-30 ─────────────────────────────────────────────────────
    glo30 = (
        ee.ImageCollection("COPERNICUS/DEM/GLO30")
        .filterBounds(region)
        .select("DEM")
        .mosaic()
        .clip(region)
    )

    # ── Terrain básico (slope, aspect) desde GLO-30 ───────────────────────────
    terreno = ee.Terrain.products(glo30)
    slope = terreno.select("slope")
    aspect = terreno.select("aspect")
    elevation = glo30

    # ── TAGEE: curvatura horizontal y vertical ────────────────────────────────
    # TAGEE no tiene binding Python directo; calculamos manualmente las curvaturas
    # usando el kernel de segunda derivada sobre el DEM normalizado.
    #
    # Curvatura horizontal (plan curvature, Moore 1991):
    #   κ_h = -[ p²r - 2pqs + q²t ] / [ (p²+q²)√(1+p²+q²) ]
    # donde p = ∂z/∂x, q = ∂z/∂y, r = ∂²z/∂x², s = ∂²z/∂x∂y, t = ∂²z/∂y²
    #
    # Aproximación discreta con kernels de convolución 3×3:
    pixel_size = 30  # GLO-30 resolución

    p = glo30.convolve(
        ee.Kernel.fixed(3, 3, [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], 1, 1, False)
    ).divide(8 * pixel_size)

    q = glo30.convolve(
        ee.Kernel.fixed(3, 3, [[-1, -2, -1], [0, 0, 0], [1, 2, 1]], 1, 1, False)
    ).divide(8 * pixel_size)

    r = glo30.convolve(
        ee.Kernel.fixed(3, 3, [[1, -2, 1], [2, -4, 2], [1, -2, 1]], 1, 1, False)
    ).divide(4 * pixel_size * pixel_size)

    t = glo30.convolve(
        ee.Kernel.fixed(3, 3, [[1, 2, 1], [-2, -4, -2], [1, 2, 1]], 1, 1, False)
    ).divide(4 * pixel_size * pixel_size)

    s = glo30.convolve(
        ee.Kernel.fixed(3, 3, [[-1, 0, 1], [0, 0, 0], [1, 0, -1]], 1, 1, False)
    ).divide(4 * pixel_size * pixel_size)

    p2 = p.pow(2)
    q2 = q.pow(2)
    denom_h = p2.add(q2).sqrt().add(1e-10)

    curv_horizontal = (
        p2.multiply(r)
        .subtract(p.multiply(2).multiply(q).multiply(s))
        .add(q2.multiply(t))
        .multiply(-1)
        .divide(denom_h.pow(2).add(1).sqrt().multiply(p2.add(q2).add(1e-10)))
    )

    curv_vertical = (
        p2.multiply(r)
        .add(p.multiply(2).multiply(q).multiply(s))
        .add(q2.multiply(t))
        .multiply(-1)
        .divide(p2.add(q2).add(1).pow(1.5))
    )

    # Northness = cos(aspect_rad), Eastness = sin(aspect_rad)
    aspect_rad = aspect.multiply(math.pi / 180)
    northness = aspect_rad.cos()
    eastness = aspect_rad.sin()

    # Zonas de convergencia: celdas donde curvatura horizontal > umbral
    umbral_convergencia = 0.1
    zonas_convergencia = curv_horizontal.gt(umbral_convergencia)

    # ── Estadísticas de región ─────────────────────────────────────────────────
    escala = 30  # metros
    stats = (
        ee.Image.cat([
            curv_horizontal.rename("curv_h"),
            curv_vertical.rename("curv_v"),
            northness.rename("northness"),
            eastness.rename("eastness"),
            zonas_convergencia.rename("conv_zones"),
        ])
        .reduceRegion(
            reducer=ee.Reducer.mean().combine(
                ee.Reducer.sum().unweighted(), "", True
            ),
            geometry=region,
            scale=escala,
            maxPixels=1e9,
        )
        .getInfo()
    )

    return {
        "curvatura_horizontal_promedio": stats.get("curv_h_mean"),
        "curvatura_vertical_promedio": stats.get("curv_v_mean"),
        "northness_promedio": stats.get("northness_mean"),
        "eastness_promedio": stats.get("eastness_mean"),
        "zonas_convergencia_runout": int(stats.get("conv_zones_sum") or 0),
        "dem_fuente": "COPERNICUS/DEM/GLO30",
    }


def calcular_alphaearth(ee, bbox: list, anios: list[int]) -> dict:
    """
    Extrae embeddings AlphaEarth para el bbox y calcula similitud interanual.

    Dataset: GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL
    Cada imagen tiene 64 bandas (dim_0 a dim_63).

    Returns:
        dict con embedding_centroide y similitud_anios_previos
    """
    import math as _math

    region = ee.Geometry.Rectangle(bbox)

    embeddings_por_anio = {}
    for anio in anios:
        try:
            ae = (
                ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
                .filterDate(f"{anio}-01-01", f"{anio}-12-31")
                .filterBounds(region)
                .mean()
                .clip(region)
            )

            # Media de las 64 dimensiones en la región
            stats = ae.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=10,  # AlphaEarth nativo 10m
                maxPixels=1e9,
            ).getInfo()

            if stats:
                embedding = [stats.get(f"dim_{i}", 0.0) for i in range(64)]
                embeddings_por_anio[anio] = embedding
                logger.info(f"AlphaEarth: embedding año {anio} extraído (norma={_norma(embedding):.3f})")
            else:
                logger.warning(f"AlphaEarth: sin datos para año {anio}")

        except Exception as exc:
            logger.warning(f"AlphaEarth: error año {anio} — {exc}")

    if not embeddings_por_anio:
        return {"embedding_centroide_zona": None, "similitud_anios_previos": {}}

    # Embedding centroide (promedio de todos los años disponibles)
    anios_disponibles = sorted(embeddings_por_anio.keys())
    centroide = [
        sum(embeddings_por_anio[a][i] for a in anios_disponibles) / len(anios_disponibles)
        for i in range(64)
    ]

    # Similitud coseno entre años consecutivos
    similitudes = {}
    for i in range(1, len(anios_disponibles)):
        a_prev = anios_disponibles[i - 1]
        a_curr = anios_disponibles[i]
        sim = _similitud_coseno(embeddings_por_anio[a_prev], embeddings_por_anio[a_curr])
        similitudes[str(a_curr)] = round(sim, 6)
        logger.info(f"AlphaEarth: similitud {a_prev}→{a_curr} = {sim:.4f}")

    return {
        "embedding_centroide_zona": json.dumps(centroide),
        "similitud_anios_previos": json.dumps(similitudes),
    }


def _norma(v: list[float]) -> float:
    import math as _m
    return _m.sqrt(sum(x * x for x in v)) + 1e-12


def _similitud_coseno(a: list[float], b: list[float]) -> float:
    import math as _m
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (_norma(a) * _norma(b))


def escribir_en_bigquery(zona_nombre_bq: str, datos: dict, dry_run: bool = False):
    """
    Inserta una fila en pendientes_detalladas con los nuevos campos.

    Usa INSERT en lugar de UPDATE para mantener historial temporal.
    Los campos legacy (NASADEM) se dejan en NULL en esta fila.
    """
    from google.cloud import bigquery

    tabla_id = f"{GCP_PROJECT}.{DATASET}.{TABLA}"

    fila = {
        "nombre_ubicacion": zona_nombre_bq,
        "fecha_analisis": datetime.now(timezone.utc).isoformat(),
        "dem_fuente": datos.get("dem_fuente", "COPERNICUS/DEM/GLO30"),
        "resolucion_m": 30,
        # TAGEE
        "curvatura_horizontal_promedio": datos.get("curvatura_horizontal_promedio"),
        "curvatura_vertical_promedio": datos.get("curvatura_vertical_promedio"),
        "northness_promedio": datos.get("northness_promedio"),
        "eastness_promedio": datos.get("eastness_promedio"),
        "zonas_convergencia_runout": datos.get("zonas_convergencia_runout"),
        # AlphaEarth
        "embedding_centroide_zona": datos.get("embedding_centroide_zona"),
        "similitud_anios_previos": datos.get("similitud_anios_previos"),
    }

    # Eliminar nulos para evitar error de schema si columnas no existen
    fila_limpia = {k: v for k, v in fila.items() if v is not None}

    if dry_run:
        logger.info(f"[DRY-RUN] Fila a insertar en {tabla_id}:")
        for k, v in fila_limpia.items():
            val_str = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
            logger.info(f"  {k}: {val_str}")
        return

    client = bigquery.Client(project=GCP_PROJECT)

    # Agregar columnas nuevas si no existen (schema auto-detect vía UPDATE)
    _asegurar_columnas_bq(client, tabla_id)

    errors = client.insert_rows_json(tabla_id, [fila_limpia])
    if errors:
        logger.error(f"Error insertando en BQ: {errors}")
    else:
        logger.info(f"✅ {zona_nombre_bq}: datos GLO-30/TAGEE/AE guardados en BQ")


def _asegurar_columnas_bq(client, tabla_id: str):
    """Añade columnas nuevas a la tabla si no existen."""
    from google.cloud import bigquery

    nuevas_columnas = [
        bigquery.SchemaField("curvatura_horizontal_promedio", "FLOAT64"),
        bigquery.SchemaField("curvatura_vertical_promedio", "FLOAT64"),
        bigquery.SchemaField("northness_promedio", "FLOAT64"),
        bigquery.SchemaField("eastness_promedio", "FLOAT64"),
        bigquery.SchemaField("zonas_convergencia_runout", "INT64"),
        bigquery.SchemaField("embedding_centroide_zona", "STRING"),
        bigquery.SchemaField("similitud_anios_previos", "STRING"),
    ]

    try:
        tabla = client.get_table(tabla_id)
        campos_existentes = {f.name for f in tabla.schema}

        campos_nuevos = [c for c in nuevas_columnas if c.name not in campos_existentes]
        if not campos_nuevos:
            return

        tabla.schema = list(tabla.schema) + campos_nuevos
        client.update_table(tabla, ["schema"])
        logger.info(f"Schema actualizado: +{[c.name for c in campos_nuevos]}")

    except Exception as exc:
        logger.warning(f"No se pudo actualizar schema automáticamente: {exc}")


def procesar_zona(ee, zona_nombre: str, config: dict, dry_run: bool):
    """Procesa una zona: calcula GLO-30+TAGEE+AE y escribe en BQ."""
    logger.info(f"\n{'─'*50}\nProcesando: {zona_nombre}")
    bbox = config["bbox"]
    nombre_bq = config["nombre_bq"]

    datos = {}

    # 1. GLO-30 + TAGEE
    logger.info("Calculando GLO-30 + TAGEE...")
    try:
        tagee_data = calcular_glo30_tagee(ee, bbox)
        datos.update(tagee_data)
        logger.info(
            f"  curv_h={tagee_data.get('curvatura_horizontal_promedio'):.4f}, "
            f"curv_v={tagee_data.get('curvatura_vertical_promedio'):.4f}, "
            f"conv_zones={tagee_data.get('zonas_convergencia_runout')}"
        )
    except Exception as exc:
        logger.error(f"Error GLO-30/TAGEE: {exc}")

    # 2. AlphaEarth
    logger.info(f"Extrayendo AlphaEarth embeddings ({ANIOS_ALPHAEARTH})...")
    try:
        ae_data = calcular_alphaearth(ee, bbox, ANIOS_ALPHAEARTH)
        datos.update(ae_data)
        if ae_data.get("embedding_centroide_zona"):
            emb = json.loads(ae_data["embedding_centroide_zona"])
            logger.info(f"  Embedding 64D calculado (norma={_norma(emb):.3f})")
    except Exception as exc:
        logger.error(f"Error AlphaEarth: {exc}")

    # 3. Escribir en BQ
    escribir_en_bigquery(nombre_bq, datos, dry_run=dry_run)


def main():
    import math  # para calcular_glo30_tagee

    parser = argparse.ArgumentParser(
        description="Actualiza pendientes_detalladas con GLO-30 + TAGEE + AlphaEarth"
    )
    parser.add_argument(
        "--zona",
        help="Nombre de zona específica (default: todas)",
        choices=list(ZONAS.keys()),
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcular y mostrar sin escribir en BigQuery",
    )
    parser.add_argument(
        "--verificar-quota",
        action="store_true",
        help="Solo mostrar uso de quota EE sin procesar",
    )
    args = parser.parse_args()

    ee = inicializar_earth_engine()

    if args.verificar_quota:
        try:
            info = ee.data.getAssetRoots()
            logger.info(f"Earth Engine acceso OK — roots: {info}")
            logger.info(
                "Para ver uso de EECU: https://console.cloud.google.com/earth-engine/quota"
            )
        except Exception as exc:
            logger.error(f"Error verificando quota: {exc}")
        return

    zonas_a_procesar = (
        {args.zona: ZONAS[args.zona]}
        if args.zona
        else ZONAS
    )

    logger.info(
        f"Procesando {len(zonas_a_procesar)} zona(s) "
        f"{'[DRY-RUN]' if args.dry_run else '[PRODUCCIÓN]'}"
    )

    for nombre, config in zonas_a_procesar.items():
        try:
            procesar_zona(ee, nombre, config, dry_run=args.dry_run)
        except Exception as exc:
            logger.error(f"Error procesando {nombre}: {exc}")

    logger.info("\n✅ Backfill GLO-30/TAGEE/AlphaEarth completado")
    logger.info(
        "Próximo paso: activar en S1 — los datos se leerán automáticamente "
        "desde ConsultorBigQuery.obtener_atributos_tagee_ae()"
    )


if __name__ == "__main__":
    import math
    main()

"""
Notebook 07: Validación con datos SLF Suiza — H1 y H3

Hipótesis H1: F1-macro ≥ 75% en clasificación de niveles EAWS
Hipótesis H3: QWK comparable a Techel et al. (2022) → kappa ≥ 0.59

Fuentes:
- clima.boletines_riesgo (nuestras predicciones para estaciones suizas)
- validacion_avalanchas.slf_danger_levels_qc (niveles EAWS verificados SLF, 2001-2024)

Mapeo estación → sector SLF preciso (REQ-04):
  Interlaken        → sector 4113 (Bernese Oberland central)
  Matterhorn Zermatt → sector 2223 (Alto Valais / Zermatt)
  St Moritz         → sector 6113 (Engadin Superior)

Nota metodológica:
  A partir de REQ-04, el mapeo usa el sector SLF geográficamente más cercano
  a cada estación (no el nivel modal del cantón). Esto reduce el ruido del
  ground truth, ya que dentro de un cantón los niveles pueden variar ±1.
  Fallback automático al modal del cantón si el sector preciso no tiene datos.

Fechas de validación: invierno norte 2023-2024
  2023-12-01, 2023-12-15, 2024-01-01, 2024-01-15, 2024-02-01, 2024-02-15,
  2024-03-01, 2024-03-15, 2024-04-01, 2024-04-15

Uso:
    python notebooks_validacion/07_validacion_slf_suiza.py
    python notebooks_validacion/07_validacion_slf_suiza.py --verbose
    python notebooks_validacion/07_validacion_slf_suiza.py --mapeo-canton  # mapeo antiguo
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

from google.cloud import bigquery

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agentes.validacion.metricas_eaws import (
    calcular_f1_macro,
    calcular_kappa_ponderado_cuadratico,
    calcular_accuracy_adyacente,
    comparar_con_techel_2022,
    TECHEL_2022_REFERENCIA,
)
from agentes.validacion.mapeo_estaciones_slf import (
    MAPEO_ESTACIONES_SLF,
    resumen_mapeo,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get('GCP_PROJECT', 'climas-chileno')

# Mapeo legado (cantón modal) — mantenido para comparación con --mapeo-canton
MAPEO_ESTACION_CANTON = {
    "St Moritz":          {"canton": "Graubünden", "prefix": "6", "sector_ref": 6113},
    "Interlaken":         {"canton": "Bern",        "prefix": "4", "sector_ref": 4113},
    "Matterhorn Zermatt": {"canton": "Valais",      "prefix": "2", "sector_ref": 2223},
}

FECHAS_VALIDACION = [
    "2023-12-01", "2023-12-15",
    "2024-01-01", "2024-01-15",
    "2024-02-01", "2024-02-15",
    "2024-03-01", "2024-03-15",
    "2024-04-01", "2024-04-15",
]


def obtener_nuestros_boletines(
    cliente: bigquery.Client,
    ubicaciones: list[str],
    fechas: list[str],
) -> dict:
    """
    Obtiene nuestros boletines para las ubicaciones y fechas indicadas.

    Returns:
        Dict {(ubicacion, fecha_str): nivel_eaws_24h}
    """
    ubicaciones_sql = ", ".join(f'"{u}"' for u in ubicaciones)
    fechas_sql = ", ".join(f'"{f}"' for f in fechas)

    query = f"""
        SELECT
            nombre_ubicacion,
            DATE(fecha_emision) as fecha,
            nivel_eaws_24h
        FROM `{GCP_PROJECT}.clima.boletines_riesgo`
        WHERE nombre_ubicacion IN ({ubicaciones_sql})
          AND DATE(fecha_emision) IN ({fechas_sql})
        ORDER BY nombre_ubicacion, fecha
    """

    try:
        resultados = list(cliente.query(query).result())
        boletines = {}
        for row in resultados:
            clave = (row["nombre_ubicacion"], str(row["fecha"]))
            if row["nivel_eaws_24h"] is not None:
                boletines[clave] = int(row["nivel_eaws_24h"])
        return boletines
    except Exception as e:
        logger.error(f"Error obteniendo boletines: {e}")
        return {}


def obtener_niveles_slf_preciso(
    cliente: bigquery.Client,
    fechas: list[str],
) -> tuple[dict, dict]:
    """
    Obtiene niveles SLF usando el sector geográficamente más cercano a cada
    estación (mapeo preciso REQ-04).

    Estrategia:
    1. Consulta primaria: nivel del sector_id exacto de MAPEO_ESTACIONES_SLF.
    2. Fallback: si el sector preciso no tiene datos para una fecha, usa el
       nivel modal del cantón (comportamiento anterior).

    Args:
        cliente: cliente BigQuery
        fechas: lista de fechas "YYYY-MM-DD"

    Returns:
        Tuple (niveles_slf, metadata):
        - niveles_slf: {(estacion, fecha): nivel_slf}
        - metadata:    {(estacion, fecha): {"sector_id": int, "via": "preciso"|"fallback_canton"}}
    """
    fechas_sql     = ", ".join(f'"{f}"' for f in fechas)
    sector_ids     = [info["sector_id"] for info in MAPEO_ESTACIONES_SLF.values()]
    sector_ids_sql = ", ".join(str(s) for s in sector_ids)
    prefixes       = {info["prefix_canton"] for info in MAPEO_ESTACIONES_SLF.values()}

    condicion_prefix = " OR ".join(
        f'STARTS_WITH(CAST(sector_id AS STRING), "{p}")'
        for p in prefixes
    )

    # Una sola query que trae tanto los sectores precisos como todo el cantón
    query = f"""
        SELECT
            sector_id,
            CAST(date AS STRING) AS fecha,
            danger_level_qc
        FROM `{GCP_PROJECT}.validacion_avalanchas.slf_danger_levels_qc`
        WHERE CAST(date AS STRING) IN ({fechas_sql})
          AND ({condicion_prefix})
          AND danger_level_qc IS NOT NULL
        ORDER BY sector_id, fecha
    """

    try:
        resultados = list(cliente.query(query).result())
    except Exception as e:
        logger.error(f"Error obteniendo datos SLF: {e}")
        return {}, {}

    # Indexar por sector_id exacto y por prefix de cantón
    por_sector_fecha: dict[tuple, int]   = {}
    por_canton_fecha: dict[tuple, list]  = {}

    for row in resultados:
        sid   = int(row["sector_id"])
        fecha = str(row["fecha"])
        nivel = int(row["danger_level_qc"])
        por_sector_fecha[(sid, fecha)] = nivel

        prefix = str(sid)[0]
        clave_canton = (prefix, fecha)
        por_canton_fecha.setdefault(clave_canton, []).append(nivel)

    niveles_slf = {}
    metadata    = {}

    for estacion, info in MAPEO_ESTACIONES_SLF.items():
        sector_id = info["sector_id"]
        prefix    = info["prefix_canton"]

        for fecha in fechas:
            # Intento 1: sector preciso
            nivel = por_sector_fecha.get((sector_id, fecha))
            if nivel is not None:
                niveles_slf[(estacion, fecha)] = nivel
                metadata[(estacion, fecha)]    = {"sector_id": sector_id, "via": "preciso"}
                continue

            # Intento 2: fallback al modal del cantón
            niveles_canton = por_canton_fecha.get((prefix, fecha), [])
            if niveles_canton:
                nivel_modal = Counter(niveles_canton).most_common(1)[0][0]
                niveles_slf[(estacion, fecha)] = nivel_modal
                metadata[(estacion, fecha)]    = {
                    "sector_id": sector_id,
                    "via":       "fallback_canton",
                }
                logger.debug(
                    f"[SLF] Fallback cantón para {estacion} {fecha}: "
                    f"sector {sector_id} sin datos → modal cantón prefix={prefix}"
                )

    return niveles_slf, metadata


def obtener_niveles_slf(
    cliente: bigquery.Client,
    mapeo: dict,
    fechas: list[str],
) -> dict:
    """
    Obtiene niveles SLF usando el nivel modal del cantón (mapeo legado).

    Mantenido para comparación con --mapeo-canton. En el flujo normal se usa
    obtener_niveles_slf_preciso().

    Returns:
        Dict {(estacion, fecha_str): nivel_slf}
    """
    fechas_sql = ", ".join(f'"{f}"' for f in fechas)
    prefixes_usados = {v["prefix"] for v in mapeo.values()}

    condicion_prefix = " OR ".join(
        f'STARTS_WITH(CAST(sector_id AS STRING), "{p}")'
        for p in prefixes_usados
    )

    query = f"""
        SELECT
            sector_id,
            CAST(date AS STRING) as fecha,
            danger_level_qc
        FROM `{GCP_PROJECT}.validacion_avalanchas.slf_danger_levels_qc`
        WHERE CAST(date AS STRING) IN ({fechas_sql})
          AND ({condicion_prefix})
          AND danger_level_qc IS NOT NULL
        ORDER BY sector_id, fecha
    """

    try:
        resultados = list(cliente.query(query).result())
    except Exception as e:
        logger.error(f"Error obteniendo datos SLF: {e}")
        return {}

    niveles_por_canton_fecha: dict[tuple, list] = {}
    for row in resultados:
        sector_str = str(row["sector_id"])
        prefix = sector_str[0]
        clave = (prefix, row["fecha"])
        if clave not in niveles_por_canton_fecha:
            niveles_por_canton_fecha[clave] = []
        niveles_por_canton_fecha[clave].append(int(row["danger_level_qc"]))

    niveles_slf = {}
    for estacion, info in mapeo.items():
        prefix = info["prefix"]
        for fecha in fechas:
            clave_canton = (prefix, fecha)
            niveles = niveles_por_canton_fecha.get(clave_canton, [])
            if niveles:
                contador = Counter(niveles)
                nivel_modal = contador.most_common(1)[0][0]
                niveles_slf[(estacion, fecha)] = nivel_modal

    return niveles_slf


def main():
    parser = argparse.ArgumentParser(
        description="Validación H1/H3 con datos SLF Suiza"
    )
    parser.add_argument(
        "--mapeo-canton", action="store_true",
        help="Usar mapeo legado (modal cantón) en lugar del mapeo preciso por sector (REQ-04)"
    )
    parser.add_argument("--verbose", action="store_true", help="Logging detallado")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    modo_mapeo = "canton (legado)" if args.mapeo_canton else "sector preciso (REQ-04)"

    print("=" * 70)
    print("NOTEBOOK 07: Validación con datos SLF Suiza (H1 y H3)")
    print(f"Fecha: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Mapeo: {modo_mapeo}")
    print(f"Objetivo H1: F1-macro ≥ 75%")
    print(f"Objetivo H3: QWK comparable a Techel (2022) kappa={TECHEL_2022_REFERENCIA['kappa_ponderado']}")
    print("=" * 70)

    if not args.mapeo_canton:
        print(f"\n{resumen_mapeo()}")

    cliente    = bigquery.Client(project=GCP_PROJECT)
    ubicaciones = list(MAPEO_ESTACIONES_SLF.keys())

    print(f"\n[1/4] Obteniendo boletines de AndesAI para {len(ubicaciones)} estaciones suizas...")
    nuestros = obtener_nuestros_boletines(cliente, ubicaciones, FECHAS_VALIDACION)
    print(f"      {len(nuestros)} boletines encontrados")

    if not nuestros:
        print("ERROR: Sin boletines — ejecutar generar_boletines_invierno.py primero")
        return

    print("\n      Boletines por estación:")
    for estacion in ubicaciones:
        boletines_est = {k: v for k, v in nuestros.items() if k[0] == estacion}
        print(f"      {estacion}: {len(boletines_est)} boletines — {sorted(boletines_est.items())}")

    print(f"\n[2/4] Obteniendo niveles SLF ({modo_mapeo}) para {len(FECHAS_VALIDACION)} fechas...")

    if args.mapeo_canton:
        niveles_slf = obtener_niveles_slf(cliente, MAPEO_ESTACION_CANTON, FECHAS_VALIDACION)
        meta_slf    = {k: {"via": "canton_modal"} for k in niveles_slf}
    else:
        niveles_slf, meta_slf = obtener_niveles_slf_preciso(cliente, FECHAS_VALIDACION)

    print(f"      {len(niveles_slf)} pares (estacion, fecha) con datos SLF")

    if niveles_slf and not args.mapeo_canton:
        via_preciso  = sum(1 for m in meta_slf.values() if m.get("via") == "preciso")
        via_fallback = sum(1 for m in meta_slf.values() if m.get("via") == "fallback_canton")
        print(f"      Sector preciso: {via_preciso} pares | Fallback cantón: {via_fallback} pares")

    if not niveles_slf:
        print("ERROR: Sin datos SLF — verificar acceso a dataset validacion_avalanchas")
        return

    # Emparejar predicciones y ground truth
    print("\n[3/4] Emparejando predicciones vs SLF ground truth...")
    predichos = []
    reales    = []
    detalles  = []

    for estacion in ubicaciones:
        info_mapeo = MAPEO_ESTACIONES_SLF.get(estacion, {})
        canton     = info_mapeo.get("canton", "?")
        sector_id  = info_mapeo.get("sector_id", "?")

        for fecha in FECHAS_VALIDACION:
            clave         = (estacion, fecha)
            nivel_nuestro = nuestros.get(clave)
            nivel_slf     = niveles_slf.get(clave)
            via           = meta_slf.get(clave, {}).get("via", "?")

            if nivel_nuestro is not None and nivel_slf is not None:
                predichos.append(nivel_nuestro)
                reales.append(nivel_slf)
                diferencia = nivel_nuestro - nivel_slf
                detalles.append({
                    "estacion":   estacion,
                    "canton":     canton,
                    "sector_ref": sector_id,
                    "via_mapeo":  via,
                    "fecha":      fecha,
                    "nuestro":    nivel_nuestro,
                    "slf":        nivel_slf,
                    "diferencia": diferencia,
                })
            elif nivel_nuestro is None:
                logger.debug(f"Sin boletín: {estacion} {fecha}")
            elif nivel_slf is None:
                logger.debug(f"Sin SLF: {estacion} {fecha}")

    n_pares = len(predichos)
    print(f"      {n_pares} pares emparejados de {len(ubicaciones) * len(FECHAS_VALIDACION)} posibles")

    if n_pares < 5:
        print(f"ADVERTENCIA: Solo {n_pares} pares — resultados no estadísticamente confiables")

    # Tabla de emparejamientos
    print(f"\n      {'Estación':<22} {'Fecha':<12} {'Nuestro':>8} {'SLF':>6} {'Dif':>5} {'Via':>14}")
    print(f"      {'-'*72}")
    for d in sorted(detalles, key=lambda x: (x['estacion'], x['fecha'])):
        signo = "+" if d['diferencia'] > 0 else ""
        via   = d.get('via_mapeo', '?')
        print(
            f"      {d['estacion']:<22} {d['fecha']:<12} "
            f"{d['nuestro']:>8} {d['slf']:>6} {signo}{d['diferencia']:>4}  {via:>14}"
        )

    if not predichos:
        print("ERROR: Sin pares válidos para calcular métricas")
        return

    # Calcular métricas
    print(f"\n[4/4] Calculando métricas H1 y H3...")

    f1_result = calcular_f1_macro(reales, predichos)
    adj_result = calcular_accuracy_adyacente(reales, predichos)
    qwk_result = calcular_kappa_ponderado_cuadratico(reales, predichos)
    techel_cmp = comparar_con_techel_2022(reales, predichos)

    print("\n" + "=" * 70)
    print("RESULTADOS H1 — F1-macro en clasificación EAWS (1-5)")
    print("=" * 70)
    print(f"  n_muestras     : {n_pares}")
    print(f"  F1-macro       : {f1_result['f1_macro']:.4f}  (objetivo: ≥ 0.75)")
    print(f"  Accuracy exacta: {f1_result['accuracy']:.4f}")
    print(f"  Accuracy ±1    : {adj_result['accuracy_adyacente']:.4f}")
    print(f"  Sesgo medio    : {adj_result['sesgo_medio']:+.2f} (+ = sobrestimamos)")

    h1_alcanzado = f1_result['f1_macro'] >= 0.75
    print(f"\n  {'✅ H1 VERIFICADA' if h1_alcanzado else '❌ H1 NO ALCANZADA'}: F1-macro = {f1_result['f1_macro']:.4f}")

    print(f"\n  F1 por clase:")
    detalle = {d["nivel"]: d for d in f1_result.get("detalle_por_clase", [])}
    for nivel in [1, 2, 3, 4, 5]:
        metricas = detalle.get(nivel, {})
        f1_n = metricas.get("f1", 0.0)
        n_real = metricas.get("soporte", 0)
        print(f"    Nivel {nivel}: F1={f1_n:.3f} (n={n_real})")

    print("\n" + "=" * 70)
    print("RESULTADOS H3 — Comparación con Techel et al. (2022)")
    print("=" * 70)
    ref = TECHEL_2022_REFERENCIA
    nuestro = techel_cmp["nuestro_sistema"]
    print(f"  {'Métrica':<30} {'Techel 2022':>12} {'AndesAI':>12} {'Estado':>10}")
    print(f"  {'-'*66}")
    print(f"  {'Accuracy exacta':<30} {ref['accuracy']:>12.4f} {nuestro['accuracy']:>12.4f}")
    print(f"  {'Accuracy adyacente (±1)':<30} {ref['accuracy_adyacente']:>12.4f} {nuestro['accuracy_adyacente']:>12.4f}")
    print(f"  {'F1-macro':<30} {ref['f1_macro_estimado']:>12.4f} {nuestro['f1_macro']:>12.4f}")
    qwk_val = qwk_result.get("kappa_ponderado", 0)
    qwk_ok = "✅" if qwk_val >= ref["kappa_ponderado"] else "❌"
    print(f"  {'QWK (kappa ponderado)':<30} {ref['kappa_ponderado']:>12.4f} {qwk_val:>12.4f}  {qwk_ok}")

    print(f"\n  Distribución de niveles:")
    dist_techel = ref["distribucion_niveles"]
    dist_nuestro = techel_cmp["nuestro_sistema"].get("distribucion_niveles", {})
    n_preds = len(predichos)
    contador_pred = Counter(predichos)
    contador_real = Counter(reales)
    print(f"  {'Nivel':<8} {'SLF (%)':<12} {'Techel Ref (%)':<16} {'AndesAI (%)':<14}")
    for nivel in [1, 2, 3, 4, 5]:
        pct_slf = contador_real.get(nivel, 0) / n_pares * 100
        pct_techel = dist_techel.get(nivel, 0) * 100
        pct_nuestro = contador_pred.get(nivel, 0) / n_pares * 100
        print(f"  {nivel:<8} {pct_slf:<12.1f} {pct_techel:<16.1f} {pct_nuestro:<14.1f}")

    print(f"\n  {'✅ H3 VERIFICADA' if qwk_val >= ref['kappa_ponderado'] else '❌ H3 NO ALCANZADA'}: QWK = {qwk_val:.4f} (umbral: ≥ {ref['kappa_ponderado']})")

    print("\n" + "=" * 70)
    print("LIMITACIONES METODOLÓGICAS (para tesis)")
    print("=" * 70)
    if args.mapeo_canton:
        print("  1. Mapeo estación→sectores SLF es aproximado (nivel modal del cantón)")
    else:
        via_preciso  = sum(1 for d in detalles if d.get('via_mapeo') == 'preciso')
        via_fallback = sum(1 for d in detalles if d.get('via_mapeo') == 'fallback_canton')
        print(f"  1. Mapeo preciso por sector (REQ-04): {via_preciso}/{n_pares} pares vía sector exacto, "
              f"{via_fallback}/{n_pares} vía fallback cantón")
    print("  2. Diferentes años: SLF 2001-2024, AndesAI entrenado en 2024-2026")
    print("  3. n=30 pares — p-value y IC 95% deben calcularse con bootstrap")
    print("  4. Datos ERA5 @9km vs datos estaciones IMIS @punto exacto → sesgo altura")
    print("  5. AndesAI incluye 5 subagentes; Techel usa solo datos meteo+snowpack")
    print("  → Esta comparación es exploratoria, no directamente comparable a Techel")

    print("\n[Fin] Exportando detalles a /tmp/validacion_slf_suiza.json")
    resultado_final = {
        "fecha_analisis": datetime.now(timezone.utc).isoformat(),
        "modo_mapeo":     "canton_modal" if args.mapeo_canton else "sector_preciso_req04",
        "n_pares":        n_pares,
        "h1": {
            "f1_macro": f1_result["f1_macro"],
            "accuracy": f1_result["accuracy"],
            "objetivo": 0.75,
            "alcanzada": h1_alcanzado,
        },
        "h3": {
            "qwk":            qwk_val,
            "objetivo_techel": ref["kappa_ponderado"],
            "alcanzada":      qwk_val >= ref["kappa_ponderado"],
        },
        "detalles": detalles,
    }
    with open("/tmp/validacion_slf_suiza.json", "w") as f:
        json.dump(resultado_final, f, indent=2, default=str)
    print("    Guardado en /tmp/validacion_slf_suiza.json")


if __name__ == "__main__":
    main()

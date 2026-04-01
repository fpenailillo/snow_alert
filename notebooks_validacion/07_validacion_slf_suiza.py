"""
Notebook 07: Validación con datos SLF Suiza — H1 y H3

Hipótesis H1: F1-macro ≥ 75% en clasificación de niveles EAWS
Hipótesis H3: QWK comparable a Techel et al. (2022) → kappa ≥ 0.59

Fuentes:
- clima.boletines_riesgo (nuestras predicciones para estaciones suizas)
- validacion_avalanchas.slf_danger_levels_qc (niveles EAWS verificados SLF, 2001-2024)

Mapeo estación → sectores SLF (por cantón):
  St Moritz         → sectores 6xxx (Graubünden/Engadin)
  Interlaken        → sectores 4xxx (Bern/Bernese Oberland)
  Matterhorn Zermatt → sectores 2xxx (Valais)

Nota metodológica:
  El mapeo usa el nivel modal de todos los sectores del cantón para la fecha dada.
  Esto es una aproximación: dentro de un cantón los niveles pueden variar ±1.
  Los sectores más representativos (mayor registro histórico) se priorizan.

Fechas de validación: invierno norte 2023-2024
  2023-12-01, 2023-12-15, 2024-01-01, 2024-01-15, 2024-02-01, 2024-02-15,
  2024-03-01, 2024-03-15, 2024-04-01, 2024-04-15

Uso:
    python notebooks_validacion/07_validacion_slf_suiza.py
    python notebooks_validacion/07_validacion_slf_suiza.py --verbose
"""

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

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get('GCP_PROJECT', 'climas-chileno')

# Mapeo estación → prefijo de canton en sector_id SLF
# Los sectores con más datos por cantón se usan como referencia
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


def obtener_niveles_slf(
    cliente: bigquery.Client,
    mapeo: dict,
    fechas: list[str],
) -> dict:
    """
    Obtiene niveles SLF para las fechas dadas, usando el modo del cantón.

    Para cada (estacion, fecha), devuelve el nivel modal de todos los sectores
    del cantón correspondiente en esa fecha.

    Returns:
        Dict {(estacion, fecha_str): nivel_slf}
    """
    fechas_sql = ", ".join(f'"{f}"' for f in fechas)
    prefixes_usados = {v["prefix"] for v in mapeo.values()}

    # Construir condición de prefixes
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

    # Agrupar por (prefix, fecha) → lista de niveles
    niveles_por_canton_fecha: dict[tuple, list] = {}
    for row in resultados:
        sector_str = str(row["sector_id"])
        prefix = sector_str[0]
        clave = (prefix, row["fecha"])
        if clave not in niveles_por_canton_fecha:
            niveles_por_canton_fecha[clave] = []
        niveles_por_canton_fecha[clave].append(int(row["danger_level_qc"]))

    # Para cada estación y fecha, calcular nivel modal del cantón
    niveles_slf = {}
    for estacion, info in mapeo.items():
        prefix = info["prefix"]
        for fecha in fechas:
            clave_canton = (prefix, fecha)
            niveles = niveles_por_canton_fecha.get(clave_canton, [])
            if niveles:
                # Usar la moda (nivel más frecuente del cantón ese día)
                contador = Counter(niveles)
                nivel_modal = contador.most_common(1)[0][0]
                niveles_slf[(estacion, fecha)] = nivel_modal

    return niveles_slf


def main():
    print("=" * 70)
    print("NOTEBOOK 07: Validación con datos SLF Suiza (H1 y H3)")
    print(f"Fecha: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Objetivo H1: F1-macro ≥ 75%")
    print(f"Objetivo H3: QWK comparable a Techel (2022) kappa={TECHEL_2022_REFERENCIA['kappa_ponderado']}")
    print("=" * 70)

    cliente = bigquery.Client(project=GCP_PROJECT)
    ubicaciones = list(MAPEO_ESTACION_CANTON.keys())

    print(f"\n[1/4] Obteniendo boletines de AndesAI para {len(ubicaciones)} estaciones suizas...")
    nuestros = obtener_nuestros_boletines(cliente, ubicaciones, FECHAS_VALIDACION)
    print(f"      {len(nuestros)} boletines encontrados")

    if not nuestros:
        print("ERROR: Sin boletines — ejecutar generar_boletines_invierno.py primero")
        return

    # Mostrar boletines encontrados
    print("\n      Boletines por estación:")
    for estacion in ubicaciones:
        boletines_est = {k: v for k, v in nuestros.items() if k[0] == estacion}
        print(f"      {estacion}: {len(boletines_est)} boletines — {sorted(boletines_est.items())}")

    print(f"\n[2/4] Obteniendo niveles SLF por cantón para {len(FECHAS_VALIDACION)} fechas...")
    niveles_slf = obtener_niveles_slf(cliente, MAPEO_ESTACION_CANTON, FECHAS_VALIDACION)
    print(f"      {len(niveles_slf)} pares (estacion, fecha) con datos SLF")

    if not niveles_slf:
        print("ERROR: Sin datos SLF — verificar acceso a dataset validacion_avalanchas")
        return

    # Emparejar predicciones y ground truth
    print("\n[3/4] Emparejando predicciones vs SLF ground truth...")
    predichos = []
    reales = []
    detalles = []

    for estacion in ubicaciones:
        canton = MAPEO_ESTACION_CANTON[estacion]["canton"]
        sector_ref = MAPEO_ESTACION_CANTON[estacion]["sector_ref"]
        for fecha in FECHAS_VALIDACION:
            clave = (estacion, fecha)
            nivel_nuestro = nuestros.get(clave)
            nivel_slf = niveles_slf.get(clave)
            if nivel_nuestro is not None and nivel_slf is not None:
                predichos.append(nivel_nuestro)
                reales.append(nivel_slf)
                diferencia = nivel_nuestro - nivel_slf
                detalles.append({
                    "estacion": estacion,
                    "canton": canton,
                    "sector_ref": sector_ref,
                    "fecha": fecha,
                    "nuestro": nivel_nuestro,
                    "slf": nivel_slf,
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
    print(f"\n      {'Estación':<22} {'Fecha':<12} {'Nuestro':>8} {'SLF':>6} {'Dif':>5}")
    print(f"      {'-'*55}")
    for d in sorted(detalles, key=lambda x: (x['estacion'], x['fecha'])):
        signo = "+" if d['diferencia'] > 0 else ""
        print(f"      {d['estacion']:<22} {d['fecha']:<12} {d['nuestro']:>8} {d['slf']:>6} {signo}{d['diferencia']:>4}")

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
    print("  1. Mapeo estación→sectores SLF es aproximado (nivel modal del cantón)")
    print("  2. Diferentes años: SLF 2001-2024, AndesAI entrenado en 2024-2026")
    print("  3. n=30 pares — p-value y IC 95% deben calcularse con bootstrap")
    print("  4. Datos ERA5 @9km vs datos estaciones IMIS @punto exacto → sesgo altura")
    print("  5. AndesAI incluye 5 subagentes; Techel usa solo datos meteo+snowpack")
    print("  → Esta comparación es exploratoria, no directamente comparable a Techel")

    print("\n[Fin] Exportando detalles a /tmp/validacion_slf_suiza.json")
    resultado_final = {
        "fecha_analisis": datetime.now(timezone.utc).isoformat(),
        "n_pares": n_pares,
        "h1": {
            "f1_macro": f1_result["f1_macro"],
            "accuracy": f1_result["accuracy"],
            "objetivo": 0.75,
            "alcanzada": h1_alcanzado,
        },
        "h3": {
            "qwk": qwk_val,
            "objetivo_techel": ref["kappa_ponderado"],
            "alcanzada": qwk_val >= ref["kappa_ponderado"],
        },
        "detalles": detalles,
    }
    with open("/tmp/validacion_slf_suiza.json", "w") as f:
        json.dump(resultado_final, f, indent=2, default=str)
    print("    Guardado en /tmp/validacion_slf_suiza.json")


if __name__ == "__main__":
    main()

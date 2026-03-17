"""
Notebook 02: Análisis de Ablación por Componente (H2)

Hipótesis H2: La incorporación del SubagenteNLP mejora la precisión
del sistema en >5 puntos porcentuales.

Método:
1. Generar boletines con sistema completo (5 subagentes)
2. Generar boletines sin SubagenteNLP (4 subagentes, degradado)
3. Comparar F1-macro, precision, recall entre ambas configuraciones
4. Extender a ablación completa (sin cada subagente)

Fuentes de datos:
- tabla clima.boletines_riesgo — campo `subagentes_ejecutados`
- campo `subagentes_degradados` identifica ejecuciones sin NLP

Requisitos:
- pip install google-cloud-bigquery
- GCP auth: gcloud auth application-default login
- Boletines generados con y sin SubagenteNLP

Uso:
    python databricks/02_analisis_ablacion.py
    python databricks/02_analisis_ablacion.py --ground-truth datos_validados.csv
"""

import sys
import os
import argparse
import json
import logging
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agentes.validacion.metricas_eaws import (
    calcular_f1_macro,
    calcular_delta_nlp,
    analisis_ablacion,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def obtener_boletines_por_configuracion(
    proyecto: str = "climas-chileno",
    dataset: str = "clima"
) -> dict:
    """
    Obtiene boletines agrupados por configuración de subagentes.

    Usa el campo `subagentes_degradados` para identificar ejecuciones
    donde algún subagente estaba desactivado/degradado.

    Returns:
        Dict {config_name: [{boletin}, ...]}
    """
    from google.cloud import bigquery

    cliente = bigquery.Client(project=proyecto)
    query = f"""
        SELECT
            nombre_ubicacion,
            fecha_emision,
            nivel_eaws_24h,
            subagentes_ejecutados,
            duracion_por_subagente,
            arquitectura
        FROM `{proyecto}.{dataset}.boletines_riesgo`
        WHERE nivel_eaws_24h IS NOT NULL
        ORDER BY fecha_emision DESC
    """

    try:
        resultados = list(cliente.query(query).result())
        boletines = [dict(row) for row in resultados]
    except Exception as e:
        logger.error(f"Error consultando boletines: {e}")
        return {}

    # Agrupar por configuración
    completos = []
    sin_nlp = []

    for b in boletines:
        ejecutados_raw = b.get("subagentes_ejecutados", "[]")
        try:
            ejecutados = json.loads(ejecutados_raw) if isinstance(ejecutados_raw, str) else ejecutados_raw
        except (json.JSONDecodeError, TypeError):
            ejecutados = []

        if "nlp" in ejecutados:
            completos.append(b)
        else:
            sin_nlp.append(b)

    return {
        "completo": completos,
        "sin_nlp": sin_nlp,
        "todos": boletines,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Análisis de ablación por componente (H2)"
    )
    parser.add_argument(
        '--ground-truth', '-g',
        help='CSV con ground truth',
        default=None
    )
    parser.add_argument(
        '--proyecto', default='climas-chileno',
        help='Proyecto GCP'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("NOTEBOOK 02: ANÁLISIS DE ABLACIÓN (H2)")
    print(f"Fecha: {datetime.now(timezone.utc).isoformat()}")
    print(f"Objetivo: Delta NLP > 5pp en F1-macro")
    print("=" * 60)

    # 1. Obtener boletines por configuración
    print("\n1. Obteniendo boletines de BigQuery...")
    grupos = obtener_boletines_por_configuracion(proyecto=args.proyecto)

    if not grupos:
        print("   ⚠ No se pudieron obtener boletines.")
        return

    n_completos = len(grupos.get("completo", []))
    n_sin_nlp = len(grupos.get("sin_nlp", []))
    n_total = len(grupos.get("todos", []))

    print(f"   Total boletines:     {n_total}")
    print(f"   Con NLP (completo):  {n_completos}")
    print(f"   Sin NLP (degradado): {n_sin_nlp}")

    if n_completos == 0:
        print("\n   ⚠ No hay boletines con sistema completo.")
        print("   Generar boletines con: python agentes/scripts/generar_todos.py")
        return

    # 2. Estadísticas descriptivas
    print("\n2. Distribución de niveles por configuración:")
    for config, boletines in grupos.items():
        if config == "todos":
            continue
        niveles = [b["nivel_eaws_24h"] for b in boletines if b.get("nivel_eaws_24h")]
        dist = Counter(niveles)
        print(f"   {config}: {dict(sorted(dist.items()))} (n={len(niveles)})")

    # 3. Análisis de ablación (requiere ground truth)
    if args.ground_truth:
        print(f"\n3. Cargando ground truth desde: {args.ground_truth}")
        # Importar loader del notebook 01
        from databricks import cargar_ground_truth_csv
        # TODO: implementar emparejamiento por (ubicacion, fecha)
        print("   ⚠ Implementar emparejamiento con ground truth")
    else:
        print("\n3. Sin ground truth — análisis solo descriptivo.")
        print("   Para H2, se necesitan:")
        print("   a) Ground truth (niveles reales validados)")
        print("   b) Boletines generados CON NLP (sistema completo)")
        print("   c) Boletines generados SIN NLP (forzar degradación)")
        print()
        print("   Para forzar degradación NLP y generar datos de ablación:")
        print("   1. Temporalmente desactivar SubagenteNLP en agente_principal.py")
        print("   2. Generar boletines para las mismas ubicaciones/fechas")
        print("   3. Reactivar SubagenteNLP")
        print("   4. Correr este notebook con --ground-truth")

    # 4. Demo con datos sintéticos
    print("\n4. Demo de ablación con datos sintéticos:")
    reales_demo = [2, 3, 3, 4, 2, 3, 2, 3, 4, 3, 2, 3, 3, 2, 4, 3, 2, 3, 3, 4]
    configs_demo = {
        "completo":          [2, 3, 3, 4, 2, 3, 2, 3, 4, 3, 2, 3, 3, 2, 4, 3, 2, 3, 3, 4],
        "sin_nlp":           [2, 3, 2, 4, 2, 3, 2, 2, 4, 3, 2, 3, 3, 2, 3, 3, 2, 3, 2, 4],
        "sin_satelital":     [2, 3, 3, 3, 2, 2, 2, 3, 3, 3, 2, 3, 2, 2, 4, 3, 2, 2, 3, 3],
        "sin_topografico":   [2, 2, 3, 3, 2, 3, 2, 2, 3, 2, 2, 3, 3, 2, 3, 2, 2, 3, 2, 3],
        "sin_meteorologico": [2, 3, 2, 3, 2, 2, 2, 3, 3, 3, 2, 3, 2, 2, 3, 3, 2, 2, 3, 3],
    }

    resultado = analisis_ablacion(reales_demo, configs_demo)

    print(f"\n   F1-macro sistema completo: {resultado['f1_completo']:.4f}")
    print(f"\n   {'Configuración':<25} {'F1-macro':<12} {'Delta (pp)':<12}")
    print(f"   {'-'*49}")
    for config, metricas in resultado["resultados_por_config"].items():
        delta = resultado["delta_pp_vs_completo"].get(
            config.replace("sin_", ""), ""
        )
        delta_str = f"{delta:+.2f}" if isinstance(delta, float) else "—"
        print(f"   {config:<25} {metricas['f1_macro']:<12.4f} {delta_str:<12}")

    print(f"\n   Ranking de importancia (mayor delta = más crítico):")
    for i, item in enumerate(resultado["ranking_importancia"], 1):
        print(f"   {i}. {item['componente']}: {item['delta_f1_pp']:+.2f}pp")

    # H2: Delta NLP específico
    delta_nlp = calcular_delta_nlp(
        reales_demo,
        configs_demo["completo"],
        configs_demo["sin_nlp"]
    )
    veredicto = "✅ CUMPLE" if delta_nlp["h2_cumple"] else "❌ NO CUMPLE"
    print(f"\n   H2 — Delta NLP: {delta_nlp['delta_f1_macro_pp']:+.2f}pp")
    print(f"   H2 (>5pp): {veredicto}")
    print(f"   (Nota: datos sintéticos — reemplazar con datos reales)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

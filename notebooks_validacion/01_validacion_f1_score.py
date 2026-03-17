"""
Notebook 01: Validación F1-score Macro por Nivel EAWS (H1)

Hipótesis H1: El sistema multi-agente alcanza F1-macro ≥ 75% en la
clasificación de niveles de peligro EAWS (1-5).

Fuentes de datos:
- tabla clima.boletines_riesgo (predicciones del sistema)
- Ground truth: niveles EAWS validados por expertos (Snowlab, SLF, o manual)

Requisitos:
- pip install google-cloud-bigquery matplotlib
- GCP auth: gcloud auth application-default login

Uso:
    python databricks/01_validacion_f1_score.py
    python databricks/01_validacion_f1_score.py --ground-truth datos_validados.csv
"""

import sys
import os
import argparse
import csv
import logging
from datetime import datetime, timezone

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agentes.validacion.metricas_eaws import (
    calcular_f1_macro,
    calcular_matriz_confusion,
    calcular_precision_recall_f1_por_clase,
    obtener_boletines_para_validacion,
    imprimir_reporte,
    generar_reporte_validacion,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def cargar_ground_truth(ruta_csv: str) -> dict:
    """
    Carga ground truth desde un CSV con columnas:
    nombre_ubicacion, fecha, nivel_eaws_real

    Returns:
        Dict {(ubicacion, fecha): nivel_real}
    """
    ground_truth = {}
    with open(ruta_csv, 'r', encoding='utf-8') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            clave = (
                fila['nombre_ubicacion'].strip(),
                fila['fecha'].strip()
            )
            ground_truth[clave] = int(fila['nivel_eaws_real'])
    logger.info(f"Cargadas {len(ground_truth)} etiquetas de ground truth")
    return ground_truth


def emparejar_predicciones_con_ground_truth(
    boletines: list,
    ground_truth: dict
) -> tuple:
    """
    Empareja boletines del sistema con ground truth por (ubicacion, fecha).

    Returns:
        (reales, predichos) — listas alineadas
    """
    reales = []
    predichos = []
    sin_match = 0

    for boletin in boletines:
        ubicacion = boletin.get("nombre_ubicacion", "")
        fecha = str(boletin.get("fecha_emision", ""))[:10]  # YYYY-MM-DD
        nivel_pred = boletin.get("nivel_eaws_24h")

        if nivel_pred is None:
            continue

        clave = (ubicacion, fecha)
        if clave in ground_truth:
            reales.append(ground_truth[clave])
            predichos.append(nivel_pred)
        else:
            sin_match += 1

    if sin_match > 0:
        logger.warning(
            f"{sin_match} boletines sin ground truth correspondiente"
        )

    return reales, predichos


def imprimir_matriz_confusion(matriz: list, niveles: list) -> None:
    """Imprime la matriz de confusión formateada."""
    print("\nMatriz de Confusión:")
    print(f"{'':>8}", end="")
    for n in niveles:
        print(f"  Pred {n}", end="")
    print()

    for i, nivel in enumerate(niveles):
        print(f"Real {nivel:>2}:", end="")
        for j in range(len(niveles)):
            print(f"  {matriz[i][j]:>5}", end="")
        print()


def imprimir_detalle_por_clase(por_clase: list) -> None:
    """Imprime métricas detalladas por nivel EAWS."""
    print(f"\n{'Nivel':<8} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Soporte':<10}")
    print("-" * 54)
    for c in por_clase:
        if c["soporte"] > 0:
            print(
                f"  {c['nivel']:<6} {c['precision']:<12.4f} {c['recall']:<12.4f} "
                f"{c['f1']:<12.4f} {c['soporte']:<10}"
            )
    print("-" * 54)


def main():
    parser = argparse.ArgumentParser(
        description="Validación F1-score macro EAWS (H1)"
    )
    parser.add_argument(
        '--ground-truth', '-g',
        help='CSV con ground truth (nombre_ubicacion, fecha, nivel_eaws_real)',
        default=None
    )
    parser.add_argument(
        '--proyecto', default='climas-chileno',
        help='Proyecto GCP (default: climas-chileno)'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("NOTEBOOK 01: VALIDACIÓN F1-SCORE MACRO (H1)")
    print(f"Fecha: {datetime.now(timezone.utc).isoformat()}")
    print(f"Objetivo: F1-macro ≥ 75%")
    print("=" * 60)

    # 1. Obtener boletines del sistema
    print("\n1. Obteniendo boletines de BigQuery...")
    boletines = obtener_boletines_para_validacion(proyecto=args.proyecto)
    print(f"   Boletines encontrados: {len(boletines)}")

    if not boletines:
        print("\n   ⚠ No hay boletines en BigQuery.")
        print("   Ejecutar: python agentes/scripts/generar_boletin.py --ubicacion 'La Parva'")
        return

    # Distribución de predicciones
    from collections import Counter
    predichos = [b["nivel_eaws_24h"] for b in boletines if b.get("nivel_eaws_24h")]
    dist = Counter(predichos)
    print(f"   Distribución de niveles predichos: {dict(sorted(dist.items()))}")

    # 2. Cargar ground truth
    if args.ground_truth:
        print(f"\n2. Cargando ground truth desde: {args.ground_truth}")
        ground_truth = cargar_ground_truth(args.ground_truth)
        reales, predichos = emparejar_predicciones_con_ground_truth(
            boletines, ground_truth
        )
        print(f"   Pares emparejados: {len(reales)}")

        if len(reales) < 10:
            print(f"   ⚠ Muy pocas muestras ({len(reales)}). Se recomienda ≥50.")

        if not reales:
            print("   ❌ No se pudieron emparejar predicciones con ground truth.")
            return

        # 3. Calcular métricas
        print("\n3. Calculando F1-score macro...")
        resultado_f1 = calcular_f1_macro(reales, predichos)

        # Imprimir resultados
        veredicto = "✅ CUMPLE" if resultado_f1["h1_cumple"] else "❌ NO CUMPLE"
        print(f"\n   F1-macro:  {resultado_f1['f1_macro']:.4f} ({resultado_f1['f1_macro']*100:.1f}%)")
        print(f"   Precision: {resultado_f1['precision_macro']:.4f}")
        print(f"   Recall:    {resultado_f1['recall_macro']:.4f}")
        print(f"   Accuracy:  {resultado_f1['accuracy']:.4f}")
        print(f"   Muestras:  {resultado_f1['total_muestras']}")
        print(f"\n   H1 (F1 ≥ 75%): {veredicto}")
        print(f"   Diferencia: {resultado_f1['h1_diferencia']:+.4f}")

        # Detalle por clase
        imprimir_detalle_por_clase(resultado_f1["detalle_por_clase"])

        # Matriz de confusión
        imprimir_matriz_confusion(
            resultado_f1["matriz_confusion"],
            resultado_f1["niveles"]
        )

        # 4. Reporte completo
        print("\n4. Generando reporte completo...")
        reporte = generar_reporte_validacion(reales=reales, predichos=predichos)
        imprimir_reporte(reporte)

    else:
        print("\n2. Sin ground truth — solo se muestran estadísticas descriptivas.")
        print("   Para calcular F1-score, proveer CSV con --ground-truth")
        print(f"\n   Boletines por ubicación:")
        ubicaciones = Counter(b.get("nombre_ubicacion", "?") for b in boletines)
        for ub, count in ubicaciones.most_common():
            print(f"     {ub}: {count} boletines")

        print(f"\n   Boletines por confianza:")
        confianzas = Counter(b.get("confianza", "N/A") for b in boletines)
        for conf, count in confianzas.most_common():
            print(f"     {conf}: {count}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

"""
Notebook 03: Comparación con Snowlab Chile + Techel (2022) (H3, H4)

Hipótesis H3: El sistema alcanza rendimiento comparable a Techel et al. (2022)
    — benchmark data-driven de SLF Suiza.
Hipótesis H4: Cohen's Kappa ≥ 0.60 entre nuestro sistema y Snowlab Chile.

Fuentes de datos:
- tabla clima.boletines_riesgo (predicciones del sistema)
- Datos Snowlab Chile (CSV manual o API si disponible)
- Referencia: Techel et al. (2022) NHESS 22(6):2031-2056

Requisitos:
- pip install google-cloud-bigquery
- GCP auth: gcloud auth application-default login

Uso:
    python databricks/03_comparacion_snowlab.py
    python databricks/03_comparacion_snowlab.py --snowlab datos_snowlab.csv --ground-truth gt.csv
"""

import sys
import os
import argparse
import csv
import logging
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agentes.validacion.metricas_eaws import (
    calcular_cohens_kappa,
    calcular_kappa_ponderado_cuadratico,
    calcular_accuracy_adyacente,
    comparar_con_techel_2022,
    obtener_boletines_para_validacion,
    TECHEL_2022_REFERENCIA,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def cargar_snowlab_csv(ruta_csv: str) -> dict:
    """
    Carga datos de Snowlab Chile desde CSV.

    Formato esperado:
    nombre_ubicacion, fecha, nivel_eaws_snowlab

    Returns:
        Dict {(ubicacion, fecha): nivel_snowlab}
    """
    datos = {}
    with open(ruta_csv, 'r', encoding='utf-8') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            clave = (
                fila['nombre_ubicacion'].strip(),
                fila['fecha'].strip()
            )
            datos[clave] = int(fila['nivel_eaws_snowlab'])
    logger.info(f"Cargados {len(datos)} registros de Snowlab")
    return datos


def emparejar_con_snowlab(boletines: list, snowlab: dict) -> tuple:
    """
    Empareja boletines del sistema con datos de Snowlab.

    Returns:
        (sistema, snowlab_alineado) — listas alineadas de niveles EAWS
    """
    sistema = []
    snowlab_alineado = []

    for b in boletines:
        ubicacion = b.get("nombre_ubicacion", "")
        fecha = str(b.get("fecha_emision", ""))[:10]
        nivel = b.get("nivel_eaws_24h")

        if nivel is None:
            continue

        clave = (ubicacion, fecha)
        if clave in snowlab:
            sistema.append(nivel)
            snowlab_alineado.append(snowlab[clave])

    return sistema, snowlab_alineado


def imprimir_referencia_techel():
    """Imprime las métricas de referencia de Techel et al. (2022)."""
    ref = TECHEL_2022_REFERENCIA
    print(f"\n   Paper: {ref['paper']}")
    print(f"   DOI:   {ref['doi']}")
    print(f"   País:  {ref['pais']} | Período: {ref['periodo']}")
    print(f"   Modelo: {ref['modelo']}")
    print(f"   Muestras: {ref['n_muestras']:,}")
    print(f"\n   Métricas de referencia:")
    print(f"     Accuracy exacta:    {ref['accuracy']:.2f}")
    print(f"     Accuracy ±1 nivel:  {ref['accuracy_adyacente']:.2f}")
    print(f"     F1-macro estimado:  {ref['f1_macro_estimado']:.2f}")
    print(f"     QWK:                {ref['kappa_ponderado']:.2f}")
    print(f"     Sesgo:              {ref['sesgo_conocido']}")
    print(f"\n   Distribución niveles Suiza:")
    for nivel, prop in ref['distribucion_niveles'].items():
        barra = "█" * int(prop * 40)
        print(f"     Nivel {nivel}: {prop:>5.0%} {barra}")


def main():
    parser = argparse.ArgumentParser(
        description="Comparación con Snowlab Chile y Techel (2022)"
    )
    parser.add_argument(
        '--snowlab', '-s',
        help='CSV con datos Snowlab (nombre_ubicacion, fecha, nivel_eaws_snowlab)',
        default=None
    )
    parser.add_argument(
        '--ground-truth', '-g',
        help='CSV con ground truth para comparación Techel',
        default=None
    )
    parser.add_argument(
        '--proyecto', default='climas-chileno',
        help='Proyecto GCP'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("NOTEBOOK 03: COMPARACIÓN SNOWLAB + TECHEL (H3, H4)")
    print(f"Fecha: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. Referencia Techel
    print("\n1. Referencia: Techel et al. (2022)")
    imprimir_referencia_techel()

    # 2. Obtener boletines
    print("\n2. Obteniendo boletines de BigQuery...")
    boletines = obtener_boletines_para_validacion(proyecto=args.proyecto)
    print(f"   Boletines encontrados: {len(boletines)}")

    if boletines:
        predichos = [b["nivel_eaws_24h"] for b in boletines if b.get("nivel_eaws_24h")]
        dist = Counter(predichos)
        print(f"   Distribución nuestro sistema:")
        for nivel in sorted(dist.keys()):
            n = dist[nivel]
            prop = n / len(predichos)
            barra = "█" * int(prop * 40)
            print(f"     Nivel {nivel}: {prop:>5.0%} ({n}) {barra}")

    # 3. H3: Comparación con Techel (requiere ground truth)
    print("\n3. H3 — Comparación con Techel et al. (2022)")
    if args.ground_truth and boletines:
        from databricks import cargar_ground_truth_csv  # notebook 01
        # TODO: cargar y emparejar ground truth
        print("   ⚠ Implementar carga de ground truth")
    else:
        print("   Sin ground truth — comparación solo descriptiva.")
        print("   La comparación cuantitativa requiere niveles EAWS reales.")
        if boletines:
            ref = TECHEL_2022_REFERENCIA
            print(f"\n   Comparación de distribución de niveles:")
            print(f"   {'Nivel':<8} {'Nuestro':<12} {'Techel':<12} {'Delta':<10}")
            print(f"   {'-'*42}")
            for nivel in [1, 2, 3, 4, 5]:
                prop_nuestro = dist.get(nivel, 0) / len(predichos) if predichos else 0
                prop_techel = ref['distribucion_niveles'].get(nivel, 0)
                delta = prop_nuestro - prop_techel
                print(f"   {nivel:<8} {prop_nuestro:<12.2%} {prop_techel:<12.2%} {delta:+.2%}")

    # 4. H4: Kappa vs Snowlab
    print("\n4. H4 — Cohen's Kappa vs Snowlab Chile (objetivo ≥ 0.60)")
    if args.snowlab and boletines:
        print(f"   Cargando Snowlab desde: {args.snowlab}")
        snowlab_data = cargar_snowlab_csv(args.snowlab)
        sistema, snowlab_niveles = emparejar_con_snowlab(boletines, snowlab_data)
        print(f"   Pares emparejados: {len(sistema)}")

        if len(sistema) >= 10:
            # Cohen's Kappa simple
            kappa_result = calcular_cohens_kappa(sistema, snowlab_niveles)
            veredicto_h4 = "✅ CUMPLE" if kappa_result["h4_cumple"] else "❌ NO CUMPLE"
            print(f"\n   Cohen's Kappa:         {kappa_result['kappa']:.4f} ({kappa_result['interpretacion']})")
            print(f"   Concordancia observada: {kappa_result['concordancia_observada']:.4f}")
            print(f"   Concordancia esperada:  {kappa_result['concordancia_esperada']:.4f}")
            print(f"   H4 (≥0.60): {veredicto_h4}")

            # QWK (comparable con Techel)
            qwk_result = calcular_kappa_ponderado_cuadratico(sistema, snowlab_niveles)
            print(f"\n   QWK (comp. Techel):     {qwk_result['kappa_ponderado']:.4f}")
            print(f"   Techel QWK referencia:  {TECHEL_2022_REFERENCIA['kappa_ponderado']:.4f}")

            # Accuracy adyacente
            adj_result = calcular_accuracy_adyacente(snowlab_niveles, sistema)
            print(f"\n   Accuracy exacta:        {adj_result['accuracy_exacta']:.4f}")
            print(f"   Accuracy ±1 nivel:      {adj_result['accuracy_adyacente']:.4f}")
            print(f"   Sesgo: {adj_result['sesgo_direccion']} ({adj_result['sesgo_medio']:+.3f})")
        else:
            print(f"   ⚠ Muy pocas muestras ({len(sistema)}). Se recomienda ≥30.")
    else:
        print("   Sin datos Snowlab — H4 pendiente.")
        print("   Proveer CSV con: --snowlab datos_snowlab.csv")
        print("   Formato: nombre_ubicacion, fecha, nivel_eaws_snowlab")

    # 5. Demo con datos sintéticos
    print("\n5. Demo con datos sintéticos:")
    sistema_demo =  [2, 3, 3, 4, 2, 3, 2, 3, 4, 3, 2, 3, 3, 2, 4, 3, 2, 3, 3, 4]
    snowlab_demo =  [2, 3, 2, 4, 2, 3, 3, 3, 4, 3, 2, 3, 3, 2, 3, 3, 2, 3, 2, 4]
    reales_demo =   [2, 3, 3, 4, 2, 3, 3, 3, 4, 3, 2, 3, 3, 2, 4, 3, 2, 3, 3, 4]

    kappa_demo = calcular_cohens_kappa(sistema_demo, snowlab_demo)
    qwk_demo = calcular_kappa_ponderado_cuadratico(sistema_demo, snowlab_demo)
    print(f"   Cohen's Kappa: {kappa_demo['kappa']:.4f} ({kappa_demo['interpretacion']})")
    print(f"   QWK:           {qwk_demo['kappa_ponderado']:.4f}")

    comp_demo = comparar_con_techel_2022(reales_demo, sistema_demo)
    delta = comp_demo["comparacion_directa"]
    print(f"\n   vs Techel (2022):")
    print(f"     Delta accuracy:   {delta['delta_accuracy']:+.4f}")
    print(f"     Delta acc. ±1:    {delta['delta_accuracy_adyacente']:+.4f}")
    print(f"     Delta F1-macro:   {delta['delta_f1_macro']:+.4f}")
    print(f"     Delta QWK:        {delta['delta_kappa_ponderado']:+.4f}")
    print(f"   (Nota: datos sintéticos — reemplazar con datos reales)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

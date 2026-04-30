"""
Validación H4 — AndesAI vs Snowlab La Parva (ground truth)

Hipótesis H4:
    Kappa ≥ 0.60 entre el nivel EAWS del sistema AndesAI y los boletines
    Snowlab La Parva (temporadas 2024 y 2025), usando como ventana de
    comparación los días de validez de cada boletín Snowlab.

Metodología:
    1. Para cada boletín Snowlab, buscar los boletines AndesAI cuyos
       días de validez caen dentro del período Snowlab.
    2. Comparar nivel_eaws_24h (AndesAI) vs nivel correspondiente por banda
       (Sector Alto → nivel_alta, Sector Medio → nivel_media,
        Sector Bajo → nivel_baja).
    3. Métricas: Cohen's Kappa, QWK (Quadratic Weighted Kappa), F1-macro,
       MAE, sesgo (EAWS − Snowlab).

Uso:
    python notebooks_validacion/08_validacion_snowlab.py
    python notebooks_validacion/08_validacion_snowlab.py --verbose
    python notebooks_validacion/08_validacion_snowlab.py --nivel-ref max
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from google.cloud import bigquery

# ── Métricas ─────────────────────────────────────────────────────────────────
try:
    from sklearn.metrics import (
        cohen_kappa_score,
        f1_score,
        confusion_matrix,
    )
    SKLEARN = True
except ImportError:
    SKLEARN = False
    print("AVISO: sklearn no disponible — solo se calculará MAE y sesgo.")


def qwk(y_true, y_pred, n_clases=5):
    """Quadratic Weighted Kappa (1-5 → índices 0-4)."""
    y_true = np.array(y_true) - 1
    y_pred = np.array(y_pred) - 1
    n = n_clases
    W = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            W[i, j] = ((i - j) ** 2) / ((n - 1) ** 2)

    hist_true = np.bincount(y_true, minlength=n)
    hist_pred = np.bincount(y_pred, minlength=n)
    E = np.outer(hist_true, hist_pred).astype(float)
    E /= E.sum()

    O = np.zeros((n, n))
    for t, p in zip(y_true, y_pred):
        O[t, p] += 1
    O /= O.sum()

    num = (W * O).sum()
    den = (W * E).sum()
    return 1.0 - num / den if den > 0 else 0.0


GCP_PROJECT = "climas-chileno"

SQL_BOLETINES_ANDESAI = """
SELECT
    br.nombre_ubicacion,
    DATE(br.fecha_emision)  AS fecha_eaws,
    br.nivel_eaws_24h,
    br.nivel_eaws_48h,
    br.nivel_eaws_72h,
FROM `climas-chileno.clima.boletines_riesgo` br
WHERE br.nombre_ubicacion IN (
    'La Parva Sector Alto', 'La Parva Sector Medio', 'La Parva Sector Bajo'
)
  AND br.nivel_eaws_24h IS NOT NULL
  AND DATE(br.fecha_emision) >= '2024-06-01'
ORDER BY nombre_ubicacion, fecha_eaws
"""

SQL_SNOWLAB = """
SELECT
    id_boletin,
    temporada,
    fecha_publicacion,
    fecha_inicio_validez,
    fecha_fin_validez,
    nivel_alta,
    nivel_media,
    nivel_baja,
    nivel_max,
    problema_principal
FROM `climas-chileno.validacion_avalanchas.snowlab_boletines`
ORDER BY fecha_inicio_validez
"""

# Mapa sector AndesAI → columna Snowlab
MAPA_SECTOR = {
    "La Parva Sector Alto":  "nivel_alta",
    "La Parva Sector Medio": "nivel_media",
    "La Parva Sector Bajo":  "nivel_baja",
}


def cargar_datos(cliente):
    df_eaws = cliente.query(SQL_BOLETINES_ANDESAI).to_dataframe()
    df_snow = cliente.query(SQL_SNOWLAB).to_dataframe()

    # Asegurar tipo fecha
    df_eaws["fecha_eaws"] = pd.to_datetime(df_eaws["fecha_eaws"]).dt.date
    for col in ["fecha_publicacion", "fecha_inicio_validez", "fecha_fin_validez"]:
        df_snow[col] = pd.to_datetime(df_snow[col]).dt.date

    return df_eaws, df_snow


def emparejar(df_eaws, df_snow, nivel_ref: str = "banda", tolerancia_dias: int = 7):
    """
    Para cada boletín Snowlab busca el boletín AndesAI más cercano a la
    fecha de inicio de validez, dentro de `tolerancia_dias`.

    Si en la ventana [inicio-tolerancia, fin+tolerancia] hay varios AndesAI,
    se elige el de menor distancia al centro del período Snowlab.
    Un boletín AndesAI puede emparejarse con varios Snowlab distintos.

    nivel_ref:
        'banda'  → compara cada sector AndesAI contra su banda correspondiente
        'max'    → compara contra nivel_max Snowlab para todos los sectores
    """
    import datetime

    pares = []

    for _, snow in df_snow.iterrows():
        inicio = snow["fecha_inicio_validez"]
        fin = snow["fecha_fin_validez"]
        centro = inicio + datetime.timedelta(days=(fin - inicio).days // 2)

        ventana_inicio = inicio - datetime.timedelta(days=tolerancia_dias)
        ventana_fin    = fin   + datetime.timedelta(days=tolerancia_dias)

        # Un par por (Snowlab × sector), tomando el AndesAI más cercano
        for sector, col_snowlab in MAPA_SECTOR.items():
            if nivel_ref == "banda":
                nivel_snowlab = snow[col_snowlab]
                if pd.isna(nivel_snowlab):
                    continue
                nivel_snowlab = int(nivel_snowlab)
            else:
                if pd.isna(snow["nivel_max"]):
                    continue
                nivel_snowlab = int(snow["nivel_max"])

            sector_df = df_eaws[df_eaws["nombre_ubicacion"] == sector].copy()
            mask = (
                (sector_df["fecha_eaws"] >= ventana_inicio) &
                (sector_df["fecha_eaws"] <= ventana_fin)
            )
            candidatos = sector_df[mask]
            if candidatos.empty:
                continue

            # El más cercano al centro del período Snowlab
            candidatos = candidatos.copy()
            candidatos["dist"] = candidatos["fecha_eaws"].apply(
                lambda d: abs((d - centro).days)
            )
            mejor = candidatos.loc[candidatos["dist"].idxmin()]

            pares.append({
                "id_boletin_snowlab": snow["id_boletin"],
                "fecha_snowlab_inicio": inicio,
                "fecha_snowlab_fin": fin,
                "fecha_eaws": mejor["fecha_eaws"],
                "dias_diferencia": int(mejor["dist"]),
                "sector": sector,
                "nivel_andesai": int(mejor["nivel_eaws_24h"]),
                "nivel_snowlab": nivel_snowlab,
                "problema_principal": snow["problema_principal"],
            })

    return pd.DataFrame(pares)


def calcular_metricas(df_pares, verbose=False):
    if df_pares.empty:
        print("ERROR: no hay pares para calcular métricas.")
        return

    y_true = df_pares["nivel_snowlab"].tolist()
    y_pred = df_pares["nivel_andesai"].tolist()

    mae = np.mean(np.abs(np.array(y_true) - np.array(y_pred)))
    sesgo = np.mean(np.array(y_pred) - np.array(y_true))
    kappa_qw = qwk(y_true, y_pred)

    print("\n" + "=" * 60)
    print("VALIDACIÓN H4 — AndesAI vs Snowlab La Parva")
    print("=" * 60)
    dist_media = df_pares["dias_diferencia"].mean() if "dias_diferencia" in df_pares else 0
    print(f"  Pares comparados     : {len(df_pares)}")
    print(f"  Boletines Snowlab    : {df_pares['id_boletin_snowlab'].nunique()}")
    print(f"  Fechas AndesAI       : {df_pares['fecha_eaws'].nunique()}")
    print(f"  Distancia media (d)  : {dist_media:.1f} días")
    print(f"  Sectores             : {sorted(df_pares['sector'].unique())}")

    print(f"\n  MAE                  : {mae:.3f}")
    print(f"  Sesgo (EAWS−Snowlab) : {sesgo:+.3f}")
    print(f"  QWK                  : {kappa_qw:.3f}")

    if SKLEARN:
        kappa_lin = cohen_kappa_score(y_true, y_pred, weights=None)
        kappa_linw = cohen_kappa_score(y_true, y_pred, weights="linear")
        f1 = f1_score(y_true, y_pred, average="macro", zero_division=0,
                      labels=sorted(set(y_true + y_pred)))
        print(f"  Kappa lineal         : {kappa_lin:.3f}")
        print(f"  Kappa lineal ponder. : {kappa_linw:.3f}")
        print(f"  F1-macro             : {f1:.3f}")

        # Hipótesis H4
        print("\n" + "-" * 60)
        if kappa_qw >= 0.60:
            print(f"  ✓ H4 ACEPTADA  — QWK = {kappa_qw:.3f} ≥ 0.60")
        elif kappa_qw >= 0.40:
            print(f"  ⚠ H4 PARCIAL   — QWK = {kappa_qw:.3f} (acuerdo moderado, < 0.60)")
        else:
            print(f"  ✗ H4 RECHAZADA — QWK = {kappa_qw:.3f} < 0.40")
        print("-" * 60)

        # Matriz de confusión
        niveles = sorted(set(y_true + y_pred))
        cm = confusion_matrix(y_true, y_pred, labels=niveles)
        cm_df = pd.DataFrame(cm, index=[f"SL={n}" for n in niveles],
                                  columns=[f"AI={n}" for n in niveles])
        print("\n  Matriz de confusión (filas=Snowlab, cols=AndesAI):")
        print(cm_df.to_string())

    # Distribución de niveles
    print("\n  Distribución de niveles:")
    dist = pd.DataFrame({
        "Snowlab": pd.Series(y_true).value_counts().sort_index(),
        "AndesAI": pd.Series(y_pred).value_counts().sort_index(),
    }).fillna(0).astype(int)
    print(dist.to_string())

    # Por sector
    print("\n  Por sector:")
    for sector, grp in df_pares.groupby("sector"):
        mae_s = np.mean(np.abs(grp["nivel_snowlab"] - grp["nivel_andesai"]))
        sesgo_s = np.mean(grp["nivel_andesai"] - grp["nivel_snowlab"])
        qwk_s = qwk(grp["nivel_snowlab"].tolist(), grp["nivel_andesai"].tolist())
        print(f"    {sector:<30} n={len(grp):3d}  "
              f"MAE={mae_s:.2f}  sesgo={sesgo_s:+.2f}  QWK={qwk_s:.3f}")

    # Análisis de cobertura: distancia entre par y Snowlab
    if "dias_diferencia" in df_pares.columns:
        exactos  = (df_pares["dias_diferencia"] == 0).sum()
        cercanos = (df_pares["dias_diferencia"] <= 3).sum()
        print(f"\n  Cobertura de pares:")
        print(f"    Distancia = 0 días : {exactos}")
        print(f"    Distancia ≤ 3 días : {cercanos}")
        print(f"    Distancia > 3 días : {len(df_pares) - cercanos}")

    # Detectar boletines Snowlab sin cobertura AndesAI cercana (≤3 días)
    if "dias_diferencia" in df_pares.columns:
        snow_cubiertos = set(
            df_pares[df_pares["dias_diferencia"] <= 3]["id_boletin_snowlab"].unique()
        )
        snow_todos = set(df_pares["id_boletin_snowlab"].unique())
        snow_lejanos = snow_todos - snow_cubiertos
        if snow_lejanos:
            print(f"\n  AVISO — Boletines Snowlab sin AndesAI a ≤3 días ({len(snow_lejanos)}):")
            for bid in sorted(snow_lejanos):
                row = df_pares[df_pares["id_boletin_snowlab"] == bid].iloc[0]
                print(f"    {bid} ({row['fecha_snowlab_inicio']}→{row['fecha_snowlab_fin']})"
                      f" — fecha AndesAI más cercana: {row['fecha_eaws']}"
                      f" ({row['dias_diferencia']}d)")

    if verbose:
        print("\n  Pares completos:")
        print(df_pares.to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true",
                        help="Mostrar todos los pares individuales")
    parser.add_argument("--tolerancia", type=int, default=7,
                        help="Máximo de días de distancia para emparejar (default: 7)")
    parser.add_argument("--nivel-ref", choices=["banda", "max"], default="banda",
                        help="'banda' usa el nivel por elevación; 'max' usa nivel_max global")
    parser.add_argument("--exportar", type=str, default=None,
                        help="Ruta CSV para exportar los pares (ej. /tmp/pares_h4.csv)")
    args = parser.parse_args()

    cliente = bigquery.Client(project=GCP_PROJECT)

    print("Cargando datos de BigQuery...")
    df_eaws, df_snow = cargar_datos(cliente)
    print(f"  AndesAI: {len(df_eaws)} boletines")
    print(f"  Snowlab: {len(df_snow)} boletines")

    print(f"\nEmparejando (nivel_ref='{args.nivel_ref}', tolerancia={args.tolerancia}d)...")
    df_pares = emparejar(df_eaws, df_snow, nivel_ref=args.nivel_ref,
                         tolerancia_dias=args.tolerancia)
    print(f"  Pares encontrados: {len(df_pares)}")

    calcular_metricas(df_pares, verbose=args.verbose)

    if args.exportar:
        df_pares.to_csv(args.exportar, index=False)
        print(f"\n  Exportado a {args.exportar}")


if __name__ == "__main__":
    main()

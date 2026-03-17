"""
Notebook 04: Análisis de Confianza y Cobertura de Datos

Evalúa la calidad operativa del sistema multi-agente:
- % de boletines con datos completos vs parciales
- Cobertura por fuente de datos (satélite, topográfico, meteorológico, NLP)
- Trazabilidad: fuentes de gradiente PINN, tamaño EAWS, versión prompts
- Tiempos de ejecución por subagente

No vinculado directamente a una hipótesis, pero esencial para la discusión
de limitaciones en la tesina.

Requisitos:
- pip install google-cloud-bigquery
- GCP auth: gcloud auth application-default login

Uso:
    python databricks/04_confianza_cobertura.py
"""

import sys
import os
import json
import logging
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def obtener_boletines_completos(
    proyecto: str = "climas-chileno",
    dataset: str = "clima"
) -> list:
    """Obtiene todos los campos de trazabilidad desde BigQuery."""
    from google.cloud import bigquery

    cliente = bigquery.Client(project=proyecto)
    query = f"""
        SELECT
            nombre_ubicacion,
            fecha_emision,
            nivel_eaws_24h,
            nivel_eaws_48h,
            nivel_eaws_72h,
            confianza,
            arquitectura,
            estado_pinn,
            factor_seguridad_pinn,
            estado_vit,
            score_anomalia_vit,
            factor_meteorologico,
            ventanas_criticas,
            relatos_analizados,
            indice_riesgo_historico,
            tipo_alud_predominante,
            confianza_historica,
            datos_topograficos_ok,
            datos_meteorologicos_ok,
            datos_satelitales_disponibles,
            version_prompts,
            fuente_gradiente_pinn,
            fuente_tamano_eaws,
            viento_kmh,
            subagentes_ejecutados,
            duracion_por_subagente,
            duracion_segundos
        FROM `{proyecto}.{dataset}.boletines_riesgo`
        ORDER BY fecha_emision DESC
    """

    try:
        resultados = list(cliente.query(query).result())
        return [dict(row) for row in resultados]
    except Exception as e:
        logger.error(f"Error consultando boletines: {e}")
        return []


def analizar_cobertura_datos(boletines: list) -> dict:
    """Analiza qué porcentaje de boletines tiene cada tipo de dato."""
    n = len(boletines)
    if n == 0:
        return {}

    campos_cobertura = {
        "nivel_eaws_24h": "Nivel EAWS 24h",
        "nivel_eaws_48h": "Nivel EAWS 48h",
        "nivel_eaws_72h": "Nivel EAWS 72h",
        "estado_pinn": "Estado PINN",
        "factor_seguridad_pinn": "Factor seguridad PINN",
        "estado_vit": "Estado ViT",
        "score_anomalia_vit": "Score anomalía ViT",
        "factor_meteorologico": "Factor meteorológico",
        "relatos_analizados": "Relatos NLP analizados",
        "datos_topograficos_ok": "Datos topográficos OK",
        "datos_meteorologicos_ok": "Datos meteorológicos OK",
        "datos_satelitales_disponibles": "Datos satelitales disponibles",
        "fuente_gradiente_pinn": "Fuente gradiente PINN",
        "fuente_tamano_eaws": "Fuente tamaño EAWS",
        "viento_kmh": "Viento km/h",
        "version_prompts": "Versión prompts",
    }

    cobertura = {}
    for campo, descripcion in campos_cobertura.items():
        no_nulos = sum(1 for b in boletines if b.get(campo) is not None)
        cobertura[campo] = {
            "descripcion": descripcion,
            "disponibles": no_nulos,
            "total": n,
            "porcentaje": round(no_nulos / n * 100, 1),
        }

    return cobertura


def analizar_confianza(boletines: list) -> dict:
    """Analiza la distribución de confianza."""
    confianzas = Counter(b.get("confianza", "N/A") for b in boletines)
    total = len(boletines)
    return {
        nivel: {"count": count, "pct": round(count / total * 100, 1)}
        for nivel, count in confianzas.most_common()
    }


def analizar_tiempos(boletines: list) -> dict:
    """Analiza tiempos de ejecución total y por subagente."""
    duraciones_total = [
        b["duracion_segundos"]
        for b in boletines
        if b.get("duracion_segundos") is not None
    ]

    tiempos_subagente = {}
    for b in boletines:
        duracion_raw = b.get("duracion_por_subagente")
        if not duracion_raw:
            continue
        try:
            dur = json.loads(duracion_raw) if isinstance(duracion_raw, str) else duracion_raw
        except (json.JSONDecodeError, TypeError):
            continue

        for subagente, tiempo in dur.items():
            if subagente not in tiempos_subagente:
                tiempos_subagente[subagente] = []
            if isinstance(tiempo, (int, float)):
                tiempos_subagente[subagente].append(tiempo)

    resultado = {"total": {}}
    if duraciones_total:
        resultado["total"] = {
            "media": round(sum(duraciones_total) / len(duraciones_total), 1),
            "min": round(min(duraciones_total), 1),
            "max": round(max(duraciones_total), 1),
            "n": len(duraciones_total),
        }

    resultado["por_subagente"] = {}
    for sa, tiempos in tiempos_subagente.items():
        if tiempos:
            resultado["por_subagente"][sa] = {
                "media": round(sum(tiempos) / len(tiempos), 1),
                "min": round(min(tiempos), 1),
                "max": round(max(tiempos), 1),
                "n": len(tiempos),
            }

    return resultado


def analizar_trazabilidad(boletines: list) -> dict:
    """Analiza fuentes de datos y versiones."""
    fuentes_gradiente = Counter(
        b.get("fuente_gradiente_pinn", "N/A") for b in boletines
    )
    fuentes_tamano = Counter(
        b.get("fuente_tamano_eaws", "N/A") for b in boletines
    )
    versiones = Counter(
        b.get("version_prompts", "N/A") for b in boletines
    )
    arquitecturas = Counter(
        b.get("arquitectura", "N/A") for b in boletines
    )

    return {
        "fuente_gradiente_pinn": dict(fuentes_gradiente.most_common()),
        "fuente_tamano_eaws": dict(fuentes_tamano.most_common()),
        "version_prompts": dict(versiones.most_common()),
        "arquitectura": dict(arquitecturas.most_common()),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Análisis de confianza y cobertura de datos"
    )
    parser.add_argument(
        '--proyecto', default='climas-chileno',
        help='Proyecto GCP'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("NOTEBOOK 04: CONFIANZA Y COBERTURA DE DATOS")
    print(f"Fecha: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. Obtener boletines
    print("\n1. Obteniendo boletines de BigQuery...")
    boletines = obtener_boletines_completos(proyecto=args.proyecto)
    print(f"   Boletines encontrados: {len(boletines)}")

    if not boletines:
        print("\n   ⚠ No hay boletines en BigQuery.")
        print("   Ejecutar: python agentes/scripts/generar_todos.py")
        return

    # 2. Cobertura de datos
    print("\n2. Cobertura de datos por campo:")
    cobertura = analizar_cobertura_datos(boletines)
    print(f"\n   {'Campo':<35} {'Disponible':<12} {'%':<8}")
    print(f"   {'-'*55}")
    for campo, info in cobertura.items():
        barra = "█" * int(info["porcentaje"] / 5)
        print(
            f"   {info['descripcion']:<35} "
            f"{info['disponibles']}/{info['total']:<8} "
            f"{info['porcentaje']:>5.1f}% {barra}"
        )

    # Score de completitud
    scores = [info["porcentaje"] for info in cobertura.values()]
    score_medio = sum(scores) / len(scores) if scores else 0
    print(f"\n   Score de completitud medio: {score_medio:.1f}%")

    # 3. Distribución de confianza
    print("\n3. Distribución de confianza:")
    confianza = analizar_confianza(boletines)
    for nivel, info in confianza.items():
        barra = "█" * int(info["pct"] / 2.5)
        print(f"   {nivel:<10} {info['count']:>5} ({info['pct']:>5.1f}%) {barra}")

    # 4. Tiempos de ejecución
    print("\n4. Tiempos de ejecución:")
    tiempos = analizar_tiempos(boletines)
    if tiempos["total"]:
        t = tiempos["total"]
        print(f"   Total: media={t['media']}s, min={t['min']}s, max={t['max']}s (n={t['n']})")
    if tiempos["por_subagente"]:
        print(f"\n   {'Subagente':<20} {'Media (s)':<12} {'Min':<8} {'Max':<8} {'N':<6}")
        print(f"   {'-'*54}")
        for sa, t in sorted(tiempos["por_subagente"].items()):
            print(f"   {sa:<20} {t['media']:<12.1f} {t['min']:<8.1f} {t['max']:<8.1f} {t['n']:<6}")

    # 5. Trazabilidad
    print("\n5. Trazabilidad:")
    traz = analizar_trazabilidad(boletines)

    print(f"   Fuente gradiente PINN:")
    for fuente, count in traz["fuente_gradiente_pinn"].items():
        print(f"     {fuente}: {count}")

    print(f"   Fuente tamaño EAWS:")
    for fuente, count in traz["fuente_tamano_eaws"].items():
        print(f"     {fuente}: {count}")

    print(f"   Versiones de prompts:")
    for version, count in traz["version_prompts"].items():
        print(f"     {version}: {count}")

    print(f"   Arquitectura:")
    for arq, count in traz["arquitectura"].items():
        print(f"     {arq}: {count}")

    # 6. Boletines por ubicación
    print("\n6. Boletines por ubicación:")
    ubicaciones = Counter(b.get("nombre_ubicacion", "?") for b in boletines)
    for ub, count in ubicaciones.most_common():
        print(f"   {ub}: {count}")

    # 7. Resumen para tesina
    print("\n7. Resumen para la tesina:")
    n_completos = sum(
        1 for b in boletines
        if b.get("datos_topograficos_ok") and b.get("datos_meteorologicos_ok")
        and b.get("datos_satelitales_disponibles")
    )
    n_con_nlp = sum(
        1 for b in boletines
        if b.get("relatos_analizados") and b.get("relatos_analizados", 0) > 0
    )
    print(f"   Total boletines:                    {len(boletines)}")
    print(f"   Con datos completos (topo+meteo+sat): {n_completos} ({n_completos/len(boletines)*100:.1f}%)")
    print(f"   Con datos NLP:                       {n_con_nlp} ({n_con_nlp/len(boletines)*100:.1f}%)")
    print(f"   Ubicaciones únicas:                  {len(ubicaciones)}")
    print(f"   Score de completitud:                {score_medio:.1f}%")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

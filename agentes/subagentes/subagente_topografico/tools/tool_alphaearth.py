"""
Tool: analizar_embedding_alphaearth

Análisis de embeddings AlphaEarth Satellite Embeddings (64D) para la zona.

AlphaEarth (DeepMind/Google, lanzado jul 2025):
  - 64 dimensiones por píxel @10m
  - Fusiona: Sentinel-1/2, Landsat, GEDI lidar, Copernicus DEM, ERA5-Land, PALSAR-2, GRACE
  - Cobertura Chile 2017-2024, actualización anual
  - Dataset EE: GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL

Uso en S1:
  - Caracterización topográfica persistente (NO señal operacional de nieve diaria)
  - Detección de cambios interanuales: retroceso glaciar, líneas de árboles
  - Features adicionales del PINN para predicción de start zones
  - Búsqueda de similaridad entre eventos históricos

Si los datos no están en BigQuery aún, retorna {"disponible": False}.
"""

import logging
import math

from agentes.datos.consultor_bigquery import ConsultorBigQuery

logger = logging.getLogger(__name__)


TOOL_ALPHAEARTH = {
    "name": "analizar_embedding_alphaearth",
    "description": (
        "Analiza el embedding AlphaEarth de 64 dimensiones para la zona: "
        "caracterización persistente del terreno fusionando múltiples sensores "
        "(Sentinel-1/2, Landsat, GEDI lidar, ERA5-Land). "
        "Detecta cambios interanuales relevantes para peligro de avalanchas: "
        "retroceso glaciar, cambios en cobertura nieve permanente, alteraciones "
        "en start zones. Complementa el PINN como feature adicional estático. "
        "NOTA: no es señal operacional de nieve diaria (eso es S2)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación en BigQuery"
            }
        },
        "required": ["nombre_ubicacion"]
    }
}


def ejecutar_analizar_embedding_alphaearth(nombre_ubicacion: str) -> dict:
    """
    Obtiene y analiza embedding AlphaEarth para la ubicación.

    Args:
        nombre_ubicacion: nombre exacto de la ubicación en BigQuery

    Returns:
        dict con análisis del embedding, drift interanual e implicaciones EAWS
        o {"disponible": False} si datos no están en BQ
    """
    consultor = ConsultorBigQuery()
    datos = consultor.obtener_atributos_tagee_ae(nombre_ubicacion)

    if not datos.get("disponible"):
        return {
            "disponible": False,
            "ubicacion": nombre_ubicacion,
            "razon": datos.get("razon", "Embeddings AlphaEarth no disponibles"),
            "mensaje": (
                "AlphaEarth embeddings no generados. "
                "Ejecutar: python agentes/datos/backfill/actualizar_glo30_tagee_ae.py"
            ),
            "nota_uso": (
                "AlphaEarth es señal ESTÁTICA anual — caracterización "
                "persistente de terreno, no operacional de nieve diaria"
            )
        }

    embedding = datos.get("embedding_centroide_zona")
    similitud_raw = datos.get("similitud_anios_previos") or {}

    if not embedding:
        return {
            "disponible": False,
            "ubicacion": nombre_ubicacion,
            "razon": "Embedding centroide no calculado en BQ"
        }

    return {
        "disponible": True,
        "ubicacion": nombre_ubicacion,
        "embedding_dimensiones": len(embedding) if isinstance(embedding, list) else "desconocido",
        "norma_l2": _calcular_norma(embedding),
        "drift_interanual": _analizar_drift(similitud_raw),
        "cambios_detectados": _interpretar_cambios(similitud_raw),
        "implicaciones_eaws": _implicaciones_para_eaws(similitud_raw),
        "nota_uso": (
            "Señal ESTÁTICA anual — caracterización persistente de terreno. "
            "No usar como indicador de condiciones de nieve del día actual."
        )
    }


def _calcular_norma(embedding: list) -> float | None:
    """Norma L2 del embedding centroide."""
    if not embedding or not isinstance(embedding, list):
        return None
    try:
        return round(math.sqrt(sum(x * x for x in embedding)), 4)
    except (TypeError, ValueError):
        return None


def _analizar_drift(similitud_raw: dict) -> dict:
    """
    Analiza el drift interanual del embedding.

    similitud_raw: {año: similitud_coseno_vs_año_anterior}
    """
    if not similitud_raw:
        return {"disponible": False, "razon": "Sin datos de similitud interanual"}

    similitudes = {}
    for k, v in similitud_raw.items():
        try:
            similitudes[str(k)] = float(v)
        except (ValueError, TypeError):
            pass

    if not similitudes:
        return {"disponible": False}

    valores = list(similitudes.values())
    drift_max = round(1.0 - min(valores), 4)
    drift_promedio = round(1.0 - (sum(valores) / len(valores)), 4)

    # Año con mayor cambio
    anio_mayor_cambio = min(similitudes, key=similitudes.get)

    return {
        "disponible": True,
        "drift_maximo": drift_max,
        "drift_promedio": drift_promedio,
        "anio_mayor_cambio": anio_mayor_cambio,
        "similitudes_anuales": similitudes,
        "tendencia": _clasificar_tendencia_drift(drift_promedio),
    }


def _clasificar_tendencia_drift(drift_promedio: float) -> str:
    """Clasifica la tendencia de cambio del terreno."""
    if drift_promedio < 0.02:
        return "terreno_estable_sin_cambios_significativos"
    elif drift_promedio < 0.05:
        return "cambios_menores_posible_variacion_estacional"
    elif drift_promedio < 0.10:
        return "cambios_moderados_verificar_con_imagenes"
    else:
        return "cambios_significativos_posible_alteracion_start_zones"


def _interpretar_cambios(similitud_raw: dict) -> list[str]:
    """Interpreta cambios detectables en el embedding para EAWS."""
    cambios = []
    if not similitud_raw:
        return ["Sin datos de cambio disponibles"]

    for anio, sim in sorted(similitud_raw.items()):
        try:
            drift = 1.0 - float(sim)
            if drift > 0.10:
                cambios.append(f"Año {anio}: cambio significativo (drift={drift:.3f}) — posible alteración glaciar o cobertura")
            elif drift > 0.05:
                cambios.append(f"Año {anio}: cambio moderado (drift={drift:.3f})")
        except (ValueError, TypeError):
            pass

    if not cambios:
        cambios.append("Sin cambios significativos en el período analizado")
    return cambios


def _implicaciones_para_eaws(similitud_raw: dict) -> list[str]:
    """Genera implicaciones directas para el análisis EAWS."""
    impl = []
    if not similitud_raw:
        impl.append("Sin datos AlphaEarth para análisis EAWS — usar solo topografía convencional")
        return impl

    valores = []
    for v in similitud_raw.values():
        try:
            valores.append(float(v))
        except (ValueError, TypeError):
            pass

    if not valores:
        return ["Sin datos válidos de drift"]

    drift_max = 1.0 - min(valores)
    if drift_max > 0.10:
        impl.append("CAMBIO_TERRENO_SIGNIFICATIVO: re-evaluar polígonos de start zones históricos")
    if drift_max > 0.05:
        impl.append("MONITOREO_RECOMENDADO: verificar con imágenes satelitales recientes")
    if drift_max < 0.03:
        impl.append("Terreno estable: polígonos históricos siguen siendo válidos")

    return impl or ["Implicaciones menores para análisis EAWS"]

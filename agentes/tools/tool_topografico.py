"""
Tool 1: Análisis de Terreno Topográfico

Obtiene el perfil topográfico de una ubicación basado en datos SRTM
y el análisis de zonas de avalancha almacenado en BigQuery.

Nombre de la tool: analizar_terreno
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# DEFINICIÓN DE LA TOOL PARA ANTHROPIC
# =============================================================================

TOOL_TOPOGRAFICO = {
    "name": "analizar_terreno",
    "description": (
        "Obtiene el perfil topográfico: zonas de avalancha, pendientes críticas, "
        "aspecto, desnivel e índice de riesgo base EAWS basado en datos SRTM. "
        "Usar SIEMPRE como primer paso."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación"
            }
        },
        "required": ["nombre_ubicacion"]
    }
}


# =============================================================================
# FUNCIÓN EJECUTORA
# =============================================================================

def ejecutar_analizar_terreno(consultor: Any, nombre_ubicacion: str) -> dict:
    """
    Ejecuta el análisis topográfico para una ubicación.

    Args:
        consultor: Instancia de ConsultorBigQuery
        nombre_ubicacion: Nombre exacto de la ubicación a analizar

    Returns:
        dict con perfil topográfico e interpretaciones automáticas
    """
    logger.info(f"[tool_topografico] Analizando terreno para: {nombre_ubicacion}")

    resultado = consultor.obtener_perfil_topografico(nombre_ubicacion)

    if resultado.get("error"):
        logger.error(f"[tool_topografico] Error al obtener perfil: {resultado['error']}")
        return resultado

    if not resultado.get("disponible"):
        logger.warning(f"[tool_topografico] Sin datos topográficos para: {nombre_ubicacion}")
        return resultado

    # Agregar interpretaciones automáticas
    interpretaciones = []

    clasificacion = resultado.get("clasificacion_riesgo", "")
    if clasificacion == "extremo":
        interpretaciones.append("⚠️ Terreno extremadamente susceptible")

    es_sombra = resultado.get("es_aspecto_sombra")
    if es_sombra:
        interpretaciones.append(
            "Orientación sombra: favorece capas débiles persistentes"
        )

    desnivel = resultado.get("desnivel_inicio_deposito", 0)
    if desnivel and desnivel > 600:
        interpretaciones.append(
            f"Desnivel alto ({desnivel}m): potencial avalancha tamaño 3+"
        )

    pendiente_max = resultado.get("pendiente_max_inicio", 0)
    if pendiente_max and pendiente_max > 45:
        interpretaciones.append(
            f"Pendiente máxima extrema: {pendiente_max}° — zona de liberación severa"
        )

    zona_inicio_pct = resultado.get("zona_inicio_pct", 0)
    if zona_inicio_pct and zona_inicio_pct > 30:
        interpretaciones.append(
            f"Alta proporción de zona de inicio ({zona_inicio_pct:.1f}%): "
            "múltiples puntos de liberación posibles"
        )

    resultado["interpretaciones"] = interpretaciones
    resultado["ubicacion_consultada"] = nombre_ubicacion

    logger.info(
        f"[tool_topografico] Perfil obtenido — "
        f"índice riesgo: {resultado.get('indice_riesgo_topografico')}, "
        f"clasificación: {clasificacion}, "
        f"{len(interpretaciones)} interpretaciones"
    )

    return resultado

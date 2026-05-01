"""
Tool: obtener_historial_ubicacion

Consulta el historial de boletines propios de la ubicación para calcular
features de persistencia temporal. Permite a S5 distinguir "calma sostenida"
(varios días consecutivos nivel ≤ 2 sin precipitación) de "calma puntual".

Si dias_consecutivos_nivel_bajo ≥ 4 y el factor meteorológico es ESTABLE,
S5 puede confirmar condiciones tranquilas con mayor confianza y evitar
el piso artificial en nivel 3.
"""

import logging
import os
import sys

_ROOT = os.path.join(os.path.dirname(__file__), '../../../..')
sys.path.insert(0, _ROOT)

from agentes.datos.consultor_bigquery import ConsultorBigQuery

logger = logging.getLogger(__name__)


TOOL_HISTORIAL_UBICACION = {
    "name": "obtener_historial_ubicacion",
    "description": (
        "Consulta el historial de boletines propios de la ubicación en los últimos 7 días. "
        "Retorna features de persistencia temporal: días consecutivos con nivel ≤ 2, "
        "nivel promedio, tendencia reciente y lista de boletines. "
        "Llamar SIEMPRE como primera tool antes de clasificar_riesgo_eaws_integrado. "
        "Si dias_consecutivos_nivel_bajo ≥ 4 y el factor meteorológico es ESTABLE, "
        "las condiciones de calma están confirmadas — usar estabilidad máx. 'fair'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación (ej: 'La Parva Sector Bajo')"
            },
            "n_dias": {
                "type": "integer",
                "description": "Ventana temporal en días hacia atrás (default: 7)",
                "default": 7
            }
        },
        "required": ["ubicacion"]
    }
}


def ejecutar_obtener_historial_ubicacion(
    ubicacion: str,
    n_dias: int = 7,
) -> dict:
    """
    Consulta el historial de boletines y calcula features de persistencia.

    Returns:
        dict con:
        - dias_consecutivos_nivel_bajo: int — días seguidos con nivel ≤ 2 (desde hoy hacia atrás)
        - nivel_promedio_7d: float | None — promedio de niveles en la ventana
        - tendencia_historica: int — nivel_más_reciente - nivel_más_antiguo (negativo = bajando)
        - n_boletines: int — boletines encontrados en la ventana
        - sin_historial: bool — True si no hay boletines previos (primera ejecución)
        - calma_confirmada: bool — True si dias_consecutivos_nivel_bajo ≥ 4
        - boletines: lista de los últimos boletines con fecha/nivel/factor
    """
    consultor = ConsultorBigQuery()
    resultado = consultor.obtener_historial_boletines(ubicacion=ubicacion, n_dias=n_dias)

    if not resultado.get("disponible", False):
        logger.warning(
            f"[HistorialUbicacion] Error consultando historial de '{ubicacion}': "
            f"{resultado.get('razon', 'desconocido')}"
        )
        return {
            "dias_consecutivos_nivel_bajo": 0,
            "nivel_promedio_7d": None,
            "tendencia_historica": 0,
            "n_boletines": 0,
            "sin_historial": True,
            "calma_confirmada": False,
            "boletines": [],
            "error": resultado.get("razon"),
        }

    dias_bajos = resultado["dias_consecutivos_nivel_bajo"]
    calma_confirmada = dias_bajos >= 4

    logger.info(
        f"[HistorialUbicacion] '{ubicacion}': {resultado['n_boletines']} boletines, "
        f"días nivel≤2 consecutivos={dias_bajos}, "
        f"nivel_promedio={resultado['nivel_promedio_7d']}, "
        f"calma_confirmada={calma_confirmada}"
    )

    return {
        "dias_consecutivos_nivel_bajo": dias_bajos,
        "nivel_promedio_7d": resultado["nivel_promedio_7d"],
        "tendencia_historica": resultado["tendencia_historica"],
        "n_boletines": resultado["n_boletines"],
        "sin_historial": resultado.get("sin_historial", False),
        "calma_confirmada": calma_confirmada,
        "boletines": resultado["boletines"][:5],  # máx 5 para no saturar el contexto LLM
    }

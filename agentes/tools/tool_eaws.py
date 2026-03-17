"""
Tool 4: Clasificación de Riesgo EAWS

Consulta la matriz EAWS para obtener el nivel de peligro (1-5) dados
los tres factores: estabilidad, frecuencia y tamaño potencial.

Importa directamente desde analizador_avalanchas/eaws_constantes.py
sin duplicar la matriz.

Nombre de la tool: clasificar_riesgo_eaws
"""

import sys
import os
import logging

# Importar desde el módulo existente sin duplicar lógica
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../analizador_avalanchas'))
from eaws_constantes import consultar_matriz_eaws, NIVELES_PELIGRO  # noqa: E402

logger = logging.getLogger(__name__)


# =============================================================================
# DEFINICIÓN DE LA TOOL PARA ANTHROPIC
# =============================================================================

TOOL_EAWS = {
    "name": "clasificar_riesgo_eaws",
    "description": (
        "Consulta la matriz EAWS para obtener el nivel de peligro (1-5) dados "
        "los tres factores: estabilidad, frecuencia y tamaño potencial. "
        "Usar como último paso."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "estabilidad": {
                "type": "string",
                "enum": ["very_poor", "poor", "fair", "good"],
                "description": (
                    "Clase de estabilidad del manto nival: "
                    "very_poor=muy inestable, poor=inestable, "
                    "fair=moderado, good=estable"
                )
            },
            "frecuencia": {
                "type": "string",
                "enum": ["many", "some", "a_few", "nearly_none"],
                "description": (
                    "Frecuencia de puntos inestables: "
                    "many=>30%, some=10-30%, a_few=3-10%, nearly_none=<3%"
                )
            },
            "tamano": {
                "type": "integer",
                "description": (
                    "Tamaño potencial de avalancha (1-5): "
                    "1=pequeña, 2=mediana, 3=grande, 4=muy grande, 5=extrema"
                )
            }
        },
        "required": ["estabilidad", "frecuencia", "tamano"]
    }
}


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def _generar_recomendaciones(nivel: int) -> str:
    """
    Genera recomendaciones específicas según el nivel EAWS para los Andes chilenos.

    Args:
        nivel: Nivel de peligro EAWS (1-5)

    Returns:
        str: Recomendaciones en español
    """
    recomendaciones = {
        1: (
            "Condiciones generalmente seguras. "
            "Precaución en terreno muy empinado (>45°) y trampas de terreno."
        ),
        2: (
            "Atención en pendientes pronunciadas. "
            "Evitar terreno empinado con capas débiles. "
            "Elegir rutas con exposición mínima en aspectos de sombra."
        ),
        3: (
            "Peligro considerable. Evaluar cuidadosamente el terreno. "
            "Reducir exposición en pendientes >35°. "
            "Solo expertos con conocimiento local. "
            "Evitar terreno bajo cornisas y zonas de depósito."
        ),
        4: (
            "Peligro alto. Solo expertos en terreno específico y "
            "con condiciones favorables confirmadas. "
            "Evitar viaje a alta montaña sin información local actualizada. "
            "No pasar bajo pendientes críticas."
        ),
        5: (
            "Peligro muy alto. Evitar todo terreno de avalanchas. "
            "Restricción de acceso a alta montaña recomendada. "
            "Riesgo de avalanchas espontáneas de gran tamaño en múltiples aspectos."
        )
    }
    return recomendaciones.get(nivel, "Nivel desconocido")


# =============================================================================
# FUNCIÓN EJECUTORA
# =============================================================================

def ejecutar_clasificar_eaws(estabilidad: str, frecuencia: str, tamano: int) -> dict:
    """
    Clasifica el nivel de riesgo EAWS según los tres factores.

    Args:
        estabilidad: Clase de estabilidad ('very_poor', 'poor', 'fair', 'good')
        frecuencia: Clase de frecuencia ('many', 'some', 'a_few', 'nearly_none')
        tamano: Tamaño potencial de avalancha (1-5)

    Returns:
        dict con niveles de peligro 24h/48h/72h y recomendaciones
    """
    logger.info(
        f"[tool_eaws] Clasificando EAWS — "
        f"estabilidad={estabilidad}, frecuencia={frecuencia}, tamaño={tamano}"
    )

    try:
        # Validar entradas
        if estabilidad not in ["very_poor", "poor", "fair", "good"]:
            return {"error": f"Estabilidad inválida: {estabilidad}"}
        if frecuencia not in ["many", "some", "a_few", "nearly_none"]:
            return {"error": f"Frecuencia inválida: {frecuencia}"}
        if tamano not in [1, 2, 3, 4, 5]:
            return {"error": f"Tamaño inválido: {tamano} (debe ser 1-5)"}

        # Consultar matriz EAWS
        d1, d2 = consultar_matriz_eaws(estabilidad, frecuencia, tamano)
        nivel_info = NIVELES_PELIGRO[d1]

        resultado = {
            "nivel_24h": d1,
            "nombre_nivel_24h": nivel_info["nombre"],
            "nivel_48h": min(d1 + 1, 5),
            "nivel_72h": min(d1 + 1, 5),
            "nivel_alternativo": d2,
            "descripcion": nivel_info["descripcion"],
            "recomendaciones": _generar_recomendaciones(d1),
            "factores_usados": {
                "estabilidad": estabilidad,
                "frecuencia": frecuencia,
                "tamano": tamano
            }
        }

        logger.info(
            f"[tool_eaws] Clasificación completada — "
            f"nivel 24h: {d1} ({nivel_info['nombre']}), "
            f"nivel 48/72h: {min(d1 + 1, 5)}, "
            f"alternativo: {d2}"
        )

        return resultado

    except KeyError as e:
        logger.error(f"[tool_eaws] Error en consulta de matriz: {e}")
        return {"error": f"Parámetro inválido para la matriz EAWS: {e}"}
    except Exception as e:
        logger.error(f"[tool_eaws] Error inesperado: {e}")
        return {"error": str(e)}

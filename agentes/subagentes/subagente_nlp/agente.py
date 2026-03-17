"""
Subagente NLP — Análisis de Relatos Históricos de Montañistas.

Consulta la tabla BigQuery clima.relatos_montanistas (Andeshandbook)
para extraer conocimiento experto comunitario sobre condiciones de
riesgo históricas en cada ubicación.
"""

from agentes.subagentes.base_subagente import BaseSubagente
from agentes.subagentes.subagente_nlp.prompts import SYSTEM_PROMPT_NLP
from agentes.subagentes.subagente_nlp.tools.tool_buscar_relatos import (
    TOOL_BUSCAR_RELATOS, ejecutar_buscar_relatos
)
from agentes.subagentes.subagente_nlp.tools.tool_extraer_patrones import (
    TOOL_EXTRAER_PATRONES, ejecutar_extraer_patrones
)
from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
    TOOL_CONOCIMIENTO_HISTORICO, ejecutar_sintetizar_conocimiento_historico
)


class SubagenteNLP(BaseSubagente):
    """
    Subagente especializado en análisis NLP de relatos históricos.

    Pipeline:
    1. Buscar relatos para la ubicación (buscar_relatos_ubicacion)
    2. Extraer patrones de riesgo por términos EAWS (extraer_patrones_riesgo)
    3. Sintetizar conocimiento histórico (sintetizar_conocimiento_historico)

    Si la tabla relatos_montanistas no existe o está vacía,
    retorna confianza Baja sin fallar.
    """

    NOMBRE = "SubagenteNLP"
    MODELO = "claude-sonnet-4-5"
    MAX_TOKENS = 4096
    MAX_ITERACIONES = 6

    def _cargar_tools(self) -> list:
        return [
            TOOL_BUSCAR_RELATOS,
            TOOL_EXTRAER_PATRONES,
            TOOL_CONOCIMIENTO_HISTORICO,
        ]

    def _cargar_ejecutores(self) -> dict:
        return {
            "buscar_relatos_ubicacion": ejecutar_buscar_relatos,
            "extraer_patrones_riesgo": ejecutar_extraer_patrones,
            "sintetizar_conocimiento_historico": ejecutar_sintetizar_conocimiento_historico,
        }

    def _obtener_system_prompt(self) -> str:
        return SYSTEM_PROMPT_NLP

"""
AgenteSituationalBriefing (S4 v2) — Reemplazo del SubagenteNLP.

Genera un Situational Briefing estructurado usando Qwen3-80B vía Databricks
(mismo endpoint gratuito que S5). Hereda BaseSubagente: usa el agentic loop
estándar donde el LLM llama las 4 tools y luego produce el briefing en texto.

Interfaz pública:
    ejecutar(nombre_ubicacion, contexto_previo) → dict compatible con orquestador
"""

from pathlib import Path

from agentes.subagentes.base_subagente import BaseSubagente
from agentes.subagentes.subagente_situational_briefing.tools.tool_clima_reciente import (
    TOOL_CLIMA_RECIENTE,
    ejecutar_obtener_clima_reciente_72h,
)
from agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico import (
    TOOL_CONTEXTO_HISTORICO,
    ejecutar_obtener_contexto_historico,
)
from agentes.subagentes.subagente_situational_briefing.tools.tool_caracteristicas_zona import (
    TOOL_CARACTERISTICAS_ZONA,
    ejecutar_obtener_caracteristicas_zona,
)
from agentes.subagentes.subagente_situational_briefing.tools.tool_eventos_pasados import (
    TOOL_EVENTOS_PASADOS,
    ejecutar_obtener_eventos_pasados,
)


class AgenteSituationalBriefing(BaseSubagente):
    """
    S4 v2: Genera situational briefings usando Qwen3-80B vía Databricks.

    El agentic loop llama las 4 tools (clima, contexto histórico, topografía,
    eventos pasados) y luego sintetiza un briefing estructurado con los campos
    de compatibilidad que S5 espera.
    """

    NOMBRE = "AgenteSituationalBriefing"
    MODELO = "databricks-qwen3-next-80b-a3b-instruct"
    PROVEEDOR = "databricks"
    MAX_TOKENS = 4096
    MAX_ITERACIONES = 8

    def _cargar_tools(self) -> list:
        return [
            TOOL_CLIMA_RECIENTE,
            TOOL_CONTEXTO_HISTORICO,
            TOOL_CARACTERISTICAS_ZONA,
            TOOL_EVENTOS_PASADOS,
        ]

    def _cargar_ejecutores(self) -> dict:
        return {
            "obtener_clima_reciente_72h": ejecutar_obtener_clima_reciente_72h,
            "obtener_contexto_historico": ejecutar_obtener_contexto_historico,
            "obtener_caracteristicas_zona": ejecutar_obtener_caracteristicas_zona,
            "obtener_eventos_pasados": ejecutar_obtener_eventos_pasados,
        }

    def _obtener_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent / "prompts" / "system_prompt.md"
        try:
            return prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (
                "Eres un experto en nivología andina. Genera situational briefings "
                "factuales en español de Chile para el sistema AndesAI EAWS. "
                "Usa todas tus tools, luego produce el briefing con los metadatos "
                "de compatibilidad S5 requeridos."
            )

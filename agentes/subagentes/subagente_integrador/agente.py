"""
Subagente Integrador EAWS.

Integra los análisis de los tres subagentes anteriores para generar
el boletín EAWS final:
- Clasificación EAWS (niveles 1-5) para 24h/48h/72h
- Explicación detallada de factores de riesgo
- Boletín completo en formato EAWS español
"""

from agentes.subagentes.base_subagente import BaseSubagente
from agentes.subagentes.subagente_integrador.prompts import SYSTEM_PROMPT_INTEGRADOR
from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
    TOOL_CLASIFICAR_EAWS_INTEGRADO, ejecutar_clasificar_riesgo_eaws_integrado
)
from agentes.subagentes.subagente_integrador.tools.tool_generar_boletin import (
    TOOL_GENERAR_BOLETIN, ejecutar_redactar_boletin_eaws
)
from agentes.subagentes.subagente_integrador.tools.tool_explicar_factores import (
    TOOL_EXPLICAR_FACTORES, ejecutar_explicar_factores_riesgo
)


class SubagenteIntegrador(BaseSubagente):
    """
    Subagente especializado en integración EAWS y generación de boletines.

    Combina los análisis de los tres subagentes para:
    1. Clasificar el riesgo EAWS final (matrix lookup)
    2. Explicar los factores determinantes del riesgo
    3. Redactar el boletín EAWS completo en español
    """

    NOMBRE = "SubagenteIntegrador"
    MODELO = "databricks-qwen3-next-80b-a3b-instruct"  # transitorio: Anthropic cuando ANTHROPIC_API_KEY esté disponible
    MAX_TOKENS = 6144  # Más tokens para el boletín completo
    MAX_ITERACIONES = 6

    def _cargar_tools(self) -> list:
        return [
            TOOL_CLASIFICAR_EAWS_INTEGRADO,
            TOOL_EXPLICAR_FACTORES,
            TOOL_GENERAR_BOLETIN,
        ]

    def _cargar_ejecutores(self) -> dict:
        return {
            "clasificar_riesgo_eaws_integrado": ejecutar_clasificar_riesgo_eaws_integrado,
            "explicar_factores_riesgo": ejecutar_explicar_factores_riesgo,
            "redactar_boletin_eaws": ejecutar_redactar_boletin_eaws,
        }

    def _obtener_system_prompt(self) -> str:
        return SYSTEM_PROMPT_INTEGRADOR

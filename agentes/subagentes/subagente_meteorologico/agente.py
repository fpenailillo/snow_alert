"""
Subagente Meteorológico (v2).

Analiza condiciones climáticas y detecta ventanas de riesgo usando:
- Condiciones actuales desde BigQuery condiciones_actuales
- Tendencia de 72h (historial 24h + pronóstico horario si disponible)
- Pronóstico de días desde BigQuery pronostico_dias
- Detección de ventanas críticas: nevada+viento, fusión, lluvia sobre nieve
- Pronóstico ensemble multi-fuente (WeatherNext 2 cuando USE_WEATHERNEXT2=true)
"""

from agentes.subagentes.base_subagente import BaseSubagente
from agentes.subagentes.subagente_meteorologico.prompts import SYSTEM_PROMPT_METEOROLOGICO
from agentes.subagentes.subagente_meteorologico.tools.tool_condiciones_actuales import (
    TOOL_CONDICIONES_ACTUALES_METEO,
    ejecutar_obtener_condiciones_actuales_meteo
)
from agentes.subagentes.subagente_meteorologico.tools.tool_tendencia_72h import (
    TOOL_TENDENCIA_72H, ejecutar_analizar_tendencia_72h
)
from agentes.subagentes.subagente_meteorologico.tools.tool_pronostico_dias import (
    TOOL_PRONOSTICO_DIAS, ejecutar_obtener_pronostico_dias
)
from agentes.subagentes.subagente_meteorologico.tools.tool_ventanas_criticas import (
    TOOL_VENTANAS_CRITICAS, ejecutar_detectar_ventanas_criticas
)
from agentes.subagentes.subagente_meteorologico.tools.tool_pronostico_ensemble import (
    TOOL_PRONOSTICO_ENSEMBLE, ejecutar_obtener_pronostico_ensemble
)


class SubagenteMeteorologico(BaseSubagente):
    """
    Subagente especializado en análisis meteorológico.

    Usa datos de BigQuery para:
    1. Obtener condiciones actuales y evaluar alertas inmediatas
    2. Analizar tendencia de 72h y ciclos temperatura
    3. Revisar pronóstico de días próximos
    4. Detectar ventanas críticas para avalanchas
    5. (Opcional) Pronóstico ensemble multi-fuente con percentiles WN2
    """

    NOMBRE = "SubagenteMeteorologico"
    MODELO = "claude-sonnet-4-5"
    MAX_TOKENS = 4096
    MAX_ITERACIONES = 8

    def _cargar_tools(self) -> list:
        return [
            TOOL_CONDICIONES_ACTUALES_METEO,
            TOOL_TENDENCIA_72H,
            TOOL_PRONOSTICO_DIAS,
            TOOL_VENTANAS_CRITICAS,
            TOOL_PRONOSTICO_ENSEMBLE,  # Nueva — multi-fuente con WN2
        ]

    def _cargar_ejecutores(self) -> dict:
        return {
            "obtener_condiciones_actuales_meteo": ejecutar_obtener_condiciones_actuales_meteo,
            "analizar_tendencia_72h": ejecutar_analizar_tendencia_72h,
            "obtener_pronostico_dias": ejecutar_obtener_pronostico_dias,
            "detectar_ventanas_criticas": ejecutar_detectar_ventanas_criticas,
            "obtener_pronostico_ensemble": ejecutar_obtener_pronostico_ensemble,
        }

    def _obtener_system_prompt(self) -> str:
        return SYSTEM_PROMPT_METEOROLOGICO

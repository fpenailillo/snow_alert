"""
Subagente Satelital con Vision Transformers (ViT).

Analiza la evolución temporal del manto nival usando:
- Imágenes satelitales (GOES, MODIS, ERA5) desde BigQuery imagenes_satelitales
- ViT (self-attention) para detectar patrones temporales críticos
- Detección de anomalías: nevada, fusión, nieve húmeda, transporte eólico
- Estimación de snowline y área nival activa
"""

from agentes.subagentes.base_subagente import BaseSubagente
from agentes.subagentes.subagente_satelital.prompts import SYSTEM_PROMPT_SATELITAL
from agentes.subagentes.subagente_satelital.tools.tool_procesar_ndsi import (
    TOOL_PROCESAR_NDSI, ejecutar_procesar_ndsi
)
from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
    TOOL_ANALIZAR_VIT, ejecutar_analizar_vit
)
from agentes.subagentes.subagente_satelital.tools.tool_detectar_anomalias import (
    TOOL_DETECTAR_ANOMALIAS, ejecutar_detectar_anomalias_satelitales
)
from agentes.subagentes.subagente_satelital.tools.tool_snowline import (
    TOOL_SNOWLINE, ejecutar_calcular_snowline
)


class SubagenteSatelital(BaseSubagente):
    """
    Subagente especializado en análisis satelital y ViT.

    Usa imágenes satelitales de BigQuery para:
    1. Procesar serie temporal NDSI y métricas satelitales
    2. Aplicar ViT (self-attention) para detectar patrones críticos
    3. Clasificar anomalías del manto nival superficial
    4. Estimar snowline y área nival activa para avalanchas
    """

    NOMBRE = "SubagenteSatelital"
    MODELO = "claude-sonnet-4-5"
    MAX_TOKENS = 4096
    MAX_ITERACIONES = 8

    def _cargar_tools(self) -> list:
        return [
            TOOL_PROCESAR_NDSI,
            TOOL_ANALIZAR_VIT,
            TOOL_DETECTAR_ANOMALIAS,
            TOOL_SNOWLINE,
        ]

    def _cargar_ejecutores(self) -> dict:
        return {
            "procesar_ndsi": ejecutar_procesar_ndsi,
            "analizar_vit": ejecutar_analizar_vit,
            "detectar_anomalias_satelitales": ejecutar_detectar_anomalias_satelitales,
            "calcular_snowline": ejecutar_calcular_snowline,
        }

    def _obtener_system_prompt(self) -> str:
        return SYSTEM_PROMPT_SATELITAL

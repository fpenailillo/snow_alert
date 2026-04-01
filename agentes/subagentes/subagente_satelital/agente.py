"""
Subagente Satelital con Vision Transformers (ViT) + vía Earth AI paralela.

Analiza la evolución temporal del manto nival usando:
- Imágenes satelitales (GOES, MODIS, ERA5) desde BigQuery imagenes_satelitales
- ViT (self-attention) para detectar patrones temporales críticos
- Detección de anomalías: nevada, fusión, nieve húmeda, transporte eólico
- Estimación de snowline y área nival activa

Vía Earth AI (paralela, A/B):
- Activa cuando S2_VIA != "vit_actual"
- Razonamiento cualitativo multi-spectral (Qwen3-80B/Databricks)
- Comparador persiste métricas en BQ para análisis de tesis

Flag de control:
  S2_VIA=vit_actual          → solo ViT (default, sin cambios)
  S2_VIA=ambas_consolidar_vit → ambas vías, S5 recibe ViT
  S2_VIA=ambas_consolidar_ea  → ambas vías, S5 recibe Earth AI
  S2_VIA=earth_ai             → solo Earth AI
"""

import os

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
from agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral import (
    TOOL_GEMINI_MULTISPECTRAL, ejecutar_analizar_via_earth_ai
)

_S2_VIA = os.environ.get("S2_VIA", "vit_actual")


class SubagenteSatelital(BaseSubagente):
    """
    Subagente especializado en análisis satelital y ViT.

    Usa imágenes satelitales de BigQuery para:
    1. Procesar serie temporal NDSI y métricas satelitales
    2. Aplicar ViT (self-attention) para detectar patrones críticos
    3. Clasificar anomalías del manto nival superficial
    4. Estimar snowline y área nival activa para avalanchas
    5. (Cuando S2_VIA != vit_actual) Razonamiento multi-spectral vía Earth AI
    """

    NOMBRE = "SubagenteSatelital"
    MODELO = "claude-sonnet-4-5"
    MAX_TOKENS = 4096
    MAX_ITERACIONES = 10

    def _cargar_tools(self) -> list:
        return [
            TOOL_PROCESAR_NDSI,
            TOOL_ANALIZAR_VIT,
            TOOL_DETECTAR_ANOMALIAS,
            TOOL_SNOWLINE,
            TOOL_GEMINI_MULTISPECTRAL,
        ]

    def _cargar_ejecutores(self) -> dict:
        return {
            "procesar_ndsi": ejecutar_procesar_ndsi,
            "analizar_vit": ejecutar_analizar_vit,
            "detectar_anomalias_satelitales": ejecutar_detectar_anomalias_satelitales,
            "calcular_snowline": ejecutar_calcular_snowline,
            "analizar_via_earth_ai": ejecutar_analizar_via_earth_ai,
        }

    def _obtener_system_prompt(self) -> str:
        return SYSTEM_PROMPT_SATELITAL

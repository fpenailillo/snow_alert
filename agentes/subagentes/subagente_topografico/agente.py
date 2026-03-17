"""
Subagente Topográfico con Physics-Informed Neural Networks (PINNs).

Analiza el terreno montañoso y el estado del manto nival usando:
- DEM (Digital Elevation Model) desde BigQuery zonas_avalancha
- PINNs para modelar dinámica física del manto (sin GPU)
- Criterio de Mohr-Coulomb para evaluación de estabilidad
"""

from agentes.subagentes.base_subagente import BaseSubagente
from agentes.subagentes.subagente_topografico.prompts import SYSTEM_PROMPT_TOPOGRAFICO
from agentes.subagentes.subagente_topografico.tools.tool_analizar_dem import (
    TOOL_ANALIZAR_DEM, ejecutar_analizar_dem
)
from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
    TOOL_CALCULAR_PINN, ejecutar_calcular_pinn
)
from agentes.subagentes.subagente_topografico.tools.tool_zonas_riesgo import (
    TOOL_ZONAS_RIESGO, ejecutar_identificar_zonas_riesgo
)
from agentes.subagentes.subagente_topografico.tools.tool_estabilidad_manto import (
    TOOL_ESTABILIDAD_MANTO, ejecutar_evaluar_estabilidad_manto
)


class SubagenteTopografico(BaseSubagente):
    """
    Subagente especializado en análisis topográfico y PINNs.

    Usa el perfil DEM de BigQuery para:
    1. Obtener geometría del terreno (zonas de inicio/tránsito/depósito)
    2. Ejecutar PINN para modelar dinámica física del manto
    3. Identificar zonas de mayor riesgo geomorfológico
    4. Clasificar estabilidad EAWS del manto
    """

    NOMBRE = "SubagenteTopografico"
    MODELO = "claude-sonnet-4-5"
    MAX_TOKENS = 4096
    MAX_ITERACIONES = 8

    def _cargar_tools(self) -> list:
        return [
            TOOL_ANALIZAR_DEM,
            TOOL_CALCULAR_PINN,
            TOOL_ZONAS_RIESGO,
            TOOL_ESTABILIDAD_MANTO,
        ]

    def _cargar_ejecutores(self) -> dict:
        return {
            "analizar_dem": ejecutar_analizar_dem,
            "calcular_pinn": ejecutar_calcular_pinn,
            "identificar_zonas_riesgo": ejecutar_identificar_zonas_riesgo,
            "evaluar_estabilidad_manto": ejecutar_evaluar_estabilidad_manto,
        }

    def _obtener_system_prompt(self) -> str:
        return SYSTEM_PROMPT_TOPOGRAFICO

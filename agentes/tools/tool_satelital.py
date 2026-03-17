"""
Tool 2: Monitoreo del Estado del Manto Nival

Obtiene el estado actual del manto nival desde imágenes satelitales:
cobertura de nieve, temperatura superficial, cambios recientes,
nieve húmeda (SAR) y snowline.

Nombre de la tool: monitorear_nieve
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# DEFINICIÓN DE LA TOOL PARA ANTHROPIC
# =============================================================================

TOOL_SATELITAL = {
    "name": "monitorear_nieve",
    "description": (
        "Obtiene el estado actual del manto nival desde imágenes satelitales: "
        "cobertura de nieve, temperatura superficial, cambios recientes, "
        "nieve húmeda (SAR) y snowline. Usar como segundo paso."
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

def ejecutar_monitorear_nieve(consultor: Any, nombre_ubicacion: str) -> dict:
    """
    Ejecuta el monitoreo satelital del manto nival para una ubicación.

    Args:
        consultor: Instancia de ConsultorBigQuery
        nombre_ubicacion: Nombre exacto de la ubicación

    Returns:
        dict con estado del manto nival y flags de alerta automáticos
    """
    logger.info(f"[tool_satelital] Monitoreando nieve para: {nombre_ubicacion}")

    resultado = consultor.obtener_estado_satelital(nombre_ubicacion)

    if resultado.get("error"):
        logger.error(f"[tool_satelital] Error al obtener datos satelitales: {resultado['error']}")
        return resultado

    if not resultado.get("disponible"):
        logger.warning(f"[tool_satelital] Sin datos satelitales recientes para: {nombre_ubicacion}")
        return resultado

    # Calcular flags de alerta automáticos
    alertas = []

    delta_pct_nieve_24h = resultado.get("delta_pct_nieve_24h")
    if delta_pct_nieve_24h is not None and delta_pct_nieve_24h > 15:
        alertas.append(
            f"NEVADA_RECIENTE: ganancia >{delta_pct_nieve_24h:.1f}% en 24h "
            "→ carga nueva sobre manto"
        )

    ami_7d = resultado.get("ami_7d")
    ciclo_diurno = resultado.get("ciclo_diurno_amplitud")
    if ami_7d is not None and ciclo_diurno is not None:
        if ami_7d > 20 and ciclo_diurno > 10:
            alertas.append(
                f"FUSION_ACTIVA: AMI 7d={ami_7d:.1f} + ciclo diurno={ciclo_diurno:.1f}°C "
                "→ nieve húmeda"
            )

    sar_pct_nieve_humeda = resultado.get("sar_pct_nieve_humeda")
    if sar_pct_nieve_humeda is not None and sar_pct_nieve_humeda > 30:
        alertas.append(
            f"NIEVE_HUMEDA_SAR: {sar_pct_nieve_humeda:.1f}% área con nieve húmeda "
            "detectada por radar"
        )

    transporte_eolico = resultado.get("transporte_eolico_activo")
    if transporte_eolico:
        alertas.append(
            "TRANSPORTE_EOLICO: viento activo redistribuyendo nieve → placas"
        )

    resultado["alertas"] = alertas
    resultado["ubicacion_consultada"] = nombre_ubicacion

    # Resumen para logging
    alertas_str = ", ".join(a.split(":")[0] for a in alertas) if alertas else "ninguna"
    logger.info(
        f"[tool_satelital] Estado obtenido — "
        f"cobertura: {resultado.get('pct_cobertura_nieve')}%, "
        f"snowline: {resultado.get('snowline_elevacion_m')}m, "
        f"alertas: {alertas_str}"
    )

    return resultado

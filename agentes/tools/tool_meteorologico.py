"""
Tool 3: Análisis Meteorológico

Obtiene condiciones meteorológicas actuales, tendencia 72h y pronóstico 3 días.
Combina los tres métodos meteorológicos del ConsultorBigQuery.

Nombre de la tool: analizar_meteorologia
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# DEFINICIÓN DE LA TOOL PARA ANTHROPIC
# =============================================================================

TOOL_METEOROLOGICO = {
    "name": "analizar_meteorologia",
    "description": (
        "Obtiene condiciones meteorológicas actuales, tendencia 72h y pronóstico "
        "3 días. Usar como tercer paso."
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

def ejecutar_analizar_meteorologia(consultor: Any, nombre_ubicacion: str) -> dict:
    """
    Ejecuta el análisis meteorológico completo para una ubicación.

    Args:
        consultor: Instancia de ConsultorBigQuery
        nombre_ubicacion: Nombre exacto de la ubicación

    Returns:
        dict con condiciones actuales, tendencia y pronóstico con alertas
    """
    logger.info(f"[tool_meteorologico] Analizando meteorología para: {nombre_ubicacion}")

    # Obtener los tres componentes en paralelo lógico
    condiciones = consultor.obtener_condiciones_actuales(nombre_ubicacion)
    tendencia = consultor.obtener_tendencia_meteorologica(nombre_ubicacion)
    pronostico = consultor.obtener_pronostico_proximos_dias(nombre_ubicacion)

    # Calcular flags de alerta automáticos desde tendencia
    alertas = []

    if tendencia.get("disponible"):
        precip_total = tendencia.get("precip_total_acumulada_mm", 0)
        if precip_total and precip_total > 30:
            alertas.append(
                f"PRECIPITACION_CRITICA: {precip_total:.1f}mm en 72h "
                "→ carga significativa"
            )

        viento_max = tendencia.get("viento_max_ms")
        if viento_max and viento_max > 15:
            alertas.append(
                f"VIENTO_FUERTE: ráfagas {viento_max:.1f}m/s "
                f"({round(viento_max * 3.6, 1)}km/h) → transporte eólico intenso"
            )

        temp_min = tendencia.get("temp_min_72h")
        temp_max = tendencia.get("temp_max_72h")
        if temp_min is not None and temp_max is not None:
            variacion = abs(temp_max - temp_min)
            if variacion > 15:
                alertas.append(
                    f"CAMBIO_TERMICO: variación de {variacion:.1f}°C en 72h "
                    "→ ciclos fusión-recongelamiento"
                )

    resultado = {
        "disponible": True,
        "ubicacion_consultada": nombre_ubicacion,
        "condiciones_actuales": condiciones,
        "tendencia_72h": tendencia,
        "pronostico_3dias": pronostico,
        "alertas": alertas
    }

    # Verificar disponibilidad general
    if not condiciones.get("disponible") and not tendencia.get("disponible"):
        resultado["disponible"] = False
        resultado["razon"] = "Sin datos meteorológicos disponibles"

    # Logging del resumen
    alertas_str = ", ".join(a.split(":")[0] for a in alertas) if alertas else "ninguna"
    logger.info(
        f"[tool_meteorologico] Análisis completado — "
        f"condiciones actuales: {'OK' if condiciones.get('disponible') else 'NO'}, "
        f"tendencia: {'OK' if tendencia.get('disponible') else 'NO'}, "
        f"pronóstico: {'OK' if pronostico.get('disponible') else 'NO'}, "
        f"alertas: {alertas_str}"
    )

    return resultado

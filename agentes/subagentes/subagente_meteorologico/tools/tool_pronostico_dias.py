"""
Tool: obtener_pronostico_dias

Obtiene el pronóstico de los próximos días desde BigQuery
(tabla pronostico_dias) y evalúa las condiciones futuras de riesgo.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

from agentes.datos.consultor_bigquery import ConsultorBigQuery


TOOL_PRONOSTICO_DIAS = {
    "name": "obtener_pronostico_dias",
    "description": (
        "Obtiene el pronóstico de los próximos 3-10 días desde BigQuery "
        "(tabla pronostico_dias): temperaturas máx/mín, precipitación "
        "diurna/nocturna, viento máximo y condición climática esperada. "
        "Evalúa las ventanas de tiempo con mayor riesgo de avalancha."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación en BigQuery"
            }
        },
        "required": ["nombre_ubicacion"]
    }
}


def ejecutar_obtener_pronostico_dias(nombre_ubicacion: str) -> dict:
    """
    Obtiene el pronóstico de días y evalúa condiciones de riesgo futuras.

    Args:
        nombre_ubicacion: nombre exacto de la ubicación

    Returns:
        dict con pronóstico estructurado y evaluación de riesgo por día
    """
    consultor = ConsultorBigQuery()
    datos = consultor.obtener_pronostico_proximos_dias(nombre_ubicacion)

    if "error" in datos:
        return datos

    if not datos.get("disponible"):
        return {
            "disponible": False,
            "ubicacion": nombre_ubicacion,
            "mensaje": "Sin datos de pronóstico en BigQuery"
        }

    dias = datos.get("dias", [])
    resumen = datos.get("resumen", {})

    # Evaluar riesgo por día
    dias_evaluados = []
    for dia in dias[:7]:  # Limitar a 7 días
        evaluacion = _evaluar_dia(dia)
        dias_evaluados.append({
            "fecha": dia.get("fecha_inicio"),
            "temp_max_C": dia.get("temp_max_dia"),
            "temp_min_C": dia.get("temp_min_dia"),
            "precip_diurna_mm": dia.get("diurno_prob_precipitacion"),
            "precip_nocturna_mm": dia.get("nocturno_prob_precipitacion"),
            "viento_max_diurno_ms": dia.get("diurno_velocidad_viento"),
            "condicion_diurna": dia.get("diurno_condicion"),
            "condicion_nocturna": dia.get("nocturno_condicion"),
            "evaluacion_riesgo": evaluacion
        })

    # Identificar el día de mayor riesgo
    dia_mayor_riesgo = _identificar_dia_mayor_riesgo(dias_evaluados)

    # Tendencia general del período
    tendencia_periodo = _evaluar_tendencia_periodo(dias_evaluados)

    return {
        "disponible": True,
        "ubicacion": nombre_ubicacion,
        "dias_pronosticados": len(dias_evaluados),
        "dias": dias_evaluados,
        "dia_mayor_riesgo": dia_mayor_riesgo,
        "tendencia_periodo": tendencia_periodo,
        "resumen_pronostico": resumen
    }


def _evaluar_dia(dia: dict) -> dict:
    """Evalúa el riesgo meteorológico de un día específico."""
    alertas = []
    score = 0

    temp_max = dia.get("temp_max_dia")
    temp_min = dia.get("temp_min_dia")
    precip_diurna = dia.get("diurno_prob_precipitacion", 0) or 0
    precip_nocturna = dia.get("nocturno_prob_precipitacion", 0) or 0
    viento_max = dia.get("diurno_velocidad_viento", 0) or 0

    # Temperatura sobre el punto de fusión
    if temp_max is not None and temp_max > 5:
        alertas.append("TEMPERATURA_MAX_ALTA")
        score += 2
    elif temp_max is not None and temp_max > 0:
        alertas.append("TEMPERATURA_MAX_SOBRE_CERO")
        score += 1

    # Ciclo fusión-congelación predicho
    if temp_max is not None and temp_min is not None:
        if temp_max > 0 and temp_min < -3:
            alertas.append("CICLO_FUSION_CONGELACION_PREVISTO")
            score += 2

    # Precipitación
    max_precip = max(precip_diurna, precip_nocturna)
    if max_precip > 70:
        alertas.append("ALTA_PROB_PRECIPITACION")
        score += 2
    elif max_precip > 40:
        alertas.append("PROBABILIDAD_PRECIPITACION_MODERADA")
        score += 1

    # Viento fuerte
    if viento_max > 20:
        alertas.append("VIENTO_FUERTE_PRONOSTICADO")
        score += 2
    elif viento_max > 12:
        alertas.append("VIENTO_MODERADO_PRONOSTICADO")
        score += 1

    # Nivel de riesgo del día
    if score >= 5:
        nivel = "muy_alto"
    elif score >= 3:
        nivel = "alto"
    elif score >= 1:
        nivel = "moderado"
    else:
        nivel = "bajo"

    return {
        "nivel_riesgo": nivel,
        "score": score,
        "alertas": alertas
    }


def _identificar_dia_mayor_riesgo(dias_evaluados: list) -> dict:
    """Identifica el día con mayor riesgo en el período."""
    if not dias_evaluados:
        return {}

    dia_max = max(
        dias_evaluados,
        key=lambda d: d.get("evaluacion_riesgo", {}).get("score", 0)
    )

    return {
        "fecha": dia_max.get("fecha"),
        "nivel_riesgo": dia_max.get("evaluacion_riesgo", {}).get("nivel_riesgo"),
        "alertas": dia_max.get("evaluacion_riesgo", {}).get("alertas", [])
    }


def _evaluar_tendencia_periodo(dias_evaluados: list) -> dict:
    """Evalúa la tendencia general del período pronosticado."""
    if not dias_evaluados:
        return {"tendencia": "sin_datos"}

    scores = [d.get("evaluacion_riesgo", {}).get("score", 0) for d in dias_evaluados]

    if not scores:
        return {"tendencia": "sin_datos"}

    score_primeros = sum(scores[:3]) / min(3, len(scores))
    score_ultimos = sum(scores[-3:]) / min(3, len(scores))

    if score_ultimos > score_primeros + 1:
        tendencia = "empeorando"
    elif score_ultimos < score_primeros - 1:
        tendencia = "mejorando"
    else:
        tendencia = "estable"

    dias_alto_riesgo = sum(
        1 for d in dias_evaluados
        if d.get("evaluacion_riesgo", {}).get("nivel_riesgo") in ("alto", "muy_alto")
    )

    return {
        "tendencia": tendencia,
        "dias_alto_riesgo_en_periodo": dias_alto_riesgo,
        "score_promedio": round(sum(scores) / len(scores), 1)
    }

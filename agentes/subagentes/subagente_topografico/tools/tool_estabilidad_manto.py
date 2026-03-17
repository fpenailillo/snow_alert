"""
Tool: evaluar_estabilidad_manto

Evalúa la estabilidad integrada del manto nival combinando el resultado
PINN, los factores topográficos y las condiciones satelitales disponibles
en el contexto previo del análisis.
"""

TOOL_ESTABILIDAD_MANTO = {
    "name": "evaluar_estabilidad_manto",
    "description": (
        "Evalúa la estabilidad integrada del manto nival combinando el "
        "resultado PINN (factor de seguridad Mohr-Coulomb, estado del manto), "
        "los factores topográficos (pendiente, aspecto, desnivel) y las "
        "condiciones satelitales del contexto. Produce una clasificación "
        "EAWS de estabilidad: very_poor, poor, fair, good."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "estado_pinn": {
                "type": "string",
                "description": "Estado PINN: CRITICO, INESTABLE, MARGINAL, ESTABLE"
            },
            "factor_seguridad": {
                "type": "number",
                "description": "Factor de seguridad Mohr-Coulomb del PINN"
            },
            "riesgo_topografico": {
                "type": "string",
                "description": "Riesgo topográfico combinado: muy_alto, alto, moderado, bajo"
            },
            "alertas_topograficas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de alertas topográficas identificadas"
            },
            "contexto_meteorologico": {
                "type": "string",
                "description": "Descripción del contexto meteorológico reciente (del contexto previo)"
            }
        },
        "required": [
            "estado_pinn",
            "factor_seguridad",
            "riesgo_topografico"
        ]
    }
}


def ejecutar_evaluar_estabilidad_manto(
    estado_pinn: str,
    factor_seguridad: float,
    riesgo_topografico: str,
    alertas_topograficas: list = None,
    contexto_meteorologico: str = None
) -> dict:
    """
    Evalúa la estabilidad integrada del manto nival.

    Args:
        estado_pinn: estado PINN (CRITICO/INESTABLE/MARGINAL/ESTABLE)
        factor_seguridad: factor de seguridad Mohr-Coulomb
        riesgo_topografico: nivel de riesgo combinado
        alertas_topograficas: lista de alertas topográficas
        contexto_meteorologico: contexto meteorológico del análisis previo

    Returns:
        dict con estabilidad EAWS, confianza y resumen topográfico
    """
    alertas = alertas_topograficas or []

    # Traducción de estado PINN a puntuación
    score_pinn = {
        "CRITICO": 4,
        "INESTABLE": 3,
        "MARGINAL": 2,
        "ESTABLE": 1
    }.get(estado_pinn, 2)

    # Puntuación topográfica
    score_topo = {
        "muy_alto": 3,
        "alto": 2,
        "moderado": 1,
        "bajo": 0
    }.get(riesgo_topografico, 1)

    # Alertas adicionales
    score_alertas = min(2, len(alertas))

    # Score total
    score_total = score_pinn + score_topo + score_alertas

    # Detectar keywords en contexto meteorológico
    score_meteo = 0
    if contexto_meteorologico:
        texto_lower = contexto_meteorologico.lower()
        if any(k in texto_lower for k in ["nevada", "precipitac", "lluvia"]):
            score_meteo += 1
        if any(k in texto_lower for k in ["fusión", "fusion", "deshielo", "0°"]):
            score_meteo += 1
        if any(k in texto_lower for k in ["viento", "temporal"]):
            score_meteo += 1

    score_total += score_meteo

    # Clasificación EAWS de estabilidad
    if score_total >= 7:
        estabilidad_eaws = "very_poor"
    elif score_total >= 5:
        estabilidad_eaws = "poor"
    elif score_total >= 3:
        estabilidad_eaws = "fair"
    else:
        estabilidad_eaws = "good"

    # Confianza del análisis
    confianza = _calcular_confianza(
        tiene_datos_topo=(riesgo_topografico != "bajo"),
        tiene_pinn=(factor_seguridad is not None),
        tiene_meteo=(contexto_meteorologico is not None and len(contexto_meteorologico) > 20)
    )

    resumen = (
        f"Estabilidad EAWS: {estabilidad_eaws}. "
        f"PINN: {estado_pinn} (FS={factor_seguridad:.2f}). "
        f"Riesgo topográfico: {riesgo_topografico}. "
        f"Score total: {score_total}/10. "
        f"Confianza: {confianza}."
    )

    return {
        "estabilidad_eaws": estabilidad_eaws,
        "score_total": score_total,
        "score_pinn": score_pinn,
        "score_topografico": score_topo,
        "score_alertas": score_alertas,
        "score_meteo_contexto": score_meteo,
        "confianza_analisis": confianza,
        "resumen_topografico": resumen
    }


def _calcular_confianza(
    tiene_datos_topo: bool,
    tiene_pinn: bool,
    tiene_meteo: bool
) -> str:
    """Calcula el nivel de confianza del análisis topográfico."""
    disponibles = sum([tiene_datos_topo, tiene_pinn, tiene_meteo])
    if disponibles == 3:
        return "alta"
    elif disponibles == 2:
        return "media"
    else:
        return "baja"

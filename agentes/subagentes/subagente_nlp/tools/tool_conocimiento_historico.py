"""
Tool: sintetizar_conocimiento_historico

Sintetiza los patrones históricos extraídos de relatos de montañistas
en un análisis estructurado de riesgo para la ubicación.
"""

TOOL_CONOCIMIENTO_HISTORICO = {
    "name": "sintetizar_conocimiento_historico",
    "description": (
        "Sintetiza el conocimiento experto comunitario a partir de los patrones "
        "extraídos de relatos. Determina el tipo de alud predominante, los meses "
        "de mayor riesgo histórico, y genera una narrativa de síntesis que "
        "complementa el análisis técnico (PINN + ViT + meteorología)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "total_relatos": {
                "type": "integer",
                "description": "Total de relatos encontrados para la zona"
            },
            "frecuencias_terminos": {
                "type": "object",
                "description": "Dict con término → número de menciones"
            },
            "indice_riesgo_base": {
                "type": "number",
                "description": "Índice de riesgo calculado (0.0-1.0) desde extraer_patrones"
            },
            "contexto_tecnico": {
                "type": "string",
                "description": (
                    "Resumen del contexto técnico actual (S1+S2+S3) para "
                    "comparar con el conocimiento histórico"
                )
            }
        },
        "required": ["total_relatos", "frecuencias_terminos", "indice_riesgo_base"]
    }
}


def ejecutar_sintetizar_conocimiento_historico(
    consultor,
    total_relatos: int,
    frecuencias_terminos: dict,
    indice_riesgo_base: float,
    contexto_tecnico: str = ""
) -> dict:
    """
    Sintetiza el conocimiento histórico de la comunidad montañera.

    No hace consultas adicionales a BigQuery; opera sobre los datos
    ya extraídos por las tools anteriores.

    Args:
        consultor: instancia de ConsultorBigQuery (no se usa pero se mantiene firma)
        total_relatos: número de relatos encontrados
        frecuencias_terminos: dict término → número de menciones
        indice_riesgo_base: índice calculado por extraer_patrones (0.0-1.0)
        contexto_tecnico: resumen del análisis técnico S1+S2+S3

    Returns:
        dict con síntesis del conocimiento histórico
    """
    if total_relatos == 0:
        return {
            "disponible": False,
            "razon": "Sin relatos históricos — tabla vacía o no cargada",
            "tipo_alud_predominante": "desconocido",
            "meses_mayor_riesgo": [],
            "patrones_recurrentes": [],
            "indice_riesgo_ajustado": 0.0,
            "confianza": "Baja",
            "narrativa": (
                "No hay relatos históricos disponibles para esta ubicación. "
                "El análisis se basa exclusivamente en datos técnicos (PINN, ViT, meteorología)."
            )
        }

    # Clasificar tipo de alud por frecuencia de términos
    menciones_placa = frecuencias_terminos.get("placa", 0)
    menciones_humeda = (frecuencias_terminos.get("húmeda", 0) +
                        frecuencias_terminos.get("mojada", 0) +
                        frecuencias_terminos.get("fusión", 0))
    menciones_reciente = (frecuencias_terminos.get("nieve blanda", 0) +
                          frecuencias_terminos.get("alud", 0) +
                          frecuencias_terminos.get("avalancha", 0))

    if menciones_placa >= max(menciones_humeda, menciones_reciente):
        tipo_predominante = "placa"
    elif menciones_humeda >= max(menciones_placa, menciones_reciente):
        tipo_predominante = "nieve_humeda"
    elif menciones_reciente > 0:
        tipo_predominante = "nieve_reciente"
    else:
        tipo_predominante = "mixto"

    # Determinar patrones recurrentes
    patrones = []
    if frecuencias_terminos.get("viento", 0) > 2:
        patrones.append("Viento frecuentemente mencionado como factor de riesgo")
    if frecuencias_terminos.get("grieta", 0) > 1:
        patrones.append("Grietas en el manto nival reportadas históricamente")
    if frecuencias_terminos.get("costra", 0) > 1:
        patrones.append("Formación de costra documentada en relatos previos")
    if frecuencias_terminos.get("peligroso", 0) > 3:
        patrones.append("Zona calificada como peligrosa en múltiples relatos")
    if frecuencias_terminos.get("canalón", 0) > 1:
        patrones.append("Canalones identificados como zonas de acumulación")

    # Confianza según número de relatos
    if total_relatos >= 10:
        confianza = "Alta"
    elif total_relatos >= 3:
        confianza = "Media"
    else:
        confianza = "Baja"

    # Índice ajustado: promedio entre base y señales cualitativas
    factor_cualitativo = min(1.0, len(patrones) / 5.0)
    indice_ajustado = round((indice_riesgo_base + factor_cualitativo) / 2.0, 3)

    # Narrativa de síntesis
    if indice_ajustado > 0.6:
        evaluacion = "La comunidad montañera documenta esta zona como de riesgo elevado"
    elif indice_ajustado > 0.3:
        evaluacion = "Los relatos sugieren riesgo moderado con eventos documentados"
    else:
        evaluacion = "Los relatos históricos no muestran patrones de alto riesgo frecuente"

    narrativa = (
        f"{evaluacion}. Se analizaron {total_relatos} relatos. "
        f"Tipo de alud predominante: {tipo_predominante}. "
    )
    if patrones:
        narrativa += "Patrones recurrentes: " + "; ".join(patrones[:3]) + "."

    return {
        "disponible": True,
        "total_relatos_analizados": total_relatos,
        "tipo_alud_predominante": tipo_predominante,
        "meses_mayor_riesgo": [],  # Requeriría campo fecha_relato agrupado por mes
        "patrones_recurrentes": patrones,
        "indice_riesgo_ajustado": indice_ajustado,
        "confianza": confianza,
        "narrativa": narrativa,
    }

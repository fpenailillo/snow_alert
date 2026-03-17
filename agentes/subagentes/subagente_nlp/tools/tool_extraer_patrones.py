"""
Tool: extraer_patrones_riesgo

Busca relatos que mencionen términos específicos de condiciones de riesgo
de avalanchas para calcular un índice histórico de peligrosidad.
"""

TERMINOS_RIESGO_EAWS = [
    "placa", "alud", "avalancha", "grieta",
    "viento", "nieve blanda", "costra", "peligroso",
    "inestable", "húmeda", "mojada", "fusión", "derretimiento",
    "canalón", "pendiente", "resbalé", "caí"
]

TOOL_EXTRAER_PATRONES = {
    "name": "extraer_patrones_riesgo",
    "description": (
        "Busca relatos que mencionen términos de riesgo de avalanchas "
        "(placas, aludes, viento, nieve blanda, etc.) para calcular un "
        "índice de peligrosidad histórica. Retorna frecuencias por término "
        "e índice de riesgo 0.0-1.0."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "terminos": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Términos de riesgo a buscar. Si no se proveen, usa la lista "
                    "estándar EAWS: placa, alud, avalancha, grieta, viento, etc."
                )
            },
            "limite_por_termino": {
                "type": "integer",
                "description": "Máximo de relatos por término (default: 10)",
                "default": 10
            }
        },
        "required": []
    }
}


def ejecutar_extraer_patrones(
    consultor,
    terminos: list = None,
    limite_por_termino: int = 10
) -> dict:
    """
    Extrae patrones de riesgo de los relatos históricos.

    Args:
        consultor: instancia de ConsultorBigQuery
        terminos: lista de términos a buscar (default: TERMINOS_RIESGO_EAWS)
        limite_por_termino: máximo de relatos por término

    Returns:
        dict con resultados por término e índice de riesgo calculado
    """
    if not terminos:
        terminos = TERMINOS_RIESGO_EAWS

    return consultor.buscar_relatos_condiciones(
        terminos=terminos,
        limite=limite_por_termino
    )

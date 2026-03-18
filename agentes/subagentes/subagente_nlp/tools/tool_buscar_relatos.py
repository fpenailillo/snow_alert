"""
Tool: buscar_relatos_ubicacion

Busca relatos históricos de montañistas para la ubicación solicitada.
Usa la tabla BigQuery clima.relatos_montanistas.
"""

TOOL_BUSCAR_RELATOS = {
    "name": "buscar_relatos_ubicacion",
    "description": (
        "Busca relatos históricos de montañistas en Andeshandbook para una "
        "ubicación específica. Retorna los relatos más recientes con título, "
        "fragmento de texto, fecha y URL. Útil para conocer experiencias "
        "previas de riesgo en la zona."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ubicacion": {
                "type": "string",
                "description": "Nombre de la ubicación a buscar (búsqueda parcial)"
            },
            "limite": {
                "type": "integer",
                "description": "Número máximo de relatos a retornar (default: 20)",
                "default": 20
            }
        },
        "required": ["ubicacion"]
    }
}


def ejecutar_buscar_relatos(ubicacion: str, limite: int = 20) -> dict:
    """
    Busca relatos históricos de montañistas para la ubicación.

    Args:
        ubicacion: nombre de la ubicación
        limite: número máximo de relatos

    Returns:
        dict con lista de relatos y metadatos
    """
    from agentes.datos.consultor_bigquery import ConsultorBigQuery
    consultor = ConsultorBigQuery()
    return consultor.obtener_relatos_ubicacion(ubicacion=ubicacion, limite=limite)

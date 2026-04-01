"""
Tool: obtener_eventos_pasados

Stub: retorna eventos históricos de avalanchas conocidos para la zona.
En la versión actual no existe tabla de avalanchas históricas en BQ.
Se implementará completamente cuando los datos SLF estén disponibles.
"""

import logging

logger = logging.getLogger(__name__)

# Eventos documentados conocidos (base de conocimiento estática inicial)
# Fuente: relatos Andeshandbook + literatura avalanchológica Andes Central
_EVENTOS_CONOCIDOS = {
    "La Parva": [
        "2021-08: Alud de placa en Couloir Central tras nevada + viento NW, afectó pista",
        "2019-07: Ciclo de avalanchas naturales en sector farellón NE tras frente atlántico",
        "2015-06: Cierre preventivo por riesgo muy alto tras 80cm nueva en 48h",
    ],
    "Valle Nevado": [
        "2022-07: Avalancha de nieve húmeda en sector Tres Puntas durante ola de calor",
        "2020-08: Aludes de placa en zona cumbre tras viento NW extremo (>100 km/h)",
        "2018-06: Activación artificial preventiva en sector glaciar de Las Lomas",
    ],
}


def obtener_eventos_pasados(ubicacion: str) -> dict:
    """
    Obtiene eventos históricos de avalanchas para la zona.

    Actualmente usa base de conocimiento estática. Cuando esté disponible
    la tabla BQ de avalanchas históricas (SLF/Snowlab), se actualizará
    para hacer la consulta directa.

    Args:
        ubicacion: Nombre de la ubicación

    Returns:
        dict con eventos_documentados, total, fuente y nota de implementacion
    """
    eventos = []
    for nombre_clave, lista in _EVENTOS_CONOCIDOS.items():
        if nombre_clave.lower() in ubicacion.lower() or ubicacion.lower() in nombre_clave.lower():
            eventos = lista
            break

    resultado = {
        "disponible": len(eventos) > 0,
        "fuente": "base_conocimiento_estatica",
        "nota": (
            "Datos históricos basados en documentación pública. "
            "Pendiente integración con datos SLF/Snowlab en tabla BQ."
        ),
        "eventos_documentados": eventos,
        "total_eventos": len(eventos),
        "tabla_bq_disponible": False,  # Se actualizará cuando exista la tabla
    }

    logger.info(
        f"tool_eventos_pasados: '{ubicacion}' — {len(eventos)} eventos documentados"
    )
    return resultado

"""
Tool: obtener_pronostico_ensemble

Obtiene el pronóstico meteorológico consolidado multi-fuente.
Con USE_WEATHERNEXT2=false (default): idéntico a solo Open-Meteo.
Con USE_WEATHERNEXT2=true: enriquece con percentiles del ensemble WN2.

Esta tool complementa las tools existentes — no las reemplaza.
S3 la puede llamar para obtener incertidumbre cuantificada.
"""

import logging
import os
from agentes.datos.constantes_zonas import COORDENADAS_ZONAS

logger = logging.getLogger(__name__)

_USE_WEATHERNEXT2 = os.environ.get("USE_WEATHERNEXT2", "false").lower() == "true"


TOOL_PRONOSTICO_ENSEMBLE = {
    "name": "obtener_pronostico_ensemble",
    "description": (
        "Obtiene pronóstico meteorológico consolidado multi-fuente con cuantificación "
        "de incertidumbre. Con WeatherNext 2 activo: entrega percentiles P10/P50/P90 "
        "de precipitación y temperatura del ensemble de 64 miembros. "
        "Con WeatherNext 2 inactivo: retorna pronóstico Open-Meteo estándar. "
        "Úsala cuando necesites evaluar incertidumbre del pronóstico o rango de "
        "precipitación esperada (importante para nieve nueva crítica EAWS)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación"
            },
            "horizonte_h": {
                "type": "integer",
                "description": "Horas de pronóstico adelante (default: 72)",
                "default": 72
            }
        },
        "required": ["nombre_ubicacion"]
    }
}


def ejecutar_obtener_pronostico_ensemble(
    nombre_ubicacion: str,
    horizonte_h: int = 72,
) -> dict:
    """
    Obtiene pronóstico consolidado multi-fuente.

    Args:
        nombre_ubicacion: nombre exacto de la ubicación
        horizonte_h: horas de pronóstico adelante

    Returns:
        dict con pronóstico principal + percentiles ensemble (si WN2 activo)
    """
    from agentes.subagentes.subagente_meteorologico.fuentes.consolidador import (
        ConsolidadorMeteorologico,
    )

    coords = COORDENADAS_ZONAS.get(nombre_ubicacion, (-33.35, -70.35))
    lat, lon = coords

    try:
        consolidador = ConsolidadorMeteorologico()
        resultado = consolidador.consolidar(nombre_ubicacion, lat, lon, horizonte_h)
        datos = resultado.to_dict()

        # Indicar si WN2 está activo para que S3 lo mencione en el análisis
        datos["weathernext2_activo"] = _USE_WEATHERNEXT2
        datos["disponible"] = resultado.pronostico_principal.fuente_disponible

        if not datos["disponible"]:
            datos["mensaje"] = (
                f"Fuente primaria ({resultado.fuente_primaria}) no disponible. "
                f"Error: {resultado.pronostico_principal.error}"
            )

        logger.info(
            f"tool_pronostico_ensemble: '{nombre_ubicacion}' — "
            f"fuente={resultado.fuente_primaria}, "
            f"wn2_activo={_USE_WEATHERNEXT2}, "
            f"divergencia={resultado.divergencia_detectada}"
        )
        return datos

    except Exception as exc:
        logger.error(f"tool_pronostico_ensemble: error para '{nombre_ubicacion}' — {exc}")
        return {
            "disponible": False,
            "error": str(exc),
            "weathernext2_activo": False,
        }

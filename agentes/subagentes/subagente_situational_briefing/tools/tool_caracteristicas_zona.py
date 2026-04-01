"""
Tool: obtener_caracteristicas_zona

Obtiene características topográficas relevantes para EAWS de la zona.
Combina datos de BigQuery (zonas_avalancha) con constantes hardcodeadas
para La Parva y Valle Nevado (hasta que pendientes_detalladas esté completa).
"""

import logging

logger = logging.getLogger(__name__)

TOOL_CARACTERISTICAS_ZONA = {
    "name": "obtener_caracteristicas_zona",
    "description": (
        "Obtiene características topográficas de la zona relevantes para EAWS: "
        "rango de altitudes, orientaciones críticas de acumulación/inicio, "
        "distribución de pendientes según rangos EAWS (<30°, 30-35°, 35-45°, 45-60°, >60°), "
        "características especiales (cornisas, couloirs, glaciares) y accesos. "
        "Enriquecida con datos BQ (zonas_avalancha) si disponibles."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación"
            }
        },
        "required": ["ubicacion"]
    }
}


def ejecutar_obtener_caracteristicas_zona(ubicacion: str) -> dict:
    return obtener_caracteristicas_zona(ubicacion)

# Constantes topográficas para zonas conocidas
# Basado en análisis DEM NASADEM/GLO-30 y conocimiento del terreno
_CARACTERISTICAS_ZONAS = {
    "La Parva": {
        "altitud_minima_m": 2662,
        "altitud_maxima_m": 3630,
        "altitud_base_m": 2662,
        "orientaciones_criticas": ["S", "SE", "E", "NE"],
        "rangos_pendiente_eaws": [
            "<30° (zonas de depósito y pistas anchas): ~35%",
            "30-35° (umbral avalancha): ~20%",
            "35-45° (zona inicio típica): ~30%",
            "45-60° (couloirs y caras abruptas): ~12%",
            ">60° (paredes verticales): ~3%",
        ],
        "caracteristicas_especiales": [
            "Farellón NE con cornisas persistentes en invierno",
            "Couloir La Parva Central: orientación NE-E, 40-50°",
            "Sector El Colorado limítrofe: acumulación por viento NW",
            "Zona de depósito en quebrada sur del resort",
        ],
        "accesos_principales": ["Ruta G-21 (camino a Farellones)", "Telesilla principal"],
    },
    "Valle Nevado": {
        "altitud_minima_m": 3025,
        "altitud_maxima_m": 4150,
        "altitud_base_m": 3025,
        "orientaciones_criticas": ["N", "NE", "E"],
        "rangos_pendiente_eaws": [
            "<30° (pistas principales): ~30%",
            "30-35° (pistas rojas/negras): ~25%",
            "35-45° (terreno off-piste superior): ~32%",
            "45-60° (couloirs de cumbre): ~10%",
            ">60° (paredes glaciares): ~3%",
        ],
        "caracteristicas_especiales": [
            "Acceso a Glaciar de Las Lomas (orientación NE, >3800m)",
            "Sector Tres Puntas: exposición viento NW dominante",
            "Zona de depósito amplia en piso del valley",
            "Cornisas en cresta E-NE sobre pistas de acceso",
        ],
        "accesos_principales": ["Ruta G-21 (Farellones → Valle Nevado)", "Gondola principal"],
    },
}

_DEFAULT_ZONA = {
    "altitud_minima_m": 2500,
    "altitud_maxima_m": 3800,
    "altitud_base_m": 2500,
    "orientaciones_criticas": ["S", "SE", "N", "NE"],
    "rangos_pendiente_eaws": [
        "<30°: ~35%", "30-35°: ~20%", "35-45°: ~30%", "45-60°: ~12%", ">60°: ~3%"
    ],
    "caracteristicas_especiales": [],
    "accesos_principales": ["Ruta G-21"],
}


def obtener_caracteristicas_zona(ubicacion: str) -> dict:
    """
    Obtiene características topográficas de la zona relevantes para EAWS.

    Usa datos hardcodeados para La Parva / Valle Nevado y enriquece con
    datos de BigQuery (tabla zonas_avalancha) si están disponibles.

    Args:
        ubicacion: Nombre de la ubicación

    Returns:
        dict con altitudes, orientaciones críticas, distribución de pendientes,
        características especiales y datos de riesgo topográfico desde BQ
    """
    # Buscar zona por nombre parcial
    zona_data = None
    for nombre_clave, datos in _CARACTERISTICAS_ZONAS.items():
        if nombre_clave.lower() in ubicacion.lower() or ubicacion.lower() in nombre_clave.lower():
            zona_data = datos.copy()
            break

    if zona_data is None:
        logger.warning(f"tool_caracteristicas_zona: zona '{ubicacion}' no conocida, usando defaults")
        zona_data = _DEFAULT_ZONA.copy()

    resultado = {
        "disponible": True,
        "nombre_zona": ubicacion,
        "fuente": "constantes_hardcodeadas",
        **zona_data,
        # Datos BQ (se sobreescribirán si hay datos)
        "indice_riesgo_topografico": None,
        "clasificacion_riesgo": None,
        "frecuencia_estimada_eaws": None,
        "tamano_estimado_eaws": None,
        "pendiente_media_inicio": None,
        "zona_inicio_ha": None,
        "total_zonas_bq": 0,
    }

    # Enriquecer con datos BigQuery
    try:
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery()
        perfil = consultor.obtener_perfil_topografico(ubicacion)

        zonas = perfil.get("zonas", [])
        if zonas:
            resultado["total_zonas_bq"] = len(zonas)
            resultado["fuente"] = "constantes_hardcodeadas + clima.zonas_avalancha"

            # Promedios de campos EAWS desde BQ
            indices = [z.get("indice_riesgo_topografico") for z in zonas if z.get("indice_riesgo_topografico")]
            pendientes = [z.get("pendiente_media_inicio") for z in zonas if z.get("pendiente_media_inicio")]
            areas = [z.get("zona_inicio_ha") for z in zonas if z.get("zona_inicio_ha")]

            if indices:
                resultado["indice_riesgo_topografico"] = round(sum(indices) / len(indices), 2)
            if pendientes:
                resultado["pendiente_media_inicio"] = round(sum(pendientes) / len(pendientes), 1)
            if areas:
                resultado["zona_inicio_ha"] = round(sum(areas), 1)

            # Tomar clasificación y frecuencia de la zona más crítica
            zona_critica = max(zonas, key=lambda z: z.get("indice_riesgo_topografico") or 0)
            resultado["clasificacion_riesgo"] = zona_critica.get("clasificacion_riesgo")
            resultado["frecuencia_estimada_eaws"] = zona_critica.get("frecuencia_estimada_eaws")
            resultado["tamano_estimado_eaws"] = zona_critica.get("tamano_estimado_eaws")

            logger.info(
                f"tool_caracteristicas_zona: '{ubicacion}' — {len(zonas)} zonas BQ, "
                f"índice_riesgo={resultado['indice_riesgo_topografico']}"
            )
        else:
            logger.info(f"tool_caracteristicas_zona: '{ubicacion}' — sin zonas en BQ, usando solo constantes")

    except Exception as exc:
        logger.warning(f"tool_caracteristicas_zona: error BQ para '{ubicacion}' — {exc}")

    return resultado

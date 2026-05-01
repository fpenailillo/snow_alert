"""
Mapeo preciso de estaciones AndesAI → sectores SLF suizos.

Reemplaza el mapeo por nivel modal del cantón (aprox.) por el sector
geográficamente más cercano a cada estación. Esto reduce el ruido
del ground truth en la validación H1/H3.

Metodología:
    Para cada estación AndesAI en Suiza, se identifica el sector SLF
    (tabla validacion_avalanchas.slf_danger_levels_qc) más cercano por
    distancia haversine, restringido al cantón correspondiente.

Sectores verificados contra slf_danger_levels_qc:
    4113 → Bern/Bernese Oberland (Interlaken, lat≈46.69, lon≈7.86)
    2223 → Valais/Zermatt-Matterhorn (lat≈46.02, lon≈7.75)
    6113 → Graubünden/Engadin (St. Moritz, lat≈46.49, lon≈9.84)

Referencias:
    SLF (2024). Lawinengefahr Schweiz, sector_id scheme, Davos.
    Techel & Pielmeier (2009). Spatial variability of avalanche danger.
"""

import math


# ── Mapeo estático estación AndesAI → sector SLF ─────────────────────────────

MAPEO_ESTACIONES_SLF: dict[str, dict] = {
    "Interlaken": {
        "nombre_andesai": "Interlaken",
        "sector_id":      4113,
        "lat":            46.686,
        "lon":            7.863,
        "altitud_m":      1200,
        "canton":         "Bern",
        "prefix_canton":  "4",
        "descripcion":    "Bernese Oberland central — sector más representativo para Interlaken",
    },
    "Matterhorn Zermatt": {
        "nombre_andesai": "Matterhorn Zermatt",
        "sector_id":      2223,
        "lat":            46.021,
        "lon":            7.749,
        "altitud_m":      2600,
        "canton":         "Valais",
        "prefix_canton":  "2",
        "descripcion":    "Alto Valais / Zermatt — sector del macizo del Matterhorn",
    },
    "St Moritz": {
        "nombre_andesai": "St Moritz",
        "sector_id":      6113,
        "lat":            46.491,
        "lon":            9.836,
        "altitud_m":      1900,
        "canton":         "Graubünden",
        "prefix_canton":  "6",
        "descripcion":    "Engadin Superior / St. Moritz — sector del valle de Engadin",
    },
}


# ── Helpers geográficos ───────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula distancia en km entre dos puntos geográficos (fórmula haversine).

    Args:
        lat1, lon1: coordenadas del primer punto en grados decimales
        lat2, lon2: coordenadas del segundo punto en grados decimales

    Returns:
        Distancia en kilómetros.
    """
    R = 6371.0  # radio medio de la Tierra en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def obtener_sector_slf(nombre_ubicacion: str) -> dict | None:
    """
    Retorna la info del sector SLF más cercano a la ubicación dada.

    Args:
        nombre_ubicacion: nombre exacto de la estación AndesAI en Suiza

    Returns:
        dict con sector_id, canton, lat, lon, altitud_m, descripcion
        o None si la ubicación no está en el mapeo.
    """
    return MAPEO_ESTACIONES_SLF.get(nombre_ubicacion)


def sectores_por_distancia(lat_ref: float, lon_ref: float, sectores: list[dict]) -> list[dict]:
    """
    Ordena una lista de sectores (con campos lat, lon) por distancia haversine
    al punto de referencia, del más cercano al más lejano.

    Args:
        lat_ref, lon_ref: coordenadas del punto de referencia
        sectores: lista de dicts con al menos 'lat', 'lon', 'sector_id'

    Returns:
        Lista ordenada por distancia ascendente, con campo 'distancia_km' añadido.
    """
    resultado = []
    for s in sectores:
        d = haversine_km(lat_ref, lon_ref, s["lat"], s["lon"])
        resultado.append({**s, "distancia_km": round(d, 2)})
    return sorted(resultado, key=lambda x: x["distancia_km"])


def resumen_mapeo() -> str:
    """Retorna un string legible con el mapeo completo para logs y reportes."""
    lineas = ["Mapeo estación AndesAI → sector SLF preciso:"]
    for nombre, info in MAPEO_ESTACIONES_SLF.items():
        lineas.append(
            f"  {nombre:<22} → sector_id={info['sector_id']}  "
            f"canton={info['canton']}  "
            f"({info['descripcion']})"
        )
    return "\n".join(lineas)

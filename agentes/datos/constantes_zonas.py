"""
Definiciones geográficas centralizadas de las zonas objetivo del sistema.

Fuente única de verdad para coordenadas, polígonos y metadatos de zona.
Importar desde aquí en lugar de duplicar coordenadas en cada módulo.
"""

# ─── Coordenadas puntuales (lat, lon) ─────────────────────────────────────────
# Usadas por Open-Meteo, ERA5-Land, WeatherNext 2 para queries puntuales.

COORDENADAS_ZONAS: dict[str, tuple[float, float]] = {
    "La Parva":             (-33.354, -70.298),
    "La Parva Sector Bajo": (-33.363, -70.301),
    "La Parva Sector Medio":(-33.352, -70.290),
    "La Parva Sector Alto": (-33.344, -70.280),
    "Valle Nevado":         (-33.357, -70.270),
    "El Colorado":          (-33.360, -70.289),
}

# ─── Bounding boxes (lon_min, lat_min, lon_max, lat_max) ──────────────────────
# Usados por Earth Engine para filtrar imágenes satelitales.

BBOX_ZONAS: dict[str, list[float]] = {
    "La Parva":             [-70.45, -33.45, -70.15, -33.25],
    "La Parva Sector Bajo": [-70.40, -33.43, -70.25, -33.32],
    "Valle Nevado":         [-70.38, -33.40, -70.18, -33.25],
    "El Colorado":          [-70.35, -33.43, -70.22, -33.30],
}

# ─── Polígonos GeoJSON (para BigQuery GEOGRAPHY y ST_REGIONSTATS) ─────────────
# Formato: anillo exterior cerrado (primer punto = último punto).

POLIGONOS_ZONAS: dict[str, dict] = {
    "La Parva": {
        "type": "Polygon",
        "coordinates": [[
            [-70.45, -33.45], [-70.15, -33.45],
            [-70.15, -33.25], [-70.45, -33.25],
            [-70.45, -33.45],
        ]],
    },
    "La Parva Sector Bajo": {
        "type": "Polygon",
        "coordinates": [[
            [-70.40, -33.43], [-70.25, -33.43],
            [-70.25, -33.32], [-70.40, -33.32],
            [-70.40, -33.43],
        ]],
    },
    "Valle Nevado": {
        "type": "Polygon",
        "coordinates": [[
            [-70.38, -33.40], [-70.18, -33.40],
            [-70.18, -33.25], [-70.38, -33.25],
            [-70.38, -33.40],
        ]],
    },
    "El Colorado": {
        "type": "Polygon",
        "coordinates": [[
            [-70.35, -33.43], [-70.22, -33.43],
            [-70.22, -33.30], [-70.35, -33.30],
            [-70.35, -33.43],
        ]],
    },
}

# ─── Metadata de zonas ─────────────────────────────────────────────────────────

METADATA_ZONAS: dict[str, dict] = {
    "La Parva": {
        "elevacion_min_m": 2200,
        "elevacion_max_m": 4500,
        "exposicion_predominante": "SE",
        "region_eaws": "Andes Central Norte",
    },
    "La Parva Sector Bajo": {
        "elevacion_min_m": 2200,
        "elevacion_max_m": 3200,
        "exposicion_predominante": "SE",
        "region_eaws": "Andes Central Norte",
    },
    "Valle Nevado": {
        "elevacion_min_m": 2800,
        "elevacion_max_m": 4500,
        "exposicion_predominante": "NO",
        "region_eaws": "Andes Central Norte",
    },
    "El Colorado": {
        "elevacion_min_m": 2400,
        "elevacion_max_m": 4100,
        "exposicion_predominante": "O",
        "region_eaws": "Andes Central Norte",
    },
}

# ─── Helpers ───────────────────────────────────────────────────────────────────

def obtener_coordenadas(zona: str) -> tuple[float, float]:
    """Retorna (lat, lon) para la zona; usa La Parva como fallback."""
    return COORDENADAS_ZONAS.get(zona, (-33.354, -70.298))


def obtener_bbox(zona: str) -> list[float]:
    """Retorna [lon_min, lat_min, lon_max, lat_max]; usa La Parva como fallback."""
    nombre_base = zona.split(" Sector")[0] if " Sector" in zona else zona
    return BBOX_ZONAS.get(zona) or BBOX_ZONAS.get(nombre_base, [-70.45, -33.45, -70.15, -33.25])


def poligono_geojson_str(zona: str) -> str:
    """Retorna el polígono como string GeoJSON para ST_GeogFromGeoJSON()."""
    import json
    nombre_base = zona.split(" Sector")[0] if " Sector" in zona else zona
    poly = POLIGONOS_ZONAS.get(zona) or POLIGONOS_ZONAS.get(nombre_base, POLIGONOS_ZONAS["La Parva"])
    return json.dumps(poly)


ZONAS_DISPONIBLES: list[str] = sorted(COORDENADAS_ZONAS.keys())

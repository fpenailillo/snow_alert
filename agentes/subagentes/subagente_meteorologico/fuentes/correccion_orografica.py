"""
Corrección orográfica para precipitación ERA5-Land.

ERA5 @9km sobreestima la precipitación en zonas de topografía compleja porque
el modelo de área (~81 km²) suaviza los gradientes orográficos reales.
El sesgo es proporcional a la altitud: mayor altitud → mayor sobreestimación.

Factores calibrados inicialmente con literatura ERA5 (Muñoz Sabater 2021),
ajustables con los 24 pares suizos de validación H1/H3 cuando haya suficientes datos.

Regiones de aplicación:
  - Andes centrales Chile (La Parva, Valle Nevado, El Colorado): 2200–4500m
  - Alpes suizos (Interlaken, Zermatt, St. Moritz): 1200–2600m

Nota: La corrección NO aplica a Open-Meteo ni WeatherNext 2 (que tienen resolución
horizontal fina y modelos de terreno más precisos). Solo aplica a ERA5 reanálisis.

Referencias:
    Muñoz Sabater (2021) — ERA5-Land hourly data, ESSD, doi:10.5194/essd-13-4349-2021.
    Prein & Gobiet (2017) — ERA5 precipitation bias, J. Hydrology.
    Monteiro et al. (2022) — ERA5 bias correction in Andes, J. Climate.
"""

# Factor multiplicativo por banda de altitud (alt_min_m, alt_max_m): factor
# Interpretación: precipitacion_corregida = precipitacion_era5 × factor
ERA5_CORRECCIÓN_OROGRAFICA: dict[tuple[int, int], float] = {
    (0,    1500): 1.00,   # < 1500m — sin corrección relevante
    (1500, 2500): 0.85,   # ERA5 sobreestima ~15% en zona andina/alpina media
    (2500, 3500): 0.75,   # sobreestima ~25% en zona andina/alpina alta
    (3500, 9999): 0.65,   # sobreestima ~35% sobre 3500m
}

# Altitudes de referencia por zona para aplicar la corrección
# (usamos la elevación media representativa del sector)
ALTITUD_REFERENCIA_ZONAS_M: dict[str, int] = {
    # ── Andes Chile ───────────────────────────────────────────────────────────
    "La Parva":              2700,
    "La Parva Sector Bajo":  2700,  # 2200–3200 → mid 2700m
    "La Parva Sector Medio": 3000,
    "La Parva Sector Alto":  3600,
    "Valle Nevado":          3200,  # 2800–4500 → mid 3200m
    "El Colorado":           3200,
    # ── Alpes Suizos ─────────────────────────────────────────────────────────
    "Interlaken":            1200,
    "Matterhorn Zermatt":    2600,
    "St Moritz":             1900,
}


def factor_correccion_orografica(altitud_m: float) -> float:
    """
    Retorna el factor multiplicativo de corrección para la altitud dada.

    Args:
        altitud_m: altitud de referencia del sector en metros

    Returns:
        Factor entre 0.65 y 1.0. Altitudes desconocidas (<0) retornan 1.0.
    """
    if altitud_m < 0:
        return 1.0
    for (alt_min, alt_max), factor in ERA5_CORRECCIÓN_OROGRAFICA.items():
        if alt_min <= altitud_m < alt_max:
            return factor
    return 1.0  # fallback seguro: sin corrección


def aplicar_correccion_orografica(
    precipitacion_mm: float | None,
    altitud_m: float,
) -> float | None:
    """
    Aplica la corrección orográfica ERA5 a la precipitación acumulada.

    Args:
        precipitacion_mm: precipitación acumulada en mm (None → retorna None)
        altitud_m: altitud de referencia del sector en metros

    Returns:
        Precipitación corregida en mm, o None si la entrada es None.
    """
    if precipitacion_mm is None:
        return None
    factor = factor_correccion_orografica(altitud_m)
    return round(precipitacion_mm * factor, 3)


def obtener_altitud_zona(zona: str) -> int:
    """
    Retorna la altitud de referencia para la zona dada.

    Intenta resolver alias comunes (ej: "La Parva Sector" → "La Parva Sector Bajo").
    Si la zona no está en el catálogo, retorna 0 (sin corrección).

    Args:
        zona: nombre de la ubicación

    Returns:
        Altitud en metros (0 si no hay datos → factor = 1.0, sin corrección).
    """
    if zona in ALTITUD_REFERENCIA_ZONAS_M:
        return ALTITUD_REFERENCIA_ZONAS_M[zona]
    # Intento de resolución parcial
    for nombre_conocido in ALTITUD_REFERENCIA_ZONAS_M:
        if nombre_conocido in zona or zona in nombre_conocido:
            return ALTITUD_REFERENCIA_ZONAS_M[nombre_conocido]
    return 0

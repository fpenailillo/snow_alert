"""
Corrección orográfica para precipitación ERA5-Land.

ERA5 @9km sobreestima la precipitación en zonas de topografía compleja porque
el modelo de área (~81 km²) suaviza los gradientes orográficos reales.
El sesgo es proporcional a la altitud: mayor altitud → mayor sobreestimación.

Factores calibrados con datos Andes centrales (Muñoz Sabater 2021 + Monteiro 2022).
NO se aplican a los Alpes suizos: el régimen orográfico alpino es distinto (alivio
dinámico, step orográfico) y los mismos factores empeoran el sesgo ERA5 en lugar
de corregirlo (validación H1/H3 Ronda 3: sesgo −0.50 → −0.92 al aplicar corrección
andina en Interlaken/Zermatt). Para Alpes se retorna factor=1.0.

Regiones de aplicación:
  - Andes centrales Chile (La Parva, Valle Nevado, El Colorado): corrección activa
  - Alpes suizos (Interlaken, Zermatt, St. Moritz): sin corrección (factor=1.0)

Nota: La corrección NO aplica a Open-Meteo ni WeatherNext 2 (que tienen resolución
horizontal fina y modelos de terreno más precisos). Solo aplica a ERA5 reanálisis.

Referencias:
    Muñoz Sabater (2021) — ERA5-Land hourly data, ESSD, doi:10.5194/essd-13-4349-2021.
    Prein & Gobiet (2017) — ERA5 precipitation bias, J. Hydrology.
    Monteiro et al. (2022) — ERA5 bias correction in Andes, J. Climate.
"""

# Factor multiplicativo por banda de altitud para región ANDES (calibrado).
# Interpretación: precipitacion_corregida = precipitacion_era5 × factor
ERA5_CORRECCIÓN_OROGRAFICA: dict[tuple[int, int], float] = {
    (0,    1500): 1.00,   # < 1500m — sin corrección relevante
    (1500, 2500): 0.85,   # ERA5 sobreestima ~15% en zona andina media
    (2500, 3500): 0.75,   # sobreestima ~25% en zona andina alta
    (3500, 9999): 0.65,   # sobreestima ~35% sobre 3500m
}

# Zonas clasificadas como Alpes suizos — NO se aplica corrección orográfica andina
_ZONAS_ALPES: frozenset[str] = frozenset({
    "Interlaken",
    "Matterhorn Zermatt",
    "St Moritz",
})

# Altitudes de referencia por zona
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


def es_zona_alpes(zona: str) -> bool:
    """Retorna True si la zona es de los Alpes suizos (sin corrección andina)."""
    if not zona:
        return False
    if zona in _ZONAS_ALPES:
        return True
    for nombre_alpes in _ZONAS_ALPES:
        if nombre_alpes in zona or zona in nombre_alpes:
            return True
    return False


def factor_correccion_orografica(altitud_m: float, region: str = "andes") -> float:
    """
    Retorna el factor multiplicativo de corrección para la altitud dada.

    Para región "alpes" siempre retorna 1.0 — la corrección andina empeora el sesgo
    ERA5 en los Alpes suizos por su distinto régimen orográfico.

    Args:
        altitud_m: altitud de referencia del sector en metros
        region: "andes" (default) o "alpes"

    Returns:
        Factor entre 0.65 y 1.0. Altitudes desconocidas (<0) retornan 1.0.
    """
    if region == "alpes":
        return 1.0
    if altitud_m < 0:
        return 1.0
    for (alt_min, alt_max), factor in ERA5_CORRECCIÓN_OROGRAFICA.items():
        if alt_min <= altitud_m < alt_max:
            return factor
    return 1.0  # fallback seguro: sin corrección


def aplicar_correccion_orografica(
    precipitacion_mm: float | None,
    altitud_m: float,
    zona: str = "",
) -> float | None:
    """
    Aplica la corrección orográfica ERA5 a la precipitación acumulada.

    Detecta automáticamente si la zona es de los Alpes (sin corrección).

    Args:
        precipitacion_mm: precipitación acumulada en mm (None → retorna None)
        altitud_m: altitud de referencia del sector en metros
        zona: nombre de la ubicación (para detectar Alpes automáticamente)

    Returns:
        Precipitación corregida en mm, o None si la entrada es None.
    """
    if precipitacion_mm is None:
        return None
    region = "alpes" if es_zona_alpes(zona) else "andes"
    factor = factor_correccion_orografica(altitud_m, region=region)
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
    for nombre_conocido in ALTITUD_REFERENCIA_ZONAS_M:
        if nombre_conocido in zona or zona in nombre_conocido:
            return ALTITUD_REFERENCIA_ZONAS_M[nombre_conocido]
    return 0

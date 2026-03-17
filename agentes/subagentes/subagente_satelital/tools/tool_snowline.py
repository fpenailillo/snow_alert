"""
Tool: calcular_snowline

Estima la línea de nieve (snowline) a partir de métricas satelitales
y datos topográficos del contexto previo.
"""

TOOL_SNOWLINE = {
    "name": "calcular_snowline",
    "description": (
        "Estima la elevación de la línea de nieve (snowline) y su "
        "variación reciente a partir de NDSI, cobertura de nieve, "
        "LST y el perfil de elevación de la ubicación. "
        "La snowline es clave para determinar el espesor efectivo "
        "del manto nival activo y el área expuesta a avalanchas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pct_cobertura_nieve": {
                "type": "number",
                "description": "Porcentaje de cobertura de nieve (%)"
            },
            "ndsi_medio": {
                "type": "number",
                "description": "NDSI promedio de la zona"
            },
            "lst_dia_celsius": {
                "type": "number",
                "description": "Temperatura superficial diurna (°C)"
            },
            "elevacion_max_m": {
                "type": "number",
                "description": "Elevación máxima del área de análisis (m)"
            },
            "elevacion_min_m": {
                "type": "number",
                "description": "Elevación mínima del área de análisis (m)"
            },
            "delta_pct_nieve_24h": {
                "type": "number",
                "description": "Cambio en cobertura de nieve en 24h (%)"
            }
        },
        "required": [
            "pct_cobertura_nieve",
            "ndsi_medio"
        ]
    }
}


def ejecutar_calcular_snowline(
    pct_cobertura_nieve: float,
    ndsi_medio: float,
    lst_dia_celsius: float = None,
    elevacion_max_m: float = None,
    elevacion_min_m: float = None,
    delta_pct_nieve_24h: float = 0.0
) -> dict:
    """
    Estima la snowline y su tendencia a partir de métricas satelitales.

    Args:
        pct_cobertura_nieve: cobertura actual (%)
        ndsi_medio: NDSI actual
        lst_dia_celsius: temperatura diurna en °C (opcional)
        elevacion_max_m: elevación máxima del área (opcional)
        elevacion_min_m: elevación mínima del área (opcional)
        delta_pct_nieve_24h: cambio de cobertura en 24h

    Returns:
        dict con snowline estimada, tendencia y área nival activa
    """
    # Si tenemos elevaciones, estimar snowline por interpolación
    snowline_estimada_m = None
    metodo_estimacion = "empirico"

    if elevacion_max_m is not None and elevacion_min_m is not None:
        rango_elevacion = elevacion_max_m - elevacion_min_m

        # La snowline se estima como la elevación donde el NDSI cae bajo 0.4
        # Asumimos distribución lineal de cobertura con la altitud
        if pct_cobertura_nieve > 0:
            # Si cubre el X% del área, la snowline está en el (100-X)% inferior
            fraccion_sin_nieve = max(0, 100 - pct_cobertura_nieve) / 100.0
            snowline_estimada_m = round(
                elevacion_min_m + fraccion_sin_nieve * rango_elevacion
            )
            metodo_estimacion = "interpolacion_elevacion"
        else:
            snowline_estimada_m = elevacion_max_m
            metodo_estimacion = "sin_cobertura_nival"

    # Tendencia de la snowline (subiendo o bajando)
    tendencia_snowline = _evaluar_tendencia_snowline(
        delta_pct_nieve_24h=delta_pct_nieve_24h,
        lst_dia_celsius=lst_dia_celsius
    )

    # Área nival activa para avalanchas (zona de inicio sobre la snowline)
    cobertura_efectiva = _calcular_cobertura_efectiva(
        pct_cobertura_nieve=pct_cobertura_nieve,
        ndsi_medio=ndsi_medio
    )

    # Clasificación del estado de la snowline
    estado_snowline = _clasificar_estado_snowline(
        cobertura_efectiva=cobertura_efectiva,
        tendencia=tendencia_snowline["direccion"],
        ndsi_medio=ndsi_medio
    )

    resultado = {
        "snowline_estimada_m": snowline_estimada_m,
        "metodo_estimacion": metodo_estimacion,
        "cobertura_nieve_pct": pct_cobertura_nieve,
        "cobertura_efectiva_pct": cobertura_efectiva,
        "ndsi_medio": ndsi_medio,
        "tendencia_snowline": tendencia_snowline,
        "estado_snowline": estado_snowline,
        "area_nival_activa": _describir_area_nival(
            cobertura_efectiva, elevacion_max_m, snowline_estimada_m
        )
    }

    if elevacion_max_m:
        resultado["elevacion_max_m"] = elevacion_max_m
    if elevacion_min_m:
        resultado["elevacion_min_m"] = elevacion_min_m

    return resultado


def _evaluar_tendencia_snowline(
    delta_pct_nieve_24h: float,
    lst_dia_celsius: float = None
) -> dict:
    """Evalúa si la snowline está subiendo, bajando o estable."""
    if delta_pct_nieve_24h > 8:
        direccion = "bajando"  # Nevada → más cobertura → snowline más baja
        velocidad = "rapida" if delta_pct_nieve_24h > 20 else "moderada"
    elif delta_pct_nieve_24h < -8:
        direccion = "subiendo"  # Fusión → menos cobertura → snowline más alta
        velocidad = "rapida" if delta_pct_nieve_24h < -20 else "moderada"
    else:
        direccion = "estable"
        velocidad = "ninguna"

    # Modificar por temperatura
    if lst_dia_celsius is not None and lst_dia_celsius > 2 and direccion == "estable":
        direccion = "subiendo_lentamente"
        velocidad = "lenta"

    return {
        "direccion": direccion,
        "velocidad": velocidad,
        "delta_cobertura_24h": delta_pct_nieve_24h
    }


def _calcular_cobertura_efectiva(
    pct_cobertura_nieve: float,
    ndsi_medio: float
) -> float:
    """
    Calcula la cobertura nival efectiva para generación de avalanchas.

    Ajusta por calidad de la nieve (NDSI):
    - NDSI alto (>0.5) → nieve seca, densa → cobertura efectiva plena
    - NDSI bajo (<0.3) → nieve húmeda, posible subestimación → ajuste menor
    """
    if ndsi_medio >= 0.5:
        factor_calidad = 1.0
    elif ndsi_medio >= 0.4:
        factor_calidad = 0.9
    elif ndsi_medio >= 0.3:
        factor_calidad = 0.8
    else:
        factor_calidad = 0.7

    return round(pct_cobertura_nieve * factor_calidad, 1)


def _clasificar_estado_snowline(
    cobertura_efectiva: float,
    tendencia: str,
    ndsi_medio: float
) -> str:
    """Clasifica el estado de la snowline en categorías de riesgo."""
    if cobertura_efectiva > 70 and "bajando" in tendencia:
        return "expansiva_alta_cobertura"
    elif cobertura_efectiva > 70:
        return "alta_cobertura_estable"
    elif cobertura_efectiva > 40:
        return "cobertura_moderada"
    elif "subiendo" in tendencia:
        return "retroceso_snowline"
    else:
        return "cobertura_baja"


def _describir_area_nival(
    cobertura_efectiva: float,
    elevacion_max_m: float = None,
    snowline_m: float = None
) -> str:
    """Describe textualmente el área nival activa."""
    if snowline_m and elevacion_max_m:
        return (
            f"Área nival activa entre {snowline_m:.0f}m y {elevacion_max_m:.0f}m "
            f"({cobertura_efectiva:.0f}% de cobertura efectiva)"
        )
    return f"Cobertura nival efectiva: {cobertura_efectiva:.0f}%"

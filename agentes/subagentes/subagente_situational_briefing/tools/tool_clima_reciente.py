"""
Tool: obtener_clima_reciente_72h

Obtiene las condiciones meteorológicas de las últimas 72 horas para la zona.
Combina datos de condiciones_actuales y tendencia meteorológica de BigQuery.
"""

import logging

logger = logging.getLogger(__name__)

TOOL_CLIMA_RECIENTE = {
    "name": "obtener_clima_reciente_72h",
    "description": (
        "Obtiene condiciones meteorológicas de las últimas 72 horas para la zona: "
        "temperatura min/max/promedio, precipitación acumulada, viento máximo y "
        "dirección dominante, humedad, condición predominante y eventos destacables "
        "(ráfagas, precipitación importante, temperatura en umbral de fusión). "
        "Es la fuente principal de datos recientes para el briefing."
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


def ejecutar_obtener_clima_reciente_72h(ubicacion: str) -> dict:
    return obtener_clima_reciente_72h(ubicacion)


def obtener_clima_reciente_72h(ubicacion: str) -> dict:
    """
    Obtiene condiciones meteorológicas de las últimas 72 horas.

    Combina la lectura de condiciones_actuales (última medición) y la
    tendencia meteorológica (72h de histórico) para construir un resumen
    de las condiciones recientes relevantes para EAWS.

    Args:
        ubicacion: Nombre de la ubicación en BigQuery

    Returns:
        dict con temperatura_promedio_c, temperatura_min_c, temperatura_max_c,
        precipitacion_acumulada_mm, viento_max_kmh, direccion_viento_dominante,
        humedad_relativa_pct, condicion_predominante, eventos_destacables,
        fuente, disponible
    """
    from agentes.datos.consultor_bigquery import ConsultorBigQuery
    consultor = ConsultorBigQuery()

    resultado = {
        "disponible": False,
        "fuente": "clima.condiciones_actuales + clima.condiciones_actuales (72h)",
        "temperatura_promedio_c": None,
        "temperatura_min_c": None,
        "temperatura_max_c": None,
        "precipitacion_acumulada_mm": 0.0,
        "viento_max_kmh": 0.0,
        "direccion_viento_dominante": "sin_datos",
        "humedad_relativa_pct": None,
        "condicion_predominante": "sin_datos",
        "eventos_destacables": [],
    }

    # Condición actual (última medición)
    actuales = consultor.obtener_condiciones_actuales(ubicacion)
    if actuales.get("disponible") is False:
        logger.warning(f"tool_clima_reciente: sin datos actuales para '{ubicacion}'")
        return resultado

    resultado["disponible"] = True
    resultado["temperatura_promedio_c"] = actuales.get("temperatura")
    resultado["temperatura_min_c"] = actuales.get("temperatura")
    resultado["temperatura_max_c"] = actuales.get("temperatura")
    resultado["precipitacion_acumulada_mm"] = actuales.get("precipitacion_acumulada") or 0.0
    resultado["viento_max_kmh"] = (actuales.get("velocidad_viento") or 0.0) * 3.6  # m/s → km/h
    resultado["humedad_relativa_pct"] = actuales.get("humedad_relativa")
    resultado["condicion_predominante"] = actuales.get("condicion_clima", "sin_datos")

    # Convertir dirección de grados a cardinal
    dir_deg = actuales.get("direccion_viento")
    if dir_deg is not None:
        resultado["direccion_viento_dominante"] = _grados_a_cardinal(dir_deg)

    # Tendencia 72h para valores min/max y acumulados
    tendencia = consultor.obtener_tendencia_meteorologica(ubicacion)
    if tendencia.get("disponible") is not False and tendencia.get("total_registros", 0) > 0:
        registros = tendencia.get("registros", [])
        if registros:
            temps = [r.get("temperatura") for r in registros if r.get("temperatura") is not None]
            vientos = [r.get("velocidad_viento", 0) for r in registros]
            precips = [r.get("precipitacion_acumulada", 0) or 0 for r in registros]
            condiciones = [r.get("condicion_clima", "") for r in registros if r.get("condicion_clima")]

            if temps:
                resultado["temperatura_min_c"] = min(temps)
                resultado["temperatura_max_c"] = max(temps)
                resultado["temperatura_promedio_c"] = round(sum(temps) / len(temps), 1)

            if vientos:
                viento_max_ms = max(v for v in vientos if v is not None)
                resultado["viento_max_kmh"] = round(viento_max_ms * 3.6, 1)

            if precips:
                resultado["precipitacion_acumulada_mm"] = round(max(precips), 1)

            if condiciones:
                # Condición más frecuente
                from collections import Counter
                mas_frecuente = Counter(condiciones).most_common(1)[0][0]
                resultado["condicion_predominante"] = mas_frecuente

    # Detectar eventos destacables
    eventos = []
    viento = resultado["viento_max_kmh"] or 0
    temp = resultado["temperatura_promedio_c"]
    precip = resultado["precipitacion_acumulada_mm"] or 0

    if viento > 60:
        eventos.append(f"Ráfagas fuertes: {viento:.0f} km/h")
    elif viento > 40:
        eventos.append(f"Viento significativo: {viento:.0f} km/h")

    if precip > 20:
        eventos.append(f"Precipitación importante: {precip:.0f} mm en 72h")
    elif precip > 5:
        eventos.append(f"Precipitación moderada: {precip:.0f} mm en 72h")

    if temp is not None:
        if temp > 5:
            eventos.append(f"Temperatura sobre cero: {temp:.1f}°C (riesgo fusión)")
        elif -2 <= temp <= 2:
            eventos.append(f"Temperatura en umbral de fusión: {temp:.1f}°C")

    resultado["eventos_destacables"] = eventos

    logger.info(
        f"tool_clima_reciente: '{ubicacion}' — T={resultado['temperatura_promedio_c']}°C, "
        f"precip={resultado['precipitacion_acumulada_mm']}mm, "
        f"viento_max={resultado['viento_max_kmh']}km/h"
    )
    return resultado


def _grados_a_cardinal(grados: float) -> str:
    """Convierte dirección en grados a punto cardinal de 8 posiciones."""
    direcciones = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int(((grados % 360) + 22.5) / 45) % 8
    return direcciones[idx]

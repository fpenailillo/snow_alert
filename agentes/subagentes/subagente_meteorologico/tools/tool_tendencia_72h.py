"""
Tool: analizar_tendencia_72h

Analiza la tendencia meteorológica de las últimas 24h y proyecta
las próximas 48h usando datos de condiciones_actuales y pronostico_horas.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

from agentes.datos.consultor_bigquery import ConsultorBigQuery


TOOL_TENDENCIA_72H = {
    "name": "analizar_tendencia_72h",
    "description": (
        "Analiza la tendencia meteorológica combinando: "
        "(1) historial de las últimas 24h desde condiciones_actuales, "
        "(2) pronóstico horario desde pronostico_horas (si disponible). "
        "Identifica ciclos de temperatura, cambios de viento, "
        "patrones de precipitación y tendencias de fusión/congelación."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación en BigQuery"
            }
        },
        "required": ["nombre_ubicacion"]
    }
}


def ejecutar_analizar_tendencia_72h(nombre_ubicacion: str) -> dict:
    """
    Analiza tendencia meteorológica de 72h (24h pasadas + 48h futuras).

    Args:
        nombre_ubicacion: nombre exacto de la ubicación

    Returns:
        dict con tendencia, ciclos y patrones de riesgo
    """
    consultor = ConsultorBigQuery()
    tendencia = consultor.obtener_tendencia_meteorologica(nombre_ubicacion)

    if "error" in tendencia:
        return tendencia

    # Analizar el historial disponible
    historial = tendencia.get("historial_24h", [])
    resumen_actual = tendencia.get("resumen_actual", {})

    # Calcular estadísticas del historial
    estadisticas = _calcular_estadisticas_historial(historial)

    # Detectar ciclos de temperatura (congelación nocturna / fusión diurna)
    ciclos_temp = _detectar_ciclos_temperatura(historial)

    # Evaluar tendencia de viento
    tendencia_viento = _evaluar_tendencia_viento(historial)

    # Detectar eventos de precipitación
    eventos_precip = _detectar_eventos_precipitacion(historial)

    # Evaluar peligro de fusión-recongelación
    peligro_fusion_congelacion = _evaluar_peligro_fusion_congelacion(
        ciclos_temp=ciclos_temp,
        estadisticas=estadisticas
    )

    return {
        "disponible": True,
        "ubicacion": nombre_ubicacion,
        "horas_analizadas": len(historial),
        "estadisticas_24h": estadisticas,
        "ciclos_temperatura": ciclos_temp,
        "tendencia_viento": tendencia_viento,
        "eventos_precipitacion": eventos_precip,
        "peligro_fusion_congelacion": peligro_fusion_congelacion,
        "resumen_actual": resumen_actual,
        "alertas_tendencia": _compilar_alertas_tendencia(
            estadisticas, ciclos_temp, tendencia_viento, eventos_precip, peligro_fusion_congelacion
        )
    }


def _calcular_estadisticas_historial(historial: list) -> dict:
    """Calcula estadísticas del historial meteorológico."""
    if not historial:
        return {
            "temp_min_C": None,
            "temp_max_C": None,
            "temp_promedio_C": None,
            "viento_max_ms": None,
            "precipitacion_total_mm": 0,
            "horas_con_datos": 0
        }

    temps = [h.get("temperatura") for h in historial if h.get("temperatura") is not None]
    vientos = [h.get("velocidad_viento", 0) for h in historial if h.get("velocidad_viento") is not None]
    precips = [h.get("precipitacion_acumulada", 0) or 0 for h in historial]

    return {
        "temp_min_C": round(min(temps), 1) if temps else None,
        "temp_max_C": round(max(temps), 1) if temps else None,
        "temp_promedio_C": round(sum(temps) / len(temps), 1) if temps else None,
        "variacion_termica_C": round(max(temps) - min(temps), 1) if len(temps) > 1 else 0,
        "viento_max_ms": round(max(vientos), 1) if vientos else None,
        "viento_promedio_ms": round(sum(vientos) / len(vientos), 1) if vientos else None,
        "precipitacion_total_mm": round(sum(precips), 1),
        "horas_con_datos": len(historial)
    }


def _detectar_ciclos_temperatura(historial: list) -> dict:
    """Detecta ciclos de congelación nocturna y fusión diurna."""
    if not historial:
        return {"ciclo_detectado": False}

    temp_dia = []
    temp_noche = []

    for hora in historial:
        temp = hora.get("temperatura")
        es_dia = hora.get("es_dia", True)
        if temp is None:
            continue
        if es_dia:
            temp_dia.append(temp)
        else:
            temp_noche.append(temp)

    temp_dia_prom = sum(temp_dia) / len(temp_dia) if temp_dia else None
    temp_noche_prom = sum(temp_noche) / len(temp_noche) if temp_noche else None

    if temp_dia_prom is None or temp_noche_prom is None:
        return {"ciclo_detectado": False, "temp_dia": temp_dia_prom, "temp_noche": temp_noche_prom}

    amplitud_ciclo = temp_dia_prom - temp_noche_prom
    ciclo_fusion_congelacion = (temp_dia_prom > 0) and (temp_noche_prom < 0)

    return {
        "ciclo_detectado": True,
        "temp_dia_promedio_C": round(temp_dia_prom, 1),
        "temp_noche_promedio_C": round(temp_noche_prom, 1),
        "amplitud_ciclo_C": round(amplitud_ciclo, 1),
        "ciclo_fusion_congelacion": ciclo_fusion_congelacion,
        "alerta_ciclo": "CICLO_FUSION_CONGELACION_ACTIVO" if ciclo_fusion_congelacion else None
    }


def _evaluar_tendencia_viento(historial: list) -> dict:
    """Evalúa la tendencia del viento en el período."""
    if not historial:
        return {"disponible": False}

    vientos = [(i, h.get("velocidad_viento", 0) or 0)
               for i, h in enumerate(historial)
               if h.get("velocidad_viento") is not None]

    if not vientos:
        return {"disponible": False}

    # Dividir en primera y segunda mitad para tendencia
    mitad = len(vientos) // 2
    primera_mitad = [v for _, v in vientos[:mitad]] if mitad > 0 else []
    segunda_mitad = [v for _, v in vientos[mitad:]]

    prom_primera = sum(primera_mitad) / len(primera_mitad) if primera_mitad else 0
    prom_segunda = sum(segunda_mitad) / len(segunda_mitad) if segunda_mitad else 0
    max_viento = max(v for _, v in vientos)

    if prom_segunda > prom_primera + 3:
        tendencia = "en_aumento"
    elif prom_segunda < prom_primera - 3:
        tendencia = "en_descenso"
    else:
        tendencia = "estable"

    return {
        "disponible": True,
        "tendencia": tendencia,
        "promedio_ms": round((prom_primera + prom_segunda) / 2, 1),
        "maximo_ms": round(max_viento, 1),
        "alerta": "VIENTO_EN_AUMENTO" if tendencia == "en_aumento" and max_viento > 10 else None
    }


def _detectar_eventos_precipitacion(historial: list) -> dict:
    """Detecta eventos de precipitación significativos."""
    if not historial:
        return {"eventos": [], "total_mm": 0}

    total_mm = sum(h.get("precipitacion_acumulada", 0) or 0 for h in historial)
    horas_con_precip = sum(
        1 for h in historial
        if (h.get("precipitacion_acumulada") or 0) > 0.5
    )

    eventos = []
    if total_mm > 20:
        eventos.append("PRECIPITACION_ACUMULADA_ALTA")
    elif total_mm > 5:
        eventos.append("PRECIPITACION_ACUMULADA_MODERADA")

    if horas_con_precip > 6:
        eventos.append("PRECIPITACION_PERSISTENTE")

    return {
        "total_mm": round(total_mm, 1),
        "horas_con_precipitacion": horas_con_precip,
        "eventos": eventos
    }


def _evaluar_peligro_fusion_congelacion(
    ciclos_temp: dict,
    estadisticas: dict
) -> dict:
    """Evalúa el peligro específico de ciclos fusión-congelación."""
    peligro = "bajo"
    factores = []

    if ciclos_temp.get("ciclo_fusion_congelacion"):
        peligro = "alto"
        factores.append("CICLO_FUSION_CONGELACION")

    amplitud = ciclos_temp.get("amplitud_ciclo_C", 0)
    if amplitud and amplitud > 10:
        if peligro == "bajo":
            peligro = "moderado"
        factores.append("ALTA_AMPLITUD_TERMICA")

    variacion = estadisticas.get("variacion_termica_C", 0)
    if variacion and variacion > 15:
        factores.append("VARIACION_TERMICA_EXTREMA")

    return {
        "nivel_peligro": peligro,
        "factores": factores,
        "descripcion": _describir_peligro_fusion(peligro, factores)
    }


def _describir_peligro_fusion(peligro: str, factores: list) -> str:
    """Genera descripción del peligro de fusión-congelación."""
    if not factores:
        return "Sin ciclos de fusión-congelación detectados."
    return (
        f"Peligro {peligro} por ciclos fusión-congelación. "
        f"Factores: {', '.join(factores)}. "
        "Posible formación de capas débiles basales y nieve húmeda diurna."
    )


def _compilar_alertas_tendencia(
    estadisticas: dict,
    ciclos_temp: dict,
    tendencia_viento: dict,
    eventos_precip: dict,
    peligro_fusion: dict
) -> list:
    """Compila todas las alertas de tendencia."""
    alertas = []

    if ciclos_temp.get("alerta_ciclo"):
        alertas.append(ciclos_temp["alerta_ciclo"])

    if tendencia_viento.get("alerta"):
        alertas.append(tendencia_viento["alerta"])

    alertas.extend(eventos_precip.get("eventos", []))

    if peligro_fusion.get("nivel_peligro") in ("alto", "muy_alto"):
        alertas.extend(peligro_fusion.get("factores", []))

    viento_max = estadisticas.get("viento_max_ms")
    if viento_max and viento_max > 20:
        alertas.append("VIENTO_MAX_TEMPORAL_24H")

    return list(set(alertas))

"""
Tool: procesar_ndsi

Procesa la serie temporal de NDSI (Normalized Difference Snow Index)
y métricas satelitales desde BigQuery para preparar el análisis ViT.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

from agentes.datos.consultor_bigquery import ConsultorBigQuery


TOOL_PROCESAR_NDSI = {
    "name": "procesar_ndsi",
    "description": (
        "Obtiene y procesa la serie temporal de métricas satelitales de BigQuery "
        "(imagenes_satelitales): NDSI, cobertura de nieve, LST día/noche, "
        "amplitud del ciclo diurno y variación de cobertura 24h. "
        "Estructura los datos como secuencia temporal para el análisis ViT."
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


def ejecutar_procesar_ndsi(nombre_ubicacion: str) -> dict:
    """
    Obtiene y procesa la serie temporal de métricas satelitales.

    Args:
        nombre_ubicacion: nombre exacto de la ubicación en BigQuery

    Returns:
        dict con serie temporal estructurada para ViT y métricas agregadas
    """
    consultor = ConsultorBigQuery()
    datos = consultor.obtener_estado_satelital(nombre_ubicacion)

    if "error" in datos:
        return datos

    if not datos.get("disponible"):
        return {
            "disponible": False,
            "ubicacion": nombre_ubicacion,
            "mensaje": "Sin imágenes satelitales recientes en BigQuery",
            "serie_temporal": [],
            "metricas_agregadas": {}
        }

    # Extraer métricas clave de los datos satelitales
    # El consultor retorna datos del último registro disponible
    ndsi_actual = datos.get("ndsi_medio", 0.0) or 0.0
    cobertura_actual = datos.get("pct_cobertura_nieve", 0.0) or 0.0
    lst_dia = datos.get("lst_dia_celsius")
    lst_noche = datos.get("lst_noche_celsius")
    delta_nieve = datos.get("delta_pct_nieve_24h", 0.0) or 0.0
    alertas_existentes = datos.get("alertas", [])

    # Calcular métricas derivadas
    ciclo_diurno = None
    if lst_dia is not None and lst_noche is not None:
        ciclo_diurno = round(lst_dia - lst_noche, 2)

    # Construir serie temporal desde el historial disponible
    serie_temporal = _construir_serie_temporal(datos)

    # Métricas agregadas para ViT
    metricas_agregadas = _calcular_metricas_agregadas(
        ndsi_actual=ndsi_actual,
        cobertura_actual=cobertura_actual,
        lst_dia=lst_dia,
        lst_noche=lst_noche,
        ciclo_diurno=ciclo_diurno,
        delta_nieve=delta_nieve,
        serie_temporal=serie_temporal
    )

    # Señales de cambio nival
    senales_cambio = _detectar_senales_cambio(
        delta_nieve=delta_nieve,
        ndsi_actual=ndsi_actual,
        cobertura_actual=cobertura_actual,
        alertas_existentes=alertas_existentes
    )

    return {
        "disponible": True,
        "ubicacion": nombre_ubicacion,
        "fuente_principal": datos.get("fuente_principal", "MODIS"),
        "fecha_captura": datos.get("fecha_captura"),
        "metricas_actuales": {
            "ndsi_medio": ndsi_actual,
            "pct_cobertura_nieve": cobertura_actual,
            "lst_dia_celsius": lst_dia,
            "lst_noche_celsius": lst_noche,
            "ciclo_diurno_amplitud": ciclo_diurno,
            "delta_pct_nieve_24h": delta_nieve
        },
        "serie_temporal": serie_temporal,
        "metricas_agregadas": metricas_agregadas,
        "senales_cambio": senales_cambio,
        "alertas_satelitales": alertas_existentes
    }


def _construir_serie_temporal(datos: dict) -> list:
    """
    Construye la serie temporal de métricas satelitales para el ViT.

    Como BigQuery almacena múltiples capturas diarias, construimos la
    secuencia a partir de los datos del historial si están disponibles,
    o sintetizamos una con el registro actual más variaciones estimadas.
    """
    serie = []

    # Si hay historial en los datos
    historial = datos.get("historial_7d", [])
    if historial:
        for registro in historial[-14:]:  # últimas 14 capturas
            ndsi = registro.get("ndsi_medio", 0)
            cobertura = registro.get("pct_cobertura_nieve", 0)
            lst_dia = registro.get("lst_dia_celsius")
            lst_noche = registro.get("lst_noche_celsius")
            ciclo = (
                round(lst_dia - lst_noche, 2)
                if lst_dia is not None and lst_noche is not None
                else None
            )
            serie.append({
                "paso_t": len(serie),
                "fecha": registro.get("fecha_captura"),
                "ndsi_medio": ndsi,
                "pct_cobertura_nieve": cobertura,
                "lst_dia_celsius": lst_dia,
                "lst_noche_celsius": lst_noche,
                "ciclo_diurno_amplitud": ciclo
            })
        return serie

    # Sin historial: usar solo el registro actual como T=0
    ndsi_actual = datos.get("ndsi_medio", 0.0) or 0.0
    cobertura_actual = datos.get("pct_cobertura_nieve", 0.0) or 0.0
    lst_dia = datos.get("lst_dia_celsius")
    lst_noche = datos.get("lst_noche_celsius")
    ciclo_diurno = (
        round(lst_dia - lst_noche, 2)
        if lst_dia is not None and lst_noche is not None
        else None
    )

    serie.append({
        "paso_t": 0,
        "fecha": datos.get("fecha_captura"),
        "ndsi_medio": ndsi_actual,
        "pct_cobertura_nieve": cobertura_actual,
        "lst_dia_celsius": lst_dia,
        "lst_noche_celsius": lst_noche,
        "ciclo_diurno_amplitud": ciclo_diurno
    })
    return serie


def _calcular_metricas_agregadas(
    ndsi_actual: float,
    cobertura_actual: float,
    lst_dia,
    lst_noche,
    ciclo_diurno,
    delta_nieve: float,
    serie_temporal: list
) -> dict:
    """Calcula métricas estadísticas de la serie temporal."""
    if len(serie_temporal) <= 1:
        return {
            "ndsi_promedio": ndsi_actual,
            "cobertura_promedio": cobertura_actual,
            "variabilidad_ndsi": 0.0,
            "tendencia_cobertura": delta_nieve,
            "ciclo_diurno_promedio": ciclo_diurno,
            "puntos_serie": 1
        }

    ndsi_vals = [p.get("ndsi_medio", 0) for p in serie_temporal if p.get("ndsi_medio") is not None]
    cob_vals = [p.get("pct_cobertura_nieve", 0) for p in serie_temporal if p.get("pct_cobertura_nieve") is not None]
    ciclos = [p.get("ciclo_diurno_amplitud") for p in serie_temporal if p.get("ciclo_diurno_amplitud") is not None]

    ndsi_prom = round(sum(ndsi_vals) / len(ndsi_vals), 4) if ndsi_vals else ndsi_actual
    cob_prom = round(sum(cob_vals) / len(cob_vals), 2) if cob_vals else cobertura_actual
    ciclo_prom = round(sum(ciclos) / len(ciclos), 2) if ciclos else ciclo_diurno

    # Variabilidad NDSI (desviación simplificada)
    if len(ndsi_vals) > 1:
        variabilidad = round(max(ndsi_vals) - min(ndsi_vals), 4)
    else:
        variabilidad = 0.0

    return {
        "ndsi_promedio": ndsi_prom,
        "cobertura_promedio": cob_prom,
        "variabilidad_ndsi": variabilidad,
        "tendencia_cobertura": delta_nieve,
        "ciclo_diurno_promedio": ciclo_prom,
        "puntos_serie": len(serie_temporal)
    }


def _detectar_senales_cambio(
    delta_nieve: float,
    ndsi_actual: float,
    cobertura_actual: float,
    alertas_existentes: list
) -> dict:
    """Detecta señales de cambio relevantes para avalanchas."""
    senales = []

    if delta_nieve > 15:
        senales.append("NEVADA_RECIENTE_SIGNIFICATIVA")
    elif delta_nieve > 5:
        senales.append("NEVADA_LEVE_RECIENTE")

    if delta_nieve < -10:
        senales.append("PERDIDA_RAPIDA_COBERTURA_NIVAL")

    if ndsi_actual < 0.4 and cobertura_actual > 50:
        senales.append("NIEVE_HUMEDA_BAJA_REFLECTANCIA")

    # Propagar alertas del consultor
    for alerta in alertas_existentes:
        if alerta not in senales:
            senales.append(alerta)

    return {
        "senales_detectadas": senales,
        "hay_cambio_significativo": len(senales) > 0
    }

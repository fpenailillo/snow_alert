"""
Tool: obtener_contexto_historico

Determina el contexto climatológico y estacional de la zona.
Basado en la fecha actual y características conocidas del Hemisferio Sur andino.
No requiere llamada a API externa — usa reglas calendáricas y promedios históricos.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TOOL_CONTEXTO_HISTORICO = {
    "name": "obtener_contexto_historico",
    "description": (
        "Determina el contexto climatológico y estacional de la zona. "
        "Retorna la época del ciclo de nieve andino (pre-temporada, temporada-temprana, "
        "mid-winter, primavera, fin-temporada), patrón típico para el mes, "
        "nivel de nieve estacional (alto/normal/bajo) y desviación vs promedio histórico. "
        "Usar para contextualizar las condiciones recientes en el ciclo anual."
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


def ejecutar_obtener_contexto_historico(ubicacion: str) -> dict:
    return obtener_contexto_historico(ubicacion)

# Promedios históricos aproximados para La Parva / Valle Nevado (~3200m snm)
# Fuente: datos climatológicos Andes Central, DGA Chile
_CLIMATOLOGIA_ANDES_CENTRAL = {
    # mes: (temp_promedio_c, precipitacion_mm_mes, descripcion)
    1:  ( 6.5,  0.5, "Verano andino: días cálidos, noches frescas, sin nieve reciente"),
    2:  ( 6.2,  1.0, "Fin de verano: posibles tormentas aisladas de alta montaña"),
    3:  ( 3.8,  5.0, "Otoño temprano: primeras nevadas ocasionales sobre 3500m"),
    4:  ( 0.5, 12.0, "Otoño: nevadas esporádicas, inicio acumulación nieve estacional"),
    5:  (-3.0, 35.0, "Pre-temporada: nevadas importantes posibles, cierre vías acceso"),
    6:  (-6.5, 65.0, "Invierno temprano: temporada activa, acumulaciones máximas"),
    7:  (-8.0, 75.0, "Mid-winter: punto máximo peligro avalanchas, fronts frecuentes"),
    8:  (-7.5, 60.0, "Invierno tardío: seguirán tormentas, viento NW intenso"),
    9:  (-4.0, 40.0, "Primavera temprana: fusión superficial, riesgo nieve húmeda"),
    10: ( 0.5, 15.0, "Primavera: fusión activa, reducción cobertura nieve"),
    11: ( 4.0,  3.0, "Fin temporada: manto reducido, acceso a cumbres"),
    12: ( 6.0,  0.5, "Verano: mínima cobertura de nieve, acceso libre"),
}


def obtener_contexto_historico(ubicacion: str) -> dict:
    """
    Determina el contexto climatológico y estacional de la zona.

    Usa la fecha actual para determinar la época estacional en el ciclo
    de nieve andino (Hemisferio Sur). Compara la temperatura actual con
    el promedio histórico para el mes.

    Args:
        ubicacion: Nombre de la ubicación (para personalización futura)

    Returns:
        dict con epoca_estacional, mes_actual, patron_climatologico_tipico,
        desviacion_vs_normal, nivel_nieve_estacional, temperatura_historica_c,
        precipitacion_historica_mes_mm
    """
    from agentes.datos.consultor_bigquery import ConsultorBigQuery

    ahora = datetime.now(timezone.utc)
    mes = ahora.month
    ano = ahora.year

    clima_historico = _CLIMATOLOGIA_ANDES_CENTRAL.get(mes, (0.0, 20.0, "datos no disponibles"))
    temp_hist, precip_hist_mes, descripcion_hist = clima_historico

    # Época estacional (Hemisferio Sur andino)
    if mes in [12, 1, 2]:
        epoca = "fin-temporada"  # Verano austral
    elif mes in [3, 4]:
        epoca = "pre-temporada"
    elif mes in [5, 6]:
        epoca = "temporada-temprana"
    elif mes in [7, 8]:
        epoca = "mid-winter"
    elif mes in [9, 10]:
        epoca = "primavera"
    else:  # 11
        epoca = "fin-temporada"

    nombres_meses = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
    }
    mes_nombre = f"{nombres_meses[mes]} {ano}"

    # Obtener temperatura actual para comparar vs histórico
    desviacion = "comparable con promedio histórico"
    nivel_nieve = "sin_datos"

    try:
        consultor = ConsultorBigQuery()
        actuales = consultor.obtener_condiciones_actuales(ubicacion)
        if actuales.get("disponible") is not False:
            temp_actual = actuales.get("temperatura")
            if temp_actual is not None and temp_hist is not None:
                diff = temp_actual - temp_hist
                if diff > 3:
                    desviacion = f"{diff:.1f}°C sobre el promedio histórico"
                elif diff < -3:
                    desviacion = f"{abs(diff):.1f}°C bajo el promedio histórico"
                else:
                    desviacion = f"dentro del rango histórico (diferencia {diff:+.1f}°C)"
    except Exception as exc:
        logger.warning(f"tool_contexto_historico: no pudo comparar vs histórico — {exc}")

    # Estimación nivel de nieve según época y mes
    if mes in [7, 8, 9]:
        nivel_nieve = "alto"  # Peak season
    elif mes in [5, 6, 10]:
        nivel_nieve = "normal"
    elif mes in [4, 11]:
        nivel_nieve = "bajo"
    else:  # Verano
        nivel_nieve = "bajo"

    resultado = {
        "disponible": True,
        "epoca_estacional": epoca,
        "mes_actual": mes_nombre,
        "patron_climatologico_tipico": descripcion_hist,
        "desviacion_vs_normal": desviacion,
        "nivel_nieve_estacional": nivel_nieve,
        "temperatura_historica_c": temp_hist,
        "precipitacion_historica_mes_mm": precip_hist_mes,
        "hemisferio": "sur",
        "zona_climatica": "Andes Central, Chile (~3000-4100m snm)",
    }

    logger.info(
        f"tool_contexto_historico: '{ubicacion}' — época={epoca}, "
        f"nivel_nieve={nivel_nieve}, desviacion='{desviacion}'"
    )
    return resultado

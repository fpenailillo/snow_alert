"""
Tool: detectar_ventanas_criticas

Detecta ventanas de tiempo con condiciones meteorológicas críticas
para el riesgo de avalanchas: combinaciones de nevada + viento,
ciclos fusión-congelación, y períodos de lluvia sobre nieve.
"""

TOOL_VENTANAS_CRITICAS = {
    "name": "detectar_ventanas_criticas",
    "description": (
        "Detecta ventanas de tiempo críticas para avalanchas combinando "
        "las condiciones actuales, la tendencia 72h y el pronóstico de días. "
        "Identifica: (1) nevada + viento simultáneos, (2) ciclos "
        "fusión-congelación, (3) lluvia sobre nieve, (4) precipitación "
        "intensa sobre manto existente. Produce un calendario de riesgo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "temperatura_actual_C": {
                "type": "number",
                "description": "Temperatura actual en °C"
            },
            "velocidad_viento_actual_ms": {
                "type": "number",
                "description": "Velocidad de viento actual en m/s"
            },
            "precipitacion_actual_mm": {
                "type": "number",
                "description": "Precipitación acumulada actual en mm"
            },
            "alertas_tendencia": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Alertas detectadas en el análisis de tendencia 72h"
            },
            "dias_alto_riesgo": {
                "type": "integer",
                "description": "Número de días de alto riesgo en el pronóstico"
            },
            "dia_mayor_riesgo_fecha": {
                "type": "string",
                "description": "Fecha del día de mayor riesgo pronosticado"
            },
            "dia_mayor_riesgo_nivel": {
                "type": "string",
                "description": "Nivel de riesgo del día más peligroso pronosticado"
            },
            "ciclo_fusion_congelacion": {
                "type": "boolean",
                "description": "¿Hay ciclo activo de fusión-congelación?"
            }
        },
        "required": [
            "temperatura_actual_C",
            "velocidad_viento_actual_ms",
            "precipitacion_actual_mm"
        ]
    }
}


def ejecutar_detectar_ventanas_criticas(
    temperatura_actual_C: float,
    velocidad_viento_actual_ms: float,
    precipitacion_actual_mm: float,
    alertas_tendencia: list = None,
    dias_alto_riesgo: int = 0,
    dia_mayor_riesgo_fecha: str = None,
    dia_mayor_riesgo_nivel: str = None,
    ciclo_fusion_congelacion: bool = False
) -> dict:
    """
    Detecta ventanas críticas de riesgo meteorológico.

    Args:
        temperatura_actual_C: temperatura actual
        velocidad_viento_actual_ms: velocidad de viento actual
        precipitacion_actual_mm: precipitación acumulada
        alertas_tendencia: alertas de la tendencia 72h
        dias_alto_riesgo: días de alto riesgo en pronóstico
        dia_mayor_riesgo_fecha: fecha del día de mayor riesgo
        dia_mayor_riesgo_nivel: nivel de riesgo del día más peligroso
        ciclo_fusion_congelacion: ¿ciclo activo?

    Returns:
        dict con ventanas críticas, periodo de mayor riesgo y recomendaciones
    """
    alertas_tendencia = alertas_tendencia or []
    ventanas = []

    # ─── Ventana 1: Nevada + Viento simultáneos ──────────────────────────────
    nevada_activa = (
        precipitacion_actual_mm > 5
        and temperatura_actual_C is not None
        and temperatura_actual_C <= 0
    )
    viento_fuerte = velocidad_viento_actual_ms > 10

    if nevada_activa and viento_fuerte:
        ventanas.append({
            "tipo": "NEVADA_MAS_VIENTO",
            "severidad": "muy_alta",
            "descripcion": (
                f"Nevada activa ({precipitacion_actual_mm:.0f}mm) con "
                f"viento fuerte ({velocidad_viento_actual_ms:.0f}m/s): "
                "transporte y acumulación de placas de nieve"
            ),
            "tiempo": "actual"
        })

    # ─── Ventana 2: Lluvia sobre nieve ───────────────────────────────────────
    lluvia_sobre_nieve = (
        precipitacion_actual_mm > 3
        and temperatura_actual_C is not None
        and temperatura_actual_C > 2
    )
    if lluvia_sobre_nieve:
        ventanas.append({
            "tipo": "LLUVIA_SOBRE_NIEVE",
            "severidad": "muy_alta",
            "descripcion": (
                f"Lluvia ({precipitacion_actual_mm:.0f}mm) sobre manto nival "
                f"a {temperatura_actual_C:.0f}°C: saturación y deslizamiento húmedo"
            ),
            "tiempo": "actual"
        })

    # ─── Ventana 3: Ciclo fusión-congelación ─────────────────────────────────
    if ciclo_fusion_congelacion:
        ventanas.append({
            "tipo": "CICLO_FUSION_CONGELACION",
            "severidad": "alta",
            "descripcion": (
                "Ciclo diurno con fusión y recongelación: "
                "formación de costras de hielo y capas débiles basales. "
                "Mayor riesgo en horas de mayor insolación."
            ),
            "tiempo": "en_curso"
        })

    # ─── Ventana 4: Viento fuerte sin nevada (transporte de nieve vieja) ─────
    if viento_fuerte and not nevada_activa and velocidad_viento_actual_ms > 15:
        ventanas.append({
            "tipo": "VIENTO_FUERTE_REDISTRIBUCION",
            "severidad": "alta",
            "descripcion": (
                f"Viento fuerte ({velocidad_viento_actual_ms:.0f}m/s) "
                "redistribuye nieve existente: formación de placas en sotavento"
            ),
            "tiempo": "actual"
        })

    # ─── Ventana 5: Pronóstico de días de alto riesgo ─────────────────────────
    if dias_alto_riesgo > 0 and dia_mayor_riesgo_fecha:
        ventanas.append({
            "tipo": "DIA_ALTO_RIESGO_PRONOSTICADO",
            "severidad": "alta" if dia_mayor_riesgo_nivel == "alto" else "muy_alta",
            "descripcion": (
                f"Día de mayor riesgo pronosticado: {dia_mayor_riesgo_fecha} "
                f"(nivel {dia_mayor_riesgo_nivel}). "
                f"Total: {dias_alto_riesgo} días de alto riesgo en período."
            ),
            "tiempo": dia_mayor_riesgo_fecha
        })

    # ─── Ventana 6: Alertas de tendencia 72h ─────────────────────────────────
    alertas_criticas_72h = [
        a for a in alertas_tendencia
        if any(k in a for k in ["PRECIPITACION_ALTA", "FUSION_CONGELACION", "TEMPORAL"])
    ]
    if alertas_criticas_72h:
        ventanas.append({
            "tipo": "ALERTAS_TENDENCIA_72H",
            "severidad": "moderada",
            "descripcion": f"Alertas en tendencia: {', '.join(alertas_criticas_72h)}",
            "tiempo": "próximas_72h"
        })

    # ─── Período de mayor riesgo ──────────────────────────────────────────────
    periodo_mayor_riesgo = _determinar_periodo_mayor_riesgo(
        ventanas=ventanas,
        temperatura=temperatura_actual_C,
        dia_mayor_riesgo_fecha=dia_mayor_riesgo_fecha
    )

    # ─── Clasificación meteorológica para EAWS ────────────────────────────────
    factor_meteorologico_eaws = _clasificar_factor_meteorologico(
        ventanas=ventanas,
        alertas_tendencia=alertas_tendencia,
        precipitacion=precipitacion_actual_mm,
        viento=velocidad_viento_actual_ms,
        temperatura=temperatura_actual_C
    )

    return {
        "ventanas_criticas": ventanas,
        "num_ventanas_criticas": len(ventanas),
        "periodo_mayor_riesgo": periodo_mayor_riesgo,
        "factor_meteorologico_eaws": factor_meteorologico_eaws,
        "condiciones_actuales_resumen": {
            "temperatura_C": temperatura_actual_C,
            "viento_ms": velocidad_viento_actual_ms,
            "precipitacion_mm": precipitacion_actual_mm,
            "nevada_activa": nevada_activa,
            "lluvia_sobre_nieve": lluvia_sobre_nieve
        }
    }


def _determinar_periodo_mayor_riesgo(
    ventanas: list,
    temperatura: float,
    dia_mayor_riesgo_fecha: str
) -> dict:
    """Determina el período de mayor riesgo consolidado."""
    if not ventanas:
        return {"periodo": "sin_ventanas_criticas", "cuando": "no_identificado"}

    # Verificar si hay riesgo actual
    ventanas_actuales = [v for v in ventanas if v.get("tiempo") in ("actual", "en_curso")]

    if ventanas_actuales:
        if temperatura is not None and temperatura > 0:
            cuando = "horas_diurnas_de_mayor_insolacion"
        else:
            cuando = "inmediato_condiciones_actuales"
    elif dia_mayor_riesgo_fecha:
        cuando = dia_mayor_riesgo_fecha
    else:
        cuando = "próximas_48_72h"

    severidades = [v.get("severidad", "baja") for v in ventanas]
    severidad_max = (
        "muy_alta" if "muy_alta" in severidades
        else "alta" if "alta" in severidades
        else "moderada"
    )

    return {
        "periodo": "activo" if ventanas_actuales else "próximo",
        "cuando": cuando,
        "severidad_maxima": severidad_max,
        "num_factores_activos": len(ventanas_actuales)
    }


def _clasificar_factor_meteorologico(
    ventanas: list,
    alertas_tendencia: list,
    precipitacion: float,
    viento: float,
    temperatura: float
) -> str:
    """
    Clasifica el factor meteorológico para EAWS.

    Returns:
        "PRECIPITACION_CRITICA", "NEVADA_RECIENTE", "VIENTO_FUERTE",
        "FUSION_ACTIVA", "CICLO_FUSION_CONGELACION", "LLUVIA_SOBRE_NIEVE",
        "ESTABLE" o combinaciones.

    Umbrales revisados (Müller et al. 2025 / EAWS operational guidelines):
    - VIENTO_FUERTE: >10 m/s (36 km/h) — placas forman desde ~25-36 km/h;
      el umbral anterior (15 m/s = 54 km/h) era demasiado conservador y
      perdía eventos de wind slab frecuentes en La Parva.
    - CICLO_FUSION_CONGELACION: se propaga desde las ventanas detectadas;
      el ciclo es relevante EAWS independientemente de que la temperatura
      media sea > o < 2°C (puede haber ciclo con T_min < 0 y T_max > 0).
    """
    factores = []
    tipos_ventanas = [v.get("tipo", "") for v in ventanas]

    if precipitacion > 30:
        factores.append("PRECIPITACION_CRITICA")
    elif precipitacion > 10:
        factores.append("NEVADA_RECIENTE")

    # Umbral bajado de 15 a 10 m/s: formación de wind slab comienza ~7-10 m/s
    if viento > 10:
        factores.append("VIENTO_FUERTE")

    # CICLO_FUSION_CONGELACION: leer directamente desde ventanas detectadas
    # (la función ejecutar_detectar_ventanas_criticas ya lo evalúa correctamente)
    if "CICLO_FUSION_CONGELACION" in tipos_ventanas:
        factores.append("CICLO_FUSION_CONGELACION")
    elif temperatura is not None and temperatura > 2:
        # FUSION_ACTIVA como señal débil cuando no hay ciclo explícito detectado
        factores.append("FUSION_ACTIVA")

    if "LLUVIA_SOBRE_NIEVE" in tipos_ventanas:
        factores.append("LLUVIA_SOBRE_NIEVE")

    return "+".join(factores) if factores else "ESTABLE"

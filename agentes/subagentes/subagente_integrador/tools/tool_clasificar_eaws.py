"""
Tool: clasificar_riesgo_eaws_integrado

Clasifica el riesgo EAWS final integrando los análisis de los tres
subagentes anteriores (topográfico, satelital, meteorológico) y
aplicando la matriz EAWS oficial.
"""

import sys
import os

_ROOT = os.path.join(os.path.dirname(__file__), '../../../..')  # → snow_alert/
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'datos'))  # → snow_alert/datos/ (dev local)

import logging

from analizador_avalanchas.eaws_constantes import (
    consultar_matriz_eaws,
    estimar_tamano_potencial,
    CLASES_ESTABILIDAD,
    CLASES_FRECUENCIA,
    CLASES_TAMANO,
    NIVELES_PELIGRO
)

logger = logging.getLogger(__name__)


TOOL_CLASIFICAR_EAWS_INTEGRADO = {
    "name": "clasificar_riesgo_eaws_integrado",
    "description": (
        "Clasifica el riesgo EAWS final (niveles 1-5) integrando los "
        "análisis topográfico (PINN), satelital (ViT) y meteorológico. "
        "Determina los 3 factores EAWS (estabilidad, frecuencia, tamaño) "
        "a partir del contexto acumulado y consulta la matriz EAWS oficial. "
        "Produce clasificaciones para 24h, 48h y 72h."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "estabilidad_topografica": {
                "type": "string",
                "description": "Estabilidad EAWS del subagente topográfico: very_poor, poor, fair, good"
            },
            "estabilidad_satelital": {
                "type": "string",
                "description": "Estabilidad EAWS del subagente satelital: very_poor, poor, fair, good"
            },
            "factor_meteorologico": {
                "type": "string",
                "description": "Factor meteorológico EAWS: PRECIPITACION_CRITICA, NEVADA_RECIENTE, VIENTO_FUERTE, FUSION_ACTIVA_CON_CARGA, CICLO_DIURNO_NORMAL (neutro), ESTABLE o combinación"
            },
            "frecuencia_topografica": {
                "type": "string",
                "description": "Frecuencia EAWS ajustada del subagente topográfico: many, some, a_few, nearly_none"
            },
            "tamano_eaws": {
                "type": "string",
                "description": "Tamaño EAWS de la zona: 1, 2, 3, 4, 5"
            },
            "ventanas_criticas_detectadas": {
                "type": "integer",
                "description": "Número de ventanas críticas meteorológicas detectadas"
            },
            "viento_kmh": {
                "type": "number",
                "description": "Velocidad del viento en km/h (para ajuste de frecuencia)"
            },
            "desnivel_inicio_deposito_m": {
                "type": "number",
                "description": "Desnivel vertical entre zona inicio y depósito en metros (para cálculo dinámico de tamaño)"
            },
            "zona_inicio_ha": {
                "type": "number",
                "description": "Hectáreas de zona de inicio de avalanchas (para cálculo dinámico de tamaño)"
            },
            "pendiente_max_grados": {
                "type": "number",
                "description": "Pendiente máxima en grados (para cálculo dinámico de tamaño)"
            },
            "tendencia_pronostico": {
                "type": "string",
                "description": "Tendencia meteorológica del pronóstico 3 días: empeorando, estable, mejorando"
            },
            "dias_consecutivos_nivel_bajo": {
                "type": "integer",
                "description": "Días consecutivos con nivel ≤ 2 (de obtener_historial_ubicacion). Si ≥ 4 y factor ESTABLE, confirma calma sostenida."
            }
        },
        "required": [
            "estabilidad_topografica",
            "factor_meteorologico"
        ]
    }
}


# Mapa de factores meteorológicos a ajuste de estabilidad
_AJUSTE_METEOROLOGICO = {
    "PRECIPITACION_CRITICA": "very_poor",
    "LLUVIA_SOBRE_NIEVE":    "very_poor",
    "NEVADA_RECIENTE+FUSION_ACTIVA_CON_CARGA": "very_poor",
    "NEVADA_RECIENTE+VIENTO_FUERTE": "poor",
    "NEVADA_RECIENTE":           "poor",
    "VIENTO_FUERTE":             "poor",
    "FUSION_ACTIVA_CON_CARGA":   "poor",   # REQ-06: ciclo térmico + carga reciente
    "FUSION_ACTIVA":             "poor",   # compatibilidad retroactiva
    "CICLO_FUSION_CONGELACION":  "poor",   # compatibilidad retroactiva
    "CICLO_DIURNO_NORMAL":       None,     # REQ-06: fenómeno geográfico neutro, sin ajuste
    "ESTABLE":                   None,     # Sin ajuste
}

# Factores que NO son activos para la lógica de calma sostenida (REQ-06)
_FACTORES_NEUTROS = frozenset({"ESTABLE", "CICLO_DIURNO_NORMAL", ""})


def ejecutar_clasificar_riesgo_eaws_integrado(
    estabilidad_topografica: str,
    factor_meteorologico: str,
    estabilidad_satelital: str = None,
    frecuencia_topografica: str = None,
    tamano_eaws: str = None,
    ventanas_criticas_detectadas: int = 0,
    viento_kmh: float = None,
    desnivel_inicio_deposito_m: float = None,
    zona_inicio_ha: float = None,
    pendiente_max_grados: float = None,
    tendencia_pronostico: str = None,
    dias_consecutivos_nivel_bajo: int = 0,
) -> dict:
    """
    Clasifica el riesgo EAWS integrando los análisis de todos los subagentes.

    Args:
        estabilidad_topografica: clasificación EAWS del análisis topográfico
        factor_meteorologico: factor del análisis meteorológico
        estabilidad_satelital: clasificación EAWS del análisis satelital
        frecuencia_topografica: frecuencia EAWS del subagente topográfico
        tamano_eaws: tamaño EAWS explícito (1-5), se calcula dinámicamente si no se provee
        ventanas_criticas_detectadas: número de ventanas críticas
        viento_kmh: velocidad del viento en km/h (incrementa frecuencia si >40)
        desnivel_inicio_deposito_m: desnivel vertical para cálculo dinámico de tamaño
        zona_inicio_ha: hectáreas de zona de inicio para cálculo dinámico de tamaño
        pendiente_max_grados: pendiente máxima para cálculo dinámico de tamaño

    Returns:
        dict con nivel EAWS 24h/48h/72h, factores y recomendaciones
    """
    # ─── 1. Determinar estabilidad dominante ─────────────────────────────────
    estabilidad_final = _determinar_estabilidad_dominante(
        estabilidad_topografica=estabilidad_topografica,
        estabilidad_satelital=estabilidad_satelital,
        factor_meteorologico=factor_meteorologico,
        dias_consecutivos_nivel_bajo=dias_consecutivos_nivel_bajo,
    )

    # ─── 2. Ajustar frecuencia ───────────────────────────────────────────────
    frecuencia_final = _determinar_frecuencia(
        frecuencia_topografica=frecuencia_topografica,
        ventanas_criticas=ventanas_criticas_detectadas,
        factor_meteorologico=factor_meteorologico,
        estabilidad=estabilidad_final,
        viento_kmh=viento_kmh
    )

    # ─── 3. Determinar tamaño (dinámico desde topografía si es posible) ──────
    tamano_final, fuente_tamano = _determinar_tamano(
        tamano_eaws=tamano_eaws,
        desnivel_inicio_deposito_m=desnivel_inicio_deposito_m,
        zona_inicio_ha=zona_inicio_ha,
        pendiente_max_grados=pendiente_max_grados
    )

    # ─── 4. Consultar matriz EAWS ─────────────────────────────────────────────
    # consultar_matriz_eaws devuelve Tuple[int, Optional[int]] → (D1, D2)
    nivel_d1, nivel_d2 = consultar_matriz_eaws(
        estabilidad=estabilidad_final,
        frecuencia=frecuencia_final,
        tamano=tamano_final
    )
    nivel_24h = nivel_d1  # Nivel primario

    # Información del nivel desde NIVELES_PELIGRO
    info_nivel = NIVELES_PELIGRO.get(nivel_24h, {})

    # ─── 5. Proyección 48h y 72h ─────────────────────────────────────────────
    nivel_48h = _proyectar_nivel(nivel_24h, factor_meteorologico, horas=48, tendencia_pronostico=tendencia_pronostico)
    nivel_72h = _proyectar_nivel(nivel_24h, factor_meteorologico, horas=72, tendencia_pronostico=tendencia_pronostico)

    # ─── 6. Recomendaciones EAWS ─────────────────────────────────────────────
    recomendaciones = []
    if ventanas_criticas_detectadas > 0:
        recomendaciones.append(
            f"Se detectaron {ventanas_criticas_detectadas} ventanas criticas "
            "meteorologicas — monitoreo continuo recomendado"
        )
    if viento_kmh and viento_kmh > 40:
        recomendaciones.append(
            f"Viento fuerte detectado ({viento_kmh:.0f} km/h) — "
            "transporte eolico activo incrementa frecuencia de avalanchas"
        )

    return {
        "nivel_eaws_24h": nivel_24h,
        "nivel_eaws_48h": nivel_48h,
        "nivel_eaws_72h": nivel_72h,
        "nombre_nivel_24h": info_nivel.get("nombre"),
        "factores_eaws": {
            "estabilidad": estabilidad_final,
            "frecuencia": frecuencia_final,
            "tamano": tamano_final,
            "fuente_tamano": fuente_tamano
        },
        "fuentes_estabilidad": {
            "topografica_pinn": estabilidad_topografica,
            "satelital_vit": estabilidad_satelital,
            "ajuste_meteorologico": _obtener_ajuste_meteorologico(factor_meteorologico)
        },
        "factor_meteorologico": factor_meteorologico,
        "tendencia_pronostico": tendencia_pronostico,
        "viento_kmh": viento_kmh,
        "recomendaciones": recomendaciones,
        "descripcion_nivel": info_nivel.get("descripcion", "")
    }


def _determinar_estabilidad_dominante(
    estabilidad_topografica: str,
    estabilidad_satelital: str,
    factor_meteorologico: str,
    dias_consecutivos_nivel_bajo: int = 0,
) -> str:
    """
    Determina la estabilidad dominante combinando todas las fuentes.

    Reglas:
    - Si el factor meteorológico implica una estabilidad peor → prioridad
    - Si las fuentes topo y satelital difieren → tomar la peor
    - Si calma sostenida confirmada (días_nivel_bajo ≥ 4 y factor ESTABLE) → cap en 'fair'
      para evitar el piso artificial en nivel 3 causado por topografía estática del PINN.
    """
    escala = ["good", "fair", "poor", "very_poor"]

    # Estabilidad base: la peor entre topo y satelital
    idx_topo = escala.index(estabilidad_topografica) if estabilidad_topografica in escala else 1
    idx_sat = escala.index(estabilidad_satelital) if estabilidad_satelital in escala else 1
    idx_base = max(idx_topo, idx_sat)

    # Ajuste meteorológico
    ajuste_meteo = _obtener_ajuste_meteorologico(factor_meteorologico)
    if ajuste_meteo and ajuste_meteo in escala:
        idx_meteo = escala.index(ajuste_meteo)
        idx_final = max(idx_base, idx_meteo)
    else:
        idx_final = idx_base

    # Confirmación de calma sostenida: si ≥ 4 días consecutivos nivel ≤ 2 y sin
    # factor meteorológico activo, el PINN topográfico puede estar sobreestimando.
    # Cap en 'fair' (índice 1) para evitar piso artificial en nivel 3.
    # REQ-06: CICLO_DIURNO_NORMAL es neutro (igual que ESTABLE) para la lógica de calma
    _factor_activo = bool(
        factor_meteorologico
        and factor_meteorologico not in _FACTORES_NEUTROS
    )
    if dias_consecutivos_nivel_bajo >= 4 and not _factor_activo:
        idx_final = min(idx_final, 1)  # cap en 'fair'
        logger.info(
            f"[ClasificarEAWS] Calma sostenida confirmada ({dias_consecutivos_nivel_bajo} días "
            f"nivel≤2, factor={factor_meteorologico}) — estabilidad capada en 'fair'"
        )

    return escala[idx_final]


def _obtener_ajuste_meteorologico(factor_meteorologico: str) -> str:
    """Obtiene el ajuste de estabilidad del factor meteorológico."""
    for patron, ajuste in _AJUSTE_METEOROLOGICO.items():
        if patron in factor_meteorologico:
            return ajuste
    return None


def _determinar_frecuencia(
    frecuencia_topografica: str,
    ventanas_criticas: int,
    factor_meteorologico: str,
    estabilidad: str,
    viento_kmh: float = None
) -> str:
    """
    Determina la frecuencia EAWS final.

    Incorpora viento como factor directo: viento >40 km/h incrementa
    la clase de frecuencia en 1 (transporte eólico activo redistribuye
    nieve hacia zonas de acumulación, aumentando probabilidad de
    desprendimiento).
    """
    escala = ["nearly_none", "a_few", "some", "many"]

    idx_base = escala.index(frecuencia_topografica) if frecuencia_topografica in escala else 1

    # Ajuste por ventanas críticas
    if ventanas_criticas >= 3:
        idx_base = min(3, idx_base + 1)

    # Ajuste por viento fuerte (C3: >40 km/h → transporte eólico activo)
    if viento_kmh and viento_kmh > 40:
        idx_base = min(3, idx_base + 1)
        if viento_kmh > 70:
            # Viento extremo → sube otro nivel más
            idx_base = min(3, idx_base + 1)

    # Ajuste por estabilidad: si very_poor → frecuencia sube
    if estabilidad == "very_poor" and idx_base < 2:
        idx_base = 2  # Al menos "some"

    # Ajuste por factor meteorológico de precipitación crítica
    if "PRECIPITACION_CRITICA" in factor_meteorologico:
        idx_base = min(3, idx_base + 1)

    return escala[idx_base]


def _determinar_tamano(
    tamano_eaws: str = None,
    desnivel_inicio_deposito_m: float = None,
    zona_inicio_ha: float = None,
    pendiente_max_grados: float = None
) -> tuple:
    """
    Determina el tamaño EAWS dinámicamente usando estimar_tamano_potencial()
    cuando hay datos topográficos disponibles.

    Returns:
        tuple: (tamano_int, fuente_str)
    """
    # Si se pasó explícitamente un tamaño, usarlo
    if tamano_eaws and tamano_eaws in ["1", "2", "3", "4", "5"]:
        return int(tamano_eaws), "explicito"

    # Calcular dinámicamente si hay datos topográficos suficientes
    if desnivel_inicio_deposito_m is not None and desnivel_inicio_deposito_m > 0:
        ha = zona_inicio_ha if zona_inicio_ha and zona_inicio_ha > 0 else 25.0
        pendiente = pendiente_max_grados if pendiente_max_grados and pendiente_max_grados > 0 else 38.0

        tamano = estimar_tamano_potencial(
            desnivel_inicio_deposito=desnivel_inicio_deposito_m,
            ha_zona_inicio=ha,
            pendiente_max=pendiente
        )
        logger.info(
            f"Tamaño EAWS calculado dinámicamente: {tamano} "
            f"(desnivel={desnivel_inicio_deposito_m}m, ha={ha}, pendiente={pendiente}°)"
        )
        return tamano, "estimar_tamano_potencial"

    # Fallback: default 2 (mediano)
    return 2, "default"


def _proyectar_nivel(
    nivel_24h: int,
    factor_meteorologico: str,
    horas: int,
    tendencia_pronostico: str = None
) -> int:
    """
    Proyecta el nivel EAWS para 48h y 72h.

    Incorpora tendencia_pronostico (empeorando/estable/mejorando) para
    proyecciones más realistas. Sin tendencia, aplica reglas conservadoras
    por factor meteorológico.

    Reglas por factor:
    - PRECIPITACION_CRITICA / LLUVIA_SOBRE_NIEVE: sube en 48h, depende de tendencia en 72h
    - FUSION_ACTIVA / CICLO_FUSION_CONGELACION: mantiene ambos días salvo mejora confirmada
    - NEVADA_RECIENTE + VIENTO: mantiene en 48h, puede bajar en 72h si mejora
    - ESTABLE: mantiene en 48h, baja 1 en 72h
    - General: mantiene; si mejorando baja 1 en 72h, si empeorando sube 1 en 48h
    """
    mejorando = tendencia_pronostico == "mejorando"
    empeorando = tendencia_pronostico == "empeorando"

    # Precipitación crítica o lluvia sobre nieve → situación en aumento
    if "PRECIPITACION_CRITICA" in factor_meteorologico or "LLUVIA_SOBRE_NIEVE" in factor_meteorologico:
        if horas == 48:
            return min(5, nivel_24h + 1)
        else:  # 72h
            if mejorando:
                return max(1, nivel_24h - 1)
            return nivel_24h  # Sin mejora confirmada, mantener

    # Factor estable o ciclo diurno normal → reducción progresiva (REQ-06)
    if factor_meteorologico in ("ESTABLE", "CICLO_DIURNO_NORMAL") or factor_meteorologico not in _AJUSTE_METEOROLOGICO:
        if horas == 72:
            return max(1, nivel_24h - 1)
        return nivel_24h

    # Fusión activa con carga, ciclo fusión-congelación (compatibilidad) → persiste
    if "FUSION_ACTIVA" in factor_meteorologico or "CICLO_FUSION_CONGELACION" in factor_meteorologico:
        if horas == 48:
            if empeorando:
                return min(5, nivel_24h + 1)
            return nivel_24h  # Fusión no remite en 24h
        else:  # 72h
            if mejorando:
                return max(1, nivel_24h - 1)
            return nivel_24h  # Sin cambio de temperatura confirmado, mantener

    # Caso general (NEVADA_RECIENTE, VIENTO_FUERTE, etc.)
    if horas == 48:
        if empeorando:
            return min(5, nivel_24h + 1)
        return nivel_24h
    else:  # 72h
        if mejorando and nivel_24h > 1:
            return nivel_24h - 1
        if not empeorando and nivel_24h > 2:
            # Sin tendencia clara: reducción conservadora solo desde nivel ≥3
            return nivel_24h - 1
        return nivel_24h

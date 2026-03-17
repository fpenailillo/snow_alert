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

from analizador_avalanchas.eaws_constantes import (
    consultar_matriz_eaws,
    CLASES_ESTABILIDAD,
    CLASES_FRECUENCIA,
    CLASES_TAMANO,
    NIVELES_PELIGRO
)


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
                "description": "Factor meteorológico EAWS: PRECIPITACION_CRITICA, NEVADA_RECIENTE, VIENTO_FUERTE, FUSION_ACTIVA, ESTABLE o combinación"
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
    "LLUVIA_SOBRE_NIEVE": "very_poor",
    "NEVADA_RECIENTE+FUSION_ACTIVA": "very_poor",
    "NEVADA_RECIENTE+VIENTO_FUERTE": "poor",
    "NEVADA_RECIENTE": "poor",
    "VIENTO_FUERTE": "poor",
    "FUSION_ACTIVA": "poor",
    "CICLO_FUSION_CONGELACION": "poor",
    "ESTABLE": None  # Sin ajuste
}


def ejecutar_clasificar_riesgo_eaws_integrado(
    estabilidad_topografica: str,
    factor_meteorologico: str,
    estabilidad_satelital: str = None,
    frecuencia_topografica: str = None,
    tamano_eaws: str = None,
    ventanas_criticas_detectadas: int = 0
) -> dict:
    """
    Clasifica el riesgo EAWS integrando los análisis de todos los subagentes.

    Args:
        estabilidad_topografica: clasificación EAWS del análisis topográfico
        factor_meteorologico: factor del análisis meteorológico
        estabilidad_satelital: clasificación EAWS del análisis satelital
        frecuencia_topografica: frecuencia EAWS del subagente topográfico
        tamano_eaws: tamaño EAWS de zonas de avalancha
        ventanas_criticas_detectadas: número de ventanas críticas

    Returns:
        dict con nivel EAWS 24h/48h/72h, factores y recomendaciones
    """
    # ─── 1. Determinar estabilidad dominante ─────────────────────────────────
    estabilidad_final = _determinar_estabilidad_dominante(
        estabilidad_topografica=estabilidad_topografica,
        estabilidad_satelital=estabilidad_satelital,
        factor_meteorologico=factor_meteorologico
    )

    # ─── 2. Ajustar frecuencia ───────────────────────────────────────────────
    frecuencia_final = _determinar_frecuencia(
        frecuencia_topografica=frecuencia_topografica,
        ventanas_criticas=ventanas_criticas_detectadas,
        factor_meteorologico=factor_meteorologico,
        estabilidad=estabilidad_final
    )

    # ─── 3. Determinar tamaño ────────────────────────────────────────────────
    tamano_final = tamano_eaws or "2"  # Default: mediano
    # Validar que esté en el rango
    if tamano_final not in ["1", "2", "3", "4", "5"]:
        tamano_final = "2"

    # ─── 4. Consultar matriz EAWS ─────────────────────────────────────────────
    # consultar_matriz_eaws devuelve Tuple[int, Optional[int]] → (D1, D2)
    nivel_d1, nivel_d2 = consultar_matriz_eaws(
        estabilidad=estabilidad_final,
        frecuencia=frecuencia_final,
        tamano=int(tamano_final)
    )
    nivel_24h = nivel_d1  # Nivel primario

    # Información del nivel desde NIVELES_PELIGRO
    info_nivel = NIVELES_PELIGRO.get(nivel_24h, {})

    # ─── 5. Proyección 48h y 72h ─────────────────────────────────────────────
    nivel_48h = _proyectar_nivel(nivel_24h, factor_meteorologico, horas=48)
    nivel_72h = _proyectar_nivel(nivel_24h, factor_meteorologico, horas=72)

    # ─── 6. Recomendaciones EAWS ─────────────────────────────────────────────
    recomendaciones = []
    if ventanas_criticas_detectadas > 0:
        recomendaciones.append(
            f"⚠️ Se detectaron {ventanas_criticas_detectadas} ventanas críticas "
            "meteorológicas — monitoreo continuo recomendado"
        )

    return {
        "nivel_eaws_24h": nivel_24h,
        "nivel_eaws_48h": nivel_48h,
        "nivel_eaws_72h": nivel_72h,
        "nombre_nivel_24h": info_nivel.get("nombre"),
        "factores_eaws": {
            "estabilidad": estabilidad_final,
            "frecuencia": frecuencia_final,
            "tamano": int(tamano_final)
        },
        "fuentes_estabilidad": {
            "topografica_pinn": estabilidad_topografica,
            "satelital_vit": estabilidad_satelital,
            "ajuste_meteorologico": _obtener_ajuste_meteorologico(factor_meteorologico)
        },
        "factor_meteorologico": factor_meteorologico,
        "recomendaciones": recomendaciones,
        "descripcion_nivel": info_nivel.get("descripcion", "")
    }


def _determinar_estabilidad_dominante(
    estabilidad_topografica: str,
    estabilidad_satelital: str,
    factor_meteorologico: str
) -> str:
    """
    Determina la estabilidad dominante combinando todas las fuentes.

    Reglas:
    - Si el factor meteorológico implica una estabilidad peor → prioridad
    - Si las fuentes topo y satelital difieren → tomar la peor
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
    estabilidad: str
) -> str:
    """Determina la frecuencia EAWS final."""
    escala = ["nearly_none", "a_few", "some", "many"]

    idx_base = escala.index(frecuencia_topografica) if frecuencia_topografica in escala else 1

    # Ajuste por ventanas críticas
    if ventanas_criticas >= 3:
        idx_base = min(3, idx_base + 1)
    elif ventanas_criticas >= 2:
        idx_base = min(3, idx_base + 0)  # Sin cambio automático, ya está incorporado

    # Ajuste por estabilidad: si very_poor → frecuencia sube
    if estabilidad == "very_poor" and idx_base < 2:
        idx_base = 2  # Al menos "some"

    # Ajuste por factor meteorológico de precipitación crítica
    if "PRECIPITACION_CRITICA" in factor_meteorologico:
        idx_base = min(3, idx_base + 1)

    return escala[idx_base]


def _proyectar_nivel(nivel_24h: int, factor_meteorologico: str, horas: int) -> int:
    """
    Proyecta el nivel EAWS para 48h y 72h.

    Reglas:
    - Si hay precipitación crítica activa → nivel sube o mantiene en 48h
    - Si factor es estable → puede bajar en 72h
    """
    if factor_meteorologico == "ESTABLE":
        if horas == 72:
            return max(1, nivel_24h - 1)
        return nivel_24h

    if "PRECIPITACION_CRITICA" in factor_meteorologico or "LLUVIA_SOBRE_NIEVE" in factor_meteorologico:
        if horas == 48:
            return min(5, nivel_24h + 1)
        else:  # 72h: puede bajar si cesa la precipitación
            return nivel_24h

    # Caso general: nivel se mantiene o baja levemente
    if horas == 72 and nivel_24h > 2:
        return nivel_24h - 1
    return nivel_24h

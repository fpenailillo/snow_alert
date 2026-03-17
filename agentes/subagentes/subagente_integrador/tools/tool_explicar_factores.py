"""
Tool: explicar_factores_riesgo

Genera una explicación detallada de los factores de riesgo identificados,
integrando los análisis PINN, ViT y meteorológico para comunicar
el riesgo de forma clara y accionable.
"""

TOOL_EXPLICAR_FACTORES = {
    "name": "explicar_factores_riesgo",
    "description": (
        "Genera una explicación detallada y accionable de los factores de "
        "riesgo identificados por los tres subagentes (PINN, ViT, "
        "meteorológico). Produce texto explicativo para el boletín final "
        "que describe el manto nival, las causas del riesgo y la "
        "confianza del análisis multi-agente."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nivel_eaws_24h": {
                "type": "integer",
                "description": "Nivel EAWS final para 24h"
            },
            "estado_pinn": {
                "type": "string",
                "description": "Estado PINN del manto: CRITICO, INESTABLE, MARGINAL, ESTABLE"
            },
            "factor_seguridad_pinn": {
                "type": "number",
                "description": "Factor de seguridad Mohr-Coulomb del PINN"
            },
            "estado_vit": {
                "type": "string",
                "description": "Estado ViT: CRITICO, ALERTADO, MODERADO, ESTABLE"
            },
            "score_vit": {
                "type": "number",
                "description": "Score de anomalía del ViT"
            },
            "alertas_satelitales": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de alertas satelitales detectadas"
            },
            "factor_meteorologico": {
                "type": "string",
                "description": "Factor meteorológico EAWS"
            },
            "ventanas_criticas": {
                "type": "integer",
                "description": "Número de ventanas críticas meteorológicas"
            },
            "confianza_topografica": {
                "type": "string",
                "description": "Confianza del análisis topográfico: alta, media, baja"
            }
        },
        "required": [
            "nivel_eaws_24h",
            "estado_pinn",
            "estado_vit",
            "factor_meteorologico"
        ]
    }
}


def ejecutar_explicar_factores_riesgo(
    nivel_eaws_24h: int,
    estado_pinn: str,
    estado_vit: str,
    factor_meteorologico: str,
    factor_seguridad_pinn: float = None,
    score_vit: float = None,
    alertas_satelitales: list = None,
    ventanas_criticas: int = 0,
    confianza_topografica: str = "media"
) -> dict:
    """
    Genera explicación detallada de factores de riesgo.

    Args:
        nivel_eaws_24h: nivel EAWS final
        estado_pinn: estado del modelo PINN
        estado_vit: estado del modelo ViT
        factor_meteorologico: factor meteorológico principal
        factor_seguridad_pinn: factor de seguridad Mohr-Coulomb
        score_vit: score de anomalía ViT
        alertas_satelitales: alertas del análisis satelital
        ventanas_criticas: número de ventanas críticas
        confianza_topografica: nivel de confianza topográfica

    Returns:
        dict con explicaciones detalladas por subagente y confianza global
    """
    alertas_satelitales = alertas_satelitales or []

    # Explicación PINN
    explicacion_pinn = _explicar_pinn(
        estado=estado_pinn,
        factor_seguridad=factor_seguridad_pinn
    )

    # Explicación ViT
    explicacion_vit = _explicar_vit(
        estado=estado_vit,
        score=score_vit,
        alertas=alertas_satelitales
    )

    # Explicación meteorológica
    explicacion_meteo = _explicar_meteorologia(
        factor=factor_meteorologico,
        ventanas=ventanas_criticas
    )

    # Coherencia entre subagentes
    coherencia = _evaluar_coherencia(
        estado_pinn=estado_pinn,
        estado_vit=estado_vit,
        factor_meteorologico=factor_meteorologico,
        nivel=nivel_eaws_24h
    )

    # Confianza global del análisis
    confianza_global = _calcular_confianza_global(
        confianza_topo=confianza_topografica,
        coherencia=coherencia["nivel"],
        tiene_datos_satelitales=(estado_vit != "sin_datos"),
        tiene_datos_meteo=(factor_meteorologico != "")
    )

    # Mensaje principal de explicación
    mensaje_principal = _generar_mensaje_principal(
        nivel=nivel_eaws_24h,
        estado_pinn=estado_pinn,
        estado_vit=estado_vit,
        factor_meteorologico=factor_meteorologico,
        ventanas=ventanas_criticas
    )

    return {
        "mensaje_principal": mensaje_principal,
        "explicacion_pinn": explicacion_pinn,
        "explicacion_vit": explicacion_vit,
        "explicacion_meteorologica": explicacion_meteo,
        "coherencia_subagentes": coherencia,
        "confianza_global": confianza_global,
        "factores_determinantes": _identificar_factores_determinantes(
            estado_pinn, estado_vit, factor_meteorologico, nivel_eaws_24h
        )
    }


def _explicar_pinn(estado: str, factor_seguridad: float = None) -> str:
    """Genera explicación del análisis PINN."""
    fs_texto = f" (FS={factor_seguridad:.2f})" if factor_seguridad else ""

    explicaciones = {
        "CRITICO": (
            f"El modelo PINN detecta condiciones CRÍTICAS{fs_texto}. "
            "El criterio de Mohr-Coulomb indica que la tensión de cizalle "
            "aplicada supera la resistencia del manto nival. "
            "La dinámica física del manto muestra alta propensión a la falla."
        ),
        "INESTABLE": (
            f"El modelo PINN detecta condiciones INESTABLES{fs_texto}. "
            "El factor de seguridad está por debajo del umbral recomendado. "
            "Las métricas físicas (densidad, gradiente térmico, metamorfismo) "
            "indican un manto vulnerable a perturbaciones adicionales."
        ),
        "MARGINAL": (
            f"El modelo PINN detecta estabilidad MARGINAL{fs_texto}. "
            "El manto nival se mantiene pero con escaso margen de seguridad. "
            "Cambios adicionales en temperatura o precipitación podrían "
            "desencadenar inestabilidad."
        ),
        "ESTABLE": (
            f"El modelo PINN indica condiciones ESTABLES{fs_texto}. "
            "Las métricas físicas del manto nival muestran resistencia "
            "adecuada frente a las cargas actuales."
        )
    }
    return explicaciones.get(estado, f"Estado PINN: {estado}{fs_texto}")


def _explicar_vit(estado: str, score: float = None, alertas: list = None) -> str:
    """Genera explicación del análisis ViT."""
    score_texto = f" (score={score:.1f})" if score is not None else ""
    alertas_texto = f" Alertas: {', '.join(alertas[:3])}." if alertas else ""

    explicaciones = {
        "CRITICO": (
            f"El Vision Transformer detecta condiciones CRÍTICAS en la "
            f"serie temporal satelital{score_texto}. "
            f"Los pesos de atención señalan eventos anómalos recientes "
            f"con alta probabilidad de impacto en la estabilidad.{alertas_texto}"
        ),
        "ALERTADO": (
            f"El Vision Transformer detecta una ALERTA en la serie temporal{score_texto}. "
            f"Cambios significativos en NDSI o cobertura nival requieren atención.{alertas_texto}"
        ),
        "MODERADO": (
            f"El Vision Transformer detecta condiciones MODERADAS{score_texto}. "
            f"Algunos cambios en el manto nival satelital, "
            f"monitoreo continuo recomendado."
        ),
        "ESTABLE": (
            f"El Vision Transformer indica condiciones ESTABLES{score_texto}. "
            "La serie temporal satelital muestra poca variabilidad."
        )
    }
    return explicaciones.get(estado, f"Estado ViT: {estado}{score_texto}")


def _explicar_meteorologia(factor: str, ventanas: int) -> str:
    """Genera explicación del factor meteorológico."""
    ventanas_texto = (
        f" Se detectaron {ventanas} ventanas críticas meteorológicas."
        if ventanas > 0 else ""
    )

    if "PRECIPITACION_CRITICA" in factor:
        return (
            f"La meteorología es el factor dominante: PRECIPITACIÓN CRÍTICA activa. "
            f"El aporte masivo de nieve nueva sobrecargaría el manto existente.{ventanas_texto}"
        )
    elif "LLUVIA_SOBRE_NIEVE" in factor:
        return (
            "Factor meteorológico CRÍTICO: LLUVIA SOBRE NIEVE. "
            "La lluvia satura el manto nival y activa el deslizamiento húmedo. "
            f"Máximo nivel de precaución.{ventanas_texto}"
        )
    elif "NEVADA_RECIENTE" in factor:
        return (
            "Factor meteorológico IMPORTANTE: NEVADA RECIENTE. "
            "Nieve nueva aún no consolidada sobre manto existente. "
            f"Período de asentamiento crítico en las próximas horas.{ventanas_texto}"
        )
    elif "VIENTO_FUERTE" in factor:
        return (
            "Factor meteorológico SIGNIFICATIVO: VIENTO FUERTE. "
            "Redistribución activa de nieve y formación de placas en sotavento. "
            f"Precaución especial en orientaciones de sotavento.{ventanas_texto}"
        )
    elif "FUSION_ACTIVA" in factor:
        return (
            "Factor meteorológico: FUSIÓN ACTIVA. "
            "Temperaturas sobre el punto de fusión activan la inestabilidad húmeda. "
            f"Mayor riesgo en horas de mayor insolación.{ventanas_texto}"
        )
    else:
        return (
            f"Condiciones meteorológicas relativamente estables. "
            f"Sin factores meteorológicos críticos activos.{ventanas_texto}"
        )


def _evaluar_coherencia(
    estado_pinn: str,
    estado_vit: str,
    factor_meteorologico: str,
    nivel: int
) -> dict:
    """Evalúa la coherencia entre los tres subagentes."""
    votos_alto_riesgo = 0

    if estado_pinn in ("CRITICO", "INESTABLE"):
        votos_alto_riesgo += 1
    if estado_vit in ("CRITICO", "ALERTADO"):
        votos_alto_riesgo += 1
    if factor_meteorologico not in ("ESTABLE", ""):
        votos_alto_riesgo += 1

    if votos_alto_riesgo == 3:
        nivel_coherencia = "alta"
        mensaje = "Los tres subagentes coinciden en condiciones de riesgo elevado."
    elif votos_alto_riesgo == 2:
        nivel_coherencia = "media"
        mensaje = "Dos de los tres subagentes identifican factores de riesgo."
    elif votos_alto_riesgo == 1:
        nivel_coherencia = "media"
        mensaje = "Solo un subagente identifica factores de riesgo significativos."
    else:
        nivel_coherencia = "alta"
        mensaje = "Los tres subagentes coinciden en condiciones de bajo riesgo."

    return {
        "nivel": nivel_coherencia,
        "votos_alto_riesgo": votos_alto_riesgo,
        "mensaje": mensaje
    }


def _calcular_confianza_global(
    confianza_topo: str,
    coherencia: str,
    tiene_datos_satelitales: bool,
    tiene_datos_meteo: bool
) -> str:
    """Calcula la confianza global del análisis multi-agente."""
    puntos = 0

    puntos += {"alta": 2, "media": 1, "baja": 0}.get(confianza_topo, 1)
    puntos += {"alta": 2, "media": 1}.get(coherencia, 0)
    puntos += 1 if tiene_datos_satelitales else 0
    puntos += 1 if tiene_datos_meteo else 0

    if puntos >= 5:
        return "Alta"
    elif puntos >= 3:
        return "Media"
    else:
        return "Baja"


def _identificar_factores_determinantes(
    estado_pinn: str,
    estado_vit: str,
    factor_meteorologico: str,
    nivel: int
) -> list:
    """Identifica los factores más determinantes para el nivel de riesgo."""
    factores = []

    if estado_pinn in ("CRITICO", "INESTABLE"):
        factores.append(f"PINN: manto {estado_pinn.lower()}")

    if estado_vit in ("CRITICO", "ALERTADO"):
        factores.append(f"ViT: {estado_vit.lower()}")

    if factor_meteorologico and factor_meteorologico != "ESTABLE":
        factores.append(f"Meteorología: {factor_meteorologico}")

    if not factores and nivel <= 2:
        factores.append("Condiciones generalmente estables en todos los subagentes")

    return factores


def _generar_mensaje_principal(
    nivel: int,
    estado_pinn: str,
    estado_vit: str,
    factor_meteorologico: str,
    ventanas: int
) -> str:
    """Genera el mensaje principal de explicación para el boletín."""
    nombres_nivel = {1: "débil", 2: "limitado", 3: "considerable", 4: "alto", 5: "muy alto"}
    nombre = nombres_nivel.get(nivel, "considerable")

    factores_activos = []
    if estado_pinn in ("CRITICO", "INESTABLE"):
        factores_activos.append("inestabilidad física del manto (PINN)")
    if estado_vit in ("CRITICO", "ALERTADO"):
        factores_activos.append("anomalías satelitales (ViT)")
    if factor_meteorologico not in ("ESTABLE", ""):
        factores_activos.append(f"factores meteorológicos ({factor_meteorologico})")

    if factores_activos:
        return (
            f"Riesgo de avalancha {nombre} (nivel {nivel}/5) determinado por: "
            f"{'; '.join(factores_activos)}. "
            f"{'Se detectaron ' + str(ventanas) + ' ventanas críticas activas.' if ventanas > 0 else ''}"
        ).strip()
    else:
        return (
            f"Riesgo de avalancha {nombre} (nivel {nivel}/5). "
            "Condiciones generalmente estables en los tres dominios de análisis."
        )

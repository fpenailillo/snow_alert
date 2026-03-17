"""
Tool: analizar_vit

Simula un Vision Transformer (ViT) aplicado a la serie temporal de
métricas satelitales. El ViT calcula pesos de atención sobre los
pasos temporales para identificar momentos críticos de cambio nival.

Implementación sin GPU: calcula el mecanismo de atención (self-attention)
directamente sobre los vectores de características satelitales.
"""

import math


TOOL_ANALIZAR_VIT = {
    "name": "analizar_vit",
    "description": (
        "Aplica un Vision Transformer (ViT) sobre la serie temporal de "
        "métricas satelitales (ndsi_medio, pct_cobertura_nieve, "
        "lst_dia_celsius, lst_noche_celsius, ciclo_diurno_amplitud, "
        "delta_pct_nieve_24h). Calcula pesos de atención para identificar "
        "los pasos temporales más relevantes para el riesgo actual. "
        "Implementación directa del mecanismo de self-attention sin GPU."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "serie_temporal": {
                "type": "array",
                "description": "Lista de dicts con métricas satelitales por paso temporal",
                "items": {"type": "object"}
            },
            "ndsi_promedio": {
                "type": "number",
                "description": "NDSI promedio de la serie"
            },
            "cobertura_promedio": {
                "type": "number",
                "description": "Cobertura nieve promedio de la serie (%)"
            },
            "variabilidad_ndsi": {
                "type": "number",
                "description": "Variabilidad del NDSI en la serie"
            }
        },
        "required": ["serie_temporal", "ndsi_promedio", "cobertura_promedio"]
    }
}


def ejecutar_analizar_vit(
    serie_temporal: list,
    ndsi_promedio: float,
    cobertura_promedio: float,
    variabilidad_ndsi: float = 0.0
) -> dict:
    """
    Aplica el mecanismo ViT (self-attention) a la serie temporal.

    Args:
        serie_temporal: lista de dicts con métricas por paso temporal
        ndsi_promedio: NDSI promedio de referencia
        cobertura_promedio: cobertura promedio de referencia
        variabilidad_ndsi: variabilidad del NDSI

    Returns:
        dict con pesos de atención, momento crítico y clasificación ViT
    """
    if not serie_temporal:
        return {
            "disponible": False,
            "mensaje": "Serie temporal vacía — no es posible calcular ViT",
            "estado_vit": "sin_datos",
            "anomalia_detectada": False
        }

    # Extraer vectores de características
    vectores = _extraer_vectores_caracteristicas(serie_temporal)

    if len(vectores) == 1:
        # Un solo punto: análisis directo sin atención temporal
        return _analizar_punto_unico(
            vectores[0], ndsi_promedio, cobertura_promedio, variabilidad_ndsi
        )

    # Calcular self-attention simplificado
    pesos_atencion = _calcular_self_attention(vectores)

    # Identificar paso temporal más relevante (mayor peso de atención)
    indice_critico = pesos_atencion.index(max(pesos_atencion))
    momento_critico = serie_temporal[indice_critico] if indice_critico < len(serie_temporal) else None

    # Clasificación global del estado nival por ViT
    estado_vit = _clasificar_estado_vit(
        pesos_atencion=pesos_atencion,
        vectores=vectores,
        ndsi_promedio=ndsi_promedio,
        variabilidad_ndsi=variabilidad_ndsi
    )

    # Detectar anomalías en la serie
    anomalias = _detectar_anomalias_serie(
        vectores=vectores,
        ndsi_promedio=ndsi_promedio,
        cobertura_promedio=cobertura_promedio
    )

    return {
        "disponible": True,
        "pasos_analizados": len(vectores),
        "pesos_atencion": [round(p, 4) for p in pesos_atencion],
        "indice_paso_critico": indice_critico,
        "momento_critico": momento_critico,
        "estado_vit": estado_vit["estado"],
        "score_anomalia": estado_vit["score_anomalia"],
        "anomalia_detectada": anomalias["hay_anomalia"],
        "tipos_anomalia": anomalias["tipos"],
        "interpretacion_vit": estado_vit["interpretacion"]
    }


def _extraer_vectores_caracteristicas(serie_temporal: list) -> list:
    """
    Extrae vectores de características normalizadas para el ViT.

    Cada vector = [ndsi, cobertura/100, lst_dia/50, lst_noche/50, ciclo/20, delta/30]
    (normalizados para que las magnitudes sean comparables)
    """
    vectores = []
    for paso in serie_temporal:
        ndsi = paso.get("ndsi_medio") or 0.0
        cobertura = (paso.get("pct_cobertura_nieve") or 0.0) / 100.0
        lst_dia = (paso.get("lst_dia_celsius") or 0.0) / 50.0
        lst_noche = (paso.get("lst_noche_celsius") or 0.0) / 50.0
        ciclo = (paso.get("ciclo_diurno_amplitud") or 0.0) / 20.0
        delta = (paso.get("delta_pct_nieve_24h") or 0.0) / 30.0

        vectores.append([ndsi, cobertura, lst_dia, lst_noche, ciclo, delta])
    return vectores


def _producto_punto(v1: list, v2: list) -> float:
    """Producto punto entre dos vectores."""
    return sum(a * b for a, b in zip(v1, v2))


def _norma(v: list) -> float:
    """Norma euclidiana de un vector."""
    return math.sqrt(sum(x ** 2 for x in v)) or 1e-8


def _calcular_self_attention(vectores: list) -> list:
    """
    Calcula pesos de self-attention simplificados.

    Implementa Q·K^T/√d para cada par de pasos temporales,
    luego softmax para obtener los pesos de atención.
    El último paso temporal (T actual) es el query principal.

    Args:
        vectores: lista de vectores de características normalizados

    Returns:
        lista de pesos de atención (suma = 1)
    """
    d = len(vectores[0])
    sqrt_d = math.sqrt(d)

    # El query es el último paso (estado actual)
    query = vectores[-1]

    # Calcular scores de atención: Q·K/√d
    scores = []
    for key in vectores:
        score = _producto_punto(query, key) / sqrt_d
        scores.append(score)

    # Softmax
    max_score = max(scores)
    exp_scores = [math.exp(s - max_score) for s in scores]
    suma_exp = sum(exp_scores)
    pesos = [e / suma_exp for e in exp_scores]

    return pesos


def _clasificar_estado_vit(
    pesos_atencion: list,
    vectores: list,
    ndsi_promedio: float,
    variabilidad_ndsi: float
) -> dict:
    """Clasifica el estado nival a partir del análisis ViT."""
    score = 0.0

    # Concentración de atención: si un paso tiene >60% del peso → evento puntual
    max_atencion = max(pesos_atencion)
    if max_atencion > 0.6:
        score += 1.5  # Evento dominante en un momento específico

    # NDSI bajo → nieve húmeda o poca cobertura
    if ndsi_promedio < 0.3:
        score += 2.0
    elif ndsi_promedio < 0.4:
        score += 1.0

    # Alta variabilidad → cambios rápidos en el manto
    if variabilidad_ndsi > 0.3:
        score += 2.0
    elif variabilidad_ndsi > 0.15:
        score += 1.0

    # Estado actual (último vector)
    vector_actual = vectores[-1] if vectores else [0] * 6
    delta_actual = vector_actual[5] * 30  # desnormalizar

    if abs(delta_actual) > 15:
        score += 2.0  # Nevada o deshielo intenso reciente
    elif abs(delta_actual) > 5:
        score += 1.0

    # Clasificación
    if score >= 5:
        estado = "CRITICO"
        interpretacion = (
            f"ViT detecta condiciones críticas (score={score:.1f}): "
            "manto nival con cambios rápidos y alta anomalía temporal."
        )
    elif score >= 3:
        estado = "ALERTADO"
        interpretacion = (
            f"ViT detecta condiciones de alerta (score={score:.1f}): "
            "cambios significativos en el manto nival."
        )
    elif score >= 1.5:
        estado = "MODERADO"
        interpretacion = (
            f"ViT detecta condiciones moderadas (score={score:.1f}): "
            "algunos cambios en el manto, monitoreo recomendado."
        )
    else:
        estado = "ESTABLE"
        interpretacion = (
            f"ViT indica condiciones estables (score={score:.1f}): "
            "manto nival con poca variabilidad temporal."
        )

    return {
        "estado": estado,
        "score_anomalia": round(score, 2),
        "interpretacion": interpretacion
    }


def _analizar_punto_unico(
    vector: list,
    ndsi_promedio: float,
    cobertura_promedio: float,
    variabilidad_ndsi: float
) -> dict:
    """Análisis ViT con un solo punto temporal."""
    ndsi = vector[0]
    delta = vector[5] * 30  # desnormalizar

    score = 0.0
    if ndsi < 0.3:
        score += 2.0
    if abs(delta) > 15:
        score += 2.0
    if variabilidad_ndsi > 0.15:
        score += 1.0

    estado = (
        "CRITICO" if score >= 4
        else "ALERTADO" if score >= 2
        else "ESTABLE"
    )

    return {
        "disponible": True,
        "pasos_analizados": 1,
        "pesos_atencion": [1.0],
        "indice_paso_critico": 0,
        "momento_critico": None,
        "estado_vit": estado,
        "score_anomalia": round(score, 2),
        "anomalia_detectada": score > 0,
        "tipos_anomalia": [],
        "interpretacion_vit": f"ViT con punto único: {estado} (score={score:.1f})"
    }


def _detectar_anomalias_serie(
    vectores: list,
    ndsi_promedio: float,
    cobertura_promedio: float
) -> dict:
    """Detecta anomalías estadísticas en la serie temporal."""
    tipos = []
    hay_anomalia = False

    if len(vectores) < 2:
        return {"hay_anomalia": False, "tipos": []}

    # Verificar cambios abruptos entre pasos consecutivos
    for i in range(1, len(vectores)):
        delta_ndsi = abs(vectores[i][0] - vectores[i-1][0])
        delta_cob = abs(vectores[i][1] - vectores[i-1][1]) * 100

        if delta_ndsi > 0.3:
            tipos.append(f"CAMBIO_ABRUPTO_NDSI_PASO_{i}")
            hay_anomalia = True

        if delta_cob > 20:
            tipos.append(f"CAMBIO_ABRUPTO_COBERTURA_PASO_{i}")
            hay_anomalia = True

    # Verificar estado actual vs promedio de la serie
    vector_actual = vectores[-1]
    ndsi_actual = vector_actual[0]

    if ndsi_promedio > 0.1 and abs(ndsi_actual - ndsi_promedio) / ndsi_promedio > 0.4:
        tipos.append("DESVIACION_NDSI_RESPECTO_PROMEDIO_SERIE")
        hay_anomalia = True

    return {"hay_anomalia": hay_anomalia, "tipos": list(set(tipos))}

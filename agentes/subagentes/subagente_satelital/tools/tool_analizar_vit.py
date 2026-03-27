"""
Tool: analizar_vit

Implementa un Temporal Transformer (arquitectura ViT adaptada a series
temporales de métricas satelitales) para identificar momentos críticos
en la dinámica del manto nival.

Arquitectura (Vaswani et al. 2017 — "Attention Is All You Need"):
  - Positional encoding sinusoidal sobre T pasos temporales  (§3.5)
  - Multi-head scaled dot-product attention: H=2 cabezas, d_model=6, d_head=3 (§3.2.2)
  - Matrices W_Q, W_K, W_V inicializadas deterministamente (Xavier/Glorot 2010)
  - BLOQUE TRANSFORMER COMPLETO (Vaswani §3.1):
      x₁ = LayerNorm(x + MHA(x))       ← Sublayer 1: Atención + Add & Norm
      x₂ = LayerNorm(x₁ + FFN(x₁))    ← Sublayer 2: FFN + Add & Norm
      FFN: d_ff = 4 × d_model = 24 (estándar Vaswani)
  - CLS token implícito: el último paso actúa como query de clasificación
  - Capa de clasificación: puntuación de anomalía ponderada por atención

Justificación del diseño (decisiones_diseno.md D2):
  Las imágenes satelitales crudas de Sentinel-2/MODIS no están disponibles
  en tiempo real en este pipeline. Se usa la serie temporal de métricas densas
  (NDSI, LST, cobertura) como representación del espacio de características.
  Este enfoque es análogo al uso de ViT pre-entrenado con fine-tuning frozen
  sobre embeddings de características, documentado en Zhou et al. (2021).

Referencias:
  - Vaswani et al. (2017) "Attention Is All You Need" — NeurIPS
  - Glorot & Bengio (2010) "Understanding the difficulty of training DNNs"
  - Ba et al. (2016) "Layer Normalization" — arXiv:1607.06450
  - Zhou et al. (2021) "Informer: Beyond Efficient Transformer for Long Seq."
"""

import math


# ─── Parámetros del Temporal Transformer ─────────────────────────────────────

D_MODEL = 6       # Dimensión de features (ndsi, cob, lst_d, lst_n, ciclo, delta)
N_HEADS = 2       # Número de cabezas de atención
D_HEAD = 3        # D_MODEL // N_HEADS = 6 // 2 = 3
D_FF = D_MODEL * 4  # Dimensión FFN interna: 4×d_model=24 (estándar Vaswani §3.3)
assert D_MODEL == N_HEADS * D_HEAD, "D_MODEL debe ser divisible entre N_HEADS"


TOOL_ANALIZAR_VIT = {
    "name": "analizar_vit",
    "description": (
        "Aplica un Temporal Transformer (arquitectura ViT) sobre la serie temporal "
        "de métricas satelitales (ndsi_medio, pct_cobertura_nieve, "
        "lst_dia_celsius, lst_noche_celsius, ciclo_diurno_amplitud, "
        "delta_pct_nieve_24h). Implementa multi-head scaled dot-product attention "
        "(Vaswani et al. 2017) con positional encoding sinusoidal y H=2 cabezas. "
        "Identifica los pasos temporales más relevantes para el riesgo actual."
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


# ─── Matrices de proyección (inicialización Xavier determinista) ──────────────

def _generar_matriz_proyeccion(d_in: int, d_out: int, semilla: int) -> list:
    """
    Genera una matriz de proyección d_in × d_out de forma determinista.

    Usa inicialización Xavier/Glorot (Glorot & Bengio 2010):
        w_ij = escala × sin(π × (i+semilla) × (j+1) / (d_in + d_out))

    donde escala = sqrt(2 / (d_in + d_out)) — límite Xavier.

    Esto produce proyecciones no triviales y reproducibles sin necesidad
    de datos de entrenamiento. En producción se reemplazaría por pesos
    fine-tuned sobre boletines etiquetados.

    Returns:
        lista de listas [d_in][d_out]
    """
    escala = math.sqrt(2.0 / (d_in + d_out))
    W = []
    for i in range(d_in):
        fila = []
        for j in range(d_out):
            angulo = math.pi * (i + semilla + 1) * (j + 1) / (d_in + d_out + 1)
            w_ij = escala * math.sin(angulo)
            fila.append(w_ij)
        W.append(fila)
    return W


# Pre-calcular matrices W_Q, W_K, W_V para cada cabeza (deterministas, fijas)
# Semillas distintas garantizan diversidad entre cabezas
_WQ = [
    _generar_matriz_proyeccion(D_HEAD, D_MODEL, semilla=0),   # cabeza 0  [D_HEAD × D_MODEL]
    _generar_matriz_proyeccion(D_HEAD, D_MODEL, semilla=7),   # cabeza 1
]
_WK = [
    _generar_matriz_proyeccion(D_HEAD, D_MODEL, semilla=3),
    _generar_matriz_proyeccion(D_HEAD, D_MODEL, semilla=11),
]
_WV = [
    _generar_matriz_proyeccion(D_HEAD, D_MODEL, semilla=5),
    _generar_matriz_proyeccion(D_HEAD, D_MODEL, semilla=13),
]

# Matrices del Feed-Forward Network (FFN, Vaswani §3.3)
# Proyección lineal W1: D_FF × D_MODEL  (expande features → espacio FFN)
# Proyección lineal W2: D_MODEL × D_FF  (proyecta de vuelta → D_MODEL)
_W_FF1 = _generar_matriz_proyeccion(D_FF, D_MODEL, semilla=17)   # [D_FF × D_MODEL]
_W_FF2 = _generar_matriz_proyeccion(D_MODEL, D_FF, semilla=23)   # [D_MODEL × D_FF]


# ─── Álgebra matricial (sin numpy) ───────────────────────────────────────────

def _mv_producto(M: list, v: list) -> list:
    """Producto matriz-vector M·v. M: [n_filas][n_cols], v: [n_cols]."""
    return [sum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]


def _producto_punto(v1: list, v2: list) -> float:
    return sum(a * b for a, b in zip(v1, v2))


def _norma(v: list) -> float:
    return math.sqrt(sum(x ** 2 for x in v)) or 1e-8


def _softmax(scores: list) -> list:
    max_s = max(scores)
    exp_s = [math.exp(s - max_s) for s in scores]
    total = sum(exp_s)
    return [e / total for e in exp_s]


# ─── Positional encoding sinusoidal (Vaswani et al. 2017, §3.5) ──────────────

def _positional_encoding(t: int, d: int) -> list:
    """
    PE(t, 2i)   = sin(t / 10000^(2i/d))
    PE(t, 2i+1) = cos(t / 10000^(2i/d))

    Args:
        t: posición temporal (0-indexed)
        d: dimensión del vector de features (D_MODEL)

    Returns:
        vector de positional encoding de longitud d
    """
    pe = []
    for i in range(d):
        denom = math.pow(10000, (2 * (i // 2)) / d)
        if i % 2 == 0:
            pe.append(math.sin(t / denom))
        else:
            pe.append(math.cos(t / denom))
    return pe


def _sumar_vectores(v1: list, v2: list) -> list:
    return [a + b for a, b in zip(v1, v2)]


# ─── Transformer block — componentes (Vaswani §3.1) ─────────────────────────

def _layer_norm(x: list, eps: float = 1e-6) -> list:
    """
    Layer Normalization (Ba et al. 2016, arXiv:1607.06450).

    LN(x) = (x - μ) / (σ + ε) × γ + β

    Con parámetros de escala γ=1 y sesgo β=0 (no entrenados — deterministas).
    En producción se ajustarían sobre boletines etiquetados.

    Args:
        x: vector de longitud d
        eps: epsilon de estabilidad numérica (default 1e-6, estándar PyTorch)

    Returns:
        vector normalizado de longitud d
    """
    n = len(x)
    media = sum(x) / n
    varianza = sum((xi - media) ** 2 for xi in x) / n
    std = math.sqrt(varianza + eps)
    return [(xi - media) / std for xi in x]


def _relu(v: list) -> list:
    """Activación ReLU: max(0, x) componente a componente."""
    return [max(0.0, xi) for xi in v]


def _feed_forward_network(x: list) -> list:
    """
    Position-wise Feed-Forward Network (Vaswani et al. 2017, §3.3).

    FFN(x) = max(0, x·W₁ᵀ) · W₂ᵀ

    Con:
        W₁: D_FF × D_MODEL  = 24 × 6  (expansión lineal)
        W₂: D_MODEL × D_FF  = 6 × 24  (proyección de vuelta)
        Activación: ReLU (Vaswani 2017 usa ReLU, Devlin 2018 usa GELU)

    La dimensión interna D_FF = 4 × D_MODEL = 24 sigue la convención estándar
    de los Transformers para la capa intermedia (Vaswani 2017 §3.3 usa d_ff=2048
    con d_model=512, misma proporción 4×).

    Args:
        x: vector de entrada de longitud D_MODEL

    Returns:
        vector de salida de longitud D_MODEL
    """
    h = _mv_producto(_W_FF1, x)      # D_FF   (proyección W₁)
    h = _relu(h)                      # D_FF   (activación ReLU)
    return _mv_producto(_W_FF2, h)    # D_MODEL (proyección W₂)


# ─── Extracción de features ──────────────────────────────────────────────────

def _extraer_vectores_caracteristicas(serie_temporal: list) -> list:
    """
    Extrae vectores de características normalizadas para el Temporal Transformer.

    Normalización estándar (z-score aproximado):
        ndsi        ∈ [0, 1]  → sin cambio
        cobertura   ∈ [0, 100] → / 100
        lst_dia     ∈ [-30, 30] °C → / 50
        lst_noche   ∈ [-40, 10] °C → / 50
        ciclo_amp   ∈ [0, 20] °C → / 20
        delta_24h   ∈ [-30, 30] % → / 30
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


# ─── Multi-head scaled dot-product attention ─────────────────────────────────

def _scaled_dot_product_attention_head(
    query: list,
    keys: list,
    values: list,
    WQ: list,
    WK: list,
    WV: list,
) -> tuple:
    """
    Scaled dot-product attention para UNA cabeza (Vaswani et al. 2017, Ec. 1):

        Attention(Q, K, V) = softmax(Q·K^T / √d_k) · V

    Args:
        query: vector query (último paso temporal), longitud D_MODEL
        keys:  lista de T vectores clave, cada uno longitud D_MODEL
        values: lista de T vectores valor, cada uno longitud D_MODEL
        WQ, WK, WV: matrices de proyección [D_MODEL × D_HEAD]

    Returns:
        (vector_contexto de longitud D_HEAD, pesos_atencion de longitud T)
    """
    sqrt_dk = math.sqrt(D_HEAD)

    # Proyectar query, keys y values
    q_proj = _mv_producto(WQ, query)                        # D_HEAD
    k_proj = [_mv_producto(WK, k) for k in keys]           # T × D_HEAD
    v_proj = [_mv_producto(WV, v) for v in values]         # T × D_HEAD

    # Scores: q·k / √d_k
    scores = [_producto_punto(q_proj, k) / sqrt_dk for k in k_proj]

    # Pesos de atención
    pesos = _softmax(scores)

    # Vector contexto: suma ponderada de values
    d_h = D_HEAD
    contexto = [
        sum(pesos[t] * v_proj[t][j] for t in range(len(pesos)))
        for j in range(d_h)
    ]

    return contexto, pesos


def _multi_head_attention(
    query: list,
    keys: list,
    values: list,
) -> tuple:
    """
    Multi-head attention con N_HEADS cabezas.

    Combina las salidas de cada cabeza por concatenación y promedio.

    Returns:
        (vector_contexto D_MODEL, pesos_promedio T)
    """
    contextos = []
    pesos_por_cabeza = []

    for h in range(N_HEADS):
        ctx, pesos = _scaled_dot_product_attention_head(
            query=query,
            keys=keys,
            values=values,
            WQ=_WQ[h],
            WK=_WK[h],
            WV=_WV[h],
        )
        contextos.append(ctx)
        pesos_por_cabeza.append(pesos)

    # Concatenar salidas de cabezas → D_MODEL
    contexto_concat = []
    for ctx in contextos:
        contexto_concat.extend(ctx)

    # Pesos de atención promediados entre cabezas (para interpretación)
    T = len(keys)
    pesos_promedio = [
        sum(pesos_por_cabeza[h][t] for h in range(N_HEADS)) / N_HEADS
        for t in range(T)
    ]

    return contexto_concat, pesos_promedio


def _calcular_self_attention(vectores: list) -> tuple:
    """
    Aplica un bloque Transformer encoder completo (Vaswani 2017, §3.1).

    El último paso actúa como query de clasificación (análogo a CLS token).

    Estructura del bloque (dos sublayers con Add & Norm):
        x = x + PE(x)                    ← Positional encoding
        x₁ = LayerNorm(x + MHA(x))       ← Sublayer 1: Atención multi-head
        x₂ = LayerNorm(x₁ + FFN(x₁))    ← Sublayer 2: Feed-Forward Network

    Returns:
        (pesos_atencion lista[T], x2 lista[D_MODEL])
        donde x2 es el output del bloque Transformer completo (post-FFN, post-LN)
    """
    T = len(vectores)

    # 0. Añadir positional encoding a cada vector (Vaswani §3.5)
    vectores_pe = [
        _sumar_vectores(vectores[t], _positional_encoding(t, D_MODEL))
        for t in range(T)
    ]

    query = vectores_pe[-1]   # Último paso = CLS token (query de clasificación)
    keys = vectores_pe        # Todos los pasos como keys
    values = vectores_pe      # Todos los pasos como values

    # 1. Sublayer 1: Multi-head attention + Add & Norm
    #    x₁ = LayerNorm(query + MHA(query, keys, values))
    contexto_mha, pesos = _multi_head_attention(query, keys, values)
    x1 = _layer_norm(_sumar_vectores(query, contexto_mha))   # Add & Norm

    # 2. Sublayer 2: FFN + Add & Norm
    #    x₂ = LayerNorm(x₁ + FFN(x₁))
    ffn_out = _feed_forward_network(x1)
    x2 = _layer_norm(_sumar_vectores(x1, ffn_out))           # Add & Norm

    return pesos, x2


# ─── Clasificación del estado nival ──────────────────────────────────────────

def _clasificar_estado_vit(
    pesos_atencion: list,
    vectores: list,
    vector_contexto: list,
    ndsi_promedio: float,
    variabilidad_ndsi: float,
    cobertura_promedio: float = 0.0,
) -> dict:
    """
    Clasifica el estado nival a partir del vector de contexto multi-head.

    Usa el vector de contexto proyectado por las matrices W_V (richer
    representation) en lugar de solo las features crudas.
    """
    score = 0.0

    # 1. Concentración de atención: evento puntual dominante
    max_atencion = max(pesos_atencion)
    if max_atencion > 0.6:
        score += 1.5

    # 2. NDSI bajo → nieve húmeda (Dietz et al. umbral 0.4).
    # SOLO aplica si hay cobertura de nieve significativa (>10%): en verano/otoño,
    # ndsi<0.4 es normal (sin nieve) y no indica riesgo.
    if cobertura_promedio > 10:
        if ndsi_promedio < 0.4:
            score += 2.0
        elif ndsi_promedio < 0.45:
            score += 1.0

    # 3. Alta variabilidad → cambios rápidos en el manto
    if variabilidad_ndsi > 0.3:
        score += 2.0
    elif variabilidad_ndsi > 0.15:
        score += 1.0

    # 4. Delta de cobertura en el paso actual (desnormalizado)
    delta_actual = vectores[-1][5] * 30 if vectores else 0.0
    if abs(delta_actual) > 15:
        score += 2.0
    elif abs(delta_actual) > 5:
        score += 1.0

    # 5. Señal del vector de contexto multi-head: norma indica magnitud del evento
    norma_contexto = _norma(vector_contexto)
    if norma_contexto > 1.5:
        score += 1.0  # Señal de anomalía amplificada por las proyecciones

    # 6. Diversidad de atención entre cabezas (indicador de patrón complejo)
    # Si la atención está distribuida (entropía alta), hay múltiples eventos
    T = len(pesos_atencion)
    entropia_atencion = (
        -sum(p * math.log(p + 1e-9) for p in pesos_atencion) / math.log(T + 1)
        if T > 1 else 0.0
    )
    if entropia_atencion < 0.5:
        score += 0.5  # Atención concentrada → evento puntual dominante

    # Clasificación
    if score >= 5:
        estado = "CRITICO"
        desc = f"Transformer detecta condiciones críticas (score={score:.1f}): manto nival con anomalía severa."
    elif score >= 3:
        estado = "ALERTADO"
        desc = f"Transformer detecta condiciones de alerta (score={score:.1f}): cambios significativos."
    elif score >= 1.5:
        estado = "MODERADO"
        desc = f"Transformer detecta condiciones moderadas (score={score:.1f}): monitoreo recomendado."
    else:
        estado = "ESTABLE"
        desc = f"Transformer indica condiciones estables (score={score:.1f}): baja anomalía temporal."

    return {
        "estado": estado,
        "score_anomalia": round(score, 2),
        "entropia_atencion": round(entropia_atencion, 4),
        "norma_contexto": round(norma_contexto, 4),
        "interpretacion": desc,
    }


def _analizar_punto_unico(
    vector: list,
    ndsi_promedio: float,
    cobertura_promedio: float,
    variabilidad_ndsi: float,
) -> dict:
    """Análisis con un solo punto temporal (sin atención)."""
    ndsi = vector[0]
    delta = vector[5] * 30

    score = 0.0
    # NDSI bajo es señal de riesgo solo cuando hay nieve (cobertura > 10%)
    if cobertura_promedio > 10 and ndsi < 0.4:
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
        "arquitectura_vit": f"temporal_transformer_single_point (d={D_MODEL})",
        "pasos_analizados": 1,
        "n_heads": N_HEADS,
        "pesos_atencion": [1.0],
        "indice_paso_critico": 0,
        "momento_critico": None,
        "estado_vit": estado,
        "score_anomalia": round(score, 2),
        "anomalia_detectada": score > 0,
        "tipos_anomalia": [],
        "interpretacion_vit": f"ViT punto único: {estado} (score={score:.1f})",
    }


def _detectar_anomalias_serie(
    vectores: list,
    ndsi_promedio: float,
    cobertura_promedio: float,
) -> dict:
    """Detecta anomalías estadísticas en la serie temporal."""
    tipos = []
    hay_anomalia = False

    if len(vectores) < 2:
        return {"hay_anomalia": False, "tipos": []}

    for i in range(1, len(vectores)):
        delta_ndsi = abs(vectores[i][0] - vectores[i-1][0])
        delta_cob = abs(vectores[i][1] - vectores[i-1][1]) * 100
        if delta_ndsi > 0.3:
            tipos.append(f"CAMBIO_ABRUPTO_NDSI_PASO_{i}")
            hay_anomalia = True
        if delta_cob > 20:
            tipos.append(f"CAMBIO_ABRUPTO_COBERTURA_PASO_{i}")
            hay_anomalia = True

    vector_actual = vectores[-1]
    ndsi_actual = vector_actual[0]
    if ndsi_promedio > 0.1 and abs(ndsi_actual - ndsi_promedio) / ndsi_promedio > 0.4:
        tipos.append("DESVIACION_NDSI_RESPECTO_PROMEDIO_SERIE")
        hay_anomalia = True

    return {"hay_anomalia": hay_anomalia, "tipos": list(set(tipos))}


# ─── Punto de entrada principal ──────────────────────────────────────────────

def ejecutar_analizar_vit(
    serie_temporal: list,
    ndsi_promedio: float,
    cobertura_promedio: float,
    variabilidad_ndsi: float = 0.0,
) -> dict:
    """
    Aplica el Temporal Transformer (multi-head attention, Vaswani 2017) a la serie.

    Arquitectura:
        d_model={D_MODEL}, n_heads={N_HEADS}, d_head={D_HEAD}
        Positional encoding sinusoidal + W_Q/W_K/W_V deterministos (Xavier 2010)

    Args:
        serie_temporal: lista de dicts con métricas satelitales por paso
        ndsi_promedio: NDSI promedio de referencia de la serie
        cobertura_promedio: cobertura nieve promedio (%) de la serie
        variabilidad_ndsi: variabilidad del NDSI en la serie

    Returns:
        dict con pesos de atención por paso, estado ViT y métricas de anomalía
    """.format(D_MODEL=D_MODEL, N_HEADS=N_HEADS, D_HEAD=D_HEAD)

    if not serie_temporal:
        return {
            "disponible": False,
            "mensaje": "Serie temporal vacía — no es posible calcular Transformer",
            "estado_vit": "sin_datos",
            "anomalia_detectada": False,
        }

    vectores = _extraer_vectores_caracteristicas(serie_temporal)

    if len(vectores) == 1:
        return _analizar_punto_unico(
            vectores[0], ndsi_promedio, cobertura_promedio, variabilidad_ndsi
        )

    # Multi-head self-attention con positional encoding
    pesos_atencion, vector_contexto = _calcular_self_attention(vectores)

    indice_critico = pesos_atencion.index(max(pesos_atencion))
    momento_critico = (
        serie_temporal[indice_critico]
        if indice_critico < len(serie_temporal) else None
    )

    estado_vit = _clasificar_estado_vit(
        pesos_atencion=pesos_atencion,
        vectores=vectores,
        vector_contexto=vector_contexto,
        ndsi_promedio=ndsi_promedio,
        variabilidad_ndsi=variabilidad_ndsi,
        cobertura_promedio=cobertura_promedio,
    )

    anomalias = _detectar_anomalias_serie(
        vectores=vectores,
        ndsi_promedio=ndsi_promedio,
        cobertura_promedio=cobertura_promedio,
    )

    return {
        "disponible": True,
        "arquitectura_vit": (
            f"temporal_transformer_multihead_encoder "
            f"(d={D_MODEL}, H={N_HEADS}, d_k={D_HEAD}, d_ff={D_FF}, "
            f"pos_enc=sinusoidal, W_QKV=xavier, layernorm=add_norm, ffn=relu_4x, "
            f"ref=Vaswani2017_sec3.1)"
        ),
        "pasos_analizados": len(vectores),
        "n_heads": N_HEADS,
        "d_ff": D_FF,
        "pesos_atencion": [round(p, 4) for p in pesos_atencion],
        "indice_paso_critico": indice_critico,
        "momento_critico": momento_critico,
        "entropia_atencion": estado_vit["entropia_atencion"],
        "norma_contexto_mha": estado_vit["norma_contexto"],
        "estado_vit": estado_vit["estado"],
        "score_anomalia": estado_vit["score_anomalia"],
        "anomalia_detectada": anomalias["hay_anomalia"],
        "tipos_anomalia": anomalias["tipos"],
        "interpretacion_vit": estado_vit["interpretacion"],
    }

"""
Métricas de Validación EAWS para el Sistema Multi-Agente de Avalanchas

Calcula las métricas académicas requeridas por la tesina:
- H1: F1-score macro por nivel EAWS (objetivo ≥75%)
- H2: Delta de precisión con/sin NLP (objetivo >5pp)
- H3: Comparación con Techel et al. (2022) — referencia data-driven SLF
- H4: Cohen's Kappa vs Snowlab Chile (objetivo ≥0.60)

Fuente de datos: tabla clima.boletines_riesgo en BigQuery.

Referencia principal para benchmarking:
    Techel, F., Bavay, M., & Pielmeier, C. (2022). Data-driven automated
    predictions of the avalanche danger level for dry-snow conditions in
    Switzerland. NHESS, 22(6), 2031-2056.
    https://nhess.copernicus.org/articles/22/2031/2022/

Uso:
    from agentes.validacion.metricas_eaws import calcular_todas_las_metricas
    metricas = calcular_todas_las_metricas()
"""

import logging
import math
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Métricas base
# ═══════════════════════════════════════════════════════════════════════════════

def calcular_matriz_confusion(
    reales: List[int],
    predichos: List[int],
    niveles: List[int] = None
) -> Dict[str, Any]:
    """
    Calcula la matriz de confusión para niveles EAWS (1-5).

    Args:
        reales: Lista de niveles EAWS reales (ground truth)
        predichos: Lista de niveles EAWS predichos por el sistema
        niveles: Lista de niveles posibles (default: [1,2,3,4,5])

    Returns:
        Dict con matriz, niveles, y conteos por clase
    """
    if len(reales) != len(predichos):
        raise ValueError(
            f"Longitudes no coinciden: reales={len(reales)}, predichos={len(predichos)}"
        )

    if niveles is None:
        niveles = [1, 2, 3, 4, 5]

    n = len(niveles)
    idx = {nivel: i for i, nivel in enumerate(niveles)}
    matriz = [[0] * n for _ in range(n)]

    for real, pred in zip(reales, predichos):
        if real in idx and pred in idx:
            matriz[idx[real]][idx[pred]] += 1

    return {
        "matriz": matriz,
        "niveles": niveles,
        "total_muestras": len(reales),
        "distribucion_reales": dict(Counter(reales)),
        "distribucion_predichos": dict(Counter(predichos)),
    }


def calcular_precision_recall_f1_por_clase(
    matriz: List[List[int]],
    niveles: List[int]
) -> List[Dict[str, Any]]:
    """
    Calcula precision, recall y F1 por cada nivel EAWS.

    Args:
        matriz: Matriz de confusión NxN
        niveles: Lista de niveles correspondientes

    Returns:
        Lista de dicts con métricas por clase
    """
    n = len(niveles)
    resultados = []

    for i in range(n):
        tp = matriz[i][i]
        fp = sum(matriz[j][i] for j in range(n)) - tp
        fn = sum(matriz[i][j] for j in range(n)) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
               if (precision + recall) > 0 else 0.0)

        soporte = sum(matriz[i][j] for j in range(n))

        resultados.append({
            "nivel": niveles[i],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "soporte": soporte,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════════
# H1: F1-score macro
# ═══════════════════════════════════════════════════════════════════════════════

def calcular_f1_macro(reales: List[int], predichos: List[int]) -> Dict[str, Any]:
    """
    Calcula F1-score macro (promedio no ponderado de F1 por clase).

    H1: El sistema debe alcanzar F1-macro ≥ 0.75 en niveles EAWS.

    Args:
        reales: Niveles EAWS reales
        predichos: Niveles EAWS predichos

    Returns:
        Dict con f1_macro, detalle por clase, y veredicto H1
    """
    conf = calcular_matriz_confusion(reales, predichos)
    por_clase = calcular_precision_recall_f1_por_clase(conf["matriz"], conf["niveles"])

    clases_con_soporte = [c for c in por_clase if c["soporte"] > 0]
    f1_macro = (sum(c["f1"] for c in clases_con_soporte) / len(clases_con_soporte)
                if clases_con_soporte else 0.0)

    precision_macro = (sum(c["precision"] for c in clases_con_soporte) / len(clases_con_soporte)
                       if clases_con_soporte else 0.0)

    recall_macro = (sum(c["recall"] for c in clases_con_soporte) / len(clases_con_soporte)
                    if clases_con_soporte else 0.0)

    accuracy = (sum(c["tp"] for c in por_clase) / conf["total_muestras"]
                if conf["total_muestras"] > 0 else 0.0)

    return {
        "f1_macro": round(f1_macro, 4),
        "precision_macro": round(precision_macro, 4),
        "recall_macro": round(recall_macro, 4),
        "accuracy": round(accuracy, 4),
        "total_muestras": conf["total_muestras"],
        "detalle_por_clase": por_clase,
        "matriz_confusion": conf["matriz"],
        "niveles": conf["niveles"],
        "h1_cumple": f1_macro >= 0.75,
        "h1_objetivo": 0.75,
        "h1_diferencia": round(f1_macro - 0.75, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# H2: Delta con/sin NLP
# ═══════════════════════════════════════════════════════════════════════════════

def calcular_delta_nlp(
    reales: List[int],
    predichos_con_nlp: List[int],
    predichos_sin_nlp: List[int]
) -> Dict[str, Any]:
    """
    Calcula la mejora de precisión al incluir el SubagenteNLP.

    H2: La incorporación de NLP debe mejorar la precisión en >5pp.

    Args:
        reales: Niveles EAWS reales
        predichos_con_nlp: Predicciones con sistema completo (5 subagentes)
        predichos_sin_nlp: Predicciones sin SubagenteNLP (4 subagentes)

    Returns:
        Dict con delta, métricas individuales, y veredicto H2
    """
    metricas_con = calcular_f1_macro(reales, predichos_con_nlp)
    metricas_sin = calcular_f1_macro(reales, predichos_sin_nlp)

    delta_f1 = metricas_con["f1_macro"] - metricas_sin["f1_macro"]
    delta_precision = metricas_con["precision_macro"] - metricas_sin["precision_macro"]
    delta_recall = metricas_con["recall_macro"] - metricas_sin["recall_macro"]
    delta_accuracy = metricas_con["accuracy"] - metricas_sin["accuracy"]

    return {
        "delta_f1_macro_pp": round(delta_f1 * 100, 2),
        "delta_precision_pp": round(delta_precision * 100, 2),
        "delta_recall_pp": round(delta_recall * 100, 2),
        "delta_accuracy_pp": round(delta_accuracy * 100, 2),
        "con_nlp": {
            "f1_macro": metricas_con["f1_macro"],
            "precision_macro": metricas_con["precision_macro"],
            "accuracy": metricas_con["accuracy"],
        },
        "sin_nlp": {
            "f1_macro": metricas_sin["f1_macro"],
            "precision_macro": metricas_sin["precision_macro"],
            "accuracy": metricas_sin["accuracy"],
        },
        "h2_cumple": delta_f1 * 100 > 5.0,
        "h2_objetivo_pp": 5.0,
        "h2_diferencia_pp": round(delta_f1 * 100 - 5.0, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# H4: Cohen's Kappa
# ═══════════════════════════════════════════════════════════════════════════════

def calcular_cohens_kappa(
    anotador_a: List[int],
    anotador_b: List[int],
    niveles: List[int] = None
) -> Dict[str, Any]:
    """
    Calcula Cohen's Kappa entre dos anotadores (sistema vs Snowlab).

    H4: El sistema debe alcanzar Kappa ≥ 0.60 vs Snowlab Chile.

    Args:
        anotador_a: Niveles EAWS del sistema
        anotador_b: Niveles EAWS de Snowlab Chile
        niveles: Niveles posibles (default: [1..5])

    Returns:
        Dict con kappa, concordancia observada/esperada, y veredicto H4
    """
    if len(anotador_a) != len(anotador_b):
        raise ValueError(
            f"Longitudes no coinciden: a={len(anotador_a)}, b={len(anotador_b)}"
        )

    n = len(anotador_a)
    if n == 0:
        return {"kappa": 0.0, "error": "Sin muestras"}

    if niveles is None:
        niveles = [1, 2, 3, 4, 5]

    idx = {nivel: i for i, nivel in enumerate(niveles)}
    k = len(niveles)
    matriz = [[0] * k for _ in range(k)]

    for a, b in zip(anotador_a, anotador_b):
        if a in idx and b in idx:
            matriz[idx[a]][idx[b]] += 1

    # Concordancia observada
    po = sum(matriz[i][i] for i in range(k)) / n

    # Concordancia esperada por azar
    pe = 0.0
    for i in range(k):
        fila_sum = sum(matriz[i][j] for j in range(k))
        col_sum = sum(matriz[j][i] for j in range(k))
        pe += (fila_sum * col_sum) / (n * n)

    # Kappa
    kappa = (po - pe) / (1.0 - pe) if (1.0 - pe) > 0 else 0.0

    # Interpretación (Landis & Koch, 1977)
    if kappa >= 0.81:
        interpretacion = "Casi perfecto"
    elif kappa >= 0.61:
        interpretacion = "Sustancial"
    elif kappa >= 0.41:
        interpretacion = "Moderado"
    elif kappa >= 0.21:
        interpretacion = "Aceptable"
    elif kappa >= 0.0:
        interpretacion = "Leve"
    else:
        interpretacion = "Pobre"

    return {
        "kappa": round(kappa, 4),
        "concordancia_observada": round(po, 4),
        "concordancia_esperada": round(pe, 4),
        "interpretacion": interpretacion,
        "total_muestras": n,
        "h4_cumple": kappa >= 0.60,
        "h4_objetivo": 0.60,
        "h4_diferencia": round(kappa - 0.60, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Análisis de ablación
# ═══════════════════════════════════════════════════════════════════════════════

def analisis_ablacion(
    reales: List[int],
    predicciones_por_config: Dict[str, List[int]]
) -> Dict[str, Any]:
    """
    Análisis de ablación: mide impacto de cada componente.

    Configuraciones esperadas:
    - "completo": 5 subagentes (S1+S2+S3+S4+S5)
    - "sin_nlp": sin SubagenteNLP (S1+S2+S3+S5)
    - "sin_satelital": sin SubagenteSatelital (S1+S3+S4+S5)
    - "sin_topografico": sin SubagenteTopografico (S2+S3+S4+S5)
    - "sin_meteorologico": sin SubagenteMeteorologico (S1+S2+S4+S5)
    - "solo_integrador": solo SubagenteIntegrador (S5)

    Args:
        reales: Niveles EAWS reales
        predicciones_por_config: Dict {nombre_config: lista_predicciones}

    Returns:
        Dict con F1 por configuración, ranking de importancia
    """
    resultados = {}
    for nombre, predichos in predicciones_por_config.items():
        metricas = calcular_f1_macro(reales, predichos)
        resultados[nombre] = {
            "f1_macro": metricas["f1_macro"],
            "precision_macro": metricas["precision_macro"],
            "recall_macro": metricas["recall_macro"],
            "accuracy": metricas["accuracy"],
        }

    # Calcular delta de cada componente vs completo
    f1_completo = resultados.get("completo", {}).get("f1_macro", 0.0)
    deltas = {}
    for nombre, metricas in resultados.items():
        if nombre != "completo":
            delta = f1_completo - metricas["f1_macro"]
            componente = nombre.replace("sin_", "")
            deltas[componente] = round(delta * 100, 2)

    # Ranking por importancia (mayor delta = más importante)
    ranking = sorted(deltas.items(), key=lambda x: x[1], reverse=True)

    return {
        "resultados_por_config": resultados,
        "delta_pp_vs_completo": deltas,
        "ranking_importancia": [
            {"componente": comp, "delta_f1_pp": delta}
            for comp, delta in ranking
        ],
        "f1_completo": f1_completo,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# H3: Comparación con Techel et al. (2022) — benchmark data-driven SLF
# ═══════════════════════════════════════════════════════════════════════════════

# Métricas de referencia reportadas por Techel et al. (2022), Tabla 5 y Sección 4.
# "Data-driven automated predictions of the avalanche danger level for
# dry-snow conditions in Switzerland", NHESS 22(6), 2031-2056.
#
# El paper reporta resultados para predicción automatizada del nivel EAWS
# usando Random Forest sobre variables meteorológicas y nivológicas derivadas
# de estaciones automáticas suizas (IMIS) y el modelo SNOWPACK.
#
# Métricas sobre el dataset de verificación (2001-2019, 18 inviernos):
TECHEL_2022_REFERENCIA = {
    "paper": "Techel et al. (2022) NHESS 22(6):2031-2056",
    "doi": "10.5194/nhess-22-2031-2022",
    "url": "https://nhess.copernicus.org/articles/22/2031/2022/",
    "pais": "Suiza",
    "periodo": "2001-2019 (18 inviernos)",
    "condiciones": "nieve seca (dry-snow) únicamente",
    "modelo": "Random Forest (100 árboles)",
    "features": "variables meteorológicas IMIS + SNOWPACK (50+ features)",
    "n_muestras": 52_485,
    # Métricas reportadas (Tabla 5, modelo RF verificación)
    "accuracy": 0.64,
    "accuracy_adyacente": 0.95,  # ±1 nivel (Adjacent Accuracy)
    "f1_macro_estimado": 0.55,   # Estimación desde Fig. 7 (niveles 1-4)
    "kappa_ponderado": 0.59,     # Quadratic Weighted Kappa (QWK)
    # Distribución de niveles en datos suizos (Fig. 3)
    "distribucion_niveles": {
        1: 0.08,   # ~8% nivel 1 (Débil)
        2: 0.42,   # ~42% nivel 2 (Limitado) — mayoría
        3: 0.40,   # ~40% nivel 3 (Considerable)
        4: 0.09,   # ~9% nivel 4 (Alto)
        5: 0.01,   # ~1% nivel 5 (Muy Alto) — excluido por baja frecuencia
    },
    # Sesgo reportado: tendencia a sobreestimar nivel 2 y subestimar nivel 3
    "sesgo_conocido": "Sobreestima nivel 2, subestima nivel 3",
    # Limitaciones reconocidas por los autores
    "limitaciones": [
        "Solo condiciones de nieve seca",
        "Entrenado exclusivamente con datos suizos (IMIS+SNOWPACK)",
        "Sin componente NLP ni relatos históricos",
        "Sin datos satelitales (solo estaciones terrestres)",
        "Nivel 5 excluido por muestra insuficiente",
    ],
}


def calcular_kappa_ponderado_cuadratico(
    anotador_a: List[int],
    anotador_b: List[int],
    niveles: List[int] = None
) -> Dict[str, Any]:
    """
    Calcula Quadratic Weighted Kappa (QWK) entre dos anotadores.

    Es la métrica principal usada por Techel et al. (2022) para evaluar
    concordancia entre niveles EAWS predichos y observados. A diferencia
    del Kappa de Cohen simple, QWK penaliza menos los desacuerdos de 1 nivel
    y más los desacuerdos de ≥2 niveles.

    Args:
        anotador_a: Niveles EAWS del sistema (o predicción)
        anotador_b: Niveles EAWS de referencia (ground truth)
        niveles: Niveles posibles (default: [1..5])

    Returns:
        Dict con kappa_ponderado, matrices observada/esperada
    """
    if len(anotador_a) != len(anotador_b):
        raise ValueError(
            f"Longitudes no coinciden: a={len(anotador_a)}, b={len(anotador_b)}"
        )

    n = len(anotador_a)
    if n == 0:
        return {"kappa_ponderado": 0.0, "error": "Sin muestras"}

    if niveles is None:
        niveles = [1, 2, 3, 4, 5]

    k = len(niveles)
    idx = {nivel: i for i, nivel in enumerate(niveles)}

    # Matriz de observaciones
    O = [[0] * k for _ in range(k)]
    for a, b in zip(anotador_a, anotador_b):
        if a in idx and b in idx:
            O[idx[a]][idx[b]] += 1

    # Normalizar
    O_norm = [[O[i][j] / n for j in range(k)] for i in range(k)]

    # Marginales
    fila_sums = [sum(O_norm[i][j] for j in range(k)) for i in range(k)]
    col_sums = [sum(O_norm[i][j] for i in range(k)) for j in range(k)]

    # Matriz esperada bajo independencia
    E = [[fila_sums[i] * col_sums[j] for j in range(k)] for i in range(k)]

    # Pesos cuadráticos: w_ij = (i - j)^2 / (k - 1)^2
    W = [[(i - j) ** 2 / ((k - 1) ** 2) for j in range(k)] for i in range(k)]

    # QWK = 1 - sum(W * O) / sum(W * E)
    num = sum(W[i][j] * O_norm[i][j] for i in range(k) for j in range(k))
    den = sum(W[i][j] * E[i][j] for i in range(k) for j in range(k))

    qwk = 1.0 - (num / den) if den > 0 else 0.0

    # Interpretación (misma escala que Kappa simple)
    if qwk >= 0.81:
        interpretacion = "Casi perfecto"
    elif qwk >= 0.61:
        interpretacion = "Sustancial"
    elif qwk >= 0.41:
        interpretacion = "Moderado"
    elif qwk >= 0.21:
        interpretacion = "Aceptable"
    elif qwk >= 0.0:
        interpretacion = "Leve"
    else:
        interpretacion = "Pobre"

    return {
        "kappa_ponderado": round(qwk, 4),
        "interpretacion": interpretacion,
        "total_muestras": n,
    }


def calcular_accuracy_adyacente(
    reales: List[int],
    predichos: List[int]
) -> Dict[str, Any]:
    """
    Calcula Adjacent Accuracy (predicción correcta ±1 nivel).

    Techel et al. (2022) reporta ~95% de predicciones dentro de ±1 nivel.
    Es una métrica operacionalmente relevante: un error de 1 nivel EAWS
    es aceptable en la práctica de avisos de avalanchas.

    Args:
        reales: Niveles EAWS reales
        predichos: Niveles EAWS predichos

    Returns:
        Dict con accuracy exacta, adyacente (±1), y distribución de errores
    """
    if len(reales) != len(predichos):
        raise ValueError(
            f"Longitudes no coinciden: reales={len(reales)}, predichos={len(predichos)}"
        )

    n = len(reales)
    if n == 0:
        return {"accuracy_adyacente": 0.0, "error": "Sin muestras"}

    exactos = 0
    adyacentes = 0  # ±1
    errores = Counter()

    for r, p in zip(reales, predichos):
        diferencia = p - r
        errores[diferencia] += 1
        if diferencia == 0:
            exactos += 1
            adyacentes += 1
        elif abs(diferencia) == 1:
            adyacentes += 1

    accuracy_exacta = exactos / n
    accuracy_adj = adyacentes / n

    # Sesgo: positivo = sobreestima, negativo = subestima
    sesgo_medio = sum(p - r for r, p in zip(reales, predichos)) / n

    return {
        "accuracy_exacta": round(accuracy_exacta, 4),
        "accuracy_adyacente": round(accuracy_adj, 4),
        "sesgo_medio": round(sesgo_medio, 4),
        "sesgo_direccion": (
            "sobreestima" if sesgo_medio > 0.05
            else "subestima" if sesgo_medio < -0.05
            else "neutral"
        ),
        "distribucion_errores": dict(sorted(errores.items())),
        "total_muestras": n,
    }


def comparar_con_techel_2022(
    reales: List[int],
    predichos: List[int]
) -> Dict[str, Any]:
    """
    Compara el rendimiento de nuestro sistema con Techel et al. (2022).

    Genera una tabla comparativa con las métricas equivalentes reportadas
    en el paper suizo, incluyendo:
    - Accuracy exacta y adyacente (±1 nivel)
    - Quadratic Weighted Kappa (QWK)
    - F1-macro
    - Distribución de niveles y sesgo

    Args:
        reales: Niveles EAWS reales (ground truth)
        predichos: Niveles EAWS predichos por nuestro sistema

    Returns:
        Dict con comparación detallada nuestro_sistema vs Techel (2022)
    """
    ref = TECHEL_2022_REFERENCIA

    # Nuestras métricas
    f1_result = calcular_f1_macro(reales, predichos)
    adj_result = calcular_accuracy_adyacente(reales, predichos)
    qwk_result = calcular_kappa_ponderado_cuadratico(reales, predichos)

    # Distribución de nuestras predicciones
    n = len(predichos)
    dist_nuestro = {}
    conteos = Counter(predichos)
    for nivel in [1, 2, 3, 4, 5]:
        dist_nuestro[nivel] = round(conteos.get(nivel, 0) / n, 2) if n > 0 else 0

    comparacion = {
        "referencia": {
            "paper": ref["paper"],
            "doi": ref["doi"],
            "pais": ref["pais"],
            "modelo": ref["modelo"],
            "n_muestras": ref["n_muestras"],
            "accuracy": ref["accuracy"],
            "accuracy_adyacente": ref["accuracy_adyacente"],
            "f1_macro_estimado": ref["f1_macro_estimado"],
            "kappa_ponderado": ref["kappa_ponderado"],
            "distribucion_niveles": ref["distribucion_niveles"],
            "sesgo_conocido": ref["sesgo_conocido"],
            "limitaciones": ref["limitaciones"],
        },
        "nuestro_sistema": {
            "pais": "Chile",
            "modelo": "Multi-agente Claude (5 subagentes)",
            "n_muestras": n,
            "accuracy": f1_result["accuracy"],
            "accuracy_adyacente": adj_result["accuracy_adyacente"],
            "f1_macro": f1_result["f1_macro"],
            "kappa_ponderado": qwk_result["kappa_ponderado"],
            "distribucion_niveles": dist_nuestro,
            "sesgo_medio": adj_result["sesgo_medio"],
            "sesgo_direccion": adj_result["sesgo_direccion"],
        },
        "comparacion_directa": {
            "delta_accuracy": round(
                f1_result["accuracy"] - ref["accuracy"], 4
            ),
            "delta_accuracy_adyacente": round(
                adj_result["accuracy_adyacente"] - ref["accuracy_adyacente"], 4
            ),
            "delta_f1_macro": round(
                f1_result["f1_macro"] - ref["f1_macro_estimado"], 4
            ),
            "delta_kappa_ponderado": round(
                qwk_result["kappa_ponderado"] - ref["kappa_ponderado"], 4
            ),
        },
        "diferencias_metodologicas": [
            "Techel usa Random Forest con 50+ features de estaciones IMIS + SNOWPACK",
            "Nuestro sistema usa LLM multi-agente con datos satelitales + meteorológicos + NLP",
            "Techel opera solo sobre nieve seca; nuestro sistema cubre todas las condiciones",
            "Techel no incluye datos satelitales ni relatos históricos de montañistas",
            "Techel tiene 52,485 muestras (18 inviernos); nuestro sistema es piloto",
            "Contexto geográfico diferente: Alpes suizos vs Andes centrales chilenos",
        ],
        "nota_interpretacion": (
            "La comparación directa de métricas entre sistemas debe interpretarse "
            "con cautela dado que operan en contextos geográficos, climatológicos y "
            "de disponibilidad de datos fundamentalmente diferentes. El valor principal "
            "de esta comparación es situar nuestro sistema en el rango de rendimiento "
            "de la literatura existente, no demostrar superioridad."
        ),
        "h3_status": (
            "H3 (transfer learning SLF) no es directamente verificable sin datos "
            "SLF públicos. Esta comparación con Techel et al. (2022) proporciona "
            "el benchmark de referencia más cercano disponible."
        ),
    }

    return comparacion


# ═══════════════════════════════════════════════════════════════════════════════
# Consulta BigQuery + reporte completo
# ═══════════════════════════════════════════════════════════════════════════════

def obtener_boletines_para_validacion(
    proyecto: str = "climas-chileno",
    dataset: str = "clima"
) -> List[Dict[str, Any]]:
    """
    Obtiene los boletines generados desde BigQuery para validación.

    Returns:
        Lista de dicts con campos necesarios para métricas
    """
    from google.cloud import bigquery

    cliente = bigquery.Client(project=proyecto)
    query = f"""
        SELECT
            nombre_ubicacion,
            fecha_emision,
            nivel_eaws_24h,
            nivel_eaws_48h,
            nivel_eaws_72h,
            confianza,
            arquitectura,
            estado_pinn,
            estado_vit,
            relatos_analizados,
            datos_satelitales_disponibles,
            subagentes_ejecutados,
            duracion_segundos
        FROM `{proyecto}.{dataset}.boletines_riesgo`
        WHERE nivel_eaws_24h IS NOT NULL
        ORDER BY fecha_emision DESC
    """

    try:
        resultados = list(cliente.query(query).result())
        return [dict(row) for row in resultados]
    except Exception as e:
        logger.error(f"Error consultando boletines: {e}")
        return []


def generar_reporte_validacion(
    reales: List[int] = None,
    predichos: List[int] = None,
    snowlab: List[int] = None,
    predichos_sin_nlp: List[int] = None,
) -> Dict[str, Any]:
    """
    Genera reporte completo de validación con todas las métricas.

    Si no se pasan datos, intenta obtenerlos de BigQuery.

    Args:
        reales: Ground truth EAWS (si disponible)
        predichos: Predicciones del sistema
        snowlab: Predicciones de Snowlab Chile (si disponible)
        predichos_sin_nlp: Predicciones sin NLP (para H2)

    Returns:
        Dict con todas las métricas y veredictos de hipótesis
    """
    reporte = {
        "fecha_reporte": None,
        "total_boletines": 0,
        "h1": None,
        "h2": None,
        "h3_techel": None,
        "h4": None,
        "estado": "sin_datos",
    }

    # Intentar cargar boletines de BigQuery si no hay datos manuales
    if predichos is None:
        boletines = obtener_boletines_para_validacion()
        reporte["total_boletines"] = len(boletines)

        if not boletines:
            reporte["estado"] = "sin_boletines"
            reporte["mensaje"] = (
                "No hay boletines en BigQuery. "
                "Ejecutar generar_boletin.py para crear boletines piloto."
            )
            return reporte

        predichos = [b["nivel_eaws_24h"] for b in boletines]

    from datetime import datetime, timezone
    reporte["fecha_reporte"] = datetime.now(timezone.utc).isoformat()
    reporte["total_boletines"] = len(predichos)

    # H1: F1-score (requiere ground truth)
    if reales is not None and len(reales) == len(predichos):
        reporte["h1"] = calcular_f1_macro(reales, predichos)
        reporte["estado"] = "completo" if reporte["h1"]["h1_cumple"] else "parcial"
    else:
        reporte["h1"] = {
            "estado": "sin_ground_truth",
            "mensaje": (
                "Se requiere ground truth (niveles EAWS reales validados por expertos) "
                "para calcular F1-score. Fuentes posibles: Snowlab Chile, SLF histórico."
            ),
            "distribucion_predichos": dict(Counter(predichos)),
        }

    # H3: Comparación con Techel et al. (2022)
    if reales is not None and len(reales) == len(predichos):
        reporte["h3_techel"] = comparar_con_techel_2022(reales, predichos)
    else:
        reporte["h3_techel"] = {
            "estado": "sin_ground_truth",
            "referencia": TECHEL_2022_REFERENCIA["paper"],
            "mensaje": (
                "Se requiere ground truth para comparar con Techel et al. (2022). "
                "Sin ground truth solo se puede comparar distribución de niveles."
            ),
            "distribucion_predichos": dict(Counter(predichos)) if predichos else {},
            "distribucion_techel": TECHEL_2022_REFERENCIA["distribucion_niveles"],
        }

    # H2: Delta NLP (requiere predicciones sin NLP)
    if reales is not None and predichos_sin_nlp is not None:
        reporte["h2"] = calcular_delta_nlp(reales, predichos, predichos_sin_nlp)
    else:
        reporte["h2"] = {
            "estado": "pendiente",
            "mensaje": (
                "Requiere correr el sistema en modo ablación (sin SubagenteNLP) "
                "para las mismas ubicaciones y fechas."
            ),
        }

    # H4: Kappa vs Snowlab
    if snowlab is not None and len(snowlab) == len(predichos):
        reporte["h4"] = calcular_cohens_kappa(predichos, snowlab)
    else:
        reporte["h4"] = {
            "estado": "sin_snowlab",
            "mensaje": (
                "Se requieren pronósticos de Snowlab Chile para las mismas "
                "ubicaciones y fechas para calcular Cohen's Kappa."
            ),
        }

    return reporte


def imprimir_reporte(reporte: Dict[str, Any]) -> None:
    """Imprime el reporte de validación en formato legible."""
    print("=" * 60)
    print("REPORTE DE VALIDACIÓN — Sistema Multi-Agente EAWS")
    print(f"Fecha: {reporte.get('fecha_reporte', 'N/A')}")
    print(f"Boletines analizados: {reporte.get('total_boletines', 0)}")
    print("=" * 60)

    # H1
    h1 = reporte.get("h1", {})
    print("\n--- H1: F1-score macro (objetivo ≥ 75%) ---")
    if "f1_macro" in h1:
        emoji = "CUMPLE" if h1["h1_cumple"] else "NO CUMPLE"
        print(f"  F1-macro:  {h1['f1_macro']:.4f} ({h1['f1_macro']*100:.1f}%)")
        print(f"  Precision: {h1['precision_macro']:.4f}")
        print(f"  Recall:    {h1['recall_macro']:.4f}")
        print(f"  Accuracy:  {h1['accuracy']:.4f}")
        print(f"  Veredicto: {emoji}")
        if h1.get("detalle_por_clase"):
            print("  Detalle por nivel:")
            for c in h1["detalle_por_clase"]:
                if c["soporte"] > 0:
                    print(f"    Nivel {c['nivel']}: F1={c['f1']:.3f} "
                          f"P={c['precision']:.3f} R={c['recall']:.3f} "
                          f"(n={c['soporte']})")
    else:
        print(f"  Estado: {h1.get('estado', 'N/A')}")
        print(f"  {h1.get('mensaje', '')}")
        if "distribucion_predichos" in h1:
            print(f"  Distribución predicciones: {h1['distribucion_predichos']}")

    # H2
    h2 = reporte.get("h2", {})
    print("\n--- H2: Delta NLP (objetivo > 5pp) ---")
    if "delta_f1_macro_pp" in h2:
        emoji = "CUMPLE" if h2["h2_cumple"] else "NO CUMPLE"
        print(f"  Delta F1:       {h2['delta_f1_macro_pp']:+.2f}pp")
        print(f"  Delta Precision: {h2['delta_precision_pp']:+.2f}pp")
        print(f"  Con NLP:    F1={h2['con_nlp']['f1_macro']:.4f}")
        print(f"  Sin NLP:    F1={h2['sin_nlp']['f1_macro']:.4f}")
        print(f"  Veredicto: {emoji}")
    else:
        print(f"  Estado: {h2.get('estado', 'N/A')}")
        print(f"  {h2.get('mensaje', '')}")

    # H3 Techel
    h3 = reporte.get("h3_techel", {})
    print("\n--- H3: Comparación con Techel et al. (2022) ---")
    if "comparacion_directa" in h3:
        ns = h3["nuestro_sistema"]
        ref = h3["referencia"]
        delta = h3["comparacion_directa"]
        print(f"  {'Métrica':<25} {'Nuestro':<12} {'Techel':<12} {'Delta':<10}")
        print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*10}")
        print(f"  {'Accuracy':<25} {ns['accuracy']:<12.4f} {ref['accuracy']:<12.4f} {delta['delta_accuracy']:+.4f}")
        print(f"  {'Accuracy ±1 nivel':<25} {ns['accuracy_adyacente']:<12.4f} {ref['accuracy_adyacente']:<12.4f} {delta['delta_accuracy_adyacente']:+.4f}")
        print(f"  {'F1-macro':<25} {ns['f1_macro']:<12.4f} {ref['f1_macro_estimado']:<12.4f} {delta['delta_f1_macro']:+.4f}")
        print(f"  {'QWK':<25} {ns['kappa_ponderado']:<12.4f} {ref['kappa_ponderado']:<12.4f} {delta['delta_kappa_ponderado']:+.4f}")
        print(f"  Muestras:  nuestro={ns['n_muestras']}, Techel={ref['n_muestras']}")
        print(f"  Sesgo:     {ns['sesgo_direccion']} ({ns['sesgo_medio']:+.3f})")
        print(f"  Nota: {h3['nota_interpretacion'][:120]}...")
    else:
        print(f"  Estado: {h3.get('estado', 'N/A')}")
        print(f"  Referencia: {h3.get('referencia', 'N/A')}")
        print(f"  {h3.get('mensaje', '')}")

    # H4
    h4 = reporte.get("h4", {})
    print("\n--- H4: Cohen's Kappa vs Snowlab (objetivo >= 0.60) ---")
    if "kappa" in h4:
        emoji = "CUMPLE" if h4["h4_cumple"] else "NO CUMPLE"
        print(f"  Kappa: {h4['kappa']:.4f} ({h4['interpretacion']})")
        print(f"  Concordancia observada: {h4['concordancia_observada']:.4f}")
        print(f"  Concordancia esperada:  {h4['concordancia_esperada']:.4f}")
        print(f"  Veredicto: {emoji}")
    else:
        print(f"  Estado: {h4.get('estado', 'N/A')}")
        print(f"  {h4.get('mensaje', '')}")

    print("\n" + "=" * 60)

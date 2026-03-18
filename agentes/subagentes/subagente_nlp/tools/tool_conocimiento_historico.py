"""
Tool: sintetizar_conocimiento_historico

Sintetiza los patrones históricos extraídos de relatos de montañistas
en un análisis estructurado de riesgo para la ubicación.

Cuando no hay relatos en BigQuery (tabla vacía / no cargada), activa
automáticamente el fallback a conocimiento_base_andino.py, que codifica
patrones documentados en literatura científica y reportes institucionales
(CEAZA, SENAPRED, CONAF, Masiokas et al. 2020).
"""

import os
import sys

_TOOL_DIR = os.path.dirname(__file__)
_AGENTES_ROOT = os.path.normpath(os.path.join(_TOOL_DIR, '../../../../'))
sys.path.insert(0, _AGENTES_ROOT)

try:
    from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
        consultar_conocimiento_zona,
        get_indice_estacional,
    )
    _BASE_ANDINO_DISPONIBLE = True
except ImportError:
    _BASE_ANDINO_DISPONIBLE = False


TOOL_CONOCIMIENTO_HISTORICO = {
    "name": "sintetizar_conocimiento_historico",
    "description": (
        "Sintetiza el conocimiento experto comunitario a partir de los patrones "
        "extraídos de relatos. Determina el tipo de alud predominante, los meses "
        "de mayor riesgo histórico, y genera una narrativa de síntesis que "
        "complementa el análisis técnico (PINN + ViT + meteorología). "
        "Si no hay relatos en BigQuery, usa la base de conocimiento andino "
        "derivada de literatura científica (CEAZA, SENAPRED, Masiokas 2020)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "total_relatos": {
                "type": "integer",
                "description": "Total de relatos encontrados para la zona"
            },
            "frecuencias_terminos": {
                "type": "object",
                "description": "Dict con término → número de menciones"
            },
            "indice_riesgo_base": {
                "type": "number",
                "description": "Índice de riesgo calculado (0.0-1.0) desde extraer_patrones"
            },
            "ubicacion": {
                "type": "string",
                "description": (
                    "Nombre de la ubicación analizada. Necesario para activar "
                    "el fallback a la base de conocimiento andino."
                )
            },
            "contexto_tecnico": {
                "type": "string",
                "description": (
                    "Resumen del contexto técnico actual (S1+S2+S3) para "
                    "comparar con el conocimiento histórico"
                )
            }
        },
        "required": ["total_relatos", "frecuencias_terminos", "indice_riesgo_base"]
    }
}


def ejecutar_sintetizar_conocimiento_historico(
    total_relatos: int,
    frecuencias_terminos: dict,
    indice_riesgo_base: float,
    ubicacion: str = "",
    contexto_tecnico: str = ""
) -> dict:
    """
    Sintetiza el conocimiento histórico de la comunidad montañera.

    Cuando no hay relatos BQ (total_relatos == 0), activa el fallback a la
    base de conocimiento andino estático, ajustado por el mes actual.

    Args:
        total_relatos: número de relatos encontrados en BQ
        frecuencias_terminos: dict término → número de menciones
        indice_riesgo_base: índice calculado por extraer_patrones (0.0-1.0)
        ubicacion: nombre de la ubicación (para fallback a base andina)
        contexto_tecnico: resumen del análisis técnico S1+S2+S3

    Returns:
        dict con síntesis del conocimiento histórico
    """
    if total_relatos == 0:
        return _fallback_conocimiento_andino(ubicacion, indice_riesgo_base)

    # ── Análisis desde relatos BQ ─────────────────────────────────────────────

    # Clasificar tipo de alud por frecuencia de términos
    menciones_placa = frecuencias_terminos.get("placa", 0)
    menciones_humeda = (frecuencias_terminos.get("húmeda", 0) +
                        frecuencias_terminos.get("mojada", 0) +
                        frecuencias_terminos.get("fusión", 0))
    menciones_reciente = (frecuencias_terminos.get("nieve blanda", 0) +
                          frecuencias_terminos.get("alud", 0) +
                          frecuencias_terminos.get("avalancha", 0))

    if menciones_placa >= max(menciones_humeda, menciones_reciente):
        tipo_predominante = "placa"
    elif menciones_humeda >= max(menciones_placa, menciones_reciente):
        tipo_predominante = "nieve_humeda"
    elif menciones_reciente > 0:
        tipo_predominante = "nieve_reciente"
    else:
        tipo_predominante = "mixto"

    # Determinar patrones recurrentes
    patrones = []
    if frecuencias_terminos.get("viento", 0) > 2:
        patrones.append("Viento frecuentemente mencionado como factor de riesgo")
    if frecuencias_terminos.get("grieta", 0) > 1:
        patrones.append("Grietas en el manto nival reportadas históricamente")
    if frecuencias_terminos.get("costra", 0) > 1:
        patrones.append("Formación de costra documentada en relatos previos")
    if frecuencias_terminos.get("peligroso", 0) > 3:
        patrones.append("Zona calificada como peligrosa en múltiples relatos")
    if frecuencias_terminos.get("canalón", 0) > 1:
        patrones.append("Canalones identificados como zonas de acumulación")

    # Confianza según número de relatos
    if total_relatos >= 10:
        confianza = "Alta"
    elif total_relatos >= 3:
        confianza = "Media"
    else:
        confianza = "Baja"

    # Índice ajustado: promedio entre base y señales cualitativas
    factor_cualitativo = min(1.0, len(patrones) / 5.0)
    indice_ajustado = round((indice_riesgo_base + factor_cualitativo) / 2.0, 3)

    # Narrativa de síntesis
    if indice_ajustado > 0.6:
        evaluacion = "La comunidad montañera documenta esta zona como de riesgo elevado"
    elif indice_ajustado > 0.3:
        evaluacion = "Los relatos sugieren riesgo moderado con eventos documentados"
    else:
        evaluacion = "Los relatos históricos no muestran patrones de alto riesgo frecuente"

    narrativa = (
        f"{evaluacion}. Se analizaron {total_relatos} relatos. "
        f"Tipo de alud predominante: {tipo_predominante}. "
    )
    if patrones:
        narrativa += "Patrones recurrentes: " + "; ".join(patrones[:3]) + "."

    return {
        "disponible": True,
        "fuente_conocimiento": "relatos_bigquery",
        "total_relatos_analizados": total_relatos,
        "tipo_alud_predominante": tipo_predominante,
        "meses_mayor_riesgo": [],
        "patrones_recurrentes": patrones,
        "indice_riesgo_ajustado": indice_ajustado,
        "confianza": confianza,
        "narrativa": narrativa,
    }


def _fallback_conocimiento_andino(ubicacion: str, indice_riesgo_base: float) -> dict:
    """
    Fallback: retorna conocimiento de la base andina cuando no hay relatos BQ.

    El índice se ajusta con el factor estacional del mes actual y el
    índice de riesgo base proveniente de las tools anteriores.
    """
    if not _BASE_ANDINO_DISPONIBLE:
        return {
            "disponible": False,
            "fuente_conocimiento": "sin_datos",
            "razon": "Sin relatos históricos ni base de conocimiento disponible",
            "tipo_alud_predominante": "desconocido",
            "meses_mayor_riesgo": [],
            "patrones_recurrentes": [],
            "indice_riesgo_ajustado": 0.0,
            "confianza": "Baja",
            "narrativa": (
                "No hay relatos históricos disponibles para esta ubicación. "
                "El análisis se basa exclusivamente en datos técnicos (PINN, ViT, meteorología)."
            ),
        }

    # Consultar base de conocimiento para la zona
    conocimiento = consultar_conocimiento_zona(ubicacion)

    # Ajustar índice con factor estacional del mes actual
    factor_estacional = get_indice_estacional()
    indice_base_andino = conocimiento.get("indice_riesgo_historico", 0.45)

    # Ponderar: 50% base andina zona + 30% estacional + 20% técnico
    indice_ajustado = round(
        0.50 * indice_base_andino
        + 0.30 * factor_estacional
        + 0.20 * indice_riesgo_base,
        3
    )

    patrones = conocimiento.get("patrones_recurrentes", [])
    meses = conocimiento.get("meses_mayor_riesgo", [])
    tipo = conocimiento.get("tipo_alud_predominante", "placa_viento")
    confianza_base = conocimiento.get("confianza", "Baja")

    # Narrativa enriquecida indicando la fuente secundaria
    zona_id = conocimiento.get("zona_identificada", "desconocida")
    narrativa = (
        f"[Fuente: base de conocimiento andino — sin relatos Andeshandbook cargados] "
        f"Zona identificada: {zona_id}. "
        f"Tipo de alud predominante históricamente: {tipo}. "
        f"Meses de mayor riesgo: {', '.join(meses) if meses else 'julio-septiembre'}. "
    )
    if patrones:
        narrativa += "Patrones documentados: " + patrones[0]
    nota = conocimiento.get("nota_academica", "")
    if nota:
        narrativa += f" Ref. académica: {nota[:120]}..."

    return {
        "disponible": True,
        "fuente_conocimiento": "base_andino_estatico",
        "zona_identificada": zona_id,
        "total_relatos_analizados": 0,
        "tipo_alud_predominante": tipo,
        "meses_mayor_riesgo": meses,
        "orientaciones_criticas": conocimiento.get("orientaciones_criticas", []),
        "patrones_recurrentes": patrones,
        "indice_riesgo_ajustado": indice_ajustado,
        "factor_estacional": factor_estacional,
        "confianza": confianza_base,
        "narrativa": narrativa,
        "advertencia": (
            "Conocimiento derivado de literatura científica y reportes institucionales. "
            "Cargar relatos Andeshandbook mejora la precisión (H2)."
        ),
    }

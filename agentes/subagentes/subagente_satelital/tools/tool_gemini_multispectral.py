"""
Tool: analizar_via_earth_ai

Segunda vía de análisis satelital usando LLM multi-spectral (Qwen3-80B/Databricks).

Vía Earth AI para S2 — complementaria al ViT actual, corre en paralelo cuando
S2_VIA = "ambas_consolidar_vit" o "ambas_consolidar_ea".

Capacidades documentadas (arxiv 2509.19087):
  - Razonamiento cualitativo cross-source: combinar GOES+MODIS+Sentinel con narrativa
  - Detección de patrones de riesgo a partir de métricas multi-fuente
  - Identificar wind slabs, cornisas, nieve húmeda a partir de señales SAR + NDSI + LST

IMPORTANTE (limitación documentada):
  - NO usar para máscaras pixel-precisas (43% errores en tareas diagramáticas)
  - Usar SOLO para razonamiento cualitativo y narrativa de riesgo
  - La señal pixel-precisa sigue siendo responsabilidad del ViT actual

Si S2_VIA = "vit_actual" (default), esta tool retorna {"via_activa": False}.
"""

import logging
import os
import time

from agentes.datos.consultor_bigquery import ConsultorBigQuery

logger = logging.getLogger(__name__)

_S2_VIA = os.environ.get("S2_VIA", "vit_actual")

TOOL_GEMINI_MULTISPECTRAL = {
    "name": "analizar_via_earth_ai",
    "description": (
        "Segunda vía de análisis satelital usando razonamiento LLM multi-spectral. "
        "Complementa el ViT con razonamiento cualitativo cross-source: combina señales "
        "GOES, MODIS, Sentinel, ERA5 para identificar factores de riesgo EAWS. "
        "Detecta wind slabs, cornisas, nieve húmeda a partir de métricas SAR + NDSI + LST. "
        "NOTA: no genera máscaras pixel-precisas — solo razonamiento cualitativo. "
        "Activa cuando S2_VIA != 'vit_actual'. Si no disponible, retorna via_activa=False."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación en BigQuery"
            },
            "contexto_vit": {
                "type": "string",
                "description": "(Opcional) Resultado del ViT para análisis cross-via"
            }
        },
        "required": ["nombre_ubicacion"]
    }
}


def ejecutar_analizar_via_earth_ai(
    nombre_ubicacion: str,
    contexto_vit: str = None,
) -> dict:
    """
    Ejecuta la vía Earth AI (Gemini multi-spectral).

    Cuando S2_VIA = "vit_actual", retorna inmediatamente con via_activa=False
    para no afectar el comportamiento por defecto.

    Args:
        nombre_ubicacion: nombre exacto de la ubicación en BigQuery
        contexto_vit: (opcional) resultado ViT para contexto cross-via

    Returns:
        dict con análisis cualitativo multi-spectral o {"via_activa": False}
    """
    if _S2_VIA == "vit_actual":
        return {
            "via_activa": False,
            "razon": "S2_VIA=vit_actual (default) — vía Earth AI desactivada",
            "activar_con": "export S2_VIA=ambas_consolidar_vit"
        }

    inicio = time.time()

    # ── Recolectar datos satelitales desde BQ ────────────────────────────────
    consultor = ConsultorBigQuery()
    estado_sat = consultor.obtener_estado_satelital(nombre_ubicacion)

    if not estado_sat.get("disponible"):
        return {
            "via_activa": True,
            "disponible": False,
            "razon": f"Sin datos satelitales BQ: {estado_sat.get('razon', 'desconocido')}",
        }

    # ── Construir prompt multi-spectral ──────────────────────────────────────
    prompt = _construir_prompt_multispectral(
        ubicacion=nombre_ubicacion,
        estado_sat=estado_sat,
        contexto_vit=contexto_vit,
    )

    # ── Inferencia LLM ────────────────────────────────────────────────────────
    try:
        from agentes.datos.cliente_llm import crear_cliente
        cliente = crear_cliente("databricks")
        respuesta = cliente.crear_mensaje(
            mensajes=[{"role": "user", "content": prompt}],
            system=_SYSTEM_PROMPT_MULTISPECTRAL,
            max_tokens=1024,
            tools=[],
        )
        texto_analisis = ""
        for bloque in respuesta.content:
            if hasattr(bloque, "text"):
                texto_analisis += bloque.text
    except Exception as exc:
        logger.error(f"tool_gemini_multispectral: error LLM — {exc}")
        return {
            "via_activa": True,
            "disponible": False,
            "razon": f"Error LLM: {exc}",
        }

    latencia_ms = round((time.time() - inicio) * 1000, 1)

    # ── Parsear resultado ────────────────────────────────────────────────────
    resultado = _parsear_analisis(texto_analisis, estado_sat)
    resultado.update({
        "via_activa": True,
        "disponible": True,
        "via": "gemini_multispectral",
        "latencia_ms": latencia_ms,
        "ubicacion": nombre_ubicacion,
        "fuentes_satelite": _detectar_fuentes(estado_sat),
        "nota_limitacion": "Solo razonamiento cualitativo — no usar para máscaras pixel-precisas",
    })

    logger.info(
        f"tool_gemini_multispectral: {nombre_ubicacion} → "
        f"score={resultado.get('score_anomalia', 0):.2f}, "
        f"lat={latencia_ms}ms"
    )
    return resultado


def _construir_prompt_multispectral(
    ubicacion: str,
    estado_sat: dict,
    contexto_vit: str = None,
) -> str:
    """Construye el prompt de análisis multi-spectral."""
    ndsi = estado_sat.get("ndsi_medio", "N/A")
    cobertura = estado_sat.get("pct_cobertura_nieve", "N/A")
    lst_dia = estado_sat.get("lst_dia_celsius", "N/A")
    lst_noche = estado_sat.get("lst_noche_celsius", "N/A")
    delta_nieve = estado_sat.get("delta_pct_nieve_24h", "N/A")
    sar_humeda = estado_sat.get("sar_pct_nieve_humeda", "N/A")
    transporte_eolico = estado_sat.get("transporte_eolico_activo", False)
    viento_kmh = estado_sat.get("viento_altura_vel_kmh", "N/A")
    ami_7d = estado_sat.get("ami_7d", "N/A")
    ami_3d = estado_sat.get("ami_3d", "N/A")

    vit_context = f"\n\nContexto ViT: {contexto_vit}" if contexto_vit else ""

    return f"""Analiza el riesgo de avalanchas para {ubicacion} usando estos datos satelitales multi-fuente:

**Señales ópticas (MODIS/Sentinel-2):**
- NDSI medio: {ndsi}
- Cobertura nieve: {cobertura}%
- Delta cobertura 24h: {delta_nieve}%
- AMI 7 días: {ami_7d}
- AMI 3 días: {ami_3d}

**Térmico (LST MODIS):**
- LST día: {lst_dia}°C
- LST noche: {lst_noche}°C

**SAR (Sentinel-1):**
- Nieve húmeda (SAR): {sar_humeda}%

**Dinámica atmosférica:**
- Transporte eólico activo: {transporte_eolico}
- Viento en altura: {viento_kmh} km/h
{vit_context}

Proporciona análisis en el formato solicitado."""


_SYSTEM_PROMPT_MULTISPECTRAL = """Eres un experto en teledetección para análisis de peligro de avalanchas en los Andes de Chile Central.

Tu rol es el razonamiento cualitativo cross-source: combinar señales de múltiples sensores para identificar factores de riesgo EAWS.

IMPORTANTE — limitaciones conocidas:
- NO generar máscaras pixel-precisas (alta tasa de error)
- Basar el análisis SOLO en los datos numéricos proporcionados
- Señalar explícitamente cuando los datos son insuficientes

Responde en este formato exacto:

## Análisis Multi-Spectral
**Score de anomalía** (0.0-1.0): X.XX
**Anomalía detectada** (sí/no): X
**Tipos de anomalía**: [lista separada por comas o "ninguna"]
**Cobertura nieve estimada**: XX.X%
**Nieve húmeda detectada** (sí/no): X
**Wind slabs indicados** (sí/no): X
**Cornisas posibles** (sí/no): X

## Descripción cualitativa
[2-4 oraciones integrando señales multi-fuente]

## Factores de riesgo EAWS observados
- [factor 1]
- [factor 2]
- [etc.]

## Confianza global (0.0-1.0): X.XX"""


def _parsear_analisis(texto: str, estado_sat: dict) -> dict:
    """Extrae campos estructurados del texto del LLM."""
    import re

    def _extraer(patron, texto, default=None):
        m = re.search(patron, texto, re.IGNORECASE)
        return m.group(1).strip() if m else default

    score_str = _extraer(r"score de anomal[ií]a.*?:\s*([\d.]+)", texto, "0.0")
    try:
        score = min(1.0, max(0.0, float(score_str)))
    except ValueError:
        score = 0.0

    anomalia_str = _extraer(r"anomal[ií]a detectada.*?:\s*(\w+)", texto, "no")
    anomalia = anomalia_str.lower() in ("sí", "si", "yes", "true", "1")

    tipos_str = _extraer(r"tipos de anomal[ií]a.*?:\s*(.+)", texto, "")
    tipos = [t.strip() for t in tipos_str.split(",") if t.strip() and t.strip().lower() != "ninguna"]

    cobertura_str = _extraer(r"cobertura nieve estimada.*?:\s*([\d.]+)", texto, "0")
    try:
        cobertura = float(cobertura_str)
    except ValueError:
        cobertura = estado_sat.get("pct_cobertura_nieve", 0.0) or 0.0

    humeda_str = _extraer(r"nieve h[uú]meda detectada.*?:\s*(\w+)", texto, "no")
    humeda = humeda_str.lower() in ("sí", "si", "yes", "true", "1")

    wslabs_str = _extraer(r"wind slabs.*?:\s*(\w+)", texto, "no")
    wind_slabs = wslabs_str.lower() in ("sí", "si", "yes", "true", "1")

    cornisas_str = _extraer(r"cornisas.*?:\s*(\w+)", texto, "no")
    cornisas = cornisas_str.lower() in ("sí", "si", "yes", "true", "1")

    # Descripción cualitativa
    m_desc = re.search(
        r"## Descripci[oó]n cualitativa\n(.+?)(?=##|\Z)", texto, re.DOTALL
    )
    descripcion = m_desc.group(1).strip() if m_desc else texto[:300]

    # Factores de riesgo
    factores = []
    m_factores = re.search(
        r"## Factores de riesgo EAWS.*?\n(.+?)(?=##|\Z)", texto, re.DOTALL
    )
    if m_factores:
        for linea in m_factores.group(1).split("\n"):
            linea = linea.strip().lstrip("- ")
            if linea:
                factores.append(linea)

    confianza_str = _extraer(r"confianza global.*?:\s*([\d.]+)", texto, "0.5")
    try:
        confianza = min(1.0, max(0.0, float(confianza_str)))
    except ValueError:
        confianza = 0.5

    return {
        "score_anomalia": score,
        "anomalia_detectada": anomalia,
        "tipos_anomalia": tipos,
        "cobertura_nieve_pct": cobertura,
        "nieve_humeda_pct": estado_sat.get("sar_pct_nieve_humeda") if humeda else None,
        "wind_slabs_indicados": wind_slabs,
        "cornisas_detectadas": cornisas,
        "descripcion_cualitativa": descripcion,
        "factores_riesgo_observados": factores,
        "confianza_global": confianza,
    }


def _detectar_fuentes(estado_sat: dict) -> list[str]:
    """Identifica qué fuentes satelitales están disponibles."""
    fuentes = ["MODIS", "GOES"]
    if estado_sat.get("sar_disponible"):
        fuentes.append("Sentinel-1")
    if estado_sat.get("ndsi_medio") is not None:
        fuentes.append("Sentinel-2/MODIS-NDSI")
    return fuentes

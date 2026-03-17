"""
Tool: detectar_anomalias_satelitales

Detecta anomalías en el estado nival a partir de la combinación de
señales satelitales: cambios de cobertura, temperatura superficial,
NDSI, y alertas del ViT.
"""

TOOL_DETECTAR_ANOMALIAS = {
    "name": "detectar_anomalias_satelitales",
    "description": (
        "Detecta y clasifica anomalías en el estado del manto nival "
        "combinando señales satelitales: NDSI, cobertura de nieve, "
        "LST (Land Surface Temperature) y el estado ViT. Identifica "
        "nevadas recientes, fusión activa, nieve húmeda y transporte "
        "eólico para determinar la estabilidad superficial del manto."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ndsi_medio": {
                "type": "number",
                "description": "NDSI actual (0-1)"
            },
            "pct_cobertura_nieve": {
                "type": "number",
                "description": "Porcentaje de cobertura de nieve actual (0-100)"
            },
            "lst_dia_celsius": {
                "type": "number",
                "description": "Temperatura superficial diurna en °C"
            },
            "lst_noche_celsius": {
                "type": "number",
                "description": "Temperatura superficial nocturna en °C"
            },
            "ciclo_diurno_amplitud": {
                "type": "number",
                "description": "Amplitud del ciclo diurno (lst_dia - lst_noche) en °C"
            },
            "delta_pct_nieve_24h": {
                "type": "number",
                "description": "Cambio en cobertura de nieve en 24h (%)"
            },
            "estado_vit": {
                "type": "string",
                "description": "Estado del ViT: CRITICO, ALERTADO, MODERADO, ESTABLE"
            },
            "alertas_previas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Alertas ya detectadas en el procesamiento NDSI"
            }
        },
        "required": [
            "ndsi_medio",
            "pct_cobertura_nieve",
            "delta_pct_nieve_24h",
            "estado_vit"
        ]
    }
}


def ejecutar_detectar_anomalias_satelitales(
    ndsi_medio: float,
    pct_cobertura_nieve: float,
    delta_pct_nieve_24h: float,
    estado_vit: str,
    lst_dia_celsius: float = None,
    lst_noche_celsius: float = None,
    ciclo_diurno_amplitud: float = None,
    alertas_previas: list = None
) -> dict:
    """
    Detecta y clasifica anomalías en el estado nival satelital.

    Args:
        ndsi_medio: NDSI actual
        pct_cobertura_nieve: cobertura actual (%)
        delta_pct_nieve_24h: cambio de cobertura en 24h
        estado_vit: estado del ViT
        lst_dia_celsius: temperatura diurna (opcional)
        lst_noche_celsius: temperatura nocturna (opcional)
        ciclo_diurno_amplitud: amplitud ciclo diurno (opcional)
        alertas_previas: alertas ya detectadas

    Returns:
        dict con anomalías detectadas, severidad y estabilidad superficial
    """
    alertas_previas = alertas_previas or []
    alertas = set(alertas_previas)

    # ─── 1. Nevada reciente ───────────────────────────────────────────────────
    if delta_pct_nieve_24h > 20:
        alertas.add("NEVADA_RECIENTE_INTENSA")
    elif delta_pct_nieve_24h > 10:
        alertas.add("NEVADA_RECIENTE_MODERADA")
    elif delta_pct_nieve_24h > 5:
        alertas.add("NEVADA_RECIENTE_LEVE")

    # ─── 2. Fusión activa ─────────────────────────────────────────────────────
    fusion_activa = False
    if lst_dia_celsius is not None and lst_dia_celsius > -2:
        if ciclo_diurno_amplitud is not None and ciclo_diurno_amplitud > 10:
            alertas.add("FUSION_ACTIVA_CICLO_DIURNO")
            fusion_activa = True
        elif delta_pct_nieve_24h < -8:
            alertas.add("FUSION_ACTIVA_PERDIDA_COBERTURA")
            fusion_activa = True

    if lst_dia_celsius is not None and lst_dia_celsius > 2:
        alertas.add("TEMPERATURA_SUPERFICIAL_POSITIVA_DIURNA")

    # ─── 3. Nieve húmeda (SAR/NDSI bajo) ─────────────────────────────────────
    if ndsi_medio < 0.3 and pct_cobertura_nieve > 40:
        alertas.add("NIEVE_HUMEDA_NDSI_BAJO")
    elif ndsi_medio < 0.35 and pct_cobertura_nieve > 60:
        alertas.add("NIEVE_POTENCIALMENTE_HUMEDA")

    # ─── 4. Transporte eólico (ciclo diurno reducido + cobertura cambiante) ──
    if (ciclo_diurno_amplitud is not None
            and ciclo_diurno_amplitud < 5
            and abs(delta_pct_nieve_24h) > 8):
        alertas.add("POSIBLE_TRANSPORTE_EOLICO")

    # ─── 5. Pérdida rápida de cobertura ──────────────────────────────────────
    if delta_pct_nieve_24h < -15:
        alertas.add("PERDIDA_RAPIDA_COBERTURA_NIVAL")

    # ─── 6. Escasa cobertura nival ─────────────────────────────────────────
    if pct_cobertura_nieve < 20:
        alertas.add("COBERTURA_NIVAL_ESCASA")

    # Incorporar señal ViT
    if estado_vit in ("CRITICO", "ALERTADO"):
        alertas.add(f"VIT_{estado_vit}")

    # ─── Clasificar estabilidad superficial ───────────────────────────────────
    estabilidad_superficial = _clasificar_estabilidad_superficial(
        alertas=alertas,
        ndsi_medio=ndsi_medio,
        pct_cobertura_nieve=pct_cobertura_nieve,
        fusion_activa=fusion_activa,
        delta_nieve=delta_pct_nieve_24h,
        estado_vit=estado_vit
    )

    # Severidad global de anomalías
    alertas_criticas = [
        a for a in alertas if any(k in a for k in [
            "INTENSA", "ACTIVA", "HUMEDA", "CRITICO", "RAPIDA"
        ])
    ]
    severidad = (
        "critica" if len(alertas_criticas) >= 2
        else "alta" if alertas_criticas
        else "moderada" if alertas
        else "baja"
    )

    return {
        "alertas_satelitales": sorted(alertas),
        "alertas_criticas": sorted(alertas_criticas),
        "severidad": severidad,
        "estabilidad_superficial_eaws": estabilidad_superficial,
        "fusion_activa": fusion_activa,
        "metricas_evaluadas": {
            "ndsi_medio": ndsi_medio,
            "cobertura_nieve_pct": pct_cobertura_nieve,
            "delta_cobertura_24h": delta_pct_nieve_24h,
            "lst_dia_celsius": lst_dia_celsius,
            "ciclo_diurno": ciclo_diurno_amplitud
        }
    }


def _clasificar_estabilidad_superficial(
    alertas: set,
    ndsi_medio: float,
    pct_cobertura_nieve: float,
    fusion_activa: bool,
    delta_nieve: float,
    estado_vit: str
) -> str:
    """
    Clasifica la estabilidad superficial en términos EAWS.

    Returns:
        "very_poor" | "poor" | "fair" | "good"
    """
    alertas_criticas = {"NEVADA_RECIENTE_INTENSA", "FUSION_ACTIVA_CICLO_DIURNO",
                        "NIEVE_HUMEDA_NDSI_BAJO", "PERDIDA_RAPIDA_COBERTURA_NIVAL",
                        "VIT_CRITICO"}
    alertas_moderadas = {"NEVADA_RECIENTE_MODERADA", "FUSION_ACTIVA_PERDIDA_COBERTURA",
                         "NIEVE_POTENCIALMENTE_HUMEDA", "POSIBLE_TRANSPORTE_EOLICO",
                         "VIT_ALERTADO"}

    n_criticas = len(alertas & alertas_criticas)
    n_moderadas = len(alertas & alertas_moderadas)

    if n_criticas >= 2:
        return "very_poor"
    elif n_criticas >= 1 or (fusion_activa and delta_nieve > 10):
        return "poor"
    elif n_moderadas >= 1 or estado_vit == "MODERADO":
        return "fair"
    else:
        return "good"

"""
Tool: consultar_estado_manto

Integra tres señales de estado del manto nival desde GEE + SAR:
  1. MODIS LST (MOD11A1/MYD11A1): temperatura superficie → manto frío/caliente
  2. ERA5-Land temperatura suelo L1/L2: gradiente térmico → metamorfismo cinético
  3. SAR Sentinel-1 VV (imagenes_satelitales): delta vs baseline → humedad superficial

Señales positivas de estabilidad (manto frío consolidado):
  - LST < -3°C sostenido → metamorfismo lento, baja probabilidad de nieve húmeda
  - Gradiente L1-L2 < -1°C sostenido → metamorfismo cinético, posibles capas frágiles

Señales de activación del manto (riesgo):
  - LST > 0°C ≥ 3 días consecutivos → activación térmica, riesgo nieve húmeda
  - SAR delta VV < -3 dB vs baseline → humedad superficial activa (Nagler et al. 2016)

Degradación graceful: si alguna fuente está vacía, el resto sigue funcionando.
"""

import logging
import os
import sys

_ROOT = os.path.join(os.path.dirname(__file__), '../../../..')
sys.path.insert(0, _ROOT)

from agentes.datos.consultor_bigquery import ConsultorBigQuery

logger = logging.getLogger(__name__)


TOOL_ESTADO_MANTO = {
    "name": "consultar_estado_manto",
    "description": (
        "Consulta el estado térmico y de humedad del manto nival desde tres fuentes: "
        "(1) MODIS LST: lst_celsius_medio_7d, dias_lst_positivo, manto_frio, activacion_termica; "
        "(2) ERA5-Land suelo: gradiente_termico_medio, metamorfismo_cinetico_posible; "
        "(3) SAR Sentinel-1: sar_delta_baseline (VV reciente − media estacional), "
        "humedad_sar_activa (delta < -3 dB → superficie húmeda → manto activo). "
        "Llamar como primera tool para enriquecer el análisis satelital. "
        "Si alguna fuente no tiene datos, retorna disponible=False para esa señal sin fallar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación (ej: 'La Parva Sector Bajo')",
            },
            "n_dias": {
                "type": "integer",
                "description": "Ventana temporal en días para LST/suelo (default: 7)",
                "default": 7,
            },
        },
        "required": ["ubicacion"],
    },
}


def _construir_interpretacion(
    manto_frio: bool,
    activacion: bool,
    metamorfismo: bool,
    humedad_sar: bool,
    dias_positivos: int,
    lst_medio: float | None,
    sar_delta: float | None,
    grad: float | None,
) -> str:
    """Genera texto interpretativo compacto para el LLM integrador."""
    señales = []

    if manto_frio:
        señales.append(
            f"Manto frío confirmado (LST medio {lst_medio:.1f}°C) — "
            "metamorfismo lento, baja probabilidad de nieve húmeda."
        )
    if activacion:
        señales.append(
            f"Activación térmica activa: {dias_positivos} días consecutivos con LST > 0°C — "
            "riesgo creciente de nieve húmeda y aludes de fondo."
        )
    if humedad_sar and sar_delta is not None:
        señales.append(
            f"Humedad superficial SAR detectada (ΔVV = {sar_delta:+.1f} dB vs baseline) — "
            "superficie húmeda, manto posiblemente activado."
        )
    if metamorfismo and grad is not None:
        señales.append(
            f"Metamorfismo cinético posible (gradiente L1-L2 = {grad:.2f}°C) — "
            "posibles capas frágiles en la base del manto."
        )
    if not señales:
        return "Estado térmico-humedad neutro — condiciones de invierno normales."
    return " | ".join(señales)


def ejecutar_consultar_estado_manto(
    ubicacion: str,
    n_dias: int = 7,
) -> dict:
    """
    Integra MODIS LST + ERA5 suelo + SAR VV para el estado del manto nival.

    Returns:
        dict con:
        Señales térmicas (MODIS LST + ERA5):
        - lst_celsius_medio_7d: float | None
        - dias_lst_positivo: int — consecutivos LST > 0°C
        - gradiente_termico_medio: float | None — L1-L2 en °C
        - manto_frio: bool — LST medio < -3°C
        - activacion_termica: bool — dias_lst_positivo ≥ 3
        - metamorfismo_cinetico_posible: bool — gradiente < -1°C
        Señales SAR (Sentinel-1):
        - sar_vv_db_reciente: float | None — VV más reciente en dB
        - sar_baseline_vv: float | None — media estacional VV
        - sar_delta_baseline: float | None — reciente - baseline (neg = más húmedo)
        - sar_pct_nieve_humeda: float | None — % pixels húmedos SAR
        - humedad_sar_activa: bool — delta < -3 dB
        Resumen:
        - interpretacion: str — texto para el LLM
        - disponible: bool — True si al menos una fuente tiene datos
    """
    consultor  = ConsultorBigQuery()
    r_termico  = consultor.obtener_estado_manto(ubicacion=ubicacion, n_dias=n_dias)
    r_sar      = consultor.obtener_sar_baseline(ubicacion=ubicacion)

    termico_ok = r_termico.get("disponible", False)
    sar_ok     = r_sar.get("disponible", False)

    if not termico_ok and not sar_ok:
        logger.info(f"[EstadoManto] Sin datos (LST ni SAR) para '{ubicacion}'")
        return {
            "disponible":                   False,
            "sin_datos":                    True,
            "lst_celsius_medio_7d":         None,
            "dias_lst_positivo":            0,
            "gradiente_termico_medio":      None,
            "temp_suelo_l1_celsius":        None,
            "manto_frio":                   False,
            "activacion_termica":           False,
            "metamorfismo_cinetico_posible": False,
            "sar_vv_db_reciente":           None,
            "sar_baseline_vv":              None,
            "sar_delta_baseline":           None,
            "sar_pct_nieve_humeda":         None,
            "humedad_sar_activa":           False,
            "interpretacion": (
                "Sin datos de estado manto — continuar solo con análisis NDSI/ViT."
            ),
        }

    # Señales térmicas
    dias_positivos = r_termico.get("dias_lst_positivo", 0) if termico_ok else 0
    lst_medio      = r_termico.get("lst_celsius_medio_7d") if termico_ok else None
    grad           = r_termico.get("gradiente_termico_medio") if termico_ok else None
    manto_frio     = r_termico.get("manto_frio", False) if termico_ok else False
    activacion     = dias_positivos >= 3
    metamorfismo   = r_termico.get("metamorfismo_cinetico_posible", False) if termico_ok else False

    # Señales SAR
    sar_delta    = r_sar.get("sar_delta_baseline") if sar_ok else None
    humedad_sar  = r_sar.get("humedad_activa", False) if sar_ok else False

    interpretacion = _construir_interpretacion(
        manto_frio, activacion, metamorfismo, humedad_sar,
        dias_positivos, lst_medio, sar_delta, grad,
    )

    logger.info(
        f"[EstadoManto] '{ubicacion}': "
        f"LST_medio={lst_medio}, dias_pos={dias_positivos}, "
        f"manto_frio={manto_frio}, activacion={activacion}, "
        f"metamorfismo={metamorfismo}, "
        f"SAR_delta={sar_delta} dB, humedad_sar={humedad_sar}"
    )

    return {
        "disponible":                   True,
        "sin_datos":                    False,
        # Señales térmicas
        "lst_celsius_medio_7d":         lst_medio,
        "dias_lst_positivo":            dias_positivos,
        "gradiente_termico_medio":      grad,
        "temp_suelo_l1_celsius":        r_termico.get("temp_suelo_l1_celsius") if termico_ok else None,
        "manto_frio":                   manto_frio,
        "activacion_termica":           activacion,
        "metamorfismo_cinetico_posible": metamorfismo,
        "n_registros_termico":          r_termico.get("n_registros", 0) if termico_ok else 0,
        "registros":                    r_termico.get("registros", []) if termico_ok else [],
        # Señales SAR
        "sar_vv_db_reciente":           r_sar.get("sar_vv_db_reciente") if sar_ok else None,
        "sar_baseline_vv":              r_sar.get("sar_baseline_vv") if sar_ok else None,
        "sar_delta_baseline":           sar_delta,
        "sar_pct_nieve_humeda":         r_sar.get("sar_pct_nieve_humeda") if sar_ok else None,
        "humedad_sar_activa":           humedad_sar,
        "fecha_sar":                    r_sar.get("fecha_sar") if sar_ok else None,
        # Resumen
        "interpretacion":               interpretacion,
    }

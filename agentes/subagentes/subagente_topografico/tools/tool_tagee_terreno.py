"""
Tool: analizar_terreno_tagee

Atributos de terreno calculados con TAGEE (Terrain Analysis in Google Earth Engine)
sobre Copernicus GLO-30. Complementa el análisis DEM con curvatura horizontal/
vertical, índices de forma y detección de zonas de convergencia de runout.

TAGEE (Donchyts et al.): https://github.com/zecojls/tagee
  - 13 atributos: curvatura horizontal, vertical, plan, perfil, shape index,
    northness, eastness, rugosidad, longitud de ladera, etc.

Si los datos aún no están en BigQuery (requiere ejecutar el script de backfill),
retorna {"disponible": False} con instrucción para generarlos.
"""

import logging

from agentes.datos.consultor_bigquery import ConsultorBigQuery

logger = logging.getLogger(__name__)


TOOL_TAGEE_TERRENO = {
    "name": "analizar_terreno_tagee",
    "description": (
        "Obtiene atributos de terreno calculados con TAGEE sobre Copernicus GLO-30: "
        "curvatura horizontal/vertical, zonas de convergencia de runout, "
        "índices northness/eastness y detección de zonas de inicio. "
        "Complementa el análisis DEM con atributos no disponibles en NASADEM. "
        "Si los datos no están disponibles, retorna disponible=False."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_ubicacion": {
                "type": "string",
                "description": "Nombre exacto de la ubicación en BigQuery"
            }
        },
        "required": ["nombre_ubicacion"]
    }
}


def ejecutar_analizar_terreno_tagee(nombre_ubicacion: str) -> dict:
    """
    Obtiene y procesa atributos TAGEE para la ubicación.

    Args:
        nombre_ubicacion: nombre exacto de la ubicación en BigQuery

    Returns:
        dict con atributos TAGEE y su interpretación EAWS,
        o {"disponible": False} si los datos no están en BQ todavía
    """
    consultor = ConsultorBigQuery()
    datos = consultor.obtener_atributos_tagee_ae(nombre_ubicacion)

    if not datos.get("disponible"):
        return {
            "disponible": False,
            "ubicacion": nombre_ubicacion,
            "razon": datos.get("razon", "Datos TAGEE no disponibles"),
            "dem_fuente": "NASADEM (activo)",
            "mensaje": (
                "Atributos TAGEE/GLO-30 no generados aún. "
                "Ejecutar: python agentes/datos/backfill/actualizar_glo30_tagee_ae.py"
            )
        }

    curv_h = datos.get("curvatura_horizontal_promedio")
    curv_v = datos.get("curvatura_vertical_promedio")
    zonas_conv = datos.get("zonas_convergencia_runout", 0)
    northness = datos.get("northness_promedio")
    eastness = datos.get("eastness_promedio")

    return {
        "disponible": True,
        "ubicacion": nombre_ubicacion,
        "dem_fuente": datos.get("dem_fuente", "COPERNICUS/DEM/GLO30"),
        "fecha_analisis": datos.get("fecha_analisis"),
        "curvatura": {
            "horizontal_promedio": curv_h,
            "vertical_promedio": curv_v,
            "interpretacion_horizontal": _interpretar_curvatura_horizontal(curv_h),
            "interpretacion_vertical": _interpretar_curvatura_vertical(curv_v),
        },
        "zonas_convergencia_runout": zonas_conv,
        "riesgo_runout": _evaluar_riesgo_runout(zonas_conv, curv_h),
        "aspecto_fisico": {
            "northness_promedio": northness,
            "eastness_promedio": eastness,
            "interpretacion": _interpretar_aspecto_fisico(northness, eastness),
        },
        "factores_eaws": _generar_factores_eaws(curv_h, curv_v, zonas_conv, northness),
    }


def _interpretar_curvatura_horizontal(curv_h: float | None) -> str:
    """
    Curvatura horizontal (plan curvature): convergencia/divergencia del flujo.

    Positiva → flujo convergente (acumulación de nieve, runout amplificado)
    Negativa → flujo divergente (dispersión, menos peligroso)
    """
    if curv_h is None:
        return "sin_datos"
    if curv_h > 0.5:
        return "alta_convergencia_flujo_critico"
    elif curv_h > 0.1:
        return "convergencia_moderada"
    elif curv_h > -0.1:
        return "plano_neutro"
    elif curv_h > -0.5:
        return "divergencia_moderada"
    else:
        return "alta_divergencia_flujo_disperso"


def _interpretar_curvatura_vertical(curv_v: float | None) -> str:
    """
    Curvatura vertical (profile curvature): aceleración/desaceleración del flujo.

    Positiva → concavidad (desaceleración, zona de depósito)
    Negativa → convexidad (aceleración, zona de inicio preferida)
    """
    if curv_v is None:
        return "sin_datos"
    if curv_v < -0.3:
        return "convexa_fuerte_zona_inicio_preferida"
    elif curv_v < -0.1:
        return "convexa_moderada_zona_inicio"
    elif curv_v < 0.1:
        return "plana_neutra"
    elif curv_v < 0.3:
        return "concava_moderada_zona_deposito"
    else:
        return "concava_fuerte_zona_deposito_principal"


def _evaluar_riesgo_runout(zonas_conv: int | None, curv_h: float | None) -> str:
    """Evalúa riesgo de runout ampliado por convergencia topográfica."""
    if zonas_conv is None:
        return "sin_datos"
    score = 0
    if zonas_conv > 50:
        score += 2
    elif zonas_conv > 20:
        score += 1
    if curv_h is not None and curv_h > 0.3:
        score += 2
    elif curv_h is not None and curv_h > 0.1:
        score += 1
    if score >= 3:
        return "muy_alto"
    elif score >= 2:
        return "alto"
    elif score >= 1:
        return "moderado"
    return "bajo"


def _interpretar_aspecto_fisico(northness: float | None, eastness: float | None) -> str:
    """Northness/Eastness son índices físicos más precisos que el aspecto categórico."""
    if northness is None:
        return "sin_datos"
    if northness > 0.7:
        return "orientacion_norte_sombra_persistente_nieve_fria"
    elif northness > 0.3:
        return "orientacion_norte_moderada"
    elif northness < -0.7:
        return "orientacion_sur_radiacion_alta_riesgo_fusion"
    elif northness < -0.3:
        return "orientacion_sur_moderada"
    else:
        return "orientacion_este_oeste_mixta"


def _generar_factores_eaws(
    curv_h: float | None,
    curv_v: float | None,
    zonas_conv: int | None,
    northness: float | None,
) -> list[str]:
    """Genera factores de atención EAWS basados en TAGEE."""
    factores = []
    if curv_h is not None and curv_h > 0.3:
        factores.append("CONVERGENCIA_TOPOGRAFICA_ALTA: zonas de runout amplificadas")
    if curv_v is not None and curv_v < -0.2:
        factores.append("CURVATURA_CONVEXA: zonas de inicio favorecidas por geometría")
    if zonas_conv is not None and zonas_conv > 30:
        factores.append(f"ZONAS_CONVERGENCIA_RUNOUT: {zonas_conv} celdas identificadas")
    if northness is not None and northness > 0.6:
        factores.append("ASPECTO_NORTE_DOMINANTE: nieve fría persistente, mayor riesgo placa viento")
    if not factores:
        factores.append("Sin factores topográficos críticos según TAGEE")
    return factores

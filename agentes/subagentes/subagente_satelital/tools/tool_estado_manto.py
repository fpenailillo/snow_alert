"""
Tool: consultar_estado_manto

Consulta el historial de temperatura de superficie (MODIS LST) y temperatura
del suelo (ERA5-Land) para detectar señales positivas de estabilidad del manto.

Señales de estabilidad (manto frío consolidado):
  - LST < -5°C sostenido → metamorfismo lento, baja probabilidad de nieve húmeda
  - Gradiente L1-L2 negativo sostenido → metamorfismo cinético, posibles capas frágiles
  - LST > 0°C varios días consecutivos → activación térmica, riesgo nieve húmeda

Esta tool provee contexto térmico que el ViT no puede inferir desde NDSI/cobertura.
Degradación graceful: si la tabla está vacía, retorna disponible=False sin fallar.
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
        "Consulta el historial de temperatura de superficie MODIS LST y temperatura "
        "del suelo ERA5-Land (últimos 7 días) para inferir el estado térmico del manto. "
        "Retorna: lst_celsius_medio_7d, dias_lst_positivo (días consecutivos con LST > 0°C), "
        "manto_frio (LST medio < -3°C → manto consolidado), activacion_termica (LST > 0°C ≥ 3 días → "
        "riesgo nieve húmeda), metamorfismo_cinetico_posible (gradiente L1-L2 < -1°C → capas frágiles). "
        "Llamar como primera tool para enriquecer el análisis satelital. "
        "Si la tabla no tiene datos, retorna disponible=False sin interrumpir el flujo."
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
                "description": "Ventana temporal en días hacia atrás (default: 7)",
                "default": 7,
            },
        },
        "required": ["ubicacion"],
    },
}


def ejecutar_consultar_estado_manto(
    ubicacion: str,
    n_dias: int = 7,
) -> dict:
    """
    Consulta el estado térmico del manto y deriva interpretaciones para el ViT.

    Returns:
        dict con:
        - lst_celsius_medio_7d: float | None
        - dias_lst_positivo: int — días consecutivos con LST > 0°C (más reciente → atrás)
        - gradiente_termico_medio: float | None — L1-L2 en °C
        - manto_frio: bool — True si LST medio < -3°C (estabilidad alta)
        - activacion_termica: bool — True si dias_lst_positivo ≥ 3 (riesgo nieve húmeda)
        - metamorfismo_cinetico_posible: bool — True si grad < -1°C (capas frágiles)
        - interpretacion: str — texto libre para el LLM integrador
        - disponible: bool
    """
    consultor = ConsultorBigQuery()
    resultado = consultor.obtener_estado_manto(ubicacion=ubicacion, n_dias=n_dias)

    if not resultado.get("disponible", False):
        logger.info(
            f"[EstadoManto] Sin datos para '{ubicacion}': "
            f"{resultado.get('razon', 'tabla vacía o sin registros')}"
        )
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
            "interpretacion": (
                "Sin datos de estado manto — continuar solo con análisis NDSI/ViT."
            ),
        }

    dias_positivos = resultado["dias_lst_positivo"]
    manto_frio     = resultado.get("manto_frio", False)
    activacion     = dias_positivos >= 3
    metamorfismo   = resultado.get("metamorfismo_cinetico_posible", False)

    if manto_frio:
        interpretacion = (
            f"Manto frío confirmado (LST medio {resultado['lst_celsius_medio_7d']:.1f}°C). "
            "Metamorfismo lento, baja probabilidad de avalanchas húmedas."
        )
    elif activacion:
        interpretacion = (
            f"Activación térmica activa: {dias_positivos} días consecutivos con LST > 0°C. "
            "Riesgo creciente de nieve húmeda y aludes de fondo."
        )
    elif metamorfismo:
        grad = resultado.get("gradiente_termico_medio")
        interpretacion = (
            f"Metamorfismo cinético posible (gradiente L1-L2 = {grad:.2f}°C). "
            "Posibles capas frágiles persistentes en la base del manto."
        )
    else:
        interpretacion = "Estado térmico neutro — condiciones de invierno normales."

    logger.info(
        f"[EstadoManto] '{ubicacion}': "
        f"LST_medio={resultado['lst_celsius_medio_7d']}, "
        f"dias_positivos={dias_positivos}, "
        f"manto_frio={manto_frio}, activacion={activacion}, "
        f"metamorfismo={metamorfismo}"
    )

    return {
        "disponible":                   True,
        "sin_datos":                    False,
        "lst_celsius_medio_7d":         resultado["lst_celsius_medio_7d"],
        "dias_lst_positivo":            dias_positivos,
        "gradiente_termico_medio":      resultado.get("gradiente_termico_medio"),
        "temp_suelo_l1_celsius":        resultado.get("temp_suelo_l1_celsius"),
        "manto_frio":                   manto_frio,
        "activacion_termica":           activacion,
        "metamorfismo_cinetico_posible": metamorfismo,
        "interpretacion":               interpretacion,
        "n_registros":                  resultado.get("n_registros", 0),
        "registros":                    resultado.get("registros", []),
    }

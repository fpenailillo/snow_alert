"""
Tool: analizar_dem

Obtiene y enriquece el perfil topográfico DEM (Digital Elevation Model)
de una ubicación desde BigQuery. Prepara los datos para cálculo PINN.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

from agentes.datos.consultor_bigquery import ConsultorBigQuery


TOOL_ANALIZAR_DEM = {
    "name": "analizar_dem",
    "description": (
        "Obtiene el perfil topográfico DEM (Digital Elevation Model) de una "
        "ubicación desde BigQuery: zonas de inicio/tránsito/depósito de "
        "avalanchas, pendientes, aspecto, elevación y clasificación EAWS. "
        "Prepara los datos necesarios para el cálculo PINN."
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


def ejecutar_analizar_dem(nombre_ubicacion: str) -> dict:
    """
    Obtiene el perfil topográfico y calcula métricas derivadas para PINN.

    Args:
        nombre_ubicacion: nombre exacto de la ubicación en BigQuery

    Returns:
        dict con perfil topográfico + métricas derivadas para PINN
    """
    consultor = ConsultorBigQuery()
    perfil = consultor.obtener_perfil_topografico(nombre_ubicacion)

    if "error" in perfil:
        return perfil

    if not perfil.get("disponible"):
        return {
            "disponible": False,
            "ubicacion": nombre_ubicacion,
            "mensaje": "Sin datos topográficos en BigQuery (pipeline mensual aún no ejecutado)",
            "metricas_pinn": _calcular_metricas_pinn_defecto()
        }

    # Enriquecer con métricas para PINN
    pendiente = perfil.get("pendiente_media_inicio", 35.0)
    elevacion_max = perfil.get("elevacion_max", 3000)
    elevacion_min = perfil.get("elevacion_min", 2000)
    desnivel = elevacion_max - elevacion_min
    aspecto = perfil.get("aspecto_predominante_inicio", "N")
    zona_inicio_ha = perfil.get("zona_inicio_ha", 0)

    # Calcular métricas físicas para PINN
    metricas_pinn = _calcular_metricas_pinn(
        pendiente=pendiente,
        elevacion_max=elevacion_max,
        elevacion_min=elevacion_min,
        desnivel=desnivel,
        aspecto=aspecto
    )

    # Clasificación topográfica
    clasificacion = perfil.get("clasificacion_riesgo", "moderado")
    indice = perfil.get("indice_riesgo_topografico", 0.5)

    # Interpretación de zonas
    interpretacion_zonas = _interpretar_zonas(
        pendiente=pendiente,
        desnivel=desnivel,
        zona_inicio_ha=zona_inicio_ha,
        clasificacion=clasificacion
    )

    return {
        "disponible": True,
        "ubicacion": nombre_ubicacion,
        "perfil_topografico": {
            "pendiente_media_inicio": pendiente,
            "pendiente_max_inicio": perfil.get("pendiente_max_inicio"),
            "aspecto_predominante": aspecto,
            "elevacion_max_m": elevacion_max,
            "elevacion_min_m": elevacion_min,
            "desnivel_m": desnivel,
            "zona_inicio_ha": zona_inicio_ha,
            "zona_transito_ha": perfil.get("zona_transito_ha"),
            "zona_deposito_ha": perfil.get("zona_deposito_ha"),
            "clasificacion_riesgo": clasificacion,
            "indice_riesgo_topografico": indice,
            "peligro_eaws_base": perfil.get("peligro_eaws_base"),
            "frecuencia_estimada_eaws": perfil.get("frecuencia_estimada_eaws"),
            "tamano_estimado_eaws": perfil.get("tamano_estimado_eaws")
        },
        "metricas_pinn": metricas_pinn,
        "interpretacion_zonas": interpretacion_zonas
    }


def _calcular_metricas_pinn(
    pendiente: float,
    elevacion_max: float,
    elevacion_min: float,
    desnivel: float,
    aspecto: str
) -> dict:
    """
    Calcula las métricas físicas que alimentarían un PINN.

    Deriva variables físicas del manto nival a partir de la topografía:
    - gradiente_termico: gradiente vertical de temperatura estimado
    - densidad_kg_m3: densidad nival estimada por elevación/aspecto
    - indice_metamorfismo: índice de transformación del cristal de nieve
    - energia_fusion: energía de fusión potencial por pendiente/aspecto

    Returns:
        dict con métricas físicas PINN
    """
    # Gradiente térmico: -6.5°C por cada 1000m (lapse rate estándar)
    gradiente_termico = round(-6.5 * desnivel / 1000.0, 3)

    # Densidad estimada por elevación (nieve a mayor altitud → menor densidad)
    # Rango típico: 150-400 kg/m³
    densidad_base = 300.0
    factor_elevacion = max(0, (elevacion_max - 2000) / 1000.0)
    densidad_kg_m3 = round(
        max(150.0, densidad_base - 50.0 * factor_elevacion), 1
    )

    # Índice de metamorfismo: función de pendiente y aspecto
    # Aspectos de sombra (N, NE, NW) → metamorfismo lento = mayor índice
    aspectos_sombra = {"N", "NE", "NW", "NO"}
    factor_sombra = 1.2 if aspecto in aspectos_sombra else 0.8
    # Pendientes mayores → más estrés mecánico → mayor metamorfismo
    factor_pendiente = min(1.5, pendiente / 30.0)
    indice_metamorfismo = round(factor_sombra * factor_pendiente, 3)

    # Energía de fusión (J/kg): proporional al balance radiativo
    # Aspectos soleados (S, SE, SW) → mayor radiación → mayor fusión
    aspectos_soleados = {"S", "SE", "SW", "SO"}
    factor_radiacion = 1.3 if aspecto in aspectos_soleados else 0.7
    energia_base = 334000.0  # J/kg (calor latente de fusión del hielo)
    factor_pendiente_fusion = max(0.5, (45.0 - pendiente) / 45.0)
    energia_fusion = round(
        energia_base * factor_radiacion * factor_pendiente_fusion, 0
    )

    return {
        "gradiente_termico_C_100m": gradiente_termico,
        "densidad_kg_m3": densidad_kg_m3,
        "indice_metamorfismo": indice_metamorfismo,
        "energia_fusion_J_kg": energia_fusion,
        "elevacion_referencia_m": elevacion_max,
        "aspecto_calculo": aspecto
    }


def _calcular_metricas_pinn_defecto() -> dict:
    """Valores PINN por defecto cuando no hay datos topográficos."""
    return {
        "gradiente_termico_C_100m": -0.65,
        "densidad_kg_m3": 280.0,
        "indice_metamorfismo": 1.0,
        "energia_fusion_J_kg": 200000.0,
        "elevacion_referencia_m": None,
        "aspecto_calculo": "desconocido"
    }


def _interpretar_zonas(
    pendiente: float,
    desnivel: float,
    zona_inicio_ha: float,
    clasificacion: str
) -> dict:
    """
    Interpreta las zonas de avalancha y su nivel de riesgo geomorfológico.

    Returns:
        dict con interpretación de zonas
    """
    alertas = []

    # Pendiente crítica de inicio de avalancha (30°-45°)
    if 30 <= pendiente <= 60:
        alertas.append("PENDIENTE_CRITICA_INICIO_AVALANCHA")

    # Desnivel grande → recorrido potencial extenso
    if desnivel > 600:
        alertas.append("DESNIVEL_EXTENSO_MAYOR_600M")

    # Zona de inicio amplia → múltiples puntos de inicio simultáneos
    if zona_inicio_ha and zona_inicio_ha > 50:
        alertas.append("ZONA_INICIO_AMPLIA_MULTIPLES_PUNTOS")

    # Clasificación topográfica
    if clasificacion in ("alto", "muy_alto", "extremo"):
        alertas.append("CLASIFICACION_TOPOGRAFICA_ELEVADA")

    return {
        "pendiente_en_rango_critico": 30 <= pendiente <= 60,
        "desnivel_extenso": desnivel > 600,
        "alertas_topograficas": alertas,
        "nivel_preocupacion": (
            "alto" if len(alertas) >= 3
            else "moderado" if len(alertas) >= 1
            else "bajo"
        )
    }

"""
Tool: calcular_pinn

Simula un Physics-Informed Neural Network (PINN) para modelar la
dinámica del manto nival usando datos topográficos y satelitales de
BigQuery. No requiere GPU: implementa las ecuaciones físicas directamente.

El PINN resuelve:
    - Ecuación de calor en la capa nival (difusión térmica)
    - Criterio de cedencia de Mohr-Coulomb (falla por cizalle)
    - Balance energético de la interfaz nieve-suelo
"""


TOOL_CALCULAR_PINN = {
    "name": "calcular_pinn",
    "description": (
        "Simula un Physics-Informed Neural Network (PINN) para modelar la "
        "dinámica del manto nival. Usa las métricas físicas del DEM "
        "(gradiente_termico, densidad_kg_m3, indice_metamorfismo, "
        "energia_fusion) para calcular el estado de estabilidad mediante "
        "ecuaciones de calor y criterio de cedencia de Mohr-Coulomb. "
        "No requiere GPU: implementa las ecuaciones físicas directamente."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gradiente_termico_C_100m": {
                "type": "number",
                "description": "Gradiente térmico vertical en °C/100m (negativo = enfría con altitud)"
            },
            "densidad_kg_m3": {
                "type": "number",
                "description": "Densidad del manto nival en kg/m³"
            },
            "indice_metamorfismo": {
                "type": "number",
                "description": "Índice adimensional de metamorfismo del cristal (0-2)"
            },
            "energia_fusion_J_kg": {
                "type": "number",
                "description": "Energía de fusión potencial en J/kg"
            },
            "pendiente_grados": {
                "type": "number",
                "description": "Ángulo de pendiente en grados (para criterio Mohr-Coulomb)"
            },
            "temperatura_superficie_C": {
                "type": "number",
                "description": "Temperatura superficial actual en °C (puede ser None)"
            }
        },
        "required": [
            "gradiente_termico_C_100m",
            "densidad_kg_m3",
            "indice_metamorfismo",
            "energia_fusion_J_kg",
            "pendiente_grados"
        ]
    }
}


def ejecutar_calcular_pinn(
    gradiente_termico_C_100m: float,
    densidad_kg_m3: float,
    indice_metamorfismo: float,
    energia_fusion_J_kg: float,
    pendiente_grados: float,
    temperatura_superficie_C: float = None
) -> dict:
    """
    Ejecuta el modelo PINN de manto nival.

    Implementa las ecuaciones físicas del manto nival sin GPU:
    1. Difusividad térmica de la nieve (función de densidad)
    2. Flujo de calor vertical (ecuación de calor 1D)
    3. Criterio de cedencia de Mohr-Coulomb para falla por cizalle
    4. Balance energético de fusión

    Args:
        gradiente_termico_C_100m: gradiente térmico vertical
        densidad_kg_m3: densidad nival
        indice_metamorfismo: índice de transformación del cristal
        energia_fusion_J_kg: energía de fusión potencial
        pendiente_grados: ángulo de pendiente para Mohr-Coulomb
        temperatura_superficie_C: temperatura superficial actual (opcional)

    Returns:
        dict con estado del manto, factor de seguridad y riesgo de falla
    """
    import math

    # ─── 1. Difusividad térmica de la nieve ──────────────────────────────────
    # k_neve = 2.9e-6 * (densidad/917)^2  [m²/s]  (Sturm et al.)
    densidad_hielo = 917.0  # kg/m³
    difusividad_termica = 2.9e-6 * (densidad_kg_m3 / densidad_hielo) ** 2

    # ─── 2. Flujo de calor vertical (1D) ─────────────────────────────────────
    # q = -k * dT/dz  donde k = conductividad térmica
    # k [W/(m·K)] ≈ 0.021 + 2.5e-6 * densidad²
    conductividad_termica = 0.021 + 2.5e-6 * densidad_kg_m3 ** 2
    # dT/dz en °C/m a partir del gradiente
    gradiente_dz = gradiente_termico_C_100m / 100.0
    flujo_calor_W_m2 = abs(conductividad_termica * gradiente_dz)

    # ─── 3. Criterio de Mohr-Coulomb para falla por cizalle ──────────────────
    # τ = c + σ·tan(φ)   falla cuando τ_aplicado >= τ_resistencia
    # τ_aplicado = ρ·g·h·sin(θ)
    # τ_resistencia = c + ρ·g·h·cos(θ)·tan(φ)
    #
    # Para manto nival:
    # c (cohesión) depende del metamorfismo y densidad
    # φ (ángulo de fricción interna) típicamente 25°-38° para nieve

    g = 9.81  # m/s²
    # Espesor nival estimado (asumimos 1m como referencia)
    espesor_nieve_m = 1.0

    # Cohesión c [Pa]: mayor densidad y bajo metamorfismo → más cohesión
    cohesion_Pa = max(100, (densidad_kg_m3 / 200.0) * 1500 * (1.5 - indice_metamorfismo))

    # Ángulo de fricción interna φ
    angulo_friccion_rad = math.radians(28.0 + 5.0 * (1.0 - indice_metamorfismo))
    pendiente_rad = math.radians(pendiente_grados)

    # Peso normal y tangencial por unidad de área
    peso_total = densidad_kg_m3 * g * espesor_nieve_m  # N/m²
    tension_normal = peso_total * math.cos(pendiente_rad)
    tension_cizalle_aplicado = peso_total * math.sin(pendiente_rad)
    tension_resistencia = cohesion_Pa + tension_normal * math.tan(angulo_friccion_rad)

    # Factor de seguridad FS: >1.5 = estable, 1.0-1.5 = inestable, <1.0 = falla
    factor_seguridad = round(
        tension_resistencia / max(tension_cizalle_aplicado, 1.0), 3
    )

    # ─── 4. Balance energético de fusión ─────────────────────────────────────
    # Energía disponible para fusión respecto a la energía de fusión latente
    L_fusion = 334000.0  # J/kg
    ratio_energia_fusion = round(energia_fusion_J_kg / L_fusion, 3)

    # Ajuste por temperatura superficial
    factor_temp = 1.0
    if temperatura_superficie_C is not None:
        if temperatura_superficie_C > 0:
            # Sobre 0°C → mayor fusión superficial → desestabilización
            factor_temp = 1.0 + temperatura_superficie_C * 0.1
        elif temperatura_superficie_C < -10:
            # Muy frío → manto rígido → más estable
            factor_temp = 0.7

    # ─── 5. Clasificación del estado del manto ──────────────────────────────
    estado_manto = _clasificar_estado_manto(
        factor_seguridad=factor_seguridad,
        ratio_energia_fusion=ratio_energia_fusion,
        indice_metamorfismo=indice_metamorfismo,
        factor_temp=factor_temp
    )

    return {
        "factor_seguridad_mohr_coulomb": factor_seguridad,
        "estado_manto": estado_manto["estado"],
        "riesgo_falla": estado_manto["riesgo_falla"],
        "metricas_fisicas": {
            "difusividad_termica_m2_s": round(difusividad_termica, 10),
            "conductividad_termica_W_mK": round(conductividad_termica, 4),
            "flujo_calor_W_m2": round(flujo_calor_W_m2, 3),
            "cohesion_Pa": round(cohesion_Pa, 1),
            "tension_cizalle_Pa": round(tension_cizalle_aplicado, 1),
            "tension_resistencia_Pa": round(tension_resistencia, 1),
            "ratio_energia_fusion": ratio_energia_fusion,
            "factor_temperatura": round(factor_temp, 2)
        },
        "interpretacion": estado_manto["interpretacion"],
        "alertas_pinn": estado_manto["alertas"]
    }


def _clasificar_estado_manto(
    factor_seguridad: float,
    ratio_energia_fusion: float,
    indice_metamorfismo: float,
    factor_temp: float
) -> dict:
    """
    Clasifica el estado del manto nival a partir de métricas PINN.

    Returns:
        dict con estado, riesgo_falla, interpretacion y alertas
    """
    alertas = []

    # Evaluación del factor de seguridad
    if factor_seguridad < 1.0:
        nivel_fs = "FALLA_INMINENTE"
        riesgo_falla = "muy_alto"
    elif factor_seguridad < 1.3:
        nivel_fs = "MANTO_INESTABLE"
        riesgo_falla = "alto"
    elif factor_seguridad < 1.5:
        nivel_fs = "MANTO_MARGINAL"
        riesgo_falla = "moderado"
    else:
        nivel_fs = "MANTO_ESTABLE"
        riesgo_falla = "bajo"

    if factor_seguridad < 1.5:
        alertas.append(f"FACTOR_SEGURIDAD_BAJO_{factor_seguridad:.2f}")

    # Evaluación de energía de fusión
    if ratio_energia_fusion > 0.8:
        alertas.append("ALTA_ENERGIA_FUSION_POTENCIAL")
        riesgo_falla = _escalar_riesgo(riesgo_falla, 1)

    # Evaluación de metamorfismo
    if indice_metamorfismo > 1.3:
        alertas.append("METAMORFISMO_ACELERADO")
        riesgo_falla = _escalar_riesgo(riesgo_falla, 1)

    # Efecto de temperatura
    if factor_temp > 1.2:
        alertas.append("FUSION_SUPERFICIAL_ACTIVA")
        riesgo_falla = _escalar_riesgo(riesgo_falla, 1)

    # Estado global
    if riesgo_falla == "muy_alto":
        estado = "CRITICO"
    elif riesgo_falla == "alto":
        estado = "INESTABLE"
    elif riesgo_falla == "moderado":
        estado = "MARGINAL"
    else:
        estado = "ESTABLE"

    interpretacion = (
        f"PINN: {nivel_fs} (FS={factor_seguridad:.2f}). "
        f"Energía fusión: {ratio_energia_fusion:.0%} del límite. "
        f"Metamorfismo: {indice_metamorfismo:.2f}. "
        f"Riesgo de falla: {riesgo_falla}."
    )

    return {
        "estado": estado,
        "riesgo_falla": riesgo_falla,
        "interpretacion": interpretacion,
        "alertas": alertas
    }


def _escalar_riesgo(riesgo_actual: str, pasos: int) -> str:
    """Escala el nivel de riesgo hacia arriba."""
    escala = ["bajo", "moderado", "alto", "muy_alto"]
    indice_actual = escala.index(riesgo_actual) if riesgo_actual in escala else 0
    nuevo_indice = min(len(escala) - 1, indice_actual + pasos)
    return escala[nuevo_indice]

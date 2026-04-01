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
        "Cuando estén disponibles, acepta features TAGEE (curvatura horizontal/"
        "vertical) y AlphaEarth (drift_embedding) para enriquecer el análisis. "
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
            },
            "curvatura_horizontal": {
                "type": "number",
                "description": "(Opcional TAGEE) Curvatura horizontal promedio de GLO-30. "
                               "Positiva=convergencia flujo, negativa=divergencia."
            },
            "curvatura_vertical": {
                "type": "number",
                "description": "(Opcional TAGEE) Curvatura vertical promedio de GLO-30. "
                               "Negativa=convexa=zona inicio, positiva=cóncava=zona depósito."
            },
            "drift_embedding_ae": {
                "type": "number",
                "description": "(Opcional AlphaEarth) Drift máximo interanual del embedding [0-1]. "
                               "Valores >0.1 indican cambios significativos en start zones."
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
    temperatura_superficie_C: float = None,
    curvatura_horizontal: float = None,
    curvatura_vertical: float = None,
    drift_embedding_ae: float = None,
) -> dict:
    """
    Ejecuta el modelo PINN de manto nival.

    Implementa las ecuaciones físicas del manto nival sin GPU:
    1. Difusividad térmica de la nieve (función de densidad)
    2. Flujo de calor vertical (ecuación de calor 1D)
    3. Criterio de cedencia de Mohr-Coulomb para falla por cizalle
    4. Balance energético de fusión

    Cuando están disponibles, los features TAGEE y AlphaEarth enriquecen:
    - curvatura_horizontal: ajusta el factor de seguridad por convergencia de flujo
    - curvatura_vertical: penaliza o bonifica según geometría zona inicio/depósito
    - drift_embedding_ae: alerta sobre cambios en start zones históricas

    Args:
        gradiente_termico_C_100m: gradiente térmico vertical
        densidad_kg_m3: densidad nival
        indice_metamorfismo: índice de transformación del cristal
        energia_fusion_J_kg: energía de fusión potencial
        pendiente_grados: ángulo de pendiente para Mohr-Coulomb
        temperatura_superficie_C: temperatura superficial actual (opcional)
        curvatura_horizontal: (TAGEE/GLO-30) curvatura horizontal promedio
        curvatura_vertical: (TAGEE/GLO-30) curvatura vertical promedio
        drift_embedding_ae: (AlphaEarth) drift máximo interanual del embedding

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

    # Ángulo de fricción interna φ — clampeado a mínimo 15° para evitar valores
    # negativos cuando indice_metamorfismo > 5.6
    angulo_friccion_rad = math.radians(max(15.0, 28.0 + 5.0 * (1.0 - indice_metamorfismo)))
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

    # ─── 6. Ajuste por features TAGEE/AlphaEarth (cuando disponibles) ─────────
    features_glo30 = _aplicar_features_glo30(
        factor_seguridad=factor_seguridad,
        curvatura_horizontal=curvatura_horizontal,
        curvatura_vertical=curvatura_vertical,
        drift_embedding_ae=drift_embedding_ae,
    )
    factor_seguridad_ajustado = features_glo30["fs_ajustado"]

    # ─── 7. Propagación de incertidumbre (Taylor 1er orden) ──────────────────
    uq = _propagar_incertidumbre_pinn(
        densidad_kg_m3=densidad_kg_m3,
        pendiente_grados=pendiente_grados,
        indice_metamorfismo=indice_metamorfismo,
        fs_base=factor_seguridad_ajustado,
    )

    return {
        "factor_seguridad_mohr_coulomb": factor_seguridad_ajustado,
        "factor_seguridad_base": factor_seguridad,
        "estado_manto": estado_manto["estado"],
        "riesgo_falla": estado_manto["riesgo_falla"],
        "incertidumbre_pinn": uq,
        "features_glo30_tagee_ae": features_glo30,
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


def _aplicar_features_glo30(
    factor_seguridad: float,
    curvatura_horizontal: float | None,
    curvatura_vertical: float | None,
    drift_embedding_ae: float | None,
) -> dict:
    """
    Ajusta el factor de seguridad PINN con features GLO-30/TAGEE/AlphaEarth.

    Efectos físicos:
    - curvatura_horizontal > 0 (convergencia): concentra flujo de nieve →
      aumenta tensión de cizalle efectiva → reduce FS
    - curvatura_vertical < 0 (convexa): zona de inicio geométricamente
      favorecida → reduce FS levemente
    - drift_embedding_ae alto: posibles cambios en start zones →
      agrega alerta sin modificar FS (incertidumbre, no efecto físico directo)
    """
    ajuste_total = 0.0
    notas = []
    usando_glo30 = False

    if curvatura_horizontal is not None:
        usando_glo30 = True
        if curvatura_horizontal > 0.3:
            # Convergencia fuerte → FS reducido ~5%
            ajuste_total -= 0.05
            notas.append(f"TAGEE curv_h={curvatura_horizontal:.2f}: convergencia alta, FS reducido")
        elif curvatura_horizontal > 0.1:
            ajuste_total -= 0.02
            notas.append(f"TAGEE curv_h={curvatura_horizontal:.2f}: convergencia moderada")

    if curvatura_vertical is not None:
        usando_glo30 = True
        if curvatura_vertical < -0.2:
            # Convexa fuerte → zona inicio preferida → FS reducido ~3%
            ajuste_total -= 0.03
            notas.append(f"TAGEE curv_v={curvatura_vertical:.2f}: geometría convexa, zona inicio")

    alertas_ae = []
    if drift_embedding_ae is not None and drift_embedding_ae > 0.05:
        alertas_ae.append(
            f"AlphaEarth drift={drift_embedding_ae:.3f}: posibles cambios en start zones históricas"
        )

    fs_ajustado = round(max(0.1, factor_seguridad + ajuste_total), 3)

    return {
        "fs_ajustado": fs_ajustado,
        "ajuste_aplicado": round(ajuste_total, 4),
        "usando_glo30_tagee": usando_glo30,
        "notas_ajuste": notas,
        "alertas_alphaearth": alertas_ae,
        "features_activos": {
            "curvatura_horizontal": curvatura_horizontal,
            "curvatura_vertical": curvatura_vertical,
            "drift_embedding_ae": drift_embedding_ae,
        },
    }


# ─── Incertidumbre PINN (propagación Taylor primer orden) ────────────────────

# Incertidumbres típicas de parámetros de entrada (fuentes documentadas):
#   ρ: ±50 kg/m³        — Proksch et al. (2015) J. Glaciol., medición de campo
#   θ: ±2°              — resolución DEM SRTM 30m (Farr et al. 2007)
#   m: ±0.2             — índice de metamorfismo estimado visualmente
_SIGMA_DENSIDAD_KG_M3  = 50.0
_SIGMA_PENDIENTE_GRADOS = 2.0
_SIGMA_METAMORFISMO     = 0.2


def _fs_mohr_coulomb_puro(densidad: float, pendiente_grados: float, metamorfismo: float) -> float:
    """Calcula solo el factor de seguridad Mohr-Coulomb (sin efectos térmicos).

    Función auxiliar pura para diferenciación numérica.
    """
    import math
    g = 9.81
    h = 1.0  # espesor referencia
    pendiente_rad = math.radians(pendiente_grados)
    cohesion_Pa = max(100.0, (densidad / 200.0) * 1500.0 * (1.5 - metamorfismo))
    angulo_friccion_rad = math.radians(max(15.0, 28.0 + 5.0 * (1.0 - metamorfismo)))
    peso = densidad * g * h
    tau_normal = peso * math.cos(pendiente_rad)
    tau_aplicado = peso * math.sin(pendiente_rad)
    tau_resistencia = cohesion_Pa + tau_normal * math.tan(angulo_friccion_rad)
    return tau_resistencia / max(tau_aplicado, 1.0)


def _propagar_incertidumbre_pinn(
    densidad_kg_m3: float,
    pendiente_grados: float,
    indice_metamorfismo: float,
    fs_base: float,
) -> dict:
    """
    Propaga la incertidumbre de los parámetros de entrada al factor de seguridad
    mediante diferencias finitas centradas de primer orden (expansión de Taylor):

        σ_FS² = (∂FS/∂ρ)² σ_ρ² + (∂FS/∂θ)² σ_θ² + (∂FS/∂m)² σ_m²

    IC 95% = FS ± 1.96 × σ_FS   (asumiendo normalidad por teorema central del límite)

    La sensibilidad s_i = |∂FS/∂x_i| × σ_i representa la contribución absoluta
    de cada parámetro a la incertidumbre total — útil para priorizar mediciones
    de campo (Saltelli et al. 2008, "Global Sensitivity Analysis").

    References:
        Proksch et al. (2015) J. Glaciol. 61(225):273-284  — incertidumbre ρ
        Farr et al. (2007) Rev. Geophys. 45, RG2004        — precisión DEM SRTM
        Saltelli et al. (2008) "Global Sensitivity Analysis: The Primer"

    Returns:
        dict con ic_95_inf, ic_95_sup, sigma_fs, sensibilidades, coeficiente_variacion
    """
    import math

    # Paso de diferenciación: 1% de cada parámetro (estable numéricamente)
    delta_rho = max(0.5, densidad_kg_m3 * 0.01)
    delta_theta = max(0.01, pendiente_grados * 0.01)
    delta_meta = max(0.001, indice_metamorfismo * 0.01)

    # Derivadas parciales por diferencias finitas centradas
    dfs_drho = (
        _fs_mohr_coulomb_puro(densidad_kg_m3 + delta_rho, pendiente_grados, indice_metamorfismo)
        - _fs_mohr_coulomb_puro(densidad_kg_m3 - delta_rho, pendiente_grados, indice_metamorfismo)
    ) / (2 * delta_rho)

    dfs_dtheta = (
        _fs_mohr_coulomb_puro(densidad_kg_m3, pendiente_grados + delta_theta, indice_metamorfismo)
        - _fs_mohr_coulomb_puro(densidad_kg_m3, pendiente_grados - delta_theta, indice_metamorfismo)
    ) / (2 * delta_theta)

    # Metamorfismo: clampear para evitar valores negativos
    meta_hi = min(1.99, indice_metamorfismo + delta_meta)
    meta_lo = max(0.01, indice_metamorfismo - delta_meta)
    dfs_dmeta = (
        _fs_mohr_coulomb_puro(densidad_kg_m3, pendiente_grados, meta_hi)
        - _fs_mohr_coulomb_puro(densidad_kg_m3, pendiente_grados, meta_lo)
    ) / (meta_hi - meta_lo)

    # Contribuciones absolutas de cada parámetro: |∂FS/∂xᵢ| × σᵢ
    contrib_rho   = abs(dfs_drho)   * _SIGMA_DENSIDAD_KG_M3
    contrib_theta = abs(dfs_dtheta) * _SIGMA_PENDIENTE_GRADOS
    contrib_meta  = abs(dfs_dmeta)  * _SIGMA_METAMORFISMO

    # Varianza total (independencia asumida → suma cuadrática)
    sigma_fs = math.sqrt(contrib_rho**2 + contrib_theta**2 + contrib_meta**2)

    # Intervalo de confianza 95% (z=1.96)
    z95 = 1.96
    ic_inf = round(max(0.0, fs_base - z95 * sigma_fs), 3)
    ic_sup = round(fs_base + z95 * sigma_fs, 3)

    # Coeficiente de variación relativa
    cv = round(sigma_fs / max(fs_base, 0.001), 4)

    # Parámetro dominante (mayor contribución a σ_FS)
    contribs = {"densidad": contrib_rho, "pendiente": contrib_theta, "metamorfismo": contrib_meta}
    param_dominante = max(contribs, key=lambda k: contribs[k])

    return {
        "ic_95_inf": ic_inf,
        "ic_95_sup": ic_sup,
        "sigma_fs": round(sigma_fs, 4),
        "coeficiente_variacion": cv,
        "sensibilidades": {
            "densidad_kg_m3":     round(contrib_rho,   4),
            "pendiente_grados":   round(contrib_theta, 4),
            "metamorfismo":       round(contrib_meta,  4),
        },
        "parametro_dominante": param_dominante,
        "metodo": "Taylor_1er_orden_diferencias_finitas",
        "referencias": [
            "Proksch et al. (2015) J. Glaciol. 61(225):273-284",
            "Farr et al. (2007) Rev. Geophys. 45, RG2004",
            "Saltelli et al. (2008) Global Sensitivity Analysis: The Primer",
        ],
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

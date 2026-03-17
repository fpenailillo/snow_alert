"""
Tool: identificar_zonas_riesgo

Identifica y prioriza las zonas de mayor riesgo de avalancha dentro de
una ubicación, combinando datos topográficos con el resultado PINN.
"""

TOOL_ZONAS_RIESGO = {
    "name": "identificar_zonas_riesgo",
    "description": (
        "Identifica y prioriza las zonas de mayor riesgo de avalancha "
        "combinando el perfil DEM con el estado PINN del manto nival. "
        "Determina zonas de inicio más probables, corredores de tránsito "
        "y áreas de depósito, con coordenadas cualitativas de riesgo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pendiente_media_inicio": {
                "type": "number",
                "description": "Pendiente media de la zona de inicio en grados"
            },
            "aspecto_predominante": {
                "type": "string",
                "description": "Aspecto predominante (N, NE, E, SE, S, SO, O, NO)"
            },
            "zona_inicio_ha": {
                "type": "number",
                "description": "Área de la zona de inicio en hectáreas"
            },
            "estado_pinn": {
                "type": "string",
                "description": "Estado PINN del manto: CRITICO, INESTABLE, MARGINAL, ESTABLE"
            },
            "riesgo_falla": {
                "type": "string",
                "description": "Nivel de riesgo PINN: muy_alto, alto, moderado, bajo"
            },
            "frecuencia_estimada_eaws": {
                "type": "string",
                "description": "Frecuencia EAWS: many, some, a_few, nearly_none"
            }
        },
        "required": [
            "pendiente_media_inicio",
            "aspecto_predominante",
            "estado_pinn",
            "riesgo_falla"
        ]
    }
}


def ejecutar_identificar_zonas_riesgo(
    pendiente_media_inicio: float,
    aspecto_predominante: str,
    estado_pinn: str,
    riesgo_falla: str,
    zona_inicio_ha: float = None,
    frecuencia_estimada_eaws: str = None
) -> dict:
    """
    Identifica y prioriza zonas de riesgo de avalancha.

    Args:
        pendiente_media_inicio: pendiente de zona inicio (grados)
        aspecto_predominante: orientación de la zona (N, S, E, O, etc.)
        estado_pinn: estado del manto según PINN
        riesgo_falla: nivel de riesgo Mohr-Coulomb
        zona_inicio_ha: área de la zona de inicio (opcional)
        frecuencia_estimada_eaws: frecuencia estimada EAWS (opcional)

    Returns:
        dict con zonas priorizadas, factores agravantes y recomendaciones
    """
    # Factores que determinan el riesgo de inicio
    factores_inicio = _evaluar_factores_inicio(
        pendiente=pendiente_media_inicio,
        aspecto=aspecto_predominante,
        zona_ha=zona_inicio_ha
    )

    # Ajuste por estado PINN
    riesgo_combinado = _combinar_riesgo_topografico_pinn(
        factores_topograficos=factores_inicio,
        estado_pinn=estado_pinn,
        riesgo_falla=riesgo_falla
    )

    # Determinar frecuencia de inicio ajustada
    frecuencia_ajustada = _ajustar_frecuencia(
        frecuencia_base=frecuencia_estimada_eaws,
        riesgo_combinado=riesgo_combinado
    )

    # Terreno de mayor riesgo para comunicar
    terreno_riesgo = _describir_terreno_riesgo(
        pendiente=pendiente_media_inicio,
        aspecto=aspecto_predominante,
        zona_ha=zona_inicio_ha,
        riesgo=riesgo_combinado
    )

    return {
        "riesgo_topografico_combinado": riesgo_combinado,
        "frecuencia_inicio_ajustada": frecuencia_ajustada,
        "factores_inicio": factores_inicio,
        "terreno_mayor_riesgo": terreno_riesgo,
        "zona_inicio_ha": zona_inicio_ha,
        "aspecto_critico": aspecto_predominante,
        "pendiente_critica_grados": pendiente_media_inicio,
        "recomendaciones_terreno": _generar_recomendaciones(
            pendiente=pendiente_media_inicio,
            aspecto=aspecto_predominante,
            riesgo=riesgo_combinado
        )
    }


def _evaluar_factores_inicio(
    pendiente: float,
    aspecto: str,
    zona_ha: float = None
) -> dict:
    """Evalúa factores topográficos de inicio de avalancha."""
    factores = {}

    # Pendiente (factor más crítico: 30°-45°)
    if pendiente >= 45:
        factores["pendiente"] = "extrema"
    elif pendiente >= 35:
        factores["pendiente"] = "muy_alta"
    elif pendiente >= 30:
        factores["pendiente"] = "alta"
    elif pendiente >= 25:
        factores["pendiente"] = "moderada"
    else:
        factores["pendiente"] = "baja"

    # Aspecto (afecta exposición solar y viento)
    aspectos_sombra = {"N", "NE", "NW", "NO"}
    aspectos_sol = {"S", "SE", "SW", "SO"}
    if aspecto in aspectos_sombra:
        factores["exposicion_solar"] = "sombra_nieve_fria"
    elif aspecto in aspectos_sol:
        factores["exposicion_solar"] = "sol_nieve_humeda"
    else:
        factores["exposicion_solar"] = "mixta"

    # Tamaño de zona
    if zona_ha:
        if zona_ha > 100:
            factores["extension_zona"] = "muy_amplia"
        elif zona_ha > 50:
            factores["extension_zona"] = "amplia"
        elif zona_ha > 10:
            factores["extension_zona"] = "moderada"
        else:
            factores["extension_zona"] = "pequeña"

    return factores


def _combinar_riesgo_topografico_pinn(
    factores_topograficos: dict,
    estado_pinn: str,
    riesgo_falla: str
) -> str:
    """Combina riesgo topográfico con estado PINN."""
    # Score de riesgo topográfico
    score = 0

    pendiente = factores_topograficos.get("pendiente", "moderada")
    if pendiente == "extrema":
        score += 3
    elif pendiente == "muy_alta":
        score += 2
    elif pendiente == "alta":
        score += 1

    # Score PINN
    mapa_pinn = {"CRITICO": 3, "INESTABLE": 2, "MARGINAL": 1, "ESTABLE": 0}
    score += mapa_pinn.get(estado_pinn, 0)

    mapa_falla = {"muy_alto": 2, "alto": 1, "moderado": 0, "bajo": 0}
    score += mapa_falla.get(riesgo_falla, 0)

    if score >= 6:
        return "muy_alto"
    elif score >= 4:
        return "alto"
    elif score >= 2:
        return "moderado"
    else:
        return "bajo"


def _ajustar_frecuencia(
    frecuencia_base: str,
    riesgo_combinado: str
) -> str:
    """Ajusta la frecuencia EAWS según el riesgo combinado."""
    escala = ["nearly_none", "a_few", "some", "many"]

    if frecuencia_base and frecuencia_base in escala:
        idx = escala.index(frecuencia_base)
    else:
        idx = 1  # a_few por defecto

    # Ajustar según riesgo combinado
    if riesgo_combinado == "muy_alto":
        idx = min(3, idx + 1)
    elif riesgo_combinado == "alto" and idx < 2:
        idx = min(3, idx + 1)

    return escala[idx]


def _describir_terreno_riesgo(
    pendiente: float,
    aspecto: str,
    zona_ha: float,
    riesgo: str
) -> str:
    """Describe el terreno de mayor riesgo para el boletín."""
    aspecto_texto = {
        "N": "orientaciones norte", "NE": "orientaciones noreste",
        "E": "orientaciones este", "SE": "orientaciones sureste",
        "S": "orientaciones sur", "SO": "orientaciones suroeste",
        "SW": "orientaciones suroeste", "O": "orientaciones oeste",
        "NO": "orientaciones noroeste", "NW": "orientaciones noroeste"
    }.get(aspecto, f"orientaciones {aspecto}")

    zona_texto = ""
    if zona_ha:
        zona_texto = f" ({zona_ha:.0f} ha de zona de inicio)"

    return (
        f"Pendientes de {pendiente:.0f}° en {aspecto_texto}{zona_texto}. "
        f"Riesgo topográfico combinado: {riesgo}."
    )


def _generar_recomendaciones(
    pendiente: float,
    aspecto: str,
    riesgo: str
) -> list:
    """Genera recomendaciones específicas para el terreno."""
    recomendaciones = []

    if riesgo in ("muy_alto", "alto"):
        recomendaciones.append(
            f"Evitar pendientes superiores a {pendiente:.0f}° "
            f"en orientaciones {aspecto}"
        )
        recomendaciones.append(
            "No transitar bajo zonas de inicio identificadas"
        )

    if riesgo == "muy_alto":
        recomendaciones.append(
            "Considerar detonación preventiva antes de apertura de pistas"
        )

    if aspecto in ("S", "SE", "SW", "SO"):
        recomendaciones.append(
            "Monitorear colapso de cornisas en horas de mayor insolación (11:00-15:00)"
        )

    if not recomendaciones:
        recomendaciones.append("Terreno con riesgo topográfico manejable bajo condiciones normales")

    return recomendaciones

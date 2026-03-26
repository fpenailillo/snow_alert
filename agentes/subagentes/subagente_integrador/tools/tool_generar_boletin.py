"""
Tool: redactar_boletin_eaws

Redacta el boletín EAWS final en español, integrando todos los análisis
de los subagentes anteriores en el formato estándar EAWS.
"""

from datetime import datetime, timezone


TOOL_GENERAR_BOLETIN = {
    "name": "redactar_boletin_eaws",
    "description": (
        "Redacta el boletín EAWS final en español integrando los análisis "
        "topográfico (PINN), satelital (ViT) y meteorológico. "
        "El boletín incluye: nivel de peligro 24h/48h/72h, situación "
        "del manto nival, factores de riesgo, terreno de mayor riesgo, "
        "pronóstico 3 días, recomendaciones y factores EAWS usados."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ubicacion": {
                "type": "string",
                "description": "Nombre de la ubicación"
            },
            "nivel_eaws_24h": {
                "type": "integer",
                "description": "Nivel EAWS para 24h (1-5)"
            },
            "nivel_eaws_48h": {
                "type": "integer",
                "description": "Nivel EAWS para 48h (1-5)"
            },
            "nivel_eaws_72h": {
                "type": "integer",
                "description": "Nivel EAWS para 72h (1-5)"
            },
            "nombre_nivel": {
                "type": "string",
                "description": "Nombre del nivel EAWS (ej: Considerable)"
            },
            "estabilidad_eaws": {
                "type": "string",
                "description": "Factor estabilidad: very_poor, poor, fair, good"
            },
            "frecuencia_eaws": {
                "type": "string",
                "description": "Factor frecuencia: many, some, a_few, nearly_none"
            },
            "tamano_eaws": {
                "type": "integer",
                "description": "Factor tamaño: 1-5"
            },
            "resumen_topografico": {
                "type": "string",
                "description": "Resumen del análisis topográfico PINN"
            },
            "resumen_satelital": {
                "type": "string",
                "description": "Resumen del análisis satelital ViT"
            },
            "resumen_meteorologico": {
                "type": "string",
                "description": "Resumen del análisis meteorológico"
            },
            "terreno_mayor_riesgo": {
                "type": "string",
                "description": "Descripción del terreno de mayor riesgo"
            },
            "factor_meteorologico": {
                "type": "string",
                "description": "Factor meteorológico EAWS identificado"
            },
            "confianza": {
                "type": "string",
                "description": "Nivel de confianza del análisis: Alta, Media, Baja"
            },
            "precipitacion_reciente_mm": {
                "type": "number",
                "description": "Precipitación registrada en las últimas 24h en mm (0 si no hubo)"
            },
            "nieve_reciente_cm": {
                "type": "number",
                "description": "Nieve nueva caída en las últimas 24h en cm (estimado si no disponible directamente)"
            },
            "tendencia_pronostico": {
                "type": "string",
                "description": "Tendencia meteorológica para los próximos días: empeorando, estable, mejorando"
            }
        },
        "required": [
            "ubicacion",
            "nivel_eaws_24h",
            "nivel_eaws_48h",
            "nivel_eaws_72h",
            "estabilidad_eaws",
            "frecuencia_eaws",
            "tamano_eaws"
        ]
    }
}


# Colores EAWS por nivel
_COLORES_EAWS = {
    1: "VERDE", 2: "AMARILLO", 3: "NARANJA", 4: "ROJO", 5: "ROJO_OSCURO"
}

# Nombres de niveles EAWS
_NOMBRES_NIVEL = {
    1: "Débil", 2: "Limitado", 3: "Considerable", 4: "Alto", 5: "Muy Alto"
}

# Nombres de factores EAWS
_NOMBRE_ESTABILIDAD = {
    "very_poor": "Muy inestable",
    "poor": "Inestable",
    "fair": "Moderada",
    "good": "Buena"
}
_NOMBRE_FRECUENCIA = {
    "many": "Muchos",
    "some": "Algunos",
    "a_few": "Pocos",
    "nearly_none": "Casi ninguno"
}


def ejecutar_redactar_boletin_eaws(
    ubicacion: str,
    nivel_eaws_24h: int,
    nivel_eaws_48h: int,
    nivel_eaws_72h: int,
    estabilidad_eaws: str,
    frecuencia_eaws: str,
    tamano_eaws: int,
    nombre_nivel: str = None,
    resumen_topografico: str = None,
    resumen_satelital: str = None,
    resumen_meteorologico: str = None,
    terreno_mayor_riesgo: str = None,
    factor_meteorologico: str = None,
    confianza: str = "Media",
    precipitacion_reciente_mm: float = None,
    nieve_reciente_cm: float = None,
    tendencia_pronostico: str = None
) -> dict:
    """
    Redacta el boletín EAWS completo en formato estándar.

    Returns:
        dict con el texto del boletín y metadatos
    """
    nombre_nivel_uso = nombre_nivel or _NOMBRES_NIVEL.get(nivel_eaws_24h, "Considerable")
    fecha_emision = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Generar secciones del boletín
    seccion_encabezado = _seccion_encabezado(
        ubicacion, nivel_eaws_24h, nivel_eaws_48h, nivel_eaws_72h,
        nombre_nivel_uso, fecha_emision
    )
    seccion_manto = _seccion_manto_nival(
        resumen_topografico, resumen_satelital, estabilidad_eaws
    )
    seccion_factores = _seccion_factores_riesgo(
        factor_meteorologico, resumen_meteorologico, estabilidad_eaws,
        precipitacion_reciente_mm=precipitacion_reciente_mm,
        nieve_reciente_cm=nieve_reciente_cm
    )
    seccion_terreno = _seccion_terreno_riesgo(
        terreno_mayor_riesgo, nivel_eaws_24h
    )
    seccion_pronostico = _seccion_pronostico(
        nivel_eaws_24h, nivel_eaws_48h, nivel_eaws_72h, factor_meteorologico,
        tendencia_pronostico=tendencia_pronostico
    )
    seccion_recomendaciones = _seccion_recomendaciones(nivel_eaws_24h)
    seccion_factores_eaws = _seccion_factores_eaws(
        estabilidad_eaws, frecuencia_eaws, tamano_eaws, confianza
    )

    boletin_texto = "\n\n".join([
        seccion_encabezado,
        seccion_manto,
        seccion_factores,
        seccion_terreno,
        seccion_pronostico,
        seccion_recomendaciones,
        seccion_factores_eaws
    ])

    return {
        "boletin_texto": boletin_texto,
        "ubicacion": ubicacion,
        "nivel_eaws_24h": nivel_eaws_24h,
        "nivel_eaws_48h": nivel_eaws_48h,
        "nivel_eaws_72h": nivel_eaws_72h,
        "fecha_emision": fecha_emision,
        "confianza": confianza
    }


def _seccion_encabezado(
    ubicacion: str,
    nivel_24h: int,
    nivel_48h: int,
    nivel_72h: int,
    nombre_nivel: str,
    fecha: str
) -> str:
    color = _COLORES_EAWS.get(nivel_24h, "NARANJA")
    return (
        f"BOLETÍN DE RIESGO DE AVALANCHAS\n"
        f"{'=' * 50}\n"
        f"Ubicación: {ubicacion}\n"
        f"Fecha de emisión: {fecha}\n\n"
        f"NIVEL DE PELIGRO\n"
        f"{'-' * 30}\n"
        f"24h → {nivel_24h} ({nombre_nivel}) [{color}]\n"
        f"48h → {nivel_48h} ({_NOMBRES_NIVEL.get(nivel_48h, nombre_nivel)}) "
        f"[{_COLORES_EAWS.get(nivel_48h, color)}]\n"
        f"72h → {nivel_72h} ({_NOMBRES_NIVEL.get(nivel_72h, nombre_nivel)}) "
        f"[{_COLORES_EAWS.get(nivel_72h, color)}]"
    )


def _seccion_manto_nival(
    resumen_topografico: str,
    resumen_satelital: str,
    estabilidad: str
) -> str:
    partes = ["SITUACIÓN DEL MANTO NIVAL\n" + "-" * 30]

    estab_texto = _NOMBRE_ESTABILIDAD.get(estabilidad, estabilidad)
    partes.append(f"Estabilidad general: {estab_texto}")

    if resumen_topografico:
        partes.append(f"Análisis PINN (topografía):\n{resumen_topografico}")

    if resumen_satelital:
        partes.append(f"Análisis ViT (satélite):\n{resumen_satelital}")

    return "\n".join(partes)


def _seccion_factores_riesgo(
    factor_meteorologico: str,
    resumen_meteorologico: str,
    estabilidad: str,
    precipitacion_reciente_mm: float = None,
    nieve_reciente_cm: float = None
) -> str:
    partes = ["FACTORES DE RIESGO\n" + "-" * 30]

    if factor_meteorologico and factor_meteorologico != "ESTABLE":
        factores_texto = factor_meteorologico.replace("+", " + ").replace("_", " ").title()
        partes.append(f"Factor meteorológico principal: {factores_texto}")

    # Datos cuantitativos de precipitación/nieve
    datos_clima = []
    if precipitacion_reciente_mm is not None:
        datos_clima.append(f"Precipitación últimas 24h: {precipitacion_reciente_mm:.1f} mm")
    if nieve_reciente_cm is not None and nieve_reciente_cm > 0:
        datos_clima.append(f"Nieve nueva estimada últimas 24h: {nieve_reciente_cm:.0f} cm")
    if datos_clima:
        partes.append("Datos climáticos recientes:\n  " + "\n  ".join(datos_clima))

    if resumen_meteorologico:
        partes.append(resumen_meteorologico)

    if estabilidad in ("very_poor", "poor"):
        partes.append(
            "⚠️ Condiciones de inestabilidad significativa — "
            "manto nival propenso a avalanchas en terreno empinado"
        )

    return "\n".join(partes)


def _seccion_terreno_riesgo(terreno: str, nivel: int) -> str:
    partes = ["TERRENO DE MAYOR RIESGO\n" + "-" * 30]

    if terreno:
        partes.append(terreno)

    if nivel >= 4:
        partes.append(
            "⚠️ PELIGRO ALTO: Evitar todo terreno avalanchoso. "
            "Las avalanchas pueden liberarse espontáneamente."
        )
    elif nivel == 3:
        partes.append(
            "Precaución en pendientes empinadas (>30°), "
            "especialmente en zonas con acumulación de nieve reciente o transportada."
        )
    elif nivel <= 2:
        partes.append(
            "Terreno generalmente seguro, con precaución "
            "en pendientes muy empinadas y bordes de cornisas."
        )

    return "\n".join(partes)


def _seccion_pronostico(
    nivel_24h: int,
    nivel_48h: int,
    nivel_72h: int,
    factor_meteorologico: str,
    tendencia_pronostico: str = None
) -> str:
    partes = ["PRONÓSTICO PRÓXIMOS 3 DÍAS\n" + "-" * 30]
    nombres = _NOMBRES_NIVEL

    if nivel_48h > nivel_24h:
        tendencia_riesgo = "en aumento"
    elif nivel_48h < nivel_24h:
        tendencia_riesgo = "en descenso"
    else:
        tendencia_riesgo = "estable"

    partes.append(
        f"Día 1: Nivel {nivel_24h} ({nombres.get(nivel_24h, '')})\n"
        f"Día 2: Nivel {nivel_48h} ({nombres.get(nivel_48h, '')})\n"
        f"Día 3: Nivel {nivel_72h} ({nombres.get(nivel_72h, '')})\n"
        f"Tendencia de riesgo: {tendencia_riesgo}"
    )

    # Contexto meteorológico del pronóstico
    if tendencia_pronostico:
        _textos_tendencia = {
            "empeorando": "Condiciones meteorológicas en deterioro — el riesgo podría aumentar respecto a lo proyectado.",
            "estable": "Condiciones meteorológicas sin cambios significativos esperados en el período.",
            "mejorando": "Condiciones meteorológicas en mejora progresiva — el riesgo disminuirá conforme avance el período."
        }
        texto = _textos_tendencia.get(tendencia_pronostico)
        if texto:
            partes.append(texto)

    if factor_meteorologico and "PRECIPITACION_CRITICA" in factor_meteorologico:
        partes.append(
            "La evolución del riesgo dependerá del cese de la precipitación "
            "y del asentamiento del manto nival nuevo."
        )
    elif factor_meteorologico and "FUSION_ACTIVA" in factor_meteorologico:
        partes.append(
            "El riesgo por fusión dependerá de la evolución de las temperaturas. "
            "Máximo peligro en horas de calor (mediodía–tarde)."
        )

    return "\n".join(partes)


def _seccion_recomendaciones(nivel: int) -> str:
    partes = ["RECOMENDACIONES\n" + "-" * 30]

    if nivel == 5:
        partes.extend([
            "🔴 PELIGRO MUY ALTO — Abstenerse de actividades en montaña",
            "• No salir a zonas de avalancha bajo ninguna circunstancia",
            "• Las avalanchas se producen de forma espontánea y masiva",
            "• Solo personal de rescate autorizado puede operar en el terreno"
        ])
    elif nivel == 4:
        partes.extend([
            "🟠 PELIGRO ALTO — Terreno avalanchoso muy peligroso",
            "• Evitar toda exposición a pendientes empinadas y sus zonas de depósito",
            "• No cruzar bajo taludes y canales de avalancha",
            "• Evaluación profesional obligatoria antes de cualquier actividad"
        ])
    elif nivel == 3:
        partes.extend([
            "🟡 PELIGRO CONSIDERABLE — Toma de decisiones cuidadosa",
            "• Evaluar cada ruta individualmente con técnicas profesionales",
            "• Llevar equipo de rescate: DVA, pala y sonda",
            "• Evitar pendientes >35° y zonas de acumulación eólica",
            "• Monitorear cambios en la temperatura y viento durante la actividad"
        ])
    elif nivel == 2:
        partes.extend([
            "🟢 PELIGRO LIMITADO — Buenas condiciones con precauciones",
            "• Precaución en pendientes muy empinadas (>40°) y bordes de cornisas",
            "• Llevar equipo de rescate básico en terreno de alta montaña",
            "• Mantenerse informado de la evolución del pronóstico"
        ])
    else:
        partes.extend([
            "🟢 PELIGRO DÉBIL — Condiciones generalmente seguras",
            "• Precaución normal en montaña",
            "• Posibles avalanchas aisladas solo en terreno muy empinado"
        ])

    return "\n".join(partes)


def _seccion_factores_eaws(
    estabilidad: str,
    frecuencia: str,
    tamano: int,
    confianza: str
) -> str:
    return (
        f"FACTORES EAWS USADOS\n"
        f"{'-' * 30}\n"
        f"Estabilidad: {estabilidad} ({_NOMBRE_ESTABILIDAD.get(estabilidad, '')})\n"
        f"Frecuencia: {frecuencia} ({_NOMBRE_FRECUENCIA.get(frecuencia, '')})\n"
        f"Tamaño: {tamano}\n"
        f"CONFIANZA: {confianza}\n"
        f"Método: Multi-Agente (PINN + ViT + Meteorología)"
    )

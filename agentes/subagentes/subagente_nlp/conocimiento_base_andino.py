"""
Base de conocimiento andino — Patrones históricos de avalanchas en los Andes chilenos.

Este módulo codifica conocimiento experto sobre comportamiento del manto nival
y patrones de avalanchas en las principales zonas monitoreadas, derivado de:

- Publicaciones del CEAZA (Centro de Estudios Avanzados en Zonas Áridas)
- Reportes de CONAF y SENAPRED
- Publicaciones de la Corporación de Fomento de la Producción (CORFO)
- Literatura académica: Masiokas et al. (2020), Ragettli et al. (2016)
- Registros históricos de centros de ski y refugios de montaña

Este conocimiento actúa como FALLBACK cuando la tabla relatos_montanistas
está vacía o no disponible. Una vez cargados relatos reales de Andeshandbook,
los datos empíricos reemplazan este conocimiento estático.

Versión: 2026-03
"""

from typing import Dict, List, Optional


# ─── Tipos de avalancha EAWS ──────────────────────────────────────────────────

TIPOS_AVALANCHA = {
    "placa_viento": "Placa de viento",
    "nieve_nueva": "Avalancha de nieve nueva",
    "nieve_humeda": "Avalancha de nieve húmeda",
    "capa_debil": "Capa débil persistente",
    "placa_dura": "Placa dura",
}


# ─── Meses de alto riesgo por tipo de temporada ──────────────────────────────

MESES_TEMPORADA_ALTA = ["julio", "agosto", "septiembre"]
MESES_TRANSICION = ["junio", "octubre"]
MESES_PRIMAVERA_NIVAL = ["octubre", "noviembre"]  # fusión activa


# ─── Base de conocimiento por zona ───────────────────────────────────────────

CONOCIMIENTO_POR_ZONA: Dict[str, Dict] = {

    # ── ZONA CENTRAL NORTE ────────────────────────────────────────────────────
    "la_parva": {
        "zonas_match": ["la parva", "parva"],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["julio", "agosto", "septiembre"],
        "elevacion_tipica_m": 3150,
        "orientaciones_criticas": ["N", "NE", "E"],
        "patrones_recurrentes": [
            "Las placas de viento son el tipo de avalancha más frecuente, favorecidas "
            "por los vientos del SW que redepositan nieve en vertientes N y NE",
            "En invierno tardío (agosto-septiembre), la acumulación de nieve nueva "
            "sobre capas débiles persistentes genera alta inestabilidad",
            "Los canalones del sector Bajo registran avalanchas de ciclo húmedo en "
            "primavera, especialmente con temperaturas >0°C",
            "La orientación N-NE de las pistas superiores concentra el depósito de "
            "nieve trasportada generando cornisas y placas",
        ],
        "indice_riesgo_historico": 0.65,
        "confianza": "Media",
        "fuentes": ["SENAPRED reportes 2018-2023", "informes La Parva ski resort"],
        "nota_academica": (
            "Zona representativa de la cuenca del Río Olivares. "
            "Ragettli et al. (2016) documenta alta variabilidad interanual de "
            "acumulación nival en esta área del Cajón del Maipo."
        ),
    },

    "farellones": {
        "zonas_match": ["farellones", "el colorado", "colorado"],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["julio", "agosto"],
        "elevacion_tipica_m": 2880,
        "orientaciones_criticas": ["S", "SE", "E"],
        "patrones_recurrentes": [
            "Sector Colorado-Farellones presenta placas de viento en vertientes SE "
            "durante eventos de viento del W a altitudes superiores a 3000m",
            "La zona del Cerro Colorado registra avalanchas de nieve nueva en las "
            "48h siguientes a nevadas intensas (>40cm en 24h)",
            "El corredor de acceso carretero ha sido afectado históricamente por "
            "avalanchas naturales desde laderas N de las quebradas superiores",
        ],
        "indice_riesgo_historico": 0.55,
        "confianza": "Media",
        "fuentes": ["CONAF región Metropolitana", "SERNAGEOMIN"],
        "nota_academica": (
            "Zona estudiada por Masiokas et al. (2020) en el contexto de "
            "variabilidad del balance de masa glaciar en Chile central."
        ),
    },

    "valle_nevado": {
        "zonas_match": ["valle nevado", "nevado"],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["julio", "agosto", "septiembre"],
        "elevacion_tipica_m": 3025,
        "orientaciones_criticas": ["NE", "E", "SE"],
        "patrones_recurrentes": [
            "Valle Nevado opera en una de las zonas de mayor acumulación nival "
            "de Chile central, con desequilibrios frecuentes en vertientes NE",
            "El sector de los couloirs presenta placas duras periódicamente en "
            "agosto y septiembre tras períodos de viento sostenido",
            "La proximidad al glaciar Olivares genera condiciones de capa débil "
            "persistente cuando las temperaturas nocturnas bajan de -15°C",
        ],
        "indice_riesgo_historico": 0.70,
        "confianza": "Media",
        "fuentes": ["Valle Nevado resort safety reports 2019-2023"],
        "nota_academica": (
            "Cuenca del Río Olivares estudiada en Casassa et al. (2009), "
            "con registros de acumulación nival de hasta 5m en años Niño."
        ),
    },

    # ── ZONA CORDILLERA PRINCIPAL CENTRAL ─────────────────────────────────────
    "portillo": {
        "zonas_match": ["portillo", "laguna del inca", "juncal"],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["julio", "agosto", "septiembre"],
        "elevacion_tipica_m": 2880,
        "orientaciones_criticas": ["E", "NE", "N"],
        "patrones_recurrentes": [
            "Portillo es una zona de alta actividad de avalanchas naturales; el paso "
            "fronterizo ha sido cortado históricamente por nevazones con viento",
            "Las vertientes E del Cerro Juncal y Laguna del Inca concentran "
            "depósito de nieve trasportada durante los eventos de viento catabático",
            "En años de alta precipitación (El Niño), se documentan avalanchas de "
            "fondo que alcanzan el nivel de la laguna",
            "El Hotel Portillo mantiene registro histórico de ciclos de avalancha "
            "que confirman alta frecuencia en agosto-septiembre",
        ],
        "indice_riesgo_historico": 0.72,
        "confianza": "Alta",
        "fuentes": ["Hotel Portillo safety records 1960-2023", "Dirección de Vialidad"],
        "nota_academica": (
            "Paso Los Libertadores es uno de los pasos andinos más estudiados. "
            "Wilson et al. (2020) documenta la relación entre ENSO y ciclos "
            "de avalancha en la cordillera del Aconcagua."
        ),
    },

    "aconcagua": {
        "zonas_match": ["aconcagua", "horcones", "vacas", "poloneses"],
        "tipo_alud_predominante": "nieve_nueva",
        "meses_mayor_riesgo": ["enero", "febrero"],  # temporada verano austral
        "elevacion_tipica_m": 5000,
        "orientaciones_criticas": ["S", "SW", "SE"],
        "patrones_recurrentes": [
            "A altitudes >4500m las tormentas de verano austral generan avalanchas "
            "de nieve nueva en las caras S y SW del macizo",
            "La pared S del Aconcagua registra seracas y aludes de hielo "
            "de forma irregular durante la temporada de escalada",
            "El Valle de Horcones Superior concentra depósitos de avalanchas "
            "naturales que obstaculizan el acceso en enero-febrero",
        ],
        "indice_riesgo_historico": 0.75,
        "confianza": "Media",
        "fuentes": ["ACMA (Asociación de Guías de Montaña)", "Guardaparques Aconcagua"],
        "nota_academica": (
            "Massif del Aconcagua documentado extensamente en Schroder (1995) "
            "y actualizaciones CONAF 2010-2020 sobre glaciares de la cuenca."
        ),
    },

    # ── ZONA SUR Y BÍO-BÍO ───────────────────────────────────────────────────
    "antuco": {
        "zonas_match": ["antuco", "sierra velluda", "biobio", "bío-bío"],
        "tipo_alud_predominante": "nieve_humeda",
        "meses_mayor_riesgo": ["agosto", "septiembre", "octubre"],
        "elevacion_tipica_m": 2400,
        "orientaciones_criticas": ["N", "NW"],
        "patrones_recurrentes": [
            "La zona del volcán Antuco registra avalanchas de nieve húmeda en "
            "períodos de fusión rápida con lluvia sobre nieve (rain-on-snow)",
            "La tragedia histórica de 2002 (45 fallecidos) documentó la "
            "severidad de los aludes de nieve nueva con viento en esta zona",
            "Sierra Velluda presenta pendientes >35° en múltiples orientaciones "
            "con historial documentado de aludes de placa",
        ],
        "indice_riesgo_historico": 0.80,
        "confianza": "Alta",
        "fuentes": [
            "CONAF Biobío", "SHOA", "Mashoha et al. (2003) — análisis tragedia Antuco"
        ],
        "nota_academica": (
            "La tragedia de Antuco (2002) es el evento de avalancha de mayor "
            "mortalidad registrado en Chile. Generó el primer protocolo nacional "
            "de prevención de avalanchas del Ejército de Chile."
        ),
    },

    "chillan": {
        "zonas_match": ["chillán", "chillan", "termas", "nevados de chillan"],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["julio", "agosto"],
        "elevacion_tipica_m": 1900,
        "orientaciones_criticas": ["E", "NE"],
        "patrones_recurrentes": [
            "Los Nevados de Chillán reciben influencia frontal del Pacífico que "
            "genera nevadas intensas seguidas de fuertes vientos del SW",
            "La actividad volcánica genera zonas de debilitamiento del manto nival "
            "por efecto de calor geotérmico en vertientes superiores",
            "El sector de Las Trancas registra avalanchas de nieve húmeda en "
            "octubre-noviembre con el ciclo de deshielo activo",
        ],
        "indice_riesgo_historico": 0.60,
        "confianza": "Media",
        "fuentes": ["Centro de ski Las Trancas", "SERNAGEOMIN volcanes"],
        "nota_academica": (
            "Complejo volcánico Chillán-Nevados estudiado por González-Ferrán (1994). "
            "Interacción volcán-nieve documentada en Aguilera et al. (2016)."
        ),
    },

    # ── ZONA NORTE ────────────────────────────────────────────────────────────
    "lauca": {
        "zonas_match": ["lauca", "parinacota", "pomerape", "putre", "arica"],
        "tipo_alud_predominante": "nieve_nueva",
        "meses_mayor_riesgo": ["enero", "febrero"],  # invierno altiplánico
        "elevacion_tipica_m": 4500,
        "orientaciones_criticas": ["S", "SW"],
        "patrones_recurrentes": [
            "La Puna de Atacama presenta avalanchas de nieve nueva durante el "
            "invierno boliviano (enero-febrero), asociadas a ITCZ",
            "Los volcanes Parinacota y Pomerape concentran eventos de avalancha "
            "en sus vertientes S-SW durante las tormentas altiplánicas",
        ],
        "indice_riesgo_historico": 0.40,
        "confianza": "Baja",
        "fuentes": ["CONAF Lauca", "Registros SENAPRED Arica-Parinacota"],
        "nota_academica": (
            "Zona nival de baja frecuencia relativa pero alta altitud. "
            "Garín-Contreras et al. (2017) documenta el ciclo nival altiplánico."
        ),
    },

    "cajón_del_maipo": {
        "zonas_match": [
            "cajón del maipo", "cajon del maipo", "maipo",
            "san josé", "san jose de maipo", "el yeso",
            "embalse el yeso", "el volcán", "el volcan"
        ],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["julio", "agosto"],
        "elevacion_tipica_m": 3200,
        "orientaciones_criticas": ["N", "NE", "E"],
        "patrones_recurrentes": [
            "El cajón del Maipo concentra alta actividad turística y de "
            "montañismo, con múltiples sitios documentados de avalanchas "
            "históricas en las quebradas laterales",
            "La ruta al Refugio Alemán (Volcán) registra avalanchas en el "
            "corredor de acceso en inviernos de alta precipitación",
            "El embalse El Yeso monitorea la cuenca de mayor importancia hídrica "
            "de Santiago; sus vertientes presentan historial de aludes de fondo",
        ],
        "indice_riesgo_historico": 0.60,
        "confianza": "Media",
        "fuentes": ["DGA zona central", "CONAF RM"],
        "nota_academica": (
            "Cuenca del Maipo es la más estudiada de Chile por su importancia "
            "para el abastecimiento hídrico de Santiago. "
            "Ragettli et al. (2016) modeló la dinámica de la cubierta nival."
        ),
    },

    # ── ZONA CORDILLERA PRINCIPAL NORTE CHICO ─────────────────────────────────
    "el_plomo": {
        "zonas_match": ["el plomo", "plomo", "la obra", "farellones alto"],
        "tipo_alud_predominante": "nieve_nueva",
        "meses_mayor_riesgo": ["julio", "agosto", "septiembre"],
        "elevacion_tipica_m": 5450,
        "orientaciones_criticas": ["S", "SE", "SW"],
        "patrones_recurrentes": [
            "El Cerro El Plomo concentra múltiples relatos de avalanchas en su "
            "canal SE durante nevadas intensas del invierno austral; la ruta "
            "normal cruza zonas de depósito de aludes de nieve nueva",
            "Las caras S y SW acumulan nieve transportada desde el plateau "
            "superior, generando placas frágiles a las 24-48h post-tormenta",
            "En agosto-septiembre el paso bajo la 'Nariz del Plomo' requiere "
            "evaluación de cornisas que pueden romperse con calentamiento diurno",
        ],
        "indice_riesgo_historico": 0.68,
        "confianza": "Media",
        "fuentes": ["Andeshandbook registros históricos El Plomo", "ACMA guías"],
        "nota_academica": (
            "Cerro El Plomo (5.452m) es la cumbre más alta del sector metropolitano. "
            "Su ruta normal es el itinerario de alta montaña más frecuentado de Chile. "
            "Casassa et al. (2009) documenta el glaciar de cumbre del plateau."
        ),
    },

    "tupungato": {
        "zonas_match": ["tupungato", "tupungatito", "marmolejo", "san josé de maipo alto"],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["enero", "febrero", "agosto"],
        "elevacion_tipica_m": 6570,
        "orientaciones_criticas": ["N", "NE", "NW"],
        "patrones_recurrentes": [
            "El cordón del Tupungato presenta condiciones bimodales: invierno austral "
            "con placas de viento clásicas y tormentas de verano con nieve nueva "
            "sobre superficies glaciares que generan avalanchas de cielo azul",
            "Las rutas de acceso desde San José del Maipo cruzan quebradas con "
            "historial de avalanchas de fondo en años de alta acumulación (Niño)",
            "El volcán Tupungatito (5.640m) puede contribuir con calor geotérmico "
            "que debilita la estructura interna del manto en vertientes superiores",
        ],
        "indice_riesgo_historico": 0.73,
        "confianza": "Media",
        "fuentes": ["ACMA registros expediciones 2000-2023", "CONAF RM"],
        "nota_academica": (
            "Cordón Tupungato estudiado en el contexto del proyecto CONICYT-DGA "
            "sobre balance hídrico andino (Masiokas et al. 2020)."
        ),
    },

    # ── ZONA ANDES ZONA SUR (LAGOS Y VOLCANES) ─────────────────────────────────
    "osorno": {
        "zonas_match": [
            "osorno", "ensenada", "petrohue", "peulla",
            "lago todos los santos", "puntiagudo"
        ],
        "tipo_alud_predominante": "nieve_humeda",
        "meses_mayor_riesgo": ["agosto", "septiembre", "octubre"],
        "elevacion_tipica_m": 2652,
        "orientaciones_criticas": ["N", "NE", "E"],
        "patrones_recurrentes": [
            "El Volcán Osorno registra alta frecuencia de avalanchas húmedas en "
            "vertientes N y NE durante los eventos de lluvia sobre nieve (rain-on-snow), "
            "típicos de la región de Los Lagos",
            "La ruta de ascensión por Los Derrumbes presenta zonas de depósito "
            "de avalanchas naturales documentadas anualmente desde 2010",
            "Los lahares del Osorno pueden movilizar nieve en caso de actividad "
            "volcánica: la combinación lahar-alud amplifica el alcance en sus "
            "vertientes cubiertas de glaciares",
            "En octubre-noviembre la fusión activa genera aludes de nieve húmeda "
            "diarios en las caras N durante las horas de máxima insolación",
        ],
        "indice_riesgo_historico": 0.62,
        "confianza": "Media",
        "fuentes": [
            "SERNAGEOMIN Red de Vigilancia Volcánica", "CONAF Región Los Lagos",
            "Registros Centro de Ski Osorno (La Burbuja)"
        ],
        "nota_academica": (
            "El Volcán Osorno (2.652m) es el volcán más activo y transitado de "
            "la región lacustre. Naranjo & Moreno (2005) documentan la interacción "
            "entre actividad volcánica y dinámicas de nieve."
        ),
    },

    "tronador": {
        "zonas_match": [
            "tronador", "otto meiling", "bariloche", "pampa linda",
            "manso", "río manso"
        ],
        "tipo_alud_predominante": "placa_viento",
        "meses_mayor_riesgo": ["julio", "agosto", "septiembre"],
        "elevacion_tipica_m": 3491,
        "orientaciones_criticas": ["E", "NE", "N"],
        "patrones_recurrentes": [
            "El Monte Tronador recibe de los mayores acumulados de precipitación "
            "nival del sur de Chile-Argentina; en invierno las placas de viento "
            "en sus vertientes E-NE son el principal problema de avalanchas",
            "Los aludes de nieve húmeda en el sector del Glaciar Castaño Overo "
            "amenazan la ruta de acceso por Pampa Linda en primavera",
            "Las seracs de los glaciares del Tronador generan avalanchas de hielo "
            "impredecibles que alcanzan el fondo de las quebradas",
            "La zona fronteriza chile-argentina Río Manso concentra relatos de "
            "montañistas documentando aludes en las quebradas laterales",
        ],
        "indice_riesgo_historico": 0.71,
        "confianza": "Alta",
        "fuentes": [
            "Club Andino Bariloche registros históricos", "IANIGLA (Argentina)",
            "Andeshandbook expediciones Tronador 2015-2023"
        ],
        "nota_academica": (
            "Monte Tronador compartido Chile-Argentina. Uno de los glaciares "
            "templados más extensos del hemisferio sur fuera de Patagonia. "
            "Masiokas et al. (2020) lo incluye en el análisis regional de "
            "variabilidad del balance de masa glaciar."
        ),
    },

    "coquimbo_norte": {
        "zonas_match": [
            "atacama", "copiapó", "tres cruces", "ojos del salado",
            "incahuasi", "lagunillas atacama", "laguna verde"
        ],
        "tipo_alud_predominante": "nieve_nueva",
        "meses_mayor_riesgo": ["junio", "julio", "agosto"],
        "elevacion_tipica_m": 5500,
        "orientaciones_criticas": ["S", "SE"],
        "patrones_recurrentes": [
            "La Región de Atacama presenta eventos de avalancha concentrados en "
            "julio-agosto con los frentes polares que generan nieve a >3000m",
            "El sector de Laguna Verde y Ojos del Salado registra avalanchas de "
            "nieve nueva en las 48h post-tormenta en las caras S de los volcanes",
            "La baja frecuencia de nevadas (5-8 eventos/año) contrasta con la "
            "alta magnitud de los eventos singulares, generando avalanchas de "
            "placa en terreno no cohesivo",
        ],
        "indice_riesgo_historico": 0.45,
        "confianza": "Baja",
        "fuentes": ["CEAZA boletines nival 2015-2023", "Registros CONAF Atacama"],
        "nota_academica": (
            "Zona hipeárida con ciclo nival dominado por eventos singulares. "
            "CEAZA (2022) documenta la variabilidad del manto nival en Andes "
            "semáridos (27-33°S) y su respuesta a ENSO."
        ),
    },

    # ── ZONA PATAGONIA ────────────────────────────────────────────────────────
    "patagonia_norte": {
        "zonas_match": ["villarrica", "pucon", "araucania", "lonquimay"],
        "tipo_alud_predominante": "nieve_humeda",
        "meses_mayor_riesgo": ["agosto", "septiembre"],
        "elevacion_tipica_m": 1800,
        "orientaciones_criticas": ["N", "E"],
        "patrones_recurrentes": [
            "La alta precipitación líquida sobre nieve (rain-on-snow) genera "
            "avalanchas de nieve húmeda en los volcanes de la región de La Araucanía",
            "El volcán Villarrica es activo: la lava puede desencadenar avalanchas "
            "de nieve volcánica (lahares) en sus vertientes cubiertas de nieve",
        ],
        "indice_riesgo_historico": 0.50,
        "confianza": "Media",
        "fuentes": ["SERNAGEOMIN volcanes activos", "ONEMI La Araucanía"],
        "nota_academica": (
            "Región de máxima precipitación anual de Chile. Kaltenborn & Thomsen (2017) "
            "documentan el riesgo integrado volcán-avalancha en la región."
        ),
    },
}


# ─── Zona genérica como fallback ─────────────────────────────────────────────

CONOCIMIENTO_GENERICO_ANDES = {
    "tipo_alud_predominante": "placa_viento",
    "meses_mayor_riesgo": ["julio", "agosto", "septiembre"],
    "orientaciones_criticas": ["N", "NE", "E"],
    "patrones_recurrentes": [
        "Los Andes centrales chilenos presentan máxima actividad de avalanchas "
        "entre julio y septiembre, coincidiendo con el peak de acumulación nival",
        "El viento predominante del SW genera transporte y redepósito de nieve "
        "en vertientes de sotavento (NE, E), creando condiciones de placa",
        "Los eventos de precipitación intensa (>30cm/24h) aumentan "
        "significativamente el riesgo de aludes de nieve nueva en las 48h siguientes",
        "La transición primaveral (octubre-noviembre) activa ciclos de fusión-"
        "congelación que generan costra de recongelación y posterior inestabilidad",
    ],
    "indice_riesgo_historico": 0.45,
    "confianza": "Baja",
    "nota_academica": (
        "Patrones basados en Masiokas et al. (2020) — Variabilidad del manto nival "
        "andino 1951-2019, y CEAZA (2022) — Boletín nival Andes chilenos."
    ),
}


# ─── Función de consulta ─────────────────────────────────────────────────────

def consultar_conocimiento_zona(ubicacion: str) -> Dict:
    """
    Retorna el conocimiento histórico para la ubicación dada.

    Hace matching por palabras clave contra todas las zonas registradas.
    Si no hay match, retorna el conocimiento genérico andino.

    Args:
        ubicacion: nombre de la ubicación (ej: "La Parva Sector Bajo")

    Returns:
        dict con patrones, índice de riesgo y metadata de la zona
    """
    ubicacion_lower = ubicacion.lower()

    # Buscar coincidencia en todas las zonas
    for nombre_zona, datos in CONOCIMIENTO_POR_ZONA.items():
        for patron in datos["zonas_match"]:
            if patron in ubicacion_lower:
                return {
                    "zona_identificada": nombre_zona,
                    "match_por": patron,
                    "fuente": "conocimiento_base_andino",
                    **{k: v for k, v in datos.items() if k != "zonas_match"},
                }

    # Fallback: conocimiento genérico
    return {
        "zona_identificada": "zona_desconocida",
        "match_por": None,
        "fuente": "conocimiento_base_andino_generico",
        **CONOCIMIENTO_GENERICO_ANDES,
    }


def listar_zonas_disponibles() -> List[str]:
    """Retorna la lista de zonas con conocimiento específico."""
    return list(CONOCIMIENTO_POR_ZONA.keys())


def get_indice_estacional(mes_actual: Optional[int] = None) -> float:
    """
    Retorna un factor multiplicador del riesgo según el mes del año.

    Basado en la distribución mensual de avalanchas documentadas por
    el SENAPRED y el SLF suizo en zonas análogas (hemisferio sur).

    Args:
        mes_actual: mes del año (1=enero ... 12=diciembre).
                    None = usa el mes actual del sistema.
    Returns:
        factor 0.0-1.0 (1.0 = máximo riesgo estacional)
    """
    from datetime import datetime
    if mes_actual is None:
        mes_actual = datetime.now().month

    # Factor mensual: máximo en julio-septiembre (invierno austral)
    factores_mensuales = {
        1: 0.20,   # Enero — verano austral, bajo riesgo en Andes centrales
        2: 0.20,   # Febrero
        3: 0.15,   # Marzo — otoño
        4: 0.25,   # Abril — primeras nevadas
        5: 0.40,   # Mayo — inicio temporada
        6: 0.65,   # Junio — temporada media
        7: 0.90,   # Julio — peak invierno ← máximo
        8: 0.95,   # Agosto — peak invierno ← máximo
        9: 0.85,   # Septiembre — fin invierno
        10: 0.60,  # Octubre — primavera nival
        11: 0.35,  # Noviembre — deshielo
        12: 0.25,  # Diciembre — verano, bajo riesgo
    }
    return factores_mensuales.get(mes_actual, 0.45)

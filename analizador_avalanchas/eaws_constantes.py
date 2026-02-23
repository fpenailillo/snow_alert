"""
Constantes y Matriz EAWS para Evaluación de Peligro de Avalanchas

Este módulo contiene las constantes, clases y la matriz de lookup completa
del European Avalanche Warning Services (EAWS) para la determinación del
nivel de peligro de avalanchas (1-5).

Referencias:
- Müller, K., Techel, F., & Mitterer, C. (2025). The EAWS matrix, a decision
  support tool to determine the regional avalanche danger level (Part A):
  conceptual development. Nat. Hazards Earth Syst. Sci., 25, 4503-4525.
  https://doi.org/10.5194/nhess-25-4503-2025

- Techel, F., Müller, K., Marquardt, C., & Mitterer, C. (2025). The EAWS matrix,
  a look-up table to determine the regional avalanche danger level (Part B):
  Operational testing and use. EGUsphere Preprint.
  https://doi.org/10.5194/egusphere-2025-3349

- Techel, F., Müller, K., & Schweizer, J. (2020). On the importance of snowpack
  stability, the frequency distribution of snowpack stability and avalanche size
  in assessing the avalanche danger level. The Cryosphere, 14, 3503-3521.
"""

from typing import Dict, Tuple, Optional


# =============================================================================
# NIVELES DE PELIGRO EAWS (Escala 1-5)
# =============================================================================

NIVELES_PELIGRO = {
    1: {
        'nombre': 'Débil',
        'nombre_en': 'Low',
        'color': '#CCFF66',  # Verde claro
        'descripcion': 'Condiciones generalmente favorables. El desencadenamiento '
                       'de avalanchas solo es posible en terreno muy empinado y extremo.',
        'probabilidad_natural': 'Muy baja',
        'probabilidad_humana': 'Muy baja'
    },
    2: {
        'nombre': 'Moderado',
        'nombre_en': 'Moderate',
        'color': '#FFFF00',  # Amarillo
        'descripcion': 'Condiciones de peligro elevado en terreno empinado específico. '
                       'Las avalanchas pueden desencadenarse por sobrecargas fuertes.',
        'probabilidad_natural': 'Baja',
        'probabilidad_humana': 'Posible en terreno empinado'
    },
    3: {
        'nombre': 'Notable',
        'nombre_en': 'Considerable',
        'color': '#FF9900',  # Naranja
        'descripcion': 'Condiciones de peligro críticas en muchas pendientes empinadas. '
                       'El desencadenamiento es posible con sobrecargas débiles.',
        'probabilidad_natural': 'Posible',
        'probabilidad_humana': 'Probable'
    },
    4: {
        'nombre': 'Fuerte',
        'nombre_en': 'High',
        'color': '#FF0000',  # Rojo
        'descripcion': 'Condiciones muy inestables. El desencadenamiento es probable '
                       'incluso con sobrecargas débiles en muchas pendientes empinadas.',
        'probabilidad_natural': 'Probable',
        'probabilidad_humana': 'Muy probable'
    },
    5: {
        'nombre': 'Muy Fuerte',
        'nombre_en': 'Very High',
        'color': '#000000',  # Negro (con patrón de cuadros)
        'descripcion': 'Situación extraordinaria. Se esperan numerosas avalanchas '
                       'espontáneas de gran tamaño. Evitar todo terreno de avalanchas.',
        'probabilidad_natural': 'Seguro',
        'probabilidad_humana': 'Seguro'
    }
}


# =============================================================================
# CLASES DE ESTABILIDAD DEL MANTO NIVAL (Factor 1 EAWS)
# Referencia: Tabla 2, Müller et al. (2025)
# =============================================================================

CLASES_ESTABILIDAD = {
    'very_poor': {
        'nombre_es': 'Muy Pobre',
        'sensibilidad_cmah': 'Touchy',
        'descripcion': 'Muy fácil de disparar. Estructura de capas débiles muy reactiva.',
        'avalanchas_naturales': True,
        'disparo_humano': True,
        'indicadores': [
            'Colapsos frecuentes (whumpfs) al caminar',
            'Grietas que se propagan (shooting cracks)',
            'Avalanchas naturales recientes observadas',
            'Capas débiles muy reactivas en test de columna'
        ]
    },
    'poor': {
        'nombre_es': 'Pobre',
        'sensibilidad_cmah': 'Reactive',
        'descripcion': 'Fácil de disparar. Capas débiles reactivas a sobrecarga humana.',
        'avalanchas_naturales': False,
        'disparo_humano': True,
        'indicadores': [
            'Colapsos ocasionales',
            'Resultados desfavorables en test de estabilidad',
            'Capas débiles identificables en perfil',
            'Señales de inestabilidad en terreno similar'
        ]
    },
    'fair': {
        'nombre_es': 'Regular',
        'sensibilidad_cmah': 'Stubborn',
        'descripcion': 'Difícil de disparar. Capas débiles que requieren sobrecarga significativa.',
        'avalanchas_naturales': False,
        'disparo_humano': 'Rara vez',
        'indicadores': [
            'Sin colapsos ni grietas observadas',
            'Capas débiles profundas o poco reactivas',
            'Test de estabilidad con resultados moderados',
            'Pocas señales de inestabilidad'
        ]
    },
    'good': {
        'nombre_es': 'Buena',
        'sensibilidad_cmah': 'Unreactive',
        'descripcion': 'Condiciones estables. Sin capas débiles significativas.',
        'avalanchas_naturales': False,
        'disparo_humano': False,
        'indicadores': [
            'Sin capas débiles identificables',
            'Manto nival bien consolidado',
            'Test de estabilidad todos favorables',
            'Sin señales de inestabilidad'
        ]
    }
}


# =============================================================================
# CLASES DE FRECUENCIA DE ESTABILIDAD (Factor 2 EAWS)
# Referencia: Tabla 3, Müller et al. (2025)
# Nota clave de Techel et al. (2020): "La frecuencia de la clase de estabilidad
# más baja es el factor más determinante para la asignación del nivel de peligro."
# =============================================================================

CLASES_FRECUENCIA = {
    'many': {
        'nombre_es': 'Muchos',
        'pct_terreno_min': 30,
        'pct_terreno_max': 100,
        'descripcion': 'Puntos de inestabilidad abundantes en el terreno de avalanchas. '
                       'Fácil encontrar evidencia de inestabilidad.',
        'caracteristicas': [
            'Múltiples aspectos y altitudes afectados',
            'Inestabilidad generalizada',
            'Fácil encontrar evidencia caminando'
        ]
    },
    'some': {
        'nombre_es': 'Algunos',
        'pct_terreno_min': 10,
        'pct_terreno_max': 30,
        'descripcion': 'Puntos de inestabilidad en características típicas del terreno '
                       '(crestas, canales, cambios de pendiente).',
        'caracteristicas': [
            'Ubicaciones con características típicas',
            'Aspectos específicos (generalmente sombra)',
            'Requiere buscar para encontrar evidencia'
        ]
    },
    'a_few': {
        'nombre_es': 'Pocos',
        'pct_terreno_min': 3,
        'pct_terreno_max': 10,
        'descripcion': 'Puntos de inestabilidad raros pero relevantes para la evaluación.',
        'caracteristicas': [
            'Ubicaciones muy específicas',
            'Difícil de encontrar pero existentes',
            'Puede requerir búsqueda extensiva'
        ]
    },
    'nearly_none': {
        'nombre_es': 'Casi Ninguno',
        'pct_terreno_min': 0,
        'pct_terreno_max': 3,
        'descripcion': 'Puntos de inestabilidad irrelevantes para la evaluación regional.',
        'caracteristicas': [
            'Muy raros o inexistentes',
            'No relevantes para decisiones',
            'Condiciones generalmente estables'
        ]
    }
}


# =============================================================================
# CLASES DE TAMAÑO DE AVALANCHA (Factor 3 EAWS)
# Referencia: Tabla 4, Müller et al. (2025)
# Basado en escala canadiense/europea de tamaño destructivo
# =============================================================================

CLASES_TAMANO = {
    1: {
        'nombre_es': 'Pequeña',
        'nombre_en': 'Small',
        'longitud_tipica_m': '<50',
        'volumen_tipico_m3': '<100',
        'potencial_destructivo': 'Relativamente inofensiva para personas. '
                                  'Puede ser peligrosa en trampas de terreno.',
        'impacto_persona': 'Difícilmente entierra persona',
        'impacto_infraestructura': 'Ninguno significativo'
    },
    2: {
        'nombre_es': 'Mediana',
        'nombre_en': 'Medium',
        'longitud_tipica_m': '50-200',
        'volumen_tipico_m3': '100-1000',
        'potencial_destructivo': 'Puede enterrar, herir o matar a una persona.',
        'impacto_persona': 'Puede enterrar completamente',
        'impacto_infraestructura': 'Daños menores a vehículos'
    },
    3: {
        'nombre_es': 'Grande',
        'nombre_en': 'Large',
        'longitud_tipica_m': '200-500',
        'volumen_tipico_m3': '1000-10000',
        'potencial_destructivo': 'Puede destruir autos, dañar camiones, '
                                  'destruir edificios pequeños, romper árboles.',
        'impacto_persona': 'Enterramiento profundo, alta letalidad',
        'impacto_infraestructura': 'Destrucción de vehículos y estructuras menores'
    },
    4: {
        'nombre_es': 'Muy Grande',
        'nombre_en': 'Very Large',
        'longitud_tipica_m': '500-1000',
        'volumen_tipico_m3': '10000-100000',
        'potencial_destructivo': 'Puede destruir camiones pesados, vagones de tren, '
                                  'edificios grandes, áreas de bosque.',
        'impacto_persona': 'Fatal, enterramiento muy profundo',
        'impacto_infraestructura': 'Destrucción de infraestructura mayor'
    },
    5: {
        'nombre_es': 'Extremadamente Grande',
        'nombre_en': 'Extremely Large',
        'longitud_tipica_m': '>1000',
        'volumen_tipico_m3': '>100000',
        'potencial_destructivo': 'Devasta el paisaje. Potencial catastrófico. '
                                  'Puede alcanzar el fondo del valle.',
        'impacto_persona': 'Catastrófico',
        'impacto_infraestructura': 'Destrucción total del área de impacto'
    }
}


# =============================================================================
# MATRIZ EAWS COMPLETA (Lookup Table)
# Estructura: EAWS_MATRIX[estabilidad][frecuencia][tamano] = (D1, D2)
# D1 = nivel primario recomendado (consenso mayoritario de expertos)
# D2 = nivel secundario (≥30% de expertos eligió diferente), None si consenso claro
#
# Referencia: Aceptada por EAWS en 2022, validada operacionalmente por
# 26 servicios europeos (Techel et al., 2025)
# =============================================================================

EAWS_MATRIX: Dict[str, Dict[str, Dict[int, Tuple[int, Optional[int]]]]] = {
    'very_poor': {
        'many': {
            5: (5, None),
            4: (5, 4),
            3: (4, None),
            2: (3, 4),
            1: (2, 3)
        },
        'some': {
            5: (5, 4),
            4: (4, None),
            3: (3, 4),
            2: (3, 2),
            1: (2, None)
        },
        'a_few': {
            5: (4, None),
            4: (3, 4),
            3: (3, 2),
            2: (2, None),
            1: (1, 2)
        },
        # 'nearly_none' con 'very_poor' -> referir al panel 'poor'
        'nearly_none': {
            5: (3, 4),
            4: (3, None),
            3: (2, 3),
            2: (2, 1),
            1: (1, None)
        }
    },
    'poor': {
        'many': {
            5: (5, 4),
            4: (4, None),
            3: (4, 3),
            2: (3, None),
            1: (2, None)
        },
        'some': {
            5: (4, None),
            4: (4, 3),
            3: (3, None),
            2: (2, 3),
            1: (2, 1)
        },
        'a_few': {
            5: (3, 4),
            4: (3, None),
            3: (2, 3),
            2: (2, 1),
            1: (1, None)
        },
        # 'nearly_none' con 'poor' -> referir al panel 'fair'
        'nearly_none': {
            5: (3, None),
            4: (2, 3),
            3: (2, 1),
            2: (1, 2),
            1: (1, None)
        }
    },
    'fair': {
        'many': {
            5: (4, 3),
            4: (3, 4),
            3: (3, 2),
            2: (2, None),
            1: (1, 2)
        },
        'some': {
            5: (3, 4),
            4: (3, None),
            3: (2, 3),
            2: (2, None),
            1: (1, 2)
        },
        'a_few': {
            5: (3, None),
            4: (2, 3),
            3: (2, 1),
            2: (1, 2),
            1: (1, None)
        },
        # 'nearly_none' con 'fair' -> D = 1 por defecto
        'nearly_none': {
            5: (2, None),
            4: (1, 2),
            3: (1, None),
            2: (1, None),
            1: (1, None)
        }
    },
    # Cuando estabilidad = 'good' en toda la región -> D = 1 (Low) por defecto
    'good': {
        'many': {5: (1, None), 4: (1, None), 3: (1, None), 2: (1, None), 1: (1, None)},
        'some': {5: (1, None), 4: (1, None), 3: (1, None), 2: (1, None), 1: (1, None)},
        'a_few': {5: (1, None), 4: (1, None), 3: (1, None), 2: (1, None), 1: (1, None)},
        'nearly_none': {5: (1, None), 4: (1, None), 3: (1, None), 2: (1, None), 1: (1, None)}
    }
}


# =============================================================================
# FUNCIONES DE ESTIMACIÓN TOPOGRÁFICA (Componentes Estáticos)
# Estas funciones estiman los factores EAWS usando solo datos topográficos.
# En fases futuras, se amplificarán con datos meteorológicos.
# =============================================================================

def estimar_frecuencia_base(pct_zona_inicio: float) -> str:
    """
    Estima la frecuencia BASE usando solo el componente topográfico.

    La frecuencia base representa la proporción del terreno que tiene
    características topográficas propensas a avalanchas (zona de inicio).

    En fases futuras, esta frecuencia se amplificará con factores
    meteorológicos (nieve nueva, viento de transporte) para obtener
    la frecuencia dinámica.

    Args:
        pct_zona_inicio: Porcentaje del buffer que es zona de inicio (0-100)

    Returns:
        str: Clase de frecuencia EAWS ('many', 'some', 'a_few', 'nearly_none')

    Referencia: Tabla 3, Müller et al. (2025)
    """
    if pct_zona_inicio >= 30:
        return 'many'
    elif pct_zona_inicio >= 10:
        return 'some'
    elif pct_zona_inicio >= 3:
        return 'a_few'
    else:
        return 'nearly_none'


def estimar_tamano_potencial(
    desnivel_inicio_deposito: float,
    ha_zona_inicio: float,
    pendiente_max: float
) -> int:
    """
    Estima el tamaño POTENCIAL de avalancha basado en topografía.

    El tamaño potencial representa la avalancha más grande que el terreno
    PERMITE generar, independiente de las condiciones de nieve actuales.

    En fases futuras, este tamaño se ajustará según profundidad de nieve
    acumulada y condiciones meteorológicas.

    Args:
        desnivel_inicio_deposito: Desnivel vertical entre zona inicio y depósito (m)
        ha_zona_inicio: Hectáreas de zona de inicio (masa potencial)
        pendiente_max: Pendiente máxima en grados (energía potencial)

    Returns:
        int: Tamaño potencial EAWS (1-5)

    Referencia: Tabla 4, Müller et al. (2025)
    Proxy basado en:
    - Desnivel (factor dominante según literatura)
    - Área de zona de inicio (masa acumulable)
    - Pendiente máxima (energía)
    """
    score = 0.0

    # Desnivel del recorrido (factor dominante en tamaño)
    if desnivel_inicio_deposito > 1500:
        score += 2.0
    elif desnivel_inicio_deposito > 800:
        score += 1.5
    elif desnivel_inicio_deposito > 400:
        score += 1.0
    elif desnivel_inicio_deposito > 200:
        score += 0.5

    # Área de zona de inicio (masa potencial acumulable)
    if ha_zona_inicio > 100:
        score += 1.5
    elif ha_zona_inicio > 50:
        score += 1.0
    elif ha_zona_inicio > 20:
        score += 0.5

    # Pendiente máxima (energía potencial)
    if pendiente_max > 55:
        score += 0.5
    elif pendiente_max > 45:
        score += 0.3

    # Clasificación final
    if score >= 3.5:
        return 5
    elif score >= 2.5:
        return 4
    elif score >= 1.5:
        return 3
    elif score >= 0.8:
        return 2
    else:
        return 1


def consultar_matriz_eaws(
    estabilidad: str,
    frecuencia: str,
    tamano: int
) -> Tuple[int, Optional[int]]:
    """
    Consulta la matriz EAWS para obtener el nivel de peligro recomendado.

    Args:
        estabilidad: Clase de estabilidad ('very_poor', 'poor', 'fair', 'good')
        frecuencia: Clase de frecuencia ('many', 'some', 'a_few', 'nearly_none')
        tamano: Tamaño de avalancha (1-5)

    Returns:
        Tuple[int, Optional[int]]: (D1, D2) donde:
            - D1 = nivel primario recomendado
            - D2 = nivel secundario (si ≥30% de expertos eligió diferente)

    Raises:
        KeyError: Si algún parámetro no es válido
    """
    if estabilidad not in EAWS_MATRIX:
        raise KeyError(f"Estabilidad inválida: {estabilidad}")
    if frecuencia not in EAWS_MATRIX[estabilidad]:
        raise KeyError(f"Frecuencia inválida: {frecuencia}")
    if tamano not in EAWS_MATRIX[estabilidad][frecuencia]:
        raise KeyError(f"Tamaño inválido: {tamano}")

    return EAWS_MATRIX[estabilidad][frecuencia][tamano]


# =============================================================================
# CONSTANTES TOPOGRÁFICAS PARA CLASIFICACIÓN DE ZONAS
# =============================================================================

# Rangos de pendiente para zona de inicio (grados)
PENDIENTE_INICIO_MIN = 30  # Mínimo para que se suelte una avalancha
PENDIENTE_INICIO_MAX = 60  # Máximo práctico (más empinado = poca acumulación)

# Sub-clasificación de zona de inicio por severidad
PENDIENTE_INICIO_MODERADO = (30, 45)   # Pendiente moderada
PENDIENTE_INICIO_SEVERO = (45, 60)     # Pendiente severa
PENDIENTE_INICIO_EXTREMO = 60          # Pendiente extrema (>60°)

# Rangos de pendiente para zona de tránsito
PENDIENTE_TRANSITO_MIN = 15
PENDIENTE_TRANSITO_MAX = 30

# Pendiente máxima para zona de depósito
PENDIENTE_DEPOSITO_MAX = 15

# Umbral de curvatura para detección de convexidad/concavidad
CURVATURA_CONVEXA_UMBRAL = 2   # Positivo = convexo = inicio
CURVATURA_CONCAVA_UMBRAL = -10  # Negativo = cóncavo = canal/depósito

# Radio de análisis por defecto (metros)
RADIO_ANALISIS_DEFAULT = 5000  # 5 km

# Valor sentinel para datos nulos de GEE
VALOR_NULO_GEE = -9999


# =============================================================================
# CATEGORÍAS DE ASPECTO (Orientación de ladera)
# =============================================================================

CATEGORIAS_ASPECTO = {
    'N':  (337.5, 22.5),   # Norte: 337.5° - 22.5°
    'NE': (22.5, 67.5),    # Noreste
    'E':  (67.5, 112.5),   # Este
    'SE': (112.5, 157.5),  # Sureste
    'S':  (157.5, 202.5),  # Sur
    'SW': (202.5, 247.5),  # Suroeste
    'W':  (247.5, 292.5),  # Oeste
    'NW': (292.5, 337.5)   # Noroeste
}


def categorizar_aspecto(grados: float) -> str:
    """
    Categoriza un aspecto en grados a su dirección cardinal.

    Args:
        grados: Aspecto en grados (0-360, 0=Norte, 90=Este)

    Returns:
        str: Categoría de dirección ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
    """
    # Normalizar a 0-360
    grados = grados % 360

    # Caso especial para Norte (cruza 0°)
    if grados >= 337.5 or grados < 22.5:
        return 'N'

    for categoria, (min_ang, max_ang) in CATEGORIAS_ASPECTO.items():
        if categoria == 'N':
            continue  # Ya manejado arriba
        if min_ang <= grados < max_ang:
            return categoria

    return 'N'  # Fallback


def es_aspecto_sombra(aspecto_grados: float, hemisferio: str) -> bool:
    """
    Determina si el aspecto corresponde a ladera de sombra según hemisferio.

    Las laderas de sombra reciben menos radiación solar directa, lo que
    resulta en:
    - Nieve más seca y menos consolidada
    - Mayor persistencia de capas débiles
    - Mayor probabilidad de problemas de "persistent weak layer"

    Args:
        aspecto_grados: Aspecto predominante (0-360°, 0=Norte)
        hemisferio: 'norte' o 'sur'

    Returns:
        bool: True si es aspecto de sombra (más propenso a inestabilidad)

    Nota:
        Hemisferio Sur: Norte/NE/NW = sombra (sol viene del norte)
        Hemisferio Norte: Sur/SE/SW = sombra (sol viene del sur)
    """
    hemisferio = hemisferio.lower()

    if hemisferio == 'sur':
        # Hemisferio sur: aspectos norte son sombra
        # Norte abarca ~315° a ~45° (o 293° a 67° con margen)
        return aspecto_grados <= 67 or aspecto_grados >= 293
    else:
        # Hemisferio norte: aspectos sur son sombra
        # Sur abarca ~135° a ~225° (o 113° a 247° con margen)
        return 113 <= aspecto_grados <= 247


def detectar_hemisferio(latitud: float) -> str:
    """
    Detecta el hemisferio basado en la latitud.

    Args:
        latitud: Latitud en grados decimales (negativo = sur)

    Returns:
        str: 'sur' o 'norte'
    """
    return 'sur' if latitud < 0 else 'norte'

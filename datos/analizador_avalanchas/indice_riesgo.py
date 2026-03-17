"""
Cálculo del Índice de Riesgo Topográfico para Avalanchas

Este módulo implementa un índice estático (0-100) de susceptibilidad
topográfica permanente para avalanchas, basado en parámetros de terreno.

El índice NO considera condiciones meteorológicas dinámicas, sino
únicamente factores de terreno que son constantes en el tiempo.

Componentes del índice:
1. Área de zona de inicio (más área = más fuentes de liberación)
2. Porcentaje de zona de inicio respecto al área total
3. Pendiente máxima (pendientes extremas = más inestabilidad)
4. Aspecto predominante (sombra = nieve seca más inestable)
5. Desnivel inicio-depósito (más desnivel = avalanchas más grandes)
6. Conectividad de zonas (inicio conectado a tránsito y depósito)

Clasificación resultante:
- BAJO: 0-25
- MEDIO: 26-50
- ALTO: 51-75
- EXTREMO: 76-100

Referencias:
- Statham, G., et al. (2018). A conceptual model of avalanche hazard.
- Müller, K., et al. (2025). The EAWS matrix, Part A.
"""

import logging
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from eaws_constantes import (
    es_aspecto_sombra,
    detectar_hemisferio,
    estimar_frecuencia_base,
    estimar_tamano_potencial,
    consultar_matriz_eaws,
    PENDIENTE_INICIO_MIN,
    PENDIENTE_INICIO_MAX
)


# Configuración de logging
logger = logging.getLogger(__name__)


class ClasificacionRiesgo(Enum):
    """Clasificación cualitativa del riesgo topográfico."""
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    EXTREMO = "extremo"


@dataclass
class IndiceRiesgoTopografico:
    """
    Resultado del cálculo del índice de riesgo topográfico.

    Attributes:
        indice_total: Índice compuesto 0-100
        clasificacion: Clasificación cualitativa (BAJO, MEDIO, ALTO, EXTREMO)
        componente_area: Puntos por área de zona de inicio (0-25)
        componente_pendiente: Puntos por pendiente máxima (0-25)
        componente_aspecto: Puntos por aspecto de sombra (0-25)
        componente_desnivel: Puntos por desnivel vertical (0-25)
        frecuencia_estimada: Estimación de frecuencia EAWS
        tamano_estimado: Estimación de tamaño EAWS
        peligro_eaws_estimado: Nivel de peligro EAWS estimado (1-5)
    """
    indice_total: float
    clasificacion: ClasificacionRiesgo
    componente_area: float
    componente_pendiente: float
    componente_aspecto: float
    componente_desnivel: float
    frecuencia_estimada: str
    tamano_estimado: int
    peligro_eaws_estimado: int


# Umbrales para clasificación
UMBRAL_BAJO = 25
UMBRAL_MEDIO = 50
UMBRAL_ALTO = 75

# Pesos de componentes (suman 100)
PESO_AREA = 25
PESO_PENDIENTE = 25
PESO_ASPECTO = 25
PESO_DESNIVEL = 25

# Umbrales para normalización de componentes
AREA_INICIO_MIN_HA = 0.1      # Mínimo para considerar riesgo
AREA_INICIO_MAX_HA = 50.0     # Área que da máximo puntaje
PENDIENTE_MAX_REFERENCIA = 60  # Pendiente para máximo puntaje
DESNIVEL_MAX_REFERENCIA = 1000 # Desnivel en metros para máximo puntaje
PCT_INICIO_ALTO = 30          # % de zona inicio considerado alto


def clasificar_riesgo(indice: float) -> ClasificacionRiesgo:
    """
    Clasifica el índice numérico en categoría cualitativa.

    Args:
        indice: Índice de riesgo 0-100

    Returns:
        ClasificacionRiesgo: Categoría (BAJO, MEDIO, ALTO, EXTREMO)
    """
    if indice <= UMBRAL_BAJO:
        return ClasificacionRiesgo.BAJO
    elif indice <= UMBRAL_MEDIO:
        return ClasificacionRiesgo.MEDIO
    elif indice <= UMBRAL_ALTO:
        return ClasificacionRiesgo.ALTO
    else:
        return ClasificacionRiesgo.EXTREMO


def normalizar_valor(
    valor: float,
    minimo: float,
    maximo: float,
    invertir: bool = False
) -> float:
    """
    Normaliza un valor al rango 0-1.

    Args:
        valor: Valor a normalizar
        minimo: Valor mínimo del rango
        maximo: Valor máximo del rango
        invertir: Si True, invierte la escala (mayor valor = menor resultado)

    Returns:
        float: Valor normalizado entre 0 y 1
    """
    if maximo <= minimo:
        return 0.0

    # Limitar al rango
    valor_limitado = max(minimo, min(valor, maximo))

    # Normalizar
    normalizado = (valor_limitado - minimo) / (maximo - minimo)

    if invertir:
        normalizado = 1.0 - normalizado

    return normalizado


def calcular_componente_area(
    ha_inicio: float,
    pct_inicio: float
) -> float:
    """
    Calcula el componente de área del índice de riesgo.

    Considera tanto el área absoluta como el porcentaje respecto al total.
    Más área de zona de inicio = más potencial de liberación de avalanchas.

    Args:
        ha_inicio: Hectáreas de zona de inicio
        pct_inicio: Porcentaje que representa la zona de inicio

    Returns:
        float: Puntaje del componente (0-25)
    """
    if ha_inicio < AREA_INICIO_MIN_HA:
        # Área despreciable, no hay riesgo significativo
        return 0.0

    # Normalizar área absoluta (0-0.6 del peso)
    factor_area = normalizar_valor(ha_inicio, AREA_INICIO_MIN_HA, AREA_INICIO_MAX_HA)

    # Normalizar porcentaje (0-0.4 del peso)
    factor_pct = normalizar_valor(pct_inicio, 0, PCT_INICIO_ALTO)

    # Combinar (60% área absoluta, 40% porcentaje)
    puntaje = (factor_area * 0.6 + factor_pct * 0.4) * PESO_AREA

    return round(puntaje, 2)


def calcular_componente_pendiente(
    pendiente_max: float,
    pendiente_media: float
) -> float:
    """
    Calcula el componente de pendiente del índice de riesgo.

    Pendientes más empinadas tienen mayor potencial de inestabilidad.
    Se considera tanto la pendiente máxima como la media.

    Args:
        pendiente_max: Pendiente máxima en grados
        pendiente_media: Pendiente media en grados

    Returns:
        float: Puntaje del componente (0-25)
    """
    if pendiente_max < PENDIENTE_INICIO_MIN:
        # Pendiente insuficiente para avalanchas
        return 0.0

    # Normalizar pendiente máxima (70% del peso)
    # El rango crítico es 30°-60°
    factor_max = normalizar_valor(
        pendiente_max,
        PENDIENTE_INICIO_MIN,
        PENDIENTE_MAX_REFERENCIA
    )

    # Normalizar pendiente media (30% del peso)
    factor_media = normalizar_valor(
        pendiente_media,
        PENDIENTE_INICIO_MIN,
        50  # Media de 50° es muy alta
    )

    # Combinar
    puntaje = (factor_max * 0.7 + factor_media * 0.3) * PESO_PENDIENTE

    return round(puntaje, 2)


def calcular_componente_aspecto(
    aspecto_predominante: float,
    latitud: float,
    pct_sombra: float = None
) -> float:
    """
    Calcula el componente de aspecto del índice de riesgo.

    Los aspectos de sombra (norte en hemisferio sur, sur en hemisferio norte)
    mantienen la nieve más seca y potencialmente más inestable.

    Args:
        aspecto_predominante: Aspecto predominante en grados (0-360)
        latitud: Latitud para determinar hemisferio
        pct_sombra: Porcentaje opcional de área en sombra (si disponible)

    Returns:
        float: Puntaje del componente (0-25)
    """
    hemisferio = detectar_hemisferio(latitud)

    # Verificar si el aspecto predominante es de sombra
    es_sombra = es_aspecto_sombra(aspecto_predominante, hemisferio)

    if es_sombra:
        # Calcular qué tan "profundo" en la sombra está
        # (más norte en HS o más sur en HN = más sombra)
        if hemisferio == 'sur':
            # Norte puro (0° o 360°) es máxima sombra
            # Calculamos distancia angular al norte
            if aspecto_predominante > 180:
                angulo_desde_norte = 360 - aspecto_predominante
            else:
                angulo_desde_norte = aspecto_predominante
            # Máximo sombra a 0°, decrece hasta 67°/293°
            factor_sombra = 1.0 - (angulo_desde_norte / 67.0)
        else:
            # Hemisferio norte: sur puro (180°) es máxima sombra
            angulo_desde_sur = abs(aspecto_predominante - 180)
            # Máximo sombra a 180°, decrece hasta 113°/247°
            factor_sombra = 1.0 - (angulo_desde_sur / 67.0)

        factor_sombra = max(0.5, factor_sombra)  # Mínimo 0.5 si es sombra
    else:
        # Aspecto soleado, menor riesgo pero no cero
        factor_sombra = 0.2

    # Si tenemos porcentaje de área en sombra, lo incorporamos
    if pct_sombra is not None:
        factor_area_sombra = pct_sombra / 100.0
        # Combinar aspecto predominante con área en sombra
        factor_final = (factor_sombra * 0.6 + factor_area_sombra * 0.4)
    else:
        factor_final = factor_sombra

    puntaje = factor_final * PESO_ASPECTO

    return round(puntaje, 2)


def calcular_componente_desnivel(
    desnivel_inicio_deposito: float,
    elevacion_maxima: float = None
) -> float:
    """
    Calcula el componente de desnivel del índice de riesgo.

    Mayor desnivel vertical = avalanchas potencialmente más grandes
    (más distancia de aceleración y acumulación de masa).

    Args:
        desnivel_inicio_deposito: Desnivel en metros entre zona inicio y depósito
        elevacion_maxima: Elevación máxima (opcional, para ajuste)

    Returns:
        float: Puntaje del componente (0-25)
    """
    if desnivel_inicio_deposito <= 0:
        return 0.0

    # Normalizar desnivel
    factor_desnivel = normalizar_valor(
        desnivel_inicio_deposito,
        0,
        DESNIVEL_MAX_REFERENCIA
    )

    # Ajuste por elevación máxima (áreas más altas tienen más nieve)
    if elevacion_maxima is not None and elevacion_maxima > 3000:
        # Bonus del 10% para zonas sobre 3000m
        factor_desnivel = min(1.0, factor_desnivel * 1.1)

    puntaje = factor_desnivel * PESO_DESNIVEL

    return round(puntaje, 2)


def calcular_indice_riesgo_topografico(
    ha_inicio: float,
    ha_deposito: float,
    pct_inicio: float,
    pendiente_max: float,
    pendiente_media: float,
    aspecto_predominante: float,
    desnivel_inicio_deposito: float,
    latitud: float,
    elevacion_maxima: float = None,
    pct_sombra: float = None
) -> IndiceRiesgoTopografico:
    """
    Calcula el índice de riesgo topográfico completo.

    Este es el método principal que combina todos los componentes
    para generar un índice de susceptibilidad topográfica 0-100.

    Args:
        ha_inicio: Hectáreas de zona de inicio
        ha_deposito: Hectáreas de zona de depósito
        pct_inicio: Porcentaje de zona de inicio respecto al total
        pendiente_max: Pendiente máxima en grados
        pendiente_media: Pendiente media en grados
        aspecto_predominante: Aspecto predominante en grados
        desnivel_inicio_deposito: Desnivel vertical en metros
        latitud: Latitud de la ubicación
        elevacion_maxima: Elevación máxima opcional
        pct_sombra: Porcentaje de área en sombra opcional

    Returns:
        IndiceRiesgoTopografico: Resultado completo con índice y componentes
    """
    logger.info(f"Calculando índice de riesgo topográfico")

    # Calcular componentes individuales
    comp_area = calcular_componente_area(ha_inicio, pct_inicio)
    comp_pendiente = calcular_componente_pendiente(pendiente_max, pendiente_media)
    comp_aspecto = calcular_componente_aspecto(aspecto_predominante, latitud, pct_sombra)
    comp_desnivel = calcular_componente_desnivel(desnivel_inicio_deposito, elevacion_maxima)

    # Sumar componentes
    indice_total = comp_area + comp_pendiente + comp_aspecto + comp_desnivel
    indice_total = round(min(100, max(0, indice_total)), 2)

    # Clasificar
    clasificacion = clasificar_riesgo(indice_total)

    # Estimar parámetros EAWS usando funciones de eaws_constantes
    frecuencia = estimar_frecuencia_base(pct_inicio)
    tamano = estimar_tamano_potencial(desnivel_inicio_deposito)

    # Para el nivel de peligro, asumimos estabilidad "fair" como base
    # (ya que no tenemos datos de condiciones de nieve)
    peligro = consultar_matriz_eaws('fair', frecuencia, tamano)

    logger.info(
        f"Índice calculado: {indice_total} ({clasificacion.value}) - "
        f"Área:{comp_area} Pend:{comp_pendiente} Asp:{comp_aspecto} Des:{comp_desnivel}"
    )

    return IndiceRiesgoTopografico(
        indice_total=indice_total,
        clasificacion=clasificacion,
        componente_area=comp_area,
        componente_pendiente=comp_pendiente,
        componente_aspecto=comp_aspecto,
        componente_desnivel=comp_desnivel,
        frecuencia_estimada=frecuencia,
        tamano_estimado=tamano,
        peligro_eaws_estimado=peligro
    )


def calcular_indice_desde_cubicacion(
    cubicacion: Dict[str, Any],
    latitud: float
) -> IndiceRiesgoTopografico:
    """
    Calcula el índice de riesgo a partir del resultado de cubicación.

    Método de conveniencia que extrae los parámetros necesarios
    del diccionario de cubicación y llama a calcular_indice_riesgo_topografico.

    Args:
        cubicacion: Diccionario resultado de cubicar_zonas_completo()
        latitud: Latitud de la ubicación

    Returns:
        IndiceRiesgoTopografico: Resultado del cálculo
    """
    # Extraer parámetros del diccionario de cubicación
    ha_inicio = cubicacion.get('zona_inicio_ha', 0)
    ha_deposito = cubicacion.get('zona_deposito_ha', 0)
    pct_inicio = cubicacion.get('zona_inicio_pct', 0)
    pendiente_max = cubicacion.get('pendiente_max_inicio', 0)
    pendiente_media = cubicacion.get('pendiente_media_inicio', 0)
    aspecto = cubicacion.get('aspecto_predominante_inicio', 0)

    # Calcular desnivel
    elev_max_inicio = cubicacion.get('elevacion_max_inicio', 0)
    elev_min_deposito = cubicacion.get('elevacion_min_deposito', 0)
    desnivel = elev_max_inicio - elev_min_deposito if elev_max_inicio > 0 and elev_min_deposito > 0 else 0

    # Elevación máxima para ajustes
    elevacion_maxima = cubicacion.get('elevacion_max_inicio', None)

    return calcular_indice_riesgo_topografico(
        ha_inicio=ha_inicio,
        ha_deposito=ha_deposito,
        pct_inicio=pct_inicio,
        pendiente_max=pendiente_max,
        pendiente_media=pendiente_media,
        aspecto_predominante=aspecto,
        desnivel_inicio_deposito=desnivel,
        latitud=latitud,
        elevacion_maxima=elevacion_maxima
    )


def generar_descripcion_riesgo(resultado: IndiceRiesgoTopografico) -> str:
    """
    Genera una descripción textual del riesgo topográfico.

    Args:
        resultado: Resultado del cálculo de índice

    Returns:
        str: Descripción textual en español
    """
    descripciones_clasificacion = {
        ClasificacionRiesgo.BAJO: (
            "Terreno con baja susceptibilidad a avalanchas. "
            "Pendientes moderadas y/o poca área de zonas de liberación."
        ),
        ClasificacionRiesgo.MEDIO: (
            "Terreno con susceptibilidad moderada a avalanchas. "
            "Existen zonas de inicio que requieren atención durante "
            "condiciones de inestabilidad del manto nival."
        ),
        ClasificacionRiesgo.ALTO: (
            "Terreno con alta susceptibilidad a avalanchas. "
            "Zonas de inicio significativas con pendientes críticas. "
            "Evitar durante condiciones de peligro elevado."
        ),
        ClasificacionRiesgo.EXTREMO: (
            "Terreno extremadamente susceptible a avalanchas. "
            "Grandes áreas de inicio con pendientes severas y/o aspectos de sombra. "
            "Solo para expertos con condiciones favorables confirmadas."
        )
    }

    descripcion_base = descripciones_clasificacion[resultado.clasificacion]

    # Agregar detalles específicos
    detalles = []

    if resultado.componente_area > PESO_AREA * 0.7:
        detalles.append("zona de inicio extensa")

    if resultado.componente_pendiente > PESO_PENDIENTE * 0.7:
        detalles.append("pendientes muy empinadas")

    if resultado.componente_aspecto > PESO_ASPECTO * 0.7:
        detalles.append("orientación predominante a la sombra")

    if resultado.componente_desnivel > PESO_DESNIVEL * 0.7:
        detalles.append("gran desnivel vertical")

    if detalles:
        descripcion_base += f" Factores destacados: {', '.join(detalles)}."

    return descripcion_base


def convertir_resultado_a_dict(resultado: IndiceRiesgoTopografico) -> Dict[str, Any]:
    """
    Convierte el resultado del índice a diccionario para BigQuery.

    Args:
        resultado: Resultado del cálculo

    Returns:
        Dict: Diccionario con campos para BigQuery
    """
    return {
        'indice_riesgo_topografico': resultado.indice_total,
        'clasificacion_riesgo': resultado.clasificacion.value,
        'componente_area': resultado.componente_area,
        'componente_pendiente': resultado.componente_pendiente,
        'componente_aspecto': resultado.componente_aspecto,
        'componente_desnivel': resultado.componente_desnivel,
        'frecuencia_estimada_eaws': resultado.frecuencia_estimada,
        'tamano_estimado_eaws': resultado.tamano_estimado,
        'peligro_eaws_base': resultado.peligro_eaws_estimado,
        'descripcion_riesgo': generar_descripcion_riesgo(resultado)
    }

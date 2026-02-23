"""
Cubicación de Zonas de Avalancha - Cálculo de Áreas y Estadísticas

Este módulo calcula métricas cuantitativas de las zonas funcionales de avalancha:
- Áreas en hectáreas por zona (inicio, tránsito, depósito)
- Porcentajes respecto al área de análisis
- Estadísticas de pendiente (media, máxima, percentiles)
- Desniveles y elevaciones
- Aspecto predominante y clasificación

Estas métricas sirven como proxies para los factores EAWS:
- % zona inicio → Factor 2 EAWS (Frecuencia)
- Desnivel inicio-depósito → Factor 3 EAWS (Tamaño)
- Aspecto sombra → Factor 1 EAWS (Estabilidad)

Referencias:
- Müller, K., Techel, F., & Mitterer, C. (2025). The EAWS matrix, Part A.
- Techel, F., et al. (2020). On the importance of snowpack stability.
"""

import logging
import math
from typing import Dict, Any, Optional

import ee

from eaws_constantes import (
    VALOR_NULO_GEE,
    categorizar_aspecto,
    es_aspecto_sombra,
    detectar_hemisferio
)


# Configuración de logging
logger = logging.getLogger(__name__)


def metros_cuadrados_a_hectareas(m2: float) -> float:
    """
    Convierte metros cuadrados a hectáreas.

    Args:
        m2: Área en metros cuadrados

    Returns:
        float: Área en hectáreas
    """
    return m2 / 10000


def calcular_area_zona(
    mascara_zona: ee.Image,
    area_buffer: ee.Geometry,
    escala: int = 30
) -> float:
    """
    Calcula el área de una zona en hectáreas.

    Args:
        mascara_zona: Máscara binaria de la zona (1 = pertenece)
        area_buffer: Geometría del área de análisis
        escala: Resolución en metros para el cálculo

    Returns:
        float: Área en hectáreas, o 0.0 si falla
    """
    try:
        # Multiplicar máscara por área de píxel
        area_pixeles = mascara_zona.multiply(ee.Image.pixelArea())

        # Reducir sumando todas las áreas
        resultado = area_pixeles.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=area_buffer,
            scale=escala,
            maxPixels=1e10
        )

        # Obtener valor y convertir a hectáreas
        area_m2 = resultado.getInfo()
        if area_m2:
            # Obtener el primer (y único) valor del diccionario
            nombre_banda = list(area_m2.keys())[0]
            valor = area_m2[nombre_banda]
            if valor is not None:
                return metros_cuadrados_a_hectareas(valor)

        return 0.0

    except Exception as e:
        logger.warning(f"Error calculando área de zona: {e}")
        return 0.0


def calcular_area_buffer(area_buffer: ee.Geometry) -> float:
    """
    Calcula el área total del buffer en hectáreas.

    Args:
        area_buffer: Geometría del área de análisis

    Returns:
        float: Área en hectáreas
    """
    try:
        area_m2 = area_buffer.area().getInfo()
        return metros_cuadrados_a_hectareas(area_m2)
    except Exception as e:
        logger.warning(f"Error calculando área de buffer: {e}")
        # Calcular aproximación basada en radio de 5km
        return math.pi * (5000 ** 2) / 10000  # ~7854 ha


def calcular_estadisticas_pendiente(
    pendiente: ee.Image,
    mascara_zona: ee.Image,
    area_buffer: ee.Geometry,
    escala: int = 30
) -> Dict[str, float]:
    """
    Calcula estadísticas de pendiente dentro de una zona.

    Args:
        pendiente: Imagen de pendiente en grados
        mascara_zona: Máscara binaria de la zona
        area_buffer: Geometría del área de análisis
        escala: Resolución en metros

    Returns:
        Dict con:
            - media: Pendiente media
            - max: Pendiente máxima
            - p90: Percentil 90
    """
    try:
        # Aplicar máscara a la pendiente
        pendiente_en_zona = pendiente.updateMask(mascara_zona)

        # Reducir con múltiples estadísticas
        resultado = pendiente_en_zona.reduceRegion(
            reducer=ee.Reducer.mean()
                .combine(ee.Reducer.max(), sharedInputs=True)
                .combine(ee.Reducer.percentile([90]), sharedInputs=True),
            geometry=area_buffer,
            scale=escala,
            maxPixels=1e10
        )

        stats = resultado.getInfo()

        return {
            'media': stats.get('slope_mean', VALOR_NULO_GEE),
            'max': stats.get('slope_max', VALOR_NULO_GEE),
            'p90': stats.get('slope_p90', VALOR_NULO_GEE)
        }

    except Exception as e:
        logger.warning(f"Error calculando estadísticas de pendiente: {e}")
        return {
            'media': VALOR_NULO_GEE,
            'max': VALOR_NULO_GEE,
            'p90': VALOR_NULO_GEE
        }


def calcular_pendiente_maxima_buffer(
    pendiente: ee.Image,
    area_buffer: ee.Geometry,
    escala: int = 30
) -> float:
    """
    Calcula la pendiente máxima en todo el buffer.

    Args:
        pendiente: Imagen de pendiente
        area_buffer: Geometría del área
        escala: Resolución

    Returns:
        float: Pendiente máxima en grados
    """
    try:
        resultado = pendiente.reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=area_buffer,
            scale=escala,
            maxPixels=1e10
        )
        stats = resultado.getInfo()
        return stats.get('slope', VALOR_NULO_GEE)
    except Exception as e:
        logger.warning(f"Error calculando pendiente máxima: {e}")
        return VALOR_NULO_GEE


def calcular_elevacion_media(
    dem: ee.Image,
    mascara_zona: ee.Image,
    area_buffer: ee.Geometry,
    escala: int = 30
) -> float:
    """
    Calcula la elevación media dentro de una zona.

    Args:
        dem: Imagen DEM de elevación
        mascara_zona: Máscara binaria de la zona
        area_buffer: Geometría del área
        escala: Resolución

    Returns:
        float: Elevación media en metros
    """
    try:
        dem_en_zona = dem.updateMask(mascara_zona)

        resultado = dem_en_zona.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=area_buffer,
            scale=escala,
            maxPixels=1e10
        )

        stats = resultado.getInfo()
        return stats.get('elevation', VALOR_NULO_GEE)

    except Exception as e:
        logger.warning(f"Error calculando elevación media: {e}")
        return VALOR_NULO_GEE


def calcular_desnivel_zonas(
    dem: ee.Image,
    zona_inicio: ee.Image,
    zona_deposito: ee.Image,
    area_buffer: ee.Geometry,
    escala: int = 30
) -> Dict[str, float]:
    """
    Calcula el desnivel entre zona de inicio y zona de depósito.

    El desnivel es un proxy clave para el Factor 3 EAWS (Tamaño de Avalancha),
    ya que el largo del recorrido es el factor dominante en el tamaño.

    Args:
        dem: Imagen DEM
        zona_inicio: Máscara de zona de inicio
        zona_deposito: Máscara de zona de depósito
        area_buffer: Geometría del área
        escala: Resolución

    Returns:
        Dict con:
            - elevacion_media_inicio: Elevación media de zona inicio
            - elevacion_media_deposito: Elevación media de zona depósito
            - desnivel: Diferencia de elevación (inicio - depósito)
    """
    elev_inicio = calcular_elevacion_media(dem, zona_inicio, area_buffer, escala)
    elev_deposito = calcular_elevacion_media(dem, zona_deposito, area_buffer, escala)

    # Calcular desnivel (manejar valores nulos)
    if elev_inicio != VALOR_NULO_GEE and elev_deposito != VALOR_NULO_GEE:
        desnivel = elev_inicio - elev_deposito
    else:
        desnivel = VALOR_NULO_GEE

    return {
        'elevacion_media_inicio': elev_inicio,
        'elevacion_media_deposito': elev_deposito,
        'desnivel': desnivel
    }


def calcular_aspecto_predominante(
    aspecto: ee.Image,
    mascara_zona: ee.Image,
    area_buffer: ee.Geometry,
    latitud: float,
    escala: int = 30
) -> Dict[str, Any]:
    """
    Calcula el aspecto predominante en una zona.

    El aspecto es relevante para el Factor 1 EAWS (Estabilidad):
    - Aspectos de sombra = nieve seca más tiempo = mayor persistencia de capas débiles

    Args:
        aspecto: Imagen de aspecto (0-360°)
        mascara_zona: Máscara binaria de la zona
        area_buffer: Geometría del área
        latitud: Latitud para determinar hemisferio
        escala: Resolución

    Returns:
        Dict con:
            - aspecto_grados: Aspecto predominante en grados
            - categoria: Categoría de dirección (N, NE, E, etc.)
            - es_sombra: True si es aspecto de sombra
    """
    try:
        aspecto_en_zona = aspecto.updateMask(mascara_zona)

        # Calcular moda (aspecto más común)
        # Usamos media circular para aspectos
        # Convertir a componentes x,y y promediar
        aspecto_rad = aspecto_en_zona.multiply(math.pi / 180)

        sin_aspecto = aspecto_rad.sin()
        cos_aspecto = aspecto_rad.cos()

        resultado = sin_aspecto.addBands(cos_aspecto).reduceRegion(
            reducer=ee.Reducer.mean().repeat(2),
            geometry=area_buffer,
            scale=escala,
            maxPixels=1e10
        )

        stats = resultado.getInfo()

        # Reconstruir ángulo desde componentes
        if stats:
            sin_mean = stats.get('aspect_mean', [0])[0] if isinstance(stats.get('aspect_mean'), list) else stats.get('sin_mean', 0)
            cos_mean = stats.get('aspect_1_mean', [1])[0] if isinstance(stats.get('aspect_1_mean'), list) else stats.get('cos_mean', 1)

            # Si tenemos valores válidos
            if sin_mean is not None and cos_mean is not None:
                aspecto_grados = (math.atan2(sin_mean, cos_mean) * 180 / math.pi) % 360
            else:
                aspecto_grados = VALOR_NULO_GEE
        else:
            aspecto_grados = VALOR_NULO_GEE

        # Categorizar y verificar sombra
        if aspecto_grados != VALOR_NULO_GEE:
            categoria = categorizar_aspecto(aspecto_grados)
            hemisferio = detectar_hemisferio(latitud)
            sombra = es_aspecto_sombra(aspecto_grados, hemisferio)
        else:
            categoria = 'N/A'
            sombra = False

        return {
            'aspecto_grados': aspecto_grados,
            'categoria': categoria,
            'es_sombra': sombra
        }

    except Exception as e:
        logger.warning(f"Error calculando aspecto predominante: {e}")
        return {
            'aspecto_grados': VALOR_NULO_GEE,
            'categoria': 'N/A',
            'es_sombra': False
        }


def cubicar_zonas_completo(
    zonas_analizadas: Dict[str, Any],
    latitud: float,
    longitud: float,
    nombre_ubicacion: str,
    radio_metros: int = 5000
) -> Dict[str, Any]:
    """
    Realiza la cubicación completa de todas las zonas de avalancha.

    Esta función calcula todas las métricas necesarias para:
    - Estimar frecuencia base EAWS (% zona inicio)
    - Estimar tamaño potencial EAWS (desnivel, área)
    - Evaluar propensión a inestabilidad (aspecto sombra)

    Args:
        zonas_analizadas: Dict con las zonas clasificadas (de zonas.analizar_zonas_ubicacion)
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        nombre_ubicacion: Nombre de la ubicación
        radio_metros: Radio del análisis en metros

    Returns:
        Dict con todas las métricas calculadas
    """
    logger.info(f"Iniciando cubicación para {nombre_ubicacion}")

    area_buffer = zonas_analizadas['area_buffer']
    zona_inicio = zonas_analizadas['zona_inicio']
    zona_transito = zonas_analizadas['zona_transito']
    zona_deposito = zonas_analizadas['zona_deposito']
    zona_severidad = zonas_analizadas['zona_inicio_por_severidad']
    pendiente = zonas_analizadas['pendiente']
    aspecto = zonas_analizadas['aspecto']
    dem = zonas_analizadas['dem']
    hemisferio = zonas_analizadas['hemisferio']

    # 1. Calcular área del buffer
    area_buffer_ha = calcular_area_buffer(area_buffer)
    logger.info(f"Área de análisis: {area_buffer_ha:.1f} ha")

    # 2. Calcular áreas de cada zona
    ha_inicio_total = calcular_area_zona(zona_inicio, area_buffer)
    ha_inicio_30_45 = calcular_area_zona(zona_severidad['moderado'], area_buffer)
    ha_inicio_45_60 = calcular_area_zona(zona_severidad['severo'], area_buffer)
    ha_inicio_mas_60 = calcular_area_zona(zona_severidad['extremo'], area_buffer)
    ha_transito = calcular_area_zona(zona_transito, area_buffer)
    ha_deposito = calcular_area_zona(zona_deposito, area_buffer)

    logger.info(f"Áreas - Inicio: {ha_inicio_total:.1f} ha, Tránsito: {ha_transito:.1f} ha, Depósito: {ha_deposito:.1f} ha")

    # 3. Calcular porcentajes (proxies para Frecuencia EAWS)
    pct_inicio = (ha_inicio_total / area_buffer_ha * 100) if area_buffer_ha > 0 else 0
    pct_deposito = (ha_deposito / area_buffer_ha * 100) if area_buffer_ha > 0 else 0

    # 4. Calcular estadísticas de pendiente
    stats_pendiente = calcular_estadisticas_pendiente(pendiente, zona_inicio, area_buffer)
    pendiente_max_buffer = calcular_pendiente_maxima_buffer(pendiente, area_buffer)

    # 5. Calcular desniveles (proxy para Tamaño EAWS)
    desniveles = calcular_desnivel_zonas(dem, zona_inicio, zona_deposito, area_buffer)

    # 6. Calcular aspecto predominante (proxy para Estabilidad EAWS)
    aspecto_info = calcular_aspecto_predominante(aspecto, zona_inicio, area_buffer, latitud)

    # Compilar resultados
    resultado = {
        'nombre_ubicacion': nombre_ubicacion,
        'latitud': latitud,
        'longitud': longitud,
        'hemisferio': hemisferio,
        'radio_analisis_km': radio_metros / 1000,

        # Áreas en hectáreas
        'ha_zona_inicio_total': round(ha_inicio_total, 2),
        'ha_inicio_30_45': round(ha_inicio_30_45, 2),
        'ha_inicio_45_60': round(ha_inicio_45_60, 2),
        'ha_inicio_mas_60': round(ha_inicio_mas_60, 2),
        'ha_zona_transito': round(ha_transito, 2),
        'ha_zona_deposito': round(ha_deposito, 2),

        # Porcentajes (proxy Frecuencia EAWS)
        'pct_zona_inicio': round(pct_inicio, 2),
        'pct_zona_deposito': round(pct_deposito, 2),

        # Estadísticas de pendiente
        'pendiente_media_inicio': round(stats_pendiente['media'], 2) if stats_pendiente['media'] != VALOR_NULO_GEE else None,
        'pendiente_max': round(pendiente_max_buffer, 2) if pendiente_max_buffer != VALOR_NULO_GEE else None,
        'pendiente_p90': round(stats_pendiente['p90'], 2) if stats_pendiente['p90'] != VALOR_NULO_GEE else None,

        # Desniveles y elevaciones (proxy Tamaño EAWS)
        'desnivel_inicio_deposito': round(desniveles['desnivel'], 2) if desniveles['desnivel'] != VALOR_NULO_GEE else None,
        'elevacion_media_inicio': round(desniveles['elevacion_media_inicio'], 2) if desniveles['elevacion_media_inicio'] != VALOR_NULO_GEE else None,
        'elevacion_media_deposito': round(desniveles['elevacion_media_deposito'], 2) if desniveles['elevacion_media_deposito'] != VALOR_NULO_GEE else None,

        # Aspecto (proxy Estabilidad EAWS)
        'aspecto_predominante': round(aspecto_info['aspecto_grados'], 2) if aspecto_info['aspecto_grados'] != VALOR_NULO_GEE else None,
        'categoria_aspecto': aspecto_info['categoria'],
        'es_aspecto_sombra': aspecto_info['es_sombra']
    }

    logger.info(f"Cubicación completada para {nombre_ubicacion}")

    return resultado

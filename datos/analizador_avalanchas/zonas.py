"""
Clasificación de Zonas Funcionales de Avalancha usando Google Earth Engine

Este módulo implementa la detección y clasificación de las tres zonas funcionales
de un sistema de avalancha usando datos SRTM (Shuttle Radar Topography Mission):

1. ZONA DE INICIO: Donde se suelta la avalancha (pendiente 30°-60°, convexa)
2. ZONA DE TRÁNSITO: Corredor de flujo donde acelera (pendiente 15°-30°, canalizada)
3. ZONA DE DEPÓSITO: Donde se acumula (pendiente <15°, cóncava)

Usa Google Earth Engine para análisis espacial con datos DEM de 30m de resolución.

Referencias:
- Statham, G., et al. (2018). A conceptual model of avalanche hazard.
  Natural Hazards, 90, 663-691.
- Müller, K., Techel, F., & Mitterer, C. (2025). The EAWS matrix, Part A.
  Nat. Hazards Earth Syst. Sci., 25, 4503-4525.
"""

import logging
from typing import Dict, Any, Tuple, Optional

import ee

from eaws_constantes import (
    PENDIENTE_INICIO_MIN,
    PENDIENTE_INICIO_MAX,
    PENDIENTE_TRANSITO_MIN,
    PENDIENTE_TRANSITO_MAX,
    PENDIENTE_DEPOSITO_MAX,
    CURVATURA_CONVEXA_UMBRAL,
    CURVATURA_CONCAVA_UMBRAL,
    RADIO_ANALISIS_DEFAULT,
    es_aspecto_sombra,
    detectar_hemisferio
)


# Configuración de logging
logger = logging.getLogger(__name__)


def inicializar_gee(proyecto: str) -> None:
    """
    Inicializa Google Earth Engine con el proyecto especificado.

    Args:
        proyecto: ID del proyecto de GCP para autenticación

    Raises:
        Exception: Si falla la inicialización
    """
    try:
        ee.Initialize(project=proyecto)
        logger.info(f"Google Earth Engine inicializado con proyecto: {proyecto}")
    except Exception as e:
        logger.warning(f"GEE ya inicializado o error: {e}")
        # Intentar inicializar sin proyecto (usa credenciales por defecto)
        try:
            ee.Initialize()
            logger.info("Google Earth Engine inicializado con credenciales por defecto")
        except Exception as e2:
            logger.error(f"Error al inicializar GEE: {e2}")
            raise


def cargar_dem_srtm() -> Tuple[ee.Image, ee.Image, ee.Image]:
    """
    Carga el DEM SRTM y calcula productos derivados de terreno.

    Returns:
        Tuple[ee.Image, ee.Image, ee.Image]: (pendiente, aspecto, elevacion)
            - pendiente: en grados (0-90)
            - aspecto: en grados (0-360, 0=Norte)
            - elevacion: en metros sobre nivel del mar
    """
    # Cargar DEM SRTM de 30m de resolución
    dem = ee.Image('USGS/SRTMGL1_003').select('elevation')

    # Calcular productos de terreno
    terreno = ee.Terrain.products(dem)

    pendiente = terreno.select('slope')    # Grados: 0-90
    aspecto = terreno.select('aspect')     # Grados: 0-360 desde norte

    logger.info("DEM SRTM cargado con pendiente y aspecto calculados")

    return pendiente, aspecto, dem


def calcular_curvatura(dem: ee.Image) -> ee.Image:
    """
    Calcula la curvatura del terreno usando filtro Laplaciano.

    La curvatura indica:
    - Valores positivos: terreno convexo (crestas, protuberancias)
    - Valores negativos: terreno cóncavo (valles, canales)

    Args:
        dem: Imagen DEM de elevación

    Returns:
        ee.Image: Curvatura del terreno
    """
    # Kernel Laplaciano de 8 vecinos
    curvatura = dem.convolve(ee.Kernel.laplacian8())
    return curvatura


def crear_mascara_aspecto_sombra(
    aspecto: ee.Image,
    latitud: float
) -> ee.Image:
    """
    Crea una máscara para aspectos de sombra según hemisferio.

    Los aspectos de sombra reciben menos radiación solar, manteniendo
    la nieve más seca y potencialmente más inestable.

    Args:
        aspecto: Imagen de aspecto (0-360°)
        latitud: Latitud de la ubicación (para determinar hemisferio)

    Returns:
        ee.Image: Máscara binaria (1 = sombra, 0 = sol)
    """
    hemisferio = detectar_hemisferio(latitud)

    if hemisferio == 'sur':
        # Hemisferio sur: Norte (NW-N-NE) = sombra
        # 293° a 360° O 0° a 67°
        mascara = aspecto.lte(67).Or(aspecto.gte(293))
    else:
        # Hemisferio norte: Sur (SE-S-SW) = sombra
        # 113° a 247°
        mascara = aspecto.gte(113).And(aspecto.lte(247))

    return mascara


def clasificar_zona_inicio(
    pendiente: ee.Image,
    aspecto: ee.Image,
    dem: ee.Image,
    latitud: float
) -> ee.Image:
    """
    Clasifica la zona de inicio de avalanchas.

    La zona de inicio es donde se suelta la avalancha. Se caracteriza por:
    - Pendiente entre 30° y 60° (rango crítico para acumulación y suelta)
    - Curvatura convexa (terreno que "empuja" la nieve)
    - Preferencia por aspectos de sombra (nieve seca más inestable)

    Esta zona es crítica para evaluar la ESTABILIDAD del manto nival (Factor 1 EAWS).

    Args:
        pendiente: Imagen de pendiente en grados
        aspecto: Imagen de aspecto en grados
        dem: Imagen DEM de elevación
        latitud: Latitud para determinar hemisferio

    Returns:
        ee.Image: Máscara binaria de zona de inicio (1 = inicio, 0 = no)
    """
    # Calcular curvatura
    curvatura = calcular_curvatura(dem)

    # Curvatura local vs promedio de vecindario (para detectar convexidad relativa)
    pendiente_local = pendiente
    pendiente_vecindario = pendiente.focal_mean(radius=300, units='meters')
    convexidad_relativa = pendiente_local.subtract(pendiente_vecindario)

    # Máscara de aspecto sombra
    mascara_sombra = crear_mascara_aspecto_sombra(aspecto, latitud)

    # Criterios de zona de inicio:
    # 1. Pendiente en rango crítico (30°-60°)
    condicion_pendiente = pendiente.gte(PENDIENTE_INICIO_MIN).And(
        pendiente.lte(PENDIENTE_INICIO_MAX)
    )

    # 2. Curvatura convexa (valores positivos relativos al vecindario)
    condicion_convexa = convexidad_relativa.gt(CURVATURA_CONVEXA_UMBRAL)

    # 3. Aspecto sombra O pendiente muy empinada (>45° cualquier aspecto)
    condicion_aspecto = mascara_sombra.Or(pendiente.gte(45))

    # Combinación: todos los criterios
    zona_inicio = condicion_pendiente.And(condicion_convexa).And(condicion_aspecto)

    return zona_inicio.rename('zona_inicio')


def clasificar_zona_inicio_por_severidad(pendiente: ee.Image) -> Dict[str, ee.Image]:
    """
    Sub-clasifica la zona de inicio por rangos de pendiente (severidad).

    Args:
        pendiente: Imagen de pendiente en grados

    Returns:
        Dict con tres máscaras:
            - 'moderado': 30°-45° (pendiente moderada, más común)
            - 'severo': 45°-60° (pendiente severa)
            - 'extremo': >60° (pendiente extrema, menos acumulación)
    """
    # Moderado: 30° - 45°
    inicio_moderado = pendiente.gte(30).And(pendiente.lt(45))

    # Severo: 45° - 60°
    inicio_severo = pendiente.gte(45).And(pendiente.lte(60))

    # Extremo: > 60°
    inicio_extremo = pendiente.gt(60)

    return {
        'moderado': inicio_moderado.rename('inicio_30_45'),
        'severo': inicio_severo.rename('inicio_45_60'),
        'extremo': inicio_extremo.rename('inicio_mas_60')
    }


def clasificar_zona_transito(
    pendiente: ee.Image,
    dem: ee.Image
) -> ee.Image:
    """
    Clasifica la zona de tránsito de avalanchas.

    La zona de tránsito es el corredor donde la avalancha acelera y fluye.
    Se caracteriza por:
    - Pendiente media (15°-30°)
    - Forma canalizada (curvatura negativa = cóncavo)

    Esta zona influye en el TAMAÑO de avalancha (Factor 3 EAWS) por su longitud.

    Args:
        pendiente: Imagen de pendiente en grados
        dem: Imagen DEM de elevación

    Returns:
        ee.Image: Máscara binaria de zona de tránsito
    """
    # Calcular curvatura
    curvatura = calcular_curvatura(dem)

    # Criterios de zona de tránsito:
    # 1. Pendiente media (15°-30°)
    condicion_pendiente = pendiente.gte(PENDIENTE_TRANSITO_MIN).And(
        pendiente.lt(PENDIENTE_TRANSITO_MAX)
    )

    # 2. Forma cóncava (canal natural de flujo)
    condicion_concava = curvatura.lt(CURVATURA_CONCAVA_UMBRAL)

    # Combinación
    zona_transito = condicion_pendiente.And(condicion_concava)

    return zona_transito.rename('zona_transito')


def clasificar_zona_deposito(
    pendiente: ee.Image,
    dem: ee.Image
) -> ee.Image:
    """
    Clasifica la zona de depósito de avalanchas.

    La zona de depósito es donde se acumula la nieve y escombros.
    Se caracteriza por:
    - Pendiente baja (<15°)
    - Forma cóncava (acumulación natural)

    Esta zona es crítica para evaluar el IMPACTO y potencial destructivo.

    Args:
        pendiente: Imagen de pendiente en grados
        dem: Imagen DEM de elevación

    Returns:
        ee.Image: Máscara binaria de zona de depósito
    """
    # Calcular curvatura
    curvatura = calcular_curvatura(dem)

    # Criterios de zona de depósito:
    # 1. Pendiente baja (<15°)
    condicion_pendiente = pendiente.lt(PENDIENTE_DEPOSITO_MAX)

    # 2. Forma cóncava (acumulación)
    condicion_concava = curvatura.lt(-5)  # Menos estricto que tránsito

    # Combinación
    zona_deposito = condicion_pendiente.And(condicion_concava)

    return zona_deposito.rename('zona_deposito')


def crear_mapa_zonas_combinado(
    zona_inicio: ee.Image,
    zona_transito: ee.Image,
    zona_deposito: ee.Image
) -> ee.Image:
    """
    Crea una imagen combinada con todas las zonas clasificadas.

    Valores del mapa:
    - 0: Sin riesgo de avalancha
    - 1: Zona de inicio
    - 2: Zona de tránsito
    - 3: Zona de depósito

    Args:
        zona_inicio: Máscara de zona de inicio
        zona_transito: Máscara de zona de tránsito
        zona_deposito: Máscara de zona de depósito

    Returns:
        ee.Image: Mapa combinado de zonas (valores 0-3)
    """
    # Prioridad: inicio > tránsito > depósito
    # Si un píxel pertenece a múltiples zonas, toma la de mayor prioridad
    mapa = (
        zona_inicio.multiply(1)
        .add(zona_transito.multiply(2).where(zona_inicio, 0))
        .add(zona_deposito.multiply(3).where(zona_inicio.Or(zona_transito), 0))
    ).rename('zona_avalancha')

    return mapa


def analizar_zonas_ubicacion(
    latitud: float,
    longitud: float,
    radio_metros: int = RADIO_ANALISIS_DEFAULT
) -> Dict[str, Any]:
    """
    Analiza las zonas de avalancha para una ubicación específica.

    Args:
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        radio_metros: Radio del área de análisis en metros (default: 5000)

    Returns:
        Dict con:
            - zona_inicio: ee.Image máscara de zona de inicio
            - zona_inicio_por_severidad: Dict de sub-zonas
            - zona_transito: ee.Image máscara de zona de tránsito
            - zona_deposito: ee.Image máscara de zona de depósito
            - mapa_combinado: ee.Image con todas las zonas
            - pendiente: ee.Image de pendiente
            - aspecto: ee.Image de aspecto
            - dem: ee.Image de elevación
            - area_buffer: ee.Geometry del área de análisis
            - hemisferio: str ('norte' o 'sur')
    """
    logger.info(f"Analizando zonas para ubicación ({latitud}, {longitud}) con radio {radio_metros}m")

    # Cargar datos de terreno
    pendiente, aspecto, dem = cargar_dem_srtm()

    # Crear buffer de análisis
    punto = ee.Geometry.Point([longitud, latitud])
    area_buffer = punto.buffer(radio_metros)

    # Determinar hemisferio
    hemisferio = detectar_hemisferio(latitud)
    logger.info(f"Hemisferio detectado: {hemisferio}")

    # Clasificar zonas
    zona_inicio = clasificar_zona_inicio(pendiente, aspecto, dem, latitud)
    zona_inicio_por_severidad = clasificar_zona_inicio_por_severidad(pendiente)
    zona_transito = clasificar_zona_transito(pendiente, dem)
    zona_deposito = clasificar_zona_deposito(pendiente, dem)

    # Crear mapa combinado
    mapa_combinado = crear_mapa_zonas_combinado(zona_inicio, zona_transito, zona_deposito)

    logger.info("Clasificación de zonas completada")

    return {
        'zona_inicio': zona_inicio,
        'zona_inicio_por_severidad': zona_inicio_por_severidad,
        'zona_transito': zona_transito,
        'zona_deposito': zona_deposito,
        'mapa_combinado': mapa_combinado,
        'pendiente': pendiente,
        'aspecto': aspecto,
        'dem': dem,
        'area_buffer': area_buffer,
        'hemisferio': hemisferio
    }


def exportar_mapa_gcs(
    imagen: ee.Image,
    area_buffer: ee.Geometry,
    nombre_ubicacion: str,
    bucket: str,
    escala: int = 30
) -> ee.batch.Task:
    """
    Exporta un mapa de zonas como GeoTIFF a Cloud Storage.

    Args:
        imagen: Imagen a exportar
        area_buffer: Geometría del área de recorte
        nombre_ubicacion: Nombre de la ubicación (para nombrar archivo)
        bucket: Nombre del bucket de GCS
        escala: Resolución en metros (default: 30)

    Returns:
        ee.batch.Task: Tarea de exportación iniciada
    """
    # Normalizar nombre para el archivo
    nombre_archivo = nombre_ubicacion.lower().replace(' ', '_').replace('/', '_')

    # Configurar exportación
    tarea = ee.batch.Export.image.toCloudStorage(
        image=imagen.clip(area_buffer),
        description=f'mapa_zonas_{nombre_archivo}',
        bucket=bucket,
        fileNamePrefix=f'topografia/mapas_riesgo/{nombre_archivo}',
        scale=escala,
        region=area_buffer,
        fileFormat='GeoTIFF',
        maxPixels=1e10
    )

    # Iniciar tarea
    tarea.start()
    logger.info(f"Exportación iniciada para {nombre_ubicacion}: {tarea.status()}")

    return tarea

"""
Análisis Detallado de Pendientes para Evaluación de Riesgo de Avalanchas

Este módulo calcula métricas cuantitativas de pendiente y aspecto sobre el
área de análisis usando el DEM NASADEM de 30m de resolución:

- Estadísticas de pendiente (media, máxima, percentiles 50 y 90)
- Distribución EAWS por rangos de pendiente (5 rangos según riesgo)
- Histograma de pendientes por rangos de 5°
- Aspecto predominante y porcentaje de laderas sur
- Áreas en hectáreas por categoría de terreno
- Índice compuesto de riesgo topográfico (0-100)

El índice compuesto sigue la misma lógica que el script GEE JavaScript de
referencia: pendiente 50% + aspecto 25% + elevación 25%.

Referencias:
- Müller, K., Techel, F., & Mitterer, C. (2025). The EAWS matrix, Part A.
- Techel, F., et al. (2020). On the importance of snowpack stability.
"""

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import ee

# Importar constantes y ubicaciones desde módulos del analizador
from eaws_constantes import (
    RADIO_ANALISIS_DEFAULT,
    VALOR_NULO_GEE,
    categorizar_aspecto,
    detectar_hemisferio,
)
from main import (
    ID_PROYECTO,
    DATASET_BIGQUERY,
    BUCKET_BRONCE,
    UBICACIONES_ANALISIS,
)


# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Constantes del módulo
TABLA_PENDIENTES = 'pendientes_detalladas'
FUENTE_DEM = 'NASADEM'
RESOLUCION_M = 30
ESCALA_REDUCCION = 30  # metros, igual al DEM
MAX_PIXELES = 1e10


# ============================================================================
# FUNCIONES DE GOOGLE EARTH ENGINE
# ============================================================================

def inicializar_gee(proyecto: str) -> None:
    """
    Inicializa Google Earth Engine con el proyecto especificado.

    Args:
        proyecto: ID del proyecto de GCP para autenticación
    """
    try:
        ee.Initialize(project=proyecto)
        logger.info(f"[AnalisisPendientes] GEE inicializado con proyecto: {proyecto}")
    except Exception as e:
        logger.warning(f"[AnalisisPendientes] GEE ya inicializado o error: {e}")
        try:
            ee.Initialize()
            logger.info("[AnalisisPendientes] GEE inicializado con credenciales por defecto")
        except Exception as e2:
            logger.error(f"[AnalisisPendientes] Error al inicializar GEE: {e2}")
            raise


def _calcular_porcentaje_rango(
    pendiente: ee.Image,
    area_buffer: ee.Geometry,
    min_grados: float,
    max_grados: float
) -> float:
    """
    Calcula el porcentaje de píxeles en un rango de pendiente dado.

    Args:
        pendiente: Imagen de pendiente en grados
        area_buffer: Geometría del área de análisis
        min_grados: Límite inferior del rango (inclusive)
        max_grados: Límite superior del rango (exclusive), usar None para sin límite

    Returns:
        float: Porcentaje de píxeles en el rango (0-100)
    """
    if max_grados is None:
        mascara = pendiente.gte(min_grados)
    else:
        mascara = pendiente.gte(min_grados).And(pendiente.lt(max_grados))

    # Calcular área en el rango y área total para obtener porcentaje
    area_rango = mascara.multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=area_buffer,
        scale=ESCALA_REDUCCION,
        maxPixels=MAX_PIXELES
    )
    area_total = ee.Image.pixelArea().reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=area_buffer,
        scale=ESCALA_REDUCCION,
        maxPixels=MAX_PIXELES
    )

    vals_rango = area_rango.getInfo()
    vals_total = area_total.getInfo()

    # Primer valor de cada dict
    if not vals_rango or not vals_total:
        return 0.0

    val_r = list(vals_rango.values())[0]
    val_t = list(vals_total.values())[0]

    if val_t is None or val_t == 0 or val_r is None:
        return 0.0

    return round((val_r / val_t) * 100, 2)


def analizar_pendientes_ubicacion(
    nombre: str,
    lat: float,
    lon: float,
    radio_m: int = RADIO_ANALISIS_DEFAULT
) -> dict:
    """
    Analiza pendientes y aspecto de una ubicación usando NASADEM via Earth Engine.

    Usa ee.Image.cat() para combinar bandas y reducir llamadas a EE. Ejecuta
    tres reduceRegion combinados: estadísticas generales, distribución EAWS
    e histograma por rangos de 5°.

    Args:
        nombre: Nombre de la ubicación
        lat: Latitud en grados decimales
        lon: Longitud en grados decimales
        radio_m: Radio del buffer circular en metros

    Returns:
        dict: Diccionario con los 27 campos del schema de BigQuery,
              o {"dato_nulo": True, "razon_nulo": "..."} si falla
    """
    logger.info(f"[AnalisisPendientes] {nombre} → iniciando análisis (radio={radio_m}m)")

    try:
        # Definir área de análisis
        punto = ee.Geometry.Point([lon, lat])
        area_buffer = punto.buffer(radio_m)

        # Cargar DEM NASADEM y calcular productos de terreno
        dem = ee.Image('NASA/NASADEM_HGT/001').select('elevation')
        pendiente = ee.Terrain.slope(dem)
        aspecto = ee.Terrain.aspect(dem)

        # OPTIMIZACIÓN: combinar bandas en una sola imagen para reducir llamadas EE
        imagen_combinada = ee.Image.cat([dem, pendiente, aspecto]).rename(
            ['elevation', 'slope', 'aspect']
        )

        # ----------------------------------------------------------------
        # Reducción 1: estadísticas generales (media, max, min, percentiles)
        # Un solo reduceRegion combinado
        # ----------------------------------------------------------------
        reductor_stats = (
            ee.Reducer.mean()
            .combine(ee.Reducer.max(), sharedInputs=True)
            .combine(ee.Reducer.min(), sharedInputs=True)
            .combine(ee.Reducer.percentile([50, 90]), sharedInputs=True)
        )

        stats_raw = imagen_combinada.reduceRegion(
            reducer=reductor_stats,
            geometry=area_buffer,
            scale=ESCALA_REDUCCION,
            maxPixels=MAX_PIXELES
        ).getInfo()

        if not stats_raw:
            return {
                "dato_nulo": True,
                "razon_nulo": f"reduceRegion retornó vacío para {nombre}"
            }

        elevacion_min = stats_raw.get('elevation_min', VALOR_NULO_GEE)
        elevacion_max = stats_raw.get('elevation_max', VALOR_NULO_GEE)
        elevacion_media = stats_raw.get('elevation_mean', VALOR_NULO_GEE)
        pendiente_media = stats_raw.get('slope_mean', VALOR_NULO_GEE)
        pendiente_max_val = stats_raw.get('slope_max', VALOR_NULO_GEE)
        pendiente_p50 = stats_raw.get('slope_p50', VALOR_NULO_GEE)
        pendiente_p90 = stats_raw.get('slope_p90', VALOR_NULO_GEE)

        # Calcular desnivel total
        if elevacion_max != VALOR_NULO_GEE and elevacion_min != VALOR_NULO_GEE:
            desnivel_m = round(elevacion_max - elevacion_min, 2)
        else:
            desnivel_m = None

        logger.info(
            f"[AnalisisPendientes] {nombre} → "
            f"elev_media={elevacion_media:.0f}m, "
            f"pendiente_media={pendiente_media:.1f}°, "
            f"pendiente_max={pendiente_max_val:.1f}°"
        )

        # ----------------------------------------------------------------
        # Reducción 2: distribución EAWS (5 rangos de pendiente)
        # Se calculan como porcentajes de área total
        # ----------------------------------------------------------------
        area_total_m2 = area_buffer.area().getInfo()
        area_total_ha = round(area_total_m2 / 10000, 2) if area_total_m2 else None

        # Máscaras para cada rango EAWS
        mascara_moderado = pendiente.lt(30)                                  # <30°
        mascara_inicio_posible = pendiente.gte(30).And(pendiente.lt(35))    # 30-35°
        mascara_optimo = pendiente.gte(35).And(pendiente.lt(45))             # 35-45°
        mascara_severo = pendiente.gte(45).And(pendiente.lt(60))             # 45-60°
        mascara_paredes = pendiente.gte(60)                                   # >60°

        # Máscara para zona de avalancha (30-60°)
        mascara_avalancha = pendiente.gte(30).And(pendiente.lt(60))

        # Combinar todas las máscaras para un solo reduceRegion
        imagen_eaws = ee.Image.cat([
            mascara_moderado,
            mascara_inicio_posible,
            mascara_optimo,
            mascara_severo,
            mascara_paredes,
            mascara_avalancha
        ]).rename([
            'moderado', 'inicio_posible', 'optimo',
            'severo', 'paredes', 'avalancha'
        ])

        sumas_eaws = imagen_eaws.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=area_buffer,
            scale=ESCALA_REDUCCION,
            maxPixels=MAX_PIXELES
        ).getInfo()

        area_total_px_m2 = ee.Image.pixelArea().reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=area_buffer,
            scale=ESCALA_REDUCCION,
            maxPixels=MAX_PIXELES
        ).getInfo()

        # Área total en m² desde píxeles (más exacto que el área geométrica)
        area_px_m2 = list(area_total_px_m2.values())[0] if area_total_px_m2 else area_total_m2

        def _pct(clave: str) -> float:
            """Calcula porcentaje a partir de suma de área de píxeles."""
            if not sumas_eaws or area_px_m2 is None or area_px_m2 == 0:
                return 0.0
            val = sumas_eaws.get(clave)
            if val is None:
                return 0.0
            return round((val / area_px_m2) * 100, 2)

        pct_moderado = _pct('moderado')
        pct_inicio_posible = _pct('inicio_posible')
        pct_optimo = _pct('optimo')
        pct_severo = _pct('severo')
        pct_paredes = _pct('paredes')

        area_avalancha_m2 = sumas_eaws.get('avalancha', 0) if sumas_eaws else 0
        area_avalancha_ha = round(area_avalancha_m2 / 10000, 2) if area_avalancha_m2 else 0.0
        pct_area_avalancha = _pct('avalancha')

        logger.info(
            f"[AnalisisPendientes] {nombre} → "
            f"pct_optimo={pct_optimo}%, pct_severo={pct_severo}%, "
            f"area_avalancha={area_avalancha_ha:.1f}ha"
        )

        # ----------------------------------------------------------------
        # Reducción 3: histograma de pendientes cada 5° (0-90°)
        # ----------------------------------------------------------------
        rangos_histograma = list(range(0, 90, 5))  # [0, 5, 10, ..., 85]
        mascaras_hist = []
        nombres_hist = []

        for inicio_rango in rangos_histograma:
            fin_rango = inicio_rango + 5
            if fin_rango <= 90:
                mask = pendiente.gte(inicio_rango).And(pendiente.lt(fin_rango))
            else:
                mask = pendiente.gte(inicio_rango)
            mascaras_hist.append(mask)
            nombres_hist.append(f'r{inicio_rango}_{inicio_rango + 5}')

        imagen_hist = ee.Image.cat(mascaras_hist).rename(nombres_hist)
        sumas_hist = imagen_hist.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=area_buffer,
            scale=ESCALA_REDUCCION,
            maxPixels=MAX_PIXELES
        ).getInfo()

        histograma = {}
        for nombre_rango in nombres_hist:
            val = sumas_hist.get(nombre_rango, 0) if sumas_hist else 0
            pct_hist = round((val / area_px_m2) * 100, 2) if (area_px_m2 and val) else 0.0
            # Clave legible: "0-5", "5-10", etc.
            partes = nombre_rango.replace('r', '').split('_')
            clave_legible = f"{partes[0]}-{partes[1]}"
            histograma[clave_legible] = pct_hist

        histograma_json = json.dumps(histograma, ensure_ascii=False)

        # ----------------------------------------------------------------
        # Aspecto predominante (moda circular) y % laderas sur
        # ----------------------------------------------------------------
        # Aspecto usando media circular (sin/cos) para evitar discontinuidad en 0/360°
        aspecto_rad = aspecto.multiply(math.pi / 180)
        sin_asp = aspecto_rad.sin().rename('sin_asp')
        cos_asp = aspecto_rad.cos().rename('cos_asp')

        stats_aspecto = sin_asp.addBands(cos_asp).reduceRegion(
            reducer=ee.Reducer.mean().repeat(2),
            geometry=area_buffer,
            scale=ESCALA_REDUCCION,
            maxPixels=MAX_PIXELES
        ).getInfo()

        aspecto_predominante_str = 'N/A'
        if stats_aspecto:
            sin_mean_val = stats_aspecto.get('sin_asp_mean')
            cos_mean_val = stats_aspecto.get('cos_asp_mean')

            # Manejar formato de lista (repeat(2)) o escalar
            if isinstance(sin_mean_val, list):
                sin_mean_val = sin_mean_val[0] if sin_mean_val else None
            if isinstance(cos_mean_val, list):
                cos_mean_val = cos_mean_val[0] if cos_mean_val else None

            if sin_mean_val is not None and cos_mean_val is not None:
                aspecto_grados_calc = (math.atan2(sin_mean_val, cos_mean_val) * 180 / math.pi) % 360
                aspecto_predominante_str = categorizar_aspecto(aspecto_grados_calc)
                logger.info(
                    f"[AnalisisPendientes] {nombre} → "
                    f"aspecto={aspecto_grados_calc:.1f}° → {aspecto_predominante_str}"
                )

        # Porcentaje de laderas sur (aspecto 135°-225°)
        mascara_laderas_sur = aspecto.gte(135).And(aspecto.lt(225))
        suma_sur = mascara_laderas_sur.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=area_buffer,
            scale=ESCALA_REDUCCION,
            maxPixels=MAX_PIXELES
        ).getInfo()

        val_sur = list(suma_sur.values())[0] if suma_sur else 0
        pct_laderas_sur = round((val_sur / area_px_m2) * 100, 2) if (area_px_m2 and val_sur) else 0.0

        # ----------------------------------------------------------------
        # Índice compuesto de riesgo topográfico (0-100)
        # Composición: pendiente 50% + aspecto 25% + elevación 25%
        # Igual a la lógica del script GEE JavaScript de referencia
        # ----------------------------------------------------------------
        hemisferio = detectar_hemisferio(lat)

        # Componente pendiente (50%): normalizado sobre rango óptimo avalancha (35-45°)
        # Mayor peso para terreno en rango óptimo (35-45°) y severo (45-60°)
        score_pendiente = 0.0
        if pendiente_media != VALOR_NULO_GEE and pendiente_media is not None:
            # Normalizar pendiente media al rango 0-1 (máximo en ~45°)
            score_pendiente = min(1.0, max(0.0, pendiente_media / 45.0))
        # Amplificar por porcentaje de terreno óptimo
        factor_optimo = min(1.0, pct_optimo / 20.0)  # 20% óptimo → factor máximo
        score_pendiente = min(1.0, score_pendiente * (1.0 + factor_optimo))

        # Componente aspecto (25%): laderas de sombra más propensas (hemisferio norte)
        # En hemisferio sur: N/NE/NW son sombra; en hemisferio norte: S/SE/SW
        if hemisferio == 'sur':
            # Hemisferio sur: sombra en Norte → pct sin laderas sur = sombra
            pct_sombra = max(0.0, 100.0 - pct_laderas_sur)
        else:
            pct_sombra = pct_laderas_sur
        score_aspecto = min(1.0, pct_sombra / 50.0)  # 50% sombra → factor máximo

        # Componente elevación (25%): mayor elevación → más nieve → más riesgo
        score_elevacion = 0.0
        if elevacion_media != VALOR_NULO_GEE and elevacion_media is not None:
            # Normalizado: 0m → 0, 4000m → 1.0
            score_elevacion = min(1.0, max(0.0, elevacion_media / 4000.0))

        # Índice compuesto ponderado (0-100)
        indice_riesgo = round(
            (score_pendiente * 50.0) +
            (score_aspecto * 25.0) +
            (score_elevacion * 25.0),
            2
        )

        logger.info(
            f"[AnalisisPendientes] {nombre} → "
            f"índice_riesgo={indice_riesgo} "
            f"(pendiente={score_pendiente:.2f}, aspecto={score_aspecto:.2f}, "
            f"elevacion={score_elevacion:.2f})"
        )

        # ----------------------------------------------------------------
        # Construir resultado con los 27 campos del schema
        # ----------------------------------------------------------------
        fecha_analisis = datetime.now(timezone.utc)

        resultado = {
            'nombre_ubicacion': nombre,
            'latitud': lat,
            'longitud': lon,
            'fecha_analisis': fecha_analisis.isoformat(),
            'fuente_dem': FUENTE_DEM,
            'resolucion_m': RESOLUCION_M,
            'radio_analisis_m': radio_m,
            'elevacion_min': round(elevacion_min, 2) if elevacion_min != VALOR_NULO_GEE else None,
            'elevacion_max': round(elevacion_max, 2) if elevacion_max != VALOR_NULO_GEE else None,
            'elevacion_media': round(elevacion_media, 2) if elevacion_media != VALOR_NULO_GEE else None,
            'desnivel_m': desnivel_m,
            'pendiente_media': round(pendiente_media, 2) if pendiente_media != VALOR_NULO_GEE else None,
            'pendiente_max': round(pendiente_max_val, 2) if pendiente_max_val != VALOR_NULO_GEE else None,
            'pendiente_p50': round(pendiente_p50, 2) if pendiente_p50 != VALOR_NULO_GEE else None,
            'pendiente_p90': round(pendiente_p90, 2) if pendiente_p90 != VALOR_NULO_GEE else None,
            'pct_terreno_moderado': pct_moderado,
            'pct_inicio_posible': pct_inicio_posible,
            'pct_optimo_avalancha': pct_optimo,
            'pct_severo': pct_severo,
            'pct_paredes': pct_paredes,
            'aspecto_predominante': aspecto_predominante_str,
            'pct_laderas_sur': pct_laderas_sur,
            'indice_riesgo_topografico': indice_riesgo,
            'histograma_pendientes': histograma_json,
            'area_total_ha': area_total_ha,
            'area_avalancha_ha': area_avalancha_ha,
            'pct_area_avalancha': pct_area_avalancha,
        }

        logger.info(f"[AnalisisPendientes] {nombre} → análisis completado exitosamente")
        return resultado

    except Exception as e:
        logger.error(f"[AnalisisPendientes] {nombre} → error en análisis: {e}")
        return {
            "dato_nulo": True,
            "razon_nulo": f"Error en análisis GEE para {nombre}: {e}"
        }


# ============================================================================
# FUNCIONES DE BIGQUERY
# ============================================================================

def crear_tabla_bigquery() -> None:
    """
    Crea la tabla pendientes_detalladas en BigQuery si no existe.

    La tabla está particionada por fecha_analisis (TIMESTAMP) y
    clusterizada por nombre_ubicacion para optimizar las consultas
    más frecuentes (última fila por ubicación).
    """
    from google.cloud import bigquery

    tabla_id = f'{ID_PROYECTO}.{DATASET_BIGQUERY}.{TABLA_PENDIENTES}'

    # Cargar schema desde archivo JSON
    schema_path = os.path.join(os.path.dirname(__file__), 'schema_pendientes_bigquery.json')

    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_raw = json.load(f)

        # Convertir a objetos SchemaField de BigQuery
        schema_bq = [
            bigquery.SchemaField(
                name=campo['name'],
                field_type=campo['type'],
                mode=campo.get('mode', 'NULLABLE'),
                description=campo.get('description', '')
            )
            for campo in schema_raw
        ]

        cliente = bigquery.Client(project=ID_PROYECTO)

        # Verificar si la tabla ya existe
        try:
            cliente.get_table(tabla_id)
            logger.info(f"[AnalisisPendientes] Tabla {tabla_id} ya existe → no se crea")
            return
        except Exception:
            pass  # La tabla no existe, proceder a crearla

        tabla = bigquery.Table(tabla_id, schema=schema_bq)

        # Particionamiento por fecha_analisis
        tabla.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field='fecha_analisis'
        )

        # Clustering por nombre_ubicacion
        tabla.clustering_fields = ['nombre_ubicacion']

        cliente.create_table(tabla)
        logger.info(f"[AnalisisPendientes] Tabla creada → {tabla_id}")

    except Exception as e:
        logger.error(f"[AnalisisPendientes] Error creando tabla {tabla_id}: {e}")
        raise


def guardar_en_bigquery(filas: list) -> int:
    """
    Inserta filas en la tabla pendientes_detalladas de BigQuery.

    Args:
        filas: Lista de dicts con los 27 campos del schema

    Returns:
        int: Número de filas insertadas exitosamente, 0 si falla
    """
    from google.cloud import bigquery

    if not filas:
        logger.warning("[AnalisisPendientes] guardar_en_bigquery → lista vacía, nada que insertar")
        return 0

    tabla_id = f'{ID_PROYECTO}.{DATASET_BIGQUERY}.{TABLA_PENDIENTES}'
    cliente = bigquery.Client(project=ID_PROYECTO)

    try:
        errores = cliente.insert_rows_json(tabla_id, filas)

        if errores:
            logger.error(f"[AnalisisPendientes] Errores al insertar en BigQuery: {errores}")
            return 0

        logger.info(f"[AnalisisPendientes] guardar_en_bigquery → {len(filas)} filas insertadas en {tabla_id}")
        return len(filas)

    except Exception as e:
        logger.error(f"[AnalisisPendientes] Error insertando en BigQuery: {e}")
        return 0


# ============================================================================
# EXPORTACIÓN DE IMÁGENES A GCS
# ============================================================================

def exportar_imagen_pendientes_gcs(
    nombre: str,
    lat: float,
    lon: float,
    radio_m: int = RADIO_ANALISIS_DEFAULT,
    fecha: Optional[datetime] = None,
) -> Dict[str, str]:
    """
    Genera imágenes PNG de clasificación EAWS de pendiente y las sube a GCS.

    Usa ee.Image.getThumbURL() para obtener miniaturas síncronas desde Earth
    Engine, las descarga con requests y las sube al bucket de bronce en:
        {nombre_norm}/topografia/visualizaciones/{YYYY/MM/DD}/

    Archivos generados:
        - {ubi}_clases_eaws_{ts}.png   : Pendiente coloreada por rangos EAWS
                                         (verde → amarillo → naranja → rojo → morado)
        - {ubi}_pendiente_{ts}.png     : Mapa de calor de pendiente cruda (0°–60°)

    Args:
        nombre:  Nombre de la ubicación
        lat:     Latitud en grados decimales
        lon:     Longitud en grados decimales
        radio_m: Radio del buffer circular en metros
        fecha:   Fecha para la ruta GCS (default: UTC ahora)

    Returns:
        Dict con claves 'clases_eaws' y 'pendiente' → URIs gs://
        Dict vacío si la exportación falla completamente.
    """
    import requests
    from google.cloud import storage as gcs_storage

    if fecha is None:
        fecha = datetime.now(timezone.utc)

    nombre_norm = nombre.lower().replace(' ', '_').replace('/', '_')
    timestamp_str = fecha.strftime('%Y%m%d_%H%M%S')
    fecha_str = fecha.strftime('%Y/%m/%d')
    prefijo = f'{nombre_norm}/topografia/visualizaciones/{fecha_str}'

    logger.info(f"[ImagenesPendientes] {nombre} → generando imágenes GCS en {prefijo}/")

    try:
        # Área de análisis y datos de terreno
        punto = ee.Geometry.Point([lon, lat])
        area_buffer = punto.buffer(radio_m)

        dem = ee.Image('NASA/NASADEM_HGT/001').select('elevation')
        pendiente = ee.Terrain.slope(dem)

        # ---------------------------------------------------------------
        # Imagen 1: Clases EAWS de pendiente (valores 1-5, paleta colores)
        # Los rangos son mutuamente excluyentes → la suma da el valor clase
        # ---------------------------------------------------------------
        clases_eaws = (
            pendiente.lt(30).multiply(1)                              # 1 moderado  <30°
            .add(pendiente.gte(30).And(pendiente.lt(35)).multiply(2)) # 2 posible   30-35°
            .add(pendiente.gte(35).And(pendiente.lt(45)).multiply(3)) # 3 óptimo    35-45°
            .add(pendiente.gte(45).And(pendiente.lt(60)).multiply(4)) # 4 severo    45-60°
            .add(pendiente.gte(60).multiply(5))                       # 5 paredes   >60°
        )

        # ---------------------------------------------------------------
        # Imagen 2: Mapa de calor de pendiente cruda (0°–60°)
        # ---------------------------------------------------------------
        # Usa la imagen de pendiente directamente (escala blanco → rojo)

        # Parámetros de thumbnails
        params_clases = {
            'dimensions': 512,
            'region': area_buffer,
            'format': 'png',
            'min': 1,
            'max': 5,
            'palette': ['#2ECC71', '#F1C40F', '#E67E22', '#E74C3C', '#8E44AD'],
        }
        params_pendiente = {
            'dimensions': 512,
            'region': area_buffer,
            'format': 'png',
            'min': 0,
            'max': 60,
            'palette': ['#FFFFFF', '#FFFACD', '#FFA500', '#FF4500', '#8B0000'],
        }

        url_clases = clases_eaws.getThumbURL(params_clases)
        url_pendiente = pendiente.getThumbURL(params_pendiente)

    except Exception as e:
        logger.error(f"[ImagenesPendientes] {nombre} → error preparando imágenes EE: {e}")
        return {}

    # Descargar bytes de ambas imágenes
    imagenes_bytes: Dict[str, bytes] = {}
    for clave, url in [('clases_eaws', url_clases), ('pendiente', url_pendiente)]:
        try:
            resp = requests.get(url, timeout=180)
            resp.raise_for_status()
            imagenes_bytes[clave] = resp.content
            logger.info(
                f"[ImagenesPendientes] {nombre} → {clave} descargado "
                f"({len(resp.content) // 1024} KB)"
            )
        except Exception as e:
            logger.error(f"[ImagenesPendientes] {nombre} → error descargando {clave}: {e}")

    if not imagenes_bytes:
        return {}

    # Subir a GCS
    uris: Dict[str, str] = {}
    try:
        cliente_gcs = gcs_storage.Client(project=ID_PROYECTO)
        bucket_obj = cliente_gcs.bucket(BUCKET_BRONCE)

        sufijos = {
            'clases_eaws': f'{nombre_norm}_clases_eaws_{timestamp_str}.png',
            'pendiente':   f'{nombre_norm}_pendiente_{timestamp_str}.png',
        }

        for clave, datos in imagenes_bytes.items():
            ruta_blob = f'{prefijo}/{sufijos[clave]}'
            try:
                blob = bucket_obj.blob(ruta_blob)
                blob.upload_from_string(datos, content_type='image/png')
                uri = f'gs://{BUCKET_BRONCE}/{ruta_blob}'
                uris[clave] = uri
                logger.info(f"[ImagenesPendientes] {nombre} → subido: {uri}")
            except Exception as e:
                logger.error(f"[ImagenesPendientes] {nombre} → error subiendo {ruta_blob}: {e}")

    except Exception as e:
        logger.error(f"[ImagenesPendientes] {nombre} → error cliente GCS: {e}")

    return uris


# ============================================================================
# FUNCIÓN PRINCIPAL Y ARGPARSE
# ============================================================================

def main() -> None:
    """
    Punto de entrada principal del script de análisis de pendientes.

    Modos de ejecución:
        --todas          Analiza todas las ubicaciones en UBICACIONES_ANALISIS
        --ubicacion NOM  Analiza solo la ubicación con nombre exacto NOM
        --dry-run        Ejecuta el análisis pero no guarda en BigQuery
    """
    parser = argparse.ArgumentParser(
        description='Análisis de pendientes para evaluación de riesgo de avalanchas'
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        '--todas',
        action='store_true',
        help='Analizar todas las ubicaciones en UBICACIONES_ANALISIS'
    )
    grupo.add_argument(
        '--ubicacion',
        type=str,
        metavar='NOMBRE',
        help='Nombre exacto de la ubicación a analizar'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Ejecutar análisis sin guardar en BigQuery'
    )
    parser.add_argument(
        '--radio',
        type=int,
        default=RADIO_ANALISIS_DEFAULT,
        metavar='METROS',
        help=f'Radio de análisis en metros (default: {RADIO_ANALISIS_DEFAULT})'
    )
    parser.add_argument(
        '--imagenes',
        action='store_true',
        help='Generar y subir imágenes PNG de pendientes EAWS a GCS'
    )

    args = parser.parse_args()

    # Inicializar GEE
    proyecto_gee = os.environ.get('GEE_PROJECT', ID_PROYECTO)
    inicializar_gee(proyecto_gee)

    # Crear tabla si no existe (a menos que sea dry-run)
    if not args.dry_run:
        crear_tabla_bigquery()

    # Seleccionar ubicaciones a analizar
    if args.todas:
        ubicaciones_a_analizar = UBICACIONES_ANALISIS
        logger.info(f"[AnalisisPendientes] main → analizando {len(ubicaciones_a_analizar)} ubicaciones")
    else:
        # Buscar la ubicación por nombre exacto
        coincidencias = [
            u for u in UBICACIONES_ANALISIS
            if u['nombre'] == args.ubicacion
        ]
        if not coincidencias:
            logger.error(
                f"[AnalisisPendientes] main → ubicación '{args.ubicacion}' no encontrada en UBICACIONES_ANALISIS"
            )
            sys.exit(1)
        ubicaciones_a_analizar = coincidencias
        logger.info(f"[AnalisisPendientes] main → analizando ubicación: {args.ubicacion}")

    # Ejecutar análisis
    filas_exitosas = []
    filas_fallidas = []

    for ubicacion in ubicaciones_a_analizar:
        nombre_ub = ubicacion['nombre']
        lat_ub = ubicacion['latitud']
        lon_ub = ubicacion['longitud']

        resultado = analizar_pendientes_ubicacion(
            nombre=nombre_ub,
            lat=lat_ub,
            lon=lon_ub,
            radio_m=args.radio
        )

        if resultado.get('dato_nulo'):
            logger.warning(
                f"[AnalisisPendientes] main → {nombre_ub} falló: {resultado.get('razon_nulo')}"
            )
            filas_fallidas.append(nombre_ub)
        else:
            filas_exitosas.append(resultado)
            logger.info(f"[AnalisisPendientes] main → {nombre_ub} → OK")

            # Exportar imágenes PNG a GCS si se solicita y no es dry-run
            if args.imagenes and not args.dry_run:
                uris_imgs = exportar_imagen_pendientes_gcs(
                    nombre=nombre_ub,
                    lat=lat_ub,
                    lon=lon_ub,
                    radio_m=args.radio,
                )
                if uris_imgs:
                    logger.info(
                        f"[AnalisisPendientes] main → {nombre_ub} → "
                        f"imágenes: {list(uris_imgs.values())}"
                    )
                else:
                    logger.warning(
                        f"[AnalisisPendientes] main → {nombre_ub} → imágenes no generadas"
                    )

    # Guardar en BigQuery
    if filas_exitosas and not args.dry_run:
        insertadas = guardar_en_bigquery(filas_exitosas)
        logger.info(
            f"[AnalisisPendientes] main → {insertadas}/{len(filas_exitosas)} filas guardadas en BigQuery"
        )
    elif args.dry_run:
        logger.info(
            f"[AnalisisPendientes] main → dry-run: {len(filas_exitosas)} filas listas "
            f"(no se guardaron en BigQuery)"
        )

    # Resumen final
    logger.info(
        f"[AnalisisPendientes] main → resumen: "
        f"{len(filas_exitosas)} exitosas, {len(filas_fallidas)} fallidas"
    )
    if filas_fallidas:
        logger.warning(f"[AnalisisPendientes] main → fallidas: {filas_fallidas}")


if __name__ == '__main__':
    main()

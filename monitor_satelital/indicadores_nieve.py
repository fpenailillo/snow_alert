"""
Monitor Satelital de Nieve - Indicadores Derivados de Nieve

Funciones para calcular indicadores derivados de los productos satelitales:
- Línea de nieve (snowline) automática
- Cambio de cobertura de nieve entre capturas
- Índice de derretimiento acumulado (AMI)

Estos indicadores son críticos para la evaluación de riesgo EAWS porque
transforman observaciones puntuales en tendencias de cambio.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List

import ee

from constantes import (
    UMBRAL_NDSI_NIEVE,
    COLECCION_MODIS_NIEVE_TERRA,
    COLECCION_MODIS_LST,
    LST_FACTOR_ESCALA,
    KELVIN_A_CELSIUS,
)


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES PARA INDICADORES
# =============================================================================

# DEM para cálculo de snowline
COLECCION_DEM = 'USGS/SRTMGL1_003'

# Percentiles para snowline
PERCENTIL_SNOWLINE_BAJO = 10   # línea de nieve inferior
PERCENTIL_SNOWLINE_MEDIO = 50  # mediana
PERCENTIL_SNOWLINE_ALTO = 90   # límite superior

# Umbrales para clasificación de cambio de nieve
UMBRAL_GANANCIA_SIGNIFICATIVA = 15  # % ganancia en 24h = tormenta
UMBRAL_PERDIDA_SIGNIFICATIVA = 10   # % pérdida en 24h = fusión activa
UMBRAL_CAMBIO_ESTABLE = 5           # % cambio considerado estable

# Umbrales para AMI
UMBRAL_AMI_RIESGO_MODERADO = 10  # °C-día en 7 días
UMBRAL_AMI_RIESGO_ALTO = 20      # °C-día en 7 días


# =============================================================================
# LÍNEA DE NIEVE (SNOWLINE)
# =============================================================================

def calcular_snowline(
    imagen_ndsi: ee.Image,
    roi: ee.Geometry,
    umbral_ndsi: int = UMBRAL_NDSI_NIEVE,
    escala: int = 500
) -> Dict[str, Optional[float]]:
    """
    Calcula la elevación de la línea de nieve (snowline) en una captura.

    La snowline es la elevación donde comienza la cobertura de nieve.
    Se calcula usando el DEM SRTM y la máscara de nieve del NDSI.

    Importancia para Andes chilenos:
    - Con ~80% días soleados, la snowline es visible casi siempre
    - Snowline subiendo rápido = fusión activa = riesgo avalanchas húmedas
    - Snowline bajando rápido = nevada reciente = carga nueva sobre manto viejo
    - Diferencia snowline mañana vs tarde = intensidad del ciclo diurno

    Args:
        imagen_ndsi: Imagen MODIS NDSI con banda NDSI_Snow_Cover
        roi: Región de interés (buffer del punto)
        umbral_ndsi: Umbral NDSI para considerar nieve (default 40)
        escala: Escala de reducción en metros

    Returns:
        dict: Métricas de snowline:
            - snowline_elevacion_m: percentil 10 de elevación con nieve (msnm)
            - snowline_mediana_m: elevación mediana de la nieve (msnm)
            - snowline_p90_m: percentil 90 de elevación con nieve (msnm)
            - tiene_suficientes_pixeles: True si hay datos válidos
    """
    try:
        # Cargar DEM
        dem = ee.Image(COLECCION_DEM).select('elevation')

        # Crear máscara de nieve
        nieve_mask = imagen_ndsi.select('NDSI_Snow_Cover').gte(umbral_ndsi)

        # Aplicar máscara de nieve al DEM
        elevacion_nieve = dem.updateMask(nieve_mask)

        # Calcular percentiles de elevación donde hay nieve
        stats = elevacion_nieve.reduceRegion(
            reducer=ee.Reducer.percentile([
                PERCENTIL_SNOWLINE_BAJO,
                PERCENTIL_SNOWLINE_MEDIO,
                PERCENTIL_SNOWLINE_ALTO
            ]),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()

        # También contar píxeles para validar
        conteo = nieve_mask.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()

        pixeles_nieve = conteo.get('NDSI_Snow_Cover', 0) or 0
        tiene_suficientes = pixeles_nieve >= 10  # mínimo 10 píxeles

        resultado = {
            'snowline_elevacion_m': stats.get(f'elevation_p{PERCENTIL_SNOWLINE_BAJO}'),
            'snowline_mediana_m': stats.get(f'elevation_p{PERCENTIL_SNOWLINE_MEDIO}'),
            'snowline_p90_m': stats.get(f'elevation_p{PERCENTIL_SNOWLINE_ALTO}'),
            'tiene_suficientes_pixeles': tiene_suficientes,
        }

        # Redondear valores
        for key in ['snowline_elevacion_m', 'snowline_mediana_m', 'snowline_p90_m']:
            if resultado[key] is not None:
                resultado[key] = round(resultado[key], 0)

        if tiene_suficientes:
            logger.info(
                f"Snowline calculada: p10={resultado['snowline_elevacion_m']}m, "
                f"mediana={resultado['snowline_mediana_m']}m "
                f"({pixeles_nieve} píxeles de nieve)"
            )
        else:
            logger.info(f"Snowline: datos insuficientes ({pixeles_nieve} píxeles)")

        return resultado

    except Exception as e:
        logger.error(f"Error al calcular snowline: {str(e)}")
        return {
            'snowline_elevacion_m': None,
            'snowline_mediana_m': None,
            'snowline_p90_m': None,
            'tiene_suficientes_pixeles': False,
        }


def calcular_cambio_snowline(
    snowline_actual: Optional[float],
    snowline_anterior_24h: Optional[float],
    snowline_anterior_72h: Optional[float]
) -> Dict[str, Optional[float]]:
    """
    Calcula el cambio de snowline respecto a capturas anteriores.

    Args:
        snowline_actual: Elevación snowline actual (msnm)
        snowline_anterior_24h: Snowline de hace 24 horas
        snowline_anterior_72h: Snowline de hace 72 horas

    Returns:
        dict: Cambios de snowline:
            - snowline_cambio_24h_m: cambio vs 24h atrás (+ subió, - bajó)
            - snowline_cambio_72h_m: cambio vs 72h atrás
    """
    resultado = {
        'snowline_cambio_24h_m': None,
        'snowline_cambio_72h_m': None,
    }

    if snowline_actual is not None:
        if snowline_anterior_24h is not None:
            resultado['snowline_cambio_24h_m'] = round(
                snowline_actual - snowline_anterior_24h, 0
            )

        if snowline_anterior_72h is not None:
            resultado['snowline_cambio_72h_m'] = round(
                snowline_actual - snowline_anterior_72h, 0
            )

    return resultado


# =============================================================================
# CAMBIO DE COBERTURA DE NIEVE
# =============================================================================

def calcular_cambio_cobertura(
    imagen_ndsi_actual: ee.Image,
    imagen_ndsi_anterior: ee.Image,
    roi: ee.Geometry,
    umbral_ndsi: int = UMBRAL_NDSI_NIEVE,
    escala: int = 500
) -> Dict[str, Any]:
    """
    Compara cobertura de nieve entre dos capturas consecutivas.

    Importancia para Andes chilenos:
    - Ganancia rápida (>15% en 24h) = tormenta depositó nieve nueva
      → Carga sobre manto existente → riesgo de avalancha de placa
      → Proxy directo para estabilidad EAWS 'poor' o 'very_poor'
    - Pérdida rápida (>10% en 24h) = fusión activa
      → Agua percolando al manto → debilitamiento de capas
      → Riesgo de avalanchas de nieve húmeda/mojada
    - Estable (<5% cambio) = condiciones consolidadas

    Args:
        imagen_ndsi_actual: Imagen NDSI de la captura actual
        imagen_ndsi_anterior: Imagen NDSI de la captura anterior
        roi: Región de interés
        umbral_ndsi: Umbral NDSI para considerar nieve
        escala: Escala de reducción

    Returns:
        dict: Métricas de cambio:
            - delta_pct_nieve: cambio porcentual de cobertura
            - ganancia_pct: % de píxeles que ganaron nieve
            - perdida_pct: % de píxeles que perdieron nieve
            - tipo_cambio: 'ganancia' / 'perdida' / 'estable'
    """
    try:
        # Crear máscaras de nieve
        nieve_actual = imagen_ndsi_actual.select('NDSI_Snow_Cover').gte(umbral_ndsi)
        nieve_anterior = imagen_ndsi_anterior.select('NDSI_Snow_Cover').gte(umbral_ndsi)

        # Calcular cobertura actual
        stats_actual = nieve_actual.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()
        pct_actual = (stats_actual.get('NDSI_Snow_Cover', 0) or 0) * 100

        # Calcular cobertura anterior
        stats_anterior = nieve_anterior.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()
        pct_anterior = (stats_anterior.get('NDSI_Snow_Cover', 0) or 0) * 100

        # Calcular diferencia pixel a pixel
        # +1 = ganó nieve, -1 = perdió nieve, 0 = sin cambio
        cambio = nieve_actual.subtract(nieve_anterior)

        # Contar ganancia (píxeles que pasaron de no-nieve a nieve)
        ganancia = cambio.eq(1).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()
        ganancia_pct = (ganancia.get('NDSI_Snow_Cover', 0) or 0) * 100

        # Contar pérdida (píxeles que perdieron nieve)
        perdida = cambio.eq(-1).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()
        perdida_pct = (perdida.get('NDSI_Snow_Cover', 0) or 0) * 100

        # Calcular delta neto
        delta_pct = pct_actual - pct_anterior

        # Clasificar tipo de cambio
        if delta_pct > UMBRAL_GANANCIA_SIGNIFICATIVA:
            tipo_cambio = 'ganancia'
        elif delta_pct < -UMBRAL_PERDIDA_SIGNIFICATIVA:
            tipo_cambio = 'perdida'
        else:
            tipo_cambio = 'estable'

        resultado = {
            'delta_pct_nieve': round(delta_pct, 2),
            'ganancia_pct': round(ganancia_pct, 2),
            'perdida_pct': round(perdida_pct, 2),
            'tipo_cambio': tipo_cambio,
            'pct_cobertura_actual': round(pct_actual, 2),
            'pct_cobertura_anterior': round(pct_anterior, 2),
        }

        logger.info(
            f"Cambio cobertura: {delta_pct:+.1f}% ({tipo_cambio}), "
            f"ganancia={ganancia_pct:.1f}%, pérdida={perdida_pct:.1f}%"
        )

        return resultado

    except Exception as e:
        logger.error(f"Error al calcular cambio de cobertura: {str(e)}")
        return {
            'delta_pct_nieve': None,
            'ganancia_pct': None,
            'perdida_pct': None,
            'tipo_cambio': None,
            'pct_cobertura_actual': None,
            'pct_cobertura_anterior': None,
        }


def calcular_tasa_cambio_nieve(
    deltas_diarios: List[float]
) -> Optional[float]:
    """
    Calcula la tasa promedio de cambio de cobertura de nieve.

    Args:
        deltas_diarios: Lista de cambios diarios de cobertura (%)

    Returns:
        float: Tasa promedio de cambio (%/día)
    """
    if not deltas_diarios:
        return None

    return round(sum(deltas_diarios) / len(deltas_diarios), 2)


# =============================================================================
# ÍNDICE DE DERRETIMIENTO ACUMULADO (AMI)
# =============================================================================

def calcular_ami_desde_lst(
    roi: ee.Geometry,
    dias: int = 7,
    fecha_fin: Optional[datetime] = None,
    escala: int = 1000
) -> Dict[str, Optional[float]]:
    """
    Calcula el Índice de Derretimiento Acumulado (AMI) usando LST.

    El AMI suma los grados-día por encima de 0°C, indicando el potencial
    de fusión acumulada del manto nival.

    Importancia para Andes chilenos:
    - El ciclo diurno intenso (sol fuerte + altitud) genera derretimiento
      diario seguido de recongelamiento nocturno
    - AMI alto = manto nival debilitado progresivamente
    - AMI > 20°C-día en una semana = riesgo significativo de avalanchas húmedas
    - Combinado con snowline ascendente → señal fuerte de inestabilidad

    Método:
    1. Obtener LST diurna de cada día en la ventana
    2. Convertir a °C: (valor × 0.02) - 273.15
    3. Si T > 0°C: sumar al acumulador
    4. AMI = Σ max(T - 0, 0) para los últimos N días

    Args:
        roi: Región de interés
        dias: Número de días hacia atrás para el cálculo
        fecha_fin: Fecha final (default: hoy)
        escala: Escala de reducción en metros

    Returns:
        dict: Métricas AMI:
            - ami_Nd: grados-día acumulados en N días
            - ami_3d: grados-día acumulados en 3 días
            - ami_tendencia: 'creciente' / 'decreciente' / 'estable'
            - dias_con_fusion: número de días con T > 0°C
    """
    try:
        if fecha_fin is None:
            fecha_fin = datetime.utcnow()

        fecha_inicio = fecha_fin - timedelta(days=dias)

        # Obtener colección LST
        lst_collection = (ee.ImageCollection(COLECCION_MODIS_LST)
            .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
            .filterBounds(roi)
            .select('LST_Day_1km'))

        # Convertir a Celsius y calcular grados positivos
        def calcular_grados_positivos(imagen):
            celsius = imagen.multiply(LST_FACTOR_ESCALA).subtract(KELVIN_A_CELSIUS)
            positivos = celsius.max(0)  # solo valores > 0
            return positivos

        # Aplicar conversión
        grados_positivos = lst_collection.map(calcular_grados_positivos)

        # Sumar todos los días (AMI)
        ami_imagen = grados_positivos.reduce(ee.Reducer.sum())

        # Calcular estadísticas sobre el ROI
        stats = ami_imagen.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()

        ami_total = stats.get('LST_Day_1km_sum', 0) or 0

        # Calcular AMI de 3 días para comparar tendencia
        fecha_inicio_3d = fecha_fin - timedelta(days=3)
        lst_collection_3d = (ee.ImageCollection(COLECCION_MODIS_LST)
            .filterDate(fecha_inicio_3d.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
            .filterBounds(roi)
            .select('LST_Day_1km'))

        grados_positivos_3d = lst_collection_3d.map(calcular_grados_positivos)
        ami_imagen_3d = grados_positivos_3d.reduce(ee.Reducer.sum())

        stats_3d = ami_imagen_3d.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=escala,
            maxPixels=1e8
        ).getInfo()

        ami_3d = stats_3d.get('LST_Day_1km_sum', 0) or 0

        # Contar días con fusión
        cantidad_imagenes = lst_collection.size().getInfo()

        # Determinar tendencia
        if dias > 3 and ami_3d > 0:
            tasa_3d = ami_3d / 3
            tasa_total = ami_total / dias if dias > 0 else 0

            if tasa_3d > tasa_total * 1.2:
                tendencia = 'creciente'
            elif tasa_3d < tasa_total * 0.8:
                tendencia = 'decreciente'
            else:
                tendencia = 'estable'
        else:
            tendencia = 'sin_datos'

        resultado = {
            f'ami_{dias}d': round(ami_total, 2),
            'ami_3d': round(ami_3d, 2),
            'ami_tendencia': tendencia,
            'dias_con_datos': cantidad_imagenes,
        }

        logger.info(
            f"AMI calculado: {dias}d={ami_total:.1f}°C-día, "
            f"3d={ami_3d:.1f}°C-día, tendencia={tendencia}"
        )

        return resultado

    except Exception as e:
        logger.error(f"Error al calcular AMI: {str(e)}")
        return {
            f'ami_{dias}d': None,
            'ami_3d': None,
            'ami_tendencia': None,
            'dias_con_datos': 0,
        }


def calcular_ciclo_diurno(
    lst_dia_celsius: Optional[float],
    lst_noche_celsius: Optional[float]
) -> Dict[str, Optional[float]]:
    """
    Calcula la amplitud del ciclo diurno de temperatura.

    La diferencia entre LST día y noche indica la intensidad del
    ciclo fusión-recongelamiento, crítico para la metamorfosis
    de la nieve y la formación de costras de hielo.

    Args:
        lst_dia_celsius: Temperatura diurna en °C
        lst_noche_celsius: Temperatura nocturna en °C

    Returns:
        dict: Métricas de ciclo diurno:
            - ciclo_diurno_amplitud: LST_día - LST_noche (°C)
            - tiene_ciclo_intenso: True si amplitud > 10°C
    """
    resultado = {
        'ciclo_diurno_amplitud': None,
        'tiene_ciclo_intenso': False,
    }

    if lst_dia_celsius is not None and lst_noche_celsius is not None:
        amplitud = lst_dia_celsius - lst_noche_celsius
        resultado['ciclo_diurno_amplitud'] = round(amplitud, 2)
        resultado['tiene_ciclo_intenso'] = amplitud > 10  # >10°C = ciclo intenso

        logger.info(
            f"Ciclo diurno: amplitud={amplitud:.1f}°C "
            f"({'intenso' if resultado['tiene_ciclo_intenso'] else 'moderado'})"
        )

    return resultado


# =============================================================================
# FUNCIONES DE INTEGRACIÓN
# =============================================================================

def obtener_imagen_ndsi_anterior(
    latitud: float,
    longitud: float,
    fecha_actual: datetime,
    dias_atras: int = 1
) -> Optional[ee.Image]:
    """
    Obtiene la imagen NDSI de una fecha anterior para comparaciones.

    Args:
        latitud: Latitud del punto
        longitud: Longitud
        fecha_actual: Fecha de referencia
        dias_atras: Días hacia atrás a buscar

    Returns:
        ee.Image o None: Imagen NDSI más reciente en el rango
    """
    try:
        punto = ee.Geometry.Point([longitud, latitud])
        fecha_fin = fecha_actual - timedelta(days=dias_atras)
        fecha_inicio = fecha_fin - timedelta(days=3)  # ventana de 3 días

        coleccion = (ee.ImageCollection(COLECCION_MODIS_NIEVE_TERRA)
            .filterDate(fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))
            .filterBounds(punto)
            .sort('system:time_start', False))

        if coleccion.size().getInfo() > 0:
            return coleccion.first()

        return None

    except Exception as e:
        logger.error(f"Error al obtener imagen NDSI anterior: {str(e)}")
        return None


def compilar_indicadores_nieve(
    imagen_ndsi: ee.Image,
    roi: ee.Geometry,
    latitud: float,
    longitud: float,
    lst_dia_celsius: Optional[float],
    lst_noche_celsius: Optional[float],
    fecha_captura: datetime
) -> Dict[str, Any]:
    """
    Compila todos los indicadores derivados de nieve.

    Esta función integra snowline, cambio de cobertura, AMI y ciclo diurno
    en un solo diccionario de métricas para BigQuery.

    Args:
        imagen_ndsi: Imagen NDSI actual
        roi: Región de interés
        latitud: Latitud del punto
        longitud: Longitud del punto
        lst_dia_celsius: LST diurna (si está disponible)
        lst_noche_celsius: LST nocturna (si está disponible)
        fecha_captura: Fecha de la captura actual

    Returns:
        dict: Todas las métricas de indicadores de nieve
    """
    metricas = {}

    try:
        # 1. Calcular snowline
        snowline = calcular_snowline(imagen_ndsi, roi)
        metricas['snowline_elevacion_m'] = snowline.get('snowline_elevacion_m')
        metricas['snowline_mediana_m'] = snowline.get('snowline_mediana_m')

        # 2. Intentar obtener imagen anterior para comparar
        imagen_anterior = obtener_imagen_ndsi_anterior(latitud, longitud, fecha_captura, 1)

        if imagen_anterior is not None:
            cambio = calcular_cambio_cobertura(imagen_ndsi, imagen_anterior, roi)
            metricas['delta_pct_nieve_24h'] = cambio.get('delta_pct_nieve')
            metricas['tipo_cambio_nieve'] = cambio.get('tipo_cambio')
        else:
            metricas['delta_pct_nieve_24h'] = None
            metricas['tipo_cambio_nieve'] = None

        # 3. Intentar calcular cambio 72h
        imagen_72h = obtener_imagen_ndsi_anterior(latitud, longitud, fecha_captura, 3)
        if imagen_72h is not None:
            cambio_72h = calcular_cambio_cobertura(imagen_ndsi, imagen_72h, roi)
            metricas['delta_pct_nieve_72h'] = cambio_72h.get('delta_pct_nieve')
        else:
            metricas['delta_pct_nieve_72h'] = None

        # 4. Calcular cambio de snowline (requiere datos históricos)
        # Nota: esto normalmente se calcularía con datos de BigQuery
        metricas['snowline_cambio_24h_m'] = None
        metricas['snowline_cambio_72h_m'] = None

        # 5. Calcular AMI
        ami = calcular_ami_desde_lst(roi, dias=7, fecha_fin=fecha_captura)
        metricas['ami_7d'] = ami.get('ami_7d')
        metricas['ami_3d'] = ami.get('ami_3d')

        # 6. Calcular ciclo diurno
        ciclo = calcular_ciclo_diurno(lst_dia_celsius, lst_noche_celsius)
        metricas['ciclo_diurno_amplitud'] = ciclo.get('ciclo_diurno_amplitud')

        # 7. Calcular tasa de cambio (placeholder - requiere histórico)
        metricas['tasa_cambio_nieve_dia'] = None

        logger.info(f"Indicadores de nieve compilados: {len([v for v in metricas.values() if v is not None])} métricas")

    except Exception as e:
        logger.error(f"Error compilando indicadores de nieve: {str(e)}")

    return metricas

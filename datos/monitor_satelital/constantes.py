"""
Monitor Satelital de Nieve - Constantes y Configuraciones

Definiciones de colecciones GEE, bandas, parámetros de visualización,
horarios de captura y configuraciones de fuentes satelitales.
"""

import os
from typing import Dict, List, Any


# =============================================================================
# CONFIGURACIÓN DE PROYECTO GCP
# =============================================================================

ID_PROYECTO = os.environ.get('GCP_PROJECT', os.environ.get('GOOGLE_CLOUD_PROJECT', ''))
GEE_PROYECTO = os.environ.get('GEE_PROJECT', ID_PROYECTO)

# Storage
BUCKET_BRONCE = os.environ.get('BUCKET_CLIMA', 'datos-clima-bronce')
PREFIJO_SATELITAL = 'satelital'

# BigQuery
DATASET_CLIMA = os.environ.get('DATASET_CLIMA', 'clima')
TABLA_IMAGENES = 'imagenes_satelitales'

# Versión de metodología
VERSION_METODOLOGIA = 'v1.0.0'


# =============================================================================
# COLECCIONES GOOGLE EARTH ENGINE
# =============================================================================

# GOES-18 (Pacífico/Américas) - Imagen cada 10 minutos
COLECCION_GOES_18 = 'NOAA/GOES/18/MCMIPF'

# GOES-16 (Atlántico/Américas) - Imagen cada 10 minutos
COLECCION_GOES_16 = 'NOAA/GOES/16/MCMIPF'

# MODIS Terra - Reflectancia superficial (pasada ~10:30 hora local)
COLECCION_MODIS_REFLECTANCIA_TERRA = 'MODIS/061/MOD09GA'

# MODIS Aqua - Reflectancia superficial (pasada ~13:30 hora local)
COLECCION_MODIS_REFLECTANCIA_AQUA = 'MODIS/061/MYD09GA'

# MODIS Terra - Cobertura de nieve NDSI
COLECCION_MODIS_NIEVE_TERRA = 'MODIS/061/MOD10A1'

# MODIS Aqua - Cobertura de nieve NDSI
COLECCION_MODIS_NIEVE_AQUA = 'MODIS/061/MYD10A1'

# MODIS Terra - Temperatura superficial (LST día/noche)
COLECCION_MODIS_LST = 'MODIS/061/MOD11A1'

# VIIRS Suomi-NPP - Reflectancia superficial
COLECCION_VIIRS_REFLECTANCIA = 'NASA/VIIRS/002/VNP09GA'

# VIIRS - LST día
COLECCION_VIIRS_LST_DIA = 'NASA/VIIRS/002/VNP21A1D'

# VIIRS - LST noche
COLECCION_VIIRS_LST_NOCHE = 'NASA/VIIRS/002/VNP21A1N'

# ERA5-Land - Datos meteorológicos horarios (sin nubes)
COLECCION_ERA5_LAND = 'ECMWF/ERA5_LAND/HOURLY'

# Sentinel-2 - Alta resolución (cuando disponible)
COLECCION_SENTINEL2 = 'COPERNICUS/S2_SR_HARMONIZED'

# Cloud Score+ para Sentinel-2
COLECCION_CLOUD_SCORE = 'GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'


# =============================================================================
# BANDAS POR PRODUCTO
# =============================================================================

# GOES ABI Bandas
BANDAS_GOES = {
    'visible_rojo': 'CMI_C02',       # 0.64µm - reflectancia diurna
    'near_ir': 'CMI_C03',            # 0.86µm - vegetación vs nieve
    'swir': 'CMI_C05',               # 1.6µm - discriminación nieve/nube
    'ir_termico': 'CMI_C13',         # 10.3µm - temperatura 24/7
    'ir_shortwave': 'CMI_C07',       # 3.9µm - detección nocturna
    'visible_azul': 'CMI_C01',       # 0.47µm - azul
}

# MODIS Reflectancia Bandas
BANDAS_MODIS_REFLECTANCIA = {
    'rojo': 'sur_refl_b01',          # 620-670nm
    'verde': 'sur_refl_b04',         # 545-565nm
    'azul': 'sur_refl_b03',          # 459-479nm
    'swir_1': 'sur_refl_b06',        # 1628-1652nm
    'swir_2': 'sur_refl_b07',        # 2105-2155nm
    'estado': 'state_1km',           # Máscara de nubes
}

# MODIS Nieve Bandas
BANDAS_MODIS_NIEVE = {
    'ndsi_snow_cover': 'NDSI_Snow_Cover',     # 0-100% cobertura
    'ndsi_raw': 'NDSI',                        # NDSI crudo (-1 a +1 × 0.0001)
    'qa': 'NDSI_Snow_Cover_Basic_QA',          # Calidad: 0=Best, 1=Good, 2=OK, 3=Poor
    'albedo': 'Snow_Albedo_Daily_Tile',        # Albedo 1-100%
}

# MODIS LST Bandas
BANDAS_MODIS_LST = {
    'lst_dia': 'LST_Day_1km',         # Temperatura diurna (raw × 0.02 = Kelvin)
    'lst_noche': 'LST_Night_1km',     # Temperatura nocturna
    'qc_dia': 'QC_Day',               # Calidad día
    'qc_noche': 'QC_Night',           # Calidad noche
    'hora_dia': 'Day_view_time',      # Hora observación día (UTC fraccional)
    'hora_noche': 'Night_view_time',  # Hora observación noche
}

# ERA5-Land Bandas
BANDAS_ERA5 = {
    'snow_depth': 'snow_depth',                       # Profundidad nieve (m)
    'swe': 'snow_depth_water_equivalent',             # SWE (m)
    'snow_cover': 'snow_cover',                       # Fracción cobertura (0-1)
    'snowmelt': 'snowmelt',                           # Fusión (m agua equiv.)
    'temp_2m': 'temperature_2m',                      # Temperatura 2m (K)
}

# Sentinel-2 Bandas
BANDAS_SENTINEL2 = {
    'azul': 'B2',                    # 490nm, 10m
    'verde': 'B3',                   # 560nm, 10m
    'rojo': 'B4',                    # 665nm, 10m
    'nir': 'B8',                     # 842nm, 10m
    'swir_1': 'B11',                 # 1610nm, 20m
    'swir_2': 'B12',                 # 2190nm, 20m
    'scl': 'SCL',                    # Scene Classification Layer
}


# =============================================================================
# PARÁMETROS DE VISUALIZACIÓN
# =============================================================================

# MODIS True Color (RGB natural)
VIS_MODIS_TRUE_COLOR: Dict[str, Any] = {
    'bands': ['R', 'G', 'B'],
    'min': 0,
    'max': 3000,
    'gamma': 1.4,
}

# MODIS False Color Nieve (nieve = ROJA, nubes = blancas)
VIS_MODIS_FALSE_COLOR_NIEVE: Dict[str, Any] = {
    'bands': ['sur_refl_b03', 'sur_refl_b06', 'sur_refl_b07'],
    'min': -100,
    'max': 8000,
}

# MODIS NDSI Snow Cover
VIS_NDSI_SNOW: Dict[str, Any] = {
    'bands': ['NDSI'],
    'min': 0,
    'max': 100,
    'palette': ['000000', '0dffff', '0524ff', '8f0af4', 'ffffff'],
}

# MODIS LST
VIS_LST: Dict[str, Any] = {
    'bands': ['LST_Celsius'],
    'min': -30,
    'max': 40,
    'palette': [
        '040274', '040281', '0502a3', '0502b8', '0502ce',
        '0602df', '0602ff', '235cb1', '307ef3', '269db1',
        '30c8e2', '32d3ef', '3be285', '3ff38f', '86e26f',
        '3ae237', 'b5e22e', 'd6e21f', 'fff705', 'ffd611',
        'ffb613', 'ff8b13', 'ff6e08', 'ff500d', 'ff0000',
        'de0101', 'c21301'
    ],
}

# GOES Pseudo Color Visual
VIS_GOES_PSEUDO_COLOR: Dict[str, Any] = {
    'bands': ['R', 'G', 'B'],
    'min': 0.0,
    'max': 0.8,
}

# GOES Térmico
VIS_GOES_TERMICO: Dict[str, Any] = {
    'bands': ['CMI_C13'],
    'min': 200,
    'max': 310,
    'palette': ['000080', '0000ff', '00ffff', '00ff00',
                'ffff00', 'ff8000', 'ff0000', '800000'],
}

# ERA5-Land Snow Depth
VIS_ERA5_SNOW_DEPTH: Dict[str, Any] = {
    'bands': ['snow_depth_m'],
    'min': 0,
    'max': 2,
    'palette': ['4a4a4a', '99ccff', '6699ff', '3366cc', '003399', 'ffffff'],
}

# Sentinel-2 True Color
VIS_SENTINEL2_TRUE_COLOR: Dict[str, Any] = {
    'bands': ['B4', 'B3', 'B2'],
    'min': 0,
    'max': 3000,
}


# =============================================================================
# CONFIGURACIÓN DE FUENTES POR REGIÓN
# =============================================================================

FUENTES_POR_REGION: Dict[str, Dict[str, Any]] = {
    # =========== AMÉRICAS: GOES-18/16 como fuente principal sub-diaria ===========
    'chile': {
        'ubicaciones': [
            'Portillo', 'Ski Arpa', 'La Parva Sector Bajo', 'La Parva Sector Medio',
            'La Parva Sector Alto', 'El Colorado', 'Valle Nevado', 'Lagunillas',
            'Chapa Verde', 'Nevados de Chillán', 'Antuco', 'Corralco',
            'Las Araucarias', 'Ski Pucón', 'Los Arenales', 'Antillanca',
            'Volcán Osorno', 'El Fraile', 'Cerro Mirador'
        ],
        'fuente_principal': 'GOES-18',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 3,
    },
    'argentina': {
        'ubicaciones': [
            'Cerro Catedral', 'Las Leñas', 'Chapelco', 'Cerro Castor', 'Cerro Bayo'
        ],
        'fuente_principal': 'GOES-18',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 3,
    },
    'norteamerica': {
        'ubicaciones': [
            'Vail', 'Aspen', 'Jackson Hole', 'Whistler', 'Park City', 'Mammoth Mountain'
        ],
        'fuente_principal': 'GOES-16',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 3,
    },
    'montanismo_americas': {
        'ubicaciones': [
            'Plaza de Mulas - Aconcagua', 'Torres del Paine Base', 'Monte Fitz Roy',
            'Denali Base'
        ],
        'fuente_principal': 'GOES-18',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 3,
    },
    'pueblos_americas': {
        'ubicaciones': [
            'Bariloche', 'Ushuaia', 'Pucon', 'San Martin de los Andes', 'Banff'
        ],
        'fuente_principal': 'GOES-18',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 3,
    },

    # =========== EUROPA/ASIA/OCEANÍA: solo MODIS (sin GOES) ===========
    'europa_alpes': {
        'ubicaciones': [
            'Chamonix', 'Zermatt', 'St Moritz', 'Verbier',
            'Courchevel', 'Val Thorens', 'Cortina dAmpezzo'
        ],
        'fuente_principal': 'MODIS',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 2,
        'nota': 'Sin cobertura GOES. Meteosat no está en GEE.',
    },
    'asia_oceania': {
        'ubicaciones': [
            'Queenstown', 'Niseko', 'Hakuba'
        ],
        'fuente_principal': 'MODIS',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 2,
        'nota': 'Sin cobertura GOES. Himawari no está en GEE.',
    },
    'montanismo_global': {
        'ubicaciones': [
            'Everest Base Camp Nepal', 'Chamonix Mont Blanc',
            'Kilimanjaro Gate', 'Matterhorn Zermatt'
        ],
        'fuente_principal': 'MODIS',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 2,
    },
    'pueblos_global': {
        'ubicaciones': ['Innsbruck', 'Interlaken'],
        'fuente_principal': 'MODIS',
        'fuente_diaria': 'MODIS',
        'fuente_alta_res': 'Sentinel-2',
        'gap_filler': 'ERA5-Land',
        'capturas_dia': 2,
    },
}


# =============================================================================
# HORARIOS DE CAPTURA
# =============================================================================

HORARIOS_CAPTURA: Dict[str, Dict[str, str]] = {
    'manana': {'hora_utc_base': '12:00', 'tipo': 'diurna'},
    'tarde': {'hora_utc_base': '18:00', 'tipo': 'diurna'},
    'noche': {'hora_utc_base': '04:00', 'tipo': 'nocturna_termica'},
}


# =============================================================================
# CONFIGURACIÓN DE PROCESAMIENTO
# =============================================================================

# Tamaño del tile en metros (radio desde el punto central)
RADIO_TILE_METROS = 5000  # 5km → tile de ~10km × 10km

# Resoluciones por fuente (metros)
RESOLUCIONES: Dict[str, int] = {
    'GOES-18': 2000,
    'GOES-16': 2000,
    'MODIS': 500,
    'MODIS_LST': 1000,
    'VIIRS': 500,
    'ERA5-Land': 11000,
    'Sentinel-2': 10,
}

# Umbrales
UMBRAL_NUBES_NUBLADO = 80  # % de nubes para marcar como nublado
UMBRAL_NDSI_NIEVE = 40     # NDSI >= 40 = nieve (estándar global)

# Días hacia atrás para buscar imágenes
DIAS_BUSQUEDA_GOES = 1     # GOES tiene latencia ~1 hora
DIAS_BUSQUEDA_MODIS = 14   # MODIS tiene latencia 2-14 días (MOD11A1 LST puede tardar >7)
DIAS_BUSQUEDA_ERA5 = 7     # ERA5 tiene latencia ~5 días
DIAS_BUSQUEDA_SENTINEL2 = 30  # Sentinel-2 tiene baja revisita

# Configuración de reintentos
MAX_REINTENTOS = 3
TIMEOUT_DESCARGA_SEGUNDOS = 60
ESPERA_ENTRE_REINTENTOS = [2, 4, 8]  # Backoff exponencial

# Batch processing
TAMANO_LOTE = 5   # 5 ubicaciones por lote → ~100s/lote, margen seguro para timeout 540s
ESPERA_ENTRE_LOTES_SEGUNDOS = 1

# Dimensiones de imágenes
DIMENSION_PREVIEW = 768
DIMENSION_THUMBNAIL = 256

# Validación de completitud de imágenes por tipo de producto.
# GeoTIFFs: umbral calibrado según resolución y tipo de dato de cada producto.
#   - NDSI (UINT8, 500m, 10km tile): 20×20px × 1B ≈ 400B raw, muy comprimible → umbral bajo
#   - LST/Visual (FLOAT32, 500m-1km): umbral estándar, 927B = patrón canónico vacío
#   - ERA5 (3 bandas FLOAT32, 11km, 25km ROI): archivos válidos > 2KB, umbral estándar
# PNGs: 1200-1500B = PNG transparente (todo enmascarado, sin datos útiles)
MIN_BYTES_GEOTIFF_NDSI = 450    # NDSI UINT8: < 450B → tile con cero píxeles válidos
MIN_BYTES_GEOTIFF = 1024        # LST/Visual/ERA5: < 1KB → vacío, patrón 927B = sin datos
MIN_BYTES_PNG = 2500            # < 2.5KB → PNG mayormente transparente, sin contenido útil


# =============================================================================
# VALORES ESPECIALES
# =============================================================================

# Valores de máscara MODIS NDSI
NDSI_VALOR_NUBE = 250
NDSI_VALOR_NOCHE = 211
NDSI_VALOR_AGUA = 237
NDSI_VALOR_SIN_DATOS = 255

# Factor de escala LST
LST_FACTOR_ESCALA = 0.02  # raw × 0.02 = Kelvin

# Conversión Kelvin a Celsius
KELVIN_A_CELSIUS = 273.15

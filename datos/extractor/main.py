"""
Snow Alert - Extractor de Condiciones de Nieve y Clima de Montaña

Cloud Function HTTP que extrae datos climáticos de la Google Weather API
para centros de esquí, pueblos de montaña y destinos de montañismo a nivel mundial.
Publica los datos a Pub/Sub para su procesamiento.

Arquitectura: Cloud Scheduler → Cloud Function (Extractor) → Pub/Sub Topic

Cobertura:
- Centros de Esquí (Chile, Argentina, Europa, Norteamérica, Oceanía)
- Pueblos de Montaña
- Bases de Montañas Populares para Montañismo
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple

import functions_framework
import httpx
import requests
from google.cloud import pubsub_v1
from google.cloud import secretmanager
from flask import Request


# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Constantes de configuración
ID_PROYECTO = os.environ.get('GCP_PROJECT', os.environ.get('GOOGLE_CLOUD_PROJECT', ''))

# Topics de Pub/Sub para cada tipo de dato
TOPIC_CONDICIONES_ACTUALES = 'clima-datos-crudos'
TOPIC_PRONOSTICO_HORAS = 'clima-pronostico-horas'
TOPIC_PRONOSTICO_DIAS = 'clima-pronostico-dias'

# URLs de la Weather API
URL_API_CONDICIONES = 'https://weather.googleapis.com/v1/currentConditions:lookup'
URL_API_PRONOSTICO_HORAS = 'https://weather.googleapis.com/v1/forecast/hours:lookup'
URL_API_PRONOSTICO_DIAS = 'https://weather.googleapis.com/v1/forecast/days:lookup'

# Configuración de pronósticos
HORAS_PRONOSTICO = 76   # Próximas 76 horas (~3 días con detalle horario)
DIAS_PRONOSTICO = 10    # Próximos 10 días (máximo de la API)

NOMBRE_SECRET_API_KEY = 'weather-api-key'

# Ubicaciones a monitorear: Centros de Esquí, Pueblos de Montaña y Destinos de Montañismo
# Cobertura mundial de destinos con nieve y alta montaña
UBICACIONES_MONITOREO = [
    # ========================================================================
    # CENTROS DE ESQUÍ - CHILE (cobertura completa, de norte a sur)
    # ========================================================================

    # --- Región de Valparaíso ---
    {
        'nombre': 'Portillo',
        'latitud': -32.8369,
        'longitud': -70.1287,
        'descripcion': 'Portillo, Los Andes, Chile - Centro de Esquí Legendario (base 2580m / cima 3310m)'
    },
    {
        'nombre': 'Ski Arpa',
        'latitud': -32.6000,
        'longitud': -70.3900,
        'descripcion': 'Ski Arpa, Los Andes, Chile - Único Centro de Cat-Ski de Chile, 4000 acres (base 2690m / cima 3740m)'
    },

    # --- Región Metropolitana (Tres Valles - MCP Mountain Partners) ---
    {
        'nombre': 'La Parva Sector Bajo',
        'latitud': -33.3630,
        'longitud': -70.3010,
        'descripcion': 'La Parva - Sector Bajo / Villa La Parva, Chile - MCP Mountain, Zona base (2650m)'
    },
    {
        'nombre': 'La Parva Sector Medio',
        'latitud': -33.3520,
        'longitud': -70.2900,
        'descripcion': 'La Parva - Sector Medio / Restaurante 3100, Chile - MCP Mountain, Zona media (3100m)'
    },
    {
        'nombre': 'La Parva Sector Alto',
        'latitud': -33.3440,
        'longitud': -70.2800,
        'descripcion': 'La Parva - Sector Alto / Cima, Chile - MCP Mountain, Zona cumbre experto (3574m)'
    },
    {
        'nombre': 'El Colorado',
        'latitud': -33.3600,
        'longitud': -70.3000,
        'descripcion': 'El Colorado / Farellones, Chile - MCP Mountain, Mayor pistas Tres Valles (base 2350m / cima 3460m)'
    },
    {
        'nombre': 'Valle Nevado',
        'latitud': -33.3547,
        'longitud': -70.2498,
        'descripcion': 'Valle Nevado, Chile - MCP Mountain, Mayor resort Sudamérica (base 2860m / cima 3670m)'
    },
    {
        'nombre': 'Lagunillas',
        'latitud': -33.6800,
        'longitud': -70.2500,
        'descripcion': 'Lagunillas, San José de Maipo, Chile - Centro familiar, 3 remontes (base 2200m / cima 2550m)'
    },

    # --- Región de O'Higgins ---
    {
        'nombre': 'Chapa Verde',
        'latitud': -34.1700,
        'longitud': -70.3700,
        'descripcion': 'Chapa Verde, Rancagua, Chile - Centro de Esquí CODELCO, acceso restringido (base 2260m / cima 3050m)'
    },

    # --- Región de Ñuble / Biobío ---
    {
        'nombre': 'Nevados de Chillán',
        'latitud': -36.8580,
        'longitud': -71.3727,
        'descripcion': 'Nevados de Chillán, Chile - Volcán Activo, Termas y Esquí (base 1530m / cima 2400m)'
    },
    {
        'nombre': 'Antuco',
        'latitud': -37.4100,
        'longitud': -71.4200,
        'descripcion': 'Ski Antuco, Los Ángeles, Chile - Volcán Antuco, Biobío (base 1400m / cima 1850m)'
    },

    # --- Región de La Araucanía ---
    {
        'nombre': 'Corralco',
        'latitud': -38.3700,
        'longitud': -71.5700,
        'descripcion': 'Corralco, Volcán Lonquimay, Chile - Bosques de Araucarias y Nieve Andina (base 1550m / cima 2400m)'
    },
    {
        'nombre': 'Las Araucarias',
        'latitud': -38.7300,
        'longitud': -71.7400,
        'descripcion': 'Las Araucarias / Llaima, Vilcún, Chile - Esquí en Volcán Llaima (base 1550m / cima 1942m)'
    },
    {
        'nombre': 'Ski Pucón',
        'latitud': -39.5000,
        'longitud': -71.9600,
        'descripcion': 'Ski Pucón / Pillán, Volcán Villarrica, Chile - MCP Mountain, Esquí volcán activo (base 1380m / cima 2100m)'
    },
    {
        'nombre': 'Los Arenales',
        'latitud': -38.8500,
        'longitud': -72.0000,
        'descripcion': 'Los Arenales, Temuco, Chile - Centro de Entrenamiento y Esquí Familiar (base 1600m / cima 1845m)'
    },

    # --- Región de Los Lagos ---
    {
        'nombre': 'Antillanca',
        'latitud': -40.7756,
        'longitud': -72.2046,
        'descripcion': 'Antillanca, Volcán Casablanca, Chile - Parque Nacional Puyehue (base 1040m / cima 1540m)'
    },
    {
        'nombre': 'Volcán Osorno',
        'latitud': -41.1000,
        'longitud': -72.5000,
        'descripcion': 'Volcán Osorno, Puerto Varas, Chile - MCP Mountain, Volcán icónico patagónico (base 1230m / cima 1760m)'
    },

    # --- Región de Aysén ---
    {
        'nombre': 'El Fraile',
        'latitud': -45.6800,
        'longitud': -71.9400,
        'descripcion': 'El Fraile, Coyhaique, Chile - Esquí entre Bosques de Lenga Patagónicos (base 980m / cima 1280m)'
    },

    # --- Región de Magallanes ---
    {
        'nombre': 'Cerro Mirador',
        'latitud': -53.1300,
        'longitud': -70.9800,
        'descripcion': 'Cerro Mirador, Punta Arenas, Chile - Centro de Esquí más Austral del Mundo (base 380m / cima 570m)'
    },

    # ========================================================================
    # CENTROS DE ESQUÍ - ARGENTINA
    # ========================================================================
    {
        'nombre': 'Cerro Catedral',
        'latitud': -41.1667,
        'longitud': -71.4500,
        'descripcion': 'Cerro Catedral, Bariloche, Argentina - Mayor Centro de Esquí de Sudamérica (2100m)'
    },
    {
        'nombre': 'Las Leñas',
        'latitud': -35.1500,
        'longitud': -70.0833,
        'descripcion': 'Las Leñas, Mendoza, Argentina - Esquí de Alta Montaña y Freeride (3430m)'
    },
    {
        'nombre': 'Chapelco',
        'latitud': -40.1500,
        'longitud': -71.2500,
        'descripcion': 'Chapelco, San Martín de los Andes, Argentina - Esquí Patagónico (1980m)'
    },
    {
        'nombre': 'Cerro Castor',
        'latitud': -54.7500,
        'longitud': -68.3333,
        'descripcion': 'Cerro Castor, Ushuaia, Argentina - Centro de Esquí más Austral del Mundo (1057m)'
    },
    {
        'nombre': 'Cerro Bayo',
        'latitud': -40.7167,
        'longitud': -71.5167,
        'descripcion': 'Cerro Bayo, Villa La Angostura, Argentina - Esquí Boutique Patagonia (1780m)'
    },

    # ========================================================================
    # CENTROS DE ESQUÍ - EUROPA (ALPES)
    # ========================================================================
    {
        'nombre': 'Chamonix',
        'latitud': 45.9237,
        'longitud': 6.8694,
        'descripcion': 'Chamonix-Mont-Blanc, Francia - Capital Mundial del Alpinismo (1035m)'
    },
    {
        'nombre': 'Zermatt',
        'latitud': 46.0207,
        'longitud': 7.7491,
        'descripcion': 'Zermatt, Suiza - Esquí con Vista al Matterhorn (1608m)'
    },
    {
        'nombre': 'St Moritz',
        'latitud': 46.4908,
        'longitud': 9.8355,
        'descripcion': 'St. Moritz, Suiza - Cuna del Turismo de Invierno de Lujo (1822m)'
    },
    {
        'nombre': 'Verbier',
        'latitud': 46.0964,
        'longitud': 7.2286,
        'descripcion': 'Verbier, Suiza - Freeride y Esquí de Alta Montaña (1500m)'
    },
    {
        'nombre': 'Courchevel',
        'latitud': 45.4154,
        'longitud': 6.6347,
        'descripcion': 'Courchevel, Francia - Parte de Les 3 Vallées, Mayor Dominio Esquiable (1850m)'
    },
    {
        'nombre': 'Val Thorens',
        'latitud': 45.2981,
        'longitud': 6.5797,
        'descripcion': 'Val Thorens, Francia - Estación de Esquí más Alta de Europa (2300m)'
    },
    {
        'nombre': 'Cortina dAmpezzo',
        'latitud': 46.5369,
        'longitud': 12.1356,
        'descripcion': 'Cortina d\'Ampezzo, Italia - Reina de las Dolomitas (1224m)'
    },

    # ========================================================================
    # CENTROS DE ESQUÍ - NORTEAMÉRICA
    # ========================================================================
    {
        'nombre': 'Vail',
        'latitud': 39.6403,
        'longitud': -106.3742,
        'descripcion': 'Vail, Colorado, USA - Legendario Resort de Esquí Rockies (2476m)'
    },
    {
        'nombre': 'Aspen',
        'latitud': 39.1911,
        'longitud': -106.8175,
        'descripcion': 'Aspen, Colorado, USA - Icono del Esquí de Lujo (2438m)'
    },
    {
        'nombre': 'Jackson Hole',
        'latitud': 43.5875,
        'longitud': -110.8278,
        'descripcion': 'Jackson Hole, Wyoming, USA - Esquí Extremo y Vida Salvaje (1924m)'
    },
    {
        'nombre': 'Whistler',
        'latitud': 50.1163,
        'longitud': -122.9574,
        'descripcion': 'Whistler Blackcomb, BC, Canadá - Mayor Resort de Esquí de Norteamérica (675m)'
    },
    {
        'nombre': 'Park City',
        'latitud': 40.6461,
        'longitud': -111.4980,
        'descripcion': 'Park City, Utah, USA - Mayor Resort de Esquí de USA (2103m)'
    },
    {
        'nombre': 'Mammoth Mountain',
        'latitud': 37.6308,
        'longitud': -119.0326,
        'descripcion': 'Mammoth Mountain, California, USA - Esquí en Sierra Nevada (2424m)'
    },

    # --- MCP Mountain Partners (Mountain Capital Partners) ---
    # Tercer grupo de resorts más grande de USA por número de centros
    {
        'nombre': 'Purgatory Resort',
        'latitud': 37.6303,
        'longitud': -107.8140,
        'descripcion': 'Purgatory Resort, Durango, Colorado, USA - MCP Mountain, San Juan Mountains (base 2710m / cima 3299m)'
    },
    {
        'nombre': 'Arizona Snowbowl',
        'latitud': 35.3304,
        'longitud': -111.7107,
        'descripcion': 'Arizona Snowbowl, Flagstaff, Arizona, USA - MCP Mountain, San Francisco Peaks (base 2805m / cima 3505m)'
    },
    {
        'nombre': 'Brian Head Resort',
        'latitud': 37.7021,
        'longitud': -112.8499,
        'descripcion': 'Brian Head Resort, Utah, USA - MCP Mountain, Base más alta de Utah (base 2926m / cima 3353m)'
    },
    {
        'nombre': 'Lee Canyon',
        'latitud': 36.3038,
        'longitud': -115.6796,
        'descripcion': 'Lee Canyon, Las Vegas, Nevada, USA - MCP Mountain, Spring Mountains (base 2594m / cima 3353m)'
    },
    {
        'nombre': 'Nordic Valley',
        'latitud': 40.4800,
        'longitud': -111.8600,
        'descripcion': 'Nordic Valley, Eden, Utah, USA - MCP Mountain, Wasatch Range (base 1676m / cima 1981m)'
    },
    {
        'nombre': 'Sipapu Ski Resort',
        'latitud': 36.1542,
        'longitud': -105.5483,
        'descripcion': 'Sipapu Ski Resort, Taos, New Mexico, USA - MCP Mountain, Carson National Forest (base 2591m / cima 2865m)'
    },
    {
        'nombre': 'Pajarito Mountain',
        'latitud': 35.8903,
        'longitud': -106.3928,
        'descripcion': 'Pajarito Mountain, Los Alamos, New Mexico, USA - MCP Mountain, Jemez Mountains (base 2743m / cima 3182m)'
    },
    {
        'nombre': 'Sandia Peak',
        'latitud': 35.2070,
        'longitud': -106.4136,
        'descripcion': 'Sandia Peak, Albuquerque, New Mexico, USA - MCP Mountain, Primer resort de NM desde 1936 (base 2591m / cima 3200m)'
    },
    {
        'nombre': 'Willamette Pass',
        'latitud': 43.6007,
        'longitud': -122.0365,
        'descripcion': 'Willamette Pass, Oregon, USA - MCP Mountain, Cascade Range, 430" nieve anual (base 1676m / cima 2011m)'
    },
    {
        'nombre': 'Hesperus Ski Area',
        'latitud': 37.2996,
        'longitud': -108.0551,
        'descripcion': 'Hesperus Ski Area, Durango, Colorado, USA - MCP Mountain, Centro familiar (base 2499m / cima 2707m)'
    },

    # ========================================================================
    # CENTROS DE ESQUÍ - OCEANÍA Y ASIA
    # ========================================================================
    {
        'nombre': 'Queenstown',
        'latitud': -45.0312,
        'longitud': 168.6626,
        'descripcion': 'Queenstown, Nueva Zelanda - Capital de la Aventura, Remarkables y Coronet Peak'
    },
    {
        'nombre': 'Niseko',
        'latitud': 42.8048,
        'longitud': 140.6874,
        'descripcion': 'Niseko, Hokkaido, Japón - Mejor Nieve Polvo del Mundo (400m)'
    },
    {
        'nombre': 'Hakuba',
        'latitud': 36.6983,
        'longitud': 137.8619,
        'descripcion': 'Hakuba Valley, Japón - Sede Olímpica Nagano 1998, Alpes Japoneses (760m)'
    },

    # ========================================================================
    # PUEBLOS DE MONTAÑA
    # ========================================================================
    {
        'nombre': 'Bariloche',
        'latitud': -41.1335,
        'longitud': -71.3103,
        'descripcion': 'San Carlos de Bariloche, Argentina - Suiza de Sudamérica, Patagonia'
    },
    {
        'nombre': 'Ushuaia',
        'latitud': -54.8019,
        'longitud': -68.3030,
        'descripcion': 'Ushuaia, Argentina - Fin del Mundo, Base para Antártida'
    },
    {
        'nombre': 'Pucon',
        'latitud': -39.2819,
        'longitud': -71.9755,
        'descripcion': 'Pucón, Chile - Turismo Aventura y Volcán Villarrica'
    },
    {
        'nombre': 'San Martin de los Andes',
        'latitud': -40.1575,
        'longitud': -71.3522,
        'descripcion': 'San Martín de los Andes, Argentina - Pueblo Patagónico de Montaña'
    },
    {
        'nombre': 'Innsbruck',
        'latitud': 47.2692,
        'longitud': 11.4041,
        'descripcion': 'Innsbruck, Austria - Capital del Tirol, Doble Sede Olímpica de Invierno'
    },
    {
        'nombre': 'Interlaken',
        'latitud': 46.6863,
        'longitud': 7.8632,
        'descripcion': 'Interlaken, Suiza - Portal a Jungfrau y Alpes Berneses'
    },
    {
        'nombre': 'Banff',
        'latitud': 51.1784,
        'longitud': -115.5708,
        'descripcion': 'Banff, Alberta, Canadá - Pueblo de Montaña en Parque Nacional Rockies'
    },

    # ========================================================================
    # BASES DE MONTAÑISMO - ALTA MONTAÑA
    # ========================================================================
    {
        'nombre': 'Plaza de Mulas - Aconcagua',
        'latitud': -32.6500,
        'longitud': -70.0167,
        'descripcion': 'Plaza de Mulas, Argentina - Campo Base Aconcagua, Techo de América (4370m)'
    },
    {
        'nombre': 'Everest Base Camp Nepal',
        'latitud': 28.0025,
        'longitud': 86.8528,
        'descripcion': 'Campo Base Everest Sur, Nepal - Base para Techo del Mundo (5364m)'
    },
    {
        'nombre': 'Chamonix Mont Blanc',
        'latitud': 45.8326,
        'longitud': 6.8652,
        'descripcion': 'Refuge du Goûter Area, Francia - Ruta al Mont Blanc (3817m)'
    },
    {
        'nombre': 'Denali Base',
        'latitud': 63.0692,
        'longitud': -151.0070,
        'descripcion': 'Denali Base Camp, Alaska, USA - Campo Base McKinley, Montaña más Alta de Norteamérica'
    },
    {
        'nombre': 'Torres del Paine Base',
        'latitud': -50.9423,
        'longitud': -72.9682,
        'descripcion': 'Torres del Paine, Chile - Base W Trek y Circuito, Patagonia'
    },
    {
        'nombre': 'Kilimanjaro Gate',
        'latitud': -3.0674,
        'longitud': 37.3556,
        'descripcion': 'Machame Gate, Tanzania - Acceso al Kilimanjaro, Techo de África (1800m)'
    },
    {
        'nombre': 'Monte Fitz Roy',
        'latitud': -49.2714,
        'longitud': -72.9411,
        'descripcion': 'El Chaltén, Argentina - Base para Monte Fitz Roy, Patagonia'
    },
    {
        'nombre': 'Matterhorn Zermatt',
        'latitud': 45.9766,
        'longitud': 7.6586,
        'descripcion': 'Hörnli Hut Area, Suiza - Base para Ascenso al Matterhorn (3260m)'
    }
]


class ErrorExtraccionClima(Exception):
    """Excepción levantada cuando falla la extracción de datos climáticos."""
    pass


class ErrorPublicacionPubSub(Exception):
    """Excepción levantada cuando falla la publicación de mensajes a Pub/Sub."""
    pass


class ErrorConfiguracion(Exception):
    """Excepción levantada cuando hay problemas con la configuración."""
    pass


def obtener_api_key() -> str:
    """
    Obtiene la API Key de Google Weather desde Secret Manager.

    Returns:
        str: API Key para autenticación con Weather API

    Raises:
        ErrorConfiguracion: Si no se puede obtener la API Key
    """
    try:
        cliente_secrets = secretmanager.SecretManagerServiceClient()

        # Construir nombre del secret
        nombre_secret = f"projects/{ID_PROYECTO}/secrets/{NOMBRE_SECRET_API_KEY}/versions/latest"

        # Obtener el secret
        respuesta = cliente_secrets.access_secret_version(request={"name": nombre_secret})
        api_key = respuesta.payload.data.decode('UTF-8')

        logger.info("API Key obtenida exitosamente desde Secret Manager")
        return api_key

    except Exception as e:
        mensaje_error = f"Error al obtener API Key desde Secret Manager: {str(e)}"
        logger.error(mensaje_error)
        raise ErrorConfiguracion(mensaje_error)


def construir_url_api(
    url_base: str,
    latitud: float,
    longitud: float,
    api_key: str,
    parametros_extra: Dict[str, Any] = None
) -> str:
    """
    Construye la URL completa para la llamada a la Weather API.

    Args:
        url_base: URL base del endpoint (condiciones, horas, días)
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        api_key: API Key para autenticación
        parametros_extra: Parámetros adicionales (ej: hours, days)

    Returns:
        str: URL completa con query parameters
    """
    # Construir URL con query parameters básicos
    url = (
        f"{url_base}"
        f"?key={api_key}"
        f"&location.latitude={latitud}"
        f"&location.longitude={longitud}"
        f"&languageCode=es"
    )

    # Agregar parámetros extra si existen
    if parametros_extra:
        for clave, valor in parametros_extra.items():
            url += f"&{clave}={valor}"

    return url


def llamar_weather_api(
    url_base: str,
    latitud: float,
    longitud: float,
    nombre_ubicacion: str,
    api_key: str,
    parametros_extra: Dict[str, Any] = None,
    tipo_consulta: str = "condiciones"
) -> Dict[str, Any]:
    """
    Realiza llamada GET a la Google Weather API.

    Args:
        url_base: URL base del endpoint
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        nombre_ubicacion: Nombre descriptivo de la ubicación
        api_key: API Key para autenticación
        parametros_extra: Parámetros adicionales (hours, days, etc.)
        tipo_consulta: Tipo de consulta para logging

    Returns:
        dict: Datos climáticos obtenidos de la API

    Raises:
        ErrorExtraccionClima: Si la llamada a la API falla
    """
    try:
        # Construir URL con query parameters
        url = construir_url_api(url_base, latitud, longitud, api_key, parametros_extra)

        logger.info(f"Consultando {tipo_consulta} para {nombre_ubicacion} ({latitud}, {longitud})")

        # Hacer GET request — usar httpx como cliente principal (SSL más robusto en Cloud Run)
        with httpx.Client(timeout=30) as cliente:
            respuesta = cliente.get(url)

        if respuesta.status_code != 200:
            mensaje_error = (
                f"Error en API ({tipo_consulta}) para {nombre_ubicacion}: "
                f"Estado {respuesta.status_code}, Respuesta: {respuesta.text[:500]}"
            )
            logger.error(mensaje_error)
            raise ErrorExtraccionClima(mensaje_error)

        datos_clima = respuesta.json()
        logger.info(f"{tipo_consulta.capitalize()} obtenido exitosamente para {nombre_ubicacion}")

        return datos_clima

    except ErrorExtraccionClima:
        raise
    except (httpx.RequestError, requests.exceptions.RequestException) as e:
        mensaje_error = f"Error de red al llamar API ({tipo_consulta}) para {nombre_ubicacion}: {str(e)}"
        logger.error(mensaje_error)
        raise ErrorExtraccionClima(mensaje_error)
    except Exception as e:
        mensaje_error = f"Error inesperado al llamar API ({tipo_consulta}) para {nombre_ubicacion}: {str(e)}"
        logger.error(mensaje_error)
        raise ErrorExtraccionClima(mensaje_error)


def obtener_condiciones_actuales(
    latitud: float,
    longitud: float,
    nombre_ubicacion: str,
    api_key: str
) -> Dict[str, Any]:
    """
    Obtiene las condiciones climáticas actuales para una ubicación.

    Args:
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        nombre_ubicacion: Nombre descriptivo
        api_key: API Key

    Returns:
        dict: Condiciones actuales
    """
    return llamar_weather_api(
        URL_API_CONDICIONES,
        latitud,
        longitud,
        nombre_ubicacion,
        api_key,
        tipo_consulta="condiciones actuales"
    )


def obtener_pronostico_horas(
    latitud: float,
    longitud: float,
    nombre_ubicacion: str,
    api_key: str,
    horas: int = HORAS_PRONOSTICO
) -> Dict[str, Any]:
    """
    Obtiene el pronóstico por hora para una ubicación.

    Args:
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        nombre_ubicacion: Nombre descriptivo
        api_key: API Key
        horas: Número de horas de pronóstico (default: 24)

    Returns:
        dict: Pronóstico por hora con array 'forecastHours'
    """
    return llamar_weather_api(
        URL_API_PRONOSTICO_HORAS,
        latitud,
        longitud,
        nombre_ubicacion,
        api_key,
        parametros_extra={'hours': horas},
        tipo_consulta=f"pronóstico {horas}h"
    )


def obtener_pronostico_dias(
    latitud: float,
    longitud: float,
    nombre_ubicacion: str,
    api_key: str,
    dias: int = DIAS_PRONOSTICO
) -> Dict[str, Any]:
    """
    Obtiene el pronóstico diario para una ubicación.

    Args:
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        nombre_ubicacion: Nombre descriptivo
        api_key: API Key
        dias: Número de días de pronóstico (default: 5)

    Returns:
        dict: Pronóstico diario con array 'forecastDays'
    """
    return llamar_weather_api(
        URL_API_PRONOSTICO_DIAS,
        latitud,
        longitud,
        nombre_ubicacion,
        api_key,
        parametros_extra={'days': dias},
        tipo_consulta=f"pronóstico {dias} días"
    )


def enriquecer_datos(
    datos_clima: Dict[str, Any],
    ubicacion: Dict[str, Any],
    tipo_dato: str = 'condiciones_actuales'
) -> Dict[str, Any]:
    """
    Enriquece los datos climáticos con metadata adicional.

    Args:
        datos_clima: Datos crudos de la Weather API
        ubicacion: Información de la ubicación monitoreada
        tipo_dato: Tipo de dato ('condiciones_actuales', 'pronostico_horas', 'pronostico_dias')

    Returns:
        dict: Datos climáticos enriquecidos con metadata
    """
    marca_tiempo = datetime.now(timezone.utc).isoformat()

    datos_enriquecidos = {
        'marca_tiempo_extraccion': marca_tiempo,
        'nombre_ubicacion': ubicacion['nombre'],
        'coordenadas': {
            'latitud': ubicacion['latitud'],
            'longitud': ubicacion['longitud']
        },
        'descripcion_ubicacion': ubicacion['descripcion'],
        'tipo_dato': tipo_dato,
        'datos_clima_raw': datos_clima,
        'version_extractor': '3.0.0'  # v3: Soporte para pronósticos hora/día
    }

    return datos_enriquecidos


def publicar_a_pubsub(
    cliente_publicador: pubsub_v1.PublisherClient,
    ruta_topic: str,
    datos_mensaje: Dict[str, Any],
    nombre_ubicacion: str
) -> str:
    """
    Publica datos climáticos a un topic de Pub/Sub.

    Args:
        cliente_publicador: Cliente de Pub/Sub Publisher
        ruta_topic: Ruta completa del topic
        datos_mensaje: Datos a publicar
        nombre_ubicacion: Nombre de la ubicación (para logging)

    Returns:
        str: ID del mensaje publicado

    Raises:
        ErrorPublicacionPubSub: Si falla la publicación
    """
    try:
        # Convertir datos a JSON bytes
        mensaje_json = json.dumps(datos_mensaje, ensure_ascii=False)
        mensaje_bytes = mensaje_json.encode('utf-8')

        # Atributos del mensaje para filtrado y routing
        atributos = {
            'ubicacion': nombre_ubicacion,
            'tipo': 'datos_clima',
            'version': '2.0'
        }

        # Publicar mensaje
        futuro = cliente_publicador.publish(
            ruta_topic,
            mensaje_bytes,
            **atributos
        )

        # Esperar confirmación
        id_mensaje = futuro.result(timeout=10)

        logger.info(
            f"Mensaje publicado exitosamente a Pub/Sub para {nombre_ubicacion}. "
            f"ID: {id_mensaje}"
        )

        return id_mensaje

    except Exception as e:
        mensaje_error = f"Error al publicar mensaje para {nombre_ubicacion}: {str(e)}"
        logger.error(mensaje_error)
        raise ErrorPublicacionPubSub(mensaje_error)


def obtener_ubicaciones_monitoreo() -> List[Dict[str, Any]]:
    """
    Obtiene la lista de ubicaciones a monitorear.

    En producción, esto podría venir de Cloud Storage, Firestore, o Secret Manager.
    Por ahora usa la constante UBICACIONES_MONITOREO.

    Returns:
        list: Lista de diccionarios con información de ubicaciones
    """
    return UBICACIONES_MONITOREO


def procesar_ubicacion(
    ubicacion: Dict[str, Any],
    api_key: str,
    cliente_publicador: pubsub_v1.PublisherClient,
    proyecto: str
) -> Dict[str, Any]:
    """
    Procesa una ubicación: extrae condiciones actuales y pronósticos,
    publica a los respectivos topics de Pub/Sub.

    Args:
        ubicacion: Información de la ubicación
        api_key: API Key para Weather API
        cliente_publicador: Cliente Pub/Sub
        proyecto: ID del proyecto GCP

    Returns:
        dict: Resultado del procesamiento con conteos de éxitos/fallos
    """
    nombre_ubicacion = ubicacion['nombre']
    resultado = {
        'ubicacion': nombre_ubicacion,
        'condiciones_actuales': {'estado': 'pendiente'},
        'pronostico_horas': {'estado': 'pendiente'},
        'pronostico_dias': {'estado': 'pendiente'},
        'exitosos': 0,
        'fallidos': 0
    }

    # Topics para cada tipo de dato
    topics = {
        'condiciones_actuales': cliente_publicador.topic_path(proyecto, TOPIC_CONDICIONES_ACTUALES),
        'pronostico_horas': cliente_publicador.topic_path(proyecto, TOPIC_PRONOSTICO_HORAS),
        'pronostico_dias': cliente_publicador.topic_path(proyecto, TOPIC_PRONOSTICO_DIAS)
    }

    # 1. Condiciones Actuales
    try:
        datos = obtener_condiciones_actuales(
            ubicacion['latitud'],
            ubicacion['longitud'],
            nombre_ubicacion,
            api_key
        )
        datos_enriquecidos = enriquecer_datos(datos, ubicacion, 'condiciones_actuales')
        id_mensaje = publicar_a_pubsub(
            cliente_publicador,
            topics['condiciones_actuales'],
            datos_enriquecidos,
            nombre_ubicacion
        )
        resultado['condiciones_actuales'] = {'estado': 'exitoso', 'id_mensaje': id_mensaje}
        resultado['exitosos'] += 1
    except (ErrorExtraccionClima, ErrorPublicacionPubSub) as e:
        resultado['condiciones_actuales'] = {'estado': 'fallido', 'error': str(e)}
        resultado['fallidos'] += 1
        logger.error(f"Error condiciones actuales {nombre_ubicacion}: {str(e)}")

    # 2. Pronóstico por Horas (próximas 24 horas)
    try:
        datos = obtener_pronostico_horas(
            ubicacion['latitud'],
            ubicacion['longitud'],
            nombre_ubicacion,
            api_key
        )
        datos_enriquecidos = enriquecer_datos(datos, ubicacion, 'pronostico_horas')
        id_mensaje = publicar_a_pubsub(
            cliente_publicador,
            topics['pronostico_horas'],
            datos_enriquecidos,
            nombre_ubicacion
        )
        resultado['pronostico_horas'] = {'estado': 'exitoso', 'id_mensaje': id_mensaje}
        resultado['exitosos'] += 1
    except (ErrorExtraccionClima, ErrorPublicacionPubSub) as e:
        resultado['pronostico_horas'] = {'estado': 'fallido', 'error': str(e)}
        resultado['fallidos'] += 1
        logger.error(f"Error pronóstico horas {nombre_ubicacion}: {str(e)}")

    # 3. Pronóstico por Días (próximos 5 días)
    try:
        datos = obtener_pronostico_dias(
            ubicacion['latitud'],
            ubicacion['longitud'],
            nombre_ubicacion,
            api_key
        )
        datos_enriquecidos = enriquecer_datos(datos, ubicacion, 'pronostico_dias')
        id_mensaje = publicar_a_pubsub(
            cliente_publicador,
            topics['pronostico_dias'],
            datos_enriquecidos,
            nombre_ubicacion
        )
        resultado['pronostico_dias'] = {'estado': 'exitoso', 'id_mensaje': id_mensaje}
        resultado['exitosos'] += 1
    except (ErrorExtraccionClima, ErrorPublicacionPubSub) as e:
        resultado['pronostico_dias'] = {'estado': 'fallido', 'error': str(e)}
        resultado['fallidos'] += 1
        logger.error(f"Error pronóstico días {nombre_ubicacion}: {str(e)}")

    return resultado


@functions_framework.http
def extraer_clima(solicitud: Request) -> Tuple[Dict[str, Any], int]:
    """
    Cloud Function HTTP principal que extrae datos climáticos y publica a Pub/Sub.

    Esta función es invocada por Cloud Scheduler periódicamente (3x/día) para:
    1. Obtener API Key desde Secret Manager
    2. Para cada ubicación, consultar 3 APIs de Weather:
       - currentConditions: Condiciones actuales
       - forecast/hours: Pronóstico próximas 24 horas
       - forecast/days: Pronóstico próximos 5 días
    3. Enriquecer datos con metadata
    4. Publicar a 3 topics de Pub/Sub diferentes

    Args:
        solicitud: Objeto HTTP request de Cloud Functions

    Returns:
        Tuple[dict, int]: Respuesta JSON y código de estado HTTP
    """
    logger.info("=" * 60)
    logger.info("Snow Alert - Iniciando extracción de datos climáticos")
    logger.info("Extrayendo: Condiciones Actuales + Pronóstico 24h + Pronóstico 5 días")
    logger.info("=" * 60)

    resultados = {
        'estado': 'exitoso',
        'total_ubicaciones': 0,
        'resumen': {
            'condiciones_actuales': {'exitosos': 0, 'fallidos': 0},
            'pronostico_horas': {'exitosos': 0, 'fallidos': 0},
            'pronostico_dias': {'exitosos': 0, 'fallidos': 0}
        },
        'total_mensajes_exitosos': 0,
        'total_mensajes_fallidos': 0,
        'detalles': [],
        'errores': []
    }

    cliente_publicador = None

    try:
        # Validar configuración
        proyecto = ID_PROYECTO
        if not proyecto:
            raise ErrorConfiguracion(
                "ID_PROYECTO no configurado. "
                "Establecer variable de entorno GCP_PROJECT o GOOGLE_CLOUD_PROJECT"
            )

        # Obtener API Key desde Secret Manager
        logger.info("Obteniendo API Key desde Secret Manager...")
        api_key = obtener_api_key()

        # Crear cliente de Pub/Sub
        cliente_publicador = pubsub_v1.PublisherClient()

        logger.info(f"Topics configurados:")
        logger.info(f"  - Condiciones Actuales: {TOPIC_CONDICIONES_ACTUALES}")
        logger.info(f"  - Pronóstico Horas: {TOPIC_PRONOSTICO_HORAS}")
        logger.info(f"  - Pronóstico Días: {TOPIC_PRONOSTICO_DIAS}")

        # Obtener ubicaciones a monitorear
        ubicaciones = obtener_ubicaciones_monitoreo()
        resultados['total_ubicaciones'] = len(ubicaciones)

        logger.info(f"Total de ubicaciones a procesar: {len(ubicaciones)}")
        logger.info(f"Total de llamadas API esperadas: {len(ubicaciones) * 3}")

        # Procesar cada ubicación
        for ubicacion in ubicaciones:
            resultado_ubicacion = procesar_ubicacion(
                ubicacion,
                api_key,
                cliente_publicador,
                proyecto
            )

            # Actualizar contadores
            resultados['total_mensajes_exitosos'] += resultado_ubicacion['exitosos']
            resultados['total_mensajes_fallidos'] += resultado_ubicacion['fallidos']

            # Actualizar resumen por tipo
            for tipo in ['condiciones_actuales', 'pronostico_horas', 'pronostico_dias']:
                if resultado_ubicacion[tipo]['estado'] == 'exitoso':
                    resultados['resumen'][tipo]['exitosos'] += 1
                else:
                    resultados['resumen'][tipo]['fallidos'] += 1
                    resultados['errores'].append({
                        'ubicacion': resultado_ubicacion['ubicacion'],
                        'tipo': tipo,
                        'error': resultado_ubicacion[tipo].get('error', 'Error desconocido')
                    })

            resultados['detalles'].append(resultado_ubicacion)

        # Determinar estado final
        total_esperado = len(ubicaciones) * 3  # 3 APIs por ubicación
        if resultados['total_mensajes_fallidos'] == total_esperado:
            resultados['estado'] = 'fallido'
            codigo_estado = 500
        elif resultados['total_mensajes_fallidos'] > 0:
            resultados['estado'] = 'parcial'
            codigo_estado = 207  # Multi-Status
        else:
            resultados['estado'] = 'exitoso'
            codigo_estado = 200

        logger.info("=" * 60)
        logger.info("Extracción completada:")
        logger.info(f"  Condiciones Actuales: {resultados['resumen']['condiciones_actuales']['exitosos']} exitosos")
        logger.info(f"  Pronóstico Horas: {resultados['resumen']['pronostico_horas']['exitosos']} exitosos")
        logger.info(f"  Pronóstico Días: {resultados['resumen']['pronostico_dias']['exitosos']} exitosos")
        logger.info(f"  Total: {resultados['total_mensajes_exitosos']} exitosos, {resultados['total_mensajes_fallidos']} fallidos")
        logger.info("=" * 60)

        return resultados, codigo_estado

    except ErrorConfiguracion as e:
        logger.error(f"Error de configuración: {str(e)}")
        return {
            'estado': 'fallido',
            'error': str(e),
            'tipo_error': 'configuracion'
        }, 500

    except Exception as e:
        logger.error(f"Error inesperado en extracción: {str(e)}", exc_info=True)
        return {
            'estado': 'fallido',
            'error': f"Error inesperado: {str(e)}",
            'tipo_error': 'desconocido'
        }, 500

    finally:
        if cliente_publicador:
            pass  # Pub/Sub client no necesita close explícito

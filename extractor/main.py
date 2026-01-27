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
NOMBRE_TOPIC = 'clima-datos-crudos'
URL_BASE_API = 'https://weather.googleapis.com/v1/currentConditions:lookup'
NOMBRE_SECRET_API_KEY = 'weather-api-key'

# Ubicaciones a monitorear: Centros de Esquí, Pueblos de Montaña y Destinos de Montañismo
# Cobertura mundial de destinos con nieve y alta montaña
UBICACIONES_MONITOREO = [
    # ========================================================================
    # CENTROS DE ESQUÍ - CHILE
    # ========================================================================
    {
        'nombre': 'Portillo',
        'latitud': -32.8375,
        'longitud': -70.1267,
        'descripcion': 'Portillo, Chile - Centro de Esquí Legendario, Cordillera de Los Andes (2880m)'
    },
    {
        'nombre': 'Valle Nevado',
        'latitud': -33.3558,
        'longitud': -70.2514,
        'descripcion': 'Valle Nevado, Chile - Centro de Esquí más Grande de Sudamérica (3025m)'
    },
    {
        'nombre': 'La Parva',
        'latitud': -33.3319,
        'longitud': -70.2856,
        'descripcion': 'La Parva, Chile - Centro de Esquí Familiar Cordillera Central (2750m)'
    },
    {
        'nombre': 'El Colorado',
        'latitud': -33.3500,
        'longitud': -70.2833,
        'descripcion': 'El Colorado-Farellones, Chile - Centro de Esquí Cercano a Santiago (2430m)'
    },
    {
        'nombre': 'Nevados de Chillán',
        'latitud': -36.9063,
        'longitud': -71.4160,
        'descripcion': 'Nevados de Chillán, Chile - Esquí y Termas en el Sur (1650m)'
    },
    {
        'nombre': 'Corralco',
        'latitud': -38.4833,
        'longitud': -71.5667,
        'descripcion': 'Corralco, Chile - Esquí en el Volcán Lonquimay, La Araucanía (1500m)'
    },
    {
        'nombre': 'Antillanca',
        'latitud': -40.7667,
        'longitud': -72.2000,
        'descripcion': 'Antillanca, Chile - Centro de Esquí Volcán Casablanca, Los Lagos (1350m)'
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


def construir_url_api(latitud: float, longitud: float, api_key: str) -> str:
    """
    Construye la URL completa para la llamada a la Weather API.

    Args:
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        api_key: API Key para autenticación

    Returns:
        str: URL completa con query parameters
    """
    # Construir URL con query parameters
    url = (
        f"{URL_BASE_API}"
        f"?key={api_key}"
        f"&location.latitude={latitud}"
        f"&location.longitude={longitud}"
        f"&languageCode=es"
    )

    return url


def llamar_weather_api(
    latitud: float,
    longitud: float,
    nombre_ubicacion: str,
    api_key: str
) -> Dict[str, Any]:
    """
    Realiza llamada GET a la Google Weather API para obtener condiciones actuales.

    Args:
        latitud: Latitud de la ubicación
        longitud: Longitud de la ubicación
        nombre_ubicacion: Nombre descriptivo de la ubicación
        api_key: API Key para autenticación

    Returns:
        dict: Datos climáticos obtenidos de la API

    Raises:
        ErrorExtraccionClima: Si la llamada a la API falla
    """
    try:
        # Construir URL con query parameters
        url = construir_url_api(latitud, longitud, api_key)

        logger.info(f"Consultando clima para {nombre_ubicacion} ({latitud}, {longitud})")

        # Hacer GET request
        respuesta = requests.get(url, timeout=30)

        if respuesta.status_code != 200:
            mensaje_error = (
                f"Error en API para {nombre_ubicacion}: "
                f"Estado {respuesta.status_code}, Respuesta: {respuesta.text[:500]}"
            )
            logger.error(mensaje_error)
            raise ErrorExtraccionClima(mensaje_error)

        datos_clima = respuesta.json()
        logger.info(f"Datos climáticos obtenidos exitosamente para {nombre_ubicacion}")

        return datos_clima

    except ErrorExtraccionClima:
        raise
    except requests.exceptions.RequestException as e:
        mensaje_error = f"Error de red al llamar API para {nombre_ubicacion}: {str(e)}"
        logger.error(mensaje_error)
        raise ErrorExtraccionClima(mensaje_error)
    except Exception as e:
        mensaje_error = f"Error inesperado al llamar API para {nombre_ubicacion}: {str(e)}"
        logger.error(mensaje_error)
        raise ErrorExtraccionClima(mensaje_error)


def enriquecer_datos_clima(
    datos_clima: Dict[str, Any],
    ubicacion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Enriquece los datos climáticos con metadata adicional.

    Args:
        datos_clima: Datos crudos de la Weather API
        ubicacion: Información de la ubicación monitoreada

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
        'datos_clima_raw': datos_clima,
        'version_extractor': '2.0.0'  # Actualizado a v2 (API Key)
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


@functions_framework.http
def extraer_clima(solicitud: Request) -> Tuple[Dict[str, Any], int]:
    """
    Cloud Function HTTP principal que extrae datos climáticos y publica a Pub/Sub.

    Esta función es invocada por Cloud Scheduler periódicamente para:
    1. Obtener API Key desde Secret Manager
    2. Consultar Weather API para cada ubicación configurada (GET con query params)
    3. Enriquecer datos con metadata
    4. Publicar a Pub/Sub topic 'clima-datos-crudos'

    Args:
        solicitud: Objeto HTTP request de Cloud Functions

    Returns:
        Tuple[dict, int]: Respuesta JSON y código de estado HTTP

    Ejemplo de respuesta exitosa:
        {
            "estado": "exitoso",
            "total_ubicaciones": 3,
            "mensajes_publicados": 3,
            "detalles": [
                {
                    "ubicacion": "Santiago",
                    "estado": "exitoso",
                    "id_mensaje": "123456789"
                }
            ]
        }
    """
    logger.info("=" * 60)
    logger.info("Iniciando extracción de datos climáticos")
    logger.info("=" * 60)

    resultados = {
        'estado': 'exitoso',
        'total_ubicaciones': 0,
        'mensajes_publicados': 0,
        'mensajes_fallidos': 0,
        'detalles': [],
        'errores': []
    }

    cliente_publicador = None
    api_key = None

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
        ruta_topic = cliente_publicador.topic_path(proyecto, NOMBRE_TOPIC)

        logger.info(f"Publicando a topic: {ruta_topic}")

        # Obtener ubicaciones a monitorear
        ubicaciones = obtener_ubicaciones_monitoreo()
        resultados['total_ubicaciones'] = len(ubicaciones)

        logger.info(f"Total de ubicaciones a procesar: {len(ubicaciones)}")

        # Procesar cada ubicación
        for ubicacion in ubicaciones:
            nombre_ubicacion = ubicacion['nombre']
            detalle_ubicacion = {
                'ubicacion': nombre_ubicacion,
                'estado': 'pendiente'
            }

            try:
                # Llamar a Weather API con GET + API Key
                datos_clima = llamar_weather_api(
                    ubicacion['latitud'],
                    ubicacion['longitud'],
                    nombre_ubicacion,
                    api_key
                )

                # Enriquecer datos
                datos_enriquecidos = enriquecer_datos_clima(datos_clima, ubicacion)

                # Publicar a Pub/Sub
                id_mensaje = publicar_a_pubsub(
                    cliente_publicador,
                    ruta_topic,
                    datos_enriquecidos,
                    nombre_ubicacion
                )

                # Registrar éxito
                detalle_ubicacion['estado'] = 'exitoso'
                detalle_ubicacion['id_mensaje'] = id_mensaje
                resultados['mensajes_publicados'] += 1

            except (ErrorExtraccionClima, ErrorPublicacionPubSub) as e:
                # Error específico en esta ubicación
                detalle_ubicacion['estado'] = 'fallido'
                detalle_ubicacion['error'] = str(e)
                resultados['mensajes_fallidos'] += 1
                resultados['errores'].append({
                    'ubicacion': nombre_ubicacion,
                    'error': str(e)
                })
                logger.error(f"Error procesando {nombre_ubicacion}: {str(e)}")

            resultados['detalles'].append(detalle_ubicacion)

        # Determinar estado final
        if resultados['mensajes_fallidos'] == resultados['total_ubicaciones']:
            resultados['estado'] = 'fallido'
            codigo_estado = 500
        elif resultados['mensajes_fallidos'] > 0:
            resultados['estado'] = 'parcial'
            codigo_estado = 207  # Multi-Status
        else:
            resultados['estado'] = 'exitoso'
            codigo_estado = 200

        logger.info("=" * 60)
        logger.info(
            f"Extracción completada: {resultados['mensajes_publicados']} exitosos, "
            f"{resultados['mensajes_fallidos']} fallidos"
        )
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
        # Cerrar cliente si existe
        if cliente_publicador:
            try:
                # Pub/Sub client no necesita close explícito
                pass
            except Exception as e:
                logger.warning(f"Error al finalizar cliente: {str(e)}")

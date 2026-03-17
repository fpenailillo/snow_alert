"""
Módulo de Visualización de Zonas de Avalancha

Genera mapas y renders visuales de las zonas de avalancha para
facilitar su integración en dashboards, reportes y aplicaciones web.

Outputs generados:
1. Imágenes PNG de mapas de zonas (para dashboards y reportes)
2. GeoJSON con polígonos de zonas (para integración web con Leaflet/Mapbox)
3. Thumbnails compactos para vistas rápidas
4. Metadatos de estilo para consistencia visual

Paleta de colores EAWS:
- Zona Inicio: Rojo (#E53935) - peligro alto
- Zona Tránsito: Naranja (#FB8C00) - peligro moderado
- Zona Depósito: Amarillo (#FDD835) - zona de impacto
- Sin clasificar: Gris (#9E9E9E)
"""

import io
import json
import logging
import base64
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

try:
    import ee
    GEE_DISPONIBLE = True
except ImportError:
    GEE_DISPONIBLE = False

try:
    import matplotlib
    matplotlib.use('Agg')  # Backend sin GUI para servidores
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap
    import numpy as np
    MATPLOTLIB_DISPONIBLE = True
except ImportError:
    MATPLOTLIB_DISPONIBLE = False


# Configuración de logging
logger = logging.getLogger(__name__)


# ============================================================================
# PALETA DE COLORES EAWS
# ============================================================================

COLORES_ZONAS = {
    'inicio': '#E53935',      # Rojo - zona de liberación
    'transito': '#FB8C00',    # Naranja - zona de tránsito
    'deposito': '#FDD835',    # Amarillo - zona de depósito
    'sin_clasificar': '#9E9E9E',  # Gris
    'fondo': '#F5F5F5',       # Gris claro para fondo
}

COLORES_RIESGO = {
    'bajo': '#4CAF50',        # Verde
    'medio': '#FFC107',       # Amarillo
    'alto': '#FF5722',        # Naranja oscuro
    'extremo': '#B71C1C',     # Rojo oscuro
}

COLORES_PENDIENTE = {
    'suave': '#81C784',       # Verde claro (0-15°)
    'moderada': '#FFD54F',    # Amarillo (15-30°)
    'pronunciada': '#FF8A65', # Naranja (30-45°)
    'severa': '#E57373',      # Rojo claro (45-60°)
    'extrema': '#C62828',     # Rojo oscuro (>60°)
}


# ============================================================================
# GENERACIÓN DE DATOS GEOJSON
# ============================================================================

def crear_geojson_zonas(
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    radio_metros: float,
    cubicacion: Dict[str, Any],
    indice_dict: Dict[str, Any],
    fecha_analisis: datetime
) -> Dict[str, Any]:
    """
    Crea un GeoJSON con la información de zonas de avalancha.

    El GeoJSON incluye un punto central con todas las propiedades
    y puede ser extendido con polígonos reales si se procesan desde GEE.

    Args:
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud central
        longitud: Longitud central
        radio_metros: Radio del área analizada
        cubicacion: Datos de cubicación
        indice_dict: Datos del índice de riesgo
        fecha_analisis: Fecha del análisis

    Returns:
        Dict: Estructura GeoJSON válida
    """
    # Calcular bounding box aproximado
    # 1 grado ≈ 111km en el ecuador
    delta_lat = radio_metros / 111000
    delta_lon = radio_metros / (111000 * abs(np.cos(np.radians(latitud)))) if MATPLOTLIB_DISPONIBLE else radio_metros / 111000

    geojson = {
        "type": "FeatureCollection",
        "name": f"zonas_avalancha_{nombre_ubicacion.lower().replace(' ', '_')}",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "metadata": {
            "fecha_analisis": fecha_analisis.isoformat(),
            "nombre_ubicacion": nombre_ubicacion,
            "radio_analisis_metros": radio_metros,
            "fuente_dem": "USGS/SRTMGL1_003",
            "resolucion_metros": 30
        },
        "features": [
            # Feature principal: punto central con resumen
            {
                "type": "Feature",
                "properties": {
                    "tipo": "centro_analisis",
                    "nombre": nombre_ubicacion,
                    "indice_riesgo": indice_dict.get('indice_riesgo_topografico', 0),
                    "clasificacion": indice_dict.get('clasificacion_riesgo', 'bajo'),
                    "zona_inicio_ha": cubicacion.get('zona_inicio_ha', 0),
                    "zona_transito_ha": cubicacion.get('zona_transito_ha', 0),
                    "zona_deposito_ha": cubicacion.get('zona_deposito_ha', 0),
                    "pendiente_max": cubicacion.get('pendiente_max_inicio', 0),
                    "desnivel": cubicacion.get('desnivel_inicio_deposito', 0),
                    "peligro_eaws": indice_dict.get('peligro_eaws_base', 1),
                    "descripcion": indice_dict.get('descripcion_riesgo', ''),
                    "estilo": {
                        "color": COLORES_RIESGO.get(
                            indice_dict.get('clasificacion_riesgo', 'bajo'),
                            COLORES_RIESGO['bajo']
                        ),
                        "radio_marcador": 10
                    }
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitud, latitud]
                }
            },
            # Feature: bounding box del área de análisis
            {
                "type": "Feature",
                "properties": {
                    "tipo": "area_analisis",
                    "nombre": f"Área de análisis - {nombre_ubicacion}",
                    "radio_metros": radio_metros,
                    "estilo": {
                        "stroke": True,
                        "color": "#333333",
                        "weight": 2,
                        "opacity": 0.8,
                        "fill": False
                    }
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [longitud - delta_lon, latitud - delta_lat],
                        [longitud + delta_lon, latitud - delta_lat],
                        [longitud + delta_lon, latitud + delta_lat],
                        [longitud - delta_lon, latitud + delta_lat],
                        [longitud - delta_lon, latitud - delta_lat]
                    ]]
                }
            }
        ],
        "style_guide": {
            "colores_zonas": COLORES_ZONAS,
            "colores_riesgo": COLORES_RIESGO,
            "colores_pendiente": COLORES_PENDIENTE
        }
    }

    return geojson


def geojson_a_string(geojson: Dict[str, Any], indent: int = 2) -> str:
    """Convierte GeoJSON a string formateado."""
    return json.dumps(geojson, ensure_ascii=False, indent=indent, default=str)


# ============================================================================
# GENERACIÓN DE IMÁGENES PNG
# ============================================================================

def crear_mapa_zonas_png(
    nombre_ubicacion: str,
    cubicacion: Dict[str, Any],
    indice_dict: Dict[str, Any],
    tamano: Tuple[int, int] = (800, 600),
    dpi: int = 100
) -> Optional[bytes]:
    """
    Crea una imagen PNG con el mapa esquemático de zonas de avalancha.

    Genera un diagrama visual que muestra:
    - Distribución proporcional de zonas (inicio, tránsito, depósito)
    - Estadísticas clave
    - Índice de riesgo con código de colores

    Args:
        nombre_ubicacion: Nombre de la ubicación
        cubicacion: Datos de cubicación
        indice_dict: Datos del índice de riesgo
        tamano: Tamaño en píxeles (ancho, alto)
        dpi: Resolución de la imagen

    Returns:
        bytes: Imagen PNG en bytes, o None si matplotlib no está disponible
    """
    if not MATPLOTLIB_DISPONIBLE:
        logger.warning("matplotlib no disponible, no se puede generar imagen PNG")
        return None

    # Extraer datos
    ha_inicio = cubicacion.get('zona_inicio_ha', 0)
    ha_transito = cubicacion.get('zona_transito_ha', 0)
    ha_deposito = cubicacion.get('zona_deposito_ha', 0)
    ha_total = ha_inicio + ha_transito + ha_deposito

    pct_inicio = cubicacion.get('zona_inicio_pct', 0)
    pct_transito = cubicacion.get('zona_transito_pct', 0)
    pct_deposito = cubicacion.get('zona_deposito_pct', 0)

    indice = indice_dict.get('indice_riesgo_topografico', 0)
    clasificacion = indice_dict.get('clasificacion_riesgo', 'bajo')
    peligro_eaws = indice_dict.get('peligro_eaws_base', 1)

    pendiente_max = cubicacion.get('pendiente_max_inicio', 0)
    desnivel = cubicacion.get('desnivel_inicio_deposito', 0)

    # Crear figura
    fig_width = tamano[0] / dpi
    fig_height = tamano[1] / dpi
    fig, axes = plt.subplots(1, 2, figsize=(fig_width, fig_height), dpi=dpi)

    # Configurar fondo
    fig.patch.set_facecolor('#FAFAFA')

    # ===== Panel izquierdo: Gráfico de torta de zonas =====
    ax1 = axes[0]

    if ha_total > 0:
        sizes = [ha_inicio, ha_transito, ha_deposito]
        labels = [
            f'Inicio\n{ha_inicio:.1f} ha\n({pct_inicio:.0f}%)',
            f'Tránsito\n{ha_transito:.1f} ha\n({pct_transito:.0f}%)',
            f'Depósito\n{ha_deposito:.1f} ha\n({pct_deposito:.0f}%)'
        ]
        colors = [
            COLORES_ZONAS['inicio'],
            COLORES_ZONAS['transito'],
            COLORES_ZONAS['deposito']
        ]

        # Filtrar zonas con área > 0
        datos_filtrados = [(s, l, c) for s, l, c in zip(sizes, labels, colors) if s > 0]
        if datos_filtrados:
            sizes_f, labels_f, colors_f = zip(*datos_filtrados)
            wedges, texts = ax1.pie(
                sizes_f,
                labels=labels_f,
                colors=colors_f,
                startangle=90,
                wedgeprops={'linewidth': 2, 'edgecolor': 'white'}
            )
            for text in texts:
                text.set_fontsize(9)
        else:
            ax1.text(0.5, 0.5, 'Sin datos\nde zonas',
                    ha='center', va='center', fontsize=12)
    else:
        ax1.text(0.5, 0.5, 'Sin datos\nde zonas',
                ha='center', va='center', fontsize=12)

    ax1.set_title('Distribución de Zonas', fontsize=12, fontweight='bold', pad=10)

    # ===== Panel derecho: Indicadores =====
    ax2 = axes[1]
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 10)
    ax2.axis('off')

    # Título del panel
    ax2.text(5, 9.5, 'Indicadores de Riesgo', ha='center', va='top',
             fontsize=12, fontweight='bold')

    # Índice de riesgo (barra grande)
    color_riesgo = COLORES_RIESGO.get(clasificacion, COLORES_RIESGO['bajo'])

    # Barra de fondo
    rect_bg = mpatches.FancyBboxPatch(
        (1, 7), 8, 1.5,
        boxstyle="round,pad=0.05",
        facecolor='#E0E0E0',
        edgecolor='none'
    )
    ax2.add_patch(rect_bg)

    # Barra de progreso
    ancho_barra = (indice / 100) * 8
    rect_fg = mpatches.FancyBboxPatch(
        (1, 7), ancho_barra, 1.5,
        boxstyle="round,pad=0.05",
        facecolor=color_riesgo,
        edgecolor='none'
    )
    ax2.add_patch(rect_fg)

    # Texto del índice
    ax2.text(5, 7.75, f'{indice:.0f}', ha='center', va='center',
             fontsize=20, fontweight='bold', color='white' if indice > 40 else 'black')
    ax2.text(5, 6.5, f'RIESGO {clasificacion.upper()}', ha='center', va='top',
             fontsize=10, fontweight='bold', color=color_riesgo)

    # Estadísticas adicionales
    stats = [
        ('Peligro EAWS', f'Nivel {peligro_eaws}', 5.0),
        ('Pendiente máx.', f'{pendiente_max:.0f}°', 3.5),
        ('Desnivel', f'{desnivel:.0f} m', 2.0),
        ('Área total', f'{ha_total:.1f} ha', 0.5),
    ]

    for label, value, y in stats:
        ax2.text(1.5, y, label, ha='left', va='center', fontsize=9, color='#666666')
        ax2.text(8.5, y, value, ha='right', va='center', fontsize=10, fontweight='bold')

    # Título general
    fig.suptitle(
        f'Análisis de Avalanchas: {nombre_ubicacion}',
        fontsize=14, fontweight='bold', y=0.98
    )

    # Ajustar layout
    plt.tight_layout(rect=[0, 0.02, 1, 0.95])

    # Guardar a bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', facecolor=fig.get_facecolor(),
                edgecolor='none', bbox_inches='tight')
    plt.close(fig)

    buffer.seek(0)
    return buffer.getvalue()


def crear_thumbnail_riesgo(
    nombre_ubicacion: str,
    indice: float,
    clasificacion: str,
    tamano: int = 200,
    dpi: int = 72
) -> Optional[bytes]:
    """
    Crea un thumbnail compacto mostrando solo el índice de riesgo.

    Ideal para vistas de lista o dashboards con muchas ubicaciones.

    Args:
        nombre_ubicacion: Nombre de la ubicación
        indice: Índice de riesgo (0-100)
        clasificacion: Clasificación de riesgo
        tamano: Tamaño del cuadrado en píxeles
        dpi: Resolución

    Returns:
        bytes: Imagen PNG en bytes
    """
    if not MATPLOTLIB_DISPONIBLE:
        return None

    fig_size = tamano / dpi
    fig, ax = plt.subplots(figsize=(fig_size, fig_size), dpi=dpi)

    color = COLORES_RIESGO.get(clasificacion, COLORES_RIESGO['bajo'])

    # Círculo de fondo
    circle = plt.Circle((0.5, 0.5), 0.4, color=color, transform=ax.transAxes)
    ax.add_patch(circle)

    # Índice en el centro
    ax.text(0.5, 0.55, f'{indice:.0f}', ha='center', va='center',
            fontsize=24, fontweight='bold', color='white',
            transform=ax.transAxes)

    # Clasificación abajo
    ax.text(0.5, 0.35, clasificacion.upper()[:4], ha='center', va='center',
            fontsize=8, fontweight='bold', color='white',
            transform=ax.transAxes)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    ax.set_facecolor('#FAFAFA')

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', facecolor='#FAFAFA',
                edgecolor='none', bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)

    buffer.seek(0)
    return buffer.getvalue()


def imagen_a_base64(imagen_bytes: bytes) -> str:
    """Convierte bytes de imagen a string base64 para embeber en HTML/JSON."""
    return base64.b64encode(imagen_bytes).decode('utf-8')


def crear_data_uri(imagen_bytes: bytes, mime_type: str = 'image/png') -> str:
    """Crea un Data URI para embeber imagen directamente en HTML."""
    b64 = imagen_a_base64(imagen_bytes)
    return f'data:{mime_type};base64,{b64}'


# ============================================================================
# EXPORTACIÓN A CLOUD STORAGE
# ============================================================================

def guardar_visualizaciones_gcs(
    cliente_gcs,
    bucket_nombre: str,
    nombre_ubicacion: str,
    fecha_analisis: datetime,
    mapa_png: bytes = None,
    thumbnail_png: bytes = None,
    geojson_data: Dict = None
) -> Dict[str, str]:
    """
    Guarda todas las visualizaciones en Cloud Storage.

    Args:
        cliente_gcs: Cliente de Cloud Storage
        bucket_nombre: Nombre del bucket
        nombre_ubicacion: Nombre de la ubicación
        fecha_analisis: Fecha del análisis
        mapa_png: Imagen PNG del mapa
        thumbnail_png: Thumbnail PNG
        geojson_data: Datos GeoJSON

    Returns:
        Dict: URIs de los archivos guardados
    """
    uris = {}

    # Normalizar nombre
    nombre_norm = nombre_ubicacion.lower().replace(' ', '_').replace('/', '_')
    fecha_str = fecha_analisis.strftime('%Y/%m/%d')
    timestamp_str = fecha_analisis.strftime('%Y%m%d_%H%M%S')

    bucket = cliente_gcs.bucket(bucket_nombre)
    prefijo = f'topografia/visualizaciones/{fecha_str}'

    try:
        # Guardar mapa PNG
        if mapa_png:
            ruta_mapa = f'{prefijo}/{nombre_norm}_mapa_{timestamp_str}.png'
            blob_mapa = bucket.blob(ruta_mapa)
            blob_mapa.upload_from_string(mapa_png, content_type='image/png')
            uris['mapa_png'] = f'gs://{bucket_nombre}/{ruta_mapa}'
            logger.info(f"Mapa guardado: {uris['mapa_png']}")

        # Guardar thumbnail
        if thumbnail_png:
            ruta_thumb = f'{prefijo}/{nombre_norm}_thumb_{timestamp_str}.png'
            blob_thumb = bucket.blob(ruta_thumb)
            blob_thumb.upload_from_string(thumbnail_png, content_type='image/png')
            uris['thumbnail_png'] = f'gs://{bucket_nombre}/{ruta_thumb}'
            logger.info(f"Thumbnail guardado: {uris['thumbnail_png']}")

        # Guardar GeoJSON
        if geojson_data:
            ruta_geojson = f'{prefijo}/{nombre_norm}_zonas_{timestamp_str}.geojson'
            blob_geojson = bucket.blob(ruta_geojson)
            contenido_geojson = geojson_a_string(geojson_data)
            blob_geojson.upload_from_string(
                contenido_geojson,
                content_type='application/geo+json'
            )
            uris['geojson'] = f'gs://{bucket_nombre}/{ruta_geojson}'
            logger.info(f"GeoJSON guardado: {uris['geojson']}")

    except Exception as e:
        logger.error(f"Error guardando visualizaciones: {e}")

    return uris


# ============================================================================
# FUNCIÓN PRINCIPAL DE VISUALIZACIÓN
# ============================================================================

def generar_visualizaciones_completas(
    nombre_ubicacion: str,
    latitud: float,
    longitud: float,
    radio_metros: float,
    cubicacion: Dict[str, Any],
    indice_dict: Dict[str, Any],
    fecha_analisis: datetime
) -> Dict[str, Any]:
    """
    Genera todas las visualizaciones para una ubicación.

    Args:
        nombre_ubicacion: Nombre de la ubicación
        latitud: Latitud
        longitud: Longitud
        radio_metros: Radio del análisis
        cubicacion: Datos de cubicación
        indice_dict: Datos del índice de riesgo
        fecha_analisis: Fecha del análisis

    Returns:
        Dict con:
        - mapa_png: bytes de la imagen del mapa
        - thumbnail_png: bytes del thumbnail
        - geojson: estructura GeoJSON
        - mapa_base64: mapa en base64 para embedding
        - thumbnail_base64: thumbnail en base64
    """
    resultado = {
        'mapa_png': None,
        'thumbnail_png': None,
        'geojson': None,
        'mapa_base64': None,
        'thumbnail_base64': None,
        'mapa_data_uri': None,
        'thumbnail_data_uri': None
    }

    # Generar GeoJSON (siempre disponible)
    resultado['geojson'] = crear_geojson_zonas(
        nombre_ubicacion=nombre_ubicacion,
        latitud=latitud,
        longitud=longitud,
        radio_metros=radio_metros,
        cubicacion=cubicacion,
        indice_dict=indice_dict,
        fecha_analisis=fecha_analisis
    )

    # Generar imágenes si matplotlib está disponible
    if MATPLOTLIB_DISPONIBLE:
        # Mapa completo
        resultado['mapa_png'] = crear_mapa_zonas_png(
            nombre_ubicacion=nombre_ubicacion,
            cubicacion=cubicacion,
            indice_dict=indice_dict
        )
        if resultado['mapa_png']:
            resultado['mapa_base64'] = imagen_a_base64(resultado['mapa_png'])
            resultado['mapa_data_uri'] = crear_data_uri(resultado['mapa_png'])

        # Thumbnail
        indice = indice_dict.get('indice_riesgo_topografico', 0)
        clasificacion = indice_dict.get('clasificacion_riesgo', 'bajo')
        resultado['thumbnail_png'] = crear_thumbnail_riesgo(
            nombre_ubicacion=nombre_ubicacion,
            indice=indice,
            clasificacion=clasificacion
        )
        if resultado['thumbnail_png']:
            resultado['thumbnail_base64'] = imagen_a_base64(resultado['thumbnail_png'])
            resultado['thumbnail_data_uri'] = crear_data_uri(resultado['thumbnail_png'])

    return resultado

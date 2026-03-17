"""
Snow Alert - Analizador Satelital de Zonas Riesgosas en Avalanchas

Este módulo implementa análisis satelital de terreno para identificar, clasificar
y cubicar zonas riesgosas de avalancha usando Google Earth Engine con datos SRTM.

Componentes:
- eaws_constantes: Matriz EAWS 2025 y constantes de terreno
- zonas: Clasificación de zonas funcionales de avalancha
- cubicacion: Cálculo de áreas y estadísticas de terreno
- indice_riesgo: Índice de riesgo topográfico 0-100
- main: Orquestador principal y Cloud Function

Referencias:
- Müller, K., Techel, F., & Mitterer, C. (2025). The EAWS matrix, Part A.
- Techel, F., Müller, K., & Schweizer, J. (2025). The EAWS matrix, Part B.
- Statham, G., et al. (2018). A conceptual model of avalanche hazard.
"""

__version__ = '1.0.0'
__author__ = 'Snow Alert Team'

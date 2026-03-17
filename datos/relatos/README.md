# Relatos de Montañistas

Este directorio contiene los scripts y utilidades para gestionar los relatos de experiencias de montañistas en zonas de avalancha.

## Fuente de Datos

Los relatos provienen de **Andeshandbook** (~4.000 relatos históricos) y se almacenan en BigQuery en la tabla `clima.relatos_montanistas`.

## Carga de Datos

Ver instrucciones en `databricks/02_carga_relatos_bigquery.py` para el proceso de carga desde Databricks.

## Uso

El **SubagenteNLP** (S4 del sistema multi-agente) usa estos relatos para:
- Búsqueda de experiencias históricas por ubicación
- Extracción de patrones de riesgo en lenguaje natural
- Validación contextual del análisis técnico

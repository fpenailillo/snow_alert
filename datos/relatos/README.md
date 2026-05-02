# Relatos de Montañistas

Este directorio contiene los scripts y utilidades para gestionar los relatos de experiencias de montañistas en zonas de avalancha.

## Fuente de Datos

Los relatos provienen de **Andeshandbook** (~4.000 relatos históricos) y se almacenan en BigQuery en la tabla `clima.relatos_montanistas`.

## Carga de Datos

Ver instrucciones en `databricks/02_carga_relatos_bigquery.py` para el proceso de carga desde Databricks.

## Uso

El **AgenteSituationalBriefing** (S4 del sistema multi-agente) usa estos relatos a través del tool `tool_eventos_pasados` para:
- Búsqueda de eventos históricos de avalancha por ubicación
- Contextualización estacional del riesgo
- Enriquecimiento del briefing situacional previo a la clasificación EAWS

> El SubagenteNLP original fue reemplazado por AgenteSituationalBriefing (Qwen3-80B vía Databricks) en la versión v4.0.

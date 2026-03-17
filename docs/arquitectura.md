# Arquitectura del Sistema — Snow Alert

## Visión General

Snow Alert es un sistema multi-agente para predicción de avalanchas sobre GCP.

## Componentes

### Capa de Datos (`datos/`)
Funciones Cloud de GCP que alimentan BigQuery:
- `extractor/` — Extrae condiciones climáticas de la Weather API
- `procesador/` — Procesa condiciones actuales
- `procesador_horas/` — Procesa pronóstico horario
- `procesador_dias/` — Procesa pronóstico diario
- `monitor_satelital/` — Imágenes satelitales (GEE/MODIS/ERA5)
- `analizador_avalanchas/` — Análisis topográfico EAWS

### Sistema Multi-Agente (`agentes/`)
Pipeline de 5 subagentes Claude que generan boletines EAWS:
1. **S1 — Topográfico**: DEM + PINNs (Mohr-Coulomb)
2. **S2 — Satelital**: Imágenes + ViT (self-attention temporal)
3. **S3 — Meteorológico**: Condiciones + ventanas críticas
4. **S4 — NLP Relatos**: Búsqueda semántica en relatos Andeshandbook
5. **S5 — Integrador**: Matriz EAWS + Boletín final

### Tablas BigQuery (`clima.*`)
- `condiciones_actuales`
- `pronostico_horas`
- `pronostico_dias`
- `imagenes_satelitales`
- `zonas_avalancha`
- `relatos_montanistas` ← nueva en Marzo 2026
- `boletines_riesgo` ← nueva en Marzo 2026

## Despliegue

Ver `docs/guia_despliegue.md`.

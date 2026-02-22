# CLAUDE.md - AI Assistant Guide for Snow Alert Project

## Project Overview

**Snow Alert** is a serverless weather and snow monitoring system focused on ski resorts, mountain towns, and popular mountaineering destinations worldwide. Built on Google Cloud Platform (GCP), it uses an event-driven medallion architecture (Bronze/Silver layers) to extract, process, and store:

- **Weather data** from Google Weather API
- **Satellite imagery** from Google Earth Engine (GOES, MODIS, ERA5)
- **Topographic analysis** for avalanche risk assessment

### Primary Purpose
Monitor weather and snow conditions at winter destinations to provide:
- Real-time snow conditions for ski resorts
- Weather alerts for mountain towns
- Climbing/mountaineering weather data for popular peaks
- Satellite-based snow coverage monitoring
- Topographic avalanche risk assessment (EAWS 2025)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD SCHEDULER                                     │
│  • extraer-clima-job (08:00, 14:00, 20:00)                                      │
│  • monitor-satelital-job (08:30, 14:30, 20:30)                                  │
│  • analizar-topografia-job (mensual: día 1 a las 03:00)                         │
└───────┬─────────────────────────────┬─────────────────────────────┬─────────────┘
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────────┐    ┌────────────────────────┐    ┌────────────────────────┐
│  EXTRACTOR CLIMA  │    │  MONITOR SATELITAL     │    │  ANALIZADOR AVALANCHAS │
│  (Weather API)    │    │  (Google Earth Engine) │    │  (GEE + SRTM DEM)      │
│  57 ubicaciones   │    │  57 ubicaciones        │    │  39 ubicaciones        │
└─────────┬─────────┘    └───────────┬────────────┘    └───────────┬────────────┘
          │                          │                             │
    ┌─────┴─────┐                    │                             │
    │  Pub/Sub  │                    │                             │
    │ (3 topics)│                    │                             │
    └─────┬─────┘                    │                             │
          ▼                          ▼                             ▼
┌───────────────────┐    ┌────────────────────────┐    ┌────────────────────────┐
│   PROCESADORES    │    │    DESCARGA GEE        │    │   ANÁLISIS TOPOGRÁFICO │
│ • Condiciones     │    │ • GOES-18/16           │    │ • Zonas inicio/tránsito│
│ • Pronóstico hrs  │    │ • MODIS Terra/Aqua     │    │   /depósito            │
│ • Pronóstico días │    │ • ERA5-Land            │    │ • Índice riesgo EAWS   │
└─────────┬─────────┘    │ • Sentinel-2           │    │ • Cubicación           │
          │              └───────────┬────────────┘    └───────────┬────────────┘
          │                          │                             │
          └──────────────────────────┼─────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
        ┌────────────────────────┐      ┌────────────────────────────────────┐
        │ GCS (Capa Bronce)      │      │ BigQuery (Capa Plata)              │
        │ • condiciones_actuales/│      │ • condiciones_actuales             │
        │ • pronostico_horas/    │      │ • pronostico_horas                 │
        │ • pronostico_dias/     │      │ • pronostico_dias                  │
        │ • satelital/           │      │ • imagenes_satelitales             │
        │ • topografia/          │      │ • zonas_avalancha                  │
        └────────────────────────┘      └────────────────────────────────────┘
```

## Project Structure

```
snow_alert/
├── extractor/                    # Weather data extraction
│   ├── main.py                   # Entry: extraer_clima()
│   ├── requirements.txt
│   └── .gcloudignore
├── procesador/                   # Current conditions processor
│   ├── main.py                   # Entry: procesar_clima()
│   ├── requirements.txt
│   └── .gcloudignore
├── procesador_horas/             # Hourly forecast processor
│   ├── main.py                   # Entry: procesar_pronostico_horas()
│   ├── requirements.txt
│   └── .gcloudignore
├── procesador_dias/              # Daily forecast processor
│   ├── main.py                   # Entry: procesar_pronostico_dias()
│   ├── requirements.txt
│   └── .gcloudignore
├── monitor_satelital/            # Satellite imagery module (GEE)
│   ├── main.py                   # Entry: monitorear_satelital()
│   ├── constantes.py             # GEE collections, bands, vis_params
│   ├── fuentes.py                # Satellite source selection by region
│   ├── productos.py              # Product processing (visual, NDSI, LST)
│   ├── metricas.py               # Metrics for BigQuery
│   ├── descargador.py            # GEE download and GCS upload
│   ├── schema_imagenes_bigquery.json
│   ├── requirements.txt
│   ├── __init__.py
│   └── .gcloudignore
├── analizador_avalanchas/        # Avalanche analysis module (GEE)
│   ├── main.py                   # Entry: analizar_topografia()
│   ├── zonas.py                  # Zone classification (inicio/tránsito/depósito)
│   ├── cubicacion.py             # Volume calculations
│   ├── indice_riesgo.py          # Risk index (EAWS 2025)
│   ├── eaws_constantes.py        # EAWS matrix thresholds
│   ├── visualizacion.py          # PNG maps and GeoJSON generation
│   ├── schema_zonas_bigquery.json
│   ├── requirements.txt
│   ├── __init__.py
│   └── .gcloudignore
├── desplegar.sh                  # Full deployment script
├── README.md                     # Complete documentation
├── CLAUDE.md                     # This file
├── requerimientos.md             # Technical requirements
└── .gitignore
```

## Key Modules

### 1. extractor/main.py
- **Entry point**: `extraer_clima(solicitud: Request)`
- **Trigger**: HTTP (Cloud Scheduler 3x/día: 08:00, 14:00, 20:00)
- **Function**: Calls 3 Google Weather API endpoints for each location
- **Key constants**:
  - `UBICACIONES_MONITOREO` - 57 locations worldwide
  - `HORAS_PRONOSTICO = 76` - Hours ahead (~3 days)
  - `DIAS_PRONOSTICO = 10` - Days ahead (API max)

### 2. procesador/main.py
- **Entry point**: `procesar_clima(evento_nube)`
- **Trigger**: Pub/Sub `clima-datos-crudos`
- **Output**: GCS + BigQuery `condiciones_actuales`

### 3. procesador_horas/main.py
- **Entry point**: `procesar_pronostico_horas(evento_nube)`
- **Trigger**: Pub/Sub `clima-pronostico-horas`
- **Output**: GCS + BigQuery `pronostico_horas` (76 hours)

### 4. procesador_dias/main.py
- **Entry point**: `procesar_pronostico_dias(evento_nube)`
- **Trigger**: Pub/Sub `clima-pronostico-dias`
- **Output**: GCS + BigQuery `pronostico_dias` (10 days, day/night periods)

### 5. monitor_satelital/main.py
- **Entry point**: `monitorear_satelital(solicitud: Request)`
- **Trigger**: HTTP (Cloud Scheduler 3x/día: 08:30, 14:30, 20:30)
- **Function**: Downloads satellite imagery from Google Earth Engine
- **Satellite sources by region**:
  - Americas: GOES-18/16 (sub-daily, 2km)
  - Global: MODIS Terra/Aqua (daily, 500m)
  - Gap-filler: ERA5-Land (hourly, no clouds)
  - Opportunistic: Sentinel-2 (high-res when available)
- **Products generated**:
  - Visual (true color + false color snow)
  - NDSI (Normalized Difference Snow Index)
  - LST (Land Surface Temperature, day/night)
  - ERA5 meteorological data
- **Output**: GCS (GeoTIFF, PNG) + BigQuery `imagenes_satelitales`

### 6. analizador_avalanchas/main.py
- **Entry point**: `analizar_topografia(solicitud: Request)`
- **Trigger**: HTTP (Cloud Scheduler monthly: day 1 at 03:00)
- **Function**: Analyzes terrain for avalanche risk using SRTM DEM
- **Analysis zones (EAWS 2025)**:
  - Zona Inicio (30°-60° slope, convex)
  - Zona Tránsito (15°-30° slope, channeled)
  - Zona Depósito (<15° slope, concave)
- **Metrics calculated**:
  - Area by zone (ha and %)
  - Slope statistics (mean, max, p90)
  - Aspect (predominant direction)
  - Elevation (max, min, desnivel)
  - Risk index and EAWS classification
- **Output**: GCS (JSON, PNG maps, GeoJSON) + BigQuery `zonas_avalancha`

### 7. desplegar.sh
- Automated deployment script for entire infrastructure
- Creates: service accounts, 6 Pub/Sub topics, GCS bucket, 5 BigQuery tables
- Deploys: 6 Cloud Functions
- Configures: 3 Cloud Scheduler jobs

## Coding Conventions

### Language
- **All code is in Spanish**: Variable names, function names, comments, docstrings, error messages
- **Examples**:
  - Variables: `nombre_ubicacion`, `datos_clima`, `marca_tiempo`
  - Functions: `extraer_clima()`, `procesar_mensaje()`, `guardar_datos()`
  - Classes: `ErrorExtraccionClima`, `ErrorAlmacenamientoGCS`
  - Constants: `UBICACIONES_MONITOREO`, `ID_PROYECTO`

### Code Style
- Python 3.11 compatible
- Type hints throughout
- Comprehensive docstrings in Spanish
- Structured logging with `logging` module
- Custom exception classes per module

### Location Data Structure
```python
{
    'nombre': 'Location Name',           # Short name (BigQuery, GCS paths)
    'latitud': -33.3558,                  # Decimal degrees, negative for south
    'longitud': -70.2989,                 # Decimal degrees, negative for west
    'descripcion': 'Full description'     # Descriptive text with context
}
```

## Development Workflow

### Local Testing
```bash
# Weather module
cd extractor && pip install -r requirements.txt
functions-framework --target=extraer_clima --port=8080

# Satellite module (requires GEE auth)
cd monitor_satelital && pip install -r requirements.txt
python main.py --prueba --ubicacion="La Parva Sector Bajo"

# Avalanche module (requires GEE auth)
cd analizador_avalanchas && pip install -r requirements.txt
python main.py --ubicacion="Portillo"
```

### Deployment
```bash
# Full deployment
export ID_PROYECTO="your-gcp-project-id"
./desplegar.sh

# Deploy individual functions
gcloud functions deploy extractor-clima --gen2 --runtime=python311 \
  --source=./extractor --entry-point=extraer_clima --trigger-http

gcloud functions deploy monitor-satelital-nieve --gen2 --runtime=python311 \
  --source=./monitor_satelital --entry-point=monitorear_satelital \
  --trigger-http --memory=2048MB --timeout=540s

gcloud functions deploy analizador-satelital-zonas-riesgosas-avalanchas --gen2 \
  --runtime=python311 --source=./analizador_avalanchas \
  --entry-point=analizar_topografia --trigger-http --memory=1024MB --timeout=540s
```

### Viewing Logs
```bash
gcloud functions logs read extractor-clima --gen2 --limit=50
gcloud functions logs read procesador-clima --gen2 --limit=50
gcloud functions logs read monitor-satelital-nieve --gen2 --limit=50
gcloud functions logs read analizador-satelital-zonas-riesgosas-avalanchas --gen2 --limit=50
```

## GCP Resources

| Resource | Name | Purpose |
|----------|------|---------|
| **Service Account** | `funciones-clima-sa` | IAM identity for functions |
| **Secret** | `weather-api-key` | Google Weather API key |
| **Pub/Sub Topics** | | |
| | `clima-datos-crudos` | Current conditions stream |
| | `clima-datos-dlq` | Dead letter queue (conditions) |
| | `clima-pronostico-horas` | Hourly forecast stream |
| | `clima-pronostico-horas-dlq` | DLQ (hours) |
| | `clima-pronostico-dias` | Daily forecast stream |
| | `clima-pronostico-dias-dlq` | DLQ (days) |
| **GCS Bucket** | `{project}-datos-clima-bronce` | Raw data storage (Bronze) |
| **BigQuery Dataset** | `clima` | Analytics data warehouse |
| **BigQuery Tables** | | |
| | `condiciones_actuales` | Current weather conditions |
| | `pronostico_horas` | Hourly forecast (76h) |
| | `pronostico_dias` | Daily forecast (10 days) |
| | `imagenes_satelitales` | Satellite imagery metadata |
| | `zonas_avalancha` | Avalanche zone analysis |
| **Cloud Functions** | | |
| | `extractor-clima` | HTTP-triggered extraction |
| | `procesador-clima` | Processes current conditions |
| | `procesador-clima-horas` | Processes hourly forecast |
| | `procesador-clima-dias` | Processes daily forecast |
| | `monitor-satelital-nieve` | Downloads satellite imagery |
| | `analizador-satelital-zonas-riesgosas-avalanchas` | Avalanche analysis |
| **Cloud Scheduler** | | |
| | `extraer-clima-job` | 3x/día (08:00, 14:00, 20:00) |
| | `monitor-satelital-job` | 3x/día (08:30, 14:30, 20:30) |
| | `analizar-topografia-job` | Mensual (día 1, 03:00) |

## Important Data Fields

### Current Conditions (`condiciones_actuales`)
- `temperatura`, `sensacion_termica`, `sensacion_viento`
- `velocidad_viento`, `direccion_viento`
- `precipitacion_acumulada`, `probabilidad_precipitacion`
- `cobertura_nubes`, `visibilidad`, `humedad_relativa`
- `condicion_clima`

### Hourly Forecast (`pronostico_horas`)
- `hora_inicio`, `hora_fin`, `es_dia`
- `temperatura`, `prob_precipitacion`, `cantidad_precipitacion`
- Wind, visibility, cloud cover per hour

### Daily Forecast (`pronostico_dias`)
- `fecha_inicio`, `fecha_fin`
- `hora_amanecer`, `hora_atardecer`
- `temp_max_dia`, `temp_min_dia`
- `diurno_*` (15 fields), `nocturno_*` (15 fields)

### Satellite Imagery (`imagenes_satelitales`)
- `nombre_ubicacion`, `latitud`, `longitud`, `region`
- `fecha_captura`, `tipo_captura` (mañana/tarde/noche)
- `fuente_principal` (GOES/MODIS/VIIRS)
- `pct_cobertura_nieve`, `ndsi_medio`, `ndsi_max`
- `lst_dia_celsius`, `lst_noche_celsius`
- `uri_geotiff_*`, `uri_png_*`, `uri_thumbnail_*`

### Avalanche Zones (`zonas_avalancha`)
- `nombre_ubicacion`, `latitud`, `longitud`
- `zona_inicio_ha`, `zona_transito_ha`, `zona_deposito_ha`
- `pendiente_media_inicio`, `pendiente_max_inicio`
- `aspecto_predominante_inicio`
- `indice_riesgo_topografico`, `clasificacion_riesgo`
- `peligro_eaws_base`, `frecuencia_estimada_eaws`

## Common Tasks for AI Assistants

### Adding New Locations
1. Edit `extractor/main.py` - add to `UBICACIONES_MONITOREO`
2. Edit `analizador_avalanchas/main.py` - add to `UBICACIONES_ANALISIS` if has avalanche terrain
3. Include accurate coordinates and Spanish description
4. Redeploy affected functions

### Modifying BigQuery Schema
1. Edit the corresponding `schema_*_bigquery.json` file
2. Update `preparar_fila_bigquery()` or equivalent in the module
3. Update `desplegar.sh` if needed
4. Consider backwards compatibility

### Debugging Failed Messages
```bash
# Check dead letter queues
gcloud pubsub subscriptions pull clima-datos-dlq-sub --limit=10 --auto-ack

# Check function errors
gcloud functions logs read procesador-clima --gen2 --limit=100 | grep ERROR
gcloud functions logs read monitor-satelital-nieve --gen2 --limit=100 | grep ERROR
```

### Changing Scheduler Frequency
```bash
# Weather extraction (current: 3x/day)
gcloud scheduler jobs update http extraer-clima-job --schedule="0 8,14,20 * * *"

# Satellite monitoring (current: 3x/day, 30 min after weather)
gcloud scheduler jobs update http monitor-satelital-job --schedule="30 8,14,20 * * *"

# Avalanche analysis (current: monthly)
gcloud scheduler jobs update http analizar-topografia-job --schedule="0 3 1 * *"
```

## Error Handling

### Custom Exceptions by Module
**extractor/**
- `ErrorExtraccionClima`, `ErrorPublicacionPubSub`, `ErrorConfiguracion`

**procesador/**
- `ErrorValidacionDatos`, `ErrorAlmacenamientoGCS`, `ErrorAlmacenamientoBigQuery`

**monitor_satelital/**
- `ErrorMonitorSatelital`, `ErrorConfiguracionGEE`, `ErrorAlmacenamientoBigQuery`

**analizador_avalanchas/**
- `ErrorAnalisisTopografico`, `ErrorAlmacenamientoBigQuery`, `ErrorAlmacenamientoGCS`

### Retry Behavior
- Pub/Sub automatically retries failed procesador invocations
- After max retries, messages go to DLQ
- GEE downloads have built-in retry with exponential backoff
- Validation errors are NOT retried (prevents poison pill loop)

## Best Practices

1. **Always test locally** before deploying to GCP
2. **Use Spanish naming** to maintain consistency
3. **Log extensively** - GCP logs are your debugging lifeline
4. **Validate data early** - Fail fast on bad data
5. **Keep locations accurate** - Wrong coordinates = wrong weather/satellite data
6. **Monitor the DLQ** - Failed messages indicate problems
7. **GEE quotas** - Use batch processing (10 items, 2s delay) to avoid rate limits

## Snow & Avalanche Considerations

When working with snow/avalanche locations:
- **Elevation matters**: Higher elevations have different weather patterns
- **Wind chill is critical**: `sensacion_viento` is key for ski safety
- **NDSI thresholds**: >0.4 indicates snow, >0.6 indicates dense snow
- **LST**: Critical for snowmelt prediction
- **Slope angles**: 30°-45° is prime avalanche terrain
- **Aspect**: North-facing slopes (S. Hemisphere) retain snow longer
- **EAWS risk levels**: 1 (Low) to 5 (Very High)

## Quick Reference Commands

```bash
# Deploy everything
./desplegar.sh

# Trigger functions manually
curl -X POST $(gcloud functions describe extractor-clima --gen2 --format='value(serviceConfig.uri)')
curl -X POST $(gcloud functions describe monitor-satelital-nieve --gen2 --format='value(serviceConfig.uri)')
curl -X POST $(gcloud functions describe analizador-satelital-zonas-riesgosas-avalanchas --gen2 --format='value(serviceConfig.uri)')

# Query current conditions
bq query --use_legacy_sql=false \
  'SELECT nombre_ubicacion, temperatura, sensacion_viento, velocidad_viento
   FROM clima.condiciones_actuales ORDER BY hora_actual DESC LIMIT 20'

# Query satellite imagery
bq query --use_legacy_sql=false \
  'SELECT nombre_ubicacion, fecha_captura, fuente_principal, pct_cobertura_nieve, ndsi_medio
   FROM clima.imagenes_satelitales ORDER BY fecha_captura DESC LIMIT 20'

# Query avalanche zones
bq query --use_legacy_sql=false \
  'SELECT nombre_ubicacion, zona_inicio_ha, indice_riesgo_topografico, clasificacion_riesgo
   FROM clima.zonas_avalancha ORDER BY indice_riesgo_topografico DESC LIMIT 20'

# Check all function status
gcloud functions describe extractor-clima --gen2
gcloud functions describe monitor-satelital-nieve --gen2
gcloud functions describe analizador-satelital-zonas-riesgosas-avalanchas --gen2

# View logs
gcloud functions logs read extractor-clima --gen2 --limit=20
gcloud functions logs read monitor-satelital-nieve --gen2 --limit=20
gcloud functions logs read analizador-satelital-zonas-riesgosas-avalanchas --gen2 --limit=20

# View scheduler jobs
gcloud scheduler jobs list --location=us-central1
```

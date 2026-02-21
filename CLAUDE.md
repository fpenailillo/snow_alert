# CLAUDE.md - AI Assistant Guide for Snow Alert Project

## Project Overview

**Snow Alert** is a serverless weather monitoring system focused on snow conditions at ski resorts, mountain towns, and popular mountaineering destinations worldwide. Built on Google Cloud Platform (GCP), it uses an event-driven medallion architecture (Bronze/Silver layers) to extract, process, and store weather data.

### Primary Purpose
Monitor weather and snow conditions at winter destinations to provide:
- Real-time snow conditions for ski resorts
- Weather alerts for mountain towns
- Climbing/mountaineering weather data for popular peaks
- Temperature, precipitation, and wind data for snow sports planning

## Architecture

```
┌─────────────────┐
│ Cloud Scheduler │ (3x/día: 08:00, 14:00, 20:00)
└────────┬────────┘
         │ HTTP POST
         ▼
┌────────────────────────────────┐
│ Cloud Function: Extractor      │
│ • Fetches from Weather API     │
│ • API Key from Secret Manager  │
│ • Publishes to Pub/Sub         │
└────────┬───────────────────────┘
         │ Pub/Sub
         ▼
┌────────────────────────────────┐
│ Cloud Function: Procesador     │
│ • Validates & transforms       │
│ • Raw → GCS (Bronze)           │
│ • Clean → BigQuery (Silver)    │
└────────┬───────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌─────────┐  ┌──────────┐
│   GCS   │  │ BigQuery │
│ (Bronze)│  │ (Silver) │
└─────────┘  └──────────┘
```

## Project Structure

```
snow_alert/
├── extractor/
│   ├── main.py              # Data extraction Cloud Function
│   ├── requirements.txt     # Python dependencies
│   └── .gcloudignore
├── procesador/
│   ├── main.py              # Data processing Cloud Function
│   ├── requirements.txt     # Python dependencies
│   └── .gcloudignore
├── desplegar.sh             # Automated deployment script
├── README.md                # Full documentation
├── requerimientos.md        # Technical requirements
├── CLAUDE.md                # This file
└── .gitignore
```

## Key Files

### extractor/main.py
- **Entry point**: `extraer_clima(solicitud: Request)`
- **Trigger**: HTTP (Cloud Scheduler 3x/día: 08:00, 14:00, 20:00)
- **Function**: Calls Google Weather API for each monitored location, enriches data with metadata, publishes to Pub/Sub
- **Key constant**: `UBICACIONES_MONITOREO` - List of locations to monitor

### procesador/main.py
- **Entry point**: `procesar_clima(evento_nube)`
- **Trigger**: Pub/Sub message from `clima-datos-crudos` topic
- **Function**: Validates data, stores raw JSON in GCS (Bronze), transforms and inserts into BigQuery (Silver)

### desplegar.sh
- Automated deployment script for entire infrastructure
- Creates service accounts, Pub/Sub topics, GCS buckets, BigQuery tables
- Deploys both Cloud Functions
- Configures Cloud Scheduler

## Coding Conventions

### Language
- **All code is in Spanish**: Variable names, function names, comments, docstrings, and error messages
- **Examples**:
  - Variables: `nombre_ubicacion`, `datos_clima`, `marca_tiempo`
  - Functions: `extraer_clima()`, `procesar_mensaje()`, `guardar_datos()`
  - Classes: `ErrorExtraccionClima`, `ErrorAlmacenamientoGCS`
  - Constants: `UBICACIONES_MONITOREO`, `ID_PROYECTO`

### Code Style
- Python 3.11 compatible
- Type hints are used throughout
- Comprehensive docstrings in Spanish
- Structured logging with `logging` module
- Custom exception classes for different error types

### Location Data Structure
When adding/modifying locations in `UBICACIONES_MONITOREO`:
```python
{
    'nombre': 'Location Name',           # Short name (used in BigQuery, GCS paths)
    'latitud': -33.3558,                  # Decimal degrees, negative for south
    'longitud': -70.2989,                 # Decimal degrees, negative for west
    'descripcion': 'Full description'     # Descriptive text with context
}
```

## Development Workflow

### Local Testing
```bash
# Install dependencies
cd extractor && pip install -r requirements.txt
cd ../procesador && pip install -r requirements.txt

# Run local function (requires GCP credentials)
functions-framework --target=extraer_clima --port=8080
```

### Deployment
```bash
# Full deployment (creates all resources)
export ID_PROYECTO="your-gcp-project-id"
./desplegar.sh

# Deploy only extractor function
gcloud functions deploy extractor-clima --gen2 \
  --runtime=python311 \
  --source=./extractor \
  --entry-point=extraer_clima \
  --trigger-http

# Deploy only procesador function
gcloud functions deploy procesador-clima --gen2 \
  --runtime=python311 \
  --source=./procesador \
  --entry-point=procesar_clima \
  --trigger-topic=clima-datos-crudos
```

### Viewing Logs
```bash
gcloud functions logs read extractor-clima --gen2 --limit=50
gcloud functions logs read procesador-clima --gen2 --limit=50
```

### Testing Manually
```bash
# Trigger extractor
curl -X POST $(gcloud functions describe extractor-clima --gen2 --format='value(serviceConfig.uri)')

# View BigQuery data
bq query --use_legacy_sql=false 'SELECT * FROM clima.condiciones_actuales ORDER BY hora_actual DESC LIMIT 10'
```

## GCP Resources

| Resource | Name | Purpose |
|----------|------|---------|
| Service Account | `funciones-clima-sa` | IAM identity for functions |
| Secret | `weather-api-key` | Google Weather API key |
| Pub/Sub Topic | `clima-datos-crudos` | Main event stream |
| Pub/Sub Topic | `clima-datos-dlq` | Dead letter queue |
| GCS Bucket | `{project}-datos-clima-bronce` | Raw data storage (Bronze) |
| BigQuery Dataset | `clima` | Analytics data warehouse |
| BigQuery Table | `condiciones_actuales` | Processed weather data (Silver) |
| Cloud Function | `extractor-clima` | HTTP-triggered extraction |
| Cloud Function | `procesador-clima` | Pub/Sub-triggered processing |
| Cloud Scheduler | `extraer-clima-job` | Periodic trigger (3x/día: 08:00, 14:00, 20:00) |

## Important Weather API Fields

The system captures these key weather metrics:
- `temperatura` - Current temperature (°C)
- `sensacion_termica` - Feels-like temperature
- `sensacion_viento` - Wind chill (critical for snow sports)
- `velocidad_viento` / `direccion_viento` - Wind speed and direction
- `precipitacion_acumulada` - Accumulated precipitation
- `probabilidad_precipitacion` - Precipitation probability
- `cobertura_nubes` - Cloud cover percentage
- `visibilidad` - Visibility distance
- `humedad_relativa` - Relative humidity
- `condicion_clima` - Weather condition type

## Common Tasks for AI Assistants

### Adding New Locations
1. Edit `extractor/main.py`
2. Add new location dict to `UBICACIONES_MONITOREO` list
3. Include accurate coordinates (use Google Maps or similar)
4. Provide meaningful Spanish description
5. Redeploy extractor function

### Modifying BigQuery Schema
1. Edit `procesador/main.py` function `transformar_datos_para_bigquery()`
2. Update the schema in `desplegar.sh` if adding new fields
3. Consider backwards compatibility with existing data

### Debugging Failed Messages
```bash
# Check dead letter queue
gcloud pubsub subscriptions pull clima-datos-dlq-sub --limit=10 --auto-ack

# Check function errors
gcloud functions logs read procesador-clima --gen2 --limit=100 | grep ERROR
```

### Changing Scheduler Frequency
```bash
# Schedule actual: 3 veces al día (08:00, 14:00, 20:00)
gcloud scheduler jobs update http extraer-clima-job \
  --schedule="0 8,14,20 * * *"

# Otros ejemplos:
# Cada hora:        "0 * * * *"
# Cada 6 horas:     "0 */6 * * *"
# Una vez al día:   "0 12 * * *"
```

## Error Handling

### Custom Exceptions
- `ErrorExtraccionClima` - Weather API call failures
- `ErrorPublicacionPubSub` - Pub/Sub publishing failures
- `ErrorConfiguracion` - Configuration/setup issues
- `ErrorValidacionDatos` - Data validation failures
- `ErrorAlmacenamientoGCS` - GCS storage failures
- `ErrorAlmacenamientoBigQuery` - BigQuery insertion failures

### Retry Behavior
- Pub/Sub automatically retries failed procesador invocations
- After max retries, messages go to DLQ (`clima-datos-dlq`)
- Validation errors are NOT retried (prevents poison pill loop)

## Best Practices

1. **Always test locally** before deploying to GCP
2. **Use Spanish naming** to maintain consistency
3. **Log extensively** - GCP logs are your debugging lifeline
4. **Validate data early** - Fail fast on bad data
5. **Keep locations accurate** - Wrong coordinates = wrong weather data
6. **Monitor the DLQ** - Failed messages indicate problems

## Snow-Specific Considerations

When working with snow locations:
- **Elevation matters**: Higher elevations have different weather patterns
- **Wind chill is critical**: `sensacion_viento` is key for ski safety
- **Precipitation type**: API returns precipitation but not snow-specific data
- **Visibility**: Important for avalanche conditions and ski operations
- **Cloud cover**: Affects snow quality and sun exposure

## Quick Reference Commands

```bash
# Deploy everything
./desplegar.sh

# View recent data
bq query --use_legacy_sql=false \
  'SELECT nombre_ubicacion, temperatura, sensacion_viento, velocidad_viento
   FROM clima.condiciones_actuales
   ORDER BY hora_actual DESC LIMIT 20'

# Check function status
gcloud functions describe extractor-clima --gen2
gcloud functions describe procesador-clima --gen2

# View scheduler job
gcloud scheduler jobs describe extraer-clima-job
```

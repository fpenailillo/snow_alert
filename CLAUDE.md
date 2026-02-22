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
┌─────────────────────────────────────────────────────────────────┐
│                  Cloud Function: Extractor                       │
│  • Calls 3 Weather API endpoints per location:                   │
│    - currentConditions (condiciones actuales)                    │
│    - forecast/hours (próximas 24 horas)                          │
│    - forecast/days (próximos 5 días)                             │
│  • API Key from Secret Manager                                   │
│  • Publishes to 3 Pub/Sub topics                                 │
└────────┬────────────────────────────────────────────────────────┘
         │ Pub/Sub (3 topics)
    ┌────┴─────────────────────┬─────────────────────────┐
    │                          │                         │
    ▼                          ▼                         ▼
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│clima-datos-    │    │clima-pronostico│    │clima-pronostico│
│crudos (+DLQ)   │    │-horas (+DLQ)   │    │-dias (+DLQ)    │
└───────┬────────┘    └───────┬────────┘    └───────┬────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ Procesador     │    │ Procesador     │    │ Procesador     │
│ (condiciones)  │    │ (horas)        │    │ (días)         │
└───────┬────────┘    └───────┬────────┘    └───────┬────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌────────────────────────┐     ┌────────────────────────────┐
│ GCS (Bronze)           │     │ BigQuery (Silver)          │
│ • condiciones_actuales/│     │ • condiciones_actuales     │
│ • pronostico_horas/    │     │ • pronostico_horas         │
│ • pronostico_dias/     │     │ • pronostico_dias          │
└────────────────────────┘     └────────────────────────────┘
```

## Project Structure

```
snow_alert/
├── extractor/
│   ├── main.py              # Extraction (3 Weather APIs)
│   ├── requirements.txt     # Python dependencies
│   └── .gcloudignore
├── procesador/
│   ├── main.py              # Procesador condiciones actuales
│   ├── requirements.txt     # Python dependencies
│   └── .gcloudignore
├── procesador_horas/
│   ├── main.py              # Procesador pronóstico por horas
│   ├── requirements.txt     # Python dependencies
│   └── .gcloudignore
├── procesador_dias/
│   ├── main.py              # Procesador pronóstico por días
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
- **Function**: Calls 3 Google Weather API endpoints for each location:
  - `currentConditions` → publishes to `clima-datos-crudos`
  - `forecast/hours` → publishes to `clima-pronostico-horas`
  - `forecast/days` → publishes to `clima-pronostico-dias`
- **Key constants**:
  - `UBICACIONES_MONITOREO` - List of 57 locations to monitor
  - `HORAS_PRONOSTICO = 76` - Hours ahead for hourly forecast (~3 days)
  - `DIAS_PRONOSTICO = 10` - Days ahead for daily forecast (API max)

### procesador/main.py
- **Entry point**: `procesar_clima(evento_nube)`
- **Trigger**: Pub/Sub message from `clima-datos-crudos` topic
- **Function**: Processes current conditions → GCS + BigQuery (`condiciones_actuales`)

### procesador_horas/main.py
- **Entry point**: `procesar_pronostico_horas(evento_nube)`
- **Trigger**: Pub/Sub message from `clima-pronostico-horas` topic
- **Function**: Processes hourly forecast (76 hours) → GCS + BigQuery (`pronostico_horas`)

### procesador_dias/main.py
- **Entry point**: `procesar_pronostico_dias(evento_nube)`
- **Trigger**: Pub/Sub message from `clima-pronostico-dias` topic
- **Function**: Processes daily forecast (10 days, with daytime/nighttime periods) → GCS + BigQuery (`pronostico_dias`)

### desplegar.sh
- Automated deployment script for entire infrastructure
- Creates service accounts, 6 Pub/Sub topics (3 main + 3 DLQ), GCS bucket, 3 BigQuery tables
- Deploys 4 Cloud Functions (1 extractor + 3 processors)
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
| Pub/Sub Topic | `clima-datos-crudos` | Current conditions stream |
| Pub/Sub Topic | `clima-datos-dlq` | Dead letter queue (conditions) |
| Pub/Sub Topic | `clima-pronostico-horas` | Hourly forecast stream |
| Pub/Sub Topic | `clima-pronostico-horas-dlq` | Dead letter queue (hours) |
| Pub/Sub Topic | `clima-pronostico-dias` | Daily forecast stream |
| Pub/Sub Topic | `clima-pronostico-dias-dlq` | Dead letter queue (days) |
| GCS Bucket | `{project}-datos-clima-bronce` | Raw data storage (Bronze) |
| BigQuery Dataset | `clima` | Analytics data warehouse |
| BigQuery Table | `condiciones_actuales` | Current weather conditions |
| BigQuery Table | `pronostico_horas` | Hourly forecast (76h) |
| BigQuery Table | `pronostico_dias` | Daily forecast (10 days) |
| Cloud Function | `extractor-clima` | HTTP-triggered extraction (3 APIs) |
| Cloud Function | `procesador-clima` | Processes current conditions |
| Cloud Function | `procesador-clima-horas` | Processes hourly forecast |
| Cloud Function | `procesador-clima-dias` | Processes daily forecast |
| Cloud Scheduler | `extraer-clima-job` | Periodic trigger (3x/día: 08:00, 14:00, 20:00) |

## Important Weather API Fields

### Current Conditions (`condiciones_actuales`)
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

### Hourly Forecast (`pronostico_horas`)
- `hora_inicio` / `hora_fin` - Forecast time interval
- `temperatura` - Forecasted temperature
- `prob_precipitacion` - Precipitation probability
- `cantidad_precipitacion` - Expected precipitation amount
- `es_dia` - Is daytime (boolean)
- All standard weather metrics per hour

### Daily Forecast (`pronostico_dias`)
- `fecha_inicio` / `fecha_fin` - Forecast date range
- `hora_amanecer` / `hora_atardecer` - Sunrise/sunset times
- `temp_max_dia` / `temp_min_dia` - Daily temperature range
- `diurno_*` - Daytime period metrics (15 fields)
- `nocturno_*` - Nighttime period metrics (15 fields)

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

# View current conditions
bq query --use_legacy_sql=false \
  'SELECT nombre_ubicacion, temperatura, sensacion_viento, velocidad_viento
   FROM clima.condiciones_actuales
   ORDER BY hora_actual DESC LIMIT 20'

# View hourly forecast
bq query --use_legacy_sql=false \
  'SELECT nombre_ubicacion, hora_inicio, temperatura, prob_precipitacion
   FROM clima.pronostico_horas
   ORDER BY hora_inicio DESC LIMIT 20'

# View daily forecast
bq query --use_legacy_sql=false \
  'SELECT nombre_ubicacion, fecha_inicio, temp_max_dia, temp_min_dia,
          diurno_condicion, nocturno_condicion
   FROM clima.pronostico_dias
   ORDER BY fecha_inicio DESC LIMIT 20'

# Check all function status
gcloud functions describe extractor-clima --gen2
gcloud functions describe procesador-clima --gen2
gcloud functions describe procesador-clima-horas --gen2
gcloud functions describe procesador-clima-dias --gen2

# View logs for all functions
gcloud functions logs read extractor-clima --gen2 --limit=20
gcloud functions logs read procesador-clima --gen2 --limit=20
gcloud functions logs read procesador-clima-horas --gen2 --limit=20
gcloud functions logs read procesador-clima-dias --gen2 --limit=20

# View scheduler job
gcloud scheduler jobs describe extraer-clima-job
```

# Snow Alert - Sistema de Monitoreo de Condiciones de Nieve

Sistema serverless event-driven para el monitoreo de condiciones climáticas y de nieve en centros de esquí, pueblos de montaña y destinos de montañismo a nivel mundial, utilizando la Google Weather API y servicios de Google Cloud Platform.

## Descripción

**Snow Alert** es un proyecto que implementa una arquitectura moderna de datos meteorológicos basada en eventos, especializado en destinos de nieve y alta montaña:

- **Extrae** datos climáticos de la Google Weather API para centros de esquí, pueblos de montaña y bases de montañismo
- **Procesa** los datos de forma asíncrona usando Pub/Sub como bus de mensajes
- **Almacena** los datos en una arquitectura medallion:
  - **Capa Bronce** (Cloud Storage): Datos crudos sin transformar
  - **Capa Plata** (BigQuery): Datos limpios y estructurados para análisis
- **Orquesta** la extracción periódica mediante Cloud Scheduler

### Casos de Uso
- Monitoreo de condiciones para esquí y snowboard
- Alertas de clima para expediciones de montañismo
- Seguimiento de temperaturas y viento para deportes de invierno
- Análisis histórico de condiciones climáticas en alta montaña

## Arquitectura

```
┌─────────────────┐
│ Cloud Scheduler │ (Cada minuto)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ Cloud Function: Extractor   │
│ • Llama a Weather API       │
│ • API Key authentication    │
│ • Publica a Pub/Sub         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Pub/Sub Topic               │
│ • clima-datos-crudos        │
│ • Dead Letter Queue         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Cloud Function: Procesador  │
│ • Procesa mensajes Pub/Sub  │
│ • Valida y transforma datos │
└────────┬────────────────────┘
         │
         ├──────────────────────┐
         ▼                      ▼
┌──────────────────┐   ┌──────────────────┐
│ Cloud Storage    │   │ BigQuery         │
│ (Capa Bronce)    │   │ (Capa Plata)     │
│ • Datos crudos   │   │ • Datos          │
│ • Particionado   │   │   estructurados  │
│   por fecha      │   │ • Particionado   │
│ • Versionado     │   │ • Clustering     │
└──────────────────┘   └──────────────────┘
```



## Ubicaciones Monitoreadas

El sistema monitorea **57 ubicaciones** de destinos de nieve y montaña a nivel mundial, organizadas en las siguientes categorías:

### Centros de Esquí - Chile (19 ubicaciones — cobertura completa de norte a sur)

**Región de Valparaíso**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Portillo** | -32.8369 | -70.1287 | 2580m / 3310m | Centro Legendario, Los Andes |
| **Ski Arpa** | -32.6000 | -70.3900 | 2690m / 3740m | Único Cat-Ski de Chile, 4000 acres |

**Región Metropolitana**
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **La Parva — Sector Bajo** | -33.3630 | -70.3010 | 2650m | Villa La Parva, base, lodges, ski school |
| **La Parva — Sector Medio** | -33.3520 | -70.2900 | 3100m | Restaurante 3100, servicios de montaña |
| **La Parva — Sector Alto** | -33.3440 | -70.2800 | 3574m | Cima, terreno experto, La Chimenea |
| **El Colorado / Farellones** | -33.3600 | -70.3000 | 2350m / 3460m | Mayor nº de pistas del Tres Valles |
| **Valle Nevado** | -33.3547 | -70.2498 | 2860m / 3670m | Mayor Centro de Esquí de Sudamérica |
| **Lagunillas** | -33.6800 | -70.2500 | 2200m / 2550m | Centro familiar, San José de Maipo |

**Región de O'Higgins**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Chapa Verde** | -34.1700 | -70.3700 | 2260m / 3050m | Centro CODELCO, acceso restringido |

**Región de Ñuble / Biobío**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Nevados de Chillán** | -36.8580 | -71.3727 | 1530m / 2400m | Volcán activo, termas y tree skiing |
| **Antuco** | -37.4100 | -71.4200 | 1400m / 1850m | Volcán Antuco, Los Ángeles |

**Región de La Araucanía**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Corralco** | -38.3700 | -71.5700 | 1550m / 2400m | Volcán Lonquimay, bosques de araucarias |
| **Las Araucarias / Llaima** | -38.7300 | -71.7400 | 1550m / 1942m | Volcán Llaima |
| **Ski Pucón / Pillán** | -39.5000 | -71.9600 | 1380m / 2100m | Volcán Villarrica (activo) |
| **Los Arenales** | -38.8500 | -72.0000 | 1600m / 1845m | Centro entrenamiento, Temuco |

**Región de Los Lagos**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Antillanca** | -40.7756 | -72.2046 | 1040m / 1540m | Volcán Casablanca, Parque Puyehue |
| **Volcán Osorno** | -41.1000 | -72.5000 | 1230m / 1760m | Volcán icónico, Puerto Varas |

**Región de Aysén**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **El Fraile** | -45.6800 | -71.9400 | 980m / 1280m | Bosques de Lenga, Coyhaique |

**Región de Magallanes**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Cerro Mirador** | -53.1300 | -70.9800 | 380m / 570m | Centro más austral del mundo |

### Centros de Esquí - Argentina (5)
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **Cerro Catedral** | -41.1667 | -71.4500 | 2100m | Mayor Centro de Esquí de Sudamérica |
| **Las Leñas** | -35.1500 | -70.0833 | 3430m | Esquí de Alta Montaña y Freeride |
| **Chapelco** | -40.1500 | -71.2500 | 1980m | Esquí Patagónico |
| **Cerro Castor** | -54.7500 | -68.3333 | 1057m | Centro más Austral del Mundo |
| **Cerro Bayo** | -40.7167 | -71.5167 | 1780m | Esquí Boutique Patagonia |

### Centros de Esquí - Europa/Alpes (7)
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **Chamonix** | 45.9237 | 6.8694 | 1035m | Capital Mundial del Alpinismo |
| **Zermatt** | 46.0207 | 7.7491 | 1608m | Vista al Matterhorn |
| **St. Moritz** | 46.4908 | 9.8355 | 1822m | Turismo de Invierno de Lujo |
| **Verbier** | 46.0964 | 7.2286 | 1500m | Freeride y Alta Montaña |
| **Courchevel** | 45.4154 | 6.6347 | 1850m | Les 3 Vallées |
| **Val Thorens** | 45.2981 | 6.5797 | 2300m | Estación más Alta de Europa |
| **Cortina d'Ampezzo** | 46.5369 | 12.1356 | 1224m | Reina de las Dolomitas |

### Centros de Esquí - Norteamérica (6)
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **Vail** | 39.6403 | -106.3742 | 2476m | Legendario Resort de Colorado |
| **Aspen** | 39.1911 | -106.8175 | 2438m | Icono del Esquí de Lujo |
| **Jackson Hole** | 43.5875 | -110.8278 | 1924m | Esquí Extremo, Wyoming |
| **Whistler** | 50.1163 | -122.9574 | 675m | Mayor Resort de Norteamérica |
| **Park City** | 40.6461 | -111.4980 | 2103m | Mayor Resort de USA |
| **Mammoth Mountain** | 37.6308 | -119.0326 | 2424m | Sierra Nevada, California |

### Centros de Esquí - Oceanía y Asia (3)
| Ubicación | Latitud | Longitud | Descripción |
|-----------|---------|----------|-------------|
| **Queenstown** | -45.0312 | 168.6626 | Capital de la Aventura, Nueva Zelanda |
| **Niseko** | 42.8048 | 140.6874 | Mejor Nieve Polvo del Mundo, Japón |
| **Hakuba** | 36.6983 | 137.8619 | Alpes Japoneses, Sede Nagano 1998 |

### Pueblos de Montaña (7)
| Ubicación | Latitud | Longitud | Descripción |
|-----------|---------|----------|-------------|
| **Bariloche** | -41.1335 | -71.3103 | Suiza de Sudamérica, Argentina |
| **Ushuaia** | -54.8019 | -68.3030 | Fin del Mundo, Argentina |
| **Pucón** | -39.2819 | -71.9755 | Volcán Villarrica, Chile |
| **San Martín de los Andes** | -40.1575 | -71.3522 | Patagonia Argentina |
| **Innsbruck** | 47.2692 | 11.4041 | Capital del Tirol, Austria |
| **Interlaken** | 46.6863 | 7.8632 | Portal a Jungfrau, Suiza |
| **Banff** | 51.1784 | -115.5708 | Rockies Canadienses |

### Bases de Montañismo - Alta Montaña (8)
| Ubicación | Latitud | Longitud | Elevación | Montaña |
|-----------|---------|----------|-----------|---------|
| **Plaza de Mulas** | -32.6500 | -70.0167 | 4370m | Aconcagua (Techo de América) |
| **Everest Base Camp** | 28.0025 | 86.8528 | 5364m | Monte Everest |
| **Chamonix Mont Blanc** | 45.8326 | 6.8652 | 3817m | Mont Blanc |
| **Denali Base** | 63.0692 | -151.0070 | - | Denali/McKinley |
| **Torres del Paine** | -50.9423 | -72.9682 | - | Patagonia Chilena |
| **Kilimanjaro Gate** | -3.0674 | 37.3556 | 1800m | Kilimanjaro |
| **Monte Fitz Roy** | -49.2714 | -72.9411 | - | Fitz Roy, El Chaltén |
| **Matterhorn Zermatt** | 45.9766 | 7.6586 | 3260m | Matterhorn/Cervino |

## Características Técnicas

### Cloud Function: Extractor

- **Trigger**: HTTP (invocado por Cloud Scheduler)
- **Runtime**: Python 3.11
- **Memoria**: 256 MB
- **Timeout**: 60 segundos
- **Funcionalidades**:
  - Autenticación con API Key desde Secret Manager
  - Llamadas GET a Weather API para múltiples ubicaciones
  - Enriquecimiento de datos con metadata
  - Publicación a Pub/Sub con atributos para routing
  - Manejo robusto de errores y logging estructurado

### Cloud Function: Procesador

- **Trigger**: Pub/Sub (topic: clima-datos-crudos)
- **Runtime**: Python 3.11
- **Memoria**: 512 MB
- **Timeout**: 120 segundos
- **Funcionalidades**:
  - Decodificación y validación de mensajes
  - Almacenamiento de datos crudos en Cloud Storage
  - Transformación a esquema estructurado
  - Inserción en BigQuery
  - Reintentos automáticos con exponential backoff
  - Dead letter queue para mensajes fallidos

### Cloud Storage (Capa Bronce)

- **Estructura de particiones**: `{ubicacion}/{AAAA}/{MM}/{DD}/{timestamp}.json`
- **Versionado**: Habilitado
- **Ciclo de vida**:
  - 0-30 días: Standard
  - 30-90 días: Nearline
  - 90-365 días: Coldline
  - 365+ días: Eliminación automática

### BigQuery (Capa Plata)

- **Dataset**: `clima`
- **Tabla**: `condiciones_actuales`
- **Particionamiento**: Por `DATE(hora_actual)`
- **Clustering**: Por `nombre_ubicacion`
- **Esquema** (27 campos):
  - Identificación: ubicación, coordenadas
  - Temporal: hora, zona horaria
  - Temperatura: actual, sensación térmica, punto de rocío, índice de calor
  - Condiciones: descripción, código
  - Precipitación: probabilidad, acumulación
  - Viento: velocidad, dirección, sensación de viento
  - Atmosféricas: presión, humedad, visibilidad
  - Otras: índice UV, cobertura de nubes, probabilidad de tormenta
  - Metadata: timestamp de ingesta, URI datos crudos, JSON completo

## Requisitos Previos

### Software Necesario

- **Google Cloud SDK** (gcloud CLI) versión 400+
- **Python** 3.11+
- **Git** para control de versiones

### Cuenta de Google Cloud

1. Proyecto de GCP activo
2. Facturación habilitada
3. Permisos necesarios:
   - Editor de proyecto o roles específicos:
     - Cloud Functions Admin
     - Pub/Sub Admin
     - Storage Admin
     - BigQuery Admin
     - Service Account Admin
     - Cloud Scheduler Admin

### APIs Requeridas

Las siguientes APIs deben estar habilitadas (el script de despliegue las habilita automáticamente):

- Cloud Functions API
- Cloud Build API
- Cloud Scheduler API
- Pub/Sub API
- Cloud Storage API
- BigQuery API
- Cloud Logging API
- Cloud Run API
- Secret Manager API
- Weather API

### Weather API Key

**IMPORTANTE**: Necesitas una API Key con acceso a la Weather API:

1. Ve a [Google Cloud Console - API Credentials](https://console.cloud.google.com/apis/credentials)
2. Crea una API Key o usa una existente
3. Asegúrate de que la API Key tenga acceso a `weather.googleapis.com`
4. Durante el despliegue, se te solicitará agregar esta API Key a Secret Manager

## Configuración

### 1. Clonar el Repositorio

```bash
git clone https://github.com/fpenailillo/snow_alert
cd snow_alert
```

### 2. Configurar Variables de Entorno

```bash
export ID_PROYECTO="climas-chileno"
export REGION="us-central1"
```

### 3. Autenticación con GCP

```bash
# Autenticarse con cuenta de GCP
gcloud auth login

# Configurar proyecto
gcloud config set project $ID_PROYECTO

# Configurar credenciales para Application Default Credentials
gcloud auth application-default login

gcloud auth list
gcloud config list project

```

## Despliegue

### Opción 1: Script Automatizado (Recomendado)

El script `desplegar.sh` despliega toda la infraestructura automáticamente:

```bash
./desplegar.sh [ID_PROYECTO] [REGION]
```

Ejemplo:

```bash
./desplegar.sh climas-chileno us-central1
```

El script realiza las siguientes acciones:

1. ✓ Valida dependencias
2. ✓ Habilita APIs necesarias (incluyendo Weather API y Secret Manager)
3. ✓ Crea cuenta de servicio y asigna permisos
4. ✓ Configura Secret Manager para Weather API Key
5. ✓ Crea topics de Pub/Sub (principal y DLQ)
6. ✓ Crea bucket de Cloud Storage con ciclo de vida
7. ✓ Crea dataset y tabla de BigQuery
8. ✓ Despliega Cloud Function Extractor
9. ✓ Despliega Cloud Function Procesador
10. ✓ Configura Cloud Scheduler (ejecución cada minuto)

**Tiempo estimado**: 5-10 minutos

**Nota**: El script pausará para que agregues tu Weather API Key a Secret Manager. Sigue las instrucciones en pantalla.

### Opción 2: Despliegue Manual

#### 2.1 Crear Topics de Pub/Sub

```bash
gcloud pubsub topics create clima-datos-crudos --project=$ID_PROYECTO
gcloud pubsub topics create clima-datos-dlq --project=$ID_PROYECTO
```

#### 2.2 Crear Bucket de Cloud Storage

```bash
gsutil mb -p $ID_PROYECTO -l $REGION gs://${ID_PROYECTO}-datos-clima-bronce
gsutil versioning set on gs://${ID_PROYECTO}-datos-clima-bronce
```

#### 2.3 Crear Dataset y Tabla de BigQuery

```bash
# Crear dataset
bq mk --project_id=$ID_PROYECTO --location=$REGION clima

# Crear tabla (el schema completo se crea automáticamente con desplegar.sh)
# Aquí se muestra solo la estructura básica
bq mk --project_id=$ID_PROYECTO \
  --table \
  --time_partitioning_field=hora_actual \
  --time_partitioning_type=DAY \
  --clustering_fields=nombre_ubicacion \
  clima.condiciones_actuales
```

#### 2.4 Desplegar Cloud Functions

```bash
# Extractor
gcloud functions deploy extractor-clima \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=./extractor \
  --entry-point=extraer_clima \
  --trigger-http \
  --set-env-vars=GCP_PROJECT=$ID_PROYECTO

# Procesador
gcloud functions deploy procesador-clima \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=./procesador \
  --entry-point=procesar_clima \
  --trigger-topic=clima-datos-crudos \
  --set-env-vars=GCP_PROJECT=$ID_PROYECTO
```

#### 2.5 Configurar Cloud Scheduler

```bash
# Obtener URL del extractor
URL_EXTRACTOR=$(gcloud functions describe extractor-clima \
  --gen2 --region=$REGION --format='value(serviceConfig.uri)')

# Crear job
gcloud scheduler jobs create http extraer-clima-job \
  --location=$REGION \
  --schedule="0 * * * *" \
  --uri=$URL_EXTRACTOR \
  --http-method=POST
```

## Verificar Despliegue

Después del despliegue, verifica que todo funcione correctamente:

```bash
# 1. Ejecutar el scheduler manualmente
gcloud scheduler jobs run extraer-clima-job --location=us-central1

# 2. Esperar 60 segundos para que los mensajes se procesen
sleep 60

# 3. Verificar datos en BigQuery
bq query --use_legacy_sql=false \
  "SELECT nombre_ubicacion, temperatura, descripcion_clima, hora_actual
   FROM clima.condiciones_actuales
   ORDER BY hora_actual DESC
   LIMIT 5"

# 4. Verificar archivos en Cloud Storage
gsutil ls gs://climas-chileno-datos-clima-bronce/**/*.json | head -10
```

## Uso

### Ejecución Manual

Para probar el sistema manualmente con autenticación:

```bash
# Obtener URL del extractor
URL_EXTRACTOR=$(gcloud functions describe extractor-clima \
  --gen2 --region=$REGION --format='value(serviceConfig.uri)')

# Ejecutar extractor con autenticación
curl -X POST $URL_EXTRACTOR \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

### Ejecución Programada

Cloud Scheduler ejecuta automáticamente el extractor cada minuto según la configuración:

- **Frecuencia**: `* * * * *` (cada minuto)
- **Zona horaria**: America/Santiago
- **Reintentos**: Hasta 3 intentos con backoff exponencial

### Ver Logs

```bash
# Logs del extractor
gcloud functions logs read extractor-clima --gen2 --region=$REGION --limit=50

# Logs del procesador
gcloud functions logs read procesador-clima --gen2 --region=$REGION --limit=50

# Logs en tiempo real
gcloud functions logs read extractor-clima --gen2 --region=$REGION --tail
```

### Consultar Datos en BigQuery

#### Últimas 10 mediciones

```sql
SELECT
  nombre_ubicacion,
  hora_actual,
  temperatura,
  descripcion_clima,
  humedad_relativa,
  velocidad_viento
FROM
  `clima.condiciones_actuales`
ORDER BY
  hora_actual DESC
LIMIT 10;
```

#### Promedio de temperatura por ubicación (últimas 24 horas)

```sql
SELECT
  nombre_ubicacion,
  AVG(temperatura) AS temperatura_promedio,
  MIN(temperatura) AS temperatura_minima,
  MAX(temperatura) AS temperatura_maxima,
  COUNT(*) AS total_mediciones
FROM
  `clima.condiciones_actuales`
WHERE
  hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY
  nombre_ubicacion
ORDER BY
  nombre_ubicacion;
```

#### Condiciones climáticas más frecuentes

```sql
SELECT
  nombre_ubicacion,
  descripcion_clima,
  COUNT(*) AS frecuencia
FROM
  `clima.condiciones_actuales`
WHERE
  descripcion_clima IS NOT NULL
  AND hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY
  nombre_ubicacion,
  descripcion_clima
ORDER BY
  nombre_ubicacion,
  frecuencia DESC;
```

#### Condiciones actuales para esquí (sensación de viento y temperatura)

```sql
SELECT
  nombre_ubicacion,
  temperatura,
  sensacion_viento AS wind_chill,
  velocidad_viento,
  humedad_relativa,
  descripcion_clima,
  hora_actual
FROM
  `clima.condiciones_actuales`
WHERE
  hora_actual = (SELECT MAX(hora_actual) FROM `clima.condiciones_actuales`)
  AND nombre_ubicacion IN ('Valle Nevado', 'Portillo', 'Cerro Catedral', 'Vail', 'Chamonix')
ORDER BY
  temperatura ASC;
```

#### Comparación de temperaturas por región de esquí

```sql
WITH ultima_hora AS (
  SELECT MAX(hora_actual) AS max_hora
  FROM `clima.condiciones_actuales`
)
SELECT
  CASE
    WHEN longitud BETWEEN -75 AND -65 THEN 'Sudamérica (Chile/Argentina)'
    WHEN longitud BETWEEN -130 AND -100 THEN 'Norteamérica'
    WHEN longitud BETWEEN 0 AND 20 THEN 'Alpes Europeos'
    WHEN longitud > 100 THEN 'Asia/Oceanía'
    ELSE 'Otras Regiones'
  END AS region_esqui,
  COUNT(DISTINCT nombre_ubicacion) AS centros,
  ROUND(AVG(temperatura), 1) AS temp_promedio,
  ROUND(MIN(temperatura), 1) AS temp_minima,
  ROUND(MAX(temperatura), 1) AS temp_maxima,
  ROUND(AVG(velocidad_viento), 1) AS viento_promedio
FROM
  `clima.condiciones_actuales`
CROSS JOIN
  ultima_hora
WHERE
  hora_actual = ultima_hora.max_hora
GROUP BY
  region_esqui
ORDER BY
  temp_promedio ASC;
```

#### Alertas de viento fuerte para montañismo

```sql
SELECT
  nombre_ubicacion,
  temperatura,
  sensacion_viento,
  velocidad_viento,
  direccion_viento,
  descripcion_clima,
  hora_actual
FROM
  `clima.condiciones_actuales`
WHERE
  hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
  AND velocidad_viento > 50  -- km/h
ORDER BY
  velocidad_viento DESC;
```

### Explorar Datos Crudos en Cloud Storage

```bash
# Listar archivos recientes
gsutil ls -l gs://${ID_PROYECTO}-datos-clima-bronce/santiago/$(date +%Y)

# Descargar un archivo
gsutil cp gs://${ID_PROYECTO}-datos-clima-bronce/santiago/2024/01/15/20240115_120000.json .

# Ver contenido
cat 20240115_120000.json | jq .
```

## Monitoreo y Alertas

### Métricas Importantes

1. **Cloud Functions**:
   - Tasa de invocaciones
   - Tasa de errores
   - Duración de ejecución
   - Memoria utilizada

2. **Pub/Sub**:
   - Mensajes publicados/procesados
   - Mensajes no confirmados
   - Mensajes en DLQ

3. **BigQuery**:
   - Filas insertadas
   - Bytes procesados
   - Errores de inserción

### Configurar Alertas

Crear alertas en Cloud Monitoring para:

```bash
# Tasa de errores alta en Cloud Functions (>5%)
# Mensajes acumulados en DLQ (>10)
# Falta de datos nuevos en BigQuery (>2 horas sin inserts)
```

Ver [documentación de Cloud Monitoring](https://cloud.google.com/monitoring/docs) para configuración detallada.

## Costos Estimados

Estimación mensual para **57 ubicaciones** con ejecución **cada minuto** (43,200 invocaciones/mes):

| Servicio | Uso | Costo Estimado (USD) |
|----------|-----|----------------------|
| Cloud Functions | 86,400 invocaciones (2 funciones × 43,200) | Gratis (tier: 2M/mes) |
| Pub/Sub | ~2,462,400 mensajes (57 ubicaciones × 43,200) | Gratis (tier: 10 GB/mes) |
| Cloud Storage | ~4.9 GB/mes (2,462,400 archivos JSON × 2 KB) | $0.10 |
| BigQuery | ~15 GB almacenado/mes | $0.30 |
| BigQuery | ~20 GB queries/mes | Gratis (tier: 1 TB/mes) |
| Cloud Scheduler | 1 job | $0.10 |
| Secret Manager | 1 secret, ~43,200 accesos/mes | $0.13 |
| **TOTAL** | | **~$0.63/mes** |

**Nota**:
- Los costos son aproximados y pueden variar según el uso real y la región
- Primer año incluye $300 de créditos gratuitos de GCP
- Con ejecución cada minuto: **1,440 mediciones/día** por ubicación (82,080 total para 57 ubicaciones)
- Volumen mensual: ~2,462,400 registros
- La mayoría de servicios siguen en tier gratuito con este volumen
- Estimación basada en precios de us-central1 (Enero 2026)

## Estructura del Proyecto

```
snow_alert/
├── extractor/
│   ├── main.py                 # Cloud Function de extracción
│   ├── requirements.txt        # Dependencias del extractor
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── procesador/
│   ├── main.py                 # Cloud Function de procesamiento
│   ├── requirements.txt        # Dependencias del procesador
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── desplegar.sh                # Script de despliegue automatizado (único punto de entrada)
├── .gcloudignore              # Archivos a ignorar en deploy general
├── .gitignore                  # Archivos a ignorar en git
├── requerimientos.md           # Requerimientos técnicos del proyecto
├── CLAUDE.md                   # Guía para asistentes de IA
└── README.md                   # Este archivo (documentación completa)
```

## Solución de Problemas

### Error: Cloud Scheduler "The request was not authenticated"

**Síntoma**: Cloud Scheduler no puede invocar Cloud Function Gen2

**Causa**: Problema con permisos de Cloud Run (Cloud Functions Gen2 corre sobre Cloud Run)

**Solución**:
```bash
# 1. Agregar permisos de Cloud Run a la cuenta de servicio
gcloud run services add-iam-policy-binding extractor-clima \
  --region=us-central1 \
  --member="serviceAccount:funciones-clima-sa@climas-chileno.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# 2. Verificar con ejecución manual
gcloud scheduler jobs run extraer-clima-job --location=us-central1

# 3. Ver logs para confirmar
gcloud functions logs read extractor-clima --gen2 --region=us-central1 --limit=20
```

### Error: Permisos insuficientes

**Síntoma**: Error 403 o "Permission denied"

**Solución**:
```bash
# Verificar permisos de la cuenta de servicio
gcloud projects get-iam-policy $ID_PROYECTO \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:funciones-clima-sa@"

# Asignar permisos faltantes
gcloud projects add-iam-policy-binding $ID_PROYECTO \
  --member="serviceAccount:funciones-clima-sa@${ID_PROYECTO}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

### Error: API no habilitada

**Síntoma**: "API [nombre] has not been used in project"

**Solución**:
```bash
# Habilitar API específica
gcloud services enable [nombre-api].googleapis.com --project=$ID_PROYECTO

# Ejemplo
gcloud services enable cloudfunctions.googleapis.com --project=$ID_PROYECTO
```

### Error: Timeout en Cloud Function

**Síntoma**: Function timeout, exceeded time limit

**Solución**:
```bash
# Aumentar timeout del extractor
gcloud functions deploy extractor-clima \
  --gen2 \
  --timeout=120s \
  --region=$REGION

# Aumentar timeout del procesador
gcloud functions deploy procesador-clima \
  --gen2 \
  --timeout=180s \
  --region=$REGION
```

### Mensajes en Dead Letter Queue

**Síntoma**: Mensajes acumulados en topic clima-datos-dlq

**Solución**:
```bash
# Ver mensajes en DLQ
gcloud pubsub subscriptions pull clima-datos-dlq-sub --limit=10

# Revisar logs del procesador para identificar causa
gcloud functions logs read procesador-clima --gen2 --region=$REGION --limit=100

# Reprocesar mensajes manualmente si es necesario
```



## Referencias

- [Google Weather API Documentation](https://developers.google.com/maps/documentation/weather)
- [Google Cloud Functions](https://cloud.google.com/functions/docs)
- [Google Cloud Pub/Sub](https://cloud.google.com/pubsub/docs)
- [Google BigQuery](https://cloud.google.com/bigquery/docs)
- [Cloud Scheduler](https://cloud.google.com/scheduler/docs)
- [Arquitectura Medallion](https://www.databricks.com/glossary/medallion-architecture)

---

**Nota**: Snow Alert está diseñado para monitoreo de condiciones climáticas en destinos de nieve y montaña. Úselo para planificar sus aventuras de esquí, snowboard y montañismo de forma segura.

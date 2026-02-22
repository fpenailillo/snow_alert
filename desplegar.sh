#!/bin/bash

##############################################################################
# Script de Despliegue - Sistema de Integración con Google Weather API
#
# Este script despliega la infraestructura completa en Google Cloud Platform:
# - Topics de Pub/Sub
# - Buckets de Cloud Storage
# - Dataset y tablas de BigQuery
# - Cloud Functions (Extractor y Procesador)
# - Cloud Scheduler
#
# Uso:
#   ./desplegar.sh [ID_PROYECTO] [REGION]
#
# Ejemplo:
#   ./desplegar.sh clima-chileno us-central1
##############################################################################

set -e  # Salir en caso de error

# Colores para output
VERDE='\033[0;32m'
AMARILLO='\033[1;33m'
ROJO='\033[0;31m'
AZUL='\033[0;34m'
NC='\033[0m' # Sin color

# Función para imprimir mensajes con formato
imprimir_titulo() {
    echo -e "\n${AZUL}========================================${NC}"
    echo -e "${AZUL}$1${NC}"
    echo -e "${AZUL}========================================${NC}\n"
}

imprimir_exito() {
    echo -e "${VERDE}✓ $1${NC}"
}

imprimir_advertencia() {
    echo -e "${AMARILLO}⚠ $1${NC}"
}

imprimir_error() {
    echo -e "${ROJO}✗ $1${NC}"
}

imprimir_info() {
    echo -e "${AZUL}ℹ $1${NC}"
}

# Función para verificar si un comando existe
verificar_comando() {
    if ! command -v $1 &> /dev/null; then
        imprimir_error "El comando '$1' no está instalado"
        exit 1
    fi
}

# Configuración
ID_PROYECTO=${1:-""}
REGION=${2:-"us-central1"}
ZONA_HORARIA="America/Santiago"

# Nombres de recursos
# Topics de Pub/Sub
TOPIC_DATOS_CRUDOS="clima-datos-crudos"
TOPIC_PRONOSTICO_HORAS="clima-pronostico-horas"
TOPIC_PRONOSTICO_DIAS="clima-pronostico-dias"
TOPIC_DLQ="clima-datos-dlq"
TOPIC_PRONOSTICO_HORAS_DLQ="clima-pronostico-horas-dlq"
TOPIC_PRONOSTICO_DIAS_DLQ="clima-pronostico-dias-dlq"

# Storage y BigQuery
BUCKET_BRONCE="datos-clima-bronce"
DATASET_CLIMA="clima"
TABLA_CONDICIONES="condiciones_actuales"
TABLA_PRONOSTICO_HORAS="pronostico_horas"
TABLA_PRONOSTICO_DIAS="pronostico_dias"

# Cloud Functions
FUNCION_EXTRACTOR="extractor-clima"
FUNCION_PROCESADOR="procesador-clima"
FUNCION_PROCESADOR_HORAS="procesador-clima-horas"
FUNCION_PROCESADOR_DIAS="procesador-clima-dias"

# Scheduler
JOB_SCHEDULER="extraer-clima-job"
CUENTA_SERVICIO="funciones-clima-sa"

# Validar parámetros
if [ -z "$ID_PROYECTO" ]; then
    imprimir_error "Debe proporcionar el ID del proyecto"
    echo "Uso: $0 [ID_PROYECTO] [REGION]"
    echo "Ejemplo: $0 clima-chileno us-central1"
    exit 1
fi

imprimir_titulo "INICIANDO DESPLIEGUE - SISTEMA DE CLIMA GCP"
echo "Proyecto: $ID_PROYECTO"
echo "Región: $REGION"
echo "Zona horaria: $ZONA_HORARIA"

# Verificar dependencias
imprimir_titulo "Verificando dependencias"
verificar_comando "gcloud"
verificar_comando "python3"
imprimir_exito "Todas las dependencias están instaladas"

# Configurar proyecto
imprimir_titulo "Configurando proyecto de GCP"
gcloud config set project $ID_PROYECTO
imprimir_exito "Proyecto configurado: $ID_PROYECTO"

# Habilitar APIs necesarias
imprimir_titulo "Habilitando APIs de Google Cloud"
apis=(
    "cloudfunctions.googleapis.com"
    "cloudbuild.googleapis.com"
    "cloudscheduler.googleapis.com"
    "pubsub.googleapis.com"
    "storage.googleapis.com"
    "bigquery.googleapis.com"
    "logging.googleapis.com"
    "run.googleapis.com"
    "secretmanager.googleapis.com"
    "eventarc.googleapis.com"
    "weather.googleapis.com"
)

for api in "${apis[@]}"; do
    echo "Habilitando $api..."
    gcloud services enable $api --project=$ID_PROYECTO
done
imprimir_exito "APIs habilitadas correctamente"

# Crear cuenta de servicio
imprimir_titulo "Creando cuenta de servicio"
if gcloud iam service-accounts describe ${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Cuenta de servicio ya existe: $CUENTA_SERVICIO"
else
    gcloud iam service-accounts create $CUENTA_SERVICIO \
        --display-name="Cuenta de Servicio para Cloud Functions de Clima" \
        --project=$ID_PROYECTO
    imprimir_exito "Cuenta de servicio creada: $CUENTA_SERVICIO"
fi

# Asignar roles a la cuenta de servicio
imprimir_titulo "Asignando permisos a cuenta de servicio"
roles=(
    "roles/pubsub.publisher"
    "roles/pubsub.subscriber"
    "roles/storage.objectCreator"
    "roles/bigquery.dataEditor"
    "roles/logging.logWriter"
    "roles/cloudfunctions.invoker"
    "roles/run.invoker"
    "roles/secretmanager.secretAccessor"
)

for rol in "${roles[@]}"; do
    echo "Asignando rol: $rol"
    gcloud projects add-iam-policy-binding $ID_PROYECTO \
        --member="serviceAccount:${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com" \
        --role="$rol" \
        --quiet
done
imprimir_exito "Permisos asignados correctamente"

# Configurar Secret Manager para API Key
imprimir_titulo "Configurando Secret Manager para Weather API Key"

# Verificar si el secret ya existe
if gcloud secrets describe weather-api-key --project=$ID_PROYECTO &> /dev/null; then
    imprimir_exito "Secret 'weather-api-key' ya existe en Secret Manager"
else
    imprimir_advertencia "Secret 'weather-api-key' NO existe"
    imprimir_info "Creando secret en Secret Manager..."

    # Crear el secret (sin valor aún)
    gcloud secrets create weather-api-key \
        --replication-policy="automatic" \
        --project=$ID_PROYECTO

    imprimir_exito "Secret creado: weather-api-key"

    echo ""
    imprimir_advertencia "⚠️  ACCIÓN REQUERIDA: Debes agregar tu Weather API Key al secret"
    echo ""
    echo "Obtén tu API Key existente:"
    echo "  gcloud alpha services api-keys list --project=$ID_PROYECTO"
    echo ""
    echo "Obtén el string de la API Key (reemplaza KEY_ID con el ID de tu key):"
    echo "  gcloud alpha services api-keys get-key-string KEY_ID --project=$ID_PROYECTO"
    echo ""
    echo "Agrega el valor al secret:"
    echo "  echo -n 'TU_API_KEY_AQUI' | gcloud secrets versions add weather-api-key --data-file=- --project=$ID_PROYECTO"
    echo ""
    read -p "Presiona ENTER cuando hayas agregado la API Key al secret..."
fi

# Verificar que el secret tenga al menos una versión
VERSION_COUNT=$(gcloud secrets versions list weather-api-key \
    --project=$ID_PROYECTO \
    --format="value(name)" 2>/dev/null | wc -l)

if [ "$VERSION_COUNT" -eq 0 ]; then
    imprimir_error "El secret 'weather-api-key' no tiene ninguna versión (está vacío)"
    echo ""
    echo "Agrega tu Weather API Key:"
    echo "  echo -n 'TU_API_KEY_AQUI' | gcloud secrets versions add weather-api-key --data-file=- --project=$ID_PROYECTO"
    echo ""
    exit 1
fi

imprimir_exito "Secret Manager configurado correctamente con API Key"

# Agregar permisos IAM al secret para la cuenta de servicio
imprimir_info "Configurando permisos IAM del secret..."
gcloud secrets add-iam-policy-binding weather-api-key \
    --member="serviceAccount:${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$ID_PROYECTO \
    --quiet

imprimir_exito "Permisos IAM del secret configurados"

# Crear topics de Pub/Sub
imprimir_titulo "Creando topics de Pub/Sub"

# Topic principal
if gcloud pubsub topics describe $TOPIC_DATOS_CRUDOS --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Topic ya existe: $TOPIC_DATOS_CRUDOS"
else
    gcloud pubsub topics create $TOPIC_DATOS_CRUDOS \
        --project=$ID_PROYECTO
    imprimir_exito "Topic creado: $TOPIC_DATOS_CRUDOS"
fi

# Topic DLQ
if gcloud pubsub topics describe $TOPIC_DLQ --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Topic DLQ ya existe: $TOPIC_DLQ"
else
    gcloud pubsub topics create $TOPIC_DLQ \
        --project=$ID_PROYECTO
    imprimir_exito "Topic DLQ creado: $TOPIC_DLQ"
fi

# Topic pronóstico por horas
if gcloud pubsub topics describe $TOPIC_PRONOSTICO_HORAS --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Topic ya existe: $TOPIC_PRONOSTICO_HORAS"
else
    gcloud pubsub topics create $TOPIC_PRONOSTICO_HORAS \
        --project=$ID_PROYECTO
    imprimir_exito "Topic creado: $TOPIC_PRONOSTICO_HORAS"
fi

# Topic DLQ pronóstico por horas
if gcloud pubsub topics describe $TOPIC_PRONOSTICO_HORAS_DLQ --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Topic DLQ ya existe: $TOPIC_PRONOSTICO_HORAS_DLQ"
else
    gcloud pubsub topics create $TOPIC_PRONOSTICO_HORAS_DLQ \
        --project=$ID_PROYECTO
    imprimir_exito "Topic DLQ creado: $TOPIC_PRONOSTICO_HORAS_DLQ"
fi

# Topic pronóstico por días
if gcloud pubsub topics describe $TOPIC_PRONOSTICO_DIAS --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Topic ya existe: $TOPIC_PRONOSTICO_DIAS"
else
    gcloud pubsub topics create $TOPIC_PRONOSTICO_DIAS \
        --project=$ID_PROYECTO
    imprimir_exito "Topic creado: $TOPIC_PRONOSTICO_DIAS"
fi

# Topic DLQ pronóstico por días
if gcloud pubsub topics describe $TOPIC_PRONOSTICO_DIAS_DLQ --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Topic DLQ ya existe: $TOPIC_PRONOSTICO_DIAS_DLQ"
else
    gcloud pubsub topics create $TOPIC_PRONOSTICO_DIAS_DLQ \
        --project=$ID_PROYECTO
    imprimir_exito "Topic DLQ creado: $TOPIC_PRONOSTICO_DIAS_DLQ"
fi

# Crear bucket de Cloud Storage
imprimir_titulo "Creando bucket de Cloud Storage"
BUCKET_COMPLETO="${ID_PROYECTO}-${BUCKET_BRONCE}"

if gsutil ls -p $ID_PROYECTO gs://$BUCKET_COMPLETO &> /dev/null; then
    imprimir_advertencia "Bucket ya existe: $BUCKET_COMPLETO"
else
    gsutil mb -p $ID_PROYECTO -l $REGION gs://$BUCKET_COMPLETO

    # Configurar versionado
    gsutil versioning set on gs://$BUCKET_COMPLETO

    # Configurar ciclo de vida
    cat > /tmp/lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
        "condition": {"age": 30}
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
        "condition": {"age": 90}
      },
      {
        "action": {"type": "Delete"},
        "condition": {"age": 365}
      }
    ]
  }
}
EOF
    gsutil lifecycle set /tmp/lifecycle.json gs://$BUCKET_COMPLETO
    rm /tmp/lifecycle.json

    imprimir_exito "Bucket creado: $BUCKET_COMPLETO"
fi

# Crear dataset de BigQuery
imprimir_titulo "Creando dataset de BigQuery"
if bq show --project_id=$ID_PROYECTO $DATASET_CLIMA &>/dev/null; then
    imprimir_advertencia "Dataset ya existe: $DATASET_CLIMA"
else
    bq mk --project_id=$ID_PROYECTO \
        --location=$REGION \
        --description="Dataset para datos climáticos procesados" \
        $DATASET_CLIMA
    imprimir_exito "Dataset creado: $DATASET_CLIMA"
fi

# Crear tabla de BigQuery
imprimir_titulo "Creando tabla de BigQuery"
cat > /tmp/schema_clima.json <<EOF
[
  {"name": "nombre_ubicacion", "type": "STRING", "mode": "REQUIRED"},
  {"name": "latitud", "type": "FLOAT64", "mode": "REQUIRED"},
  {"name": "longitud", "type": "FLOAT64", "mode": "REQUIRED"},
  {"name": "hora_actual", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "zona_horaria", "type": "STRING", "mode": "NULLABLE"},
  {"name": "temperatura", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "sensacion_termica", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "punto_rocio", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "indice_calor", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "sensacion_viento", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "condicion_clima", "type": "STRING", "mode": "NULLABLE"},
  {"name": "descripcion_clima", "type": "STRING", "mode": "NULLABLE"},
  {"name": "probabilidad_precipitacion", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "precipitacion_acumulada", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "presion_aire", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "velocidad_viento", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "direccion_viento", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "visibilidad", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "humedad_relativa", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "indice_uv", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "probabilidad_tormenta", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "cobertura_nubes", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "es_dia", "type": "BOOLEAN", "mode": "NULLABLE"},
  {"name": "marca_tiempo_ingestion", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "uri_datos_crudos", "type": "STRING", "mode": "NULLABLE"},
  {"name": "datos_json_crudo", "type": "STRING", "mode": "NULLABLE"}
]
EOF

if bq ls --project_id=$ID_PROYECTO $DATASET_CLIMA | grep -q $TABLA_CONDICIONES; then
    imprimir_advertencia "Tabla ya existe: $TABLA_CONDICIONES"
else
    bq mk --project_id=$ID_PROYECTO \
        --table \
        --time_partitioning_field=hora_actual \
        --time_partitioning_type=DAY \
        --clustering_fields=nombre_ubicacion \
        --description="Condiciones climáticas actuales de ubicaciones monitoreadas" \
        $DATASET_CLIMA.$TABLA_CONDICIONES \
        /tmp/schema_clima.json
    imprimir_exito "Tabla creada: $TABLA_CONDICIONES"
fi
rm /tmp/schema_clima.json

# Crear tabla de pronóstico por horas
imprimir_titulo "Creando tabla de BigQuery: Pronóstico por Horas"
cat > /tmp/schema_pronostico_horas.json <<EOF
[
  {"name": "nombre_ubicacion", "type": "STRING", "mode": "REQUIRED"},
  {"name": "latitud", "type": "FLOAT64", "mode": "REQUIRED"},
  {"name": "longitud", "type": "FLOAT64", "mode": "REQUIRED"},
  {"name": "hora_inicio", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "hora_fin", "type": "TIMESTAMP", "mode": "NULLABLE"},
  {"name": "temperatura", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "sensacion_termica", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "indice_calor", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "sensacion_viento", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "punto_rocio", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "condicion_clima", "type": "STRING", "mode": "NULLABLE"},
  {"name": "descripcion_clima", "type": "STRING", "mode": "NULLABLE"},
  {"name": "icono_url", "type": "STRING", "mode": "NULLABLE"},
  {"name": "humedad_relativa", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "velocidad_viento", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "direccion_viento", "type": "STRING", "mode": "NULLABLE"},
  {"name": "prob_precipitacion", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "cantidad_precipitacion", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "prob_tormenta", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "cobertura_nubes", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "indice_uv", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "es_dia", "type": "BOOLEAN", "mode": "NULLABLE"},
  {"name": "visibilidad", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "presion_aire", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "marca_tiempo_extraccion", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "marca_tiempo_ingestion", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "uri_datos_crudos", "type": "STRING", "mode": "NULLABLE"}
]
EOF

if bq ls --project_id=$ID_PROYECTO $DATASET_CLIMA | grep -q $TABLA_PRONOSTICO_HORAS; then
    imprimir_advertencia "Tabla ya existe: $TABLA_PRONOSTICO_HORAS"
else
    bq mk --project_id=$ID_PROYECTO \
        --table \
        --time_partitioning_field=hora_inicio \
        --time_partitioning_type=DAY \
        --clustering_fields=nombre_ubicacion \
        --description="Pronóstico climático por horas (próximas 76 horas)" \
        $DATASET_CLIMA.$TABLA_PRONOSTICO_HORAS \
        /tmp/schema_pronostico_horas.json
    imprimir_exito "Tabla creada: $TABLA_PRONOSTICO_HORAS"
fi
rm /tmp/schema_pronostico_horas.json

# Crear tabla de pronóstico por días
imprimir_titulo "Creando tabla de BigQuery: Pronóstico por Días"
cat > /tmp/schema_pronostico_dias.json <<EOF
[
  {"name": "nombre_ubicacion", "type": "STRING", "mode": "REQUIRED"},
  {"name": "latitud", "type": "FLOAT64", "mode": "REQUIRED"},
  {"name": "longitud", "type": "FLOAT64", "mode": "REQUIRED"},
  {"name": "fecha_inicio", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "fecha_fin", "type": "TIMESTAMP", "mode": "NULLABLE"},
  {"name": "anio", "type": "INT64", "mode": "NULLABLE"},
  {"name": "mes", "type": "INT64", "mode": "NULLABLE"},
  {"name": "dia", "type": "INT64", "mode": "NULLABLE"},
  {"name": "hora_amanecer", "type": "STRING", "mode": "NULLABLE"},
  {"name": "hora_atardecer", "type": "STRING", "mode": "NULLABLE"},
  {"name": "temp_max_dia", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "temp_min_dia", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_condicion", "type": "STRING", "mode": "NULLABLE"},
  {"name": "diurno_descripcion", "type": "STRING", "mode": "NULLABLE"},
  {"name": "diurno_icono_url", "type": "STRING", "mode": "NULLABLE"},
  {"name": "diurno_temp_max", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_temp_min", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_sensacion_max", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_sensacion_min", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_humedad", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_velocidad_viento", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_direccion_viento", "type": "STRING", "mode": "NULLABLE"},
  {"name": "diurno_prob_precipitacion", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_cantidad_precipitacion", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_prob_tormenta", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_cobertura_nubes", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "diurno_indice_uv", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_condicion", "type": "STRING", "mode": "NULLABLE"},
  {"name": "nocturno_descripcion", "type": "STRING", "mode": "NULLABLE"},
  {"name": "nocturno_icono_url", "type": "STRING", "mode": "NULLABLE"},
  {"name": "nocturno_temp_max", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_temp_min", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_sensacion_max", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_sensacion_min", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_humedad", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_velocidad_viento", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_direccion_viento", "type": "STRING", "mode": "NULLABLE"},
  {"name": "nocturno_prob_precipitacion", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_cantidad_precipitacion", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_prob_tormenta", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_cobertura_nubes", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "nocturno_indice_uv", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "marca_tiempo_extraccion", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "marca_tiempo_ingestion", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "uri_datos_crudos", "type": "STRING", "mode": "NULLABLE"}
]
EOF

if bq ls --project_id=$ID_PROYECTO $DATASET_CLIMA | grep -q $TABLA_PRONOSTICO_DIAS; then
    imprimir_advertencia "Tabla ya existe: $TABLA_PRONOSTICO_DIAS"
else
    bq mk --project_id=$ID_PROYECTO \
        --table \
        --time_partitioning_field=fecha_inicio \
        --time_partitioning_type=DAY \
        --clustering_fields=nombre_ubicacion \
        --description="Pronóstico climático por días (próximos 10 días)" \
        $DATASET_CLIMA.$TABLA_PRONOSTICO_DIAS \
        /tmp/schema_pronostico_dias.json
    imprimir_exito "Tabla creada: $TABLA_PRONOSTICO_DIAS"
fi
rm /tmp/schema_pronostico_dias.json

# Desplegar Cloud Function Extractor
imprimir_titulo "Desplegando Cloud Function: Extractor"
gcloud functions deploy $FUNCION_EXTRACTOR \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source=./extractor \
    --entry-point=extraer_clima \
    --trigger-http \
    --service-account=${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com \
    --set-env-vars=GCP_PROJECT=$ID_PROYECTO \
    --memory=256MB \
    --timeout=60s \
    --max-instances=10 \
    --project=$ID_PROYECTO \
    --quiet

imprimir_exito "Cloud Function desplegada: $FUNCION_EXTRACTOR"

# Obtener URL del extractor
URL_EXTRACTOR=$(gcloud functions describe $FUNCION_EXTRACTOR \
    --gen2 \
    --region=$REGION \
    --project=$ID_PROYECTO \
    --format='value(serviceConfig.uri)')

echo "URL del extractor: $URL_EXTRACTOR"

# Otorgar permisos de invocación al servicio Cloud Run del extractor
imprimir_titulo "Otorgando permisos al servicio Cloud Run del extractor"
imprimir_info "Cloud Functions Gen2 corre sobre Cloud Run - configurando permisos..."

gcloud run services add-iam-policy-binding $FUNCION_EXTRACTOR \
    --region=$REGION \
    --member="serviceAccount:${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --project=$ID_PROYECTO \
    --quiet

imprimir_exito "Permisos de invocación configurados para Cloud Scheduler"

# Desplegar Cloud Function Procesador
imprimir_titulo "Desplegando Cloud Function: Procesador"
gcloud functions deploy $FUNCION_PROCESADOR \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source=./procesador \
    --entry-point=procesar_clima \
    --trigger-topic=$TOPIC_DATOS_CRUDOS \
    --service-account=${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com \
    --set-env-vars=GCP_PROJECT=$ID_PROYECTO,BUCKET_CLIMA=$BUCKET_COMPLETO,DATASET_CLIMA=$DATASET_CLIMA,TABLA_CLIMA=$TABLA_CONDICIONES \
    --memory=512MB \
    --timeout=120s \
    --max-instances=10 \
    --project=$ID_PROYECTO \
    --quiet

imprimir_exito "Cloud Function desplegada: $FUNCION_PROCESADOR"

# Desplegar Cloud Function Procesador de Pronóstico por Horas
imprimir_titulo "Desplegando Cloud Function: Procesador Pronóstico Horas"
gcloud functions deploy $FUNCION_PROCESADOR_HORAS \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source=./procesador_horas \
    --entry-point=procesar_pronostico_horas \
    --trigger-topic=$TOPIC_PRONOSTICO_HORAS \
    --service-account=${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com \
    --set-env-vars=GCP_PROJECT=$ID_PROYECTO,BUCKET_CLIMA=$BUCKET_COMPLETO,DATASET_CLIMA=$DATASET_CLIMA \
    --memory=512MB \
    --timeout=120s \
    --max-instances=10 \
    --project=$ID_PROYECTO \
    --quiet

imprimir_exito "Cloud Function desplegada: $FUNCION_PROCESADOR_HORAS"

# Desplegar Cloud Function Procesador de Pronóstico por Días
imprimir_titulo "Desplegando Cloud Function: Procesador Pronóstico Días"
gcloud functions deploy $FUNCION_PROCESADOR_DIAS \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source=./procesador_dias \
    --entry-point=procesar_pronostico_dias \
    --trigger-topic=$TOPIC_PRONOSTICO_DIAS \
    --service-account=${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com \
    --set-env-vars=GCP_PROJECT=$ID_PROYECTO,BUCKET_CLIMA=$BUCKET_COMPLETO,DATASET_CLIMA=$DATASET_CLIMA \
    --memory=512MB \
    --timeout=120s \
    --max-instances=10 \
    --project=$ID_PROYECTO \
    --quiet

imprimir_exito "Cloud Function desplegada: $FUNCION_PROCESADOR_DIAS"

# Crear job de Cloud Scheduler
imprimir_titulo "Creando job de Cloud Scheduler"

# Eliminar job existente si existe
if gcloud scheduler jobs describe $JOB_SCHEDULER --location=$REGION --project=$ID_PROYECTO &> /dev/null; then
    imprimir_advertencia "Eliminando job existente: $JOB_SCHEDULER"
    gcloud scheduler jobs delete $JOB_SCHEDULER \
        --location=$REGION \
        --project=$ID_PROYECTO \
        --quiet
fi

# Crear nuevo job
gcloud scheduler jobs create http $JOB_SCHEDULER \
    --location=$REGION \
    --schedule="0 8,14,20 * * *" \
    --uri=$URL_EXTRACTOR \
    --http-method=POST \
    --oidc-service-account-email=${CUENTA_SERVICIO}@${ID_PROYECTO}.iam.gserviceaccount.com \
    --oidc-token-audience=$URL_EXTRACTOR \
    --time-zone=$ZONA_HORARIA \
    --description="Ejecuta extracción de datos climáticos 3 veces al día (08:00, 14:00, 20:00)" \
    --project=$ID_PROYECTO

imprimir_exito "Job de Cloud Scheduler creado: $JOB_SCHEDULER"

# Resumen final
imprimir_titulo "DESPLIEGUE COMPLETADO EXITOSAMENTE"

echo -e "${VERDE}Recursos creados:${NC}"
echo ""
echo "  Pub/Sub Topics:"
echo "  • $TOPIC_DATOS_CRUDOS (condiciones actuales)"
echo "  • $TOPIC_PRONOSTICO_HORAS (pronóstico por horas)"
echo "  • $TOPIC_PRONOSTICO_DIAS (pronóstico por días)"
echo "  • $TOPIC_DLQ (dead letter queue - condiciones)"
echo "  • $TOPIC_PRONOSTICO_HORAS_DLQ (dead letter queue - horas)"
echo "  • $TOPIC_PRONOSTICO_DIAS_DLQ (dead letter queue - días)"
echo ""
echo "  Storage:"
echo "  • Bucket GCS: gs://$BUCKET_COMPLETO"
echo ""
echo "  BigQuery:"
echo "  • Dataset: $DATASET_CLIMA"
echo "  • Tabla: $TABLA_CONDICIONES (condiciones actuales)"
echo "  • Tabla: $TABLA_PRONOSTICO_HORAS (pronóstico 76 horas)"
echo "  • Tabla: $TABLA_PRONOSTICO_DIAS (pronóstico 10 días)"
echo ""
echo "  Cloud Functions:"
echo "  • $FUNCION_EXTRACTOR (extrae datos de Weather API)"
echo "  • $FUNCION_PROCESADOR (procesa condiciones actuales)"
echo "  • $FUNCION_PROCESADOR_HORAS (procesa pronóstico por horas)"
echo "  • $FUNCION_PROCESADOR_DIAS (procesa pronóstico por días)"
echo ""
echo "  Scheduler:"
echo "  • $JOB_SCHEDULER (3x/día: 08:00, 14:00, 20:00)"
echo ""
echo -e "${AZUL}URLs importantes:${NC}"
echo "  • Extractor: $URL_EXTRACTOR"
echo "  • Logs: https://console.cloud.google.com/logs/query?project=$ID_PROYECTO"
echo "  • BigQuery: https://console.cloud.google.com/bigquery?project=$ID_PROYECTO&d=$DATASET_CLIMA"
echo ""
echo -e "${AMARILLO}Próximos pasos:${NC}"
echo "  1. Probar extractor manualmente: curl -X POST $URL_EXTRACTOR"
echo "  2. Ver logs: gcloud functions logs read $FUNCION_EXTRACTOR --gen2 --region=$REGION"
echo "  3. Consultar condiciones actuales:"
echo "     bq query --use_legacy_sql=false 'SELECT * FROM $DATASET_CLIMA.$TABLA_CONDICIONES LIMIT 10'"
echo "  4. Consultar pronóstico por horas:"
echo "     bq query --use_legacy_sql=false 'SELECT * FROM $DATASET_CLIMA.$TABLA_PRONOSTICO_HORAS LIMIT 10'"
echo "  5. Consultar pronóstico por días:"
echo "     bq query --use_legacy_sql=false 'SELECT * FROM $DATASET_CLIMA.$TABLA_PRONOSTICO_DIAS LIMIT 10'"
echo "  6. El scheduler ejecutará automáticamente 3 veces al día (08:00, 14:00 y 20:00)"
echo ""

imprimir_exito "¡Listo! El sistema está desplegado y funcionando."

# Guía de Despliegue — Snow Alert

## Prerrequisitos

- `gcloud` CLI autenticado con `climas-chileno`
- `ANTHROPIC_API_KEY` o `CLAUDE_CODE_OAUTH_TOKEN` en Secret Manager
- Acceso a BigQuery dataset `clima`

## Capa de Datos (Cloud Functions)

```bash
cd datos
./desplegar.sh
```

## Sistema Multi-Agente (Cloud Run Job)

```bash
cd agentes
# Build image
gcloud builds submit --config despliegue/cloudbuild.yaml

# Deploy job
gcloud run jobs replace despliegue/job_cloud_run.yaml --region=us-central1
```

## FASE 1: Carga Relatos Andeshandbook

1. Abrir Databricks workspace del proyecto `climas-chileno`
2. Importar los notebooks de `databricks/`
3. Ejecutar en orden: 01 → 02 → 03 → 04 → 05
4. Verificar con: `bq query "SELECT COUNT(*) FROM clima.relatos_montanistas"`
5. El notebook `02_carga_relatos_bigquery.py` es el responsable de la carga masiva

### Schema `clima.relatos_montanistas`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_relato` | STRING | ID único del relato |
| `ubicacion` | STRING | Nombre de la ubicación |
| `fecha_actividad` | DATE | Fecha de la actividad |
| `titulo` | STRING | Título del relato |
| `texto_completo` | STRING | Texto íntegro |
| `condiciones_nieve` | STRING | Descripción de condiciones |
| `nivel_dificultad` | STRING | Dificultad reportada |
| `menciona_avalancha` | BOOL | ¿Menciona avalanchas? |
| `palabras_clave` | STRING | Keywords extraídos |
| `fuente` | STRING | Andeshandbook / manual |
| `fecha_carga` | TIMESTAMP | Cuándo se cargó |

### Configuración Databricks

- Cluster: Standard_DS3_v2 o similar
- Runtime: DBR 14.x (Python 3.11)
- Librerías: `google-cloud-bigquery`, `pandas`, `requests`
- Credenciales GCP: Service account JSON en secrets

## Variables de Entorno

```bash
# En Secret Manager (climas-chileno)
CLAUDE_CODE_OAUTH_TOKEN=...
WEATHER_API_KEY=...

# En Cloud Run Job
ID_PROYECTO=climas-chileno
DATASET_ID=clima
```

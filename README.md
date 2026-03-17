# Snow Alert — Sistema Inteligente de Predicción de Avalanchas

Sistema multi-agente sobre Google Cloud Platform que genera boletines EAWS (niveles 1-5) para zonas de montaña chilenas, combinando análisis topográfico (PINNs), satelital (Vision Transformers), meteorológico, y conocimiento experto de relatos históricos de montañistas.

**Proyecto GCP:** `climas-chileno` | **Cuenta:** `fpenailillom@correo.uss.cl`
**Repo:** `https://github.com/fpenailillo/snow_alert`

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                      GOOGLE CLOUD PLATFORM                          │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                  CAPA DE DATOS  (datos/)                    │    │
│  │                                                            │    │
│  │  Cloud Scheduler                                           │    │
│  │  ├── extractor-clima (3x/día) ──────────────→ BigQuery ✅  │    │
│  │  ├── monitor-satelital (3x/día) ────────────→ BigQuery ⚠️  │    │
│  │  └── analizador-topografico (mensual) ──────→ BigQuery ⚠️  │    │
│  └────────────────────────────────────────────────────────────┘    │
│                               ↓ BigQuery clima.*                   │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │               CAPA DE AGENTES  (agentes/)                   │    │
│  │                                                            │    │
│  │  Cloud Scheduler (3x/día: 09:00, 15:00, 21:00)            │    │
│  │           ↓                                                │    │
│  │  Cloud Run Job: orquestador-avalanchas                     │    │
│  │                                                            │    │
│  │   [S1 Topográfico+PINN] → [S2 Satelital+ViT]              │    │
│  │   → [S3 Meteorológico] → [S4 NLP Relatos]                 │    │
│  │   → [S5 Integrador EAWS+Boletín]                          │    │
│  └────────────────────────────────────────────────────────────┘    │
│                               ↓                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │               CAPA DE RESULTADOS                            │    │
│  │  BigQuery: clima.boletines_riesgo                          │    │
│  │  GCS: boletines/{ubicacion}/{YYYY/MM/DD}/{timestamp}.json  │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Estructura del repositorio

```
snow_alert/
├── datos/                    ← Cloud Functions de recolección (NO modificar)
│   ├── extractor/            # Weather API → clima.condiciones_actuales ✅
│   ├── procesador/           # Pub/Sub processor
│   ├── procesador_horas/     # Pub/Sub processor
│   ├── procesador_dias/      # Pub/Sub processor
│   ├── monitor_satelital/    # GEE → clima.imagenes_satelitales ⚠️
│   ├── analizador_avalanchas/# GEE → clima.zonas_avalancha ⚠️
│   └── desplegar.sh          # Script de despliegue Cloud Functions
│
├── agentes/                  ← Sistema multi-agente (aquí trabajamos)
│   ├── datos/                # ConsultorBigQuery (acceso centralizado a tablas)
│   ├── subagentes/           # S1 Topográfico, S2 Satelital, S3 Meteo, S4 NLP, S5 Integrador
│   ├── orquestador/          # Coordina los 5 subagentes en secuencia
│   ├── salidas/              # Almacenador + schema BigQuery
│   ├── diagnostico/          # Scripts de diagnóstico de datos
│   ├── despliegue/           # Dockerfile, cloudbuild.yaml, job_cloud_run.yaml
│   ├── scripts/              # CLI: generar_boletin.py, generar_todos.py
│   └── tests/                # Tests unitarios e integración
│
├── relatos/                  ← Relatos Andeshandbook (~4.000)
│   └── README.md             # Instrucciones de carga a BigQuery
│
├── databricks/               ← Notebooks de carga y análisis offline
│   ├── 01_explorar_andeshandbook.py
│   ├── 02_carga_relatos_bigquery.py
│   └── ...
│
└── docs/                     ← Documentación técnica
    ├── arquitectura.md
    └── guia_despliegue.md
```

---

## Tablas BigQuery (`climas-chileno.clima.*`)

| Tabla | Estado | Descripción |
|-------|--------|-------------|
| `condiciones_actuales` | ✅ ~69.000 filas | Condiciones meteorológicas 3x/día |
| `pronostico_horas` | ✅ Con datos | Pronóstico horario 76h |
| `pronostico_dias` | ✅ Con datos | Pronóstico diario 10 días |
| `imagenes_satelitales` | ⚠️ Nulos | Métricas satelitales (NDSI, LST, cobertura) |
| `zonas_avalancha` | ⚠️ Nulos | Análisis topográfico EAWS mensual |
| `relatos_montanistas` | ❌ Pendiente | ~4.000 relatos Andeshandbook |
| `boletines_riesgo` | ❌ Pendiente | Output del sistema multi-agente |

---

## Requisitos

```bash
Python 3.11+
gcloud CLI autenticado (fpenailillom@correo.uss.cl)
ANTHROPIC_API_KEY  o  CLAUDE_CODE_OAUTH_TOKEN
google-cloud-bigquery
anthropic
```

## Instalación local

```bash
cd agentes
pip install -r requirements.txt
export ANTHROPIC_API_KEY="..."
```

## Tests

```bash
cd agentes

# Tests unitarios (sin credenciales Anthropic ni BigQuery)
python -m pytest tests/test_subagentes.py -v -k "TestTools"

# Tests de datos BigQuery (requiere GCP auth)
python -m pytest tests/test_fase0_datos.py -v

# Tests de integración (requiere ANTHROPIC_API_KEY)
python -m pytest tests/test_sistema_completo.py -v -s
```

## Generar un boletín localmente

```bash
cd agentes
python scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"
```

## Despliegue en GCP

```bash
# Capa de datos (Cloud Functions)
cd datos && ./desplegar.sh

# Sistema multi-agente (Cloud Run Job)
cd agentes
gcloud builds submit --config despliegue/cloudbuild.yaml --project=climas-chileno
gcloud run jobs execute orquestador-avalanchas --region=us-central1
```

Ver `docs/guia_despliegue.md` para instrucciones completas.

---

## Estado del proyecto — Marzo 2026

- ✅ Capa de datos operacional (Cloud Functions + BigQuery)
- ✅ Sistema multi-agente v2 (4 subagentes) funcionando localmente
- 🔨 En construcción: S4 SubagenteNLP + actualización a 5 subagentes
- 🔨 Pendiente: datos nulos en imagenes_satelitales y zonas_avalancha (FASE 0)
- 🔨 Pendiente: carga de relatos Andeshandbook (FASE 1)
- 🔨 Pendiente: despliegue Cloud Run Job (FASE 3)

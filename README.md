# Snow Alert — Sistema Inteligente de Predicción de Avalanchas

Sistema multi-agente sobre Google Cloud Platform que genera boletines EAWS (niveles 1-5) para zonas de montaña chilenas, combinando análisis topográfico (PINNs + SRTM), monitoreo satelital (Vision Transformers + MODIS/GEE), meteorología (Google Weather API) y conocimiento experto extraído de relatos históricos de montañistas (NLP).

> Tesina de Magíster en Tecnologías de la Información — Francisco Peñailillo — UTFSM — Dr. Mauricio Solar

**Proyecto GCP:** `climas-chileno` | **Dataset BigQuery:** `clima` | **Región:** `us-central1`

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────────────┐
│                       GOOGLE CLOUD PLATFORM                          │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  CAPA DE DATOS  (datos/)                     │    │
│  │                                                             │    │
│  │  Cloud Scheduler                                            │    │
│  │  ├── extractor-clima (3x/día) ──────────────→ BigQuery ✅   │    │
│  │  ├── procesador-clima-horas (Pub/Sub) ──────→ BigQuery ✅   │    │
│  │  ├── procesador-clima-dias (Pub/Sub) ───────→ BigQuery ✅   │    │
│  │  ├── monitor-satelital-nieve (3x/día) ──────→ BigQuery ✅   │    │
│  │  └── analizador-zonas-avalanchas (mensual) ─→ BigQuery ✅   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               ↓ BigQuery clima.*                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │               CAPA DE AGENTES  (agentes/)                    │    │
│  │                                                             │    │
│  │  Cloud Run Job: orquestador-avalanchas                      │    │
│  │                                                             │    │
│  │   [S1 Topográfico+PINN] → [S2 Satelital+ViT]               │    │
│  │   → [S3 Meteorológico] → [S4 NLP Relatos]                  │    │
│  │   → [S5 Integrador EAWS+Boletín]                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  CAPA DE RESULTADOS                          │    │
│  │  BigQuery: clima.boletines_riesgo (34 campos)               │    │
│  │  GCS: boletines/{ubicacion}/{YYYY/MM/DD}/{timestamp}.json   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline de 5 subagentes

| # | Subagente | Técnica | Output clave |
|---|-----------|---------|--------------|
| S1 | Topográfico | PINNs + DEM SRTM 30m + UQ Taylor | `clase_estabilidad_eaws`, `indice_riesgo_topografico`, IC 95% FS |
| S2 | Satelital | Vision Transformer (multi-head attention H=2) + MODIS/GEE | `alertas_satelitales`, `patron_detectado`, `anomalia_score` |
| S3 | Meteorológico | Google Weather API + análisis tendencias | `ventanas_criticas`, `alertas_meteorologicas` |
| S4 | NLP Relatos | Búsqueda semántica sobre 3.131 relatos Andeshandbook | `indice_riesgo_historico`, `tipo_alud_predominante` |
| S5 | Integrador | Matriz EAWS 2025 (Müller, Techel & Mitterer) | Boletín EAWS completo 24h/48h/72h |

---

## Estructura del repositorio

```
snow_alert/
├── datos/                         ← Cloud Functions de recolección (6 activas en GCP)
│   ├── extractor/                 # Google Weather API → condiciones_actuales
│   ├── procesador/                # Pub/Sub: condiciones brutas → BigQuery
│   ├── procesador_horas/          # Pub/Sub: pronóstico horario → pronostico_horas
│   ├── procesador_dias/           # Pub/Sub: pronóstico diario → pronostico_dias
│   ├── monitor_satelital/         # GEE MODIS → imagenes_satelitales
│   ├── analizador_avalanchas/     # GEE SRTM → zonas_avalancha (eaws_constantes.py)
│   └── relatos/                   # ETL Andeshandbook → relatos_montanistas
│
├── agentes/                       ← Sistema multi-agente Claude
│   ├── datos/
│   │   ├── consultor_bigquery.py  # Acceso centralizado a las 6 tablas BQ
│   │   └── cliente_llm.py         # ClienteAnthropic + ClienteDatabricks (fallback)
│   ├── subagentes/
│   │   ├── base_subagente.py      # Clase base con agentic loop
│   │   ├── subagente_topografico/ # S1: PINN + DEM + estabilidad EAWS
│   │   ├── subagente_satelital/   # S2: ViT + NDSI + snowline
│   │   ├── subagente_meteorologico/ # S3: condiciones + pronóstico + ventanas
│   │   ├── subagente_nlp/         # S4: relatos + patrones + conocimiento andino
│   │   └── subagente_integrador/  # S5: clasificar EAWS + generar boletín
│   ├── orquestador/
│   │   └── agente_principal.py    # Coordina S1→S2→S3→S4→S5
│   ├── salidas/
│   │   ├── almacenador.py         # Guarda boletín en BQ + GCS
│   │   └── schema_boletines.json  # Schema 34 campos
│   ├── validacion/
│   │   └── metricas_eaws.py       # F1-macro, Kappa, QWK, Techel 2022
│   ├── despliegue/
│   │   ├── Dockerfile
│   │   ├── cloudbuild.yaml
│   │   └── job_cloud_run.yaml
│   ├── scripts/
│   │   ├── generar_boletin.py     # CLI para generar un boletín
│   │   └── generar_todos.py       # Genera boletines para todas las ubicaciones
│   └── tests/
│       ├── test_subagentes.py     # Tests unitarios por subagente (126 passed)
│       ├── test_sistema_completo.py # Test E2E (requiere credenciales)
│       └── test_fase0_datos.py    # Tests conexión BigQuery
│
├── notebooks_validacion/          ← Notebooks de validación académica (H1-H4)
│   ├── 01_validacion_f1_score.py
│   ├── 02_analisis_ablacion.py
│   ├── 03_comparacion_snowlab.py
│   ├── 04_confianza_cobertura.py
│   ├── 05_pruebas_estadisticas.py # Bootstrap IC 95%, McNemar, análisis de potencia
│   └── 06_analisis_nlp_sintetico.py # H2 confirmada sintéticamente (+7.9pp)
│
├── claude/                        ← Guías para sesiones de Claude Code
│   ├── CLAUDE.md
│   ├── PROGRESO.md
│   ├── PLAN_BRECHAS_MARCO_TEORICO.md
│   ├── PROMPT_VALIDACION_ESTADO.md
│   └── PROMPT_REVISION_MARCO_TEORICO.md
│
└── docs/                          ← Documentos académicos (gestión manual)
```

---

## Tablas BigQuery (`climas-chileno.clima.*`)

| Tabla | Estado | Descripción |
|-------|--------|-------------|
| `condiciones_actuales` | ✅ ~69.000 filas, 84 ubicaciones | Condiciones meteorológicas 3x/día (Google Weather API) |
| `pronostico_horas` | ✅ ~2.500 filas, 61 ubicaciones | Pronóstico horario 76h |
| `pronostico_dias` | ✅ ~17.000 filas, 63 ubicaciones | Pronóstico diario 10 días |
| `imagenes_satelitales` | ✅ 376 filas | Métricas MODIS (NDSI, snowline, pct_cobertura) |
| `zonas_avalancha` | ⚠️ 37 filas, re-run pendiente | Análisis topográfico SRTM mensual (fix desplegado) |
| `relatos_montanistas` | ✅ 3.131 rutas | Relatos Andeshandbook (37 campos) |
| `boletines_riesgo` | ⬜ Schema listo (34 campos) | Output del sistema multi-agente |

---

## Hipótesis de investigación

| ID | Hipótesis | Métrica objetivo | Estado |
|----|-----------|-----------------|--------|
| H1 | F1-score macro ≥ 75% en predicción EAWS 24-72h | F1-macro | ⬜ Requiere boletines piloto |
| H2 | NLP mejora precisión > 5pp vs sin NLP | Delta F1 ablación | ✅ Confirmada sintéticamente (+7.9pp) |
| H3 | Transfer learning SLF supera modelo solo chileno | QWK | ⬜ Pendiente datos SLF |
| H4 | ≥ 75% concordancia con Snowlab Chile | Cohen's Kappa ≥ 0.60 | ⬜ Pendiente datos Snowlab |

---

## Instalación y uso local

```bash
# Requisitos
Python 3.11+
gcloud CLI autenticado (fpenailillom@correo.uss.cl)
ANTHROPIC_API_KEY  o  CLAUDE_CODE_OAUTH_TOKEN

# Instalar dependencias
cd agentes
pip install -r despliegue/requirements.txt

# Generar un boletín
cd snow_alert
python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"
```

## Tests

```bash
cd snow_alert

# Tests unitarios — sin credenciales externas (126 passed)
python -m pytest agentes/tests/test_subagentes.py -v -k "TestTools"

# Tests conexión BigQuery (requiere GCP auth)
python -m pytest agentes/tests/test_fase0_datos.py -v

# Test E2E completo (requiere ANTHROPIC_API_KEY o Databricks token)
python -m pytest agentes/tests/test_sistema_completo.py -v -s
```

## Despliegue en GCP

```bash
# Capa de datos (6 Cloud Functions)
cd datos && ./desplegar.sh climas-chileno us-central1

# Sistema multi-agente (Cloud Run Job)
gcloud builds submit --config agentes/despliegue/cloudbuild.yaml --project=climas-chileno
gcloud run jobs execute orquestador-avalanchas --region=us-central1
```

---

## Estado del proyecto — Marzo 2026

### ✅ Operacional
- 6 Cloud Functions activas recolectando datos 3x/día
- 5 subagentes implementados con agentic loop (S1–S5)
- 3.131 relatos Andeshandbook cargados en BigQuery (37 campos)
- Pipeline completo funciona end-to-end en ~114s con 5/5 subagentes
- LLM alternativo Databricks/Qwen3-80B operativo como fallback a Anthropic
- 126 tests unitarios passing
- Framework de validación académica completo (F1, Kappa, QWK, Techel 2022)
- H2 confirmada sintéticamente: NLP mejora +7.9pp sobre baseline

### ⚠️ Pendiente
- Re-ejecutar `analizador-satelital-zonas-riesgosas-avalanchas` para regenerar `zonas_avalancha` con pendientes correctas
- Desplegar Cloud Run Job `orquestador-avalanchas` en producción
- Generar ≥ 50 boletines piloto para calcular métricas reales H1/H4

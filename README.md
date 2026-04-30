# Snow Alert — Sistema Inteligente de Predicción de Avalanchas

Sistema multi-agente sobre Google Cloud Platform que genera boletines EAWS (niveles 1-5) para zonas de montaña chilenas, combinando análisis topográfico (PINNs + Copernicus GLO-30 + TAGEE + AlphaEarth), monitoreo satelital (Vision Transformers + Sentinel-1/2 + MODIS), meteorología (Open-Meteo + ERA5-Land + WeatherNext 2) y situational briefing contextual (Qwen3-80B vía Databricks).

> Propuesta Tesina de Magíster en Tecnologías de la Información — Francisco Peñailillo — UTFSM

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
│  │   [S1 Topográfico+PINN+GLO30+TAGEE+AlphaEarth]             │    │
│  │   → [S2 Satelital+ViT+GeminiMultispectral]                 │    │
│  │   → [S3 Meteorológico+WeatherNext2]                        │    │
│  │   → [S4 SituationalBriefing (Qwen3-80B)]                   │    │
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
| S1 | Topográfico | PINNs + Copernicus GLO-30 + TAGEE (13 atributos) + AlphaEarth embeddings 64D | `clase_estabilidad_eaws`, `indice_riesgo_topografico`, IC 95% FS, drift interanual |
| S2 | Satelital | Vision Transformer (MHA H=2) + Sentinel-1 SAR + Sentinel-2 SR + MODIS/061; Gemini 2.5 multispectral en paralelo (A/B) | `alertas_satelitales`, `patron_detectado`, `anomalia_score` |
| S3 | Meteorológico | ConsolidadorMeteorologico: Open-Meteo + ERA5-Land + WeatherNext 2 (64 miembros ensemble, flag `USE_WEATHERNEXT2`) | `ventanas_criticas`, `alertas_meteorologicas`, P10/P50/P90 |
| S4 | Situational Briefing | AgenteSituationalBriefing — Qwen3-80B vía Databricks; 4 tools: clima reciente, contexto histórico, características zona, eventos pasados | `narrativa_integrada`, `factores_atencion_eaws`, `indice_riesgo_cualitativo` |
| S5 | Integrador | Matriz EAWS 2025 (Müller, Techel & Mitterer) — Qwen3-80B vía Databricks | Boletín EAWS completo 24h/48h/72h |

---

## Estructura del repositorio

```
snow_alert/
├── datos/                         ← Cloud Functions de recolección (6 activas en GCP)
│   ├── extractor/                 # Google Weather API → condiciones_actuales
│   ├── procesador/                # Pub/Sub: condiciones brutas → BigQuery
│   ├── procesador_horas/          # Pub/Sub: pronóstico horario → pronostico_horas
│   ├── procesador_dias/           # Pub/Sub: pronóstico diario → pronostico_dias
│   ├── monitor_satelital/         # GEE MODIS/Sentinel → imagenes_satelitales
│   ├── analizador_avalanchas/     # GEE GLO-30 → zonas_avalancha (eaws_constantes.py)
│   └── relatos/                   # ETL Andeshandbook → relatos_montanistas
│
├── agentes/                       ← Sistema multi-agente
│   ├── datos/
│   │   ├── consultor_bigquery.py  # Acceso centralizado a tablas BQ
│   │   ├── constantes_zonas.py    # Fuente única de coordenadas/bbox/polígonos
│   │   └── cliente_llm.py         # ClienteAnthropic + ClienteDatabricks (fallback)
│   ├── datos/backfill/
│   │   ├── backfill_clima_historico.py  # Backfill ERA5 para fechas históricas
│   │   └── backfill_satelital.py        # Backfill SAR+MODIS+ERA5+S2 multi-región
│   ├── subagentes/
│   │   ├── base_subagente.py      # Clase base con agentic loop
│   │   ├── subagente_topografico/ # S1: PINN + GLO-30 + TAGEE + AlphaEarth
│   │   │   └── tools/             # tool_analizar_dem, tool_calcular_pinn, tool_tagee_terreno, tool_alphaearth
│   │   ├── subagente_satelital/   # S2: ViT + SAR + Gemini multispectral (A/B)
│   │   │   ├── schemas.py         # DeteccionSatelital con campo via (vit/gemini/rsfm)
│   │   │   └── comparador/ab_runner.py  # ComparadorS2 — persiste en s2_comparaciones
│   │   ├── subagente_meteorologico/ # S3: ConsolidadorMeteorologico multi-fuente
│   │   │   ├── fuentes/           # FuenteOpenMeteo, FuenteERA5Land, FuenteWeatherNext2
│   │   │   └── tools/tool_pronostico_ensemble.py
│   │   ├── subagente_situational_briefing/ # S4: reemplazo del NLP anterior
│   │   │   ├── agente.py          # AgenteSituationalBriefing (Qwen3-80B)
│   │   │   ├── schemas.py         # SituationalBriefing, CondicionesRecientes, ContextoHistorico
│   │   │   ├── tools/             # tool_clima_reciente, tool_contexto_historico, tool_caracteristicas_zona, tool_eventos_pasados
│   │   │   └── prompts/system_prompt.md
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
│   │   ├── generar_boletin.py     # CLI para generar un boletín individual
│   │   └── generar_todos.py       # Genera boletines para todas las ubicaciones
│   └── tests/
│       ├── test_subagentes.py
│       ├── test_situational_briefing.py  # S4 — 20 tests
│       ├── test_weathernext2.py          # S3 WeatherNext 2 — 17 tests
│       ├── test_s1_glo30.py              # S1 GLO-30/TAGEE/AlphaEarth — 23 tests
│       ├── test_s2_earth_ai.py           # S2 Gemini multispectral — 15 tests
│       ├── test_req05_st_regionstats.py  # ST_REGIONSTATS — 19 tests
│       └── test_sistema_completo.py      # E2E (requiere credenciales GCP)
│
├── notebooks_validacion/          ← Validación académica (H1-H4)
│   ├── 01_validacion_f1_score.py
│   ├── 02_analisis_ablacion.py
│   ├── 03_comparacion_snowlab.py
│   ├── 04_confianza_cobertura.py
│   ├── 05_pruebas_estadisticas.py
│   ├── 06_analisis_nlp_sintetico.py     # H2 confirmada sintéticamente (+7.9pp)
│   ├── 07_validacion_slf_suiza.py        # H1/H3: SLF vs AndesAI (n=24 pares)
│   └── 08_validacion_snowlab.py          # H4: Snowlab La Parva (n=87 pares)
│
├── claude/                        ← Guías para sesiones de Claude Code
│   ├── CLAUDE.md
│   └── requirements/              ← 5 especificaciones técnicas REQ-01 a REQ-05
│
└── docs/                          ← Documentos de diseño y validación
    ├── marco_etico_legal.md
    └── validacion/
        ├── MAPPING_deapsnow.md
        └── reporte_calidad_datos_suizos.md
```

---

## Tablas BigQuery (`climas-chileno.clima.*`)

| Tabla | Estado | Descripción |
|-------|--------|-------------|
| `condiciones_actuales` | ✅ ~69.000 filas, 84 ubicaciones | Condiciones meteorológicas 3x/día (Open-Meteo + ERA5) |
| `pronostico_horas` | ✅ ~2.500 filas, 61 ubicaciones | Pronóstico horario 76h |
| `pronostico_dias` | ✅ ~17.000 filas, 63 ubicaciones | Pronóstico diario 10 días |
| `imagenes_satelitales` | ✅ ~406 filas | SAR (Sentinel-1) + NDSI (Sentinel-2) + ERA5-Land; Andes + Alpes Suizos |
| `zonas_avalancha` | ✅ 37 filas | Análisis topográfico GLO-30 mensual |
| `zonas_objetivo` | ✅ 4 zonas | Polígonos GEOGRAPHY para ST_REGIONSTATS; La Parva, Valle Nevado, etc. |
| `relatos_montanistas` | ✅ 3.131 rutas | Relatos Andeshandbook (37 campos) |
| `boletines_riesgo` | ✅ ~287 boletines | Output del sistema multi-agente (34 campos, Chile + Swiss) |
| `s2_comparaciones` | ✅ activa | A/B testing ViT vs Gemini multispectral |
| `pendientes_detalladas` | ✅ activa | GLO-30 + TAGEE (curvatura H/V) + AlphaEarth (embeddings 64D) |

**Dataset de validación** (`climas-chileno.validacion_avalanchas.*`):

| Tabla | Filas | Descripción |
|-------|-------|-------------|
| `slf_danger_levels_qc` | 45.049 | Ground truth EAWS niveles diarios SLF Suiza 2001-2024 |
| `slf_meteo_snowpack` | 29.296 | Datos estaciones IMIS suizas 2001-2020 |
| `slf_avalanchas_davos` | 13.918 | Eventos avalancha Davos |
| `snowlab_boletines` | 30 | Boletines Snowlab La Parva (Domingo Valdivieso Ducci L2 CAA, 2024-2025) |

---

## Hipótesis de investigación

| ID | Hipótesis | Métrica objetivo | Resultado | Estado |
|----|-----------|-----------------|-----------|--------|
| H1 | F1-score macro ≥ 75% en predicción EAWS 24-72h vs SLF Suiza | F1-macro | 0.191 (n=24) | ❌ Rechazada |
| H2 | NLP mejora precisión > 5pp vs sin NLP | Delta F1 ablación | +7.9pp | ✅ Confirmada (sintético) |
| H3 | QWK comparable a Techel et al. 2022 (kappa=0.59) vs SLF Suiza | QWK | 0.1087 (n=24) | ❌ Rechazada |
| H4 | ≥ 75% concordancia con Snowlab La Parva | QWK ≥ 0.60 | -0.016 (n=87) | ❌ Rechazada |

**Hallazgos publicables:**
- H1/H3: gap de dominio Andes→Alpes cuantificado; datos satelitales mejoran QWK +0.165 (de -0.056 a +0.1087)
- H4: sesgo asimétrico — AndesAI detecta tormentas (MAE=0.75, n=12) pero tiene piso en nivel 3 en condiciones de calma (MAE=2.32, n=75); causa: ausencia de modelo de estado del manto nivoso

---

## Instalación y uso local

```bash
# Requisitos
Python 3.11+
gcloud CLI autenticado (fpenailillom@correo.uss.cl)
ANTHROPIC_API_KEY  o  CLAUDE_CODE_OAUTH_TOKEN  (local)
# En producción: Databricks token leído desde GCP Secret Manager automáticamente

# Instalar dependencias
cd agentes
pip install -r despliegue/requirements.txt

# Generar un boletín
cd snow_alert
python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"

# Solo imprimir (sin guardar en BQ/GCS)
python agentes/scripts/generar_boletin.py --ubicacion "Valle Nevado" --solo-imprimir

# Listar ubicaciones disponibles
python agentes/scripts/generar_boletin.py --listar-ubicaciones

# Backfill satelital (región suiza u otras)
python agentes/datos/backfill/backfill_satelital.py --preset validacion_suiza --dry-run
```

## Tests

```bash
cd snow_alert

# Suite completa (sin credenciales externas)
python -m pytest agentes/tests/ -q
# → 256 passed, 8 skipped

# Por módulo
python -m pytest agentes/tests/test_situational_briefing.py -v   # S4
python -m pytest agentes/tests/test_weathernext2.py -v           # S3 WeatherNext 2
python -m pytest agentes/tests/test_s1_glo30.py -v               # S1 GLO-30/TAGEE/AlphaEarth
python -m pytest agentes/tests/test_s2_earth_ai.py -v            # S2 Gemini multispectral
python -m pytest agentes/tests/test_req05_st_regionstats.py -v   # ST_REGIONSTATS

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

## Estado del proyecto — Abril 2026

### ✅ Operacional
- 6 Cloud Functions activas recolectando datos 3x/día
- 5 subagentes implementados con agentic loop (S1–S5), todos los REQ-01 a REQ-05 completados
- 3.131 relatos Andeshandbook cargados en BigQuery (37 campos)
- Pipeline completo end-to-end en ~860s por lote de 10 ubicaciones
- LLM producción: Databricks/Qwen3-80B vía GCP Secret Manager
- Cloud Run Job `orquestador-avalanchas` desplegado
- ~287 boletines en BigQuery + GCS (Chile + Swiss, temporadas 2024-2025)
- 256 tests unitarios passing, 8 skipped (requieren credenciales GCP)
- Validación H1/H3 ejecutada vs SLF Suiza (n=24 pares); H4 ejecutada vs Snowlab La Parva (n=87 pares)
- Backfill satelital multi-región operativo (SAR Sentinel-1, MODIS/061, ERA5-Land, Sentinel-2)

### ⏳ Pendiente
- Activar `USE_WEATHERNEXT2=true` cuando llegue aprobación de Analytics Hub (S3)
- Activar `S2_VIA=ambas_consolidar_vit` para recolectar datos A/B temporada 2026 (S2)
- Capa de calibración post-procesamiento (isotonic regression) para reducir piso nivel 3 (H4)
- Integración datos snowpack in situ (NIVOLOG/CEAZA) como feature adicional para S5

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
│   │   ├── consultor_bigquery.py       # Acceso centralizado a tablas BQ
│   │   ├── constantes_zonas.py         # Fuente única de coordenadas/bbox/polígonos
│   │   ├── cliente_llm.py              # ClienteAnthropic + ClienteDatabricks (fallback)
│   │   └── backfill/
│   │       ├── backfill_clima_historico.py   # Backfill ERA5 para condiciones_actuales
│   │       ├── backfill_satelital.py         # Backfill SAR+MODIS+ERA5+S2 multi-región
│   │       ├── backfill_estado_manto_gee.py  # Backfill MODIS LST + SAR para estado_manto_gee
│   │       └── actualizar_glo30_tagee_ae.py  # Actualización GLO-30 + TAGEE + AlphaEarth
│   ├── subagentes/
│   │   ├── base_subagente.py      # Clase base con agentic loop, retries, logging
│   │   ├── subagente_topografico/ # S1: PINN + GLO-30 + TAGEE + AlphaEarth
│   │   │   └── tools/
│   │   │       ├── tool_analizar_dem.py        # DEM GLO-30, pendiente, aspecto, morfología
│   │   │       ├── tool_calcular_pinn.py        # Factor de seguridad + UQ Taylor
│   │   │       ├── tool_estabilidad_manto.py    # Score EAWS (very_poor → good)
│   │   │       ├── tool_zonas_riesgo.py         # Clasificación final nivel 1-5
│   │   │       ├── tool_tagee_terreno.py        # Curvatura H/V, northness, convergencia
│   │   │       └── tool_alphaearth.py           # Embeddings 64D AlphaEarth, drift interanual
│   │   ├── subagente_satelital/   # S2: ViT + SAR + MODIS LST + Gemini multispectral (A/B)
│   │   │   ├── schemas.py         # DeteccionSatelital con campo via (vit/gemini/rsfm)
│   │   │   ├── comparador/ab_runner.py  # ComparadorS2 — persiste en s2_comparaciones
│   │   │   └── tools/
│   │   │       ├── tool_analizar_vit.py          # ViT: anomalia_score, patron_detectado
│   │   │       ├── tool_procesar_ndsi.py         # Sentinel-2/MODIS: NDSI, cobertura nieve
│   │   │       ├── tool_snowline.py              # Línea de nieve, cambios 24h/72h
│   │   │       ├── tool_detectar_anomalias.py    # Detección de anomalías térmicas/nivales
│   │   │       ├── tool_estado_manto.py          # MODIS LST + SAR humedad (REQ-02a/02b)
│   │   │       └── tool_gemini_multispectral.py  # Gemini 2.5 multispectral (flag S2_VIA)
│   │   ├── subagente_meteorologico/ # S3: ConsolidadorMeteorologico multi-fuente
│   │   │   ├── fuentes/
│   │   │   │   ├── base.py                  # Interfaz FuenteMeteorologica
│   │   │   │   ├── fuente_open_meteo.py     # Fuente primaria (siempre activa)
│   │   │   │   ├── fuente_era5_land.py      # Reanálisis (siempre activa)
│   │   │   │   ├── fuente_weathernext2.py   # 64 miembros ensemble (flag USE_WEATHERNEXT2)
│   │   │   │   ├── correccion_orografica.py # Corrección ERA5 por altitud (calibrada Andes)
│   │   │   │   └── consolidador.py          # Fusión multi-fuente + detección divergencias
│   │   │   └── tools/
│   │   │       ├── tool_condiciones_actuales.py
│   │   │       ├── tool_pronostico_dias.py
│   │   │       ├── tool_tendencia_72h.py
│   │   │       ├── tool_ventanas_criticas.py
│   │   │       └── tool_pronostico_ensemble.py  # Expone ConsolidadorMeteorologico al agente
│   │   ├── subagente_situational_briefing/ # S4: briefing contextual (reemplaza NLP)
│   │   │   ├── agente.py          # AgenteSituationalBriefing (Qwen3-80B/Databricks)
│   │   │   ├── schemas.py         # SituationalBriefing, CondicionesRecientes, ContextoHistorico
│   │   │   ├── prompts/system_prompt.md
│   │   │   └── tools/
│   │   │       ├── tool_clima_reciente.py        # Condiciones 72h desde BQ
│   │   │       ├── tool_contexto_historico.py    # Época estacional + desviación histórica
│   │   │       ├── tool_caracteristicas_zona.py  # Constantes topográficas EAWS por zona
│   │   │       └── tool_eventos_pasados.py       # Histórico de avalanchas documentadas
│   │   └── subagente_integrador/  # S5: Matriz EAWS + boletín final
│   │       └── tools/
│   │           ├── tool_clasificar_eaws.py      # Aplica Matriz EAWS 2025
│   │           ├── tool_explicar_factores.py    # Justifica los 3 factores EAWS
│   │           ├── tool_generar_boletin.py      # Redacta boletín EAWS 24h/48h/72h
│   │           └── tool_historial_ubicacion.py  # Consulta boletines anteriores (REQ-01)
│   ├── orquestador/
│   │   └── agente_principal.py    # Coordina S1→S2→S3→S4→S5
│   ├── prompts/
│   │   └── registro_versiones.py  # Hashes SHA-256 de prompts + VERSION_GLOBAL (v4.0)
│   ├── salidas/
│   │   ├── almacenador.py         # DELETE+INSERT idempotente en BQ; upload GCS
│   │   └── schema_boletines.json  # Schema 34 campos (particionado por fecha_emision)
│   ├── validacion/
│   │   ├── metricas_eaws.py           # F1-macro, Kappa, QWK, Techel 2022
│   │   └── mapeo_estaciones_slf.py    # Mapeo estaciones AndesAI → sector_id SLF (REQ-04)
│   ├── diagnostico/
│   │   └── revisar_datos.py       # Health check de tablas BQ y disponibilidad de datos
│   ├── despliegue/
│   │   ├── Dockerfile
│   │   ├── cloudbuild.yaml
│   │   ├── job_cloud_run.yaml
│   │   └── requirements.txt
│   ├── scripts/
│   │   ├── generar_boletin.py          # CLI para generar un boletín individual
│   │   ├── generar_todos.py            # Genera boletines para todas las ubicaciones
│   │   └── generar_boletines_invierno.py  # Genera serie histórica de invierno
│   └── tests/
│       ├── test_subagentes.py
│       ├── test_tools.py
│       ├── test_boletin_completo.py
│       ├── test_situational_briefing.py  # S4 — 20 tests
│       ├── test_weathernext2.py          # S3 WeatherNext 2 — 17 tests
│       ├── test_s1_glo30.py              # S1 GLO-30/TAGEE/AlphaEarth — 23 tests
│       ├── test_s2_earth_ai.py           # S2 Gemini multispectral — 15 tests
│       ├── test_req01_persistencia_temporal.py  # REQ-01 (calma sostenida) — 12 tests
│       ├── test_req02a_estado_manto_gee.py      # REQ-02a MODIS LST — 10 tests
│       ├── test_req02b_sar_humedad.py           # REQ-02b SAR humedad — 10 tests
│       ├── test_req03_correccion_orografica.py  # REQ-03 ERA5 orográfico — 15 tests
│       ├── test_req04_mapeo_slf.py              # REQ-04 mapeo SLF — 10 tests
│       ├── test_req05_st_regionstats.py         # ST_REGIONSTATS — 19 tests
│       └── test_sistema_completo.py             # E2E (requiere credenciales GCP)
│
├── notebooks_validacion/          ← Validación académica (H1-H4)
│   ├── 01_validacion_f1_score.py
│   ├── 02_analisis_ablacion.py
│   ├── 03_comparacion_snowlab.py
│   ├── 04_confianza_cobertura.py
│   ├── 05_pruebas_estadisticas.py
│   ├── 06_analisis_nlp_sintetico.py     # H2 confirmada sintéticamente (+7.9pp)
│   ├── 07_validacion_slf_suiza.py        # H1/H3: SLF vs AndesAI (n=24 pares)
│   ├── 08_validacion_snowlab.py          # H4: Snowlab La Parva (n=90 pares)
│   ├── cargar_snowlab_bq.py              # Carga inicial snowlab_boletines a BQ
│   ├── reprocesar_retroactivo.py         # Replay retroactivo 120 runs para Ronda 3
│   ├── baseline_v32_ronda2.json          # Métricas v3.2 preservadas (referencia permanente)
│   └── RESULTADOS_VALIDACION.md          # Resultados Ronda 1-3 H1/H3/H4
│
├── claude/                        ← Guías para sesiones de Claude Code
│   ├── CLAUDE.md
│   ├── log_claude.md              # Historial de sesiones y decisiones
│   └── requirements/              ← Especificaciones técnicas (todas implementadas)
│       ├── Mejoras04_v1.md        # REQ-01 a REQ-04 (v4.0)
│       ├── 01-s4-situational-briefing.md
│       ├── 02-s3-weathernext-aditivo.md
│       ├── 03-s1-alphaearth-pinn.md
│       ├── 04-s2-rsfm-paralelo.md
│       └── 05-cross-cutting-bigquery-st.md
│
└── docs/                          ← Documentos de diseño y validación académica
    ├── marco_etico_legal.md
    ├── propuesta_tesina_fpenailillo.pdf
    ├── papers-relevantes/         # Techel 2022, EAWS matrix, PINNs, etc.
    └── validacion/
        ├── EDA_DATOS_VALIDACION.md         # EDA completo de todas las tablas BQ
        ├── RESULTADOS_VALIDACION.md        # Métricas Ronda 1-3 (copia en docs/)
        ├── baseline_v32_ronda2.json        # Métricas v3.2 preservadas
        ├── MAPPING_deapsnow.md
        ├── reporte_calidad_datos_suizos.md
        └── reporte_validacion_andesai_2026.md
```

---

## Tablas BigQuery (`climas-chileno.clima.*`)

| Tabla | Filas | Descripción |
|-------|------:|-------------|
| `condiciones_actuales` | 77,480 | Condiciones meteorológicas 3x/día (Open-Meteo + ERA5) — 92 ubicaciones |
| `pronostico_horas` | 201,563 | Pronóstico horario hasta 14 días — 71 ubicaciones |
| `pronostico_dias` | 42,353 | Pronóstico diario con separación diurno/nocturno — 71 ubicaciones |
| `imagenes_satelitales` | 3,555 | GOES-18 + SAR Sentinel-1 + ERA5-Land; 15 zonas andinas |
| `zonas_objetivo` | 4 | Polígonos GEOGRAPHY La Parva / Valle Nevado / El Colorado |
| `zonas_avalancha` | activa | Análisis topográfico GLO-30 mensual |
| `relatos_montanistas` | 3,131 | Relatos Andeshandbook (37 campos) |
| `boletines_riesgo` | 427 | Output del sistema multi-agente (34 campos, Chile + Swiss, v3.1/v3.2/v4.0) |
| `estado_manto_gee` | ❌ pendiente | MODIS LST + SAR humedad desde GEE (REQ-02a/02b — tabla aún no creada) |
| `s2_comparaciones` | activa | A/B testing ViT vs Gemini multispectral |
| `pendientes_detalladas` | activa | GLO-30 + TAGEE (curvatura H/V) + AlphaEarth (embeddings 64D) |

**Dataset de validación** (`climas-chileno.validacion_avalanchas.*`, región US):

| Tabla | Filas | Descripción |
|-------|------:|-------------|
| `slf_danger_levels_qc` | 45,049 | Ground truth EAWS niveles diarios SLF Suiza 2001-2024 |
| `slf_meteo_snowpack` | 29,296 | Datos estaciones IMIS suizas 2001-2020 |
| `slf_avalanchas_davos` | 13,918 | Eventos avalancha Davos |
| `snowlab_boletines` | 30 | Boletines Snowlab La Parva (Domingo Valdivieso Ducci L2 CAA, 2024-2025) |

---

## Hipótesis de investigación

| ID | Hipótesis | Métrica objetivo | v3.2 (Ronda 2) | v4.0 (Ronda 3) | Estado |
|----|-----------|-----------------|----------------|----------------|--------|
| H1 | F1-macro ≥ 75% vs SLF Suiza | F1-macro ≥ 0.75 | 0.161 (n=24) | 0.155 (n=24) | ❌ Rechazada |
| H2 | NLP mejora > 5pp vs sin NLP | Delta F1 ablación | +7.9pp | — | ✅ Confirmada (sintético) |
| H3 | QWK ≥ 0.59 (Techel 2022) vs SLF | QWK ≥ 0.59 | +0.016 (n=24) | +0.162 (n=24) | ❌ Rechazada |
| H4 | QWK ≥ 0.60 vs Snowlab La Parva | QWK ≥ 0.60 | −0.016 (n=90) | −0.006 (n=90) | ❌ Rechazada |

**Hallazgos publicables (Ronda 3 v4.0):**
- H1/H3: QWK mejoró +0.146 con REQ-02a/02b (MODIS LST + SAR humedad); sesgo regresó −0.92 porque REQ-03 (corrección orográfica ERA5) está calibrado para Andes, no para Alpes
- H4: piso nivel 3 causado por S1 (riesgo topográfico inherente a La Parva) + S3 (`FUSION_ACTIVA` por ciclo diurno); REQ-01 funciona pero nunca se activa porque S1/S3 upstream generan nivel 3 incluso sin eventos
- Gap de dominio Andes→Alpes documentado y cuantificado — publicable como hallazgo metodológico

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
# → 334 passed, 8 skipped

# Por módulo
python -m pytest agentes/tests/test_situational_briefing.py -v   # S4 — 20 tests
python -m pytest agentes/tests/test_weathernext2.py -v           # S3 WeatherNext 2 — 17 tests
python -m pytest agentes/tests/test_s1_glo30.py -v               # S1 GLO-30/TAGEE/AlphaEarth
python -m pytest agentes/tests/test_s2_earth_ai.py -v            # S2 Gemini multispectral
python -m pytest agentes/tests/test_req01_persistencia_temporal.py -v  # REQ-01
python -m pytest agentes/tests/test_req02a_estado_manto_gee.py -v      # REQ-02a MODIS LST
python -m pytest agentes/tests/test_req02b_sar_humedad.py -v           # REQ-02b SAR
python -m pytest agentes/tests/test_req03_correccion_orografica.py -v  # REQ-03 ERA5 orográfico
python -m pytest agentes/tests/test_req04_mapeo_slf.py -v              # REQ-04 mapeo SLF
python -m pytest agentes/tests/test_req05_st_regionstats.py -v         # ST_REGIONSTATS

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

## Estado del proyecto — Mayo 2026

### ✅ Operacional
- 6 Cloud Functions activas recolectando datos 3x/día
- 5 subagentes implementados con agentic loop (S1–S5), REQ-01 a REQ-05 completados (v4.0)
- 3,131 relatos Andeshandbook cargados en BigQuery (37 campos)
- Pipeline completo end-to-end en ~120s por boletín individual
- LLM producción: Databricks/Qwen3-80B vía GCP Secret Manager
- Cloud Run Job `orquestador-avalanchas` desplegado
- 427 boletines en BigQuery + GCS (Chile + Swiss, v3.1/v3.2/v4.0)
- 334 tests unitarios passing, 8 skipped (requieren credenciales GCP)
- Validación Ronda 3 completada: H1/H3 vs SLF Suiza (n=24), H4 vs Snowlab La Parva (n=90)
- Backfill satelital multi-región operativo (SAR Sentinel-1, MODIS/061, ERA5-Land, Sentinel-2)
- EDA completo de tablas BQ documentado en `docs/validacion/EDA_DATOS_VALIDACION.md`

### ⏳ Pendiente
- Activar `USE_WEATHERNEXT2=true` cuando se apruebe suscripción Analytics Hub (~2026-05-05)
- Crear tabla `estado_manto_gee` en BQ y ejecutar backfill (`backfill_estado_manto_gee.py`)
- Fix H4: corregir upstream S1 (riesgo topográfico potencial vs activo) y S3 (`FUSION_ACTIVA` sin precipitación) para desbloquear REQ-01
- Capa de calibración post-procesamiento (isotonic regression) como alternativa al fix upstream

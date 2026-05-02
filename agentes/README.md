# Sistema Multi-Agente de Predicción de Avalanchas

Sistema basado en Qwen3-80B vía Databricks (producción) o Claude/Anthropic (local) que genera boletines de riesgo EAWS (niveles 1-5) en español, consultando datos de BigQuery desde el proyecto `climas-chileno`.

## Arquitectura

```
Orquestador (agente_principal.py)
    │
    ├── S1: SubagenteTopografico ──────→ zonas_avalancha + pendientes_detalladas (GLO-30, TAGEE, AlphaEarth)
    ├── S2: SubagenteSatelital ────────→ imagenes_satelitales (SAR, NDSI, ViT, Gemini A/B)
    ├── S3: SubagenteMeteorologico ────→ condiciones_actuales + pronostico_* (Open-Meteo, ERA5, WeatherNext2)
    ├── S4: AgenteSituationalBriefing ─→ situational briefing contextual (Qwen3-80B)
    └── S5: SubagenteIntegrador ───────→ Boletín EAWS 24h/48h/72h (Matriz Müller-Techel 2025)
    │
    ▼
almacenador.py
    ├── BigQuery: clima.boletines_riesgo (34 campos)
    └── GCS: gs://climas-chileno-datos-clima-bronce/boletines/
```

## Requisitos

- Python 3.11+
- GCP con Application Default Credentials: `gcloud auth application-default login`
- Variable de entorno `DATABRICKS_TOKEN` (producción: Secret Manager) o `ANTHROPIC_API_KEY` (local)
- Paquetes: ver `despliegue/requirements.txt`

## Instalación

```bash
cd ~/Desktop/avalanche_report/snow_alert/agentes
pip install -r despliegue/requirements.txt
gcloud auth application-default login
```

## Uso

### Boletín individual

```bash
# Desde la raíz del repo (snow_alert/)
python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"

# Solo imprimir (sin guardar en BigQuery/GCS)
python agentes/scripts/generar_boletin.py --ubicacion "Valle Nevado" --solo-imprimir

# Boletín para fecha histórica
python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Alto" --fecha 2024-08-15

# Listar ubicaciones con datos disponibles
python agentes/scripts/generar_boletin.py --listar-ubicaciones

# Salida en formato JSON
python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo" --json
```

### Boletines masivos

```bash
# Generar para todas las ubicaciones y guardar (default)
python agentes/scripts/generar_todos.py

# Generar para una fecha histórica sin backfill ERA5
python agentes/scripts/generar_todos.py --fecha 2024-08-15 --sin-backfill

# Preset específico de ubicaciones
python agentes/scripts/generar_todos.py --preset laparva
```

### Backfill de datos satelitales

```bash
# Backfill para estaciones de validación suiza (dry-run)
python agentes/datos/backfill/backfill_satelital.py --preset validacion_suiza --dry-run

# Backfill para La Parva (todas las fuentes disponibles)
python agentes/datos/backfill/backfill_satelital.py --preset laparva --fuentes sar modis era5 s2

# Backfill ERA5 para fechas históricas
python agentes/datos/backfill/backfill_clima_historico.py
```

## Tests

```bash
# Suite completa (sin credenciales externas)
python -m pytest agentes/tests/ -q
# → 334 passed, 8 skipped

# Por subagente / requerimiento
python -m pytest agentes/tests/test_situational_briefing.py -v          # S4 — 20 tests
python -m pytest agentes/tests/test_weathernext2.py -v                  # S3 WeatherNext 2 — 17 tests
python -m pytest agentes/tests/test_s1_glo30.py -v                      # S1 GLO-30/TAGEE/AlphaEarth — 23 tests
python -m pytest agentes/tests/test_s2_earth_ai.py -v                   # S2 Gemini multispectral — 15 tests
python -m pytest agentes/tests/test_req01_persistencia_temporal.py -v   # REQ-01 calma sostenida — 12 tests
python -m pytest agentes/tests/test_req02a_estado_manto_gee.py -v       # REQ-02a MODIS LST — 10 tests
python -m pytest agentes/tests/test_req02b_sar_humedad.py -v            # REQ-02b SAR humedad — 10 tests
python -m pytest agentes/tests/test_req03_correccion_orografica.py -v   # REQ-03 ERA5 orográfico — 15 tests
python -m pytest agentes/tests/test_req04_mapeo_slf.py -v               # REQ-04 mapeo SLF — 10 tests
python -m pytest agentes/tests/test_req05_st_regionstats.py -v          # ST_REGIONSTATS — 19 tests

# Test E2E (requiere ANTHROPIC_API_KEY o Databricks token)
python -m pytest agentes/tests/test_sistema_completo.py -v -s
```

## Estructura de archivos

```
agentes/
├── datos/
│   ├── consultor_bigquery.py          # Acceso centralizado a BigQuery (retorna dict)
│   ├── constantes_zonas.py            # COORDENADAS_ZONAS, BBOX_ZONAS, POLIGONOS_ZONAS — fuente única
│   ├── cliente_llm.py                 # ClienteAnthropic + ClienteDatabricks (fallback)
│   └── backfill/
│       ├── backfill_clima_historico.py    # ERA5 histórico para condiciones_actuales
│       ├── backfill_satelital.py          # SAR+MODIS+ERA5+S2 multi-región (idempotente)
│       ├── backfill_estado_manto_gee.py   # MODIS LST + SAR para tabla estado_manto_gee
│       └── actualizar_glo30_tagee_ae.py   # Actualización GLO-30 + TAGEE + AlphaEarth
│
├── subagentes/
│   ├── base_subagente.py              # Clase base: agentic loop, retries, logging
│   │
│   ├── subagente_topografico/         # S1: Análisis físico del terreno
│   │   ├── agente.py
│   │   └── tools/
│   │       ├── tool_analizar_dem.py       # DEM GLO-30, pendiente, aspecto, morfología
│   │       ├── tool_calcular_pinn.py      # Factor de seguridad Mohr-Coulomb + UQ Taylor
│   │       ├── tool_estabilidad_manto.py  # Score EAWS de estabilidad del manto
│   │       ├── tool_zonas_riesgo.py       # Clasificación de zonas de riesgo nivel 1-5
│   │       ├── tool_tagee_terreno.py      # Curvatura H/V, northness/eastness, convergencia
│   │       └── tool_alphaearth.py         # Embeddings 64D AlphaEarth, drift interanual
│   │
│   ├── subagente_satelital/           # S2: Análisis satelital multi-fuente
│   │   ├── agente.py
│   │   ├── schemas.py                 # DeteccionSatelital (via: vit/gemini/rsfm)
│   │   ├── comparador/
│   │   │   └── ab_runner.py           # ComparadorS2: A/B ViT vs Gemini → s2_comparaciones
│   │   └── tools/
│   │       ├── tool_analizar_vit.py          # Vision Transformer: anomalia_score, patron
│   │       ├── tool_procesar_ndsi.py         # Sentinel-2/MODIS: NDSI, cobertura nieve
│   │       ├── tool_snowline.py              # Línea de nieve, cambios 24h/72h
│   │       ├── tool_detectar_anomalias.py    # Detección de anomalías térmicas/nivales
│   │       ├── tool_estado_manto.py          # MODIS LST + SAR humedad (REQ-02a/02b)
│   │       └── tool_gemini_multispectral.py  # Gemini 2.5 multispectral (flag S2_VIA)
│   │
│   ├── subagente_meteorologico/       # S3: Meteorología multi-fuente
│   │   ├── agente.py
│   │   ├── fuentes/
│   │   │   ├── base.py                    # Interfaz FuenteMeteorologica + PronosticoMeteorologico
│   │   │   ├── fuente_open_meteo.py       # Fuente primaria (siempre activa)
│   │   │   ├── fuente_era5_land.py        # Reanálisis ERA5-Land (siempre activa)
│   │   │   ├── fuente_weathernext2.py     # 64 miembros ensemble (flag USE_WEATHERNEXT2)
│   │   │   ├── correccion_orografica.py   # Corrección ERA5 por altitud (calibrada para Andes)
│   │   │   └── consolidador.py            # Fusión multi-fuente + detección divergencias >3°C/50%
│   │   └── tools/
│   │       ├── tool_condiciones_actuales.py
│   │       ├── tool_pronostico_dias.py
│   │       ├── tool_tendencia_72h.py
│   │       ├── tool_ventanas_criticas.py
│   │       └── tool_pronostico_ensemble.py  # Expone ConsolidadorMeteorologico al agente
│   │
│   ├── subagente_situational_briefing/ # S4: Briefing situacional contextual
│   │   ├── agente.py                   # AgenteSituationalBriefing (Qwen3-80B/Databricks)
│   │   ├── schemas.py                  # SituationalBriefing, CondicionesRecientes, ContextoHistorico
│   │   ├── prompts/
│   │   │   └── system_prompt.md
│   │   └── tools/
│   │       ├── tool_clima_reciente.py        # Condiciones 72h desde condiciones_actuales
│   │       ├── tool_contexto_historico.py    # Época estacional + desviación vs promedio ERA5
│   │       ├── tool_caracteristicas_zona.py  # Constantes topográficas EAWS por zona
│   │       └── tool_eventos_pasados.py       # Histórico de avalanchas documentadas
│   │
│   └── subagente_integrador/          # S5: Matriz EAWS 2025 + boletín final
│       ├── agente.py
│       └── tools/
│           ├── tool_clasificar_eaws.py       # Aplica Matriz EAWS 2025 (Müller, Techel & Mitterer)
│           ├── tool_explicar_factores.py     # Justifica los 3 factores EAWS (estabilidad, frecuencia, tamaño)
│           ├── tool_generar_boletin.py       # Redacta boletín EAWS 24h/48h/72h
│           └── tool_historial_ubicacion.py   # Consulta boletines anteriores (REQ-01 persistencia)
│
├── orquestador/
│   └── agente_principal.py            # Coordina S1→S2→S3→S4→S5; manejo de degradación graceful
│
├── prompts/
│   └── registro_versiones.py          # Hashes SHA-256 de prompts + VERSION_GLOBAL (actualmente v4.0)
│
├── salidas/
│   ├── almacenador.py                 # DELETE+INSERT idempotente en BQ; upload GCS
│   └── schema_boletines.json          # Schema 34 campos (particionado por fecha_emision)
│
├── validacion/
│   ├── metricas_eaws.py               # F1-macro, Cohen's Kappa, QWK, Techel 2022
│   └── mapeo_estaciones_slf.py        # Mapeo estación AndesAI → sector_id SLF (REQ-04)
│
├── diagnostico/
│   └── revisar_datos.py               # Health check tablas BQ y disponibilidad de datos
│
├── scripts/
│   ├── generar_boletin.py             # CLI por ubicación individual
│   ├── generar_todos.py               # Genera boletines para preset de ubicaciones
│   └── generar_boletines_invierno.py  # Genera serie histórica de invierno completa
│
├── despliegue/
│   ├── Dockerfile
│   ├── cloudbuild.yaml
│   ├── job_cloud_run.yaml
│   └── requirements.txt
│
└── tests/
    ├── test_subagentes.py
    ├── test_tools.py
    ├── test_boletin_completo.py
    ├── test_conexion.py
    ├── test_fase0_datos.py
    ├── test_situational_briefing.py          # 20 tests — S4
    ├── test_weathernext2.py                  # 17 tests — S3 WeatherNext 2
    ├── test_s1_glo30.py                      # 23 tests — S1 GLO-30/TAGEE/AlphaEarth
    ├── test_s2_earth_ai.py                   # 15 tests — S2 Gemini multispectral
    ├── test_req01_persistencia_temporal.py   # 12 tests — REQ-01 calma sostenida
    ├── test_req02a_estado_manto_gee.py        # 10 tests — REQ-02a MODIS LST
    ├── test_req02b_sar_humedad.py             # 10 tests — REQ-02b SAR humedad
    ├── test_req03_correccion_orografica.py    # 15 tests — REQ-03 ERA5 orográfico
    ├── test_req04_mapeo_slf.py                # 10 tests — REQ-04 mapeo SLF
    ├── test_req05_st_regionstats.py           # 19 tests — ST_REGIONSTATS
    └── test_sistema_completo.py               # E2E (requiere credenciales GCP)
```

## Subagentes — descripción técnica

### S1 — Subagente Topográfico

Calcula el factor de seguridad (FS) del manto nival usando PINNs con datos de Copernicus GLO-30 (DEM 30m), atributos TAGEE (curvatura horizontal/vertical, northness/eastness, zonas de convergencia de runout) y embeddings AlphaEarth (64 dimensiones multi-sensor, señal de cambio interanual). Aplica UQ Taylor para IC 95% del FS. El drift interanual de AlphaEarth activa alerta de incertidumbre sin modificar el FS.

### S2 — Subagente Satelital

Analiza el estado del manto desde tres vías:
- **ViT** (siempre activo): Vision Transformer con multi-head attention H=2, entrenado sobre parches MODIS/Sentinel-2
- **SAR Sentinel-1**: detección de nieve húmeda (VV < -15 dB = húmeda, -15 a -8 dB = seca, Nagler et al. 2016)
- **Gemini 2.5 multispectral** (flag `S2_VIA=ambas_*`): análisis cualitativo paralelo para A/B testing; resultados persisten en `s2_comparaciones`

### S3 — Subagente Meteorológico

`ConsolidadorMeteorologico` fusiona tres fuentes con patrón Strategy:
- **Open-Meteo**: fuente primaria, siempre activa
- **ERA5-Land**: reanálisis, siempre activo
- **WeatherNext 2** (flag `USE_WEATHERNEXT2=true`): 64 miembros ensemble vía BigQuery Analytics Hub; calcula P10/P50/P90; detecta divergencias >3°C temperatura o >50% precipitación

### S4 — AgenteSituationalBriefing

Reemplaza el antiguo subagente NLP de relatos. Genera un briefing situacional estructurado (`SituationalBriefing`) con 4 tools:
- `tool_clima_reciente`: condiciones 72h desde `condiciones_actuales`
- `tool_contexto_historico`: época estacional + desviación vs promedio histórico ERA5
- `tool_caracteristicas_zona`: constantes topográficas EAWS por zona
- `tool_eventos_pasados`: histórico de eventos avalancha documentados

Output: narrativa 150-300 palabras + lista de factores EAWS + estimación cualitativa de riesgo. Mantiene compatibilidad con S5 a través de campos heredados.

### S5 — Subagente Integrador

Aplica la Matriz EAWS 2025 (Müller, Techel & Mitterer) integrando los outputs de S1-S4. Genera el boletín final con niveles 24h/48h/72h, horizonte de 5 días, tipo de problema predominante y factores contribuyentes. Redacción en español de Chile con terminología EAWS estándar.

## Factores EAWS

El integrador determina 3 factores para aplicar la matriz EAWS:

| Factor | Fuente principal |
|--------|-----------------|
| **Estabilidad** | S1 (FS + clase_estabilidad_eaws) + S2 (alertas satelitales) + S3 (ventanas críticas) |
| **Frecuencia** | `frecuencia_estimada_eaws` + ajuste eólico dinámico |
| **Tamaño** | `tamano_estimado_eaws` + corrección por condiciones de humedad |

## Variables de entorno relevantes

| Variable | Default | Descripción |
|----------|---------|-------------|
| `USE_WEATHERNEXT2` | `false` | Activa WeatherNext 2 en S3 |
| `S2_VIA` | `vit_actual` | Vía satelital S2: `vit_actual`, `ambas_consolidar_vit`, `ambas_consolidar_gemini` |
| `DATABRICKS_TOKEN` | — | Token Databricks (producción desde Secret Manager) |
| `ANTHROPIC_API_KEY` | — | API key Anthropic (uso local) |

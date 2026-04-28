# CLAUDE.md — snow_alert — Sistema Multi-Agente Predicción Avalanchas

> **Skills disponibles**:
> - `snow-alert-dev/SKILL.md` — Framework de desarrollo (7 flujos)
> - `eaws-methodology/SKILL.md` — Metodología EAWS 2025 (matriz, factores, workflow)
> **Log**: `log_claude.md` — Registro detallado de todo lo hecho por sesión.

---

## Inicio rápido de sesión

```bash
# 1. Leer log de progreso (últimas 60 líneas)
tail -60 log_claude.md 2>/dev/null || echo "log_claude.md no existe aún"

# 2. Leer skill si la tarea lo requiere
cat snow-alert-dev/SKILL.md 2>/dev/null | head -80

# 3. Tests
cd snow_alert && python -m pytest agentes/tests/test_subagentes.py -v --tb=short -q 2>&1 | tail -10

# 4. Reportar estado ANTES de escribir código
```

---

## Proyecto

| Campo | Valor |
|-------|-------|
| Proyecto GCP | `climas-chileno` |
| Dataset BQ | `clima` |
| Bucket GCS | `climas-chileno-datos-clima-bronce` |
| Región | `us-central1` |
| Cloud Run Job | `orquestador-avalanchas` |
| LLM producción | Databricks/Qwen3-80B (Secret Manager) |

---

## Estructura

```
snow_alert/
├── claude/CLAUDE.md           ← ESTE ARCHIVO (guía de sesión)
├── log_claude.md              ← Log de progreso detallado por sesión
├── snow-alert-dev/            ← Skill: desarrollo (7 flujos, scripts health-check)
│   ├── SKILL.md               ← 7 flujos (diagnóstico, agentes, datos, validación, despliegue, docs, tesina)
│   ├── references/            ← 7 guías especializadas (bajo demanda)
│   └── scripts/               ← verificar_proyecto.py, actualizar_progreso.py
├── eaws-methodology/          ← Skill: metodología EAWS 2025 (matriz, factores, workflow)
│   ├── SKILL.md               ← 3 factores, 5 niveles, workflow 7 pasos, mapeo AndesAI
│   └── references/            ← eaws_matrix_2025.md, evidencia_estabilidad.md
├── datos/                     ← Cloud Functions GCP (NO modificar sin confirmación)
├── agentes/                   ← Sistema multi-agente (aquí trabajamos)
│   ├── datos/consultor_bigquery.py
│   ├── subagentes/{topografico,satelital,meteorologico,nlp,integrador}/
│   ├── orquestador/agente_principal.py
│   ├── salidas/almacenador.py + schema_boletines.json (33 campos)
│   ├── validacion/metricas_eaws.py
│   ├── despliegue/Dockerfile + cloudbuild.yaml
│   └── tests/
├── notebooks_validacion/      ← H1-H4
└── docs/                      ← Decisiones de diseño, ética, arquitectura
```

---

## Reglas de código

- **Todo en español**: variables, funciones, clases, comentarios, docstrings, logs
- `ConsultorBigQuery` retorna `dict` (nunca DataFrame)
- Logging: `[NombreSubagente] operación → resultado`
- Nulos: nunca fallar silenciosamente → `{"dato_nulo": True, "razon_nulo": "..."}`
- EAWS: importar de `datos/analizador_avalanchas/eaws_constantes.py` (no duplicar)
- Credenciales: Secret Manager o env vars (nunca hardcodeadas)
- Tests: deben correr sin GCP auth ni API key
- `log_claude.md`: **SIEMPRE** actualizar al terminar cada tarea significativa

---

## Pipeline: S1→S2→S3→S4→S5

| # | Subagente | Técnica | Output |
|---|-----------|---------|--------|
| S1 | Topográfico | PINNs + DEM SRTM + UQ Taylor | `clase_estabilidad_eaws`, IC 95% FS |
| S2 | Satelital | ViT (H=2, MHA) + MODIS | `alertas_satelitales`, `anomalia_score` |
| S3 | Meteorológico | Google Weather API | `ventanas_criticas` |
| S4 | NLP | Relatos + base andina 15 zonas | `indice_riesgo_historico` |
| S5 | Integrador | Matriz EAWS 2025 | Boletín 24h/48h/72h |

S4 es no-crítico: si falla, pipeline continúa con `subagentes_degradados`.

---

## Comandos frecuentes

```bash
# Tests
python -m pytest agentes/tests/test_subagentes.py -v -k "TestTools"

# Boletín
python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"

# Desplegar agentes
gcloud builds submit --config agentes/despliegue/cloudbuild.yaml --project=climas-chileno

# Ejecutar job
gcloud run jobs execute orquestador-avalanchas --region=us-central1

# Health check rápido
python snow-alert-dev/scripts/verificar_proyecto.py --solo-local

# Ver boletines
bq query --use_legacy_sql=false \
  "SELECT nombre_ubicacion, nivel_eaws_24h, confianza
   FROM climas-chileno.clima.boletines_riesgo ORDER BY fecha_emision DESC LIMIT 10"
```

---

## Hipótesis

| ID | Métrica | Umbral | Estado |
|----|---------|--------|--------|
| H1 | F1-macro EAWS | ≥75% | ⚠️ 0.197 con Swiss SLF — requiere Snowlab La Parva (datos meteo ERA5 ausentes en Swiss) |
| H2 | Delta NLP | >5pp | ✅ +7.9pp (sintético, notebook 06) |
| H3 | Transfer SLF | QWK Techel 2022 | ⚠️ QWK=-0.056 Swiss — gap dominio documentado (sesgo -0.79 por falta ERA5 Swiss) |
| H4 | vs Snowlab | Kappa≥0.60 | ❌ Bloqueada (snowlab_boletines = 0 rows en BQ) |

**Dataset validación suiza (H1/H3) — EJECUTADO 2026-04-28:**
- Ground truth: `climas-chileno.validacion_avalanchas.slf_danger_levels_qc` (45k filas, 2001-2024)
- Mapeo: Interlaken→canton Bern(4xxx), Zermatt→Valais(2xxx), St Moritz→Graubünden(6xxx)
- Boletines: 30/30 pares en BQ. Emparejados: 24/30 (6 sin datos SLF en esas fechas)
- Resultado: F1=0.197, QWK=-0.056 — sesgo sistemático de subestimación (-0.79 niveles)
- Causa: ERA5 Swiss ausente para invierno 2023-2024 → S3 sin datos → niveles bajos
- Conclusión: H1/H3 requieren validación con Snowlab La Parva (ERA5 disponible allí)
- Script validación: `notebooks_validacion/07_validacion_slf_suiza.py`

## Marco Teórico — Auditoría (2026-03-17)

| Dimensión | Score | Estado |
|-----------|-------|--------|
| 1. Arquitectura Multi-Agente | 10/10 | ✅ |
| 2. PINNs (manto nival) | 9/10 | ✅ gradiente LST real + UQ Taylor IC 95% |
| 3. Vision Transformers | 8/10 | ✅ MHA H=2, Xavier, PE sinusoidal |
| 4. Escala EAWS + Matriz | 9/10 | ✅ tamaño dinámico + ajuste viento |
| 5. NLP Relatos | 8/10 | ✅ fallback 15 zonas andinas + H2 sintética |
| 6. Infraestructura Serverless | 9/10 | ✅ |
| 7. Métricas de Validación | 9/10 | ✅ F1, Kappa, QWK, Techel, bootstrap |
| 8. Marco Ético-Legal | 9/10 | ✅ docs/marco_etico_legal.md + D12 |
| **Total** | **71/80** | **ALTA** |

Brechas B1–B11: todas cerradas. Pendiente solo: ≥50 boletines reales para H1/H4.

---

## Fases

```
✅ Fase -1  Reorganizar repositorio
✅ Fase  0  Diagnosticar datos nulos
✅ Fase  1  Cargar relatos (3,131 rutas)
✅ Fase  2  5 subagentes construidos (REQ-01 a REQ-05 completados)
✅ Fase  3  Archivos despliegue Cloud Run
✅ Fase  4  Schema boletines 33 campos (confirmado BQ 2026-03-18)
✅ Fase  5  Tests actualizados (260 passed, 8 skipped — 2026-04-01)
✅ Fase  6  212 boletines + reprocesados Chile con fixes metodológicos
✅ Fase  7  Validación H1/H3 con SLF ejecutada — gap dominio documentado (F1=0.197)
⏳ Fase  8  Validación H1/H4 con Snowlab La Parva (requiere datos usuario)
```

**Regla de oro: no avanzar de fase sin que los tests pasen.**

## Requerimientos implementados

| # | Requerimiento | Estado | Commit |
|---|---|---|---|
| REQ-01 | S4 Situational Briefing (Qwen3-80B/Databricks) | ✅ | 9e4ae33 |
| REQ-02 | S3 WeatherNext 2 aditivo (pendiente suscripción) | ✅ código | fe79532 |
| REQ-03 | S1 AlphaEarth + GLO-30 + TAGEE | ✅ | fcc079a |
| REQ-04 | S2 vía Earth AI paralela al ViT | ✅ | fcc079a |
| REQ-05 | BigQuery ST_REGIONSTATS + zonas_objetivo | ✅ | 218faa1 |
| — | Fix metodológico: metamorfismo estático | ✅ | a444a02 |
| — | Fix: viento(15→10 m/s), ciclo fusión, tamaño EAWS | ✅ | c1d6812 |

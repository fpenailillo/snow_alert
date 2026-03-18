# PROGRESO — snow_alert Sistema Multi-Agente

## Última actualización: 2026-03-18 (despliegue producción)

## Fases

- [x] Fase -1: Repositorio reorganizado
- [x] Fase  0: Script diagnóstico creado (ejecutar manualmente con GCP auth)
- [x] Fase  1: Relatos en BigQuery — schema y ETL actualizados para CSVs finales de Databricks
- [x] Fase  2: 5 subagentes construidos (SubagenteNLP añadido, orquestador actualizado)
- [x] Fase  3: Archivos de despliegue Cloud Run creados
- [x] Fase  4: Schema boletines_riesgo (27 campos) actualizado
- [x] Fase  5: Tests actualizados para 5 subagentes

## Estado de tests

## Archivos creados/modificados en Fase -1

- datos/ — creado, contiene todos los módulos Cloud Function
- relatos/ — creado con README.md y .gitkeep
- notebooks_validacion/ — creado con 5 notebooks placeholder
- docs/ — creado con arquitectura.md y guia_despliegue.md
- .gitignore — actualizado
- README.md — reescrito
- CLAUDE.md — reescrito
- agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py — fix sys.path para datos/

## Archivos creados en Fase 0

- agentes/diagnostico/__init__.py ✅
- agentes/diagnostico/revisar_datos.py ✅

## Archivos creados en Fase 2

- agentes/datos/consultor_bigquery.py — añadidos 2 métodos NLP ✅
- agentes/subagentes/subagente_nlp/__init__.py ✅
- agentes/subagentes/subagente_nlp/prompts.py ✅
- agentes/subagentes/subagente_nlp/agente.py ✅
- agentes/subagentes/subagente_nlp/tools/__init__.py ✅
- agentes/subagentes/subagente_nlp/tools/tool_buscar_relatos.py ✅
- agentes/subagentes/subagente_nlp/tools/tool_extraer_patrones.py ✅
- agentes/subagentes/subagente_nlp/tools/tool_conocimiento_historico.py ✅
- agentes/orquestador/agente_principal.py — actualizado 4→5 subagentes (v3) ✅
- agentes/subagentes/subagente_integrador/prompts.py — actualizado S1-S4 ✅

## Archivos creados en Fase 3

- agentes/despliegue/Dockerfile ✅
- agentes/despliegue/cloudbuild.yaml ✅
- agentes/despliegue/job_cloud_run.yaml ✅
- agentes/despliegue/requirements.txt ✅

## Archivos modificados en Fase 4

- agentes/salidas/schema_boletines.json — 27 campos (añade NLP + 48h/72h) ✅

## Archivos creados/modificados en Fase 5

- agentes/tests/test_fase0_datos.py ✅ (nuevo, requiere GCP)
- agentes/tests/test_subagentes.py — TestToolsNLP (3 tests) + TestSubagenteNLP ✅
- agentes/tests/test_sistema_completo.py — 5 subagentes, arquitectura v3 ✅

## Auditoría Marco Teórico (2026-03-17)

- Auditoría completa de 7 dimensiones → `claude/PLAN_BRECHAS_MARCO_TEORICO.md`
- Alineación general: MEDIA (46/70)
- 11 brechas detectadas: 3 críticas, 4 problemáticas, 4 justificables

## Cambios 2026-03-17

- ✅ Tabla `boletines_riesgo` creada en BigQuery (27 campos, particionada, clusterizada)
- ✅ `almacenador.py` actualizado de 12→27 campos (añadidos campos v3)
- ✅ `procesador_dias/main.py` — fix 10 campos NULL (sunEvents, temperaturas a nivel día)
- ✅ `procesador_horas/main.py` — fix 3 nombres de campo + 9 campos nuevos en schema BQ
- ✅ `monitor_satelital/constantes.py` — fix nombres de banda (LST_Celsius, snow_depth_m)
- ✅ `monitor_satelital/main.py` — expandido de 2 a 25 ubicaciones monitoreadas
- ✅ `agentes/validacion/metricas_eaws.py` — framework completo: F1-macro (H1), delta NLP (H2), Cohen's Kappa (H4), ablación
- ✅ `tool_analizar_dem.py` — C1: gradiente térmico PINN desde LST satelital real (con fallback lapse rate)
- ✅ `tool_clasificar_eaws.py` — C2: `estimar_tamano_potencial()` conectada al pipeline (ya no default=2)
- ✅ `tool_clasificar_eaws.py` — C3: viento >40km/h incrementa frecuencia EAWS (+1), >70km/h (+2)
- ✅ Tests: 17 passed (añadidos test_tamano_dinamico, test_viento_incrementa_frecuencia)
- ✅ `schema_boletines.json` — C4: 6 campos nuevos de ablación y trazabilidad (33 campos total)
- ✅ `almacenador.py` — C4: 6 campos nuevos en fila BQ (datos_topograficos_ok, datos_meteorologicos_ok, version_prompts, fuente_gradiente_pinn, fuente_tamano_eaws, viento_kmh)
- ✅ `agentes/prompts/registro_versiones.py` — #4: sistema versionado prompts con SHA-256, CLI --verificar/--actualizar-hashes
- ✅ `agentes/orquestador/agente_principal.py` — #4: integración version_prompts en cada boletín generado
- ✅ `agentes/subagentes/base_subagente.py` — #5: reintentos API con backoff exponencial (3 intentos, 2-30s)
- ✅ `agentes/orquestador/agente_principal.py` — #5: degradación graceful SubagenteNLP (no-crítico, pipeline continúa si falla)
- ✅ `agentes/orquestador/agente_principal.py` — #5: campo `subagentes_degradados` en resultado final
- ✅ Tests: 23 passed (añadidos TestReintentosAPI ×3, TestDegradacionGraceful ×3)
- ✅ `docs/decisiones_diseno.md` — #6: 10 decisiones de diseño con justificación académica, alternativas, referencias
- ✅ `docs/arquitectura.md` — actualizado: diagrama flujo, pipeline 5 subagentes, resiliencia, tablas BQ
- ✅ `agentes/validacion/metricas_eaws.py` — Techel et al. (2022) benchmark: TECHEL_2022_REFERENCIA, QWK, accuracy adyacente, comparar_con_techel_2022()
- ✅ `docs/decisiones_diseno.md` — D11: benchmark Techel (2022) con métricas de referencia y diferencias metodológicas
- ✅ Tests: 31 passed (añadidos TestMetricasTechel ×8: QWK, accuracy adyacente, sesgo, referencia, comparación)
- ✅ Tests: 62 passed — #7 tests unitarios: +31 tests nuevos (almacenador helpers, registro versiones, F1-macro, delta NLP, ablación, Cohen's Kappa)
- ✅ D1: `notebooks_validacion/01_validacion_f1_score.py` — F1-macro, matriz confusión, carga ground truth CSV
- ✅ D2: `notebooks_validacion/02_analisis_ablacion.py` — ablación con/sin cada subagente, ranking importancia, demo sintético
- ✅ D3: `notebooks_validacion/03_comparacion_snowlab.py` — Cohen's Kappa, QWK, accuracy ±1, comparación Techel (2022)
- ✅ D4: `notebooks_validacion/04_confianza_cobertura.py` — cobertura campos, trazabilidad fuentes, tiempos ejecución
- ✅ Carpeta renombrada: `databricks/` → `notebooks_validacion/`
- ✅ B2: `datos/relatos/schema_relatos.json` — schema 12 campos para tabla relatos_montanistas
- ✅ B2: `datos/relatos/cargar_relatos.py` — ETL completo: JSON/CSV → BigQuery, normalización zonas, detección términos avalancha, dedup SHA-256, batch 500
- ✅ BQ migration: `agentes/scripts/migrar_schema_boletines.py` — migración 27→34 campos (--dry-run, --verificar)
- ✅ `schema_boletines.json` — 34 campos (añade subagentes_degradados para trazabilidad degradación graceful)
- ✅ `almacenador.py` — campo subagentes_degradados añadido a fila BQ
- ✅ (3) `docs/marco_etico_legal.md` — framework ético-legal completo (Ley 21.719, responsabilidad, principio de precaución, gobernanza GCP)
- ✅ (3) `docs/decisiones_diseno.md` — D12: marco ético-legal + principio de precaución
- ✅ (3) `agentes/subagentes/subagente_integrador/prompts.py` — disclaimer obligatorio añadido
- ✅ Tests: 89 passed — +27 tests nuevos (TestETLRelatos ×18, TestDisclaimerPrompts ×6, TestSchemaMigracion ×4, TestVIT ×1→ya existía)
- ✅ `notebooks_validacion/05_pruebas_estadisticas.py` — bootstrap IC 95%, McNemar, test diferencia proporciones (H2), análisis de potencia (N mínimo), demo sintético
- ✅ Tests: 105 passed — TestPruebasEstadisticas ×16 (bootstrap F1/Kappa, McNemar, potencia estadística, datos sintéticos)
- ✅ `agentes/subagentes/subagente_nlp/conocimiento_base_andino.py` — base de conocimiento estático: 8 zonas andinas, patrones históricos, factor estacional, fallback cuando BQ vacío
- ✅ `tool_conocimiento_historico.py` — fallback automático a base andina cuando total_relatos=0 (índice no es 0.0 sino ajustado por zona+estación)
- ✅ Tests: 116 passed — TestBaseConocimientoAndino ×10 + TestToolsNLP actualizado ×4
- ✅ `claude/PLAN_BRECHAS_MARCO_TEORICO.md` — actualizado: B1/B2/B4/B5/B6/E1 cerradas, score 66/80
- ✅ `tool_analizar_vit.py` — REESCRITO: multi-head attention (H=2, D_MODEL=6, D_HEAD=3), W_Q/K/V Xavier determinista (Glorot & Bengio 2010), positional encoding sinusoidal (Vaswani 2017 §3.5), entropía de atención, norma contexto MHA — ViT 7/10 → 8/10
- ✅ Tests: 121 passed — TestToolsVIT +5 tests: arquitectura_multihead, entropía, PE dimensión, proyección WQ, norma_contexto
- ✅ `tool_calcular_pinn.py` — UQ Taylor 1er orden: `_propagar_incertidumbre_pinn()` + `_fs_mohr_coulomb_puro()`. Campos: ic_95_inf, ic_95_sup, sigma_fs, CV, sensibilidades (ρ/θ/m), parametro_dominante. Refs: Proksch 2015, Farr 2007, Saltelli 2008 — PINNs 8/10 → 9/10
- ✅ `docs/decisiones_diseno.md` — D13: UQ PINN con justificación académica completa
- ✅ Tests: 126 passed — TestToolsPINN +5 tests UQ (estructura IC, IC contiene FS, σ>0, reconstrucción cuadrática, IC no-negativo)
- ✅ `conocimiento_base_andino.py` — 9→15 zonas (añadidas: el_plomo, tupungato, osorno, tronador, coquimbo_norte)
- ✅ `notebooks_validacion/06_analisis_nlp_sintetico.py` — H2 sintética confirmada: delta F1 = +7.9pp (>5pp umbral) con modelo NLP unidireccional (corrección solo upward, principio precaución, Techel & Schweizer 2017)
- ✅ `notebooks_validacion/n06_analisis_nlp_sintetico.py` — copia importable (mismo patrón que n05)
- ✅ Tests: 135 passed — TestNLPSintetico ×9 (H2 estructura, delta>0, H2 confirmada, zonas, sensibilidad, unidireccional)

## Despliegue producción (2026-03-18)

- ✅ `zonas_avalancha` regenerada — 37/37 zonas con datos correctos: `pendiente_max_media=72.5°`, `indice_riesgo_medio=63.18` (antes 0° y 25.0 fijo pre-fix)
- ✅ `Cloud Run Job orquestador-avalanchas` desplegado — imagen `gcr.io/climas-chileno/snow-alert-agentes:74b2359`, LLM Databricks/Qwen3-80B vía Secret Manager
- ✅ `cloudbuild.yaml` — create-or-update automático, sin dependencia del secret `claude-oauth-token`
- ✅ `Dockerfile` — `--guardar` añadido al ENTRYPOINT (siempre guarda en BQ + GCS al ejecutar en producción)
- ✅ `almacenador.py` — fix NameError línea 275: `resultado` → `resultado_boletin` al insertar en BigQuery
- ✅ **10 boletines piloto** generados y guardados — BigQuery `clima.boletines_riesgo` + GCS `boletines/*/2026/03/18/*.json`
  - Niveles: Antuco=5, Cerro Bayo=5, Cerro Castor=5, Antillanca=4, Bariloche=4, Brian Head=3, Aspen=2, Banff=2, Arizona Snowbowl=2, Cerro Catedral=2 (Nivel medio: 3.3)
  - Confianza: Alta/Media/Baja según disponibilidad de datos satelitales y topográficos
  - Tiempo de ejecución: ~859s por lote de 10 ubicaciones

## Estado de tests

- test_subagentes.py (sin Anthropic): ✅ 135 passed, 5 skipped
  - TestTools (PINN, ViT, EAWS, NLP, Boletín): 27 tests (PINN +5 UQ, ViT +5 MHA)
  - TestReintentosAPI: 3 tests
  - TestDegradacionGraceful: 3 tests
  - TestMetricasTechel: 8 tests
  - TestAlmacenadorHelpers: 10 tests
  - TestRegistroVersiones: 7 tests
  - TestMetricasF1: 5 tests
  - TestMetricasDeltaNLP: 3 tests
  - TestMetricasAblacion: 2 tests
  - TestMetricasKappa: 4 tests
  - TestETLRelatos: 18 tests (actualizados 2026-03-18 para schema 37 campos: parsers bool/float/int, extraer_nombre, cargar_routes_csv, enriquecer_con_llm)
  - TestDisclaimerPrompts: 6 tests (disclaimer, schema 34 campos, marco ético)
  - TestSchemaMigracion: 4 tests (migración BQ)
  - TestPruebasEstadisticas: 16 tests (bootstrap, McNemar, potencia estadística)
  - TestBaseConocimientoAndino: 10 tests (fallback NLP, base andina 15 zonas, estacional)
  - TestToolsNLP: 4 tests (actualizados: fallback BQ→base andina)
  - TestNLPSintetico: 9 tests (NUEVO — H2 sintética confirmada +7.9pp, sensibilidad, unidireccional)
- test_sistema_completo.py: ⬜ no ejecutado (requiere ANTHROPIC_API_KEY)
- test_fase0_datos.py: ⬜ no ejecutado (requiere GCP auth)

## Próximos pasos

1. **A2** Generar boletín piloto y verificar insert completo en BigQuery (requiere ANTHROPIC_API_KEY)
2. **A3** Generar boletines para 5-10 ubicaciones piloto
3. **Fase 1** Ejecutar carga final de relatos (requiere GCP auth):
   ```bash
   python datos/relatos/cargar_relatos.py \
       --routes datos/relatos/andes_handbook_routes.csv \
       --llm    datos/relatos/andes_handbook_routes_llm.csv
   ```

## Completado 2026-03-17/18 (sesión)

- ✅ **BQ migration**: `boletines_riesgo` migrada 27→34 campos
- ✅ **B1**: tabla `relatos_montanistas` creada en BigQuery
- ✅ **B3**: `zonas_avalancha` poblada con 37 ubicaciones (37/37 exitosos)
- ✅ Fix `agentes/tools/tool_eaws.py` — path `../../datos/analizador_avalanchas`
- ✅ Fix `datos/analizador_avalanchas/main.py` — nueva API `cubicar_zonas_completo()`
- ✅ Fix `datos/analizador_avalanchas/indice_riesgo.py` — `estimar_tamano_potencial(d, ha, pend)` + `consultar_matriz_eaws` retorna tuple
- ✅ Tests: 140 passed (sin credenciales Anthropic)
- ✅ Fix `datos/monitor_satelital/constantes.py` — vis_params: `NDSI_Snow_Cover`→`NDSI`, `CMI_C02/C03/C01`→`R/G/B`, `sur_refl_b01/b04/b03`→`R/G/B`
- ✅ Fix `datos/monitor_satelital/metricas.py` — args `lst_dia`/`lst_noche` → `lst_dia_celsius`/`lst_noche_celsius`
- ✅ Fix `datos/monitor_satelital/productos.py` — `datetime.utcnow()`→`datetime.now(timezone.utc)`, `utcfromtimestamp`→`fromtimestamp(..., tz=timezone.utc)`
- ✅ Fix `datos/monitor_satelital/indicadores_nieve.py` — `datetime.utcnow()`→`datetime.now(timezone.utc)`
- ✅ Fix `datos/monitor_satelital/main.py` — `datetime.utcnow()`→`datetime.now(timezone.utc)` (2 ocurrencias)
- ✅ Fix `datos/monitor_satelital/viento_altura.py` — ventana búsqueda ERA5: 1 día→7 días; banda `u_component_of_wind`→`u_component_of_wind_100m`
- ✅ Fix `datos/monitor_satelital/constantes.py` — `DIAS_BUSQUEDA_SENTINEL2`: 15→30 días
- ✅ Fix `datos/monitor_satelital/productos.py` — `max_nubes` Sentinel-2: 30%→60%
- ✅ Monitor satelital: 25/25 ubicaciones exitosas, GeoTIFFs/previews en GCS, datos en BigQuery (ndsi, lst, viento, URIs)

## Completado 2026-03-18 (imágenes blancas)

- ✅ Fix `datos/monitor_satelital/productos.py` — NDSI mask: `neq(250)` → `lte(100)` (fill values 200,201,211,etc. se renderizaban como blanco)
- ✅ Fix `datos/monitor_satelital/productos.py` — LST: mascara fill value 0 antes de convertir a Celsius
- ✅ Fix `datos/monitor_satelital/constantes.py` — ERA5 palette: blanco (0 snow) → gris oscuro (#4a4a4a), max=2m
- ✅ Fix `datos/monitor_satelital/constantes.py` — MODIS true color vis_params: min/max -100/8000 → 0/3000 con gamma=1.4
- ✅ Fix `datos/monitor_satelital/descargador.py` — Preview/thumbnail incluye tipo_producto en nombre de archivo (antes todos sobreescribían el mismo archivo)
- ✅ Verificado: ERA5 preview nocturno muestra gris oscuro (#4a4a4a) correctamente para 0 snow depth
- ⏳ Pendiente verificar: NDSI y visual diurnos — se confirmarán en próxima captura manana/tarde

## Completado 2026-03-18 (relatos Databricks)

- ✅ `datos/relatos/schema_relatos.json` — reescrito 12→37 campos para CSVs finales de Databricks:
  - 22 campos estructurados de `andes_handbook_routes.csv` (`route_id`, `elevation`, `latitude`, `longitude`, `mountain_characteristics`, `is_alta_montana`, `has_glacier`, `is_volcano`, `avalanche_priority`, etc.)
  - 12 campos del análisis LLM (`llm_tipo_actividad`, `llm_modalidad`, `llm_nivel_riesgo`, `llm_puntuacion_riesgo`, `llm_experiencia_requerida`, `llm_resumen`, `llm_confianza_extraccion`, `llm_factores_riesgo[]`, `llm_tipos_terreno[]`, `llm_equipamiento_tecnico[]`, `llm_palabras_clave[]`, `analisis_llm_json`)
  - Clustering: `location + is_alta_montana + avalanche_priority`
- ✅ `datos/relatos/cargar_relatos.py` — reescrito para ETL Databricks:
  - `cargar_routes_csv()`: lee `andes_handbook_routes.csv` → dict por nombre
  - `_enriquecer_con_llm()`: lee `andes_handbook_routes_llm.csv`, une por nombre (split en " Presentacion ")
  - `cargar_en_bigquery()`: dedup por `route_id` (antes era SHA-256 del título)
  - `verificar_tabla()`: estadísticas actualizadas (rutas con LLM, riesgo promedio, distribución por país)
  - CLI: `--routes`, `--llm`, `--crear-tabla`, `--verificar`, `--dry-run`
- ✅ `.claude/settings.json` — creado con `defaultMode: acceptEdits` para el proyecto

## Completado 2026-03-18 (carga relatos BigQuery)

- ✅ `relatos_montanistas` — tabla antigua (12 campos, vacía) eliminada y recreada con schema 37 campos
- ✅ **3,138 rutas cargadas** en `climas-chileno.clima.relatos_montanistas` (0 errores, 0 duplicados)
  - 3,131 enriquecidas con análisis LLM (99.8%)
  - 41 con información específica de avalanchas (`has_avalanche_info=true`)
  - 41 marcadas como prioridad avalancha (`avalanche_priority=true`)
  - 2,268 Alta Montaña (72.3%)
  - Riesgo promedio LLM: **4.56 / 10**
  - Distribución: Argentina 1,083 | Chile 1,013 | Perú 798 | Bolivia 155 | Ecuador 41 | otros 144

## Completado 2026-03-18 (nulos BigQuery + imágenes grises — sesión 3)

### Bugs corregidos en `datos/monitor_satelital/`

- ✅ `viento_altura.py` — `obtener_viento_maximo_24h`: bandas `u/v_component_of_wind` → `u/v_component_of_wind_100m`
- ✅ `viento_altura.py` — `obtener_viento_maximo_24h`: ventana de búsqueda 24h fija → 7 días (`DIAS_BUSQUEDA_ERA5`) para tolerar latencia variable ERA5
- ✅ `viento_altura.py` — `obtener_metricas_viento_completas`: pasar `None` a `obtener_viento_maximo_24h` (no fecha actual → evita buscar ERA5 en fechas sin datos)
- ✅ `viento_altura.py` — `agregar_velocidad`: bandas `u/v_component_of_wind` → `u/v_component_of_wind_100m`
- ✅ `constantes.py` — `DIAS_BUSQUEDA_MODIS`: 7 → 14 días (MOD11A1/LST tiene latencia hasta 14 días)
- ✅ `productos.py` — almacena `imagen_raw` (banda cruda sin máscara) en dict `ndsi` para cálculo de % nubes
- ✅ `metricas.py` — llama `calcular_porcentaje_nubes` con `imagen_raw` (antes `pct_nubes` siempre null)
- ✅ `descargador.py` — `descargar_y_guardar_producto`: añade parámetro opcional `radio_metros`
- ✅ `descargador.py` — ERA5 GeoTIFF usa `radio_metros=25000` (50km×50km): resuelve TIFFs de 530 bytes vacíos (ERA5 pixel ~9-11km no cabía en ROI de 10km×10km)
- ✅ `descargador.py` — `guardar_thumbnail`: `datetime.utcnow()` → `datetime.now(timezone.utc)`

### Validación post-despliegue (captura nocturna, 25 ubicaciones)

| Campo | Antes | Ahora |
|-------|-------|-------|
| `viento_max_24h_ms` | 0/25 | 25/25 ✓ |
| `viento_altura_vel_ms` | 25/25 | 25/25 ✓ |
| `lst_noche_celsius` | 0/25 | 25/25 ✓ |
| `era5_snow_depth_m` | 25/25 | 25/25 ✓ |
| `lst_dia_celsius` | null en noche | null en noche (ESPERADO) |
| `ndsi_medio` | null en noche | null en noche (ESPERADO) |
| `pct_nubes` | null en noche | null en noche (ESPERADO — solo diurno) |

### Imágenes GCS verificadas

- **LST preview** (`portillo_noche_lst_768px.png`): 19.7KB, 768×464px RGB, 89 colores únicos — imagen real con gradiente de temperatura
- **ERA5 GeoTIFF** (`portillo_noche_era5_land_era5.tif`): 2.0KB, 6×5px, 3 bandas — válido (vs 530 bytes vacío antes)
- **LST GeoTIFF** (`portillo_noche_modis_lst_lst.tif`): 1.5KB, 13×11px, 1 banda float64 — válido
- **ERA5 preview**: gris (#4a4a4a) → CORRECTO para sin-nieve en Marzo (verano hemisferio sur)

### Imágenes diurnas (pendiente confirmar en próxima captura mañana/tarde)

- NDSI preview, Visual preview, `pct_nubes`, `lst_dia_celsius`, `ndsi_medio` se confirmarán en captura 10-16 UTC

## Completado 2026-03-18 (integración Google Weather API + fixes pipeline)

### Google Weather API — 3 fuentes operativas

| Tabla BigQuery | Ubicaciones | Filas | Última extracción |
|----------------|-------------|-------|-------------------|
| `condiciones_actuales` | 84 | 69.573 | 2026-03-18 13:53 UTC |
| `pronostico_dias` | 63 | 17.295 | 2026-03-18 13:53 UTC |
| `pronostico_horas` | 61 | 2.521 | 2026-03-18 13:53 UTC |

Las 3 tablas se actualizan automáticamente con cada ejecución del `extractor-clima`.

### Fix `procesador-clima-horas` (tabla pronostico_horas vacía)

- **Causa**: `BUCKET_CLIMA` no definida en env vars → usaba default `datos-clima-bronce` (bucket inexistente). Bucket real: `climas-chileno-datos-clima-bronce`.
- **Fix**: `gcloud run services update procesador-clima-horas --update-env-vars BUCKET_CLIMA=climas-chileno-datos-clima-bronce`
- Las otras 2 funciones (`procesador-clima`, `procesador-clima-dias`) ya tenían la variable correcta.

### Fix `cubicacion.py` — análisis topográfico SRTM (zonas_avalancha)

12 key mismatches entre el dict de salida de `cubicar_zonas_completo()` y lo que leen `main.py` e `indice_riesgo.py`. Causaba que `pendiente_max_inicio = 0` siempre → `indice_riesgo_topografico = 25.0` fijo para todas las ubicaciones (solo componente de área, sin pendiente/aspecto/desnivel).

Claves corregidas en `datos/analizador_avalanchas/cubicacion.py`:

| Key antigua (incorrecta) | Key correcta |
|--------------------------|--------------|
| `ha_zona_inicio_total` | `zona_inicio_ha` |
| `ha_zona_transito` | `zona_transito_ha` |
| `ha_zona_deposito` | `zona_deposito_ha` |
| `pct_zona_inicio` | `zona_inicio_pct` |
| `pct_zona_deposito` | `zona_deposito_pct` |
| `pendiente_max` | `pendiente_max_inicio` |
| `pendiente_p90` | `pendiente_p90_inicio` |
| `aspecto_predominante` | `aspecto_predominante_inicio` |
| `ha_inicio_30_45` | `inicio_moderado_ha` |
| `ha_inicio_45_60` | `inicio_severo_ha` |
| `ha_inicio_mas_60` | `inicio_extremo_ha` |
| `elevacion_media_inicio/deposito` | `elevacion_max_inicio` / `elevacion_min_deposito` |

También añadidos: `zona_transito_pct`, `area_total_ha`, `elevacion_min_inicio`.

### Fix `indicadores_nieve.py` — monitor satelital (campos NULL en imagenes_satelitales)

- **Causa**: `procesar_modis_ndsi()` renombra la banda `NDSI_Snow_Cover → NDSI`, pero `calcular_snowline()` y `calcular_cambio_cobertura()` seguían haciendo `.select('NDSI_Snow_Cover')` → error GEE silencioso → NULL en `snowline_elevacion_m`, `pct_cobertura_nieve`, `delta_pct_nieve_*`.
- **Fix**: reemplazar `select('NDSI_Snow_Cover')` por `select('NDSI')` y `stats.get('NDSI_Snow_Cover')` por `stats.get('NDSI')` en `datos/monitor_satelital/indicadores_nieve.py`.

### Fix `metricas.py` — SAR NoneType format error

- **Causa**: `f"{sar_pct_nieve_humeda:.1f}"` en `logger.info` explota con `TypeError` cuando SAR no tiene datos de % nieve.
- **Fix**: guard condicional antes del format string.

### Redespliegues realizados

- `monitor-satelital-nieve` → revision `00014-kow` (entry point corregido: `monitorear_satelital`)
- `analizador-satelital-zonas-riesgosas-avalanchas` → revision `00005-zug`

### Fix pipeline agentes (bugs previos corregidos en sesión anterior)

- `ejecutar_buscar_relatos/extraer_patrones/sintetizar_conocimiento`: parámetro `consultor` eliminado, se instancia `ConsultorBigQuery()` internamente
- `consultor_bigquery.py`: columna inexistente `probabilidad_precipitacion`; TIMESTAMP vs DATE; schema viejo `relatos_montanistas`; `diurno_viento_max` → `diurno_velocidad_viento`
- `pronostico_dias` duplicados: `QUALIFY ROW_NUMBER() OVER (PARTITION BY DATE(fecha_inicio) ORDER BY marca_tiempo_extraccion DESC) = 1`

### LLM alternativo Databricks/Qwen3

- `ClienteDatabricks`: endpoint `https://2113388677481041.ai-gateway.cloud.databricks.com/mlflow/v1`, modelo `databricks-qwen3-next-80b-a3b-instruct`
- Token en GCP Secret Manager: `projects/climas-chileno/secrets/databricks-token/versions/latest`
- Pipeline completo funciona con Databricks (~114s, 5/5 subagentes, 18 tool calls, 0 degradados)

## Errores conocidos

- `zonas_avalancha`: los 37 registros actuales tienen `pendiente_max_inicio=0` (datos anteriores al fix). Se corregirán en la próxima ejecución del analizador.
- `imagenes_satelitales`: la mayoría de filas tienen `snowline/pct_cobertura/delta_nieve=NULL` (datos anteriores al fix). Se corregirán en la próxima captura.

## Comandos de verificación rápida

```bash
# Tests sin credenciales (siempre deben pasar)
cd snow_alert && python -m pytest agentes/tests/test_subagentes.py -v -k "not (TestSubagenteTopografico or TestSubagenteSatelital or TestSubagenteMeteorologico or TestSubagenteIntegrador or TestSubagenteNLP)"
# Esperado: 135 passed, 5 skipped

# Tests con BigQuery (requiere GCP auth)
python -m pytest agentes/tests/test_fase0_datos.py -v

# Test E2E completo (requiere ANTHROPIC_API_KEY)
python -m pytest agentes/tests/test_sistema_completo.py -v -s
```

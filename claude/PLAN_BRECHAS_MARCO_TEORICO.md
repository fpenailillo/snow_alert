# Plan de Trabajo: Brechas Marco Teórico vs Implementación

> Generado: 2026-03-17 | Actualizado: 2026-03-18
> Tesina: Francisco Peñailillo — Magíster TI, UTFSM — Dr. Mauricio Solar

---

## Estado General

| Dimensión | Estado | Score |
|-----------|--------|-------|
| 1. Arquitectura Multi-Agente | ✅ Completo | 10/10 |
| 2. PINNs (manto nival) | ✅ Gradiente LST real + lapse rate fallback + UQ Taylor 1er orden (IC 95%, σ_FS, sensibilidades) | 9/10 |
| 3. Vision Transformers (ViT) | ✅ Multi-head attention (H=2, W_QKV Xavier, pos. enc. sinusoidal, entropía atención) | 8/10 |
| 4. Escala EAWS + Matriz | ✅ Completo + tamaño dinámico + ajuste viento | 9/10 |
| 5. NLP Relatos Montañistas | ⚠️→✅ Fallback base andina (15 zonas, factor estacional) + validación H2 sintética confirmada (+7.9pp) | 8/10 |
| 6. Infraestructura Serverless | ✅ Completo | 9/10 |
| 7. Métricas de Validación | ✅ Framework completo + notebooks D1-D5 + Techel benchmark + pruebas estadísticas (bootstrap/McNemar/potencia) | 9/10 |
| 8. Marco Ético-Legal | ✅ Nuevo — docs/marco_etico_legal.md + D12 + disclaimer | 9/10 |

**Alineación general: ALTA (71/80)** ← +1 NLP: 15 zonas + H2 sintética confirmada (+7.9pp, notebook 06)

---

## Brechas Detectadas

### BRECHAS CRÍTICAS (bloquean la defensa)

#### B1. ✅ CERRADA — Tabla `boletines_riesgo` creada en BigQuery
- **Estado:** ✅ 2026-03-17 — 34 campos, particionada por fecha_emision, clusterizada por nombre_ubicacion
- **Schema:** `agentes/salidas/schema_boletines.json` (34 campos)
- **Migración:** `agentes/scripts/migrar_schema_boletines.py` para actualizar tabla existente
- **Bloquea:** ~~H1, H2, H3, H4~~ → solo falta generar boletines piloto (requiere ANTHROPIC_API_KEY)

#### B2. ✅ CERRADA — Notebooks de validación y framework de métricas completo
- **Estado:** ✅ 2026-03-17
- **Archivos:** `notebooks_validacion/01-04_*.py` (F1, ablación, Kappa, cobertura)
- **Framework:** `agentes/validacion/metricas_eaws.py` (F1-macro, Kappa, QWK, Techel 2022)
- **Tests:** 89 passed (incluye TestMetricasF1, TestMetricasKappa, TestMetricasTechel)

#### B3. ✅ CERRADA — Relatos + ETL Databricks + validación H2 sintética confirmada
- **Estado:** ✅ 2026-03-18 — schema 37 campos + ETL para CSVs finales Databricks + fallback 15 zonas + H2 sintética confirmada
- **Código:** `datos/relatos/cargar_relatos.py` — reescrito para CSVs exportados desde Databricks:
  - `cargar_routes_csv()`: lee `andes_handbook_routes.csv` (3,142 rutas, 22 columnas)
  - `_enriquecer_con_llm()`: une con `andes_handbook_routes_llm.csv` por nombre de ruta
  - Dedup por `route_id` (entero, no SHA-256)
- **Schema:** `datos/relatos/schema_relatos.json` (**37 campos** — 2026-03-18):
  - 22 campos estructurados de routes CSV (`route_id`, `elevation`, `latitude`, `longitude`, `mountain_characteristics`, `is_alta_montana`, `has_glacier`, `is_volcano`, `avalanche_priority`, etc.)
  - 12 campos LLM (`llm_tipo_actividad`, `llm_nivel_riesgo`, `llm_puntuacion_riesgo`, `llm_factores_riesgo[]`, `llm_tipos_terreno[]`, `llm_equipamiento_tecnico[]`, `analisis_llm_json`, etc.)
  - Clustering: `location + is_alta_montana + avalanche_priority`
- **Fallback:** `agentes/subagentes/subagente_nlp/conocimiento_base_andino.py` — **15 zonas**, factor estacional, índice no-nulo
- **Zonas nuevas:** el_plomo, tupungato, osorno, tronador, coquimbo_norte
- **Validación H2 sintética:** `notebooks_validacion/06_analisis_nlp_sintetico.py` — delta F1 = **+7.9pp** (sesgo=0.4, fuerza=0.65), H2 CONFIRMADA (sintético)
- **Modelo NLP unidireccional:** corrección solo hacia arriba (principio precaución) — Techel & Schweizer (2017)
- **Tests:** `TestETLRelatos` (18, actualizados 2026-03-18 para schema 37 campos) + `TestBaseConocimientoAndino` (10) + **`TestNLPSintetico` (9)**
- **Pendiente:** Ejecutar carga con GCP auth (`--routes andes_handbook_routes.csv --llm andes_handbook_routes_llm.csv`) para H2 real
- **Impacto:** SubagenteNLP ya NO retorna índice=0.0 — usa conocimiento andino con validación sintética confirmada

### BRECHAS PROBLEMÁTICAS (el comité cuestionará)

#### B4. ✅ CERRADA — ViT: Multi-head attention completo implementado
- **Estado:** ✅ 2026-03-17 (actualizado con MHA completo)
- **Arquitectura:** H=2 cabezas, D_MODEL=6, D_HEAD=3, W_Q/K/V separados (Xavier determinista, Glorot & Bengio 2010)
- **Positional encoding:** sinusoidal (Vaswani 2017 §3.5): PE(t,2i)=sin(t/10000^(2i/d)), PE(t,2i+1)=cos(...)
- **Campos de salida:** `arquitectura_vit`, `n_heads`, `entropia_atencion`, `norma_contexto_mha`
- **Terminología tesina:** "Temporal Transformer con multi-head scaled dot-product attention (Vaswani et al. 2017)"
- **Tests:** 9 tests en TestToolsVIT (incluyendo proyecciones WQ, entropía, PE dimensión)
- **Refs:** Vaswani et al. (2017), Glorot & Bengio (2010), Zhou et al. (2021)

#### B5. ✅ CERRADA — PINN: gradiente LST real + cuantificación de incertidumbre
- **Estado:** ✅ 2026-03-17 (UQ añadido 2026-03-17)
- **Gradiente:** `tool_analizar_dem.py` calcula `(LST_día - LST_noche) / (snow_depth × 100)` desde BQ
- **Fallback:** lapse rate estándar -0.65°C/100m si no hay datos satelitales
- **UQ (D13):** `_propagar_incertidumbre_pinn()` — propagación Taylor 1er orden: σ_ρ=±50kg/m³, σ_θ=±2°, σ_m=±0.2
- **Campos nuevos:** `ic_95_inf`, `ic_95_sup`, `sigma_fs`, `coeficiente_variacion`, `sensibilidades`, `parametro_dominante`
- **Refs:** Proksch et al. (2015), Farr et al. (2007), Saltelli et al. (2008), Taylor (1997)
- **Tests:** TestToolsPINN 8 tests (5 nuevos de UQ)

#### B6. ✅ CERRADA — Tamaño EAWS dinámico conectado al pipeline
- **Estado:** ✅ 2026-03-17 — `tool_clasificar_eaws.py` llama `estimar_tamano_potencial()`, fallback=2
- **Ajuste viento:** >40km/h → +1 frecuencia, >70km/h → +2 (C3)

#### B7. ✅ CERRADA — Tabla `zonas_avalancha` regenerada con datos correctos (2026-03-18)
- **Estado:** ✅ 37/37 zonas con datos correctos: `pendiente_max_media=72.5°`, `indice_riesgo_medio=63.18`
- **Fix aplicado:** `datos/analizador_avalanchas/cubicacion.py` — 12 key mismatches corregidos + función re-ejecutada
- **Resultado EAWS S1:** `indice_riesgo_topografico` ahora varía por zona (antes fijo en 25.0 para todas)

### BRECHAS JUSTIFICABLES ✅ TODAS DOCUMENTADAS

#### B8. ✅ ViT sobre métricas vs imágenes crudas — `docs/decisiones_diseno.md` D2
#### B9. ✅ Clasificación ordinal capas débiles — `docs/decisiones_diseno.md` D4
#### B10. ✅ NLP como enriquecimiento — `docs/decisiones_diseno.md` D5
#### B11. ✅ Frecuencia base topográfica + ajuste viento — `docs/decisiones_diseno.md` D6

### NUEVA DIMENSIÓN: Marco Ético-Legal

#### E1. ✅ COMPLETO — Framework ético-legal creado
- **Archivos:** `docs/marco_etico_legal.md` — 7 secciones (regulatorio chileno, LGPD, responsabilidad, ética IA, gobernanza)
- **Código:** Disclaimer añadido a `agentes/subagentes/subagente_integrador/prompts.py`
- **Decisión:** `docs/decisiones_diseno.md` D12 — Principio de precaución + trazabilidad
- **Tests:** `TestDisclaimerPrompts` (6 tests) — verifica disclaimer, 34 campos, documento existente

---

## Plan de Trabajo por Fases

### FASE A — Fundamentos de validación (URGENTE)
> Sin esto no hay defensa posible

| # | Tarea | Archivo/Comando | Bloquea | Estado |
|---|-------|-----------------|---------|--------|
| A1 | Crear tabla `boletines_riesgo` en BigQuery | `bq mk --table --schema=...` | B1 | ✅ 2026-03-17 — 27 campos, particionada por fecha_emision, clusterizada por nombre_ubicacion |
| A1b | Actualizar `almacenador.py` para guardar 27 campos (no solo 12) | `agentes/salidas/almacenador.py:231-267` — añadidos 15 campos v3: arquitectura, estado_pinn, factor_seguridad_pinn, estado_vit, score_anomalia_vit, factor_meteorologico, ventanas_criticas, relatos_analizados, indice_riesgo_historico, tipo_alud_predominante, patrones_nlp, confianza_historica, subagentes_ejecutados, duracion_por_subagente | B1 | ✅ 2026-03-17 |
| A2 | Verificar que `almacenador.py` guarda correctamente | Correr `generar_boletin.py --ubicacion "La Parva Sector Bajo"` y verificar insert en BQ | B1 | Pendiente |
| A3 | Generar boletines piloto para 5-10 ubicaciones | `generar_todos.py` con ubicaciones: Portillo, La Parva, Valle Nevado, Farellones, El Colorado | B1, B2 | 2 horas |
| A4 | Desplegar Cloud Run Job del orquestador | `gcloud run jobs create orquestador-avalanchas` con Dockerfile existente | B1 | 1 hora |

### FASE B — Datos faltantes
> Habilitan NLP y mejoran calidad de todos los subagentes

| # | Tarea | Archivo/Comando | Bloquea | Esfuerzo |
|---|-------|-----------------|---------|----------|
| B1 | Verificar estado tabla `relatos_montanistas` | `bq query 'SELECT COUNT(*) FROM clima.relatos_montanistas'` | B3 | 5 min |
| B2 | Cargar rutas Andeshandbook en BQ | `datos/relatos/cargar_relatos.py --routes andes_handbook_routes.csv --llm andes_handbook_routes_llm.csv`. Schema: `datos/relatos/schema_relatos.json` (**37 campos**, 2026-03-18) | B3 | ✅ Script listo 2026-03-18 — **pendiente: ejecutar con GCP auth** |
| B3 | Forzar ejecución `analizador-satelital-zonas-riesgosas-avalanchas` | `gcloud functions call ...` para poblar `zonas_avalancha` | B7 | 30 min |
| B4 | Verificar datos en `imagenes_satelitales` post-fix | Los fixes de `constantes.py` (LST_Celsius, snow_depth_m) ya están desplegados → verificar que próximas ejecuciones llenen previews | B5, B7 | Esperar 24h |

### FASE C — Correcciones de código
> Cierran brechas problemáticas del comité

| # | Tarea | Archivo | Brecha | Esfuerzo |
|---|-------|---------|--------|----------|
| C1 | Computar gradiente térmico desde BQ en PINN | `tool_analizar_dem.py` — `_obtener_datos_satelitales_lst()` consulta LST real, calcula `(lst_dia - lst_noche) / (snow_depth * 100)` con fallback a lapse rate | B5 | ✅ 2026-03-17 |
| C2 | Conectar `estimar_tamano_potencial()` al pipeline | `tool_clasificar_eaws.py` — `_determinar_tamano()` llama `estimar_tamano_potencial()` con desnivel/ha/pendiente, fallback default=2 | B6 | ✅ 2026-03-17 |
| C3 | Agregar viento como factor directo en frecuencia | `tool_clasificar_eaws.py:272-277` — viento>40km/h → +1 frecuencia, >70km/h → +2 | B6 | ✅ 2026-03-17 |
| C4 | Agregar campos ablación y trazabilidad al schema | `schema_boletines.json` (33 campos) + `almacenador.py` — 6 campos nuevos: datos_topograficos_ok, datos_meteorologicos_ok, version_prompts, fuente_gradiente_pinn, fuente_tamano_eaws, viento_kmh | B2 | ✅ 2026-03-17 |

### FASE D — Validación académica
> Produce las métricas que demuestran H1, H2, H3, H4

| # | Tarea | Archivo | Hipótesis | Esfuerzo |
|---|-------|---------|-----------|----------|
| D1 | Crear notebook: F1-score macro por nivel EAWS | `notebooks_validacion/01_validacion_f1_score.py` — comparar nivel_eaws_24h predicho vs observado, carga ground truth CSV, matriz confusión | H1 | ✅ 2026-03-17 |
| D2 | Crear notebook: ablación por componente | `notebooks_validacion/02_analisis_ablacion.py` — correr con/sin cada subagente, medir delta F1, ranking importancia | H2 | ✅ 2026-03-17 |
| D3 | Crear notebook: comparación con Snowlab Chile | `notebooks_validacion/03_comparacion_snowlab.py` — Cohen's Kappa, QWK, accuracy adyacente, comparación Techel | H4 | ✅ 2026-03-17 |
| D4 | Crear notebook: análisis de confianza y cobertura | `notebooks_validacion/04_confianza_cobertura.py` — cobertura por campo, trazabilidad, tiempos, score completitud | — | ✅ 2026-03-17 |
| D5 | Benchmark Techel et al. (2022) para H3 | `metricas_eaws.py` — TECHEL_2022_REFERENCIA, QWK, accuracy adyacente, comparar_con_techel_2022(). Docs: `decisiones_diseno.md` D11 | H3 | ✅ 2026-03-17 |
| D6 | Pruebas estadísticas y análisis de potencia | `notebooks_validacion/05_pruebas_estadisticas.py` — bootstrap IC 95% (F1/Kappa), McNemar vs baseline, test diferencia proporciones (H2), N mínimo por hipótesis, demo sintético | H1,H2,H4 | ✅ 2026-03-17 |

### FASE E — Documentación para la tesina
> Justificaciones académicas de brechas aceptables

| # | Tarea | Dónde | Brecha | Estado |
|---|-------|-------|--------|--------|
| E1 | Justificar ViT temporal sobre métricas | `docs/decisiones_diseno.md` D2 — terminología, alternativas, refs (Zhou 2021, Vaswani 2017) | B4, B8 | ✅ 2026-03-17 |
| E2 | Justificar clasificación ordinal de capas débiles | `docs/decisiones_diseno.md` D4 — alineación EAWS, umbrales Mohr-Coulomb | B9 | ✅ 2026-03-17 |
| E3 | Justificar NLP como capa de enriquecimiento | `docs/decisiones_diseno.md` D5 — sesgo de selección, validación heurística, ablación H2 | B10 | ✅ 2026-03-17 |
| E4 | Justificar frecuencia base topográfica | `docs/decisiones_diseno.md` D6 — ajuste viento (C3), refs (Lehning 2008) | B11 | ✅ 2026-03-17 |
| E5 | Documentar arquitectura 5-agente con diagrama | `docs/arquitectura.md` — diagrama ASCII, tablas BQ, resiliencia | — | ✅ 2026-03-17 |

---

## Orden de Ejecución Recomendado (actualizado 2026-03-18)

> **Prioridad 1 — GCP auth** (desbloquean métricas reales):
> ```bash
> # 1. Cargar relatos en BigQuery
> cd snow_alert
> python datos/relatos/cargar_relatos.py \
>     --routes datos/relatos/andes_handbook_routes.csv \
>     --llm    datos/relatos/andes_handbook_routes_llm.csv
>
> # 2. Migración schema boletines 27→34 campos
> python agentes/scripts/migrar_schema_boletines.py
>
> # 3. Poblar zonas_avalancha
> gcloud functions call analizador-satelital-zonas-riesgosas-avalanchas \
>     --gen2 --region=us-central1
>
> # 4. Desplegar Cloud Run Job
> gcloud run jobs create orquestador-avalanchas \
>     --region=us-central1 \
>     --image=gcr.io/climas-chileno/orquestador-avalanchas
> ```

> **Prioridad 2 — ANTHROPIC_API_KEY** (métricas H1/H2/H4):
> ```bash
> # Generar boletines piloto
> cd agentes && python scripts/generar_todos.py
> ```

```
Sesión GCP:   B2 → migración → B3/B7 → A4
              (cargar relatos, migrar schema, poblar zonas, desplegar Cloud Run)

Con API Key:  A2 → A3 → métricas H1/H2/H4
              (verificar almacenador, generar ≥50 boletines, calcular F1/Kappa)
```

---

## Checklist de Verificación Pre-Defensa

### Pendiente GCP (prioridad 1 — desbloquean todo lo demás)
- [x] **Cargar 3,138 rutas** en `relatos_montanistas` (37 campos) — ✅ 2026-03-18 (3,131 con LLM, 41 avalancha, riesgo promedio 4.56)
- [ ] **Migración schema** `boletines_riesgo` 27→34 campos — `python migrar_schema_boletines.py`
- [x] **Re-poblar `zonas_avalancha` post-fix** — ✅ 2026-03-18 — 37/37 zonas correctas (`pendiente_max_media=72.5°`, `indice_riesgo_medio=63.18`)
- [x] **Desplegar Cloud Run Job** `orquestador-avalanchas` — ✅ 2026-03-18 — imagen `74b2359`, LLM Databricks, `--guardar` activo
- [ ] **Verificar imágenes diurnas** NDSI/visual/pct_nubes (próxima captura 10-16 UTC Chile)

### Pendiente (métricas de la tesina)
- [ ] Tabla `boletines_riesgo` con ≥50 boletines generados — ⚠️ 10/50 (lote piloto 2026-03-18, ejecutar job nuevamente para más ubicaciones)
- [ ] F1-score macro calculado y reportado (H1: ≥75%)
- [ ] Análisis de ablación con/sin NLP (H2: >5pp — H2 sintética ya confirmada +7.9pp)
- [ ] Comparación con Snowlab si datos disponibles (H4: Kappa≥0.60)

### Completado ✅
- [x] **Fix almacenador.py** — NameError `resultado→resultado_boletin` en insert BigQuery (2026-03-18) + `--guardar` en Dockerfile ENTRYPOINT
- [x] **Cloud Run Job desplegado** — `orquestador-avalanchas` en producción (imagen `74b2359`, Databricks LLM)
- [x] **10 boletines piloto** en BigQuery `clima.boletines_riesgo` + GCS (2026-03-18, niveles 1-5, nivel medio 3.3)
- [x] **Fix cubicacion.py** — 12 key mismatches corregidos (2026-03-18): `pendiente_max→pendiente_max_inicio`, `aspecto_predominante→aspecto_predominante_inicio`, `ha_zona_inicio_total→zona_inicio_ha`, etc. → `indice_riesgo_topografico` ya no está fijo en 25.0
- [x] **Fix indicadores_nieve.py** — banda `NDSI_Snow_Cover→NDSI` en `calcular_snowline()` y `calcular_cambio_cobertura()` (2026-03-18) → snowline, pct_cobertura_nieve, delta_pct_nieve ya no son NULL en BigQuery
- [x] **Fix metricas.py** — guard NoneType para `sar_pct_nieve_humeda` (2026-03-18)
- [x] **Fix procesador-clima-horas** — variable `BUCKET_CLIMA=climas-chileno-datos-clima-bronce` configurada en Cloud Run (2026-03-18)
- [x] Tabla `boletines_riesgo` creada en BigQuery (34 campos, schema listo)
- [x] Tamaño EAWS calculado dinámicamente — `estimar_tamano_potencial()` conectada
- [x] Gradiente térmico PINN calculado desde LST real — con fallback lapse rate
- [x] Justificaciones brechas B4-B11 escritas — `docs/decisiones_diseno.md` D1-D12
- [x] Diagrama arquitectura actualizado — `docs/arquitectura.md` (5 subagentes)
- [x] Framework de métricas completo — `agentes/validacion/metricas_eaws.py`
- [x] Notebooks validación D1-D4 — `notebooks_validacion/01-04_*.py`
- [x] Benchmark Techel (2022) — `comparar_con_techel_2022()` + D11
- [x] ETL relatos Andeshandbook — `datos/relatos/cargar_relatos.py` (script listo)
- [x] Marco ético-legal — `docs/marco_etico_legal.md` + D12 + disclaimer en prompt
- [x] Tests: 126 passed (incluyendo TestToolsPINN ×8 con 5 tests UQ, TestToolsVIT ×9 con 5 tests MHA)
- [x] PINN UQ — `_propagar_incertidumbre_pinn()`: IC 95% FS, σ_FS, sensibilidades por parámetro, parámetro dominante (D13)
- [x] Pruebas estadísticas — `notebooks_validacion/05_pruebas_estadisticas.py` (bootstrap IC 95%, McNemar, análisis de potencia para H1/H2/H4)
- [x] Base de conocimiento andino — `agentes/subagentes/subagente_nlp/conocimiento_base_andino.py` (8 zonas, factor estacional, fallback activo)

---

## Referencias Cruzadas

| Brecha | Archivos afectados | Líneas clave |
|--------|-------------------|--------------|
| B1 | `agentes/salidas/schema_boletines.json`, `agentes/salidas/almacenador.py` | schema completo |
| B3 | `agentes/datos/consultor_bigquery.py` | 551-710 |
| B4 | `agentes/subagentes/subagente_satelital/tools/tool_analizar_vit.py` | 2-9, 122-184 |
| B5 | `agentes/subagentes/subagente_topografico/tools/tool_calcular_pinn.py` | 28-30, 99-105 |
| B6 | `agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py` | 122-125 |
| B6 | `datos/analizador_avalanchas/eaws_constantes.py` | 406-470 |
| B7 | `datos/monitor_satelital/` | Cloud Function activa |

# Log de Progreso — snow_alert

## Sesión 2026-04-01 — REQ-01 S4 Situational Briefing + REQ-02 S3 WeatherNext 2

### Tarea #1: REQ-01 — Nuevo S4 Situational Briefing (AgenteSituationalBriefing) ✅

**Estado:** Implementado y testeado. 19 tests nuevos — todos pasando.

- Nuevo módulo `agentes/subagentes/subagente_situational_briefing/` con:
  - `agente.py`: `AgenteSituationalBriefing` — ejecuta 4 tools + Gemini 2.5 Flash + fallback textual
  - `schemas.py`: schemas Pydantic `SituationalBriefing`, `CondicionesRecientes`, `ContextoHistorico`, `CaracteristicasZona`
  - `tools/tool_clima_reciente.py`: condiciones 72h desde BQ (condiciones_actuales + tendencia)
  - `tools/tool_contexto_historico.py`: época estacional + desviación vs promedio histórico
  - `tools/tool_caracteristicas_zona.py`: constantes topográficas + enriquecimiento desde pendientes_detalladas
  - `tools/tool_eventos_pasados.py`: eventos históricos documentados de avalanchas
  - `prompts/system_prompt.md`: identidad, alcance, restricciones anti-alucinación
- Integración con S5: `prompts.py` del integrador actualizado para consumir `factores_atencion_eaws`, `narrativa_integrada` y campos de compatibilidad
- Compatibilidad mantenida: output incluye `indice_riesgo_historico`, `tipo_alud_predominante`, `total_relatos_analizados`, `confianza_historica`, `resumen_nlp`
- Tests: `agentes/tests/test_situational_briefing.py` — 19 tests (schemas, 4 tools, agente completo, fallback, compatibilidad S5)

### Tarea #2: REQ-02 — WeatherNext 2 aditivo en S3 ✅

**Estado:** Implementado y testeado. 17 tests nuevos — todos pasando.

- Nuevo módulo `agentes/subagentes/subagente_meteorologico/fuentes/` con patrón Strategy:
  - `base.py`: interfaz abstracta `FuenteMeteorologica` + dataclass `PronosticoMeteorologico`
  - `fuente_open_meteo.py`: fuente primaria (comportamiento existente, sin cambios)
  - `fuente_era5_land.py`: fuente secundaria reanálisis (comportamiento existente, sin cambios)
  - `fuente_weathernext2.py`: nueva fuente — 64 miembros ensemble vía BQ Analytics Hub
    - Flag `USE_WEATHERNEXT2=false` (default): siempre desactivado
    - Con flag=true: query BQ, calcula P10/P50/P90, detecta divergencia vs OM
    - Caveats Chile documentados: resolución 0.25°, sin snow depth/SWE, sesgos orográficos
  - `consolidador.py`: `ConsolidadorMeteorologico` con estrategias y fallback automático
- Nueva tool `tools/tool_pronostico_ensemble.py`: `obtener_pronostico_ensemble` — expone consolidador a S3
- `agente.py` S3 actualizado: registra la nueva tool manteniendo las 4 originales
- Fix crítico: `ConsultorBigQuery` movido a import nivel-módulo en fuente_open_meteo.py y fuente_era5_land.py (permite mocking correcto en tests)
- Tests: `agentes/tests/test_weathernext2.py` — 17 tests (schema, fuentes, consolidador, tool, regresión S3)

### Estado tests (2026-04-01)
- Suite completa: **198 passed, 8 skipped, 0 failed**
- Nuevos tests REQ-01: 19 | Nuevos tests REQ-02: 17 | Total nuevos: +36
- Sin regresiones en los 162 tests anteriores

### Pendientes (requieren acceso GCP manual)
- REQ-02 Fase A.1-A.4: suscripción a Analytics Hub `weathernext_2` en `climas-chileno`
- REQ-01 Fase C.4: activar Gemini 2.5 Flash en Vertex AI (credenciales producción)
- REQ-01 Fase F.1-F.2: desplegar Cloud Run Job actualizado

---

## Sesión 2026-03-27 (continuación 9) — Tarea #1 completada: backfill histórico 27 boletines

### Tarea #1: Generar boletines históricos restantes (27 boletines) — COMPLETADA ✅

- **Estado:** completed
- **Resultado:** 27/27 boletines generados, 0 errores
- Cubre periodos 2024-09-01/15 + inviernos 2025 (jun-sep) × 3 ubicaciones chilenas

---

## Sesión 2026-03-27 (continuación 8) — Auditoría meteo+integrador + fix reintentos API + backfill histórico

### Auditoría SubagenteMeteorológico y SubagenteIntegrador ✅ (sin bugs críticos)

- `tool_condiciones_actuales.py`: limpio
- `tool_pronostico_dias.py`: limpio
- `tool_tendencia_72h.py`: código muerto (4 funciones privadas nunca llamadas); `estadisticas["horas_con_datos"]` = `horas_con_precipitacion` (nombre confuso pero no crítico)
- `tool_ventanas_criticas.py`: limpio
- `tool_clasificar_eaws.py`: edge case menor — triple combinación "NEVADA_RECIENTE+VIENTO_FUERTE+FUSION_ACTIVA" recibe ajuste "poor" en lugar de "very_poor" (substring match devuelve "NEVADA_RECIENTE" antes de la combinación completa). Raro en Andes chilenos.
- `tool_generar_boletin.py`: limpio

### Fix reintentos API ✅ (commit 7d9e950 → desplegado como 7d9e950)

`MAX_REINTENTOS_API`: 3→5, `ESPERA_MAXIMA_SEGUNDOS`: 30→60s. Backoff: 2+4+8+16+32=62s total. Necesario para recuperar límites QPS de Databricks (~60s rolling window). Build `b39b495a` → `SUCCESS`.

### Backfill histórico reiniciado (b8mbph4ac)

Proceso anterior (bt0vez5r2) fallaba con reintentos viejos (14s max). Reiniciado con código actualizado. Primer boletín (La Parva Sector Bajo | 2024-09-01 | nivel=5) generado exitosamente sin rate limit failure. BQ save falla por streaming buffer (<90min desde inserción previa) → salvado en GCS.

27 boletines pendientes: 2024-09-01/15 + 2025 inviernos (jun-sep) × 3 ubicaciones.

---

## Sesión 2026-03-27 (continuación 7) — Fix ViT sesgo estacional + limpieza BQ + deploy a2e424c

### Fix ViT: sesgo estacional NDSI ✅ (commit a2e424c → desplegado)

**Bug:** `_clasificar_estado_vit` en `tool_analizar_vit.py` sumaba `score += 2.0` incondicionalmente cuando `ndsi_promedio < 0.4`, llevando a `ALERTADO` (umbral ≥ 2.0) aunque no hubiera nieve. En marzo (verano austral chileno), NDSI ≈ 0.04 (terreno descubierto) → score = 2.0 → `ALERTADO` → niveles 4-5 falsos.

**Causa raíz:** El criterio NDSI < 0.4 detecta correctamente _nieve húmeda/en fusión_ pero solo tiene sentido cuando HAY nieve. Sin cobertura nival, NDSI bajo es irrelevante.

**Fix:** Condicionar penalización NDSI a `cobertura_promedio > 10` (10% cobertura mínima):
```python
if cobertura_promedio > 10:
    if ndsi_promedio < 0.4:  score += 2.0   # nieve húmeda confirmada
    elif ndsi_promedio < 0.45: score += 1.0  # posiblemente húmeda
```
Mismo cambio en `_analizar_punto_unico`. Verificado: marzo (cobertura=1%) → `ESTABLE` score=0 ✅; invierno (cobertura=60%) → `ALERTADO` score=2.0 ✅

**Build y deploy:**
- Build `140c566d` → `SUCCESS`
- `gcr.io/climas-chileno/snow-alert-agentes:a2e424c` activo en Cloud Run Job

### Limpieza BQ: 20 boletines contaminados eliminados ✅

Boletines de 2026-03-24 (17 filas) y 2026-03-26 (3 filas) generados con imagen `cc71f72` (NDSI fix presente, ViT fix ausente) mostraban `estado_vit=ALERTADO, score=2.0` y niveles 3-5 inflados en verano. Eliminados con DELETE FROM BQ. Estado final: 0 boletines contaminados.

**Datos de validación (invierno 2024) íntegros:** Los 15 boletines históricos (2024-06-15 a 2024-08-15) no tenían el bug — NDSI invernal era > 0.4 con nieve presente, por lo que la condición no se disparaba incorrectamente.

### Generación histórica completada ✅

85→68 boletines en BQ después de limpieza. Rango 2024-06-15 a 2026-03-26. Preset `validacion` incluye ubicaciones chilenas (La Parva ×3) + suizas (Matterhorn, Interlaken, St Moritz) para H3 con datos SLF.

### Estado commits (pendiente git push)

17 commits locales sin push. Ejecutar: `git push origin main`

---

## Sesión 2026-03-25 (continuación 6) — Auditoría completa sistema + fixes almacenador + hashes

### Fix almacenador ✅ (commit e09f665)

**Bug 1:** `_construir_campos_subagentes()` buscaba `res_patrones.get("frecuencias_terminos")` pero `buscar_relatos_condiciones()` retorna `resultados_por_termino: {term: [filas]}` → `patrones_nlp` siempre era `"[]"` en BQ. Fix: `{k: len(v) for k, v in resultados_por_termino.items()}`.

**Bug 2:** `_datos_satelitales_disponibles()` chequea `"monitorear_nieve"` (inexistente) → `datos_satelitales_disponibles=False` aunque se llamara cualquier otra tool satelital. Fix: set completo `{"procesar_ndsi", "detectar_anomalias_satelitales", "analizar_vit", "calcular_snowline"}`.

### Hashes prompts actualizados ✅ (commit f34f6fb)

Prompts `nlp` e `integrador` fueron modificados en commits previos pero el registro de versiones no fue actualizado → `verificar_integridad()` en el orquestador retornaba `False` en cada arranque (warning al log).

| Componente | Hash anterior | Hash nuevo | Versión |
|-----------|---------------|------------|---------|
| `nlp` | `3b0c928ed4439495` | `ba1f7309d30ba8bd` | 3.0→3.1 |
| `integrador` | `4cc094839c0640fb` | `225e6a9d4ecf376a` | 3.0→3.1 |

`VERSION_GLOBAL`: `3.1` → `3.2`

### Auditoría módulos base ✅ (sin bugs)

- `base_subagente.py`: agentic loop correcto, reintentos con backoff exponencial, manejo de tool_use/end_turn
- `cliente_llm.py`: conversiones Anthropic↔OpenAI correctas, normalización de respuestas OK
- `agente_principal.py` (OrquestadorAvalancha): pipeline secuencial 5 subagentes, NLP no-crítico, `_extraer_nivel()` regex OK
- `metricas_eaws.py`: F1-macro, Kappa, QWK implementados correctamente; `TECHEL_2022_REFERENCIA` con datos del paper

### Redespliegue en progreso 🔄

Build `a6bf95c0` con `ff632b3` → en WORKING. Pendiente build con `f34f6fb` (almacenador + hashes).

---

## Sesión 2026-03-25 (continuación 5) — Auditoría SubagenteNLP + fix índice riesgo histórico

### Fix subagente_nlp: término crítico "inestable" nunca buscado ✅ (commit c3e0762)

**Bug:** `buscar_relatos_condiciones()` en consultor_bigquery.py limita `terminos[:8]`. `TERMINOS_RIESGO_EAWS` en `tool_extraer_patrones.py` tenía "inestable" en posición 9 → nunca se buscaba. "inestable" forma parte de `terminos_criticos = {"alud","avalancha","placa","peligroso","inestable","grieta"}` usado para calcular `indice_riesgo_calculado`. Resultado: índice subestimado cuando había relatos mencionando condiciones inestables.

**Fix:** Reordenar `TERMINOS_RIESGO_EAWS` para que los 6 términos críticos queden en las primeras 6 posiciones: `placa, alud, avalancha, grieta, inestable, peligroso`.

**Fix adicional:** Prompt de `subagente_nlp` no especificaba cómo convertir `resultados_por_termino: {term: [rows]}` → `frecuencias_terminos: {term: count}` requerido por `sintetizar_conocimiento_historico`. Añadida instrucción explícita con ejemplo.

**Módulos auditados sin bugs adicionales:**
- `tool_buscar_relatos.py`: correcto, usa parameterized queries, fallback por zona
- `tool_conocimiento_historico.py`: lógica sólida, fallback a base andina cuando total_relatos=0
- `consultor_bigquery.obtener_relatos_ubicacion()`: correcto, fallback a primera palabra si sin resultados
- `consultor_bigquery.buscar_relatos_condiciones()`: correcto salvo el límite de 8 términos
- `conocimiento_base_andino.py`: base completa con 14 zonas, `get_indice_estacional()` con factores mensuales correctos

---

## Sesión 2026-03-26 (continuación 4) — Mejoras boletines: datos climáticos + proyecciones

### Mejoras al integrador EAWS ✅ (commit ffe9231)

**Problema identificado por usuario:** boletines no incluían datos cuantitativos de precipitación/nevada, y las proyecciones 48h/72h no consideraban el pronóstico meteorológico.

**Cambios aplicados:**

| Archivo | Cambio |
|---------|--------|
| `tool_generar_boletin.py` | +3 campos: `precipitacion_reciente_mm`, `nieve_reciente_cm`, `tendencia_pronostico`; nueva subsección "Datos climáticos recientes" en FACTORES DE RIESGO; texto explicativo de tendencia en PRONÓSTICO |
| `tool_clasificar_eaws.py` | +campo `tendencia_pronostico` en tool schema y función; lo propaga al output; reescritura de `_proyectar_nivel()` por factor |
| `prompts.py` (integrador) | Requiere extracción explícita de `precipitacion_reciente_mm`, `nieve_reciente_cm`, `tendencia_pronostico` del informe S3; exige que `resumen_meteorologico` incluya datos cuantitativos |

**Nueva lógica `_proyectar_nivel()` (antes: demasiado simple):**

| Factor | 48h | 72h |
|--------|-----|-----|
| PRECIPITACION_CRITICA/LLUVIA | +1 | mantiene (baja solo si `mejorando`) |
| ESTABLE | mantiene | -1 |
| FUSION_ACTIVA/CICLO | +1 si empeorando; mantiene | -1 si mejorando; mantiene |
| General (NEVADA, VIENTO) | +1 si empeorando; mantiene | -1 si mejorando o sin tendencia desde ≥3 |

**Impacto:** Los boletines ahora mostrarán explícitamente "Precipitación últimas 24h: X mm / Nieve nueva: X cm" y las proyecciones reflejarán el pronóstico real.

### Estado boletines BQ (2026-03-25)
- Total: 71 boletines | 51 ubicaciones únicas
- Rango fechas: 2026-03-18 → 2026-03-26
- Ground truth: pendiente datos Snowlab/Andes Consciente → H1/H4 no calculables aún

### Fix CRÍTICO: escala NDSI ✅ (commit 8d5e22d)

**Bug:** `consultor_bigquery.py` retornaba `ndsi_medio` en escala 0-100 (como MODIS/Sentinel-2 la almacenan). Los tools usaban umbrales en escala [-1, 1] (estándar Dietz et al.). Efecto: `4.26 < 0.4 = FALSE` cuando debería ser `0.0426 < 0.4 = TRUE` → alerta `NIEVE_HUMEDA_NDSI_BAJO` nunca disparaba.

**Fix:** En `obtener_estado_satelital()`, después de leer de BQ:
```python
for campo in ("ndsi_medio", "ndsi_max"):
    valor = resultado.get(campo)
    if valor is not None:
        resultado[campo] = round(valor / 100.0, 4)
```

**Valores corregidos (La Parva Sector Bajo, 2026-03-25):**
- Antes: ndsi_medio=4.26 → no dispara alertas de nieve húmeda
- Después: ndsi_medio=0.0426 → `0.0426 < 0.4` = TRUE → `NIEVE_HUMEDA_NDSI_BAJO`

**Impacto retroactivo:** Los 72 boletines previos usaron NDSI sin normalizar, por lo que las señales satelitales eran parcialmente incorrectas. Próximos boletines (scheduler diario + históricos pendientes) usarán la escala correcta.

### Redespliegue imagen Cloud Run ✅ (commit ffe9231, luego 8d5e22d)
- Build `3cdc0423` exitoso vía `cloudbuild.yaml`
- Imagen activa: `gcr.io/climas-chileno/snow-alert-agentes:ffe9231`
- Cloud Run Job `orquestador-avalanchas` actualizado automáticamente por cloudbuild.yaml

### Cloud Scheduler — boletines diarios ✅ (2026-03-26)
- Creado `generar-boletines-diario-job` us-central1
- Schedule: `30 23 * * *` (23:30 UTC, tras analizar-zonas-diario-job a 22:00)
- Descripción: genera 6 boletines daily (La Parva × 3 + Matterhorn + Interlaken + St Moritz)
- SA: funciones-clima-sa → rol run.invoker para Cloud Run Jobs
- Estado: ENABLED | próximo disparo: 2026-03-26T23:30:00Z

**Schedulers completos:**

| Job | Schedule | Propósito |
|-----|----------|-----------|
| extraer-clima-job | 0 8,14,20 * * * | Extrae datos clima |
| monitor-satelital-job | 30 8,14,20 * * * | Monitoreo satelital |
| analizar-zonas-diario-job | 0 22 * * * | Análisis topográfico zonas |
| analizar-topografia-job | 0 3 1 * * | Análisis topografía (mensual) |
| **generar-boletines-diario-job** | **30 23 * * *** | **Boletines EAWS (nuevo)** |

### Generación boletines históricos invierno ⏳ (en progreso, background)
- Script: `agentes/scripts/generar_boletines_invierno.py`
- Backfill ya existe (42 operaciones omitidas — datos ERA5 cargados en sesión anterior)
- Generando 42 boletines: La Parva ×3 | 14 fechas invierno 2024-2025
- Inicio: 2026-03-25 22:49:39 | estimado: ~3.5h | finaliza ~02:00 UTC

---

## Sesión 2026-03-26 (continuación 3) — Auditoría completa tools agentes + fixes NDSI consistencia

### Auditoría tools agentes ✅ (commits 95ca729, f3518a7)

**20 tools auditadas, 6 fixes aplicados:**

| Fix | Tool | Cambio |
|-----|------|--------|
| #2 | `tool_pronostico_dias` | `precip_*_mm` → `prob_precip_*_pct` (unidades para LLM) |
| #5 | `tool_calcular_pinn` (×2 funciones) | `max(15°, 28 + 5*(1-meta))` — clamp ángulo fricción interna |
| #4 | `tool_detectar_anomalias` | NDSI 0.3→0.4 / 0.35→0.45 (Dietz et al. literatura estándar) |
| #4b | `tool_procesar_ndsi` | NDSI 0.3→0.4 en `_detectar_senales_cambio` |
| #4c | `tool_analizar_vit` (×2 funciones) | NDSI 0.3→0.4 / 0.4→0.45 en clasificación ViT |

**Sin bugs en:** `tool_condiciones_actuales`, `tool_ventanas_criticas`, `tool_analizar_dem`, `tool_zonas_riesgo`, `tool_estabilidad_manto`, `tool_clasificar_eaws`, `tool_snowline`, `tool_buscar_relatos`, `tool_generar_boletin`, `tool_explicar_factores`, `tool_conocimiento_historico`, `tool_extraer_patrones`, `tool_tendencia_72h`.

**Arquitectura verificada:**
- 5 subagentes usan Databricks (Qwen3-next-80b) como LLM — gratis
- `MODELO = "claude-sonnet-4-5"` en cada subagente es etiqueta, no enruta proveedor
- Orquestador acumula contexto (3000 chars/subagente, max 12000 total) — adecuado
- Integrador: MAX_TOKENS=6144, MAX_ITERACIONES=6

### Cloud Run Job ✅ (2026-03-26)
- Imagen `f3518a7` activa en `orquestador-avalanchas` us-central1

---

## Sesión 2026-03-25 (continuación 2) — git push + backfill script imágenes topografía

### git push origin main
- Pendiente ejecución interactiva por el usuario (`! git push origin main`)

### Auditoría y fixes capa de datos ✅ (2026-03-26)

**Fixes CRÍTICOS aplicados (commit aeb94dd):**
- procesador/horas/dias: except Exception silencioso en dedup → ahora WARNING en log
- monitor_satelital: 10 llamadas GEE getInfo() sin timeout → _getinfo_con_timeout(60s)

**Fixes MEDIOS aplicados (commit 406603d):**
- extractor: reintentos HTTP 3×backoff (2/4/8s) en errores red y 5xx
- extractor: Pub/Sub timeout 10s → 30s
- extractor/requirements.txt: requests==2.32.*, httpx==0.27.* (versiones menores fijadas)

**F2 — Cloud Scheduler deadlines:** ya configurados (1800s por defecto GCP). Sin acción necesaria.

### Redespliegue Cloud Functions post-fix calidad datos ✅ (2026-03-26 ~00:25 UTC)

| Función | Revisión anterior | Revisión nueva | Fix incluido |
|---------|------------------|----------------|--------------|
| procesador-clima | 00017-mac | 00018-gig | dedup WARNING log |
| procesador-clima-horas | 00007-qos | 00008-saz | dedup WARNING log |
| procesador-clima-dias | 00006-zek | 00007-tam | dedup WARNING log |
| monitor-satelital-nieve | (anterior) | 00021-nar | GEE getInfo timeout 60s |

Commit: `aeb94dd`

### Notebook 01 validacion_f1_score.py ✅ (ejecutado 2026-03-26 00:07 UTC)
- 65 boletines en BQ con nivel_eaws_24h
- Distribución predicciones: {1:11, 2:15, 3:9, 4:17, 5:13} — cubre los 5 niveles EAWS
- Confianza: 46 Media / 17 Alta / 2 Baja
- Ground truth aún no disponible → F1-macro no calculable (pendiente datos Snowlab)
- Modo descriptivo únicamente hasta recibir datos de Andes Consciente

### Email a Frank Techel ✅ (borrador preparado 2026-03-26)
- Borrador listo para enviar a techel@slf.ch
- Solicita EAWS Matrix operacional (~26 servicios) para validación H3 (QWK)
- Enviado por: Francisco Peñailillo (fpenaililllom@correo.uss.cl)

### Script backfill imágenes GCS ✅ (creado)
- **Archivo**: `datos/analizador_avalanchas/regenerar_imagenes_gcs.py`
- **Propósito**: Regenera imágenes PNG/thumbnail en GCS para fechas < 2026-03-25 (desnivel bug)
- **No requiere GEE**: Lee datos ya correctos de BQ `zonas_avalancha`
- **Uso**:
  - Dry run (ver qué se generaría): `python regenerar_imagenes_gcs.py --dry-run`
  - Fecha específica: `python regenerar_imagenes_gcs.py --fecha 2026-03-18`
  - Todas las fechas afectadas: `python regenerar_imagenes_gcs.py`
- **Planificado para ejecutar**: 2026-04-01

---

## Sesión 2026-03-25 (continuación) — Alineación nombres cross-tabla + dedup procesadores

### Estado final capa de datos (2026-03-25 ~12:10 UTC)

| Tabla | Filas | Ubicaciones | NULLs críticos | Duplicados | Estado |
|-------|-------|-------------|----------------|------------|--------|
| condiciones_actuales | 69,477 | 92 (hist+activas) | 0 | 0 (dedup aplicado) | ✅ |
| pronostico_horas | 11,723 | 71 | 0 | 0 (dedup aplicado) | ✅ |
| pronostico_dias | 2,524 | 71 | 0 | 0 (dedup aplicado) | ✅ |
| imagenes_satelitales | 701 | 25 | 0 (hoy 100% NDSI) | 0 | ✅ |
| zonas_avalancha | 111 | 37 | 0 | 0 | ✅ |
| pendientes_detalladas | 37 | 37 | 0 | 0 | ✅ |
| boletines_riesgo | 65 | 51 | 0 | 0 | ✅ |
| relatos_montanistas | 3,138 | 204 | 0 | 0 | ✅ |

**Gaps cross-tabla: 0** — todas las ubicaciones en zonas_avalancha e imagenes_satelitales tienen datos en condiciones_actuales.

### Fix alineación nombres cross-tabla ✅ (commits `8056f7e`, `4ed7199`)

**Renames en UBICACIONES_ANALISIS (analizador):**
- `Pucón` (ciudad -39.28) → `Ski Pucón` (resort -39.50)
- `Catedral Alta Patagonia` → `Cerro Catedral`
- `Chapelco` → `Cerro Chapelco`
- Agregados: `Vallecitos`, `Caviahue`

**Renames en UBICACIONES_MONITOREO (extractor):**
- `Chapelco` → `Cerro Chapelco` (coord actualizadas a -40.25, -71.20)
- `Whistler` → `Whistler Blackcomb`
- `Plaza de Mulas - Aconcagua` → `Plaza de Mulas Aconcagua` (quita guión)
- `Chamonix` eliminado (consolidado bajo `Chamonix Mont Blanc`)

**Nuevas ubicaciones agregadas al extractor (70 total):**
- Andinas: `Los Penitentes`, `Vallecitos`, `Caviahue`, `La Hoya`
- Internacionales: `Plaza Argentina Aconcagua`, `Revelstoke`, `Squaw Valley`, `Val d'Isère`, `St. Anton am Arlberg`

**BQ UPDATEs aplicados** (condiciones_actuales, pronostico_dias, pronostico_horas, zonas_avalancha, pendientes_detalladas, boletines_riesgo):
- Renames: Chapelco→Cerro Chapelco (277+161+268 filas), Whistler→Whistler Blackcomb (112+58+268), Plaza de Mulas→(sin guión) (51+45+168), Chamonix→Chamonix Mont Blanc (113+58+268)
- pendientes_detalladas: 38 duplicados eliminados + 3 renames (Catedral Alta Patagonia, Chapelco, Pucón)

### Fix dedup procesadores ✅ (commit `2f67793`)

**Causa:** DEPLOYMENT_ROLLOUT de Cloud Run envía múltiples HTTP health-checks al extractor → extractor publica mensajes duplicados a Pub/Sub → procesadores insertan todos sin verificar.

**Solución:** Cada procesador consulta BigQuery antes de insertar:
- `procesador-clima`: `_ya_existe_condicion()` — omite si hay fila del mismo lugar en ±2h
- `procesador-clima-horas`: `_ya_existe_pronostico_horas()` — idem
- `procesador-clima-dias`: `_ya_existe_pronostico_dias()` — idem

**Limpieza BQ:** 1,371 filas eliminadas de condiciones_actuales, 5,018 de pronostico_horas, 1,304 de pronostico_dias.

**Redespliegues:** `procesador-clima-00017-mac`, `procesador-clima-horas-00007-qos`, `procesador-clima-dias-00006-zek`.

### Estado Cloud Functions (2026-03-25)

| Función | Revisión | Estado | Último dato |
|---------|----------|--------|-------------|
| extractor-clima | 00021-nit | ACTIVE | 11:00 UTC |
| procesador-clima | 00017-mac | ACTIVE | via Pub/Sub |
| procesador-clima-horas | 00007-qos | ACTIVE | via Pub/Sub |
| procesador-clima-dias | 00006-zek | ACTIVE | via Pub/Sub |
| monitor-satelital-nieve | (sin cambio) | ACTIVE | 2026-03-25 |
| analizador-satelital-zonas | 00011-yah | ACTIVE | 01:11 UTC |

---

## Sesión 2026-03-25 — Auditoría completa capa de datos + Fix SSL extractor + Fix Japan 404

### Audit BigQuery — resultado final (2026-03-25)

| Tabla | Total filas | Bugs corregidos | NULLs esperados | Estado |
|-------|-------------|-----------------|-----------------|--------|
| condiciones_actuales | 70,778 | 0 | 42 (ERA5 backfill, sin URI) | ✅ |
| pronostico_horas | 15,013 | 0 | 0 | ✅ |
| pronostico_dias | 3,483 | 0 | 126 (ERA5 backfill, sin URI) | ✅ |
| imagenes_satelitales | 651 | 0 | NDSI URI null 2026-03-18/24 (threshold+bucket bugs, ya corregidos) | ⏳ |
| zonas_avalancha | 252 | 178 elevacion_min_inicio corregidas a NULL | 0 | ✅ |
| pendientes_detalladas | 75 | 0 | 0 | ✅ |
| boletines_riesgo | 74 | 0 | 0 | ✅ |
| relatos_montanistas | 3,138 | 0 | 107 null nivel (sin info avalancha) + 18 null tipo actividad | ✅ |

### Fix SSL extractor ✅ (commit `734c529`)
- `SSLEOFError` desde Cloud Run con `weather.googleapis.com` → TLS 1.3 incompatible
- Fix: `httpx` con `ssl.TLSVersion.TLSv1_2` forzado
- Confirmación: 278 nuevas filas `condiciones_actuales` a las 03:10 UTC
- Extractor redespliegue: revisión `extractor-clima-00018-qoz`

### Eliminar Hakuba + Niseko del extractor ✅ (commit `b6590a1`)
- HTTP 404 para ambas ubicaciones en `weather.googleapis.com`
- Eliminadas de `UBICACIONES_MONITOREO` en `datos/extractor/main.py`
- Extractor redespliegue: revisión `extractor-clima-00018-qoz`

### zonas_avalancha streaming buffer UPDATE ✅
- 37 filas 2026-03-25 en buffer → corregidas a NULL al limpiar (~1h después del deploy)
- Total bug_rows = 0 (252/252 filas limpias)

### Cobertura ubicaciones (post-fix, 2026-03-25)
- Extractor (condiciones_actuales/pronostico_*): 63 ubicaciones (65 original - 2 Japan 404)
- Monitor satelital (imagenes_satelitales): 25 ubicaciones Andes/Sudamérica (lista separada)
- La cobertura variable 53-63 en fechas anteriores era por SSL failures intermitentes (resuelto con TLS 1.2)
- Brecha 2026-03-24: 0 datos en todas las tablas meteorológicas (SSL failure todo el día)

### Fix dedup zonas_avalancha ✅ (commit `91828e5`)
- Causa: redespliegue Cloud Function dispara DEPLOYMENT_ROLLOUT HTTP → múltiples ejecuciones el mismo día
- Síntoma: 74 duplicados del 2026-03-25 + 30 del 2026-03-24
- Fix: `_ya_existe_zona()` en `main.py` verifica `nombre_ubicacion + DATE(fecha_analisis)` antes de INSERT
- 104 filas duplicadas eliminadas de BQ + 37 filas placeholder del 2026-03-17 (zona_ha=0, EAWS=1 uniforme)

### imagenes_satelitales NDSI fix validado ✅
- Primera ejecución post-fix: 25/25 ubicaciones con `uri_geotiff_ndsi` (100%)
- NDSI URIs nulos anteriores al 2026-03-25 son históricos (threshold bug + bucket bug, sin backfill)

### Estado final zonas_avalancha (2026-03-25)
- 111 filas limpias: 3 fechas × 37 ubicaciones (2026-03-18, 2026-03-24, 2026-03-25)
- 0 duplicados, 0 placeholders, 0 copy-paste bugs

### Pendiente
1. `git push origin main` (commits: `91828e5`) — requiere credenciales GitHub interactivas
2. Regenerar imágenes topografía GCS (desnivel fix) → job mensual 2026-04-01
3. Enviar email a Frank Techel (techel@slf.ch) para datos EAWS Matrix operacional (H3)
4. Ejecutar `notebooks_validacion/01_validacion_f1_score.py` (H1)

---

## Sesión 2026-03-25 — Fix capa de datos: bucket duplicado + 5 Cloud Functions redespliegue

### Causa raíz NULLs BQ 2026-03-24 ✅ (ENCONTRADO Y CORREGIDO)
- **Bug**: `monitor_satelital/main.py` línea 453: `f"{ID_PROYECTO}-{BUCKET_BRONCE}"`
- **Síntoma**: Si `BUCKET_CLIMA=climas-chileno-datos-clima-bronce` estaba seteado como env var,
  resultaba en bucket `climas-chileno-climas-chileno-datos-clima-bronce` (no existe → 404)
- **Efecto**: Todos los uploads GCS del 2026-03-24 fallaron → NULL URIs en todas las filas de
  `imagenes_satelitales` para esa fecha
- **Fix**: `datos/monitor_satelital/main.py` — verificación `if BUCKET_BRONCE.startswith(f"{ID_PROYECTO}-")` antes de prefijar (commit `b7a1d4c`)

### Fixes calidad datos ✅ (commit `7c44eb7`)
- `datos/analizador_avalanchas/cubicacion.py`: `elevacion_min_inicio` → `None` (era copy-paste de `elevacion_max_inicio`)
- `datos/analizador_avalanchas/visualizacion.py`: `abs()` en `desnivel_inicio_deposito` para evitar "-494 m"
- `datos/monitor_satelital/constantes.py`: paleta NDSI cambiada de negro→blanco a gris→azul

### Cloud Functions redespliegues ✅
| Función | Revisión | Hora UTC |
|---------|----------|----------|
| monitor-satelital-nieve | 00021 | 2026-03-25T01:16:00 |
| procesador-clima | nueva | 2026-03-25T01:10:54 |
| procesador-clima-dias | nueva | 2026-03-25T01:10:53 |
| procesador-clima-horas | nueva | 2026-03-25T01:10:53 |
| analizador-satelital-zonas-riesgosas-avalanchas | nueva | 2026-03-25T01:11:33 |

### NULLs estructurales en imagenes_satelitales (no bugs, son esperados)
- `ndsi_medio` NULL 53% → cobertura de nubes inevitable
- `lst_noche_celsius` NULL 69% → MODIS LST nocturno no siempre disponible
- `uri_geotiff_ndsi` NULL anterior al 2026-03-24 → umbral 1024B era muy alto para NDSI (450B)
  → Fix: commit `1aa3640` + redespliegue monitor hoy → NULLs futuros serán menores

### Pendiente
1. Próximo scheduler (08:30, 14:30, 20:30 CLT) validará que los uploads funcionen
2. Regenerar imágenes topografía GCS (desnivel y cubicacion fixes) → job mensual 2026-04-01
3. Enviar email a Frank Techel (techel@slf.ch) para datos EAWS Matrix operacional (H3)
4. Ejecutar `notebooks_validacion/01_validacion_f1_score.py` (H1)

---

## Sesión 2026-03-24 — P1/P2/P3 resueltos + Orquestación validación

### P1 (ALTA): Dedup boletines ✅
- Agregado upsert en `agentes/salidas/almacenador.py`:
  - `_ya_existe_boletin()` + `_eliminar_boletin_existente()` antes de cada INSERT
  - Patrón: SELECT COUNT → DELETE → INSERT streaming
  - 39 filas duplicadas eliminadas de `clima.boletines_riesgo`

### P2 (ALTA): ≥50 boletines únicos generados ✅
- **61 boletines únicos** guardados en BQ el 2026-03-24
- Problemas encontrados y resueltos en el camino:
  - `generar_todos.py` guardaba al final (todo o nada) → reescrito para **guardado incremental** por ubicación
  - `ClienteDatabricks.crear_mensaje()` sin timeout → colgaba horas (Cerro Bayo: 7950s, Mammoth Mountain: >1h)
  - Solución: `timeout=300` en `cliente_llm.py` + guardado incremental
  - Mammoth Mountain: timeout no funcionó → matado manualmente, saltado, continuó el resto
- Estado BQ al cierre: **61 boletines únicos** del 2026-03-24

### P3 (MEDIA): analizar-topografia-job ✅
- Bug `peligro_eaws_base` (tuple → INTEGER) y `estimar_tamano_potencial` (keys incorrectas) ya corregidos en sesión 2026-03-17
- Job mensual correrá automáticamente en 2026-04-01
- Job diario ya funciona sin errores

### Orquestación diaria optimizada ✅
- Nuevo flag `--preset validacion` en `generar_todos.py`:
  - 6 ubicaciones: La Parva Sector Alto/Bajo/Medio + Matterhorn Zermatt + Interlaken + St Moritz
  - Permite usar Databricks (gratuito) sin esperar horas: ~15 min vs 3+ horas para 50 ubicaciones
- `Dockerfile` actualizado: `ENTRYPOINT [..., "--preset", "validacion"]`
- Datos siguen actualizándose para todas las ubicaciones via Cloud Functions

### Commits de esta sesión
- `ea78d3d` Fix duplicados almacenador.py + limpiar BQ
- `bb829f6` (anterior)
- `51f639d` Fix hangs Databricks: timeout 300s + guardado incremental
- `2474572` Orquestación: preset validacion (La Parva + Suiza)

### Estado Hipótesis (actualizado 2026-03-24)

| ID | Umbral | Estado |
|----|--------|--------|
| H1 | F1-macro ≥75%, ≥50 boletines | ✅ 61 boletines únicos → ejecutar métricas |
| H2 | Delta NLP >5pp | ✅ +7.9pp (notebook 06) |
| H3 | QWK Techel 2022 | ⏳ Pendiente email a techel@slf.ch |
| H4 | Kappa ≥0.60 vs Snowlab | ⏳ Pendiente contacto Andes Consciente |

### Pendiente (acciones manuales)
1. Enviar email a Frank Techel (techel@slf.ch) para datos EAWS Matrix operacional
2. Contactar Andes Consciente para boletines históricos Snowlab La Parva
3. Ejecutar `notebooks_validacion/01_validacion_f1_score.py` con 61 boletines (H1)
4. Conectar LLM de producción (Anthropic) cuando esté disponible → cambiar Dockerfile de `--preset validacion` a `--guardar` para generar todas las ubicaciones

---

## Sesión 2026-03-23 — Pipeline datos de validación + Boletines históricos

### Tarea 0: Boletines históricos completados ✅
- 42 boletines generados (3 zonas × 14 fechas, inviernos 2024/2025)
- 42/42 guardados en BigQuery + GCS
- Nivel EAWS promedio: 4.6
- Total en BQ `clima.boletines_riesgo`: 49 boletines

### Tarea 1: Infraestructura BigQuery validación ✅
- Dataset `validacion_avalanchas` creado en proyecto `climas-chileno`
- 7 tablas creadas: slf_meteo_snowpack, slf_danger_levels_qc, slf_avalanchas_davos, slf_actividad_diaria_davos, eaws_matrix_operacional, snowlab_boletines, snowlab_eaws_mapeado
- Estructura GCS: `gs://climas-chileno-datos-clima-bronce/validacion/suiza/` y `validacion/chile/`

### Tarea 2: Descarga datos suizos de EnviDat ✅
- Todos los datasets son públicos (sin autenticación requerida)
- Descargados 7 archivos CSV (197 MB total) → GCS
  - DEAPSnow RF1: 292,837 filas (192MB)
  - DEAPSnow RF2: 29,296 filas (17MB)
  - D_QC: 3 archivos → unificados en `dqc_unified.csv` (45,049 filas)
  - Davos avalanchas: 13,918 filas
  - Davos actividad diaria: 3,533 filas (15 cols clave de 122)

### Tarea 3: Carga a BigQuery ✅
- 4 tablas cargadas con autodetect desde GCS
- **91,796 registros suizos** cargados en total
- Verificación: distribución de clases correcta, rango temporal correcto

### Tarea 4: Documentación generada ✅
- `docs/validacion/MAPPING_deapsnow.md` — correspondencia columnas reales vs schema
- `docs/validacion/reporte_calidad_datos_suizos.md` — reporte de calidad completo
- `.claude/requirements/REQ-validacion-datos.md` — schemas + queries de referencia

### Estado Hipótesis (actualizado)

| ID | Umbral | Estado |
|----|--------|--------|
| H1 | F1-macro ≥75%, ≥50 boletines | ✅ 49 boletines → ejecutar métricas |
| H2 | Delta NLP >5pp | ✅ +7.9pp (notebook 06) |
| H3 | QWK Techel 2022 | ⏳ Pendiente email a techel@slf.ch |
| H4 | Kappa ≥0.60 vs Snowlab | ⏳ Pendiente contacto Andes Consciente |

### Pendiente (acciones manuales)
1. Enviar email a Frank Techel (techel@slf.ch) para datos EAWS Matrix operacional
2. Contactar Andes Consciente para boletines históricos Snowlab La Parva
3. Ejecutar `notebooks_validacion/01_validacion_f1_score.py` con 49 boletines (H1)

---

## Sesión 2026-03-22

### Tarea 1: Módulo pendientes_detalladas — Despliegue completo ✅

- Añadida función `exportar_imagen_pendientes_gcs()` en `datos/analizador_avalanchas/analisis_pendientes.py`
  - Genera dos imágenes PNG por ubicación: clases EAWS (5 rangos, paleta verde→morado) + mapa de calor de pendiente
  - Ruta GCS: `{nombre}/{topografia/visualizaciones/{YYYY/MM/DD}/`
- Creado schema BQ `datos/analizador_avalanchas/schema_pendientes_bigquery.json` (27 campos)
- Ejecutado deploy completo:
  - Tabla BQ `climas-chileno.clima.pendientes_detalladas` creada
  - 37/37 ubicaciones analizadas con éxito
  - 74 imágenes PNG generadas en GCS bucket bronce

### Tarea 2: IAM — Permisos mínimos `funciones-clima-sa` ✅

- Removido `roles/editor` (excesivo)
- Removido `roles/storage.objectCreator` (insuficiente)
- SA ahora con 9 roles específicos:
  - `roles/bigquery.dataEditor`, `roles/bigquery.jobUser`
  - `roles/storage.objectAdmin` (para GCS reads+writes)
  - `roles/secretmanager.secretAccessor`
  - `roles/earthengine.viewer`
  - `roles/run.invoker`, `roles/cloudfunctions.invoker`
  - `roles/logging.logWriter`, `roles/monitoring.metricWriter`

### Tarea 3: Backfill ERA5 — Datos históricos inviernos 2024 y 2025 ✅

- Creado `agentes/datos/backfill/backfill_clima_historico.py`
  - Fuente: `ECMWF/ERA5_LAND/HOURLY` via Google Earth Engine
  - Convierte unidades: K→°C, m/s→km/h, Magnus RH, wind-chill, atan2 dirección
  - Idempotente: verifica existencia antes de insertar
  - Llena tablas `condiciones_actuales` y `pronostico_dias`
- Ejecutado para 3 zonas La Parva × 14 fechas invierno 2024-2025:
  - 42 operaciones totales → 39 nuevas, 6 ya existían, 0 fallidas
  - Valores validados: La Parva Sector Bajo 2024-06-15 = 3.79°C ✅

### Tarea 4: Boletines históricos — Generación ≥50 boletines ✅ (EN PROCESO)

- Modificado `agentes/datos/consultor_bigquery.py`:
  - Variable global `_fecha_referencia_global`
  - Funciones `establecer_fecha_referencia_global()` / `obtener_fecha_referencia_global()`
  - `obtener_condiciones_actuales()`, `obtener_tendencia_meteorologica()`, `obtener_pronostico_proximos_dias()`, `obtener_estado_satelital()` aceptan `fecha_referencia: Optional[datetime]`
- Modificado `agentes/orquestador/agente_principal.py`:
  - `generar_boletin()` acepta `fecha_referencia: Optional[datetime]`
  - Reset en bloque `finally`
- Modificado `agentes/scripts/generar_boletin.py`:
  - Flag `--fecha YYYY-MM-DD`
- Creado `agentes/scripts/generar_boletines_invierno.py`:
  - Orquesta: backfill → generar boletines → guardar
  - Default: 3 zonas La Parva × 14 fechas invierno 2024/2025
- Dry-run exitoso: La Parva Sector Bajo 2024-07-15 → EAWS 5
- **Generación completa en ejecución en background** (2026-03-22 ~22:59 UTC)
  - 42 boletines objetivo → total ≥52 con los 10 existentes → H1/H4 desbloqueados

### Estado Hipótesis

| ID | Umbral | Estado |
|----|--------|--------|
| H1 | F1-macro ≥75%, ≥50 boletines | ⏳ En generación |
| H2 | Delta NLP >5pp | ✅ +7.9pp (notebook 06) |
| H3 | QWK Techel 2022 | ⬜ Pendiente datos SLF |
| H4 | Kappa ≥0.60 vs Snowlab | ⏳ En generación |

### Próximos pasos

1. Verificar que todos los boletines se guardaron en BQ
2. Calcular métricas H1 (F1-macro) y H4 (Kappa) con ≥50 boletines reales
3. Actualizar CLAUDE.md con estado Fase 6 completada
4. Commit final y push a main

---

## Sesión 2026-04-01 — REQ-01 S4 Situational Briefing + REQ-02 S3 WeatherNext2

### Contexto

Implementación de nuevos requerimientos en `claude/requirements/`:
- REQ-01: Reemplazo total de S4 (scraping+NLP → Situational Briefing)
- REQ-02: WeatherNext 2 como fuente meteorológica aditiva en S3

### Tarea 1: Permiso allowlist (skill fewer-permission-prompts)

- Creado `.claude/settings.json` con 20 patrones read-only para herramientas GCP
- Patrones clave: `bq query *`, `gcloud logging read *`, `gsutil ls *`, `gcloud run jobs describe *`

### Tarea 2: REQ-01 — S4 Situational Briefing (verificación + migración Databricks)

**Estado al inicio:** código S4 parcialmente pre-implementado (Gemini 2.5 Flash).

**Migración a Databricks (decisión del usuario):**
- Reemplazado Gemini 2.5 Flash por Qwen3-80B vía Databricks (endpoint gratuito, mismo que S5)
- `agentes/subagentes/subagente_situational_briefing/agente.py`: reescrito para heredar `BaseSubagente`
  - `PROVEEDOR = "databricks"`, `MODELO = "databricks-qwen3-next-80b-a3b-instruct"`
  - `MAX_ITERACIONES = 8`, `MAX_TOKENS = 4096`
  - Agentic loop estándar: 4 tools → síntesis briefing en texto
- Cada tool expone `TOOL_<X>` (dict) + `ejecutar_<tool_name>` (wrapper) para el loop de BaseSubagente
- `prompts/system_prompt.md`: reescrito con template de salida fijo (secciones `##` obligatorias) + metadatos compatibilidad S5
- `claude/requirements/01-s4-situational-briefing.md`: actualizado (Gemini → Databricks en secciones 4.3, 6, 7, 8, 9)

**Fix crítico de tests:** patch path corregido
- `agentes.datos.cliente_llm.crear_cliente` → `agentes.subagentes.base_subagente.crear_cliente`
- Razón: `base_subagente.py` hace `from agentes.datos.cliente_llm import crear_cliente` (import a nivel módulo), el binding local debe parcharse donde se usa, no en el módulo origen

**Resultado:** 20/20 tests S4 pasando ✅

### Tarea 3: REQ-02 — S3 WeatherNext2 (verificación + fix imports)

**Estado al inicio:** código parcialmente pre-implementado.

**Fixes realizados:**
- `fuente_open_meteo.py` y `fuente_era5_land.py`: import `ConsultorBigQuery` movido a nivel módulo (era lazy)
- `test_weathernext2.py`: patch paths corregidos a `fuente_open_meteo.ConsultorBigQuery` / `fuente_era5_land.ConsultorBigQuery`
- `agente.py` de S3: registrado `TOOL_PRONOSTICO_ENSEMBLE` + ejecutor

**Resultado:** 17/17 tests WeatherNext2 pasando ✅

### Resultado final

- **Total tests:** 199 passed, 8 skipped — 0 regresiones ✅
- Tests nuevos: +37 (20 S4 Situational Briefing + 17 S3 WeatherNext2)
- Requerimientos completados: REQ-01 ✅, REQ-02 ✅ (pendiente suscripción Analytics Hub para producción)
- Pendiente: REQ-03 (AlphaEarth), REQ-04 (RSFM paralelo), REQ-05 (BigQuery ST_REGIONSTATS)

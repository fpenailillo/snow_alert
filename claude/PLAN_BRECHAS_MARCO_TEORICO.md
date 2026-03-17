# Plan de Trabajo: Brechas Marco Teórico vs Implementación

> Generado: 2026-03-17 | Auditoría completa de 7 dimensiones académicas
> Tesina: Francisco Peñailillo — Magíster TI, UTFSM — Dr. Mauricio Solar

---

## Estado General

| Dimensión | Estado | Score |
|-----------|--------|-------|
| 1. Arquitectura Multi-Agente | ✅ Completo | 10/10 |
| 2. PINNs (manto nival) | ⚠️ Parcial | 6/10 |
| 3. Vision Transformers (ViT) | ⚠️ Parcial | 6/10 |
| 4. Escala EAWS + Matriz | ✅ Completo (gaps menores) | 8/10 |
| 5. NLP Relatos Montañistas | ⚠️ Parcial (sin datos) | 5/10 |
| 6. Infraestructura Serverless | ✅ Completo | 9/10 |
| 7. Métricas de Validación | ⚠️ Parcial (framework + Techel benchmark, sin datos) | 7/10 |

**Alineación general: MEDIA-ALTA (54/70)**

---

## Brechas Detectadas

### BRECHAS CRÍTICAS (bloquean la defensa)

#### B1. Tabla `boletines_riesgo` no existe en BigQuery
- **Dimensión:** 7 (Validación)
- **Impacto:** Sin registro de predicciones no hay F1-score, Kappa, ni análisis de ablación
- **Evidencia:** `bq show climas-chileno:clima.boletines_riesgo` → Not found
- **Schema listo:** `agentes/salidas/schema_boletines.json` (27 campos)
- **Bloquea:** H1, H2, H3, H4

#### B2. Sin notebooks de validación ni framework de métricas
- **Dimensión:** 7 (Validación)
- **Impacto:** H1 (F1≥75%), H3 (transfer learning SLF), H4 (Kappa≥0.60) indefendibles
- **Evidencia:** Carpeta `notebooks_validacion/` no existe, no hay scripts de comparación
- **Bloquea:** H1, H3, H4

#### B3. Relatos de montañistas no cargados en BigQuery
- **Dimensión:** 5 (NLP)
- **Impacto:** SubagenteNLP retorna `confianza="Baja"`, `indice=0.0` sin datos
- **Evidencia:** Tabla `clima.relatos_montanistas` — estado de datos desconocido/vacío
- **Código listo:** `consultor_bigquery.py:551-710` (métodos completos)
- **Bloquea:** H2 (mejora >5pp)

### BRECHAS PROBLEMÁTICAS (el comité cuestionará)

#### B4. ViT opera sobre métricas escalares, no sobre imágenes satelitales
- **Dimensión:** 3 (ViT)
- **Impacto:** Comité esperará análisis de imágenes; implementación usa vectores [NDSI, LST, cobertura]
- **Evidencia:** `tool_analizar_vit.py:2-9` dice "Simula un ViT"
- **Atención:** Solo temporal, no espacial (sin patch embedding)
- **Mitigación:** Documentar como "Temporal Transformer sobre representaciones densas"

#### B5. Gradiente térmico PINN no se calcula desde datos satelitales reales
- **Dimensión:** 2 (PINNs)
- **Impacto:** El gradiente es parámetro de entrada, no calculado como `(LST_día - LST_noche) / (snow_depth × 100)`
- **Evidencia:** `tool_calcular_pinn.py:28-30` — `gradiente_termico_C_100m` es input
- **Datos necesarios:** `imagenes_satelitales.lst_dia_celsius`, `lst_noche_celsius`, `era5_snow_depth`

#### B6. Tamaño EAWS siempre = 2 (nunca se calcula dinámicamente)
- **Dimensión:** 4 (EAWS)
- **Impacto:** 1/3 de la matriz de decisión está hardcodeado
- **Evidencia:** `tool_clasificar_eaws.py:122` → `tamano = contexto.get('tamano_eaws', 2)`
- **Función existe:** `eaws_constantes.py:406-470` `estimar_tamano_potencial()` — nunca llamada
- **Requiere:** Tabla `zonas_avalancha` con datos O cálculo directo desde DEM

#### B7. Tabla `zonas_avalancha` vacía
- **Dimensión:** 2, 4 (PINNs, EAWS)
- **Impacto:** PINN usa métricas por defecto; tamaño EAWS no se puede estimar
- **Evidencia:** Pipeline mensual `analizar-topografia-job` no ha generado datos aún
- **Cloud Function:** `analizador-satelital-zonas-riesgosas-avalanchas` (ACTIVE)

### BRECHAS JUSTIFICABLES (diferencias válidas entre teoría e implementación)

#### B8. ViT sobre métricas vs imágenes crudas
- **Justificación:** NDSI, LST, SWE son representaciones densas de procesamiento GEE. Self-attention temporal es línea activa de investigación (Zhou et al. 2021). Sin GPU disponible en Cloud Functions.
- **Documentar en tesina:** "ViT adaptado sin GPU, operando sobre representaciones densas de métricas satelitales extraídas por Google Earth Engine"

#### B9. Capas débiles como clasificación, no probabilidad escalar
- **Justificación:** Estado del manto (CRITICO/INESTABLE/MARGINAL/ESTABLE) es clasificación ordinal más operativa que P∈[0,1]
- **Evidencia:** `tool_calcular_pinn.py:217-219` (alerta si metamorfismo>1.3)
- **Documentar en tesina:** "La probabilidad de capas débiles se expresa como clasificación ordinal alineada con EAWS"

#### B10. NLP como enriquecimiento contextual, no factor EAWS directo
- **Justificación:** Diseño intencional documentado en `prompts.py:64`
- **Documentar en tesina:** "El SubagenteNLP opera como capa de validación heurística complementaria"

#### B11. Frecuencia base solo desde topografía
- **Justificación:** `eaws_constantes.py:381-386` documenta diseño escalonado
- **Documentar en tesina:** "Fase 1 del modelo; frecuencia se amplificará con factores meteorológicos en iteraciones futuras"

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
| B2 | Si vacía: scraping Andeshandbook + carga BQ | `datos/relatos/cargar_relatos.py` — ETL completo (JSON/CSV→BQ, normalización zonas, dedup, batch). Schema: `datos/relatos/schema_relatos.json` (12 campos) | B3 | ✅ Script listo 2026-03-17 — pendiente: ejecutar con datos reales + GCP auth |
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

## Orden de Ejecución Recomendado

```
Semana 1:  A1 → A2 → A3 → B1 → B3 → B4
           (crear tabla, generar boletines piloto, verificar datos)

Semana 2:  B2 → C1 → C2 → C3 → C4
           (cargar relatos, cerrar brechas de código)

Semana 3:  A4 → D1 → D2 → D3 → D4
           (desplegar Cloud Run, crear notebooks validación)

Semana 4:  D5 → E1 → E2 → E3 → E4 → E5
           (documentación y justificaciones para tesina)
```

---

## Checklist de Verificación Pre-Defensa

- [ ] Tabla `boletines_riesgo` con ≥50 boletines generados
- [ ] F1-score macro calculado y reportado (H1: ≥75%)
- [ ] Análisis de ablación con/sin NLP (H2: >5pp)
- [ ] Comparación con Snowlab si datos disponibles (H4: Kappa≥0.60)
- [ ] Tamaño EAWS calculado dinámicamente (no default=2)
- [ ] Gradiente térmico PINN calculado desde LST real
- [ ] Relatos cargados en BigQuery (≥1,000 para significancia)
- [ ] Cloud Run Job desplegado y ejecutando automáticamente
- [ ] Justificaciones de brechas B8-B11 escritas en tesina
- [ ] Diagrama de arquitectura actualizado con 5 subagentes

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

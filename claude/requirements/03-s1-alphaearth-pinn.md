# 03 — S1: Reemplazo con AlphaEarth + Copernicus GLO-30 + TAGEE

**Subagente:** S1 — Topográfico
**Tipo de cambio:** Reemplazo total
**Prioridad:** Media-alta (mejora calidad de start zones EAWS)
**Estimación:** 24-32 horas

---

## 1. Objetivo

Reemplazar la implementación actual de S1 (PINN sobre NASADEM 30m con análisis básico de slope/aspect) por un stack moderno:

- **DEM:** Copernicus GLO-30 (sustituye NASADEM, mejor calidad en montaña)
- **Atributos terreno:** TAGEE (13 atributos, incluye curvatura horizontal/vertical)
- **Caracterización persistente:** AlphaEarth Satellite Embeddings (64D fusión multi-sensor)
- **Inferencia PINN:** opcionalmente vía `ee.Model.fromVertexAi()` para servir el PINN como endpoint Vertex AI consumido directamente desde Earth Engine

El PINN actual no se descarta sino que **se enriquece** con embeddings AlphaEarth como features adicionales y se beneficia de un DEM superior.

---

## 2. Justificación del cambio

- **NASADEM 30m** tiene errores significativos en topografía abrupta andina; **Copernicus GLO-30** entrega banda de error y es el estándar de facto para análisis montañoso 2025+.
- **AlphaEarth Satellite Embeddings** (lanzado 30 julio 2025, cobertura Chile 2017-2024 completa) entrega 64 dimensiones por píxel @10m que fusionan Sentinel-1/2, Landsat, GEDI lidar, Copernicus DEM, ERA5-Land, PALSAR-2, GRACE. Reportado: **24% menor error** que métodos previos en 15+ benchmarks.
- **TAGEE** (Terrain Analysis in Earth Engine) computa atributos no disponibles nativamente: curvatura horizontal/vertical, shape index, Northness/Eastness — directamente útiles para identificar zonas de convergencia de runout.
- **`ee.Model.fromVertexAi()`** elimina infra custom de inferencia: el PINN se sirve desde Vertex y se llama desde EE como `ee.Image`.

---

## 3. Caveat crítico sobre AlphaEarth

**AlphaEarth es un layer ESTÁTICO anual.** Codifica firmas persistentes de terreno/nieve, NO captura el estado del snowpack en ciclos de tormenta.

**Uso correcto:**
- ✅ Caracterización topográfica multi-año (ej: detección de nuevos abanicos de detritos, retroceso de glaciares, líneas de árboles)
- ✅ Features adicionales del PINN para predicción de start zones
- ✅ Búsqueda de similaridad entre eventos avalanchosos históricos
- ❌ NO usar como señal operacional de nieve diaria (eso es trabajo de S2)

---

## 4. Estado actual

**A revisar en el repo (Claude Code debe inspeccionar):**

- `subagents/s1_*` (estructura del agente topográfico)
- Script GEE existente para análisis de pendientes en La Parva/Valle Nevado (mencionado en memoria)
- Tabla `pendientes_detalladas` (22 campos, estado: requirement pendiente según memoria)
- `tools/tool_analizar_dem.py` (mencionado en memoria)
- PINN actual: archivos de modelo, weights, training scripts

---

## 5. Estado deseado

### 5.1 Estructura de módulos

```
subagents/s1_topografico/
├── data/
│   ├── dem_loader.py              # Copernicus GLO-30 (reemplaza NASADEM)
│   ├── alphaearth_loader.py       # NUEVO - embeddings 64D
│   └── tagee_wrapper.py           # NUEVO - 13 atributos TAGEE
├── pinn/
│   ├── model.py                   # PINN existente (preservar)
│   ├── features.py                # NUEVO - construye feature stack incluyendo AE
│   ├── inference_local.py         # Inferencia local (preservar para fallback)
│   └── inference_vertex.py        # NUEVO - via ee.Model.fromVertexAi()
├── eaws/
│   ├── slope_classifier.py        # EAWS bins (<30, 30-35, 35-45, 45-60, >60)
│   ├── start_zone_detector.py     # Lógica zonas de inicio
│   ├── runout_detector.py         # NUEVO - usa curvatura TAGEE
│   └── deposition_detector.py     # NUEVO - zonas de depósito (más críticas para alertas)
├── export/
│   └── pendientes_detalladas_export.py  # Llena tabla BQ existente
└── tests/
```

### 5.2 Features para PINN

Stack de features actualizado:

```python
# Geometría (existente, reemplazando NASADEM por GLO-30)
slope_deg, aspect_deg, elevation_m, curvature_basic

# TAGEE (nuevos - 13 atributos)
curvature_horizontal, curvature_vertical, shape_index,
northness, eastness, slope_length, terrain_roughness, ...

# AlphaEarth (nuevo - 64 dimensiones)
ae_dim_00, ae_dim_01, ..., ae_dim_63
```

Total: ~80 features vs los pocos actuales. El PINN debe re-entrenarse o, mínimamente, evaluar mediante ablación qué features aportan.

### 5.3 Tabla BigQuery `pendientes_detalladas`

Aprovechar este reemplazo para finalmente implementar la tabla pendiente (mencionada en memoria como pendiente con schema de 22 campos). Schema sugerido enriquecido:

```sql
CREATE TABLE clima.pendientes_detalladas (
  zona STRING,
  fecha_calculo TIMESTAMP,
  -- EAWS bins (existentes)
  pct_pendiente_lt30 FLOAT64,
  pct_pendiente_30_35 FLOAT64,
  pct_pendiente_35_45 FLOAT64,
  pct_pendiente_45_60 FLOAT64,
  pct_pendiente_gt60 FLOAT64,
  -- Orientaciones
  pct_norte FLOAT64, pct_este FLOAT64, pct_sur FLOAT64, pct_oeste FLOAT64,
  -- Histograma cada 5°
  histograma_5deg JSON,
  -- Indices compuestos
  indice_riesgo_topografico FLOAT64,
  -- NUEVOS - TAGEE
  curvatura_horizontal_promedio FLOAT64,
  curvatura_vertical_promedio FLOAT64,
  zonas_convergencia_runout INT64,
  -- NUEVOS - AlphaEarth
  embedding_centroide_zona ARRAY<FLOAT64>,  -- 64 dim
  similitud_anios_previos JSON,  -- detección de cambios
  -- Metadata
  dem_fuente STRING DEFAULT 'COPERNICUS/DEM/GLO30',
  resolucion_m INT64 DEFAULT 30
);
```

---

## 6. Tareas técnicas

### Fase A: DEM upgrade (4h)
- [ ] **A.1** Adaptar scripts GEE para usar `ee.ImageCollection("COPERNICUS/DEM/GLO30")` en lugar de NASADEM
- [ ] **A.2** Validar que análisis existente de slope produce resultados comparables o mejores (no peores)
- [ ] **A.3** Aprovechar banda de error de GLO-30 para flagear celdas de baja confianza
- [ ] **A.4** Documentar diferencias en bbox La Parva: ¿GLO-30 captura mejor la geometría del cerro El Plomo?

### Fase B: TAGEE integration (5h)
- [ ] **B.1** Importar módulo TAGEE: `users/zecojls/TAGEE`
- [ ] **B.2** Wrapper `tagee_wrapper.py` con 13 atributos relevantes para EAWS
- [ ] **B.3** Para cada zona, calcular y persistir atributos en `pendientes_detalladas`
- [ ] **B.4** Validar que detector de zonas de runout (basado en curvatura horizontal positiva) coincide con polígonos conocidos en La Parva

### Fase C: AlphaEarth integration (6h)
- [ ] **C.1** Habilitar acceso a `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` (no requiere registro especial)
- [ ] **C.2** Loader `alphaearth_loader.py` con queries por bbox y año
- [ ] **C.3** Test: extraer embedding centroide para La Parva años 2020-2024, calcular similitud coseno → debe haber drift significativo si hay cambios reales (validar contra eventos conocidos: glaciar Olivares, retroceso de nieve permanente)
- [ ] **C.4** Notebook análisis: ¿qué dimensiones del AE correlacionan con eventos avalanchosos pasados? (si dataset histórico existe)

### Fase D: PINN feature engineering (4h)
- [ ] **D.1** `features.py` que ensambla feature stack ~80D
- [ ] **D.2** Decidir: ¿re-entrenar PINN con feature stack completo o agregar AE como features auxiliares manteniendo arquitectura?
- [ ] **D.3** Estudio de ablación: comparar PINN baseline vs +TAGEE vs +AE vs +ambos
- [ ] **D.4** Documentar resultados como apéndice de tesis

### Fase E: Inferencia Vertex AI (5h, opcional según ablación)
- [ ] **E.1** Solo si ablación justifica nueva arquitectura: serializar PINN entrenado
- [ ] **E.2** Crear endpoint Vertex AI en `us-central1` con NVIDIA H100/A100
- [ ] **E.3** Configurar `ee.Model.fromVertexAi()` con `payloadFormat='GRPC_TF_TENSORS'`, `inputTileSize=[144,144]`, overlap 8px
- [ ] **E.4** Test latencia y costo vs inferencia local

### Fase F: Migración y tests (4h)
- [ ] **F.1** Tests unitarios por módulo (DEM loader, AE loader, TAGEE wrapper)
- [ ] **F.2** Test integración end-to-end: zona → embeddings + atributos terreno + clasificación EAWS
- [ ] **F.3** Test regresión: para 3 fechas históricas, comparar output S1 antiguo vs S1 nuevo. Documentar diferencias.
- [ ] **F.4** Llenar tabla `pendientes_detalladas` para La Parva y Valle Nevado

### Fase G: Cleanup (2h)
- [ ] **G.1** Marcar archivos NASADEM-dependientes como deprecated
- [ ] **G.2** Actualizar skill `snow-alert-dev/F2` con nuevo flujo
- [ ] **G.3** Documentar en `log_claude.md`

---

## 7. Criterios de aceptación

- [ ] Tabla `pendientes_detalladas` poblada para La Parva y Valle Nevado con todos los campos
- [ ] PINN produce predicciones con feature stack expandido (testar con datos sintéticos validados)
- [ ] Tests pasando (target: +25 tests)
- [ ] Quota EE bajo control: cada ejecución S1 consume <5 EECU-hr (estimar antes de deadline 27 abril 2026)
- [ ] Documentación de ablación: tabla comparativa baseline vs nuevo feature stack
- [ ] Sin regresión en latencia: S1 completo en <5 minutos por zona

---

## 8. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|-----------|
| AE no aporta vs PINN baseline | Media | Bajo | Documentar como negative result; el upgrade DEM+TAGEE ya justifica el cambio |
| Quota EE excede 150 EECU-hr/mes (Community tier) | Media | Alto | Calcular consumo en notebook ANTES de migrar; considerar Contributor tier (1000 EECU-hr) si necesario |
| Costo Vertex AI endpoint impacta presupuesto | Media | Medio | Hacer fase E opcional; mantener inferencia local como default |
| GLO-30 no cubre completamente bbox Andes | Baja | Bajo | Verificar cobertura primero (es global, debería estar OK) |
| Re-entrenar PINN abre Pandora's box | Alta | Alto | Solo re-entrenar si ablación lo justifica claramente |

---

## 9. Referencias técnicas

- AlphaEarth dataset: `https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL`
- Tutoriales AE: `https://developers.google.com/earth-engine/tutorials/community/satellite-embedding-01-introduction` (5 partes)
- AlphaEarth paper DeepMind: `https://deepmind.google/blog/alphaearth-foundations-helps-map-our-planet-in-unprecedented-detail/`
- Copernicus GLO-30: `https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30`
- TAGEE: `https://github.com/zecojls/tagee`
- ee.Model.fromVertexAi: `https://developers.google.com/earth-engine/guides/ml_examples`
- Earth Engine quota deadline: `https://developers.google.com/earth-engine/help/transition_to_paid` (verificar tier antes 27 abril 2026)

---

## 10. Notas para Claude Code

- **Earth Engine quota:** ANTES de empezar fase B, ejecutar `ee.data.getAssetRoots()` y verificar tier actual + uso del mes en consola GCP. Si consumo proyectado supera Community tier, escalar a Contributor.
- **No modificar S5**: el output de S1 alimenta a S5 vía formatos existentes; no cambiar contratos de salida.
- **Preservar PINN actual**: incluso si la ablación justifica nueva arquitectura, preservar el modelo antiguo en `pinn/model_v1_legacy.py` para reproducibilidad académica.
- **Documentar ablación en tesis:** los resultados de la fase D son material directamente publicable.
- **Logging:** flujo F2 (desarrollo agente) + F3 (data pipeline) en skill `snow-alert-dev`.

# 05 — Cross-cutting: BigQuery `ST_REGIONSTATS` y optimizaciones transversales

**Subagentes afectados:** S1, S2, S3 (S4 y S5 indirectamente)
**Tipo de cambio:** Refactor incremental
**Prioridad:** Baja (optimización, no funcionalidad nueva)
**Estimación:** 8-12 horas

---

## 1. Objetivo

Aprovechar `ST_REGIONSTATS()` (GA en BigQuery 2025) para colapsar pipelines multi-paso EE → GCS → Python → BQ en queries SQL únicas. Esto:

- Reduce ~20-30% de boilerplate de pipeline
- Disminuye costo (menos exports a GCS)
- Permite que S5 consulte estadísticas zonales directamente vía SQL sin esperar a un job de S1/S2 previo
- Habilita el **BigQuery MCP server** (GA diciembre 2025) para que S5 acceda a `ST_*` functions sin glue code

---

## 2. Justificación

Con la arquitectura actual, S1/S2 generan rasters → exportan a GCS → Python re-procesa → escribe en BQ. Con `ST_REGIONSTATS`:

```sql
SELECT
  zona_nombre,
  ST_REGIONSTATS(geometry, 'ee://COPERNICUS/DEM/GLO30', 'DEM').mean AS elevacion_media,
  ST_REGIONSTATS(geometry, 'ee://COPERNICUS/DEM/GLO30', 'DEM').stddev AS elevacion_std,
  ST_REGIONSTATS(geometry, 'ee://GOOGLE/DYNAMICWORLD/V1', 'snow_and_ice').mean AS prob_nieve_media
FROM clima.zonas_objetivo
WHERE zona_nombre IN ('La Parva', 'Valle Nevado')
```

Una query, sin export, sin Python intermedio.

---

## 3. Estado actual

**A revisar en el repo:**

- `tools/tool_consultor_bigquery.py` (clase `ConsultorBigQuery` mencionada en memoria)
- Qualquier código que haga `Export.image.toDrive` o `Export.table.toBigQuery` que pueda ser reemplazado
- Tabla `clima.zonas_objetivo` o equivalente con polígonos de La Parva/Valle Nevado

---

## 4. Estado deseado

### 4.1 Identificar candidatos a refactor

Buscar patrones del tipo:

```python
# ANTES: 3 pasos
imagen = ee.Image(...)
task = ee.batch.Export.image.toCloudStorage(...)
# ... esperar task ...
df = pd.read_csv(gcs_path)
bq.load_table_from_dataframe(df, "clima.tabla_x")
```

Reemplazables por:

```sql
-- DESPUÉS: 1 query
INSERT INTO clima.tabla_x
SELECT
  ST_REGIONSTATS(geom, 'ee://...', 'banda').mean AS valor,
  CURRENT_TIMESTAMP() AS computed_at
FROM clima.zonas_objetivo
```

### 4.2 BigQuery MCP server para S5 (opcional, fase futura)

Una vez que las consultas `ST_*` estén funcionando, exponer BQ Geo functions como tools al integrador EAWS. **NO modificar el LLM de S5 (Qwen3-80B)** — solo agregar tools que pueda invocar.

---

## 5. Tareas técnicas

### Fase A: Inventario (2h)
- [ ] **A.1** Listar todos los exports EE → GCS → BQ en el repo
- [ ] **A.2** Para cada uno, evaluar si `ST_REGIONSTATS` aplica (raster + polígono + agregación)
- [ ] **A.3** Priorizar por frecuencia de uso

### Fase B: Refactor incremental (5h)
- [ ] **B.1** Refactorizar primer candidato (el más simple) como prueba de concepto
- [ ] **B.2** Validar resultado idéntico al pipeline anterior
- [ ] **B.3** Refactorizar 2-3 candidatos más
- [ ] **B.4** Actualizar `ConsultorBigQuery` con métodos helper para `ST_REGIONSTATS`

### Fase C: Tabla `zonas_objetivo` (2h)
- [ ] **C.1** Si no existe, crear tabla con polígonos La Parva/Valle Nevado en formato `GEOGRAPHY`
- [ ] **C.2** Centralizar todas las definiciones geográficas aquí (eliminar bbox hardcodeados)

### Fase D: Tests (3h)
- [ ] **D.1** Tests de paridad: pipeline antiguo vs nuevo, verificar valores equivalentes ±0.1%
- [ ] **D.2** Test de costo: medir EECU consumido y dólares

---

## 6. Criterios de aceptación

- [ ] Al menos 3 pipelines refactorizados a `ST_REGIONSTATS`
- [ ] Tabla `zonas_objetivo` consolidada
- [ ] Reducción ≥20% en líneas de código de los pipelines refactorizados
- [ ] Sin regresión funcional
- [ ] Tests pasando

---

## 7. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|-----------|
| Costo BQ-EE diferente al esperado | Media | Bajo | Empezar con 1 pipeline pequeño; medir antes de migrar masivamente |
| Diferencias numéricas vs pipeline original | Media | Medio | Tests de paridad obligatorios antes de promover |
| `ST_REGIONSTATS` con asset privado requiere permisos extra | Baja | Bajo | Usar solo assets públicos en primera iteración |

---

## 8. Referencias técnicas

- `ST_REGIONSTATS` docs: `https://cloud.google.com/bigquery/docs/reference/standard-sql/geography_functions#st_regionstats`
- BigQuery EE integration blog: `https://cloud.google.com/blog/products/data-analytics/earth-engine-raster-analytics-and-visualization-in-bigquery-geospatial`
- BQ MCP server: `https://cloud.google.com/bigquery/docs/mcp-server`

---

## 9. Notas para Claude Code

- Esta es **optimización**, no funcionalidad nueva. NO bloquear los requerimientos 01-04 esperando esto.
- Hacer en background, idealmente cuando S1/S2/S3 ya estén estables con sus nuevos features.
- **No tocar S5**: el integrador EAWS sigue usando Qwen3-80B vía Databricks. Si en el futuro se quiere exponer BQ MCP a S5, será otro requerimiento aparte.

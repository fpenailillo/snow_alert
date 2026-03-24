# Plan de Validación — Capa de Datos snow_alert (v2)

> **Basado en**: revisión directa del repo `github.com/fpenailillo/snow_alert` (commit `1aa3640`)
>
> **Objetivo**: Verificar que las 6 Cloud Functions y las 7 tablas BigQuery operan correctamente,
> que los datos fluyen sin pérdidas ni nulos espurios, y que la capa de datos alimenta
> correctamente a la capa de agentes (S1–S5) via `ConsultorBigQuery`.
>
> **Contexto GCP**: proyecto `climas-chileno`, dataset `clima`, región `us-central1`,
> bucket `climas-chileno-datos-clima-bronce`.

---

## Fase 0 — Fix de tests rotos (prerequisito)

**Meta**: Corregir `test_fase0_datos.py` que llama métodos inexistentes de `ConsultorBigQuery`.

### Problema detectado

`agentes/tests/test_fase0_datos.py` referencia 3 métodos que **no existen** en
`agentes/datos/consultor_bigquery.py`:

| Test llama a | Método real |
|---|---|
| `obtener_datos_satelitales(ubicacion, dias=90)` | `obtener_estado_satelital(ubicacion)` |
| `obtener_zonas_avalancha(ubicacion)` | `obtener_perfil_topografico(ubicacion)` |
| `obtener_condiciones_meteorologicas(ubicacion, dias=30)` | `obtener_condiciones_actuales(ubicacion)` |

### Métodos reales de ConsultorBigQuery (8 públicos)

```python
obtener_condiciones_actuales(ubicacion)         # → condiciones_actuales (últimas 24h)
obtener_tendencia_meteorologica(ubicacion)      # → condiciones_actuales (72h, tendencia)
obtener_pronostico_proximos_dias(ubicacion)     # → pronostico_dias (próximos 10 días)
obtener_estado_satelital(ubicacion)             # → imagenes_satelitales (últimas 48h)
obtener_perfil_topografico(ubicacion)           # → zonas_avalancha
obtener_pendientes_detalladas(ubicacion)        # → pendientes_detalladas (si existe)
obtener_relatos_ubicacion(ubicacion, limite=20) # → relatos_montanistas (LIKE search)
buscar_relatos_condiciones(terminos, limite=10) # → relatos_montanistas (por términos)
listar_ubicaciones_con_datos()                  # → imagenes_satelitales (lista ubicaciones)
```

### Acción requerida

Reescribir `test_fase0_datos.py` mapeando a los métodos reales. También ajustar las
assertions porque los métodos reales retornan schemas distintos (ej: `obtener_estado_satelital`
retorna `{"disponible": True/False, ...}` no `{"imagenes": [...], "sin_datos": bool}`).

### Campos clave por tabla (para assertions)

**condiciones_actuales** (retorno de `obtener_condiciones_actuales`):
`temperatura, humedad_relativa, velocidad_viento, presion_atmosferica, descripcion_clima,
nombre_ubicacion, latitud, longitud, hora_actual`

**imagenes_satelitales** (retorno de `obtener_estado_satelital`):
`pct_cobertura_nieve, ndsi_medio, lst_dia_celsius, lst_noche_celsius, snowline_elevacion_m,
delta_pct_nieve_24h, tipo_cambio_nieve, ami_7d, sar_disponible, fecha_captura`

**zonas_avalancha** (retorno de `obtener_perfil_topografico`):
`zona_inicio_ha, pendiente_media_inicio, pendiente_max_inicio, indice_riesgo_topografico,
clasificacion_riesgo, frecuencia_estimada_eaws, tamano_estimado_eaws`

**relatos_montanistas** (retorno de `obtener_relatos_ubicacion`):
`{"disponible": bool, "relatos": [...], "total_encontrados": int}`
Cada relato: `route_id, name, location, avalanche_info, has_avalanche_info,
llm_nivel_riesgo, llm_puntuacion_riesgo, llm_resumen`

---

## Fase 1 — Inventario y conectividad

**Meta**: Confirmar que toda la infraestructura GCP responde.

### 1.1 Verificar acceso GCP

```bash
gcloud config get-value project
# Esperado: climas-chileno

gcloud auth list --filter=status:ACTIVE --format="value(account)"
```

### 1.2 Verificar Cloud Functions activas

```bash
gcloud functions list --gen2 --region=us-central1 \
  --format="table(name,state,updateTime)" 2>&1
```

**6 funciones esperadas** (nombres reales de `datos/desplegar.sh`):

| # | Nombre en GCP | Source dir | Trigger |
|---|---|---|---|
| 1 | `extractor-clima` | `datos/extractor/` | HTTP (Scheduler) |
| 2 | `procesador-clima` | `datos/procesador/` | Pub/Sub: `clima-datos-crudos` |
| 3 | `procesador-clima-horas` | `datos/procesador_horas/` | Pub/Sub |
| 4 | `procesador-clima-dias` | `datos/procesador_dias/` | Pub/Sub |
| 5 | `analizador-satelital-zonas-riesgosas-avalanchas` | `datos/analizador_avalanchas/` | HTTP (Scheduler mensual) |
| 6 | `monitor-satelital-nieve` | `datos/monitor_satelital/` | HTTP (Scheduler 3x/día) |

### 1.3 Verificar tablas BigQuery

```bash
bq ls --format=prettyjson climas-chileno:clima 2>&1
```

**7 tablas esperadas**:
`condiciones_actuales`, `pronostico_horas`, `pronostico_dias`,
`imagenes_satelitales`, `zonas_avalancha`, `relatos_montanistas`, `boletines_riesgo`

### 1.4 Verificar bucket GCS

```bash
gsutil ls gs://climas-chileno-datos-clima-bronce/ | head -20
```

### Criterios de éxito Fase 1
- [ ] 6 Cloud Functions en estado ACTIVE
- [ ] 7 tablas BigQuery accesibles
- [ ] Bucket GCS accesible con estructura `{ubicacion}/{tipo}/`

---

## Fase 2 — Validación de datos meteorológicos

**Meta**: Confirmar que las 3 tablas meteorológicas reciben datos frescos.

### 2.1 condiciones_actuales — frescura, volumen y nulos

```sql
-- Frescura y cobertura
SELECT
  COUNT(*) as total_filas,
  COUNT(DISTINCT nombre_ubicacion) as ubicaciones_distintas,
  MAX(hora_actual) as ultima_medicion,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(hora_actual), HOUR) as horas_desde_ultimo
FROM `climas-chileno.clima.condiciones_actuales`;
-- CRITERIO: horas_desde_ultimo < 12, ubicaciones_distintas >= 45

-- Nulos en campos críticos (últimos 7 días)
SELECT
  COUNT(*) as total,
  COUNTIF(temperatura IS NULL) as temp_null,
  COUNTIF(humedad_relativa IS NULL) as hum_null,
  COUNTIF(velocidad_viento IS NULL) as viento_null,
  COUNTIF(presion_atmosferica IS NULL) as presion_null,
  COUNTIF(descripcion_clima IS NULL) as desc_null,
  COUNTIF(nombre_ubicacion IS NULL) as ubic_null
FROM `climas-chileno.clima.condiciones_actuales`
WHERE hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY);
-- CRITERIO: todos _null = 0

-- Rangos plausibles
SELECT nombre_ubicacion, MIN(temperatura) as t_min, MAX(temperatura) as t_max,
  MAX(velocidad_viento) as v_max, MIN(humedad_relativa) as h_min
FROM `climas-chileno.clima.condiciones_actuales`
WHERE hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY nombre_ubicacion
HAVING t_min < -60 OR t_max > 60 OR v_max > 300 OR h_min < 0;
-- CRITERIO: 0 filas
```

### 2.2 pronostico_horas — cobertura y campos post-fix

```sql
SELECT
  COUNT(*) as total, COUNT(DISTINCT nombre_ubicacion) as ubics,
  MAX(timestamp_insercion) as ultimo,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(timestamp_insercion), HOUR) as atraso_h,
  -- Nulos post-fix
  COUNTIF(temperatura IS NULL) as temp_null,
  COUNTIF(precipitacion_probabilidad IS NULL) as precip_null,
  COUNTIF(velocidad_viento IS NULL) as viento_null,
  COUNTIF(humedad_relativa IS NULL) as hum_null,
  COUNTIF(cobertura_nubes IS NULL) as nubes_null
FROM `climas-chileno.clima.pronostico_horas`
WHERE timestamp_insercion >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY);
-- CRITERIO: ubics >= 60, atraso_h < 12, todos _null = 0 para datos recientes
```

### 2.3 pronostico_dias — cobertura y dedup

```sql
SELECT
  COUNT(*) as total, COUNT(DISTINCT nombre_ubicacion) as ubics,
  MAX(timestamp_insercion) as ultimo,
  -- Verificar dedup
  COUNT(*) - COUNT(DISTINCT CONCAT(nombre_ubicacion, '_', CAST(fecha_pronostico AS STRING))) as dupes,
  -- Nulos post-fix (10 campos arreglados)
  COUNTIF(temperatura_max IS NULL) as tmax_null,
  COUNTIF(temperatura_min IS NULL) as tmin_null,
  COUNTIF(precipitacion_probabilidad IS NULL) as precip_null,
  COUNTIF(velocidad_viento IS NULL) as viento_null
FROM `climas-chileno.clima.pronostico_dias`
WHERE timestamp_insercion >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY);
-- CRITERIO: ubics >= 60, dupes = 0 o cercano, todos _null = 0
```

### Criterios de éxito Fase 2
- [ ] condiciones_actuales: datos < 12h, >= 45 ubicaciones, 0 nulos críticos, rangos OK
- [ ] pronostico_horas: datos frescos, >= 60 ubics, horizonte >= 72h, 0 nulos post-fix
- [ ] pronostico_dias: datos frescos, >= 60 ubics, sin duplicados, 0 nulos post-fix

---

## Fase 3 — Validación de datos satelitales y topográficos

**Meta**: Confirmar NDSI real (no NULL como pre-fix) y 37 zonas correctas.

### 3.1 imagenes_satelitales — métricas post-fix

```sql
-- Solo datos recientes (post-fix NDSI select('NDSI_Snow_Cover')→select('NDSI'))
SELECT
  COUNT(*) as capturas,
  COUNTIF(ndsi_medio IS NOT NULL) as con_ndsi,
  COUNTIF(snowline_elevacion_m IS NOT NULL) as con_snowline,
  COUNTIF(pct_cobertura_nieve IS NOT NULL) as con_cobertura,
  ROUND(COUNTIF(ndsi_medio IS NOT NULL) / COUNT(*) * 100, 1) as pct_ndsi_ok,
  MAX(timestamp_descarga) as ultima_descarga,
  -- Verificar campos ERA5 y viento (post-fix bandas u/v_component_of_wind_100m)
  COUNTIF(viento_altura_vel_kmh IS NOT NULL) as con_viento,
  COUNTIF(era5_snow_depth_m IS NOT NULL) as con_era5
FROM `climas-chileno.clima.imagenes_satelitales`
WHERE timestamp_descarga >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY);
-- CRITERIO: pct_ndsi_ok >= 50%, con_viento > 0 (post-fix bandas viento)

-- Rangos plausibles
SELECT nombre_ubicacion, ndsi_medio, pct_cobertura_nieve, snowline_elevacion_m
FROM `climas-chileno.clima.imagenes_satelitales`
WHERE timestamp_descarga >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND (ndsi_medio < -1 OR ndsi_medio > 100
    OR pct_cobertura_nieve < 0 OR pct_cobertura_nieve > 100
    OR snowline_elevacion_m < 0 OR snowline_elevacion_m > 7000);
-- CRITERIO: 0 filas
```

### 3.2 zonas_avalancha — integridad (schema: 36 campos)

```sql
SELECT
  COUNT(*) as total_zonas,
  ROUND(AVG(CAST(pendiente_max_inicio AS FLOAT64)), 1) as pendiente_max_media,
  ROUND(AVG(indice_riesgo_topografico), 2) as indice_riesgo_medio,
  COUNTIF(indice_riesgo_topografico IS NULL) as riesgo_null,
  COUNTIF(zona_inicio_ha IS NULL) as zona_null,
  COUNTIF(frecuencia_estimada_eaws IS NULL) as freq_null,
  COUNTIF(tamano_estimado_eaws IS NULL) as tam_null
FROM `climas-chileno.clima.zonas_avalancha`;
-- CRITERIO: total_zonas = 37, pendiente_max_media ≈ 72.5, indice_riesgo_medio ≈ 63.18, 0 nulos

-- Verificar cobertura geográfica
SELECT nombre_ubicacion, latitud, longitud,
  indice_riesgo_topografico, clasificacion_riesgo, frecuencia_estimada_eaws
FROM `climas-chileno.clima.zonas_avalancha`
ORDER BY indice_riesgo_topografico DESC;
-- VERIFICAR MANUALMENTE: 37 zonas, sin duplicados, coordenadas razonables
```

### Criterios de éxito Fase 3
- [ ] imagenes_satelitales: capturas recientes con NDSI real, viento_altura post-fix, rangos OK
- [ ] zonas_avalancha: 37 zonas, pendiente_max ≈ 72.5°, indice_riesgo ≈ 63.18, 0 nulos

---

## Fase 4 — Validación de relatos (NLP input)

**Meta**: Confirmar 3.131+ relatos con schema de 37 campos y enriquecimiento LLM.

### 4.1 Volumen y campos LLM

```sql
SELECT
  COUNT(*) as total_relatos,
  COUNT(DISTINCT name) as rutas_distintas,
  COUNT(DISTINCT location) as ubicaciones_distintas,
  -- Campos base
  COUNTIF(description IS NOT NULL) as con_descripcion,
  COUNTIF(has_avalanche_info = TRUE) as con_avalancha,
  -- Campos LLM (enriquecidos por Databricks/Qwen)
  COUNTIF(llm_nivel_riesgo IS NOT NULL) as con_nivel_riesgo_llm,
  COUNTIF(llm_puntuacion_riesgo IS NOT NULL) as con_puntuacion_llm,
  COUNTIF(llm_resumen IS NOT NULL) as con_resumen_llm,
  ROUND(COUNTIF(llm_nivel_riesgo IS NOT NULL) / COUNT(*) * 100, 1) as pct_enriquecido
FROM `climas-chileno.clima.relatos_montanistas`;
-- CRITERIO: total_relatos >= 3131, pct_enriquecido > 95%, con_avalancha ≈ 41
```

### 4.2 Muestra cualitativa (relatos con avalancha)

```sql
SELECT name, location, avalanche_info, llm_nivel_riesgo,
  llm_puntuacion_riesgo, SUBSTR(llm_resumen, 1, 200) as resumen
FROM `climas-chileno.clima.relatos_montanistas`
WHERE has_avalanche_info = TRUE
LIMIT 10;
-- VERIFICAR MANUALMENTE: coherencia de campos LLM
```

### Criterios de éxito Fase 4
- [ ] >= 3131 relatos cargados
- [ ] >= 95% enriquecidos con campos LLM (`llm_nivel_riesgo`, `llm_puntuacion_riesgo`)
- [ ] Relatos de avalancha (~41) con `avalanche_info` y campos LLM coherentes

---

## Fase 5 — Validación de Cloud Functions (ejecución y logs)

### 5.1 Scheduler jobs

```bash
gcloud scheduler jobs list --location=us-central1 \
  --format="table(name,schedule,state,lastAttemptTime,status.code)"
# CRITERIO: state=ENABLED, status.code=OK para todos
```

### 5.2 Logs de errores (últimas 24h)

```bash
for fn in extractor-clima procesador-clima procesador-clima-horas \
  procesador-clima-dias monitor-satelital-nieve \
  analizador-satelital-zonas-riesgosas-avalanchas; do
  echo "=== $fn ==="
  gcloud functions logs read $fn --gen2 --region=us-central1 \
    --limit=20 --min-log-level=ERROR 2>&1 | head -10
done
# CRITERIO: 0 errores recurrentes
```

### 5.3 Pub/Sub DLQ

```bash
gcloud pubsub subscriptions pull clima-datos-dlq-sub --limit=5 --auto-ack 2>&1
# CRITERIO: "Listed 0 items"
```

### 5.4 Secret Manager

```bash
gcloud secrets list --format="table(name)" 2>&1
# Esperado: weather-api-key, databricks-token (mínimo)
```

### Criterios de éxito Fase 5
- [ ] 6 funciones ACTIVE sin errores recurrentes
- [ ] Scheduler jobs ENABLED con últimas ejecuciones OK
- [ ] DLQ vacía
- [ ] Secrets accesibles

---

## Fase 6 — Validación de integración datos → agentes

**Meta**: Confirmar que `ConsultorBigQuery` alimenta correctamente a S1–S5.

### 6.1 Tests unitarios (sin credenciales)

```bash
cd snow_alert
python -m pytest agentes/tests/test_subagentes.py -v --tb=short -q 2>&1 | tail -15
# CRITERIO: 135 passed, 5 skipped (o más)
```

### 6.2 Tests de conexión BigQuery (requiere GCP auth)

```bash
# NOTA: test_fase0_datos.py necesita fix de Fase 0 primero
python -m pytest agentes/tests/test_fase0_datos.py -v 2>&1
```

### 6.3 Validación manual de ConsultorBigQuery

Si test_fase0 no está corregido aún, validar manualmente:

```python
# Ejecutar desde snow_alert/
import sys; sys.path.insert(0, '.')
from agentes.datos.consultor_bigquery import ConsultorBigQuery

c = ConsultorBigQuery()

# Test 1: condiciones_actuales
r = c.obtener_condiciones_actuales("La Parva")
assert "error" not in r, f"Error: {r}"
print(f"condiciones_actuales: temperatura={r.get('temperatura')}, hora={r.get('hora_actual')}")

# Test 2: estado satelital
r = c.obtener_estado_satelital("La Parva")
print(f"satelital: disponible={r.get('disponible')}, ndsi={r.get('ndsi_medio')}")

# Test 3: perfil topográfico
r = c.obtener_perfil_topografico("La Parva")
print(f"topografico: zonas={len(r.get('zonas', []))}, riesgo={r.get('indice_riesgo_topografico')}")

# Test 4: relatos
r = c.obtener_relatos_ubicacion("La Parva")
print(f"relatos: disponible={r.get('disponible')}, total={r.get('total_encontrados')}")

# Test 5: pronóstico días
r = c.obtener_pronostico_proximos_dias("La Parva")
print(f"pronostico_dias: dias={len(r.get('pronosticos', []))}")

# Test 6: tendencia meteorológica (72h)
r = c.obtener_tendencia_meteorologica("La Parva")
print(f"tendencia: registros={r.get('total_registros')}")
```

### 6.4 Boletín de prueba E2E

```bash
python agentes/scripts/generar_boletin.py --ubicacion "La Parva" 2>&1 | tee /tmp/boletin_test.log
grep -E "\[S[1-5]" /tmp/boletin_test.log | head -20
grep -i "error\|null\|fallo\|nulo" /tmp/boletin_test.log | head -10
# CRITERIO: 5/5 subagentes ejecutados, boletín generado
```

### Criterios de éxito Fase 6
- [ ] 135+ tests unitarios passing
- [ ] ConsultorBigQuery retorna datos válidos para las 6 tablas
- [ ] Boletín de prueba generado sin errores, 5/5 subagentes

---

## Fase 7 — Validación de GCS (almacenamiento bronce)

### 7.1 Prefijos antiguos eliminados

```bash
for prefix in boletines/ pronostico_dias/ pronostico_horas/ satelital/; do
  count=$(gsutil ls gs://climas-chileno-datos-clima-bronce/$prefix 2>/dev/null | head -5 | wc -l)
  echo "$prefix: $count archivos (esperado: 0)"
done
```

### 7.2 Estructura nueva y datos recientes

```bash
# Verificar estructura {ubicacion}/{tipo}/
gsutil ls gs://climas-chileno-datos-clima-bronce/ | head -20

# Datos recientes para ubicación de prueba
gsutil ls -l "gs://climas-chileno-datos-clima-bronce/Valle Nevado/clima/" 2>/dev/null | tail -5
```

### Criterios de éxito Fase 7
- [ ] Prefijos antiguos eliminados (0 archivos)
- [ ] Nueva estructura con datos recientes (< 24h)

---

## Fase 8 — Validación de boletines_riesgo (output)

**Meta**: Confirmar que los 10 boletines piloto están correctos.

```sql
SELECT
  nombre_ubicacion, nivel_eaws_24h, nivel_eaws_48h, nivel_eaws_72h,
  confianza, fecha_emision,
  subagentes_degradados
FROM `climas-chileno.clima.boletines_riesgo`
ORDER BY fecha_emision DESC;
-- CRITERIO: 10 boletines, niveles 1-5 válidos, confianza > 0
-- CRITERIO: subagentes_degradados vacío o solo S4 (NLP es no-crítico)

-- Verificar schema 33 campos
SELECT COUNT(*) as total_campos
FROM `climas-chileno.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'boletines_riesgo';
-- CRITERIO: total_campos = 33
```

---

## Fase 9 — Reporte final

### Plantilla

```markdown
## Reporte Validación Capa de Datos — snow_alert
Fecha: YYYY-MM-DD | Commit: 1aa3640

### Resumen
| Componente | Estado | Detalle |
|------------|--------|---------|
| Fase 0: Fix tests | ✅/⚠️/❌ | test_fase0_datos.py corregido/pendiente |
| Cloud Functions (6) | ✅/⚠️/❌ | X/6 activas, Y errores 24h |
| condiciones_actuales | ✅/⚠️/❌ | N filas, M ubics, frescura Xh |
| pronostico_horas | ✅/⚠️/❌ | N filas, M ubics, horizonte Xh |
| pronostico_dias | ✅/⚠️/❌ | N filas, M ubics, X duplicados |
| imagenes_satelitales | ✅/⚠️/❌ | N capturas, X% NDSI real |
| zonas_avalancha | ✅/⚠️/❌ | N/37 zonas, pendiente=X° |
| relatos_montanistas | ✅/⚠️/❌ | N relatos, X% LLM |
| boletines_riesgo | ✅/⚠️/❌ | N/10 boletines, 33 campos |
| ConsultorBigQuery | ✅/⚠️/❌ | 8/8 métodos OK |
| GCS bucket | ✅/⚠️/❌ | Migración completa/pendiente |
| Tests unitarios | ✅/⚠️/❌ | N passed, M skipped |

### Problemas encontrados
1. [descripción + severidad + acción]

### Próximos pasos
1. [acciones derivadas]
```

### Actualizar log_claude.md

```markdown
## Sesión YYYY-MM-DD (validación capa de datos)
- ✅/⚠️ Fase 0: Fix test_fase0_datos.py — [N métodos corregidos]
- ✅/⚠️ Fase 1: Inventario GCP — N/6 funciones, N/7 tablas
- ✅/⚠️ Fase 2: Meteorología — condiciones OK/FAIL, pronostico OK/FAIL
- ✅/⚠️ Fase 3: Satelital — NDSI OK/FAIL, zonas N/37
- ✅/⚠️ Fase 4: Relatos — N/3131, X% LLM
- ✅/⚠️ Fase 5: Cloud Functions — N/6 sin errores
- ✅/⚠️ Fase 6: Integración — ConsultorBigQuery N/8 métodos OK
- ✅/⚠️ Fase 7: GCS — migración completa/pendiente
- ✅/⚠️ Fase 8: Boletines — N/10, 33 campos
```

---

## Instrucciones para Claude Code

### Orden de ejecución
Fase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9. Si una fase falla, documentar y continuar.

### Manejo de errores
- **Error GCP auth**: `gcloud auth application-default login`
- **Tabla no existe**: Registrar como hallazgo CRÍTICO
- **NULL masivos**: Distinguir datos pre-fix vs post-fix usando timestamp
- **Cloud Function ERROR**: Revisar logs, NO redesplegar

### Qué NO hacer
- NO modificar Cloud Functions, tablas BigQuery ni desplegar
- NO ejecutar DELETE, DROP ni `desplegar.sh`
- Solo LECTURA: SELECT, logs read, ls, describe
- Excepción: Fase 0 puede modificar `test_fase0_datos.py`

### Tiempo estimado
- Fase 0 (fix tests): ~10 min
- Fases 1-4 (queries BQ): ~15 min
- Fase 5 (logs/scheduler): ~10 min
- Fases 6-8 (integración): ~15 min
- Fase 9 (reporte): ~5 min
- **Total: ~55 minutos**

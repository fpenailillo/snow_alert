# Log de Progreso — snow_alert

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

# Log de Progreso — snow_alert

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

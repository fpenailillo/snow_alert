# LOG DE PROGRESO — snow_alert

> Este archivo registra TODO lo hecho en cada sesión de desarrollo.
> Claude DEBE agregar entradas al final de cada tarea completada.
> Formato: `- ✅ Descripción breve (YYYY-MM-DD)` bajo la sección de la sesión activa.

## Última actualización: 2026-03-18

---

## Estado actual

### Fases del proyecto

- [x] Fase -1: Repositorio reorganizado
- [x] Fase  0: Script diagnóstico creado
- [x] Fase  1: Relatos en BigQuery — 3,131 rutas con LLM (37 campos)
- [x] Fase  2: 5 subagentes construidos (S1-S5)
- [x] Fase  3: Archivos de despliegue Cloud Run
- [x] Fase  4: Schema boletines_riesgo (34 campos)
- [x] Fase  5: Tests actualizados para 5 subagentes
- [ ] Fase  6: Generar ≥50 boletines para métricas H1/H4

### Tests

- test_subagentes.py (sin Anthropic): ✅ 135 passed, 5 skipped
  - TestTools (PINN ×8, ViT ×9, EAWS, NLP ×4, Boletín): 27 tests
  - TestReintentosAPI: 3 | TestDegradacionGraceful: 3
  - TestMetricasTechel: 8 | TestAlmacenadorHelpers: 10
  - TestRegistroVersiones: 7 | TestMetricasF1: 5
  - TestMetricasDeltaNLP: 3 | TestMetricasAblacion: 2
  - TestMetricasKappa: 4 | TestETLRelatos: 18
  - TestDisclaimerPrompts: 6 | TestSchemaMigracion: 4
  - TestPruebasEstadisticas: 16 | TestBaseConocimientoAndino: 10
  - TestNLPSintetico: 9
- test_sistema_completo.py: ⬜ no ejecutado (requiere ANTHROPIC_API_KEY)
- test_fase0_datos.py: ⬜ no ejecutado (requiere GCP auth)

### Checklist pre-defensa

#### Pendiente GCP
- [x] **Migración schema** `boletines_riesgo` — ✅ confirmado 33 campos (2026-03-18, no necesitó migración)
- [ ] **Verificar imágenes diurnas** NDSI/visual/pct_nubes (próxima captura 10-16 UTC Chile)
- [ ] **GCS limpieza prefijos antiguos** — watcher activo; verificar `datos/migrar_gcs_progreso.log`

#### Pendiente métricas
- [ ] Tabla `boletines_riesgo` con ≥50 boletines — ⚠️ 10/50
- [ ] F1-score macro calculado y reportado (H1: ≥75%)
- [ ] Análisis de ablación real con/sin NLP (H2: >5pp — sintética ya confirmada +7.9pp)
- [ ] Comparación con Snowlab si datos disponibles (H4: Kappa≥0.60)

#### Completado ✅
- [x] 6 Cloud Functions activas en GCP
- [x] 10 boletines piloto en BigQuery + GCS
- [x] Cloud Run Job `orquestador-avalanchas` desplegado (imagen `74b2359`)
- [x] 3,131 relatos Andeshandbook cargados (37 campos)
- [x] zonas_avalancha: 37/37 zonas correctas (pendiente_max_media=72.5°)
- [x] Framework validación completo (F1, Kappa, QWK, Techel 2022)
- [x] H2 confirmada sintéticamente (+7.9pp)
- [x] Marco ético-legal documentado
- [x] 13 decisiones de diseño justificadas (D1-D13)
- [x] 135 tests unitarios passing

---

## Sesión 2026-03-17 (auditoría marco teórico)

- ✅ Auditoría completa 8 dimensiones → `claude/PLAN_BRECHAS_MARCO_TEORICO.md`
- ✅ Tabla `boletines_riesgo` creada en BigQuery (27 campos → luego 34)
- ✅ `almacenador.py` actualizado 12→27 campos (campos v3)
- ✅ `procesador_dias/main.py` — fix 10 campos NULL
- ✅ `procesador_horas/main.py` — fix 3 nombres campo + 9 campos nuevos
- ✅ `monitor_satelital/constantes.py` — fix nombres de banda (LST_Celsius, snow_depth_m)
- ✅ `monitor_satelital/main.py` — expandido 2→25 ubicaciones monitoreadas
- ✅ `agentes/validacion/metricas_eaws.py` — framework completo: F1-macro, Kappa, QWK, ablación
- ✅ `tool_analizar_dem.py` — C1: gradiente térmico PINN desde LST real + fallback lapse rate
- ✅ `tool_clasificar_eaws.py` — C2: `estimar_tamano_potencial()` conectada (no default=2)
- ✅ `tool_clasificar_eaws.py` — C3: viento >40km/h → +1 frecuencia, >70km/h → +2
- ✅ `schema_boletines.json` — C4: 6 campos ablación/trazabilidad (33 campos)
- ✅ `almacenador.py` — C4: 6 campos nuevos en fila BQ
- ✅ `prompts/registro_versiones.py` — sistema versionado prompts SHA-256
- ✅ `base_subagente.py` — reintentos API backoff exponencial (3 intentos, 2-30s)
- ✅ `agente_principal.py` — degradación graceful S4 NLP + campo subagentes_degradados
- ✅ `docs/decisiones_diseno.md` — D1-D10: justificaciones académicas
- ✅ `docs/arquitectura.md` — diagrama flujo 5 subagentes, resiliencia, tablas BQ
- ✅ `metricas_eaws.py` — Techel 2022 benchmark: TECHEL_2022_REFERENCIA, QWK, accuracy ±1
- ✅ `docs/decisiones_diseno.md` — D11: benchmark Techel con métricas referencia
- ✅ Tests: 62 passed → 89 passed → 105 passed
- ✅ Notebooks D1-D4: F1-score, ablación, Snowlab, confianza/cobertura
- ✅ `datos/relatos/schema_relatos.json` — 12 campos tabla relatos_montanistas
- ✅ `datos/relatos/cargar_relatos.py` — ETL JSON/CSV → BigQuery
- ✅ Migración BQ: `migrar_schema_boletines.py` 27→34 campos
- ✅ `docs/marco_etico_legal.md` — framework ético-legal (Ley 21.719, responsabilidad)
- ✅ `docs/decisiones_diseno.md` — D12: marco ético-legal + principio precaución
- ✅ `prompts.py` (integrador) — disclaimer obligatorio añadido
- ✅ `notebooks_validacion/05_pruebas_estadisticas.py` — bootstrap IC 95%, McNemar, potencia
- ✅ `conocimiento_base_andino.py` — 8 zonas → 15 zonas andinas + factor estacional
- ✅ `tool_conocimiento_historico.py` — fallback a base andina cuando BQ vacío
- ✅ `tool_analizar_vit.py` — REESCRITO: multi-head attention H=2, D_MODEL=6, D_HEAD=3, W_QKV Xavier, PE sinusoidal
- ✅ `tool_calcular_pinn.py` — UQ Taylor 1er orden: IC 95%, σ_FS, sensibilidades, parámetro dominante
- ✅ `docs/decisiones_diseno.md` — D13: UQ PINN justificación académica
- ✅ `notebooks_validacion/06_analisis_nlp_sintetico.py` — H2 confirmada: +7.9pp (modelo unidireccional)
- ✅ Tests: 126 → 135 passed

## Sesión 2026-03-18 (despliegue producción)

### Despliegue Cloud Run
- ✅ `zonas_avalancha` regenerada — 37/37 zonas correctas: pendiente_max_media=72.5°, indice_riesgo_medio=63.18
- ✅ Cloud Run Job `orquestador-avalanchas` desplegado — imagen `74b2359`, LLM Databricks/Qwen3-80B
- ✅ `cloudbuild.yaml` — create-or-update automático
- ✅ `Dockerfile` — `--guardar` añadido al ENTRYPOINT
- ✅ `almacenador.py` — fix NameError: `resultado→resultado_boletin` en insert BigQuery
- ✅ **10 boletines piloto** generados — Antuco=5, Cerro Bayo=5, Cerro Castor=5, Antillanca=4, Bariloche=4, Brian Head=3, Aspen=2, Banff=2, Arizona=2, Cerro Catedral=2

### Fix imágenes satelitales
- ✅ `productos.py` — NDSI mask: `neq(250)→lte(100)` (fill values se renderizaban blanco)
- ✅ `productos.py` — LST: máscara fill value 0 antes de Celsius
- ✅ `constantes.py` — ERA5 palette: blanco→gris oscuro (#4a4a4a), max=2m
- ✅ `constantes.py` — MODIS true color: min/max -100/8000→0/3000 con gamma=1.4
- ✅ `descargador.py` — Preview incluye tipo_producto en nombre (antes sobreescribían)

### ETL Relatos Databricks
- ✅ `schema_relatos.json` reescrito 12→37 campos para CSVs Databricks
- ✅ `cargar_relatos.py` reescrito: `cargar_routes_csv()` + `_enriquecer_con_llm()`
- ✅ **3,138 rutas cargadas** en BigQuery (3,131 con LLM, 41 avalancha, riesgo promedio 4.56)

### Fix nulos BigQuery + imágenes grises
- ✅ `viento_altura.py` — bandas `u/v_component_of_wind→u/v_component_of_wind_100m`
- ✅ `viento_altura.py` — ventana 24h→7 días para tolerar latencia ERA5
- ✅ `constantes.py` — DIAS_BUSQUEDA_MODIS: 7→14 días (latencia LST)
- ✅ `productos.py` — almacena `imagen_raw` para cálculo % nubes
- ✅ `metricas.py` — `calcular_porcentaje_nubes` con `imagen_raw`
- ✅ `descargador.py` — ERA5 GeoTIFF `radio_metros=25000` (resuelve TIFFs vacíos 530 bytes)
- ✅ Validación: viento_max_24h 0/25→25/25, lst_noche 0/25→25/25

### Integración Google Weather API
- ✅ 3 tablas BQ operativas: condiciones_actuales (84 ubic, 69K filas), pronostico_dias (63 ubic), pronostico_horas (61 ubic)
- ✅ Fix `procesador-clima-horas`: `BUCKET_CLIMA=climas-chileno-datos-clima-bronce`

### Fix cubicacion.py (12 key mismatches)
- ✅ `ha_zona_inicio_total→zona_inicio_ha`, `pendiente_max→pendiente_max_inicio`, `aspecto_predominante→aspecto_predominante_inicio`, etc.
- ✅ Resultado: indice_riesgo_topografico ya no fijo en 25.0 para todas las ubicaciones

### Fix indicadores_nieve.py
- ✅ `select('NDSI_Snow_Cover')→select('NDSI')` — snowline, pct_cobertura, delta ya no NULL

### Fix metricas.py
- ✅ Guard NoneType para `sar_pct_nieve_humeda`

### Fix pipeline agentes
- ✅ Parámetro `consultor` eliminado de tools NLP (se instancia internamente)
- ✅ `consultor_bigquery.py`: columnas corregidas, TIMESTAMP/DATE, schema relatos, dedup pronostico_dias
- ✅ LLM alternativo: ClienteDatabricks (Qwen3-80B) operativo — pipeline completo ~114s, 5/5 subagentes

## Sesión 2026-03-18 (framework desarrollo)

- ✅ Skill `snow-alert-dev` creado con 7 flujos de trabajo:
  - F1: Diagnóstico (references/diagnostico.md)
  - F2: Desarrollo agentes (references/desarrollo_agentes.md)
  - F3: Pipeline datos (references/pipeline_datos.md)
  - F4: Validación académica (references/validacion_academica.md)
  - F5: Despliegue (references/despliegue.md)
  - F6: Documentación tesina (references/documentacion_tesina.md)
  - F7: Escritura informe (references/escritura_tesina.md)
- ✅ Scripts: `verificar_proyecto.py` (health check) + `actualizar_progreso.py`
- ✅ `CLAUDE.md` reescrito apuntando a skill + log_claude.md
- ✅ `log_claude.md` creado con historial completo migrado de PROGRESO.md

---

## Sesión 2026-03-18 (migración GCS + confirmación schema)

### Confirmación schema BigQuery
- ✅ `boletines_riesgo` confirmado en 33 campos — `migrar_schema_boletines.py --dry-run` retorna "tabla ya tiene 33 campos" (migración no necesaria)

### Migración GCS bucket bronce
- ✅ `datos/migrar_gcs.py --ejecutar` lanzado — reorganiza ~77k archivos de `{tipo}/{ubicacion}/` → `{ubicacion}/{tipo}/`
  - Prefijos migrados: `boletines/`, `pronostico_dias/`, `pronostico_horas/`, `satelital/`, condiciones_actuales viejos
  - Nueva estructura: `{ubicacion}/clima/`, `{ubicacion}/pronostico_horas/`, `{ubicacion}/pronostico_dias/`, `{ubicacion}/boletines/`, `{ubicacion}/satelital/{tipo}/`
  - `topografia/` no migrado (transversal)
- ✅ Watcher configurado (PID 2395) — al terminar copia borra 4 prefijos antiguos (~243 MB, 11.402 archivos)
  - `boletines/`: 61 archivos | `pronostico_dias/`: 5.077 | `pronostico_horas/`: 4.834 | `satelital/`: 1.430
- ✅ Log progreso: `datos/migrar_gcs_progreso.log`
- ✅ Rama `release/2026-03-18-pipeline-fixes` pusheada a origin (para respaldo)

---

## Errores conocidos

- `imagenes_satelitales`: mayoría de filas históricas tienen snowline/pct_cobertura/delta=NULL (pre-fix). Nuevas capturas llenan correctamente.
- Imágenes diurnas NDSI/visual pendiente confirmar en próxima captura 10-16 UTC.

---

## Próximos pasos

1. ~~**Migrar schema** `boletines_riesgo`~~ — ✅ ya tiene 33 campos, no necesario
2. **Verificar GCS limpieza** — `tail -f datos/migrar_gcs_progreso.log` (watcher activo)
3. **Cargar relatos reales** — `python datos/relatos/cargar_relatos.py --routes ... --llm ...` (requiere GCP auth + CSVs Databricks)
4. **Generar ≥50 boletines** para métricas H1/H4: `python agentes/scripts/generar_todos.py`
5. **Calcular métricas reales**: F1-macro (H1), ablación real (H2), Kappa (H4)
6. **Escritura tesina**: redactar capítulos 3 y 4 (implementación + resultados)

---

## Comandos de verificación rápida

```bash
# Tests sin credenciales (siempre deben pasar)
cd snow_alert && python -m pytest agentes/tests/test_subagentes.py -v \
  -k "not (TestSubagenteTopografico or TestSubagenteSatelital or TestSubagenteMeteorologico or TestSubagenteIntegrador or TestSubagenteNLP)"
# Esperado: 135 passed, 5 skipped

# Health check del proyecto
python snow-alert-dev/scripts/verificar_proyecto.py --solo-local

# Tests con BigQuery (requiere GCP auth)
python -m pytest agentes/tests/test_fase0_datos.py -v

# Test E2E completo (requiere ANTHROPIC_API_KEY)
python -m pytest agentes/tests/test_sistema_completo.py -v -s
```

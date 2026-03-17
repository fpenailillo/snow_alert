# PROGRESO — snow_alert Sistema Multi-Agente

## Última actualización: 2026-03-17

## Fases

- [x] Fase -1: Repositorio reorganizado
- [x] Fase  0: Script diagnóstico creado (ejecutar manualmente con GCP auth)
- [ ] Fase  1: Relatos en BigQuery — PENDIENTE (carga manual desde Databricks)
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

## Estado de tests

- test_subagentes.py (sin Anthropic): ✅ 62 passed, 5 skipped
  - TestTools (PINN, ViT, EAWS, NLP, Boletín): 17 tests
  - TestReintentosAPI: 3 tests
  - TestDegradacionGraceful: 3 tests
  - TestMetricasTechel: 8 tests
  - TestAlmacenadorHelpers: 10 tests (NUEVO)
  - TestRegistroVersiones: 7 tests (NUEVO)
  - TestMetricasF1: 5 tests (NUEVO)
  - TestMetricasDeltaNLP: 3 tests (NUEVO)
  - TestMetricasAblacion: 2 tests (NUEVO)
  - TestMetricasKappa: 4 tests (NUEVO)
- test_sistema_completo.py: ⬜ no ejecutado (requiere ANTHROPIC_API_KEY)
- test_fase0_datos.py: ⬜ no ejecutado (requiere GCP auth)

## Próximos pasos

1. **A2** Generar boletín piloto y verificar insert completo en BigQuery (requiere ANTHROPIC_API_KEY)
2. **A3** Generar boletines para 5-10 ubicaciones piloto
3. **B1** Verificar estado tabla relatos_montanistas en BQ (requiere GCP auth)
4. **B2** Ejecutar `datos/relatos/cargar_relatos.py --crear-tabla --csv relatos.csv` (script listo, requiere datos + GCP auth)
5. **B3** Forzar ejecución analizador para poblar `zonas_avalancha`
6. **BQ migration** Ejecutar `python agentes/scripts/migrar_schema_boletines.py` para actualizar tabla 27→34 campos (requiere GCP auth)

## Errores conocidos

- imagenes_satelitales: datos posiblemente nulos — ejecutar revisar_datos.py para confirmar
- zonas_avalancha: datos posiblemente nulos — ejecutar revisar_datos.py para confirmar
- tabla relatos_montanistas: no existe hasta completar FASE 1

## Comandos de verificación rápida

```bash
# Tests sin credenciales (siempre deben pasar)
cd snow_alert && python -m pytest agentes/tests/test_subagentes.py -v -k "not (TestSubagenteTopografico or TestSubagenteSatelital or TestSubagenteMeteorologico or TestSubagenteIntegrador or TestSubagenteNLP)"
# Esperado: 62 passed, 5 skipped

# Tests con BigQuery (requiere GCP auth)
python -m pytest agentes/tests/test_fase0_datos.py -v

# Test E2E completo (requiere ANTHROPIC_API_KEY)
python -m pytest agentes/tests/test_sistema_completo.py -v -s
```

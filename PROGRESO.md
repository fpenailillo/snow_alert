# PROGRESO — snow_alert Sistema Multi-Agente

## Última actualización: 2026-03-16

## Fases

- [x] Fase -1: Repositorio reorganizado
- [ ] Fase  0: Datos nulos resueltos — PENDIENTE (script diagnóstico creado, ejecutar manualmente)
- [ ] Fase  1: Relatos en BigQuery — PENDIENTE (carga manual desde Databricks)
- [ ] Fase  2: Agentes construidos (5 subagentes)
- [ ] Fase  3: Cloud Run desplegado
- [ ] Fase  4: Schema boletines_riesgo (27 campos)
- [ ] Fase  5: Tests actualizados (5 subagentes)

## Estado de tests

- test_subagentes.py (tools sin Anthropic): ✅ 12 passed, 4 skipped
- test_sistema_completo.py: ⬜ no ejecutado aún (requiere credenciales)
- test_fase0_datos.py: ❌ no creado aún

## Archivos creados/modificados en Fase -1

- datos/ — creado, contiene todos los módulos Cloud Function
- relatos/ — creado con README.md y .gitkeep
- databricks/ — creado con 5 notebooks placeholder
- docs/ — creado con arquitectura.md y guia_despliegue.md
- .gitignore — actualizado
- README.md — reescrito
- CLAUDE.md — reescrito
- agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py — fix sys.path para datos/

## Archivos creados en Fase 0

- agentes/diagnostico/__init__.py ⬜ pendiente
- agentes/diagnostico/revisar_datos.py ⬜ pendiente

## Próximo paso exacto

Crear agentes/diagnostico/revisar_datos.py (FASE 0)
Luego crear SubagenteNLP (FASE 2)

## Errores conocidos

- imagenes_satelitales: datos posiblemente nulos — ejecutar revisar_datos.py
- zonas_avalancha: datos posiblemente nulos — ejecutar revisar_datos.py

## Notas para la próxima sesión

1. Ejecutar: python agentes/diagnostico/revisar_datos.py (requiere GCP auth)
2. Si hay nulos, forzar Cloud Functions: gcloud functions call monitor-satelital-nieve --gen2
3. Luego construir SubagenteNLP

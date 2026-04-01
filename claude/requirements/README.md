# Requerimientos: Integración Google Earth AI 2025-2026 en AndesAI

**Generado:** 2026-04-25
**Contexto:** Modernización de subagentes S1-S4 con stack Google Earth AI (AlphaEarth, WeatherNext 2, Gemini 2.5, Earth AI RSFM). S5 (Integrador EAWS) se mantiene sin cambios usando Qwen3-80B vía Databricks.

---

## Decisiones de diseño

| Subagente | Estrategia | Razón |
|-----------|-----------|-------|
| **S1 — Topográfico** | **Reemplazo** | AlphaEarth + Copernicus GLO-30 + TAGEE superan PINN actual con menos código |
| **S2 — Satelital** | **Paralelo (A/B)** | ViT actual funciona; agregar RSFM/Gemini para comparar antes de decidir |
| **S3 — Meteorológico** | **Aditivo** | WeatherNext 2 como fuente complementaria; Open-Meteo/ERA5 siguen activos |
| **S4 — NLP** | **Reemplazo** | Cambio de paradigma: ya no scraping+sentiment, sino situational briefing |
| **S5 — Integrador EAWS** | **Sin cambios** | Qwen3-80B vía Databricks (gratuito) sigue siendo óptimo |

---

## Orden de ejecución sugerido

Ordenado por **dependencias técnicas** y **riesgo bajo → alto**:

1. **`01-s4-situational-briefing.md`** — Reemplazo S4 (independiente, valor inmediato)
2. **`02-s3-weathernext-aditivo.md`** — WeatherNext 2 como fuente paralela en S3
3. **`03-s1-alphaearth-pinn.md`** — Reemplazo S1 con AlphaEarth + GLO-30 + TAGEE
4. **`04-s2-rsfm-paralelo.md`** — RSFM/Gemini en S2 corriendo en paralelo al ViT actual
5. **`05-cross-cutting-bigquery-st.md`** — Optimizaciones transversales (BigQuery `ST_REGIONSTATS`)

---

## Restricciones globales

- **Earth Engine quota deadline:** 27 abril 2026 — verificar tier (Community 150 EECU-hr/mes vs Contributor 1000 con billing).
- **GCP project:** `climas-chileno`
- **Region:** `us-central1` (requerido para `ee.Model.fromVertexAi()`)
- **Zonas objetivo:** La Parva (-33.45,-70.45 → -33.25,-70.15) y Valle Nevado (similar bbox)
- **LLM producción:** Qwen3-80B vía Databricks (Secret Manager) — **NO modificar** en S5
- **Lenguaje bulletins:** español de Chile, formato EAWS
- **Validación final:** SLF Suiza (transfer learning) + Snowlab La Parva (operacional)

---

## Convenciones para Claude Code

Cada archivo de requerimiento sigue esta estructura:

1. **Objetivo** — Una frase clara
2. **Estado actual** — Qué existe en el repo hoy
3. **Estado deseado** — Qué debe existir al terminar
4. **Tareas técnicas** — Pasos accionables ordenados
5. **Criterios de aceptación** — Tests que deben pasar
6. **Riesgos y mitigaciones**
7. **Referencias técnicas** — Links a documentación
8. **Estimación** — Horas de desarrollo

Al consumir cada archivo, registrar progreso en `claude/log_claude.md` siguiendo el flujo F2 (desarrollo de agente) o F3 (pipeline de datos) de la skill `snow-alert-dev`.

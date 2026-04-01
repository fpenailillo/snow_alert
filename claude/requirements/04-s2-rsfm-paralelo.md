# 04 — S2: RSFM + Gemini 2.5 multi-spectral en paralelo al ViT actual

**Subagente:** S2 — Satelital
**Tipo de cambio:** Implementación paralela (A/B testing)
**Prioridad:** Media (validar antes de reemplazar)
**Estimación:** 20-28 horas

---

## 1. Objetivo

Implementar una **segunda vía de procesamiento satelital en S2** usando los modelos foundation Earth AI de Google, **sin retirar** el Vision Transformer actual. El objetivo es comparar A/B durante la temporada de invierno 2026 antes de decidir si reemplazar.

Las dos vías corren en paralelo y producen outputs comparables. Un comparador externo evalúa cuál tiene mejor performance contra ground truth (avalanchas verificadas, observaciones Snowlab).

---

## 2. Justificación del enfoque paralelo

- El ViT actual ya funciona y está en producción. Reemplazarlo a ciegas es riesgoso.
- Los modelos Earth AI RSFM están en **Trusted Tester** — acceso requiere aplicación, no es completamente reproducible aún.
- La comparación A/B en una temporada real (julio-septiembre 2026) genera **datos publicables** para la tesis.
- Si Earth AI no llega a aprobarse a tiempo, Gemini 2.5 con razonamiento multi-spectral nativo (paper arxiv 2509.19087) es alternativa GA inmediata.

---

## 3. Estado actual

**A revisar en el repo (Claude Code debe inspeccionar):**

- `subagents/s2_*` (estructura del agente satelital)
- ViT actual: arquitectura, weights, training scripts
- Tabla `clima.satellite_imagery` (deployed, devuelve null según memoria — investigar por qué antes de extender)
- Conectores: GOES-18/16, MODIS, VIIRS, Sentinel-2, ERA5-Land

**Tarea preliminar crítica:** investigar por qué `satellite_imagery` retorna null. Posiblemente esquema mal alineado, queries fallidas o backfill incompleto. Resolver ANTES de agregar segunda vía.

---

## 4. Estado deseado

### 4.1 Arquitectura dual

```
subagents/s2_satelital/
├── via_actual_vit/                # PRESERVAR sin cambios
│   ├── vit_model.py
│   ├── inference.py
│   └── ...
├── via_earth_ai/                  # NUEVA - paralela
│   ├── rsfm_client.py             # Cliente RSFM (cuando Trusted Tester aprobado)
│   ├── gemini_multispectral.py    # Fallback/complemento con Gemini 2.5
│   └── inference.py
├── comparador/
│   ├── ab_runner.py               # Ejecuta ambas vías sobre mismo input
│   ├── metricas.py                # IoU, F1, latencia, costo
│   └── persist_comparacion.py     # Guarda resultados en BQ para análisis
├── consolidador.py                # Decide qué output usar para S5
└── tests/
```

### 4.2 Flag de feature

```bash
S2_VIA="vit_actual"         # Default - usa solo ViT
S2_VIA="earth_ai"            # Solo nueva vía
S2_VIA="ambas_consolidar_vit" # Ambas, output ViT alimenta S5 (comparación)
S2_VIA="ambas_consolidar_ea"  # Ambas, output Earth AI alimenta S5
```

### 4.3 Tareas que ambas vías deben resolver

Outputs comparables (mismo schema):

```python
class DeteccionSatelital(BaseModel):
    via: Literal["vit_actual", "rsfm", "gemini_multispectral"]
    zona: str
    timestamp: datetime
    fuente_imagen: str  # "S2", "MODIS", "GOES-19", ...
    # Detecciones
    cobertura_nieve_pct: float
    nieve_humeda_pct: float | None         # Solo S2 con SAR
    nieve_seca_pct: float | None
    detecciones_avalancha: list[dict]      # GeoJSON polígonos
    cornisas_detectadas: list[dict] | None  # Solo Earth AI VLM
    wind_slabs_detectados: list[dict] | None
    # Confianza
    confianza_global: float
    flags_calidad: list[str]
```

### 4.4 Modelos a integrar (vía Earth AI)

#### Opción A — Earth AI RSFM (preferida si llega Trusted Tester)
- Vision Language Model: queries en lenguaje natural ("debris flows on snow-covered slopes")
- RS-OWL-ViT-v2: detección zero-shot de objetos
- ViT backbone: clasificación/segmentación 0.1-10m
- Acceso: formulario `forms.gle/1DPfcuys2AU63HgZ8`

#### Opción B — Gemini 2.5 multi-spectral (fallback GA)
- Endpoint: `gemini-2.5-pro` en Vertex AI
- Capacidades documentadas en arxiv 2509.19087: +0.041 F1 en BigEarthNet-43
- Limitación documentada: 43% errores de percepción en tareas diagramáticas → **NO usar para máscaras pixel-precisas**
- Uso recomendado: razonamiento cualitativo cross-source (combinar GOES + MODIS + S2 con narrativa textual)

#### Opción C — Mejoras GA inmediatas (sin esperar Earth AI)
Agregar como mejora baseline aunque vía Earth AI no aterrice:
- **GOES-19** (`NOAA/GOES/19/MCMIPF`) sustituyendo GOES-18 — operacional desde 7 abril 2025, mejor geometría sobre Andes
- **Sentinel-1 ILS mask** (`Earth_Big_Data/GLOBAL_SEASONAL_S1/V2019/INCIDENCE_LAYOVER_SHADOW`) — esencial para Andes 30-60°
- **Sentinel-1C** operacional desde 26 marzo 2025 — restaura revisita de 6 días
- **Dynamic World V1** (`GOOGLE/DYNAMICWORLD/V1`) banda `snow_and_ice` como signal zero-effort

### 4.5 Resolución del bug `satellite_imagery` null

Antes de cualquier extensión, debugging:

```python
# Hipótesis a verificar
1. Schema mismatch entre escritura y lectura
2. Backfill no ejecutado completo
3. Filtros temporales/espaciales eliminan todos los registros
4. Permisos IAM en service account
5. Particionamiento mal configurado
```

---

## 5. Tareas técnicas

### Fase A: Bugfix `satellite_imagery` (4h) — BLOQUEANTE
- [ ] **A.1** Inspeccionar tabla en BQ: ¿registros físicos? ¿partitions correctas?
- [ ] **A.2** Logs de Cloud Run del último ciclo S2 — ¿errores de escritura?
- [ ] **A.3** Reproducir query que devuelve null, identificar causa
- [ ] **A.4** Fix + backfill mínimo (últimos 7 días)
- [ ] **A.5** Test que valida tabla devuelve datos

### Fase B: Mejoras GA inmediatas (5h)
- [ ] **B.1** Agregar GOES-19 al pool de fuentes ViT actual
- [ ] **B.2** Integrar Sentinel-1 ILS mask al pipeline de wet snow detection
- [ ] **B.3** Agregar Dynamic World snow band como sanity check
- [ ] **B.4** Validar Sentinel-1C disponible y agregarlo

### Fase C: Vía Earth AI (8h)
- [ ] **C.1** Aplicar a Trusted Tester de Earth AI (formulario)
- [ ] **C.2** Implementar `gemini_multispectral.py` (no requiere aprobación, GA)
- [ ] **C.3** Diseñar prompts para detección cualitativa: "describe avalanche risk indicators visible in this multi-band image"
- [ ] **C.4** **Si y solo si** Trusted Tester aprueba: implementar `rsfm_client.py`
- [ ] **C.5** Output adapter al schema `DeteccionSatelital`

### Fase D: Comparador A/B (5h)
- [ ] **D.1** `ab_runner.py`: ejecuta ambas vías sobre mismo set de imágenes
- [ ] **D.2** Métricas: IoU, F1, latencia, costo, tasa de detección de eventos verificados
- [ ] **D.3** Tabla BQ `s2_comparaciones` con resultados por timestamp
- [ ] **D.4** Dashboard simple (notebook o Looker Studio) con curvas comparativas

### Fase E: Tests y despliegue (4h)
- [ ] **E.1** Tests por vía + tests del comparador
- [ ] **E.2** Test regresión: con `S2_VIA=vit_actual`, comportamiento es idéntico al actual
- [ ] **E.3** Desplegar con flag `vit_actual` por defecto
- [ ] **E.4** Activar modo `ambas_consolidar_vit` para temporada 2026 → recolectar datos

### Fase F: Análisis post-temporada (2h)
- [ ] **F.1** Análisis estadístico de comparación A/B
- [ ] **F.2** Decisión documentada: ¿reemplazar, mantener dual, descartar Earth AI?
- [ ] **F.3** Capítulo de tesis con resultados

---

## 6. Criterios de aceptación

- [ ] **Bloqueante resuelto:** tabla `satellite_imagery` devuelve datos válidos
- [ ] Mejoras GA (GOES-19, S1 ILS, S1C, DW snow) integradas
- [ ] Vía Gemini multi-spectral funcional incluso si RSFM no aprobado
- [ ] Comparador A/B persiste métricas en BQ
- [ ] Sin regresión: con `S2_VIA=vit_actual`, comportamiento idéntico
- [ ] Tests pasando (target: +30 tests)
- [ ] Documentación de la decisión arquitectónica final

---

## 7. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|-----------|
| Trusted Tester RSFM no aprobado a tiempo | Media | Medio | Gemini 2.5 multi-spectral + mejoras GA cubren mucho del valor |
| Gemini 2.5 alucina detecciones | Media | Alto | NO usar para máscaras pixel; solo razonamiento cualitativo + flags |
| Latencia comparativa hace S2 lento | Alta | Medio | Ejecutar ambas vías async en paralelo, no secuencial |
| Costo Vertex AI Gemini explota | Media | Medio | Quotas + alertas; cache responses por imagen |
| Bug `satellite_imagery` más profundo de lo esperado | Media | Alto | Fase A es bloqueante; si toma >8h, escalar antes de continuar |

---

## 8. Referencias técnicas

- Earth AI overview: `https://research.google/blog/google-earth-ai-unlocking-geospatial-insights-with-foundation-models-and-cross-modal-reasoning/`
- Earth AI paper: `arxiv.org/abs/2510.18318`
- Gemini multi-spectral paper: `arxiv.org/abs/2509.19087`
- Trusted Tester form Earth AI: `forms.gle/1DPfcuys2AU63HgZ8`
- Sentinel-1 ILS mask: `developers.google.com/earth-engine/datasets/catalog/Earth_Big_Data_GLOBAL_SEASONAL_S1_V2019_INCIDENCE_LAYOVER_SHADOW`
- GOES-19 dataset: `developers.google.com/earth-engine/datasets/catalog/NOAA_GOES_19_MCMIPF`
- Dynamic World V1: `developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1`

---

## 9. Notas para Claude Code

- **Bloqueante:** Fase A (bugfix `satellite_imagery`) DEBE resolverse antes que cualquier otra cosa.
- **Preservar ViT actual:** ningún cambio en `via_actual_vit/` excepto adapters al schema común.
- **No comprometer S5:** mientras el flag esté en `vit_actual`, S5 recibe exactamente lo mismo que recibe hoy.
- **Datos para tesis:** la fase F (análisis post-temporada) puede ser un capítulo entero. Diseñar la persistencia con eso en mente: timestamps, hashes de input, semilla aleatoria si aplica.
- **Logging:** flujo F2 + F4 (validación académica) de skill `snow-alert-dev`.

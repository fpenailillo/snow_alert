# 02 — S3: WeatherNext 2 como fuente meteorológica complementaria

**Subagente:** S3 — Meteorológico
**Tipo de cambio:** Aditivo (sin romper Open-Meteo/ERA5 actual)
**Prioridad:** Alta (habilita mejoras en S4 y S5)
**Estimación:** 16-24 horas

---

## 1. Objetivo

Integrar **WeatherNext 2** (DeepMind, GA noviembre 2025) como fuente meteorológica adicional en S3, **manteniendo intactos** Open-Meteo y ERA5-Land actualmente operativos. WeatherNext 2 aporta:

- **64 miembros de ensemble** → cuantificación de incertidumbre nativa
- **Hasta 15 días de horizonte** (vs 10 actuales)
- **6.5% mejor CRPS** vs WeatherNext anterior
- **Inicialización 4× diaria** con resolución horaria (vía Vertex AI Model Garden)

La integración debe ser **estrictamente aditiva**: S3 sigue funcionando si WeatherNext 2 falla.

---

## 2. Justificación del cambio

- Las reglas EAWS de estabilidad dependen de **probabilidades** (frecuencia × tamaño × estabilidad), no solo valores deterministas. Un ensemble de 64 miembros es la fuente probabilística natural.
- El horizonte de 15 días permite alertas tempranas (más allá del foco actual de 24-72h).
- La paridad con Open-Meteo permite **validación cruzada** y detección de outliers entre modelos.

---

## 3. Estado actual

**A revisar en el repo (Claude Code debe inspeccionar):**

- `subagents/s3_*` o equivalente (agente meteorológico actual)
- Tabla `clima.weather_conditions` (~69k registros activos)
- Conectores actuales: `tools/tool_open_meteo.py`, `tools/tool_era5_*` (verificar nombres)
- Cron actual del orquestador (3 ejecuciones/día confirmadas en memoria)

---

## 4. Estado deseado

### 4.1 Nueva fuente, sin reemplazar las actuales

S3 expone tres fuentes complementarias accesibles vía un **patrón Strategy**:

```
subagents/s3_meteorologico/
├── fuentes/
│   ├── __init__.py
│   ├── base.py                    # Interfaz FuenteMeteorologica (abstract)
│   ├── fuente_open_meteo.py       # EXISTENTE - sin cambios
│   ├── fuente_era5_land.py        # EXISTENTE - sin cambios
│   └── fuente_weathernext2.py     # NUEVA
├── consolidador.py                # Lógica de fusión multi-fuente
└── ...
```

### 4.2 Acceso a WeatherNext 2

Tres opciones, recomendada en orden:

1. **BigQuery Analytics Hub** (recomendado para producción):
   - Suscripción gratuita, costo BQ estándar (~<$5/mes a escala tesis)
   - Path: `bigquery-public-data:weathernext_2.forecasts`
   - Ventaja: SQL nativo, integra con `ConsultorBigQuery` existente

2. **Earth Engine** (para análisis exploratorio):
   - `projects/gcp-public-data-weathernext/assets/weathernext_2_0_0`
   - Gratuito para investigación

3. **Vertex AI Model Garden** (Early Access):
   - Para inferencia custom con resolución horaria
   - Requiere aplicación a EAP — **no priorizar inicialmente**

### 4.3 Schema de salida unificado

Las tres fuentes deben mapearse a un schema común antes del consolidador:

```python
class PronosticoMeteorologico(BaseModel):
    fuente: Literal["open_meteo", "era5_land", "weathernext_2"]
    zona: str
    timestamp_init: datetime
    horizonte_h: int
    lat: float
    lon: float
    # Variables EAWS-críticas
    temperatura_2m_c: float
    precipitacion_mm: float
    viento_10m_kmh: float
    direccion_viento_deg: float
    humedad_pct: float
    # Solo WeatherNext 2 (None para otras fuentes)
    ensemble_id: int | None = None
    n_miembros_ensemble: int | None = None
    # Probabilísticos derivados
    p10_precipitacion: float | None = None
    p50_precipitacion: float | None = None
    p90_precipitacion: float | None = None
```

### 4.4 Consolidador multi-fuente

- **Por defecto:** Open-Meteo sigue siendo fuente primaria (NO romper lo que funciona)
- **WeatherNext 2:** se usa para enriquecer con percentiles y detectar divergencia
- **Flag de feature:** `USE_WEATHERNEXT2_AS_PRIMARY=false` por defecto en variables de entorno
- **Logging de divergencia:** si WN2 P50 difiere >3°C o >50% precip de Open-Meteo, log warning para análisis posterior

---

## 5. Caveats Chile-específicos (CRÍTICOS)

### 5.1 Resolución espacial

A 0.25° (~28×23 km en -33°), **La Parva y Valle Nevado caen en la misma celda**. WeatherNext 2 NO puede distinguir microclimas entre ambas zonas.

**Mitigación:**
- Documentar explícitamente esta limitación en docstrings y bulletin
- Aplicar **bias correction** contra estaciones AWS locales (CEAZAMet, DGA, Snowlab)
- Para diferenciación zonal, seguir dependiendo de Open-Meteo (que sí ofrece consultas por lat/lon precisas)

### 5.2 Variables ausentes

WeatherNext 2 **NO entrega** snow depth, SWE, ni nieve nueva en cm. Solo precipitación líquida-equivalente.

**Mitigación:**
- Las variables EAWS de snowpack siguen viniendo de modelo físico downstream (placeholder hasta implementar SNOWPACK/Crocus)
- Documentar en schema que `precipitacion_mm` es liquid-equivalent

### 5.3 Sesgos orográficos

Esperar:
- Sesgo cálido sistemático en altitudes de ski (orografía suavizada)
- Subestimación de precipitación orográfica en ladera windward chilena
- Subrepresentación de ráfagas en cumbres (señal crítica para wind slab)

**Mitigación:**
- Reservar para fase posterior un módulo `bias_correction.py` con quantile mapping vs AWS Snowlab La Parva
- Por ahora, registrar valores raw + flag `requires_local_correction=True`

---

## 6. Tareas técnicas

### Fase A: Suscripción y exploración (3h)
- [ ] **A.1** Llenar formulario WeatherNext Data Request (gratis)
- [ ] **A.2** Suscribirse a Analytics Hub `weathernext_2` en proyecto `climas-chileno`
- [ ] **A.3** Notebook exploratorio: extraer 1 día de datos para bbox La Parva, validar variables disponibles
- [ ] **A.4** Comparar valores extraídos vs Open-Meteo histórico para 1 semana — documentar magnitud del bias

### Fase B: Implementación fuente (5h)
- [ ] **B.1** Crear interfaz abstracta `FuenteMeteorologica` (si no existe) y refactorizar fuentes actuales para implementarla — **sin cambiar comportamiento**
- [ ] **B.2** Implementar `fuente_weathernext2.py` con métodos `obtener_pronostico(zona, horizonte_h)` y `obtener_ensemble(zona, horizonte_h)`
- [ ] **B.3** Helper SQL para queries BigQuery con cuantiles (P10/P50/P90) sobre miembros del ensemble
- [ ] **B.4** Cache local (Redis o BigQuery materializada) para evitar queries repetidas en mismo ciclo

### Fase C: Consolidador (4h)
- [ ] **C.1** Implementar `consolidador.py` con estrategias: `solo_open_meteo` (default), `enriquecido_con_wn2`, `wn2_primario` (futuro)
- [ ] **C.2** Lógica de fallback: si WN2 falla o devuelve null, log warning y devolver solo Open-Meteo
- [ ] **C.3** Generar nuevas columnas en tabla `weather_conditions`: `ensemble_p10_precip`, `ensemble_p50_precip`, `ensemble_p90_precip`, `fuente_enriquecimiento`

### Fase D: Tests (4h)
- [ ] **D.1** Tests unitarios para nueva fuente con respuestas BQ mockeadas
- [ ] **D.2** Test integración: ejecutar S3 con/sin WN2, verificar que sin WN2 sigue funcionando idéntico
- [ ] **D.3** Test de regresión: 5 días históricos donde S3 actual ya tenía resultados, verificar que con flag `USE_WEATHERNEXT2_AS_PRIMARY=false` los resultados son idénticos
- [ ] **D.4** Test de divergencia: simular WN2 con valores muy distintos a Open-Meteo, verificar que warning se emite

### Fase E: Integración y validación (4h)
- [ ] **E.1** Actualizar Cloud Run Job para que S3 lea el flag de feature
- [ ] **E.2** Ejecutar 1 semana en modo "shadow" (WN2 se consulta y persiste pero NO afecta bulletin)
- [ ] **E.3** Análisis comparativo: ¿WN2 predijo eventos que Open-Meteo perdió?
- [ ] **E.4** Documentar findings en `log_claude.md` y skill `snow-alert-dev`

---

## 7. Criterios de aceptación

- [ ] S3 sigue funcionando idéntico cuando `USE_WEATHERNEXT2_AS_PRIMARY=false` (default)
- [ ] Cuando flag está activo: ensemble percentiles se persisten en `weather_conditions`
- [ ] Tests pasando (target: +20 tests, 0 regresiones en los 135 actuales)
- [ ] Latencia S3 no aumenta más de 30% con WN2 activo
- [ ] Costo BigQuery WN2 <$10/mes a 3 ejecuciones diarias
- [ ] Documentación de caveats Chile-específicos visible en docstrings y README del subagente
- [ ] Al menos 1 semana de datos shadow recolectados antes de considerar habilitar como primario

---

## 8. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|-----------|
| Bias orográfico invalida pronósticos en altura | Alta | Alto | Mantener Open-Meteo como primario; bias correction como fase futura |
| Una sola celda 0.25° para ambas zonas | Cierto | Medio | Documentar; usar Open-Meteo para diferenciación zonal |
| BQ Analytics Hub costos inesperados | Baja | Bajo | Configurar quotas + alertas billing |
| Rompe S3 actual durante refactor | Media | Alto | Refactor a interface SIN cambiar lógica; tests de regresión obligatorios |
| WN2 EAP no llega a tiempo | Baja | Bajo | BigQuery Hub es suficiente para tesis |

---

## 9. Referencias técnicas

- WeatherNext 2 anuncio: `https://blog.google/technology/google-deepmind/weathernext-2/`
- BigQuery dataset: `https://developers.google.com/weathernext/guides/bigquery`
- Earth Engine asset: `projects/gcp-public-data-weathernext/assets/weathernext_2_0_0`
- Colab starter: `https://storage.googleapis.com/weathernext-public/colabs/WeatherNext_2_Starter_Guide_BigQuery.ipynb`
- Paper técnico (FGN): buscar en arxiv.org "WeatherNext 2 Functional Generative Network 2025"

---

## 10. Notas para Claude Code

- **NO ROMPER S3 actual:** este requerimiento es estrictamente aditivo. Cualquier cambio en `fuente_open_meteo.py` o `fuente_era5_land.py` debe ser **solo** para implementar la interfaz común, sin cambiar comportamiento observable.
- **Flag por defecto en false:** desplegar a producción con WN2 deshabilitado; activar manualmente solo después de la semana shadow.
- **No modificar S5:** los percentiles WN2 entran al bulletin vía S5 sin cambios en su LLM (Qwen3-80B).
- **Logging:** seguir flujo F3 (data pipeline) de skill `snow-alert-dev`.

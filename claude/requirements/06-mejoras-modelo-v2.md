# REQ-MEJORAS-MODELO-V2 — Plan integrado post-EDA

**Fecha:** 2026-05-02
**Basado en:** `RESULTADOS_VALIDACION.md` (Ronda 3 v4.0) + `EDA_VALIDACION.md` + Techel et al. 2025 Part B
**Branch sugerido:** `feat/mejoras-modelo-v2`
**Autor:** Francisco Peñailillo — UTFSM MTI 2024

---

## Diagnóstico consolidado

La validación Ronda 3 reveló dos problemas independientes:

1. **Piso nivel 3 en H4 (Snowlab):** S3 clasifica `FUSION_ACTIVA` con un umbral (`diurno_temp_max > 0°C` AND `nocturno_temp_min < −2°C`) que se cumple casi todos los días de verano andino, contaminando S5 con señal espuria de inestabilidad. Sesgo +1.79 niveles, MAE 1.94 sobre 90 pares Snowlab.

2. **Gap de dominio Andes→Alpes en H1/H3:** Sistema calibrado para Andes produce QWK 0.162 en Alpes (vs 0.59 Techel 2022). La regresión de sesgo en Ronda 3 (−0.92) es consecuencia directa de REQ-03 (corrección orográfica calibrada para Andes) aplicado en Alpes.

El EDA confirma además dos limitaciones de datos críticas:

- **Período satelital BQ ≠ período validación:** `imagenes_satelitales` cubre mar–may 2026, pero las fechas Snowlab son jun 2024–sep 2025. REQ-02 GEE no puede mejorar validación retroactiva — debe enfocarse en temporada operacional 2026.
- **Backfill meteorológico parcial:** `condiciones_actuales` cubre desde dic 2023 (77k filas), pero `pronostico_horas` solo desde mar 2026. La validación retroactiva usa pronóstico actual como aproximación de fechas históricas.

---

## Filosofía del plan

**Stack Google primero:** todas las mejoras se implementan extendiendo componentes ya desplegados (Cloud Functions, GEE, BigQuery, Pub/Sub) sin introducir nueva infraestructura.

**Causa raíz antes que síntomas:** REQ-06 (S3) primero, porque es la causa raíz confirmada del piso nivel 3. REQ-01 (persistencia) depende de que REQ-06 funcione.

**Validación retroactiva vs operacional separadas:** REQ-07 (backfill Open-Meteo histórico) habilita validación retroactiva limpia. REQ-02 GEE se reorienta a temporada 2026.

---

## REQ-06 — Refactor S3: distinguir ciclo diurno normal vs fusión con carga

**Prioridad:** 🔴 Máxima — causa raíz confirmada del piso nivel 3

**Componentes Google:** BigQuery (`clima.pronostico_dias`, `clima.imagenes_satelitales`)

### Problema

EDA sección 6.3 identifica el umbral exacto:

```python
# ACTUAL en agentes/subagentes/subagente_meteorologico/
if diurno_temp_max > 0 and nocturno_temp_min < -2:
    factor_meteorologico = "FUSION_ACTIVA"  # → empuja nivel a 3
```

En La Parva (33°S, 2200–4500m), esta condición se cumple ~95% de los días de junio-septiembre incluso sin precipitación reciente. El ciclo diurno es geográfico, no señal de inestabilidad.

Confirmación EDA sección 4.4: estado PINN dominante es `ESTABLE` cuando S5 emite nivel 3-4 → la causa no es S1, es el factor meteorológico.

### Solución

Diferenciar ciclo diurno normal (sin carga reciente) de fusión activa con manto cargado.

**Archivo:** `agentes/subagentes/subagente_meteorologico/tools/tool_analizar_meteorologia.py` (o equivalente — verificar nombre exacto)

```python
def clasificar_factor_meteorologico(
    diurno_temp_max: float,
    nocturno_temp_min: float,
    precipitacion_72h_mm: float,
    era5_swe_anomalia: float | None,
) -> str:
    """
    Clasifica el factor meteorológico EAWS dominante.

    REQ-06: distinguir CICLO_DIURNO_NORMAL de FUSION_ACTIVA_CON_CARGA.
    El ciclo diurno por sí solo no es indicador de inestabilidad en
    climas continentales como los Andes centrales.
    """
    # Ciclo térmico presente
    hay_ciclo_termico = diurno_temp_max > 0 and nocturno_temp_min < -2

    if not hay_ciclo_termico:
        if precipitacion_72h_mm >= 15:
            return "NEVADA_RECIENTE"
        return "ESTABLE"

    # Ciclo presente — evaluar si hay carga
    hay_carga_reciente = precipitacion_72h_mm >= 10
    hay_anomalia_swe = (
        era5_swe_anomalia is not None and era5_swe_anomalia > 0.2
    )

    if hay_carga_reciente or hay_anomalia_swe:
        return "FUSION_ACTIVA_CON_CARGA"  # sí indica riesgo

    return "CICLO_DIURNO_NORMAL"  # neutro al nivel EAWS
```

**Datos requeridos:**
- `precipitacion_72h_mm`: agregable desde `clima.pronostico_horas` o `clima.condiciones_actuales`
- `era5_swe_anomalia`: ya existe en `clima.imagenes_satelitales` — nuevo input al tool

### Cambio en S5 (integrador)

`CICLO_DIURNO_NORMAL` debe interpretarse como factor neutro, no contribuir al nivel EAWS. En el prompt de S5:

```
Factores meteorológicos y su contribución al nivel EAWS:
- ESTABLE: nivel base
- CICLO_DIURNO_NORMAL: NO contribuye al nivel — fenómeno geográfico esperable
- NEVADA_RECIENTE: contribuye +1 a +2 niveles según intensidad
- FUSION_ACTIVA_CON_CARGA: contribuye +1 a +2 según anomalía SWE
- PRECIPITACION_CRITICA: contribuye +2 a +3 niveles
```

### Tests

- `test_meteorologico.py`: dado `temp_max=5, temp_min=-3, precip_72h=0`, retorna `CICLO_DIURNO_NORMAL`.
- `test_meteorologico.py`: dado `temp_max=5, temp_min=-3, precip_72h=20`, retorna `FUSION_ACTIVA_CON_CARGA`.
- `test_e2e_calma.py`: simular 5 días de calma andina (sin precipitación, ciclo diurno normal) → S5 emite nivel ≤ 2.

### Criterio de éxito

| Métrica Snowlab | Actual | Objetivo REQ-06 |
|-----------------|--------|-----------------|
| Sesgo medio | +1.79 | ≤ +0.80 |
| MAE casos calma | 2.30 | ≤ 1.20 |
| MAE casos tormenta | 0.75 | mantener ≤ 1.0 |
| % predicciones nivel 1-2 | 11% | ≥ 30% |

**Esfuerzo estimado:** ~6h código + 2h tests + 1 corrida de validación retroactiva.

---

## REQ-07 — Backfill meteorológico Open-Meteo histórico

**Prioridad:** 🔴 Alta — habilita validación retroactiva con datos reales

**Componentes Google:** Cloud Functions (patrón existente), Cloud Scheduler, BigQuery, Pub/Sub

### Problema

EDA sección 9.4: la validación retroactiva usa `pronostico_horas` que solo cubre desde mar 2026, pero las fechas Snowlab son jun 2024–sep 2025. El sistema actualmente aproxima el estado meteorológico histórico con datos actuales, lo que invalida el reprocesamiento.

### Solución

Crear nueva Cloud Function `extractor_historico` siguiendo el patrón de `datos/extractor/`. Open-Meteo ofrece **Historical Weather API** gratuita con datos horarios desde 1940 con la misma granularidad que la API de pronóstico.

```
https://archive-api.open-meteo.com/v1/archive
  ?latitude=-33.354&longitude=-70.298
  &start_date=2024-06-15&end_date=2025-09-21
  &hourly=temperature_2m,precipitation,snowfall,wind_speed_10m,...
```

### Implementación

**Estructura:**

```
datos/extractor_historico/
├── main.py                  # Cloud Function trigger HTTP
├── requirements.txt
├── cloudbuild.yaml
└── desplegar.sh
```

**Tabla BigQuery destino:** Reutilizar `clima.condiciones_actuales` con nuevo campo `fuente='openmeteo_historical'` para distinguir registros backfill de los de tiempo real, o crear tabla específica `clima.condiciones_historicas` con schema idéntico.

**Modo de ejecución:**
- Trigger HTTP manual (no Scheduler) — backfill es operación one-shot.
- Cloud Function recibe `{ubicaciones: [...], fecha_inicio, fecha_fin}`.
- Procesa en chunks de 30 días para evitar timeout (max 540s en Cloud Functions Gen2).
- Publica a Pub/Sub `procesador-clima-horas` para reusar la pipeline existente.

**Ubicaciones objetivo del backfill (mínimo):**
- La Parva Sector Bajo, Medio, Alto (validación H4)
- Interlaken, Matterhorn Zermatt, St Moritz (validación H1/H3)
- Período: 2023-12-01 → 2025-09-21

### Tests

- Test unitario: parser de respuesta Open-Meteo → schema BigQuery.
- Test integración: backfill 1 día La Parva → fila aparece en BQ con `fuente='openmeteo_historical'`.
- Validación: re-correr `08_validacion_snowlab.py` con datos backfilled y confirmar que MAE en tormentas no se degrada (sigue ≤ 1.0).

### Criterio de éxito

- 100% de fechas Snowlab tienen datos meteorológicos reales en BQ (no aproximaciones).
- 100% de fechas SLF Suiza (n=24) tienen datos meteorológicos reales.
- `notebooks_validacion/reprocesar_retroactivo.py` puede ejecutarse usando solo datos BQ históricos.

**Esfuerzo estimado:** ~10h (Cloud Function + tests + ejecución backfill).

---

## REQ-01 — Persistencia temporal en S5 (revisado, condicionado a REQ-06)

**Prioridad:** 🟡 Media — depende de REQ-06

**Componentes Google:** BigQuery (`clima.boletines_riesgo`)

### Problema

S5 evalúa cada boletín de forma independiente. Sin memoria de días anteriores, no puede confirmar calma sostenida.

### Por qué depende de REQ-06

Sin REQ-06, S3 emite `FUSION_ACTIVA` casi todos los días → S5 emite nivel 3+ → la cadena de "días consecutivos con nivel ≤ 2" nunca se forma → REQ-01 nunca se activa. El reporte v4.0 confirma esto: REQ-01 está implementado pero bloqueado upstream.

### Solución

Agregar método `get_bulletin_history` a `agentes/datos/consultor_bigquery.py`:

```python
def get_bulletin_history(
    self,
    nombre_ubicacion: str,
    fecha_referencia: date,
    n_dias: int = 7,
) -> list[dict]:
    """Retorna los últimos n_dias boletines emitidos para la ubicación,
    excluyendo el de fecha_referencia."""
    query = """
    SELECT fecha_emision, nivel_eaws_24h, factor_meteorologico
    FROM `climas-chileno.clima.boletines_riesgo`
    WHERE nombre_ubicacion = @ubicacion
      AND DATE(fecha_emision) < @fecha_ref
      AND DATE(fecha_emision) >= DATE_SUB(@fecha_ref, INTERVAL @n DAY)
    ORDER BY fecha_emision DESC
    """
    # ...
```

Calcular features de persistencia y agregarlas al prompt de S5:

```python
features = {
    "dias_consecutivos_nivel_bajo": ...,  # cuenta consecutiva nivel ≤ 2
    "nivel_promedio_7d": ...,
    "tendencia": ...,                      # diff último vs 4 días atrás
    "calma_confirmada": dias_consecutivos_nivel_bajo >= 4,
}
```

### Cambio en S5

```
## Contexto histórico
- Días consecutivos con nivel ≤ 2: {dias_consecutivos_nivel_bajo}
- Nivel promedio últimos 7 días: {nivel_promedio_7d:.1f}
- Calma confirmada: {calma_confirmada}

Si calma_confirmada=True Y factor_meteorologico in [ESTABLE, CICLO_DIURNO_NORMAL],
limita el nivel emitido a máximo 2.
```

### Tests

- Test unitario: `get_bulletin_history` retorna lista vacía si no hay historial.
- Test integración: secuencia sintética de 5 días calmos → activación de `calma_confirmada=True`.
- Test regresión: secuencia con tormenta intermedia → `calma_confirmada=False` correctamente.

### Criterio de éxito

Reducir adicionalmente el sesgo H4 desde el residual post-REQ-06 (~+0.80) hasta ≤ +0.40.

**Esfuerzo estimado:** ~6h (después de REQ-06).

---

## REQ-02 (revisado) — GEE estado del manto para temporada operacional 2026

**Prioridad:** 🟢 Media — reorientado a uso operacional, no validación retroactiva

**Componentes Google:** Earth Engine (extender `datos/monitor_satelital/`), BigQuery, Cloud Scheduler

### Problema

El EDA confirma que GEE LST + SAR no pueden mejorar la validación retroactiva (datos en BQ son mar–may 2026, validación es 2024-2025). Pero estas señales son cruciales para la operación durante invierno 2026 — la temporada que define la Fase 3 de validación operacional.

### Solución

Extender `datos/monitor_satelital/main.py` (Cloud Function existente) para incluir tres nuevas extracciones GEE:

**REQ-02a — MODIS LST diurno/nocturno**
```python
lst = ee.ImageCollection('MODIS/061/MOD11A1') \
    .filterDate(fecha, fecha_siguiente) \
    .filterBounds(geometry) \
    .select(['LST_Day_1km', 'LST_Night_1km'])
```

**REQ-02b — Sentinel-1 SAR backscatter**
```python
s1 = ee.ImageCollection('COPERNICUS/S1_GRD') \
    .filterDate(fecha_menos_12, fecha) \
    .filterBounds(geometry) \
    .filter(ee.Filter.eq('instrumentMode', 'IW')) \
    .select('VV')
```

**REQ-02c — ERA5-Land soil temperature** (ya disponible vía GEE)
```python
era5 = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY') \
    .filterDate(fecha, fecha_siguiente) \
    .select(['soil_temperature_level_1', 'soil_temperature_level_2'])
```

### Esquema BigQuery

Crear tabla `clima.estado_manto_gee`:

```sql
CREATE TABLE `climas-chileno.clima.estado_manto_gee` (
  nombre_ubicacion STRING NOT NULL,
  fecha DATE NOT NULL,
  lst_dia_celsius FLOAT64,
  lst_noche_celsius FLOAT64,
  ciclo_amplitud FLOAT64,
  lst_dias_positivo_consecutivos INT64,
  sar_vv_db FLOAT64,
  sar_delta_baseline FLOAT64,
  sar_disponible BOOL,
  era5_temp_suelo_l1_celsius FLOAT64,
  era5_temp_suelo_l2_celsius FLOAT64,
  gradiente_termico_suelo FLOAT64,
  ingested_at TIMESTAMP,
  PRIMARY KEY (nombre_ubicacion, fecha) NOT ENFORCED
)
PARTITION BY fecha;
```

**Esfuerzo estimado:** ~12h (3 extracciones GEE + tests + despliegue).

---

## REQ-03 — Fix regional corrección orográfica

**Prioridad:** 🟡 Baja — fix puntual

La corrección orográfica ERA5 actual aplica factores Andes globalmente. En Alpes degrada (regresión sesgo −0.50 → −0.92 en Ronda 3). Solución:

```python
def factor_correccion_orografica(altitud_m: float, region: str) -> float:
    if region == "andes_chile":
        return _factor_andes(altitud_m)
    elif region == "alpes":
        return 1.0  # no aplicar — ERA5 ya capta orografía alpina
    return 1.0
```

`region` se deriva del campo `region_eaws` de `clima.zonas_objetivo`.

**Esfuerzo:** ~2h.

---

## REQ-04 y REQ-05 — Status

REQ-04 (mapeo SLF preciso) ya implementado en Ronda 3 — sin cambios requeridos.
REQ-05 (WeatherNext 2) sigue pendiente de activación cuando llegue suscripción Analytics Hub.

---

## Orden de ejecución consolidado

| Orden | REQ | Bloquea a | Esfuerzo | Impacto métrica |
|-------|-----|-----------|----------|-----------------|
| 1 | **REQ-06** (S3 ciclo diurno) | REQ-01 | 8h | Sesgo H4: +1.79 → +0.80 |
| 2 | **REQ-07** (backfill Open-Meteo) | Validación retroactiva limpia | 10h | Habilita métricas confiables |
| 3 | **REQ-01** (persistencia) | — | 6h | Sesgo H4: +0.80 → +0.40 |
| 4 | **REQ-03 fix regional** | — | 2h | Mejora marginal H1/H3 |
| 5 | **REQ-02 GEE** (operacional 2026) | Fase 3 validación | 12h | Habilita validación operacional |
| 6 | REQ-05 (WeatherNext 2) | — | 3h | Marginal |

**Total:** ~41h desarrollo + ejecución de backfill + re-validación.

---

## Criterio de éxito global de la iteración v5.0

| Métrica | Ronda 3 (v4.0) | Objetivo v5.0 |
|---------|---------------|---------------|
| QWK Snowlab | -0.006 | ≥ 0.30 |
| MAE Snowlab calma | 2.30 | ≤ 1.20 |
| MAE Snowlab tormenta | 0.75 | ≤ 1.00 |
| % predicciones nivel 1-2 La Parva | 11% | ≥ 35% |
| QWK SLF Suiza | 0.162 | ≥ 0.20 |

---

## Componentes que NO se tocan

- Cloud Run Job `orquestador-avalanchas` — sin cambios
- Pipeline de relatos NLP (`datos/relatos/` y S4) — H2 confirmada
- `clima.zonas_avalancha` — datos topográficos correctos
- Secret Manager (Databricks token) — sin cambios

---

*Referencias bibliográficas:*
- Techel, F., Müller, K., Marquardt, C., Mitterer, C. (2025). The EAWS matrix Part B. *EGUsphere* preprint, doi:10.5194/egusphere-2025-3349.
- Müller, K., Techel, F., Mitterer, C. (2025). The EAWS matrix Part A. *NHESS Discussions*.

*Branch: `feat/mejoras-modelo-v2`*

# REQ-validacion-datos — Plan de Obtención de Datos de Validación

**Proyecto GCP**: `climas-chileno`
**Dataset BQ validación**: `validacion_avalanchas`
**Storage GCS**: `gs://climas-chileno-datos-clima-bronce/validacion/`

---

## Dataset BigQuery: `validacion_avalanchas`

```sql
CREATE SCHEMA IF NOT EXISTS `climas-chileno.validacion_avalanchas`
OPTIONS (
  location = 'US',
  description = 'Datos de validación para sistema AndesAI de avalanchas'
);
```

---

## Tabla 1: `slf_meteo_snowpack` — DEAPSnow RF1/RF2

Fuente: EnviDat — https://www.envidat.ch/dataset/weather-snowpack-danger_ratings-data

```sql
CREATE TABLE IF NOT EXISTS `climas-chileno.validacion_avalanchas.slf_meteo_snowpack` (
  date DATE,
  station_id STRING,
  station_name STRING,
  region STRING,
  elevation_m INTEGER,
  aspect STRING,
  temp_max_c FLOAT64,
  temp_min_c FLOAT64,
  temp_mean_c FLOAT64,
  precip_mm FLOAT64,
  new_snow_cm FLOAT64,
  snow_depth_cm FLOAT64,
  wind_speed_ms FLOAT64,
  wind_direction_deg FLOAT64,
  relative_humidity_pct FLOAT64,
  wet_snow_flag INTEGER,
  danger_level_forecast INTEGER,
  danger_level_actual INTEGER,
  settlement_cm FLOAT64,
  hardness STRING,
  grain_type STRING,
  loaded_layer_flag INTEGER,
  dataset_split STRING  -- train/val/test
);
```

---

## Tabla 2: `slf_danger_levels_qc` — D_QC Re-analyzed

Fuente: EnviDat — https://www.envidat.ch/dataset/re-analysed-regional-avalanche-danger-levels-in-switzerland

```sql
CREATE TABLE IF NOT EXISTS `climas-chileno.validacion_avalanchas.slf_danger_levels_qc` (
  date DATE,
  region_id STRING,
  region_name STRING,
  danger_level_qc INTEGER,     -- nivel EAWS re-analizado 1-5
  danger_level_am INTEGER,     -- nivel AM (mañana)
  danger_level_pm INTEGER,     -- nivel PM (tarde)
  elevation_split_m INTEGER,
  danger_level_above INTEGER,
  danger_level_below INTEGER,
  forecast_issue_time TIMESTAMP,
  season STRING,
  source STRING
);
```

---

## Tabla 3: `slf_avalanchas_davos` — Registros individuales Davos

Fuente: EnviDat — https://www.envidat.ch/dataset/snow-avalanche-data-davos

```sql
CREATE TABLE IF NOT EXISTS `climas-chileno.validacion_avalanchas.slf_avalanchas_davos` (
  avalanche_id STRING,
  date DATE,
  location STRING,
  elevation_start_m INTEGER,
  elevation_stop_m INTEGER,
  aspect STRING,
  inclination_deg FLOAT64,
  avalanche_type STRING,   -- wet/dry/slush
  avalanche_size INTEGER,  -- EAWS 1-5
  length_m FLOAT64,
  width_m FLOAT64,
  area_m2 FLOAT64,
  trigger STRING,          -- natural/artificial
  fracture_type STRING,
  danger_level_day INTEGER,
  new_snow_24h_cm FLOAT64,
  snow_depth_cm FLOAT64,
  temp_c FLOAT64
);
```

---

## Tabla 4: `slf_actividad_diaria_davos` — Actividad diaria Davos

```sql
CREATE TABLE IF NOT EXISTS `climas-chileno.validacion_avalanchas.slf_actividad_diaria_davos` (
  date DATE,
  avalanche_count INTEGER,
  wet_count INTEGER,
  dry_count INTEGER,
  natural_count INTEGER,
  artificial_count INTEGER,
  max_size INTEGER,
  mean_size FLOAT64,
  danger_level INTEGER,
  new_snow_cm FLOAT64,
  temp_max_c FLOAT64,
  wind_speed_ms FLOAT64
);
```

---

## Tabla 5: `eaws_matrix_operacional` — Paper Techel 2025

Fuente: Techel et al. 2025 (doi:10.5194/egusphere-2025-3349), 26 servicios EAWS

```sql
CREATE TABLE IF NOT EXISTS `climas-chileno.validacion_avalanchas.eaws_matrix_operacional` (
  date DATE,
  country STRING,
  service_name STRING,
  region_id STRING,
  stability_eaws STRING,    -- very_poor, poor, fair, good
  frequency_eaws STRING,    -- many, some, a_few, nearly_none
  size_eaws INTEGER,        -- 1-5
  danger_level_issued INTEGER,  -- nivel emitido por servicio
  danger_level_matrix INTEGER,  -- nivel según lookup EAWS Matrix
  compliance_group STRING,  -- A, B, C
  season STRING,
  avalanche_problem STRING
);
```

---

## Tabla 6: `snowlab_boletines` — Boletines Snowlab Chile

Fuente: Andes Consciente / Snowlab (contacto pendiente)

```sql
CREATE TABLE IF NOT EXISTS `climas-chileno.validacion_avalanchas.snowlab_boletines` (
  boletin_id STRING,
  fecha_emision DATE,
  fecha_validez_inicio DATE,
  fecha_validez_fin DATE,
  ubicacion STRING,
  nivel_peligro_texto STRING,
  nivel_peligro_eaws INTEGER,
  problemas_avalancha STRING,
  elevacion_critica_m INTEGER,
  aspectos_afectados STRING,
  texto_completo STRING,
  fuente_extraccion STRING,
  archivo_original STRING
);
```

---

## Tabla 7: `snowlab_eaws_mapeado` — Normalizado diario

```sql
CREATE TABLE IF NOT EXISTS `climas-chileno.validacion_avalanchas.snowlab_eaws_mapeado` (
  date DATE,
  ubicacion STRING,
  nivel_peligro_eaws INTEGER,
  estabilidad_eaws STRING,
  frecuencia_eaws STRING,
  tamano_eaws INTEGER,
  confianza_mapeo STRING,
  boletin_id STRING
);
```

---

## Estructura GCS

```
gs://climas-chileno-datos-clima-bronce/
  validacion/
    suiza/
      deapsnow/        ← DEAPSnow RF1/RF2 CSVs
      danger_levels_qc/ ← D_QC CSVs
      avalanchas_davos/ ← Davos avalanche CSVs
      eaws_matrix/      ← Techel 2025 datos (cuando lleguen)
    chile/
      snowlab/          ← Boletines Snowlab PDFs/CSVs
```

---

## Queries de Verificación (FASE 5)

```sql
-- 5.1 Distribución de clases DEAPSnow
SELECT
  danger_level_forecast,
  COUNT(*) as n,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
FROM `climas-chileno.validacion_avalanchas.slf_meteo_snowpack`
GROUP BY 1 ORDER BY 1;

-- 5.2 Split temporal
SELECT
  dataset_split,
  MIN(date) as desde,
  MAX(date) as hasta,
  COUNT(*) as registros
FROM `climas-chileno.validacion_avalanchas.slf_meteo_snowpack`
GROUP BY 1 ORDER BY 2;

-- Cruce DEAPSnow × D_QC
SELECT COUNT(*) as registros_con_dqc
FROM `climas-chileno.validacion_avalanchas.slf_meteo_snowpack` s
JOIN `climas-chileno.validacion_avalanchas.slf_danger_levels_qc` d
  ON s.date = d.date AND s.region = d.region_id;
```

---

## Fuentes y URLs

| Dataset | URL EnviDat |
|---------|------------|
| DEAPSnow RF1/RF2 | https://www.envidat.ch/dataset/weather-snowpack-danger_ratings-data |
| D_QC | https://www.envidat.ch/dataset/re-analysed-regional-avalanche-danger-levels-in-switzerland |
| Avalanchas Davos | https://www.envidat.ch/dataset/snow-avalanche-data-davos |
| EAWS Matrix | Contactar Frank Techel (techel@slf.ch) |
| Snowlab | Contactar Andes Consciente (andesconsciente@gmail.com o Instagram) |

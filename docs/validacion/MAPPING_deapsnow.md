# Mapping DEAPSnow RF2 → BigQuery `slf_meteo_snowpack`

**Archivo fuente**: `data_rf2_tidy.csv`
**Filas**: 29,296
**Período**: 2001-12-01 → 2020-04-23
**Estaciones IMIS**: 129

## Columnas originales → BQ (autodetect)

| CSV original | BQ (`slf_meteo_snowpack`) | Tipo | Descripción |
|---|---|---|---|
| `datum` | `datum` | DATE | Fecha del registro (24h resampled) |
| `station_code` | `station_code` | STRING | Código estación IMIS (ej: BER3) |
| `sector_id` | `sector_id` | INTEGER | ID sector de pronóstico |
| `dangerLevel` | `dangerLevel` | FLOAT64 | **TARGET**: Nivel peligro EAWS 1-5 |
| `elevation_th` | `elevation_th` | FLOAT64 | Umbral elevación pronóstico (m) |
| `warnreg` | `warnreg` | FLOAT64 | Región de alerta |
| `elevation_station` | `elevation_station` | FLOAT64 | Elevación estación (m) |
| `set` | `set` | STRING | Split ML: train/val/test |
| `TA` | `TA` | FLOAT64 | Temperatura aire (°C) |
| `TSS_mod` | `TSS_mod` | FLOAT64 | Temperatura superficie nieve - modelo (°C) |
| `TSS_meas` | `TSS_meas` | FLOAT64 | Temperatura superficie nieve - medición (°C) |
| `RH` | `RH` | FLOAT64 | Humedad relativa (%) |
| `VW` | `VW` | FLOAT64 | Velocidad viento (m/s) |
| `DW` | `DW` | FLOAT64 | Dirección viento (°) |
| `HN24` | `HN24` | FLOAT64 | Nieve nueva 24h (cm) |
| `HS_meas` | `HS_meas` | FLOAT64 | Altura nieve medida (cm) |
| `HS_mod` | `HS_mod` | FLOAT64 | Altura nieve modelo (cm) |
| `SWE` | `SWE` | FLOAT64 | Snow Water Equivalent (kg/m²) |
| `wind_trans24` | `wind_trans24` | FLOAT64 | Transporte de viento 24h |
| `hoar_size` | `hoar_size` | FLOAT64 | Tamaño granos escarcha |
| `Sclass2` | `Sclass2` | FLOAT64 | Clase estabilidad manto nival |
| `pwl_100` | `pwl_100` | FLOAT64 | Weak layer score (top 100cm) |
| `base_pwl` | `base_pwl` | FLOAT64 | Score capa débil base |

## Distribución de clases (variable objetivo)

| `dangerLevel` | N | % |
|---|---|---|
| 1 — Baja | 9,128 | 31.2% |
| 2 — Limitada | 9,309 | 31.8% |
| 3 — Considerable | 9,583 | 32.7% |
| 4 — Alta | 1,194 | 4.1% |
| 5 — Muy Alta | 82 | 0.3% |

## Split temporal ML

| Set | Período (aprox) |
|---|---|
| train | 1997-2016 (~70%) |
| val | 2016-2018 (~15%) |
| test | 2018-2020 (~15%) |

## GCS

```
gs://climas-chileno-datos-clima-bronce/validacion/suiza/deapsnow/
  data_rf1_forecast.csv   → 292,837 filas (RF1 original, 192MB)
  data_rf2_tidy.csv       → 29,296 filas  (RF2 QC, 17MB) ← CARGADO A BQ
```

## Nota RF1 vs RF2

- **RF1** (292k filas): Dataset original completo con más fechas y estaciones
- **RF2** (29k filas): Subset QC — mismo período pero solo estaciones y días donde todos los variables clave están disponibles. Usado para entrenamiento de clasificadores.

Para validación de AndesAI, usamos **RF2** ya que tiene `dangerLevel` 100% completo.

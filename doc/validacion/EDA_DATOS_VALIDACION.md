# EDA — Datos de Validación AndesAI
## Análisis Exploratorio de Tablas BigQuery

**Proyecto:** Tesis Doctoral MTI UTFSM — Francisco Peñailillo M.
**Sistema:** AndesAI v4.0 — predicción de riesgo de avalanchas EAWS
**Fecha EDA:** 2026-05-02
**Proyecto GCP:** `climas-chileno`

---

## 1. Inventario de Tablas

| Dataset | Tabla | Filas | Rol en validación | Estado |
|---------|-------|------:|-------------------|--------|
| `validacion_avalanchas` | `slf_danger_levels_qc` | 45,049 | Ground truth H1/H3 (Swiss SLF) | ✅ disponible |
| `validacion_avalanchas` | `snowlab_boletines` | 30 | Ground truth H4 (Snowlab La Parva) | ✅ disponible |
| `clima` | `boletines_riesgo` | 427 | Predicciones AndesAI (todas versiones) | ✅ disponible |
| `clima` | `imagenes_satelitales` | 3,555 | Input S2 satelital (ViT + NDSI + SAR) | ✅ disponible |
| `clima` | `condiciones_actuales` | 77,480 | Input S3 meteorológico (observaciones) | ✅ disponible |
| `clima` | `pronostico_horas` | 201,563 | Input S3 meteorológico (pronóstico horario) | ✅ disponible |
| `clima` | `pronostico_dias` | 42,353 | Input S3 meteorológico (pronóstico diario) | ✅ disponible |
| `clima` | `zonas_objetivo` | 4 | Metadatos geográficos de zonas operativas | ✅ disponible |
| `clima` | `estado_manto_gee` | — | Input REQ-02a/02b (MODIS LST + SAR) | ❌ no creada |

> **Nota de regiones BQ:** `clima` está en `us-central1`; `validacion_avalanchas` está en `US` (multi-region). Los JOINs cross-dataset deben hacerse en Python (fetch separado), no en SQL nativo.

---

## 2. Ground Truth — `validacion_avalanchas.slf_danger_levels_qc`

**Descripción:** Niveles EAWS verificados por el Instituto Federal de Investigación de Nieve y Avalanchas (SLF), cubriendo los Alpes suizos del invierno 2001-2002 al 2023-2024. Fuente primaria para H1 (F1-macro) y H3 (QWK).

### 2.1 Esquema

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `date` | DATE | Fecha del boletín |
| `sector_id` | INTEGER | ID del sector geográfico SLF (146 sectores únicos) |
| `danger_level_qc` | INTEGER | Nivel EAWS verificado (1–5) — variable objetivo |
| `elevation_m` | FLOAT | Elevación representativa del sector (0–3700 m) |
| `north/east/south/west` | FLOAT | Coordenadas del bounding box del sector |
| `dry_wet` | STRING | Tipo de avalancha: `'dry'` (seca), `NULL` (no especificado) |
| `source_file` | STRING | Archivo fuente de la carga |

### 2.2 Estadísticas clave

| Estadística | Valor |
|-------------|-------|
| Período | 2001-12-01 → 2024-05-18 |
| Días únicos con registro | 3,327 |
| Sectores SLF cubiertos | 146 |
| Total filas | 45,049 |
| Nivel EAWS medio | 2.13 |
| Elevación | 0 m – 3,700 m |

### 2.3 Distribución de niveles EAWS (serie completa)

| Nivel | Nombre EAWS | n | % |
|-------|-------------|---|---|
| 1 | Débil | 13,864 | 30.8% |
| 2 | Limitado | 14,579 | 32.4% |
| 3 | Considerable | 13,382 | 29.7% |
| 4 | Alto | 3,128 | 6.9% |
| 5 | Muy Alto | 96 | 0.2% |

> Los Alpes muestran una distribución bimodal 1-2-3 con niveles 4-5 poco frecuentes. El nivel dominante es el 2 (Limitado).

### 2.4 Estacionalidad (nivel medio por mes)

| Mes | Nivel medio | n |
|-----|-------------|---|
| Noviembre | 2.47 | 238 |
| Diciembre | 2.29 | 7,687 |
| Enero | 2.40 | 11,166 |
| Febrero | 2.24 | 9,380 |
| Marzo | 2.03 | 9,552 |
| Abril | 1.52 | 6,938 |

> El pico de peligro ocurre en noviembre-enero (inicio de temporada), con descenso hacia abril.

### 2.5 Tipo de avalancha (`dry_wet`)

| Valor | n | Observación |
|-------|---|-------------|
| `'dry'` | 28,206 | Nieve seca — condiciones frías |
| `NULL` | 16,843 | Sin clasificación de tipo |
| `'wet'` | 0 | Sin registros húmedos en el dataset |

> El dataset no contiene registros de nieve húmeda — refleja que el ground truth SLF prioriza condiciones de invierno (temperatura bajo 0°C).

### 2.6 Subconjunto de validación Ronda 3 (n=24)

Se seleccionaron 3 estaciones × 10 fechas del invierno 2023-2024. El mapeo de estación → sector SLF usa REQ-04 (sector_id exacto por cercanía geográfica con fallback a cantón modal):

| Estación AndesAI | Cantón SLF | Fechas evaluadas |
|------------------|-----------|-----------------|
| Interlaken | Berna (BE) | dic-2023, ene-2024, feb-2024, mar-2024, abr-2024 (×2 c/u) |
| Matterhorn Zermatt | Valais (VS) | ídem |
| St Moritz | Grisones (GR) | ídem |

Distribución real en el subconjunto n=24:

| Nivel SLF real | n | % |
|---------------|---|---|
| 1 | 3 | 12.5% |
| 2 | 13 | 54.2% |
| 3 | 5 | 20.8% |
| 4 | 3 | 12.5% |
| 5 | 0 | 0.0% |

> Domina el nivel 2 (54.2%) — las fechas seleccionadas representan condiciones moderadas típicas de los Alpes en temporada.

---

## 3. Ground Truth — `validacion_avalanchas.snowlab_boletines`

**Descripción:** 30 boletines de avalancha de La Parva emitidos por Domingo Valdivieso Ducci (Nivel 2 CAA, Snowlab), cubriendo temporadas 2024 y 2025. Fuente primaria para H4 (QWK ≥ 0.60).

### 3.1 Esquema

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `id_boletin` | STRING | REQUIRED | Identificador único, p.ej. `'2024-01'` |
| `temporada` | INTEGER | REQUIRED | Año de la temporada (2024 / 2025) |
| `numero_boletin` | INTEGER | REQUIRED | Número correlativo dentro de la temporada |
| `fecha_publicacion` | DATE | REQUIRED | Fecha de publicación |
| `fecha_inicio_validez` | DATE | REQUIRED | Primer día de validez |
| `fecha_fin_validez` | DATE | REQUIRED | Último día de validez |
| `nivel_alta` | INTEGER | NULLABLE | Peligro banda Alta (3000–4040 msnm) |
| `nivel_media` | INTEGER | NULLABLE | Peligro banda Media (2500–3000 msnm) |
| `nivel_baja` | INTEGER | NULLABLE | Peligro banda Baja (1500–2500 msnm) |
| `nivel_max` | INTEGER | REQUIRED | **Peligro máximo global** — variable objetivo H4 |
| `problema_principal` | STRING | NULLABLE | Tipo de problema de avalancha |
| `url_instagram` | STRING | NULLABLE | URL boletín original |
| `fuente` | STRING | REQUIRED | Fuente del boletín (`'Snowlab'`) |

### 3.2 Estadísticas clave

| Temporada | Boletines | Período | Nivel máx medio | Rango |
|-----------|-----------|---------|-----------------|-------|
| 2024 | 14 | 2024-06-15 → 2024-09-15 | 1.79 | 1–5 |
| 2025 | 16 | 2025-06-06 → 2025-09-21 | 1.69 | 1–3 |
| **Total** | **30** | **2024-06-15 → 2025-09-21** | **1.73** | **1–5** |

### 3.3 Distribución de `nivel_max` (variable objetivo H4)

| Nivel | n | % | Notas |
|-------|---|---|-------|
| 1 | 17 | 56.7% | Condiciones calmas — **clase dominante** |
| 2 | 7 | 23.3% | Post-tormenta descendente |
| 3 | 4 | 13.3% | Tormentas recientes |
| 4 | 1 | 3.3% | Evento significativo |
| 5 | 1 | 3.3% | Evento extremo (2024-06-15) |

> **Desequilibrio crítico para validación:** el 80% de los boletines son nivel 1-2 (condiciones calmas). Este es el desequilibrio que el sistema no puede reproducir — AndesAI predice nivel 3-4 incluso en calma.

### 3.4 Distribución por banda altitudinal

Los boletines especifican niveles diferenciados por banda cuando la topografía lo justifica:

| Campo | Disponible en | Significado |
|-------|---------------|-------------|
| `nivel_alta` | 28/30 boletines | Zona alta 3000–4040 msnm (p.ej. sector cumbre) |
| `nivel_media` | 25/30 boletines | Zona media 2500–3000 msnm |
| `nivel_baja` | 30/30 boletines | Zona baja 1500–2500 msnm |

> Los 5 boletines de fin de temporada 2024 (sept) no tienen `nivel_media` — corresponden a condiciones simples donde solo se diferencia alta vs baja.

### 3.5 Tipos de problema avalanchístico

| Problema | n | Notas |
|----------|---|-------|
| `NULL` (sin problema específico) | 20 | Condiciones calmas, sin problema dominante |
| Placas de tormenta | 3 | Evento post-nevada |
| Placas de tormenta + viento | 2 | Evento combinado (más severo) |
| Post-tormenta, condiciones en descenso | 2 | Transición calma |
| Sin problema específico | 1 | Explícitamente tranquilo |
| Inicio de ciclo nevoso | 1 | Primer evento de la temporada |
| Placa de viento + placa persistente | 1 | Problema complejo persistente |

> El 66.7% de los boletines no tiene problema dominante — confirma que los días calmos son la norma en La Parva.

### 3.6 Serie temporal completa (todos los boletines)

| ID | T | # | Validez | max | alta | media | baja | Problema |
|----|---|---|---------|-----|------|-------|------|----------|
| 2024-01 | 2024 | 1 | 15-17 jun | **5** | 5 | 4 | 2 | Placas tormenta+viento |
| 2024-02 | 2024 | 2 | 21-23 jun | **4** | 4 | 4 | 2 | — |
| 2024-03 | 2024 | 3 | 28-30 jun | **2** | 2 | 2 | 2 | Post-tormenta desc. |
| 2024-04 | 2024 | 4 | 05-07 jul | **1** | 1 | 1 | 1 | — |
| 2024-05 | 2024 | 5 | 12-14 jul | **1** | 1 | 1 | 1 | — |
| 2024-06 | 2024 | 6 | 19-21 jul | **1** | 1 | 1 | 1 | — |
| 2024-07 | 2024 | 7 | 26-28 jul | **1** | 1 | 1 | 1 | — |
| 2024-08 | 2024 | 8 | 02-04 ago | **3** | 3 | 3 | 1 | Placas de tormenta |
| 2024-09 | 2024 | 9 | 09-11 ago | **2** | 2 | 1 | 1 | — |
| 2024-10 | 2024 | 10 | 16-18 ago | **1** | 1 | 1 | 1 | — |
| 2024-11 | 2024 | 11 | 23-25 ago | **1** | 1 | 1 | 1 | — |
| 2024-12 | 2024 | 12 | 30ago-01sep | **1** | 1 | — | 1 | — |
| 2024-13 | 2024 | 13 | 06-08 sep | **1** | 1 | — | 1 | — |
| 2024-14 | 2024 | 14 | 13-15 sep | **1** | 1 | — | 1 | — |
| 2025-01 | 2025 | 1 | 06-08 jun | **1** | 1 | 1 | 1 | Sin prob. específico |
| 2025-02 | 2025 | 2 | 14-16 jun | **3** | 3 | 3 | 2 | Placas tormenta+viento |
| 2025-03 | 2025 | 3 | 21-23 jun | **2** | 2 | 2 | 1 | Post-tormenta desc. |
| 2025-04 | 2025 | 4 | 27-29 jun | **1** | 1 | 1 | 1 | — |
| 2025-05 | 2025 | 5 | 04-06 jul | **1** | 1 | 1 | 1 | — |
| 2025-06 | 2025 | 6 | 11-13 jul | **1** | 1 | 1 | 1 | — |
| 2025-07 | 2025 | 7 | 18-20 jul | **1** | 1 | 1 | 1 | — |
| 2025-08 | 2025 | 8 | 25-27 jul | **2** | 1 | 1 | 2 | Inicio ciclo nevoso |
| 2025-09 | 2025 | 9 | 01-03 ago | **3** | 3 | 3 | 2 | Placas de tormenta |
| 2025-10 | 2025 | 10 | 08-10 ago | **1** | 1 | 1 | 1 | — |
| 2025-11 | 2025 | 11 | 15-17 ago | **1** | 1 | 1 | 1 | — |
| 2025-12 | 2025 | 12 | 22-24 ago | **3** | 3 | 3 | 1 | Placas de tormenta |
| 2025-13 | 2025 | 13 | 29-31 ago | **2** | 2 | 1 | 1 | — |
| 2025-14 | 2025 | 14 | 05-07 sep | **1** | 1 | 1 | 1 | — |
| 2025-15 | 2025 | 15 | 12-14 sep | **2** | 1 | 1 | 2 | — |
| 2025-16 | 2025 | 16 | 19-21 sep | **2** | 2 | 1 | 2 | Placa viento+persistente |

---

## 4. Predicciones — `clima.boletines_riesgo`

**Descripción:** Boletines generados por el sistema AndesAI en todas sus versiones. Contiene los outputs de todos los subagentes, métricas de ejecución y el nivel EAWS predicho. Tabla central del sistema.

### 4.1 Esquema (variables clave)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `nombre_ubicacion` | STRING REQUIRED | Nombre exacto de la ubicación |
| `fecha_emision` | TIMESTAMP REQUIRED | Fecha y hora de emisión (UTC) |
| `nivel_eaws_24h` | INTEGER | **Nivel EAWS 24h** — predicción principal |
| `nivel_eaws_48h` | INTEGER | Nivel EAWS 24–48h |
| `nivel_eaws_72h` | INTEGER | Nivel EAWS 48–72h |
| `version_prompts` | STRING | Versión del sistema que generó este boletín (`v3.1`, `v3.2`, `v4.0`) |
| `estado_pinn` | STRING | Estado del PINN topográfico: `CRITICO`, `INESTABLE`, `MARGINAL`, `ESTABLE` |
| `factor_seguridad_pinn` | FLOAT | Factor de seguridad Mohr-Coulomb del PINN (>1.5 = estable) |
| `estado_vit` | STRING | Estado del Vision Transformer: `CRITICO`, `ALERTADO`, `MODERADO`, `ESTABLE` |
| `score_anomalia_vit` | FLOAT | Score de anomalía ViT (0–10) |
| `factor_meteorologico` | STRING | Factor EAWS dominante detectado por S3 |
| `ventanas_criticas` | INTEGER | Número de ventanas críticas meteorológicas |
| `indice_riesgo_historico` | FLOAT | Índice de riesgo histórico NLP (0.0–1.0) |
| `confianza` | STRING | Nivel de confianza del boletín: `Alta`, `Media`, `Baja` |
| `duracion_segundos` | FLOAT | Duración total de la generación |
| `subagentes_degradados` | STRING | JSON con subagentes que fallaron gracefully |

### 4.2 Distribución de niveles por versión

| Versión | Nivel 1 | Nivel 2 | Nivel 3 | Nivel 4 | Nivel 5 | Total |
|---------|---------|---------|---------|---------|---------|-------|
| v3.1 | 22.9% | 27.1% | 12.5% | 22.9% | 14.6% | 48 |
| v3.2 | 8.8% | 13.0% | 31.8% | 32.6% | 13.4% | 261 |
| v4.0 | **16.7%** | **8.3%** | **40.8%** | **28.3%** | **5.8%** | 120 |

> v3.2 y v4.0 muestran sesgo hacia nivel 3-4 — confirma el hallazgo del piso de nivel 3 identificado en H4.

### 4.3 Cobertura temporal por ubicación (v4.0 únicamente)

| Ubicación | n | Período | Nivel medio | Duración media |
|-----------|---|---------|-------------|----------------|
| La Parva Sector Medio | 30 | 2024-06-15 → 2025-09-19 | 3.63 | 160s |
| La Parva Sector Bajo | 30 | 2024-06-15 → 2025-09-19 | 3.47 | 115s |
| La Parva Sector Alto | 30 | 2024-06-15 → 2025-09-19 | 3.47 | 121s |
| St Moritz | 10 | 2023-12-01 → 2024-04-15 | 1.00 | 131s |
| Interlaken | 10 | 2023-12-01 → 2024-04-15 | 1.70 | 116s |
| Matterhorn Zermatt | 10 | 2023-12-01 → 2024-04-15 | 1.40 | 114s |

> El nivel medio para La Parva (3.47–3.63) contrasta con el ground truth Snowlab (1.73). Esta discrepancia cuantifica el sesgo positivo (+2.0) documentado en H4.

### 4.4 Estados PINN y ViT (v4.0)

| Confianza | Estado PINN | Estado ViT | n |
|-----------|-------------|------------|---|
| Alta | ESTABLE | — | 68 |
| Media | ESTABLE | sin_datos | 13 |
| Media | ESTABLE | ESTABLE | 9 |
| Media | ESTABLE | — | 8 |
| Media | ESTABLE | ALERTADO | 6 |
| Alta | MARGINAL | ESTABLE | 5 |

> El estado PINN dominante es `ESTABLE` incluso cuando el nivel EAWS predicho es 3–4, lo que confirma que el piso de nivel 3 viene del factor meteorológico S3 (`FUSION_ACTIVA`), no del subagente topográfico S1.

### 4.5 Emparejamiento H4: pares AndesAI v4.0 × Snowlab (n=90)

Todos los 90 pares tienen ≤1 día de diferencia entre fecha_emision AndesAI y fecha_inicio_validez Snowlab.

**Matriz de confusión (Snowlab × AndesAI v4.0):**

```
                   AndesAI v4.0
              1    2    3    4    5
Snowlab  1  [ 0    1   30   17    3 ]  (51 pares — 56.7% del GT)
         2  [ 0    0    7   11    3 ]  (21 pares — 23.3%)
         3  [ 0    0    7    4    1 ]  (12 pares — 13.3%)
         4  [ 0    0    2    1    0 ]  ( 3 pares —  3.3%)
         5  [ 0    0    2    1    0 ]  ( 3 pares —  3.3%)
```

| Métrica | Valor |
|---------|-------|
| Sesgo medio | +1.789 |
| MAE | 1.944 |
| Cobertura (pares con match) | 90/90 (100%) |
| Días de diferencia máximos | 0 (todos ≤1 día) |

---

## 5. Imágenes Satelitales — `clima.imagenes_satelitales`

**Descripción:** Imágenes procesadas del satélite GOES-18 y Sentinel-1 SAR para cada zona de monitoreo. Input primario del subagente satelital S2 (ViT + NDSI + SAR). Cada fila es una captura diaria (mañana/tarde/noche) por zona.

### 5.1 Esquema (variables clave para validación)

| Grupo | Variables | Descripción |
|-------|-----------|-------------|
| **Identificación** | `nombre_ubicacion`, `fecha_captura`, `tipo_captura` | Qué, cuándo, momento del día |
| **Calidad imagen** | `pct_nubes`, `es_nublado` | Disponibilidad efectiva del píxel |
| **NDSI / nieve** | `ndsi_medio`, `ndsi_max`, `pct_cobertura_nieve`, `tiene_nieve` | Índice de Nieve por Diferencia Normalizada |
| **Línea de nieve** | `snowline_elevacion_m`, `snowline_mediana_m` | Elevación de la línea de nieve (m) |
| **Cambios temporales** | `delta_pct_nieve_24h`, `delta_pct_nieve_72h`, `tipo_cambio_nieve` | Tendencia del manto nival |
| **LST** | `lst_dia_celsius`, `lst_noche_celsius`, `ciclo_diurno_amplitud` | Land Surface Temperature (MODIS/GOES) |
| **AMI** | `ami_3d`, `ami_7d` | Accumulated Melting Index (grados-día sobre 0°C) |
| **ERA5** | `era5_snow_depth_m`, `era5_swe_m`, `era5_temp_2m_celsius`, `era5_swe_anomalia` | Reanálisis climático ERA5-Land |
| **SAR** | `sar_disponible`, `sar_pct_nieve_humeda`, `sar_delta_vv_db` | Sentinel-1 SAR (humedad superficial manto) |
| **Viento altura** | `viento_altura_vel_ms`, `viento_altura_dir_grados`, `transporte_eolico_activo` | Viento en 700 hPa (~3000 m) |
| **URIs GCS** | `uri_geotiff_*`, `uri_preview_*` | Imágenes almacenadas en Cloud Storage |

### 5.2 Cobertura geográfica (15 ubicaciones monitoreadas)

| Ubicación | n | Desde | Hasta | NDSI medio | SAR | S2 |
|-----------|---|-------|-------|-----------|-----|-----|
| La Parva Sector Bajo | 176 | 2026-03-03 | 2026-05-02 | 2.0 | 27 | 176 |
| Valle Nevado | 176 | 2026-03-03 | 2026-05-02 | 5.8 | 41 | 176 |
| Chapa Verde | 138 | 2026-03-17 | 2026-05-02 | 10.4 | 44 | 138 |
| La Parva Sector Alto | 138 | 2026-03-17 | 2026-05-02 | 4.0 | 31 | 138 |
| El Colorado | 138 | 2026-03-17 | 2026-05-02 | 2.2 | 27 | 138 |
| Antuco | 138 | 2026-03-17 | 2026-05-02 | 10.9 | 59 | 138 |
| Las Araucarias | 138 | 2026-03-17 | 2026-05-02 | **39.7** | 65 | 138 |
| Volcán Osorno | 138 | 2026-03-17 | 2026-05-02 | 15.9 | 54 | 138 |

> Las ubicaciones de la zona central (La Parva, El Colorado) tienen NDSI bajos (2–4) en mayo 2026, consistente con inicio de temporada nival. Las Araucarias (sur, >1000 mm precipitación anual) tiene NDSI 39.7 — nieve persistente.

### 5.3 Disponibilidad de sensores

| Sensor | Disponible | % del total |
|--------|-----------|-------------|
| Sentinel-2 (óptico) | 3,545 / 3,555 | 99.7% |
| SAR Sentinel-1 | 1,039 / 3,555 | 29.2% |
| Ambos simultáneos | 1,032 / 3,555 | 29.0% |
| Ninguno | 3 / 3,555 | 0.1% |

> SAR disponible en ~30% de los registros — refleja la cadencia de revisita de Sentinel-1 (~6 días). El ViT opera principalmente con S2; SAR aporta señal de humedad cuando está disponible (REQ-02b).

### 5.4 Estadísticas NDSI (píxeles sin nube)

| Estadística | Valor |
|-------------|-------|
| Media | 9.8 |
| Mínimo | 0.0 |
| Máximo | 65.2 |
| Desviación estándar | 13.1 |
| % cobertura nieve media | 8.1% |
| Registros con nieve (`tiene_nieve=True`) | 1,007 / 2,249 sin nube (44.8%) |

> El NDSI está en escala 0–100. Umbral de detección de nieve: NDSI ≥ 40. Valor máximo observado (65.2) indica nieve limpia y densa.

### 5.5 Tipo de cambio del manto nival

| Tipo | n | % | Interpretación |
|------|---|---|----------------|
| `perdida` | 1,992 | 56.0% | Retroceso del manto — derretimiento o sublimación |
| `NULL` | 1,426 | 40.1% | Sin referencia histórica para comparar |
| `estable` | 107 | 3.0% | Sin cambio significativo en cobertura |
| `sin_datos` | 30 | 0.8% | Imagen disponible pero sin datos de nieve |

> El 56% de las capturas muestran pérdida de nieve — coherente con que el período de datos (mar–may 2026) corresponde al verano austral (manto en retroceso).

### 5.6 Fuentes de imágenes

| Fuente | Versión metodología | n |
|--------|--------------------|----|
| GOES-18 (óptico) | v1.1.0 | 3,525 |
| SAR (backfill Sentinel-1) | backfill_satelital_v1 | 30 |

---

## 6. Datos Meteorológicos

### 6.1 `clima.condiciones_actuales`

Observaciones meteorológicas en tiempo real descargadas periódicamente para cada ubicación desde la API WeatherAPI.

| Estadística | Valor |
|-------------|-------|
| Ubicaciones cubiertas | 92 |
| Período | 2023-12-01 → 2026-05-02 |
| Total registros | 77,480 |
| Temperatura media | 15.3°C |
| Rango temperatura | −30.6°C → +29.6°C |
| Precipitación media acumulada | 0.06 mm |

**Variables de avalanchas relevantes:**

| Variable | Tipo | Descripción |
|----------|------|-------------|
| `temperatura` | FLOAT | Temperatura actual (°C) |
| `punto_rocio` | FLOAT | Punto de rocío (°C) — proxy humedad manto |
| `velocidad_viento` | FLOAT | Viento superficial (km/h) |
| `precipitacion_acumulada` | FLOAT | Precipitación acumulada en la observación (mm) |
| `probabilidad_tormenta` | FLOAT | Probabilidad de tormenta (%) |

### 6.2 `clima.pronostico_horas`

Pronóstico horario (hasta 14 días) descargado en cada ejecución del sistema.

| Estadística | Valor |
|-------------|-------|
| Ubicaciones cubiertas | 71 |
| Período | 2026-03-18 → 2026-05-02 |
| Total registros | 201,563 |
| Temperatura media | 3.9°C |
| Tipos de precipitación | 6 (`rain`, `snow`, `sleet`, y variantes) |

**Variables de avalanchas relevantes:**

| Variable | Descripción |
|----------|-------------|
| `temperatura` / `punto_rocio` | Indicadores de ciclo de fusión/congelación |
| `tipo_precipitacion` | `snow` activa el factor `NEVADA_RECIENTE` en S3 |
| `rafaga_viento` | Ráfagas > 50 km/h activan `TRANSPORTE_EOLICO` en S3 |
| `temperatura_bulbo_humedo` | Umbral de nieve/lluvia en altitud |
| `prob_precipitacion` / `cantidad_precipitacion` | Intensidad para calcular `HN24`, `HN48`, `HN72` |

### 6.3 `clima.pronostico_dias`

Pronóstico diario con separación diurno/nocturno — usado por S3 para detectar el ciclo de fusión diurna/congelación nocturna (`FUSION_ACTIVA`).

| Estadística | Valor |
|-------------|-------|
| Ubicaciones cubiertas | 71 |
| Período | 2023-12-01 → 2026-05-05 |
| Total registros | 42,353 |
| Temperatura máxima media | 8.2°C |
| Probabilidad precipitación media | 20.3% |

**Variables de avalanchas relevantes:**

| Variable | Descripción |
|----------|-------------|
| `diurno_temp_max` / `nocturno_temp_min` | Amplitud térmica → detecta `FUSION_ACTIVA` |
| `diurno_prob_precipitacion` | Umbral para activar `NEVADA_RECIENTE` |
| `diurno_velocidad_viento` | Transporte eólico diurno |

> **Nota sobre `FUSION_ACTIVA`:** cuando `diurno_temp_max > 0°C` y `nocturno_temp_min < −2°C`, S3 clasifica el ciclo como `FUSION_ACTIVA`. Este factor empuja el nivel EAWS predicho hacia 3 incluso sin precipitación — es el principal driver del sesgo en H4.

---

## 7. Zonas Objetivo — `clima.zonas_objetivo`

Metadatos geográficos de las 4 zonas operativas del sistema.

| Zona | Latitud | Longitud | Elevación | Exposición | Región EAWS |
|------|---------|----------|-----------|-----------|-------------|
| El Colorado | −33.360 | −70.289 | 2400–4100 m | Oeste | Andes Central Norte |
| La Parva | −33.354 | −70.298 | 2200–4500 m | Sureste | Andes Central Norte |
| La Parva Sector Bajo | −33.363 | −70.301 | 2200–3200 m | Sureste | Andes Central Norte |
| Valle Nevado | −33.357 | −70.270 | 2800–4500 m | Noroeste | Andes Central Norte |

> Las 4 zonas están en la cordillera andina central (~33°S), a menos de 3 km entre sí. Comparten masa de aire y régimen de viento, lo que explica la alta correlación entre sectores del mismo boletín Snowlab.

---

## 8. Tabla Faltante — `clima.estado_manto_gee`

**Estado:** ❌ **No creada en BigQuery**

Esta tabla debería almacenar los outputs de REQ-02a (MODIS LST + ERA5 suelo) y REQ-02b (SAR humedad superficial Sentinel-1) procesados desde Google Earth Engine. Su ausencia implica que:

- El subagente satelital S2 degrada gracefully: no puede leer `obtener_modis_lst()` ni `obtener_sar_baseline()` desde BQ
- Las señales `lst_dia_celsius`, `ciclo_diurno_amplitud` y `sar_delta_vv_db` existen en `imagenes_satelitales` pero no en un formato optimizado para el PINN

**Schema previsto** (documentado en `tool_estado_manto.py`):

| Campo esperado | Tipo | Descripción |
|----------------|------|-------------|
| `nombre_ubicacion` | STRING | Zona |
| `fecha` | DATE | Fecha de la observación |
| `lst_dia_celsius` | FLOAT | LST diurna MODIS |
| `lst_noche_celsius` | FLOAT | LST nocturna MODIS |
| `ciclo_amplitud` | FLOAT | Amplitud térmica día-noche |
| `sar_vv_db` | FLOAT | Backscatter VV Sentinel-1 |
| `sar_delta_vv_db` | FLOAT | Delta VV vs referencia seca |
| `humedad_superficial` | FLOAT | Estimación humedad manto |

---

## 9. Hallazgos EDA Relevantes para la Tesis

### 9.1 Desequilibrio de clases en ground truth

| Dataset | Nivel 1 | Nivel 2 | Nivel 3+ |
|---------|---------|---------|---------|
| SLF Suiza (n=45,049) | 30.8% | 32.4% | 36.8% |
| SLF subconjunto validación (n=24) | 12.5% | 54.2% | 33.3% |
| Snowlab La Parva (n=30) | **56.7%** | 23.3% | 20.0% |

> Snowlab tiene fuerte sesgo hacia el nivel 1 (56.7%). El sistema no fue entrenado para discriminar dentro de los niveles bajos, lo que explica el piso de nivel 3.

### 9.2 Gap de dominio Andes–Alpes

La Parva (Andes, ~33°S, roca volcánica, 2200–4500 m) vs Alpes suizos (46°N, roca caliza/granito, 0–3700 m) difieren en:

| Factor | Andes (La Parva) | Alpes (SLF) |
|--------|-----------------|-------------|
| Rango elevación dataset | 2200–4500 m | 0–3700 m |
| Nivel EAWS medio dataset | 3.5 (AndesAI v4) | 2.13 (SLF real) |
| Sesgo AndesAI v4 | +1.79 vs Snowlab | −0.92 vs SLF |
| Ciclo de fusión | Frecuente (FUSION_ACTIVA) | Menos frecuente en invierno |
| Precipitación orográfica ERA5 | Subestimada en Andes → REQ-03 corrige (+) | Diferente régimen → REQ-03 contraproducente |

### 9.3 Cobertura SAR como limitación para REQ-02b

Con SAR disponible en el 29.2% de los registros de `imagenes_satelitales`, la señal de humedad del manto (`sar_delta_vv_db`) solo está activa en ~1 de cada 3.5 días. Esto limita la capacidad de REQ-02b para detectar ciclos de fusión en el manto.

### 9.4 Período de validación vs período de datos satelitales

| Conjunto | Período validación (fechas Snowlab) | Período datos satelitales disponibles |
|----------|------------------------------------|------------------------------------|
| H4 La Parva | jun 2024 – sep 2025 | mar 2026 – may 2026 |
| H1/H3 Suiza | dic 2023 – abr 2024 | mar 2026 – may 2026 |

> Los datos satelitales en `imagenes_satelitales` corresponden a imágenes actuales (2026), no a las fechas históricas de validación. El sistema usa datos BQ históricos (`condiciones_actuales`, `pronostico_horas`) para el contexto meteorológico, pero las imágenes GOES/Sentinel son aproximaciones del estado actual del manto, no del estado en las fechas de validación.

---

## 10. Referencias de Archivos

| Archivo | Descripción |
|---------|-------------|
| `notebooks_validacion/07_validacion_slf_suiza.py` | Cálculo de métricas H1/H3 desde BQ |
| `notebooks_validacion/08_validacion_snowlab.py` | Cálculo de métricas H4 desde BQ |
| `notebooks_validacion/cargar_snowlab_bq.py` | Script de carga inicial de snowlab_boletines |
| `notebooks_validacion/reprocesar_retroactivo.py` | Replay 120 runs v4.0 |
| `notebooks_validacion/baseline_v32_ronda2.json` | Métricas v3.2 preservadas |
| `notebooks_validacion/RESULTADOS_VALIDACION.md` | Resultados completos Ronda 1-3 |
| `agentes/subagentes/subagente_satelital/tools/tool_estado_manto.py` | Tool que lee `estado_manto_gee` (degrada si no existe) |
| `agentes/prompts/registro_versiones.py` | Hashes y versiones de prompts (v4.0) |

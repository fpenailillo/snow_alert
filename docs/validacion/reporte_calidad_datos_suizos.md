# Reporte de Calidad — Datos de Validación Suizos

**Fecha generación**: 2026-03-23
**Proyecto GCP**: `climas-chileno`
**Dataset BQ**: `validacion_avalanchas`

---

## Resumen ejecutivo

| Tabla | Filas | Período | Estado |
|---|---|---|---|
| `slf_meteo_snowpack` | 29,296 | 2001-12-01 → 2020-04-23 | ✅ Completo |
| `slf_danger_levels_qc` | 45,049 | 2001-12-01 → 2024-05-18 | ✅ Completo |
| `slf_avalanchas_davos` | 13,918 | 1998-11-06 → 2019-05-27 | ✅ Completo |
| `slf_actividad_diaria_davos` | 3,533 | 1998-11-20 → 2019-05-21 | ✅ Completo |
| `eaws_matrix_operacional` | 0 | — | ⏳ Pendiente (email a Techel) |
| `snowlab_boletines` | 0 | — | ⏳ Pendiente (contacto Andes Consciente) |
| `snowlab_eaws_mapeado` | 0 | — | ⏳ Pendiente (depende de snowlab_boletines) |
| **TOTAL suizos** | **91,796** | 1997-2024 | ✅ |

---

## 1. `slf_meteo_snowpack` (DEAPSnow RF2)

**Fuente**: EnviDat — WSL Institute for Snow and Avalanche Research (SLF), Davos
**Licencia**: CC-BY
**Referencia**: Pérez-Guillén et al. 2022, *Nat. Hazards Earth Syst. Sci.*

### Cobertura
- **129 estaciones IMIS** en Alpes Suizos
- **Período**: diciembre 2001 → abril 2020
- **Frecuencia**: Resolución diaria (24h)
- **Variable objetivo**: `dangerLevel` (1-5, 100% completo)

### Distribución de clases
| Nivel | N | % | Clase EAWS |
|---|---|---|---|
| 1 | 9,128 | 31.2% | Baja |
| 2 | 9,309 | 31.8% | Limitada |
| 3 | 9,583 | 32.7% | Considerable |
| 4 | 1,194 | 4.1% | Alta |
| 5 | 82 | 0.3% | Muy Alta |

**Nota**: Distribución de clases ~63% entre niveles 2-3 (típico Alpes suizos), niveles 4-5 representen eventos extremos (~4.4%).

### Split ML
| Set | N | % |
|---|---|---|
| train | ~20,500 | ~70% |
| val | ~4,400 | ~15% |
| test | ~4,400 | ~15% |

---

## 2. `slf_danger_levels_qc` (D_QC Re-analyzed)

**Fuente**: EnviDat — Frank Techel (SLF)
**DOI**: 10.16904/envidat.426
**Licencia**: CC-BY-SA

### Cobertura
- **146 regiones únicas** en Suiza
- **Período**: diciembre 2001 → mayo 2024 (22+ temporadas)
- **3 archivos fuente** unificados con schema normalizado

### Distribución de clases (re-analizadas QC)
| `danger_level_qc` | N | % |
|---|---|---|
| 1 | 13,864 | 30.8% |
| 2 | 14,579 | 32.4% |
| 3 | 13,382 | 29.7% |
| 4 | 3,128 | 6.9% |
| 5 | 96 | 0.2% |

**Nota**: Los niveles re-analizados QC representan la "verdad de campo" más fiable para validación. Ligero shift hacia niveles más altos vs. pronóstico.

---

## 3. `slf_avalanchas_davos` (Observaciones individuales)

**Fuente**: EnviDat — SLF Davos
**Licencia**: ODbL

- **13,918 avalanchas** observadas en Davos
- **Período**: invierno 1998-99 → invierno 2018-19 (21 temporadas)
- Incluye: tipo nieve, trigger, elevación inicio/stop, aspecto, tamaño EAWS (1-4), danger level correlacionado

---

## 4. `slf_actividad_diaria_davos` (Actividad diaria)

- **3,533 días** con registro de actividad
- Variables clave: `max_danger_corr`, `AAI_all`, conteos por tipo y tamaño
- 15 columnas clave seleccionadas de 122 originales

---

## 5. Calidad de datos

### Nulos por tabla
| Tabla | % nulos (cols clave) |
|---|---|
| `slf_meteo_snowpack` | <5% en columnas físicas, 0% en dangerLevel |
| `slf_danger_levels_qc` | 0% en date, sector_id, danger_level_qc |
| `slf_avalanchas_davos` | ~2% en max_danger_corr (NA → NULL) |
| `slf_actividad_diaria_davos` | 0% en columnas clave |

---

## 6. Relevancia para hipótesis AndesAI

| Hipótesis | Dataset usado | Uso |
|---|---|---|
| H1 (F1-macro ≥75%) | `slf_meteo_snowpack` | Benchmark distribución clases, comparación con modelo suizo |
| H3 (QWK vs Techel) | `slf_danger_levels_qc` | Ground truth re-analizado para QWK |
| H4 (Kappa vs Snowlab) | `snowlab_eaws_mapeado` | **Pendiente datos Snowlab** |

---

## Acciones pendientes

1. **Techel EAWS Matrix**: Enviar email a techel@slf.ch — datos de 26 servicios para H3
2. **Snowlab**: Contactar Andes Consciente para boletines históricos La Parva
3. **DEAPSnow RF1**: Considerar cargar RF1 completo (292k filas) si se necesita más data de entrenamiento para benchmark

# Resultados de Validación — AndesAI Sistema Multi-Agente

**Proyecto:** Tesis Doctoral MTI UTFSM — Francisco Peñailillo M.
**Sistema:** AndesAI, predicción de riesgo de avalanchas EAWS (5 subagentes)
**Última actualización:** 2026-05-02

---

## Resumen de hipótesis

| Hipótesis | Descripción | Objetivo | Estado |
|-----------|-------------|----------|--------|
| H1 | F1-macro ≥ 75% en clasificación EAWS vs SLF Suiza | F1 ≥ 0.75 | ✗ No alcanzada |
| H3 | QWK comparable a Techel et al. (2022) | QWK ≥ 0.59 | ✗ No alcanzada |
| H4 | QWK ≥ 0.60 vs Snowlab La Parva | QWK ≥ 0.60 | ✗ No alcanzada |

---

## H1 y H3 — Validación Swiss SLF

**Script:** `notebooks_validacion/07_validacion_slf_suiza.py`
**Ground truth:** `validacion_avalanchas.slf_danger_levels_qc` (SLF Suiza 2001-2024)
**Muestra:** n=24 pares emparejados (3 estaciones × 10 fechas invierno 2023-2024)
**Mapeo:** sector geográfico preciso REQ-04 (sector_id exacto + fallback cantón modal)

### Progresión por rondas

| Ronda | Versión | QWK | F1-macro | Acc exacta | Acc ±1 | Sesgo |
|-------|---------|-----|----------|------------|--------|-------|
| 1 | v3.0 (sin satélite) | −0.056 | 0.197 | — | 0.708 | −0.79 |
| 2 | v3.2 (con satélite, mapeo cantón) | +0.109 | 0.191 | 0.250 | 0.750 | −0.54 |
| 2b | v3.2 (con satélite, sector preciso) | +0.016 | 0.161 | 0.208 | 0.750 | −0.50 |
| **3** | **v4.0 (REQs implementados)** | **+0.162** | **0.155** | **0.250** | **0.792** | **−0.92** |
| Ref. | Techel et al. 2022 | 0.590 | 0.550 | 0.640 | 0.950 | — |

### Distribución de niveles predichos vs reales (Ronda 3 v4.0)

| Nivel | SLF real (%) | AndesAI v4.0 (%) | AndesAI v3.2 (%) |
|-------|-------------|------------------|------------------|
| 1 | 12.5 | 62.5 | 45.8 |
| 2 | 54.2 | 33.3 | 29.2 |
| 3 | 20.8 | 4.2 | 20.8 |
| 4 | 12.5 | 0.0 | 4.2 |
| 5 | 0.0 | 0.0 | 0.0 |

### Análisis de mejoras entre rondas

**Ronda 1 → Ronda 2:** QWK −0.056 → +0.109 (+0.165). Los datos satelitales (NDSI, ERA5, SAR en `imagenes_satelitales`) son el driver principal.

**Ronda 2 → Ronda 3:** QWK +0.016 → +0.162 (+0.146). Las señales MODIS LST y SAR humedad (REQ-02a/02b) enriquecen el contexto satelital de S2.

**Regresión de sesgo (−0.50 → −0.92):** REQ-03 aplica corrección orográfica ERA5 calibrada para Andes (reduce precipitación 15-35% según altitud). En los Alpes el régimen orográfico es diferente → la reducción penaliza la señal meteorológica → el modelo predice más conservador en Europa. Limitación geográfica del REQ-03, válido para Chile.

### Causa raíz — gap de dominio Andes→Alpes

El sistema fue calibrado en topografía andina (PINN, ViT, parámetros EAWS para Andes). En los Alpes suizos:
- Los sectores SLF tienen niveles 2-4 en condiciones que en Andes serían nivel 1-2
- El PINN usa métricas topográficas de La Parva/Valle Nevado; la fricción y cohesión en granito alpino difieren de la roca volcánica andina
- ERA5 @9km subrepresenta la orografía alpina más compleja

→ H1 y H3 rechazadas. Resultado publicable: cuantifica el gap de transferencia de dominio entre sistemas montañosos.

---

## H4 — Validación Snowlab La Parva

**Script:** `notebooks_validacion/08_validacion_snowlab.py`
**Ground truth:** `validacion_avalanchas.snowlab_boletines` (30 boletines, Domingo Valdivieso Ducci L2 CAA)
**Muestra:** n=87 pares (3 sectores × 30 boletines, 85/87 a ≤3 días de distancia)

### Progresión por rondas

| Ronda | Versión | QWK | MAE | Sesgo | F1-macro |
|-------|---------|-----|-----|-------|----------|
| 2 | v3.2 | −0.016 | 2.103 | +1.989 | 0.104 |
| **3** | **v4.0** | **−0.006** | **2.138** | **+2.023** | **0.030** |
| Objetivo | — | ≥ 0.60 | — | ≤ +0.50 | — |

### Matriz de confusión v4.0 (Ronda 3)

```
                    AndesAI
              1    2    3    4    5
Snowlab  1  [ 0    1   32   24    3 ]  (60 casos)
         2  [ 0    0    5    8    2 ]  (15 casos)
         3  [ 0    0    4    3    1 ]  ( 8 casos)
         4  [ 0    0    3    0    0 ]  ( 3 casos)
         5  [ 0    0    1    0    0 ]  ( 1 caso)
```

### Hallazgo crítico — piso de nivel 3 en condiciones calmas

El sesgo asimétrico es la principal limitación:
- **Cuando Snowlab ≥ 3 (tormentas, n=12):** el modelo detecta correctamente (MAE ≈ 0.75)
- **Cuando Snowlab ≤ 2 (calma, n=75):** el modelo predice sistemáticamente 3-4 (MAE ≈ 2.30)

El sistema es un buen detector de tormentas pero no puede confirmar condiciones tranquilas.

### Diagnóstico causa raíz del piso nivel 3

REQ-01 (persistencia temporal) fue implementado para resolver este problema pero está **bloqueado upstream**:

1. **S1 — PINN topográfico:** calcula riesgo basado en la geometría del terreno (pendientes 35-45°, 700+ ha de zona de inicio en La Parva). Este riesgo es inherente al terreno, no al estado del manto → S1 siempre contribuye un nivel base de "riesgo topográfico moderado" aunque no haya eventos
2. **S3 — Meteorológico:** clasifica el ciclo de fusión diurna/congelación nocturna (frecuente en Andes austral) como `FUSION_ACTIVA` → empuja el nivel hacia 3 aunque no haya precipitación reciente
3. **S5 — Integrador:** recibe señales de S1 y S3 que ya suman nivel 3 → REQ-01 nunca puede aplicar el cap
4. **REQ-01:** necesita ≥4 boletines consecutivos con nivel ≤2 para activar `calma_confirmada=True`, pero el propio modelo genera nivel 3 → la cadena nunca se forma

### Fix pendiente para H4

Para que REQ-01 funcione correctamente hay que corregir upstream:

1. **S1 prompt:** distinguir entre "riesgo topográfico potencial" (geometría fija) y "riesgo activo" (requiere evento meteorológico + estado del manto). No contribuir nivel base en ausencia de precipitación reciente.
2. **S3 lógica:** ponderar `FUSION_ACTIVA` como factor menor cuando no hay precipitación y temperatura máxima < 5°C.
3. **Verificación:** correr 2-3 boletines con condiciones calmas simuladas y confirmar que REQ-01 se activa con la cadena v4.

---

## Metodología del reprocesamiento Ronda 3

Para comparar v3.2 vs v4.0 sobre el mismo ground truth se usó `OrquestadorAvalancha.generar_boletin(fecha_referencia=...)`:
- Las queries BQ filtran datos históricos por `fecha_referencia`
- Las APIs externas (ERA5, Open-Meteo) devuelven datos actuales como aproximación
- El procesamiento fue cronológico para que REQ-01 pudiera leer la cadena de predicciones v4 anteriores
- Script: `notebooks_validacion/reprocesar_retroactivo.py` — 120 runs, 0 errores

**Limitación del método:** los datos satelitales en tiempo real (Open-Meteo, ERA5 vía API) corresponden a condiciones actuales (mayo 2026), no a las fechas históricas de validación. Solo los datos almacenados en BQ (`imagenes_satelitales`, `condiciones_actuales`, `pronostico_horas`) reflejan el estado histórico exacto.

---

## Archivos relevantes

| Archivo | Descripción |
|---------|-------------|
| `notebooks_validacion/07_validacion_slf_suiza.py` | Validación H1/H3 (ejecutar para métricas actuales) |
| `notebooks_validacion/08_validacion_snowlab.py` | Validación H4 (ejecutar para métricas actuales) |
| `notebooks_validacion/reprocesar_retroactivo.py` | Replay retroactivo con nueva versión de código |
| `notebooks_validacion/baseline_v32_ronda2.json` | Métricas v3.2 preservadas (JSON) |
| `log_claude.md` | Historial de sesiones y decisiones de implementación |
| `claude/requirements/Mejoras04_v1.md` | Especificación de los REQs implementados |

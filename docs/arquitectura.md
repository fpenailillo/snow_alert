# Arquitectura del Sistema — Snow Alert

> Sistema Multi-Agente para Predicción de Avalanchas sobre GCP
> Tesina: Francisco Peñailillo — Magíster TI, UTFSM — Dr. Mauricio Solar

## Visión General

Snow Alert es un sistema multi-agente que genera boletines de riesgo de avalanchas
siguiendo la escala EAWS (European Avalanche Warning Services) de 5 niveles.
Opera sobre Google Cloud Platform con 5 subagentes especializados de Claude
que analizan datos topográficos, satelitales, meteorológicos e históricos.

## Diagrama de Flujo

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPA DE DATOS (Cloud Functions)              │
│                                                                 │
│  Weather API → extractor → procesador → BQ:condiciones_actuales │
│                         → procesador_horas → BQ:pronostico_horas│
│                         → procesador_dias  → BQ:pronostico_dias │
│  GEE/MODIS/ERA5 → monitor_satelital → BQ:imagenes_satelitales  │
│  DEM → analizador_avalanchas → BQ:zonas_avalancha              │
│  Andeshandbook → (ETL manual) → BQ:relatos_montanistas         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ BigQuery
┌──────────────────────────▼──────────────────────────────────────┐
│               SISTEMA MULTI-AGENTE (Cloud Run Job)              │
│                                                                 │
│  ┌──────────┐  contexto  ┌──────────┐  contexto  ┌──────────┐  │
│  │    S1    │───────────→│    S2    │───────────→│    S3    │  │
│  │Topográf. │            │Satelital │            │Meteorol. │  │
│  │DEM+PINN  │            │ViT temp. │            │Ventanas  │  │
│  └──────────┘            └──────────┘            └────┬─────┘  │
│                                                       │         │
│                          ┌──────────┐  contexto  ┌────▼─────┐  │
│                          │    S5    │←───────────│    S4    │  │
│                          │Integrador│            │   NLP    │  │
│                          │EAWS+Bol. │            │ Relatos  │  │
│                          └────┬─────┘            └──────────┘  │
│                               │                                 │
└───────────────────────────────┼─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                    CAPA DE SALIDA                                │
│  BQ:boletines_riesgo (33 campos) + GCS:boletines/{ubicacion}/   │
└─────────────────────────────────────────────────────────────────┘
```

## Pipeline de 5 Subagentes

| # | Subagente | Modelo | Tools | Output clave |
|---|-----------|--------|-------|--------------|
| S1 | Topográfico | claude-sonnet-4-5 | dem, pinn, zonas, estabilidad | `clase_estabilidad_eaws`, `factor_seguridad_mohr_coulomb` |
| S2 | Satelital | claude-sonnet-4-5 | ndsi, vit, anomalias, snowline | `estado_vit`, `score_anomalia` |
| S3 | Meteorológico | claude-sonnet-4-5 | condiciones, tendencia, pronostico, ventanas | `ventanas_criticas`, `factor_meteorologico` |
| S4 | NLP Relatos | claude-sonnet-4-5 | buscar_relatos, extraer_patrones, conocimiento | `indice_riesgo_historico`, `tipo_alud_predominante` |
| S5 | Integrador | claude-sonnet-4-5 | clasificar_eaws, generar_boletin, explicar | Boletín EAWS completo (niveles 24/48/72h) |

### Flujo de contexto

Cada subagente recibe el análisis acumulado de todos los subagentes anteriores
(máximo 12,000 caracteres, truncado si excede). El contexto se construye como
bloques etiquetados:

```
[ANÁLISIS TOPOGRÁFICO (PINN)]
PINN: MARGINAL (FS=1.35). Estabilidad: fair. ...

[ANÁLISIS SATELITAL (ViT)]
ViT: ALERTADO. NDSI=0.45. Cobertura=65%. ...

[ANÁLISIS METEOROLÓGICO]
Viento: 45 km/h. Precipitación: 15mm. ...

[ANÁLISIS NLP RELATOS]
15 relatos analizados. Tipo predominante: placa. ...
```

## Componentes de la Capa de Datos

### Cloud Functions (`datos/`)
| Función | Frecuencia | Tabla BQ destino |
|---------|-----------|-----------------|
| `extractor/` | cada 3h | `condiciones_actuales` |
| `procesador/` | cada 3h | `condiciones_actuales` |
| `procesador_horas/` | cada 6h | `pronostico_horas` |
| `procesador_dias/` | diario | `pronostico_dias` |
| `monitor_satelital/` | diario | `imagenes_satelitales` |
| `analizador_avalanchas/` | mensual | `zonas_avalancha` |

### Tablas BigQuery (`clima.*`)
| Tabla | Campos clave | Partición |
|-------|-------------|-----------|
| `condiciones_actuales` | temp, viento, precipitación, humedad | fecha |
| `pronostico_horas` | temp_hora, viento_hora, prob_precip | fecha |
| `pronostico_dias` | temp_max/min, viento_max, precip_total | fecha |
| `imagenes_satelitales` | NDSI, LST día/noche, cobertura nieve, snow_depth | fecha |
| `zonas_avalancha` | pendiente, orientación, altitud, desnivel | — |
| `relatos_montanistas` | texto, ubicación, fecha, fuente | fecha |
| `boletines_riesgo` | 33 campos (nivel EAWS, boletín, métricas por subagente) | fecha_emision |

## Mecanismos de Resiliencia

### Reintentos API (base_subagente.py)
- 3 reintentos con backoff exponencial (2s base, 30s máximo)
- Reintenta: rate limit (429), errores servidor (5xx), errores conexión
- Falla rápido: errores cliente (400, 401, 403)

### Degradación Graceful (agente_principal.py)
- SubagenteNLP es no-crítico: si falla, pipeline continúa con 4 subagentes
- Resultado incluye `subagentes_degradados` para trazabilidad
- Boletín válido incluso sin datos históricos de relatos

### Versionado de Prompts (registro_versiones.py)
- SHA-256 por componente (6 prompts versionados)
- Verificación de integridad al iniciar orquestador
- Campo `version_prompts` en cada boletín generado

## Decisiones de Diseño

Ver `docs/decisiones_diseno.md` para las 10 justificaciones académicas detalladas,
incluyendo alternativas consideradas, referencias bibliográficas y archivos relevantes.

## Recursos GCP

| Recurso | Valor |
|---------|-------|
| Proyecto | `climas-chileno` |
| Dataset | `clima` |
| Bucket | `climas-chileno-datos-clima-bronce` |
| Cloud Run Job | `orquestador-avalanchas` (us-central1) |
| Secret | `claude-oauth-token` (Secret Manager) |

# PROMPT_VALIDACION_ESTADO — snow_alert

> Pega este prompt completo al inicio de una sesión de Claude Code para obtener
> un diagnóstico del sistema en ~2 minutos. Requiere estar en el directorio
> raíz de `snow_alert/`.

---

## INSTRUCCIONES PARA CLAUDE CODE

Ejecuta las verificaciones descritas abajo **en paralelo donde sea posible**
(usa múltiples llamadas de herramientas en el mismo turno). Al terminar, genera
un **Reporte de Estado** con semáforos y acciones concretas.

Criterios de semáforo:
- ✅ Todo funciona dentro de los parámetros normales
- ⚠️ Funciona pero hay degradación, datos viejos o advertencias
- ❌ Fallo crítico que bloquea el sistema

---

## DIMENSIÓN 1 — Autenticación GCP

Ejecuta en bash:
```bash
gcloud auth list 2>&1 | head -5
gcloud config get-value project 2>&1
gcloud auth application-default print-access-token 2>&1 | head -c 20
```

Evalúa:
- ✅ Cuenta activa es `fpenailillom@correo.uss.cl`, proyecto es `climas-chileno`, ADC responde con token
- ⚠️ Cuenta activa distinta pero proyecto correcto
- ❌ Sin cuenta activa, proyecto incorrecto, o ADC falla con error

---

## DIMENSIÓN 2 — Secret Manager (credencial Claude)

Ejecuta en bash:
```bash
gcloud secrets versions list claude-oauth-token \
  --project=climas-chileno \
  --format="table(name,state,createTime)" 2>&1 | head -5
```

Evalúa:
- ✅ Existe al menos 1 versión en estado `enabled`
- ⚠️ Existe pero la versión más reciente tiene >30 días
- ❌ Secret no existe o no tiene versiones habilitadas

---

## DIMENSIÓN 3 — Cloud Functions activas

Ejecuta en bash:
```bash
gcloud functions list \
  --project=climas-chileno \
  --region=us-central1 \
  --gen2 \
  --format="table(name,state,updateTime)" 2>&1
```

Las 6 funciones esperadas son:
- `extractor-clima`
- `procesador-clima`
- `procesador-clima-horas`
- `procesador-clima-dias`
- `analizador-satelital-zonas-riesgosas-avalanchas`
- `monitor-satelital-nieve`

Evalúa por función:
- ✅ Estado `ACTIVE`, updateTime < 30 días
- ⚠️ Estado `ACTIVE` pero updateTime > 30 días (código desactualizado)
- ❌ Estado `FAILED`, `DEPLOYING` atascado, o función ausente

---

## DIMENSIÓN 4 — Cloud Scheduler jobs

Ejecuta en bash:
```bash
gcloud scheduler jobs list \
  --location=us-central1 \
  --project=climas-chileno \
  --format="table(name,schedule,state,lastAttemptTime,status)" 2>&1
```

Los 3 jobs esperados son:
- `extraer-clima-job` → `0 8,14,20 * * *`
- `analizar-topografia-job` → `0 3 1 * *`
- `monitor-satelital-job` → `30 8,14,20 * * *`

Evalúa por job:
- ✅ Estado `ENABLED`, lastAttemptTime < 8 horas (para los de 3x/día)
- ⚠️ ENABLED pero lastAttemptTime > 8 horas o status con error reciente
- ❌ Estado `DISABLED`, `PAUSED`, o job ausente

---

## DIMENSIÓN 5 — Cloud Run Job (orquestador)

Ejecuta en bash:
```bash
gcloud run jobs describe orquestador-avalanchas \
  --region=us-central1 \
  --project=climas-chileno \
  --format="yaml(metadata.name,status,spec.template.spec.template.spec.containers[0].image)" 2>&1

gcloud run jobs executions list \
  --job=orquestador-avalanchas \
  --region=us-central1 \
  --project=climas-chileno \
  --limit=3 \
  --format="table(name,completionTime,succeeded,failed)" 2>&1
```

Evalúa:
- ✅ Job existe, imagen reciente, última ejecución exitosa
- ⚠️ Job existe pero no hay ejecuciones recientes (>48h) o imagen con commit antiguo
- ❌ Job no existe o última ejecución falló

---

## DIMENSIÓN 6 — Calidad de datos BigQuery

Ejecuta en bash (cada query en paralelo si es posible, o secuencial):

```bash
# Tabla 1: imagenes_satelitales — frescura y nulos en NDSI
bq query --use_legacy_sql=false --project_id=climas-chileno --format=prettyjson \
'SELECT
  COUNT(*) AS total_filas,
  COUNTIF(fecha_captura >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)) AS filas_ultimas_48h,
  COUNTIF(ndsi_medio IS NULL) AS nulos_ndsi,
  ROUND(COUNTIF(ndsi_medio IS NULL) / COUNT(*) * 100, 1) AS pct_nulos_ndsi,
  MAX(fecha_captura) AS ultima_captura
FROM `climas-chileno.clima.imagenes_satelitales`' 2>&1

# Tabla 2: zonas_avalancha — frescura y nulos en pendiente
bq query --use_legacy_sql=false --project_id=climas-chileno --format=prettyjson \
'SELECT
  COUNT(*) AS total_filas,
  COUNTIF(fecha_analisis >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)) AS filas_ultimas_48h,
  COUNTIF(pendiente_media_grados IS NULL) AS nulos_pendiente,
  ROUND(COUNTIF(pendiente_media_grados IS NULL) / COUNT(*) * 100, 1) AS pct_nulos_pendiente,
  MAX(fecha_analisis) AS ultimo_analisis
FROM `climas-chileno.clima.zonas_avalancha`' 2>&1

# Tabla 3: condiciones_actuales (condiciones meteorológicas actuales) — frescura
bq query --use_legacy_sql=false --project_id=climas-chileno --format=prettyjson \
'SELECT
  COUNT(*) AS total_filas,
  COUNTIF(hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 8 HOUR)) AS filas_ultimas_8h,
  MAX(hora_actual) AS ultima_condicion,
  COUNT(DISTINCT nombre_ubicacion) AS ubicaciones_activas
FROM `climas-chileno.clima.condiciones_actuales`' 2>&1

# Tabla 4: boletines_riesgo — últimos boletines generados
bq query --use_legacy_sql=false --project_id=climas-chileno --format=prettyjson \
'SELECT
  COUNT(*) AS total_boletines,
  COUNTIF(fecha_emision >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)) AS boletines_24h,
  MAX(fecha_emision) AS ultimo_boletin,
  IF(COUNT(nivel_eaws_24h) > 0,
     CAST(APPROX_QUANTILES(nivel_eaws_24h, 2)[OFFSET(1)] AS STRING),
     "sin_datos") AS nivel_eaws_mediano
FROM `climas-chileno.clima.boletines_riesgo`' 2>&1

# Tabla 5: relatos_montanistas — verificar si existe y tiene datos
bq query --use_legacy_sql=false --project_id=climas-chileno --format=prettyjson \
'SELECT COUNT(*) AS total_relatos, MAX(fecha_actividad) AS relato_mas_reciente
FROM `climas-chileno.clima.relatos_montanistas`' 2>&1
```

Evalúa por tabla:

**imagenes_satelitales:**
- ✅ filas_ultimas_48h > 0, pct_nulos_ndsi < 20%
- ⚠️ pct_nulos_ndsi entre 20-50%, o última captura entre 48-72h
- ❌ Sin filas recientes o pct_nulos_ndsi > 50%

**zonas_avalancha:**
- ✅ total_filas > 0, pct_nulos_pendiente < 20%
- ⚠️ pct_nulos_pendiente entre 20-50%
- ❌ Sin filas o pct_nulos_pendiente > 50%

**condiciones_actuales:**
- ✅ filas_ultimas_8h > 0, ubicaciones_activas >= 5
- ⚠️ ubicaciones_activas < 5, o última condición entre 8-24h
- ❌ Sin datos en últimas 24h

**boletines_riesgo:**
- ✅ tabla existe y tiene filas (puede ser 0 boletines si es sistema nuevo)
- ⚠️ tabla existe pero boletines_24h = 0 y el sistema lleva >1 día operando
- ❌ tabla no existe (error en query)

**relatos_montanistas:**
- ✅ total_relatos >= 100
- ⚠️ total_relatos entre 1-99 (carga parcial)
- ❌ tabla no existe (FASE 1 pendiente) — esto es esperado, no bloqueante

---

## DIMENSIÓN 7 — Estructura del repositorio

Lee y verifica que existan los siguientes archivos críticos:

```
snow_alert/
├── CLAUDE.md                         ← guía de sesión
├── PROGRESO.md                       ← estado de fases
├── datos/
│   ├── desplegar.sh
│   ├── extractor/main.py
│   ├── procesador/main.py
│   ├── procesador_horas/main.py
│   ├── procesador_dias/main.py
│   ├── monitor_satelital/main.py
│   └── analizador_avalanchas/eaws_constantes.py
├── agentes/
│   ├── datos/consultor_bigquery.py
│   ├── subagentes/base_subagente.py
│   ├── subagentes/subagente_topografico/agente.py
│   ├── subagentes/subagente_satelital/agente.py
│   ├── subagentes/subagente_meteorologico/agente.py
│   ├── subagentes/subagente_nlp/agente.py
│   ├── subagentes/subagente_integrador/agente.py
│   ├── orquestador/agente_principal.py
│   ├── salidas/almacenador.py
│   ├── salidas/schema_boletines.json
│   ├── diagnostico/revisar_datos.py
│   ├── despliegue/Dockerfile
│   ├── despliegue/cloudbuild.yaml
│   ├── despliegue/job_cloud_run.yaml
│   ├── tests/test_subagentes.py
│   ├── tests/test_sistema_completo.py
│   └── tests/test_fase0_datos.py
```

Usa `Glob` para verificar existencia de cada archivo. Usa `Read` en los archivos críticos para verificar contenido específico:
- `agente_principal.py`: debe contener `SubagenteNLP` y `multi_agente_v3`
- `schema_boletines.json`: debe tener 27 campos (verificar con `len()`)
- `tool_clasificar_eaws.py`: sys.path debe usar `'../../../..'` (4 niveles, no 5)

Evalúa:
- ✅ Todos los archivos existen y contenidos críticos son correctos
- ⚠️ 1-2 archivos faltantes no críticos para la operación
- ❌ Archivos críticos ausentes (agente_principal, consultor_bigquery, eaws_constantes)

---

## DIMENSIÓN 8 — Tests unitarios

Ejecuta en bash:
```bash
cd /Users/user/Desktop/avalanche_report/snow_alert && \
python -m pytest agentes/tests/test_subagentes.py -v -k "TestTools" --tb=short -q 2>&1
```

Evalúa:
- ✅ ≥15 passed, 0 failed (los skip por Anthropic son esperados)
- ⚠️ Algunos passed pero hay 1-2 failed en TestToolsNLP o TestToolsEAWS
- ❌ Error de importación o 3+ tests fallando

---

## DIMENSIÓN 9 — Imports Python críticos

Ejecuta en bash:
```bash
cd /Users/user/Desktop/avalanche_report/snow_alert && python3 -c "
import sys, os
sys.path.insert(0, '.')
sys.path.insert(0, 'datos')

resultados = {}

# Test 1: eaws_constantes
try:
    from analizador_avalanchas.eaws_constantes import consultar_matriz_eaws, NIVELES_PELIGRO
    n, _ = consultar_matriz_eaws('poor', 'some', 2)
    resultados['eaws_constantes'] = f'OK (nivel={n})'
except Exception as e:
    resultados['eaws_constantes'] = f'ERROR: {e}'

# Test 2: consultor_bigquery (sin conexión real)
try:
    from agentes.datos.consultor_bigquery import ConsultorBigQuery
    resultados['consultor_bigquery'] = 'OK (import)'
except Exception as e:
    resultados['consultor_bigquery'] = f'ERROR: {e}'

# Test 3: orquestador (sin instanciar, solo import)
try:
    from agentes.orquestador.agente_principal import OrquestadorAvalancha
    resultados['orquestador'] = 'OK (import)'
except Exception as e:
    resultados['orquestador'] = f'ERROR: {e}'

# Test 4: subagente_nlp
try:
    from agentes.subagentes.subagente_nlp.agente import SubagenteNLP
    resultados['subagente_nlp'] = 'OK (import)'
except Exception as e:
    resultados['subagente_nlp'] = f'ERROR: {e}'

# Test 5: tool_clasificar_eaws
try:
    from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
        ejecutar_clasificar_riesgo_eaws_integrado
    )
    r = ejecutar_clasificar_riesgo_eaws_integrado('poor', 'NEVADA_RECIENTE')
    resultados['tool_clasificar_eaws'] = f'OK (nivel={r[\"nivel_eaws_24h\"]})'
except Exception as e:
    resultados['tool_clasificar_eaws'] = f'ERROR: {e}'

for k, v in resultados.items():
    print(f'  {k}: {v}')
" 2>&1
```

Evalúa:
- ✅ Todos los módulos con `OK`
- ⚠️ Error en `consultor_bigquery` (sin credenciales GCP en entorno local — puede ser esperado)
- ❌ Error en `eaws_constantes`, `orquestador`, `subagente_nlp`, o `tool_clasificar_eaws`

---

## REPORTE FINAL

Al terminar todas las verificaciones, genera el siguiente reporte con los datos reales obtenidos:

```
═══════════════════════════════════════════════════════════
REPORTE DE ESTADO — snow_alert — [FECHA/HORA ACTUAL]
═══════════════════════════════════════════════════════════

DIMENSIÓN                        ESTADO   DETALLE
─────────────────────────────────────────────────────────
1. Autenticación GCP               [✅/⚠️/❌]   [cuenta activa, proyecto]
2. Secret Manager (Claude token)   [✅/⚠️/❌]   [versiones, última fecha]
3. Cloud Functions (6)             [✅/⚠️/❌]   [N/6 activas, función con problemas si hay]
4. Cloud Scheduler (3 jobs)        [✅/⚠️/❌]   [N/3 habilitados, último éxito]
5. Cloud Run Job (orquestador)     [✅/⚠️/❌]   [existe, última ejecución]
6. Calidad datos BigQuery          [✅/⚠️/❌]   [por tabla: frescura y % nulos]
   ├─ imagenes_satelitales         [✅/⚠️/❌]   [última captura, % nulos NDSI]
   ├─ zonas_avalancha              [✅/⚠️/❌]   [última análisis, % nulos pendiente]
   ├─ condiciones_actuales         [✅/⚠️/❌]   [última condición, N ubicaciones]
   ├─ boletines_riesgo             [✅/⚠️/❌]   [total boletines, último]
   └─ relatos_montanistas          [✅/⚠️/❌]   [N relatos o "FASE 1 pendiente"]
7. Estructura repositorio          [✅/⚠️/❌]   [archivos críticos presentes]
8. Tests unitarios                 [✅/⚠️/❌]   [N passed / N failed]
9. Imports Python                  [✅/⚠️/❌]   [módulos OK o errores]

─────────────────────────────────────────────────────────
RESUMEN: N/9 dimensiones OK

ESTADO GENERAL: [OPERACIONAL / DEGRADADO / BLOQUEADO]
═══════════════════════════════════════════════════════════

ACCIONES REQUERIDAS:
[Listar solo si hay ⚠️ o ❌, con comando exacto para resolver cada una]

Ejemplo de formato de acciones:
  ❌ imagenes_satelitales sin datos recientes:
     → gcloud functions call monitor-satelital-nieve --gen2 --region=us-central1 --project=climas-chileno

  ❌ Secret claude-oauth-token no existe:
     → Obtener token: ver CLAUDE.md sección Autenticación
     → Crear secret: gcloud secrets create claude-oauth-token --project=climas-chileno
     → Añadir versión: echo -n "TOKEN" | gcloud secrets versions add claude-oauth-token --data-file=-

  ⚠️ Cloud Function extractor-clima con código >30 días:
     → cd datos && ./desplegar.sh climas-chileno us-central1

  ⚠️ relatos_montanistas vacía (FASE 1 pendiente):
     → Ver databricks/02_carga_relatos_bigquery.py para instrucciones de carga
     → Esta es la ÚNICA acción pendiente de FASE 1

  ⚠️ test_subagentes falla en TestToolsNLP:
     → Revisar agentes/subagentes/subagente_nlp/tools/
     → Ejecutar: python -m pytest agentes/tests/test_subagentes.py::TestToolsNLP -v --tb=long

PRÓXIMO PASO RECOMENDADO:
[Una sola acción concreta según el estado actual]
═══════════════════════════════════════════════════════════
```

**Criterio de ESTADO GENERAL:**
- `OPERACIONAL`: ≥7 dimensiones ✅, ninguna ❌ en dimensiones 1, 3, 8, 9
- `DEGRADADO`: 1-2 dimensiones ❌ no críticas, o 3+ dimensiones ⚠️
- `BLOQUEADO`: ❌ en autenticación (D1), imports (D9), o tests (D8)

---

## NOTAS DE CONTEXTO

Recursos del proyecto para referencia durante las verificaciones:

| Recurso | Valor |
|---------|-------|
| Proyecto GCP | `climas-chileno` |
| Cuenta GCP | `fpenailillom@correo.uss.cl` |
| Dataset BigQuery | `clima` |
| Bucket GCS | `climas-chileno-datos-clima-bronce` |
| Región | `us-central1` |
| Cloud Run Job | `orquestador-avalanchas` |
| Secret (Claude) | `claude-oauth-token` |
| Service Account | `funciones-clima-sa@climas-chileno.iam.gserviceaccount.com` |

Fases del proyecto (para contexto al interpretar resultados):
- ✅ FASE -1: Repositorio reorganizado
- ✅ FASE 0: Script diagnóstico creado
- ⬜ FASE 1: Relatos en BigQuery — requiere carga manual desde Databricks
- ✅ FASE 2: 5 subagentes construidos
- ✅ FASE 3: Archivos despliegue Cloud Run
- ✅ FASE 4: Schema boletines_riesgo 27 campos
- ✅ FASE 5: Tests actualizados

El reporte debe tomar <2 minutos de tiempo de herramientas. Si algún comando GCP tarda >15 segundos, marcarlo ⚠️ con nota "timeout" y continuar.

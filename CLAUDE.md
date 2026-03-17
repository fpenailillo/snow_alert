# CLAUDE.md — Guía para Claude Code — snow_alert

## Lectura obligatoria al inicio de cada sesión

```bash
# 1. Leer estado del proyecto
cat PROGRESO.md 2>/dev/null || echo "PROGRESO.md no existe aún"

# 2. Ver archivos Python en agentes/
find agentes/ -name "*.py" | sort 2>/dev/null | head -40

# 3. Correr tests existentes
python -m pytest agentes/tests/ -v --tb=short -q 2>/dev/null || echo "tests aún no configurados"

# 4. Reportar estado antes de escribir código
```

---

## Estructura del proyecto

```
snow_alert/
├── datos/          ← Cloud Functions GCP (NO modificar sin razón crítica)
│   ├── extractor/
│   ├── procesador/
│   ├── procesador_horas/
│   ├── procesador_dias/
│   ├── monitor_satelital/
│   ├── analizador_avalanchas/   ← eaws_constantes.py aquí
│   └── desplegar.sh
│
├── agentes/        ← Aquí trabajamos
│   ├── datos/consultor_bigquery.py     # Acceso a las 6 tablas BQ
│   ├── subagentes/base_subagente.py    # Clase base agentic loop
│   ├── subagentes/subagente_topografico/
│   ├── subagentes/subagente_satelital/
│   ├── subagentes/subagente_meteorologico/
│   ├── subagentes/subagente_nlp/       ← NUEVO (FASE 2)
│   ├── subagentes/subagente_integrador/
│   ├── orquestador/agente_principal.py
│   ├── salidas/almacenador.py
│   ├── salidas/schema_boletines.json
│   ├── diagnostico/revisar_datos.py   ← FASE 0
│   ├── despliegue/Dockerfile           ← FASE 3
│   ├── despliegue/cloudbuild.yaml
│   ├── despliegue/job_cloud_run.yaml
│   ├── scripts/generar_boletin.py
│   ├── scripts/generar_todos.py
│   └── tests/
│
├── relatos/        ← Relatos Andeshandbook
├── databricks/     ← Notebooks análisis offline
└── docs/           ← Documentación técnica
```

---

## GCP

| Recurso | Valor |
|---------|-------|
| Proyecto | `climas-chileno` |
| Cuenta | `fpenailillom@correo.uss.cl` |
| Dataset BigQuery | `clima` |
| Bucket GCS | `climas-chileno-datos-clima-bronce` |
| Service Account | `funciones-clima-sa@climas-chileno.iam.gserviceaccount.com` |
| Secret (Claude) | `claude-oauth-token` en Secret Manager |
| Cloud Run Job | `orquestador-avalanchas` en `us-central1` |

---

## Autenticación

```bash
# GCP: Application Default Credentials
gcloud auth application-default login

# Claude API
export CLAUDE_CODE_OAUTH_TOKEN="..."  # desde Secret Manager
# o
export ANTHROPIC_API_KEY="..."
```

---

## Convenciones de código

- **Todo en español**: variables, funciones, clases, comentarios, docstrings, logs, mensajes de error
- Tipo de retorno de métodos `ConsultorBigQuery`: siempre `dict`, nunca `DataFrame`
- Excepciones: `ErrorSubagente`, `ErrorOrquestador`, `ErrorConexionBigQuery`, `ErrorAlmacenamiento`
- Formato de logging: `[NombreSubagente] operación → resultado`
- Manejo explícito de nulos: nunca fallar silenciosamente, siempre documentar con `"dato_nulo": True`
- Timeout 30s por query BigQuery
- No duplicar `EAWS_MATRIX` — importar de `datos/analizador_avalanchas/eaws_constantes.py`

---

## Import path para eaws_constantes.py

Después de FASE -1, `analizador_avalanchas/` está en `datos/analizador_avalanchas/`.
En todos los archivos que lo importan usar:

```python
import sys
import os
_ROOT = os.path.join(os.path.dirname(__file__), '../../../..')  # ajustar niveles
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'datos'))
from analizador_avalanchas.eaws_constantes import consultar_matriz_eaws, NIVELES_PELIGRO
```

En Docker (`Dockerfile`), `analizador_avalanchas/` se copia a `/app/analizador_avalanchas/`
(al mismo nivel que `agentes/`), por lo que el path funciona sin `datos/`.

---

## Orden de ejecución de Fases

```
Fase -1  Organizar repositorio         ← COMPLETADO (Marzo 2026)
Fase  0  Diagnosticar datos nulos      ← agentes/diagnostico/revisar_datos.py
Fase  1  Cargar relatos (manual)       ← ver databricks/02_carga_relatos_bigquery.py
Fase  2  Construir SubagenteNLP + upgrade 4→5 subagentes
Fase  3  Archivos despliegue Cloud Run
Fase  4  Reemplazar schema_boletines.json (27 campos)
Fase  5  Tests actualizados (5 subagentes)
```

**Regla de oro: no avanzar de fase sin que los tests de la anterior pasen.**

---

## Pipeline de 5 subagentes

| # | Subagente | Tools | Output clave |
|---|-----------|-------|--------------|
| S1 | Topográfico | dem, pinn, zonas, estabilidad | `clase_estabilidad_eaws`, `frecuencia_estimada_eaws` |
| S2 | Satelital | ndsi, vit, anomalias, snowline | `alertas_satelitales`, `confianza_datos` |
| S3 | Meteorológico | condiciones, tendencia, pronostico, ventanas | `ventanas_criticas`, `alertas_meteorologicas` |
| S4 | NLP Relatos | buscar_relatos, extraer_patrones, conocimiento_historico | `indice_riesgo_historico`, `tipo_alud_predominante` |
| S5 | Integrador | clasificar_eaws, generar_boletin, explicar_factores | Boletín EAWS completo |

---

## Reglas importantes

1. **NUNCA** modificar archivos dentro de `datos/` sin confirmación explícita
2. **NUNCA** hardcodear credenciales — usar Secret Manager o variables de entorno
3. **SIEMPRE** actualizar `PROGRESO.md` al terminar cada fase
4. **SIEMPRE** hacer commit y push al terminar cada fase
5. **NUNCA** avanzar de fase sin confirmar que los tests de la anterior pasan
6. Los boletines deben tener **todas** las secciones del formato aunque falten datos
7. El nivel 72h es siempre ≥ nivel 24h (degradación conservadora de la incertidumbre)

---

## Comandos frecuentes

```bash
# Tests
cd snow_alert && python -m pytest agentes/tests/test_subagentes.py -v -k "TestTools"
python -m pytest agentes/tests/test_sistema_completo.py -v -s

# Boletín de prueba
cd agentes && python scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"

# Diagnóstico de datos
python agentes/diagnostico/revisar_datos.py

# Forzar Cloud Functions
gcloud functions call monitor-satelital-nieve --gen2 --region=us-central1
gcloud functions call analizador-satelital-zonas-riesgosas-avalanchas --gen2 --region=us-central1

# Ver boletines en BigQuery
bq query --use_legacy_sql=false \
  "SELECT nombre_ubicacion, fecha_emision, nivel_eaws_24h, confianza
   FROM climas-chileno.clima.boletines_riesgo ORDER BY fecha_emision DESC LIMIT 10"
```

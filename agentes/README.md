# Sistema Multi-Agente de Predicción de Avalanchas

Sistema basado en la API de Anthropic (Claude) que genera boletines de riesgo de avalanchas EAWS (niveles 1-5) en español, consultando datos de BigQuery desde el proyecto `climas-chileno`.

## Arquitectura

```
Prompt usuario
    │
    ▼
AgenteRiesgoAvalancha (agentic loop)
    │
    ├── analizar_terreno    → BigQuery: zonas_avalancha
    ├── monitorear_nieve    → BigQuery: imagenes_satelitales
    ├── analizar_meteorologia → BigQuery: condiciones_actuales + pronostico_*
    └── clasificar_riesgo_eaws → Matriz EAWS (eaws_constantes.py)
    │
    ▼
Boletín EAWS nivel 1-5 en español
    │
    ├── BigQuery: clima.boletines_riesgo
    └── GCS: gs://climas-chileno-datos-clima-bronce/boletines/
```

## Requisitos

- Python 3.11+
- GCP con Application Default Credentials: `gcloud auth application-default login`
- Variable de entorno `CLAUDE_CODE_OAUTH_TOKEN` (disponible automáticamente en Claude Code)
- Paquetes: `anthropic`, `google-cloud-bigquery`, `google-cloud-storage`, `pytest`

## Instalación

```bash
cd ~/Desktop/avalanche_report/snow_alert
pip install anthropic google-cloud-bigquery google-cloud-storage pytest
gcloud auth application-default login
```

## Uso

### Boletín individual

```bash
# Desde la raíz del repo (snow_alert/)
python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"

# Solo imprimir (sin guardar en BigQuery/GCS)
python agentes/scripts/generar_boletin.py --ubicacion "Valle Nevado" --solo-imprimir

# Listar ubicaciones con datos disponibles
python agentes/scripts/generar_boletin.py --listar-ubicaciones

# Salida en formato JSON
python agentes/scripts/generar_boletin.py --ubicacion "Portillo" --json
```

### Boletines masivos

```bash
# Generar para todas las ubicaciones (sin guardar)
python agentes/scripts/generar_todos.py

# Generar y guardar en BigQuery + GCS
python agentes/scripts/generar_todos.py --guardar
```

## Tests

```bash
# 1. Tests de conexión (verificar BigQuery)
python -m pytest agentes/tests/test_conexion.py -v

# 2. Tests de tools individuales
python -m pytest agentes/tests/test_tools.py -v

# 3. Test end-to-end (con salida detallada del agentic loop)
python -m pytest agentes/tests/test_boletin_completo.py -v -s
```

## Estructura de archivos

```
agentes/
├── datos/
│   └── consultor_bigquery.py      # Acceso centralizado a BigQuery (retorna dict)
├── tools/
│   ├── tool_topografico.py        # Tool 1: perfil de terreno SRTM
│   ├── tool_satelital.py          # Tool 2: estado del manto nival (satelital)
│   ├── tool_meteorologico.py      # Tool 3: condiciones y pronóstico
│   └── tool_eaws.py               # Tool 4: clasificación EAWS (lookup matrix)
├── orquestador/
│   ├── agente_principal.py        # Agentic loop con tool_use nativo
│   └── prompts.py                 # System prompt en español
├── salidas/
│   ├── almacenador.py             # Guarda en BigQuery y GCS
│   └── schema_boletines.json      # Schema tabla clima.boletines_riesgo
├── scripts/
│   ├── generar_boletin.py         # CLI por ubicación individual
│   └── generar_todos.py           # Genera boletines para todas las ubicaciones
├── tests/
│   ├── test_conexion.py
│   ├── test_tools.py
│   └── test_boletin_completo.py
└── README.md
```

## Autenticación

```python
import anthropic, os

# Dentro de Claude Code (CLAUDE_CODE_OAUTH_TOKEN disponible automáticamente)
cliente = anthropic.Anthropic(
    auth_token=os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
)

# Fuera de Claude Code (usar ANTHROPIC_API_KEY)
cliente = anthropic.Anthropic()
```

## Factores EAWS

El sistema determina 3 factores para consultar la matriz EAWS:

| Factor | Fuente |
|--------|--------|
| **Estabilidad** | Alertas dinámicas de nieve + meteorología |
| **Frecuencia** | `frecuencia_estimada_eaws` de zonas_avalancha + ajuste eólico |
| **Tamaño** | `tamano_estimado_eaws` de zonas_avalancha (estático) |

### Lógica de estabilidad dinámica

- `NEVADA_RECIENTE` o `PRECIPITACION_CRITICA` → **poor**
- `NEVADA_RECIENTE` + `FUSION_ACTIVA` → **very_poor**
- `NIEVE_HUMEDA_SAR` → **poor**
- `FUSION_ACTIVA` sola → **poor**
- Sin alertas críticas → **fair**
- Clasificación topográfica "bajo" y sin alertas → **good**

## Tabla BigQuery generada

`clima.boletines_riesgo` — particionada por `fecha_emision`:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `nombre_ubicacion` | STRING REQUIRED | Nombre de la ubicación |
| `fecha_emision` | TIMESTAMP REQUIRED | Fecha/hora de emisión |
| `nivel_eaws_24h` | INT64 | Nivel 1-5 para 24h |
| `nivel_eaws_48h` | INT64 | Nivel 1-5 para 48h |
| `nivel_eaws_72h` | INT64 | Nivel 1-5 para 72h |
| `boletin_texto` | STRING | Texto completo EAWS |
| `tools_llamadas` | STRING (JSON) | Registro del agentic loop |
| `confianza` | STRING | Alta / Media / Baja |
| `modelo` | STRING | ID del modelo usado |

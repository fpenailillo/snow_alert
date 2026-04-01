# 01 — S4: Situational Briefing Agent (reemplazo total)

**Subagente:** S4 — anteriormente "NLP / Web Scraping Mountaineer Reports"
**Tipo de cambio:** Reemplazo total
**Prioridad:** Alta (independiente, valor inmediato)
**Estimación:** 12-16 horas

---

## 1. Objetivo

Reemplazar el agente S4 actual (web scraping + sentiment analysis sobre relatos de montañistas) por un **agente generador de Situational Briefing** que produce una descripción narrativa de la zona objetivo combinando:

- Condiciones meteorológicas recientes (últimas 72h)
- Contexto histórico-climatológico de la zona
- Características topográficas relevantes para EAWS
- Patrones estacionales conocidos

El briefing alimentará a S5 (integrador EAWS) como **contexto cualitativo** para mejorar la determinación del nivel de peligro y la redacción del bulletin final.

---

## 2. Justificación del cambio

El enfoque anterior (scraping + sentiment de relatos) presenta problemas operacionales documentados:

- **Cobertura inconsistente:** los relatos no aparecen con regularidad para todas las zonas
- **Calidad heterogénea:** sesgos de quien reporta (mountaineers vs patrulleros vs turistas)
- **Latencia de información:** los relatos llegan días después del evento
- **Afecta negativamente la determinación del riesgo:** ruido > señal en la práctica

El nuevo enfoque produce un **artefacto consistente, predecible y siempre disponible** que enriquece el contexto del bulletin sin depender de fuentes externas variables.

---

## 3. Estado actual

**A revisar en el repo (Claude Code debe inspeccionar):**

- `subagents/s4_*` (estructura actual del agente NLP)
- Tabla BigQuery `clima.relatos_montanistas` o similar (verificar nombre exacto)
- Tests asociados a S4 en `tests/`
- Llamadas a S4 desde `orquestador-avalanchas` (Cloud Run Job)

---

## 4. Estado deseado

### 4.1 Nuevo módulo: `subagents/s4_situational_briefing/`

Estructura propuesta:

```
subagents/s4_situational_briefing/
├── __init__.py
├── agent.py                      # AgenteSituationalBriefing
├── tools/
│   ├── __init__.py
│   ├── tool_clima_reciente.py    # Últimas 72h desde S3
│   ├── tool_contexto_historico.py # Patrones climatológicos zona
│   ├── tool_caracteristicas_zona.py # Topografía + exposiciones críticas
│   └── tool_eventos_pasados.py   # Avalanchas históricas registradas (si existe)
├── prompts/
│   ├── system_prompt.md          # Identidad y rol del agente
│   ├── briefing_template.md      # Estructura del output
│   └── few_shot_examples.md      # 2-3 ejemplos de briefings ideales
├── schemas.py                    # Pydantic: SituationalBriefing
└── README.md
```

### 4.2 Schema de salida (Pydantic)

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class CondicionesRecientes(BaseModel):
    temperatura_promedio_72h_c: float
    precipitacion_acumulada_72h_mm: float
    viento_max_72h_kmh: float
    direccion_viento_dominante: str  # N, NE, E, SE, S, SW, W, NW
    eventos_destacables: list[str]   # ["frente frío 23/04", "ráfagas >80 km/h"]

class ContextoHistorico(BaseModel):
    epoca_estacional: Literal["pre-temporada", "temporada-temprana",
                              "mid-winter", "primavera", "fin-temporada"]
    patron_climatologico_tipico: str  # 1-2 frases
    desviacion_vs_normal: str         # "10°C sobre promedio histórico"
    eventos_historicos_relevantes: list[str]

class CaracteristicasZona(BaseModel):
    nombre_zona: str  # "La Parva", "Valle Nevado"
    altitudes_criticas_m: tuple[int, int]  # rango EAWS-relevante
    orientaciones_problematicas: list[str]
    rangos_pendiente_dominantes: list[str]  # EAWS: <30, 30-35, 35-45, 45-60, >60
    accesos_principales: list[str]

class SituationalBriefing(BaseModel):
    zona: str
    timestamp_generacion: datetime
    horizonte_validez_h: int = Field(default=24, le=72)
    condiciones_recientes: CondicionesRecientes
    contexto_historico: ContextoHistorico
    caracteristicas_zona: CaracteristicasZona
    narrativa_integrada: str = Field(
        description="Briefing en prosa, 150-300 palabras, español de Chile"
    )
    factores_atencion_eaws: list[str] = Field(
        description="Banderas de atención específicas para integrador EAWS"
    )
    confianza: Literal["alta", "media", "baja"]
    fuentes_datos: list[str]  # Trazabilidad
```

### 4.3 Modelo LLM

Usar **Qwen3-80B vía Databricks** (mismo endpoint gratuito que S5):

- Razón: endpoint gratuito ya disponible en el proyecto, sin dependencia adicional de Vertex AI ni billing extra
- Modelo: `databricks-qwen3-next-80b-a3b-instruct` vía AI Gateway Databricks
- Credenciales: `DATABRICKS_TOKEN` en Secret Manager (misma config que S5)
- Patrón: hereda `BaseSubagente` → agentic loop estándar con tools + síntesis final en texto
- No se requiere fallback separado: misma infraestructura que S5, ya validada en producción

### 4.4 Integración con orquestador

El `orquestador-avalanchas` debe:

1. Ejecutar S1, S2, S3 (en paralelo)
2. Ejecutar S4 con outputs de S3 como input
3. Pasar `SituationalBriefing` como contexto adicional a S5
4. S5 mantiene su lógica EAWS sin cambios; el briefing entra como `contexto_cualitativo` en su prompt

---

## 5. Tareas técnicas (orden de ejecución)

### Fase A: Preparación (2h)
- [ ] **A.1** Inventariar código actual de S4: archivos, tests, llamadas desde orquestador
- [ ] **A.2** Decidir estrategia: ¿deprecar carpeta antigua o reemplazar in-place? Recomendado: nueva carpeta + flag de feature en orquestador
- [ ] **A.3** Verificar tabla BigQuery `relatos_montanistas` — ¿se preserva por trazabilidad histórica o se archiva?

### Fase B: Implementación tools (4h)
- [ ] **B.1** `tool_clima_reciente.py`: query a tabla `weather_conditions` (últimas 72h por zona)
- [ ] **B.2** `tool_contexto_historico.py`: cálculo de promedios climatológicos vs valor actual
- [ ] **B.3** `tool_caracteristicas_zona.py`: lectura desde tabla `pendientes_detalladas` (cuando exista) o desde constantes hardcodeadas iniciales
- [ ] **B.4** `tool_eventos_pasados.py`: query a tabla de avalanchas históricas (si existe) o stub vacío

### Fase C: Agente y prompts (3h)
- [ ] **C.1** Redactar `system_prompt.md` con identidad, alcance y restricciones (no inventar datos, no especular fuera de evidencia)
- [ ] **C.2** Diseñar `briefing_template.md` con estructura fija EAWS-friendly
- [ ] **C.3** Generar 2-3 few-shot examples manuales (uno mid-winter, uno primavera, uno con condiciones extremas)
- [ ] **C.4** Implementar `agent.py` con `LlmAgent` de ADK o llamada directa a `vertexai.generative_models.GenerativeModel`

### Fase D: Tests (3h)
- [ ] **D.1** Test unitario por tool (mocks de BigQuery)
- [ ] **D.2** Test integración: briefing completo para La Parva y Valle Nevado con datos sintéticos
- [ ] **D.3** Test de schema: validar que output siempre cumple Pydantic
- [ ] **D.4** Test de no-alucinación: verificar que no inventa eventos no presentes en datos

### Fase E: Integración (2h)
- [ ] **E.1** Modificar `orquestador-avalanchas` para invocar nuevo S4
- [ ] **E.2** Modificar prompt de S5 para consumir `narrativa_integrada` y `factores_atencion_eaws`
- [ ] **E.3** Comparar bulletins con/sin S4 nuevo en 5 días históricos

### Fase F: Despliegue (2h)
- [ ] **F.1** Actualizar Cloud Run Job
- [ ] **F.2** Validar 3 ciclos de ejecución completos
- [ ] **F.3** Documentar en `claude/log_claude.md` y actualizar skill `snow-alert-dev`

---

## 6. Criterios de aceptación

- [ ] El briefing se genera en <10 segundos por zona
- [ ] Costo por briefing $0 (Qwen3-80B vía Databricks, endpoint gratuito)
- [ ] Schema de salida en texto validado en 100% de ejecuciones
- [ ] Tests unitarios e integración pasando (target: +15 tests nuevos)
- [ ] No-alucinación verificada: 0 datos inventados en 20 ejecuciones de prueba
- [ ] S5 consume el briefing sin romper su lógica actual
- [ ] Bulletin final mantiene o mejora coherencia comparado contra baseline (eval cualitativo con experto)
- [ ] Tabla `relatos_montanistas` archivada o documentada como "deprecated" sin pérdida de histórico

---

## 7. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|-----------|
| Qwen3 alucina eventos pasados | Media | Alto | System prompt con énfasis en "solo mencionar lo presente en tools"; test de no-alucinación |
| Briefing demasiado genérico | Media | Medio | Iterar template; incluir métricas específicas (no solo prosa) |
| Pérdida de información cualitativa de relatos | Baja | Bajo | Mantener tabla histórica para análisis posterior; relatos no fueron útiles operacionalmente |
| Databricks AI Gateway no disponible | Baja | Medio | Misma infraestructura que S5; si falla, S4 se marca degradado y pipeline continúa |
| Latencia Databricks > 10s | Baja | Bajo | MAX_ITERACIONES=8, timeout razonable; pipeline marca degradado si supera límite |

---

## 8. Referencias técnicas

- Databricks AI Gateway: `https://docs.databricks.com/aws/en/ai-gateway/index.html`
- Qwen3-80B modelo base: `https://huggingface.co/Qwen/Qwen3-80B`
- BaseSubagente (patrón interno): `agentes/subagentes/base_subagente.py`
- ClienteDatabricks (patrón interno): `agentes/datos/cliente_llm.py`
- EAWS matrix (referencia interna): skill `eaws-methodology/`

---

## 9. Notas para Claude Code

- **S4 y S5 usan el mismo endpoint Databricks**: ambos usan `databricks-qwen3-next-80b-a3b-instruct`; S4 genera el briefing de contexto, S5 determina el nivel EAWS. No hay conflicto de recursos.
- **Idempotencia:** el briefing del mismo día con mismos inputs debe producir output equivalente (temperatura LLM=0.2)
- **Trazabilidad:** persistir cada briefing en BigQuery `clima.situational_briefings` con UUID y inputs usados (auditoría académica)
- **Lengua:** todo el briefing en español de Chile, terminología EAWS estándar (no traducir términos técnicos)
- **Logging:** seguir flujo F2 de skill `snow-alert-dev`, registrar sesión en `log_claude.md`

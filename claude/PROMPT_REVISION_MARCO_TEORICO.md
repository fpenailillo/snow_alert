# Prompt 2: Revisión Marco Teórico vs Implementación
## Usar para validar que el código cumple los compromisos académicos de la tesina

---

Eres Claude Code trabajando en el proyecto **snow_alert** de Francisco Peñailillo,
tesina de Magíster en Tecnologías de la Información, Universidad Técnica Federico
Santa María, bajo supervisión del Dr. Mauricio Solar.

## Contexto académico

El sistema debe demostrar las siguientes hipótesis:

**H1 (Principal):** Un sistema multi-agente serverless que integra análisis
topográfico (SRTM), monitoreo satelital (Vision Transformers), meteorología
(Google Weather API) y conocimiento experto (NLP) puede generar pronósticos
EAWS con precisión ≥75% (F1-score macro) en horizontes 24-72h.

**H2 (Conocimiento Experto):** La incorporación de NLP sobre relatos de
montañistas mejora la precisión en >5 puntos porcentuales vs sin NLP.

**H3 (Transfer Learning):** Un modelo pre-entrenado con datos suizos SLF
supera al entrenado solo con datos chilenos escasos.

**H4 (Equiparación Humana):** El sistema alcanza ≥75% de concordancia
con pronósticos manuales de Snowlab Chile (Kappa ≥0.60).

## Tu tarea: auditoría de alineación teoría-código

Lee todos los archivos del proyecto y evalúa cada componente teórico
contra su implementación real. Sé específico: cita el archivo y la línea
de código donde se implementa cada concepto. Si algo está ausente o
incompleto, indica exactamente qué falta.

---

## Dimensión 1: Arquitectura Multi-Agente

**Marco teórico dice:**
- Arquitectura de 4+ agentes autónomos especializados
- Comunicación asíncrona con contexto compartido
- Especialización por dominio: topográfico, satelital, meteorológico, NLP, integrador
- Pipeline secuencial con retroalimentación entre agentes

**Verificar en el código:**

```bash
# ¿Cuántos subagentes están implementados?
find agentes/subagentes -name "agente.py" | sort

# ¿La clase base implementa el agentic loop correcto?
cat agentes/subagentes/base_subagente.py

# ¿El orquestador pasa contexto acumulado entre subagentes?
grep -n "contexto_previo\|contexto_acumulado" agentes/orquestador/agente_principal.py

# ¿Cada subagente tiene tools propias?
find agentes/subagentes -name "tool_*.py" | sort
```

**Evaluar:**
- [ ] ¿Existen los 5 subagentes? (topográfico, satelital, meteorológico, NLP, integrador)
- [ ] ¿Cada subagente es una instancia Claude independiente con tool_use?
- [ ] ¿El contexto se acumula y pasa correctamente de S1→S2→S3→S4→S5?
- [ ] ¿Los agentes tienen tools exclusivas por dominio?

**Brecha identificada:** [describir qué falta o está mal implementado]

---

## Dimensión 2: Physics-Informed Neural Networks (PINNs)

**Marco teórico dice:**
- PINNs integran principios físicos como restricciones en función de pérdida
- Incorporan ecuaciones de conservación de energía y mecánica del manto nival
- Modelan: gradiente térmico, densidad del manto, metamorfismo de cristales
- Reducen requerimientos de datos empíricos manteniendo consistencia física
- Variables físicas: temperatura, SWE, snow depth, gradiente térmico

**Verificar en el código:**

```bash
cat agentes/subagentes/subagente_topografico/tools/tool_calcular_pinn.py
```

**Evaluar:**
- [ ] ¿Implementa el cálculo de gradiente térmico?
  `gradiente = (lst_dia - lst_noche) / (snow_depth * 100)`
- [ ] ¿Estima la densidad del manto nival?
  `densidad = (swe_m / snow_depth_m) * 1000`
- [ ] ¿Calcula índice de metamorfismo constructivo?
- [ ] ¿Calcula probabilidad de formación de capas débiles?
- [ ] ¿Usa datos reales de BigQuery (lst_dia, lst_noche, era5_snow_depth, era5_swe)?
- [ ] ¿El output incluye: estabilidad_fisica, tipo_manto, capas_debiles_prob?

**Qué hace la implementación actual:**
[describir lo que hay]

**Qué falta para cumplir el marco teórico:**
[describir brechas]

---

## Dimensión 3: Vision Transformers (ViT)

**Marco teórico dice:**
- ViT aplica mecanismos de self-attention a datos satelitales
- Captura dependencias de largo alcance espacial y temporal
- Detecta patrones evolutivos en secuencias de imágenes satelitales
- Aplicado a: NDSI, LST, cobertura de nieve, anomalías espaciotemporales

**Verificar en el código:**

```bash
cat agentes/subagentes/subagente_satelital/tools/tool_analizar_vit.py
```

**Evaluar:**
- [ ] ¿Implementa mecanismo de atención sobre serie temporal de métricas?
- [ ] ¿La secuencia temporal incluye múltiples capturas de BigQuery?
- [ ] ¿Calcula anomaly_score comparando con distribución histórica?
- [ ] ¿Detecta patrones: nevada, fusión, estable, anómalo?
- [ ] ¿El output incluye: patron_detectado, anomalia_score?
- [ ] ¿Se documenta claramente que opera sobre métricas (no imágenes crudas)?

**Justificación académica necesaria:**
El ViT implementado opera sobre series temporales de métricas satelitales
extraídas de BigQuery. Esto es metodológicamente válido ya que:
1. Las métricas (NDSI, LST, SWE) son representaciones densas de las imágenes
2. El mecanismo de atención identifica qué capturas temporales son más relevantes
3. La literatura reciente valida ViT para series temporales multimodales

¿Está esta justificación documentada en el código (docstring)?

---

## Dimensión 4: Escala EAWS y Matriz de Decisión

**Marco teórico dice:**
- Usar Escala Europea de Peligro de Aludes (5 niveles: 1-Débil a 5-Muy Fuerte)
- Basada en 3 factores: Estabilidad, Frecuencia, Tamaño
- Implementar la matriz EAWS 2025 de Müller, Techel & Mitterer (2025)
- Generar boletines siguiendo estructura SLF/AEMET

**Verificar en el código:**

```bash
# ¿La EAWS_MATRIX está correctamente implementada?
grep -n "EAWS_MATRIX\|consultar_matriz_eaws" datos/analizador_avalanchas/eaws_constantes.py | head -20

# ¿El subagente integrador importa correctamente desde eaws_constantes?
grep -n "import\|from eaws" agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py

# ¿Los 3 factores se determinan dinámicamente?
grep -n "determinar_estabilidad\|determinar_frecuencia\|determinar_tamano" \
    agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py
```

**Evaluar:**
- [ ] ¿Se usa consultar_matriz_eaws() del módulo existente (no duplicado)?
- [ ] ¿La estabilidad se determina dinámicamente desde S1+S2+S3?
- [ ] ¿La frecuencia incluye ajuste por transporte eólico?
- [ ] ¿El tamaño usa el valor topográfico estático?
- [ ] ¿El boletín sigue la estructura SLF/AEMET con todas las secciones?
- [ ] ¿Se generan pronósticos para 24h, 48h y 72h con degradación?

---

## Dimensión 5: NLP sobre Relatos de Montañistas

**Marco teórico dice:**
- Extraer conocimiento experto de ~4.000 relatos de Andeshandbook
- NLP para identificación de patrones de riesgo
- Named Entity Recognition geográfica
- Mejora de precisión en >5pp (H2)

**Verificar en el código:**

```bash
# ¿Existe el subagente NLP?
ls agentes/subagentes/subagente_nlp/

# ¿Las tools buscan patrones relevantes?
cat agentes/subagentes/subagente_nlp/tools/tool_extraer_patrones.py

# ¿Los relatos están en BigQuery?
python3 -c "
from google.cloud import bigquery
c = bigquery.Client(project='climas-chileno')
r = list(c.query('SELECT COUNT(*) as n FROM clima.relatos_montanistas').result())[0]
print(f'Relatos en BigQuery: {r.n}')
"
```

**Evaluar:**
- [ ] ¿Existe el subagente NLP con sus tools?
- [ ] ¿`tool_extraer_patrones` busca términos EAWS relevantes?
- [ ] ¿`tool_conocimiento_historico` sintetiza patrones por ubicación?
- [ ] ¿Los relatos están cargados en `clima.relatos_montanistas`?
- [ ] ¿El output del subagente NLP incluye `indice_riesgo_historico`?

---

## Dimensión 6: Infraestructura Serverless GCP

**Marco teórico dice:**
- Arquitectura serverless event-driven escalable
- Costo operacional mínimo
- Cobertura territorial amplia (57 ubicaciones, 45 monitoreadas)
- Cloud Functions + Pub/Sub + BigQuery + Cloud Storage

**Verificar en el código:**

```bash
# ¿Cuántas ubicaciones tienen datos activos?
python3 -c "
from google.cloud import bigquery
c = bigquery.Client(project='climas-chileno')
q = '''SELECT COUNT(DISTINCT nombre_ubicacion) as n
       FROM clima.condiciones_actuales
       WHERE hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)'''
r = list(c.query(q).result())[0]
print(f'Ubicaciones activas 24h: {r.n}')
"

# ¿Los agentes se despliegan en Cloud Run Job (serverless)?
gcloud run jobs list --region=us-central1 --project=climas-chileno 2>/dev/null

# ¿El Dockerfile existe para el despliegue?
cat agentes/despliegue/Dockerfile 2>/dev/null || echo "Dockerfile pendiente"
```

**Evaluar:**
- [ ] ¿Las Cloud Functions de datos están activas?
- [ ] ¿El Cloud Run Job de agentes está desplegado?
- [ ] ¿El sistema cubre las 57 ubicaciones del proyecto?
- [ ] ¿El costo es mínimo (pago por uso, sin servidores permanentes)?

---

## Dimensión 7: Validación y Métricas

**Marco teórico dice:**
- Métrica primaria: F1-score macro por nivel EAWS
- Comparación con Snowlab Chile (Cohen's Kappa ≥0.60)
- Análisis de ablación por componente
- Validación con datos históricos SLF

**Verificar en el código:**

```bash
# ¿Existe tabla de boletines con campos para validación?
python3 -c "
from google.cloud import bigquery
c = bigquery.Client(project='climas-chileno')
try:
    t = c.get_table('climas-chileno.clima.boletines_riesgo')
    campos = [f.name for f in t.schema]
    campos_validacion = ['nivel_eaws_24h','nivel_eaws_48h','nivel_eaws_72h',
                         'estabilidad_eaws','frecuencia_eaws','tamano_eaws',
                         'confianza','datos_satelitales_ok','datos_topograficos_ok']
    for c in campos_validacion:
        estado = '✅' if c in campos else '❌'
        print(f'{estado} {c}')
except:
    print('❌ Tabla boletines_riesgo no existe aún')
"

# ¿Existen notebooks de validación?
ls notebooks/ 2>/dev/null || echo "Carpeta notebooks pendiente"
```

**Evaluar:**
- [ ] ¿La tabla `boletines_riesgo` tiene campos suficientes para calcular F1-score?
- [ ] ¿Se registra qué datos estaban disponibles (para análisis de ablación)?
- [ ] ¿Existen notebooks de comparación con Snowlab?
- [ ] ¿El sistema puede correr retrospectivamente para backtest?

---

## Reporte final de alineación

Al terminar todas las verificaciones, genera este reporte:

```
════════════════════════════════════════════════════════════════════
AUDITORÍA MARCO TEÓRICO vs IMPLEMENTACIÓN — snow_alert
Fecha: [fecha y hora]
════════════════════════════════════════════════════════════════════

RESUMEN EJECUTIVO
  Componentes implementados:     [N/7]
  Componentes parciales:         [N/7]
  Componentes pendientes:        [N/7]
  Alineación general:            [Alta / Media / Baja]

DETALLE POR COMPONENTE
┌─────────────────────────────┬──────────┬──────────────────────────────┐
│ Componente                  │ Estado   │ Brecha principal             │
├─────────────────────────────┼──────────┼──────────────────────────────┤
│ Arquitectura Multi-Agente   │ ✅⚠️❌  │                              │
│ PINNs (manto nival)         │ ✅⚠️❌  │                              │
│ Vision Transformers (ViT)   │ ✅⚠️❌  │                              │
│ Escala EAWS + Matriz        │ ✅⚠️❌  │                              │
│ NLP Relatos Montañistas     │ ✅⚠️❌  │                              │
│ Infraestructura Serverless  │ ✅⚠️❌  │                              │
│ Métricas de Validación      │ ✅⚠️❌  │                              │
└─────────────────────────────┴──────────┴──────────────────────────────┘

HALLAZGOS CRÍTICOS PARA LA TESINA
(componentes que el comité evaluador podría cuestionar)

1. [hallazgo]
   → Código actual: [qué hace]
   → Marco teórico dice: [qué debería hacer]
   → Acción recomendada: [qué cambiar o documentar]

BRECHAS JUSTIFICABLES ACADÉMICAMENTE
(diferencias entre teoría e implementación que tienen justificación válida)

1. [brecha]
   → Justificación: [por qué es válida]
   → Cómo documentarlo en la tesina: [sugerencia]

PRÓXIMAS ACCIONES PRIORITARIAS
(ordenadas por impacto en la defensa de la tesina)

1. [acción] — impacto: [Alto/Medio/Bajo]
2. [acción] — impacto: [Alto/Medio/Bajo]
3. [acción] — impacto: [Alto/Medio/Bajo]
════════════════════════════════════════════════════════════════════
```

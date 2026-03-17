# Decisiones de Diseño — Sistema Multi-Agente de Predicción de Avalanchas

> Documento de justificación académica para la defensa de tesina
> Francisco Peñailillo — Magíster TI, UTFSM — Dr. Mauricio Solar
> Última actualización: 2026-03-17

---

## Índice

1. [D1. Arquitectura Multi-Agente vs Monolítica](#d1-arquitectura-multi-agente-vs-monolítica)
2. [D2. ViT Temporal sobre Métricas Densas vs Imágenes Crudas](#d2-vit-temporal-sobre-métricas-densas)
3. [D3. PINN Analítico vs Red Neuronal Entrenada](#d3-pinn-analítico-vs-red-neuronal-entrenada)
4. [D4. Clasificación Ordinal de Capas Débiles vs Probabilidad Escalar](#d4-clasificación-ordinal-de-capas-débiles)
5. [D5. NLP como Enriquecimiento Contextual vs Factor EAWS Directo](#d5-nlp-como-enriquecimiento-contextual)
6. [D6. Frecuencia Base Topográfica con Ajuste Meteorológico](#d6-frecuencia-base-topográfica-con-ajuste-meteorológico)
7. [D7. Matriz EAWS 5×4×5 Determinista vs Modelo Probabilístico](#d7-matriz-eaws-determinista)
8. [D8. Gradiente Térmico desde LST Satelital con Fallback](#d8-gradiente-térmico-desde-lst-satelital)
9. [D9. Versionado de Prompts con SHA-256 para Reproducibilidad](#d9-versionado-de-prompts)
10. [D10. Degradación Graceful del Pipeline](#d10-degradación-graceful-del-pipeline)
11. [D11. Benchmark contra Techel et al. (2022)](#d11-benchmark-contra-techel-et-al-2022)
12. [D12. Marco Ético-Legal y Principio de Precaución](#d12-marco-ético-legal-y-principio-de-precaución)

---

## D1. Arquitectura Multi-Agente vs Monolítica

### Decisión
Cinco subagentes especializados de Claude ejecutándose en secuencia con contexto acumulado, en lugar de un único agente monolítico con todas las tools.

### Alternativas consideradas
| Opción | Ventajas | Desventajas |
|--------|----------|-------------|
| Agente monolítico | Simple, menor latencia | Ventana de contexto saturada, sin modularidad |
| Multi-agente paralelo | Menor latencia total | Sin contexto compartido entre subagentes |
| **Multi-agente secuencial** | **Contexto acumulado, modularidad, ablación** | **Mayor latencia, más costoso** |

### Justificación
- **Modularidad para ablación**: Cada subagente puede activarse/desactivarse independientemente para medir su contribución al F1-score (H2), requisito fundamental para la validación académica.
- **Especialización de prompts**: Cada subagente tiene un system prompt optimizado para su dominio (física del manto, teledetección, meteorología, NLP, integración EAWS), lo que mejora la calidad de las respuestas respecto a un prompt genérico.
- **Contexto acumulado**: El análisis del subagente N alimenta al N+1, permitiendo que el integrador final tenga una visión completa de todas las dimensiones de riesgo.
- **Trazabilidad**: Cada subagente registra sus tools llamadas, duración e iteraciones, permitiendo auditoría completa del proceso de decisión.

### Referencias
- Wooldridge, M. (2009). *An Introduction to MultiAgent Systems*. Wiley. — Arquitecturas BDI y cooperación entre agentes.
- Park et al. (2023). "Generative Agents: Interactive Simulacra of Human Behavior". — Agentes LLM especializados cooperando.

### Archivos relevantes
- `agentes/orquestador/agente_principal.py` — Orquestador secuencial
- `agentes/subagentes/base_subagente.py` — Clase base con agentic loop

---

## D2. ViT Temporal sobre Métricas Densas

### Decisión
El Vision Transformer opera sobre vectores de métricas satelitales extraídas por Google Earth Engine (NDSI, LST, cobertura nieve, ciclo diurno, delta 24h), no sobre imágenes satelitales crudas.

### Alternativas consideradas
| Opción | Ventajas | Desventajas |
|--------|----------|-------------|
| ViT sobre imágenes crudas | Fidelidad al paper original, patch embedding espacial | Requiere GPU, procesamiento pesado, datos crudos no disponibles en BQ |
| CNN sobre imágenes | Extracción de features espaciales | Requiere GPU, no captura dependencias temporales |
| **ViT temporal sobre métricas densas** | **Sin GPU, self-attention temporal, compatible con Cloud Functions** | **Sin resolución espacial intra-pixel** |

### Justificación
- **Restricción de infraestructura**: El sistema opera sobre Cloud Functions (sin GPU). Las métricas densas (NDSI, LST día/noche, cobertura %, amplitud ciclo diurno) son representaciones de alto nivel ya procesadas por Google Earth Engine, que capturan la información esencial de las imágenes originales.
- **Self-attention temporal**: El mecanismo de atención identifica qué pasos temporales (fechas) son más relevantes para el riesgo actual. Un paso con delta_nieve_24h=+25% recibirá mayor peso de atención que un paso estable. Esto es análogo al self-attention de ViT pero aplicado a la dimensión temporal en lugar de espacial.
- **Precedente académico**: Zhou et al. (2021) y Vaswani et al. (2017) demuestran que self-attention es efectivo sobre representaciones densas de features, no solo sobre patches de imagen. El enfoque es válido como "Temporal Transformer sobre representaciones densas de métricas satelitales".
- **Detección de anomalías**: El score de anomalía combina residuos de atención con estadísticas de la serie temporal, proporcionando una métrica cuantitativa de cambio anómalo en el manto nival.

### Terminología recomendada para la tesina
> "Temporal Transformer adaptado sin GPU, operando sobre representaciones densas de métricas satelitales extraídas por Google Earth Engine (NDSI, LST, cobertura nieve). El mecanismo de self-attention se aplica sobre la dimensión temporal para identificar pasos críticos de cambio en el manto nival."

### Archivos relevantes
- `agentes/subagentes/subagente_satelital/tools/tool_analizar_vit.py` — Implementación ViT temporal
- `datos/monitor_satelital/main.py` — Extracción de métricas GEE

---

## D3. PINN Analítico vs Red Neuronal Entrenada

### Decisión
La Physics-Informed Neural Network resuelve directamente las ecuaciones diferenciales del manto nival (difusión térmica, criterio Mohr-Coulomb, balance energético interfaz nieve-suelo) de forma analítica, sin entrenamiento de una red neuronal.

### Alternativas consideradas
| Opción | Ventajas | Desventajas |
|--------|----------|-------------|
| PINN entrenada (Raissi et al.) | Aprendizaje de parámetros, generalización | Requiere datos de entrenamiento, GPU, tiempo de convergencia |
| Modelo puramente estadístico | Simple, rápido | Sin fundamento físico, no interpretable |
| **PINN analítica (ecuaciones directas)** | **Determinista, interpretable, sin GPU, basada en física** | **Sin aprendizaje adaptativo** |

### Justificación
- **Interpretabilidad**: El factor de seguridad Mohr-Coulomb (FS) es directamente interpretable: FS>1.5 = estable, FS<1.0 = crítico. Esto es esencial para un sistema de alerta donde los operadores necesitan entender la base de la clasificación.
- **Fundamento físico riguroso**: Las tres ecuaciones implementadas (difusión térmica, criterio de falla por corte, balance energético) son los pilares de la mecánica del manto nival establecidos en la literatura (Schweizer et al., 2003; Jamieson & Johnston, 2001).
- **Sin datos de entrenamiento**: En Chile no existe un dataset histórico de perfiles de manto nival etiquetados como existe para los Alpes (SLF). La aproximación analítica permite operar sin datos de entrenamiento.
- **Reproducibilidad**: Al ser determinista, el mismo input produce siempre el mismo output, facilitando la verificación y auditoría académica.

### Terminología recomendada para la tesina
> "Implementación de ecuaciones diferenciales del manto nival informadas por física (Physics-Informed), incluyendo el criterio de falla Mohr-Coulomb y difusión térmica. El enfoque prioriza interpretabilidad y fundamento físico sobre aprendizaje adaptativo, dado que no existe un dataset etiquetado de perfiles de manto nival para la cordillera central chilena."

### Archivos relevantes
- `agentes/subagentes/subagente_topografico/tools/tool_calcular_pinn.py` — Motor PINN
- `agentes/subagentes/subagente_topografico/tools/tool_analizar_dem.py` — Integración con DEM y LST

---

## D4. Clasificación Ordinal de Capas Débiles

### Decisión
La probabilidad de capas débiles se expresa como clasificación ordinal (CRITICO / INESTABLE / MARGINAL / ESTABLE) en lugar de una probabilidad escalar P∈[0,1].

### Justificación
- **Alineación con EAWS**: La escala europea de peligro de avalanchas usa clasificaciones ordinales (niveles 1-5), no probabilidades continuas. La clasificación ordinal del manto se mapea directamente al eje de estabilidad de la matriz EAWS.
- **Operatividad**: Los boletines de avalanchas profesionales (SLF, AINEVA, AEMET) usan clasificaciones categóricas, no probabilidades. Un operador entiende "INESTABLE" mejor que "P=0.67".
- **Umbrales del PINN**: Los umbrales de clasificación (FS<1.0→CRITICO, 1.0-1.3→INESTABLE, 1.3-1.5→MARGINAL, >1.5→ESTABLE) están basados en la literatura de mecánica del manto nival y son directamente auditables.

### Archivos relevantes
- `agentes/subagentes/subagente_topografico/tools/tool_calcular_pinn.py:217-219` — Umbrales de clasificación

---

## D5. NLP como Enriquecimiento Contextual

### Decisión
El SubagenteNLP opera como capa de validación heurística complementaria que enriquece el contexto del integrador, no como un factor directo en la matriz EAWS.

### Alternativas consideradas
| Opción | Ventajas | Desventajas |
|--------|----------|-------------|
| NLP como factor EAWS directo | Influencia directa en nivel de peligro | Fuente subjetiva (relatos), sesgo de selección, no cuantificable en escala EAWS |
| NLP ignorado | Simplifica el pipeline | Pierde información histórica valiosa |
| **NLP como enriquecimiento** | **Valida patrones históricos sin sesgar la clasificación cuantitativa** | **Contribución indirecta, difícil de medir** |

### Justificación
- **Naturaleza de los datos**: Los relatos de montañistas son subjetivos, con sesgo de selección (se reportan más los eventos dramáticos), y no tienen la estructura cuantitativa necesaria para alimentar directamente la matriz EAWS (estabilidad × frecuencia × tamaño).
- **Valor como validación**: Si los relatos históricos mencionan frecuentemente "placas" y "viento" en una ubicación, y el análisis meteorológico actual detecta viento fuerte, el NLP refuerza la confianza en la predicción sin modificar la clasificación EAWS.
- **Diseño intencional**: Documentado en el system prompt del integrador como "contexto adicional para validar y enriquecer el análisis, no para reemplazar las métricas cuantitativas".
- **Medibilidad para H2**: Al ser un subagente independiente, su contribución se mide por ablación (F1 con NLP vs F1 sin NLP > 5pp).

### Archivos relevantes
- `agentes/subagentes/subagente_nlp/prompts.py:64` — Diseño intencional documentado
- `agentes/subagentes/subagente_integrador/prompts.py` — Integración de contexto NLP

---

## D6. Frecuencia Base Topográfica con Ajuste Meteorológico

### Decisión
La frecuencia esperada de avalanchas se determina en dos fases:
1. **Base topográfica**: Clasificación inicial desde ángulo de pendiente y orientación (S1)
2. **Ajuste meteorológico**: Viento >40 km/h incrementa la clase de frecuencia en +1, >70 km/h en +2 (C3)

### Justificación
- **Fundamento físico**: La topografía determina el potencial de generación de avalanchas (pendientes >30° son requisito necesario), mientras que la meteorología modula la frecuencia de ocurrencia en el corto plazo. Este diseño escalonado refleja la realidad física.
- **Transporte eólico**: Viento >40 km/h activa el transporte eólico de nieve (Lehning et al., 2008), formando placas de viento que aumentan la frecuencia de eventos. El umbral de 70 km/h corresponde a transporte eólico extremo documentado en la literatura alpina.
- **Extensibilidad**: El diseño permite incorporar factores adicionales (precipitación reciente, temperatura) como ajustes incrementales a la frecuencia base, sin modificar la clasificación topográfica.

### Archivos relevantes
- `agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py:272-277` — Ajuste por viento
- `datos/analizador_avalanchas/eaws_constantes.py:381-386` — Diseño escalonado documentado

---

## D7. Matriz EAWS Determinista

### Decisión
La clasificación final de peligro usa la matriz EAWS 5×4×5 (estabilidad × frecuencia × tamaño) de forma determinista, con degradación conservadora para 48h y 72h.

### Justificación
- **Estándar internacional**: La matriz EAWS es el estándar de facto para clasificación de peligro de avalanchas en Europa y progresivamente adoptado en Sudamérica. Usarla permite comparabilidad directa con boletines de otros servicios (SLF, AINEVA, AEMET).
- **Peer-reviewed**: La implementación se basa en Müller et al. (2025) y Techel et al. (2025), los trabajos más recientes sobre la formalización de la matriz de decisión EAWS.
- **Degradación conservadora**: El nivel 48h es max(nivel_24h, nivel_24h - 1) y el nivel 72h es max(nivel_48h, nivel_48h - 1), reflejando el principio de incertidumbre creciente con el horizonte temporal. Esto es una decisión de seguridad: nunca predecir peligro menor a mayor plazo sin evidencia que lo justifique.

### Archivos relevantes
- `datos/analizador_avalanchas/eaws_constantes.py` — Matriz EAWS y constantes
- `agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py` — Clasificación integrada

---

## D8. Gradiente Térmico desde LST Satelital

### Decisión
El gradiente térmico del PINN se calcula preferentemente desde datos LST satelitales reales (MODIS), con fallback a tasa adiabática estándar cuando los datos no están disponibles.

### Fuentes de gradiente (orden de prioridad)
| Prioridad | Fuente | Fórmula | Condición |
|-----------|--------|---------|-----------|
| 1 | LST + snow_depth | `(LST_día - LST_noche) / (snow_depth × 100)` | LST disponible Y snow_depth > 0.05m |
| 2 | LST + desnivel | `amplitud_diurna × 100 / desnivel` | LST disponible, sin snow_depth |
| 3 | Lapse rate estándar | `-0.65 °C/100m` | Sin datos satelitales |

### Justificación
- **Fundamentación física**: El gradiente térmico real del manto nival depende de la diferencia de temperatura entre superficie y base, no de la tasa adiabática atmosférica. Usar LST día/noche como proxy de la amplitud térmica superficial proporciona un dato medido, no asumido.
- **Fallback robusto**: El sistema nunca falla por falta de datos satelitales; degrada gracefully a la tasa estándar de -0.65°C/100m, que es la asunción estándar en la literatura.
- **Trazabilidad**: Cada boletín registra `fuente_gradiente_pinn` en BigQuery, permitiendo analizar si las predicciones con gradiente satelital son más precisas que con lapse rate (análisis de ablación).

### Archivos relevantes
- `agentes/subagentes/subagente_topografico/tools/tool_analizar_dem.py` — Cálculo del gradiente

---

## D9. Versionado de Prompts

### Decisión
Cada prompt del sistema tiene un hash SHA-256 registrado en `registro_versiones.py`. Cada boletín generado incluye la versión global de prompts usada (`version_prompts` en BigQuery).

### Justificación
- **Reproducibilidad académica**: La tesina debe poder afirmar "los boletines evaluados fueron generados con la versión v3.1 de los prompts". Sin versionado, un cambio inadvertido en un prompt invalida la comparación entre boletines.
- **Integridad verificable**: `python -m agentes.prompts.registro_versiones --verificar` confirma que ningún prompt fue modificado sin actualizar el registro. Esto es un control de calidad esencial para la reproducibilidad.
- **Auditoría por componente**: El registro detalla la versión y hash de cada uno de los 6 componentes (orquestador, topográfico, satelital, meteorológico, NLP, integrador), permitiendo identificar exactamente qué cambió entre dos conjuntos de boletines.

### Archivos relevantes
- `agentes/prompts/registro_versiones.py` — Sistema de versionado
- `agentes/orquestador/agente_principal.py` — Integración en el pipeline

---

## D10. Degradación Graceful del Pipeline

### Decisión
El SubagenteNLP es no-crítico: si falla, el pipeline continúa con los 4 subagentes restantes y produce un boletín válido con un flag `degradado=True`.

### Justificación
- **Disponibilidad**: En producción, un error transitorio en la API de Anthropic o la falta de relatos históricos no debe impedir la generación de boletines de riesgo. Los subagentes críticos (topográfico, satelital, meteorológico, integrador) son suficientes para una clasificación EAWS válida.
- **Trazabilidad de calidad**: El campo `subagentes_degradados` en el resultado permite filtrar boletines parciales en el análisis de métricas. Un boletín sin NLP no debe compararse directamente con uno completo al evaluar H2.
- **Reintentos antes de degradar**: Antes de declarar un subagente como degradado, el sistema reintenta 3 veces con backoff exponencial (2s, 4s, 8s, máximo 30s), manejando errores transitorios de rate limit y servidor.

### Archivos relevantes
- `agentes/orquestador/agente_principal.py` — Degradación graceful del NLP
- `agentes/subagentes/base_subagente.py` — Reintentos con backoff exponencial

---

## Resumen de Decisiones para la Defensa

| ID | Decisión | Brecha que cierra | Sección de tesina sugerida |
|----|----------|-------------------|---------------------------|
| D1 | Multi-agente secuencial | — | Capítulo 3: Diseño del Sistema |
| D2 | ViT temporal sobre métricas densas | B4, B8 | Capítulo 4: Metodología |
| D3 | PINN analítica sin entrenamiento | B9 | Capítulo 4: Metodología |
| D4 | Clasificación ordinal de capas débiles | B9 | Capítulo 4: Metodología |
| D5 | NLP como enriquecimiento contextual | B10 | Capítulo 3: Diseño del Sistema |
| D6 | Frecuencia base topográfica + ajuste viento | B11 | Capítulo 4: Metodología |
| D7 | Matriz EAWS determinista | — | Capítulo 4: Metodología |
| D8 | Gradiente térmico desde LST satelital | B5 | Capítulo 4: Metodología |
| D9 | Versionado de prompts SHA-256 | — | Capítulo 5: Validación |
| D10 | Degradación graceful del pipeline | — | Capítulo 3: Diseño del Sistema |
| D11 | Benchmark contra Techel et al. (2022) | H3 | Capítulo 5: Validación |
| D12 | Marco ético-legal y principio de precaución | — | Capítulo 6: Aspectos Éticos y Legales |

---

## D11. Benchmark contra Techel et al. (2022)

### Decisión
Usar Techel et al. (2022) como referencia principal para situar el rendimiento de nuestro sistema en el contexto de la literatura data-driven de predicción de avalanchas.

### Referencia
> Techel, F., Bavay, M., & Pielmeier, C. (2022). Data-driven automated predictions of the avalanche danger level for dry-snow conditions in Switzerland. *Natural Hazards and Earth System Sciences*, 22(6), 2031-2056. https://doi.org/10.5194/nhess-22-2031-2022

### Métricas de referencia (Techel 2022, modelo RF verificación)
| Métrica | Valor | Notas |
|---------|-------|-------|
| Accuracy exacta | 0.64 | 52,485 muestras, 18 inviernos |
| Accuracy adyacente (±1) | 0.95 | Operacionalmente aceptable |
| F1-macro estimado | ~0.55 | Desde Fig. 7 (niveles 1-4) |
| Quadratic Weighted Kappa | 0.59 | Concordancia "Moderada" |

### Métricas comparables implementadas
- `calcular_accuracy_adyacente()` — accuracy exacta + ±1 nivel + sesgo
- `calcular_kappa_ponderado_cuadratico()` — QWK (métrica principal de Techel)
- `comparar_con_techel_2022()` — tabla comparativa completa

### Diferencias metodológicas documentadas
1. Techel usa Random Forest con 50+ features de estaciones IMIS + modelo SNOWPACK
2. Nuestro sistema usa LLM multi-agente con datos satelitales + meteorológicos + NLP
3. Techel opera solo sobre nieve seca; nuestro sistema cubre todas las condiciones
4. Contexto geográfico diferente: Alpes suizos vs Andes centrales chilenos
5. Techel tiene 52,485 muestras; nuestro sistema es piloto

### Justificación de la comparación
- Es el paper más citado y reciente sobre predicción automatizada de niveles EAWS
- Proporciona un baseline cuantitativo para H3 (transfer learning SLF)
- La nota de interpretación advierte que la comparación directa requiere cautela por las diferencias de contexto

### Archivos relevantes
- `agentes/validacion/metricas_eaws.py` — `TECHEL_2022_REFERENCIA`, `comparar_con_techel_2022()`

---

## D12. Marco Ético-Legal y Principio de Precaución

### Decisión
El sistema se clasifica como **herramienta de apoyo a la decisión**, implementa el principio de precaución en la degradación temporal (72h ≥ 24h), e incluye un framework completo de protección de datos personales y trazabilidad ética.

### Alternativas consideradas
| Opción | Ventajas | Desventajas |
|--------|----------|-------------|
| Sistema autónomo de alerta | Respuesta inmediata sin intervención humana | Responsabilidad legal directa, riesgo de falsos negativos sin supervisión |
| Sin framework ético formal | Desarrollo más rápido | Cuestionable por comité, no cumple estándares académicos |
| **Herramienta de apoyo con framework completo** | **Responsabilidad clara, cumple Ley 21.719, principio de precaución** | **Requiere validación humana, menor automatización** |

### Justificación
- **Clasificación como herramienta de apoyo**: Evita responsabilidad directa del sistema por decisiones operativas, alineándose con la práctica de servicios profesionales de avalanchas (SLF, AINEVA, AEMET) que también clasifican sus productos como "informativos".
- **Principio de precaución**: La degradación conservadora (nivel futuro ≥ nivel actual) es una decisión ética explícita: un falso negativo (predecir seguridad cuando hay peligro) tiene consecuencias potencialmente letales, mientras que un falso positivo tiene costo económico pero no humano.
- **Protección de datos**: Cumplimiento de Ley 21.719 mediante seudonimización (hash SHA-256), minimización de datos (12 campos necesarios de relatos), y control de acceso IAM restrictivo.
- **Trazabilidad como rendición de cuentas**: Los 34 campos del boletín (incluyendo `confianza`, `subagentes_degradados`, `version_prompts`, `fuente_gradiente_pinn`) permiten auditar completamente cada predicción.

### Referencias
- Floridi, L. et al. (2018). "AI4People—An Ethical Framework for a Good AI Society". *Minds and Machines*, 28(4).
- High-Level Expert Group on AI (2019). "Ethics Guidelines for Trustworthy AI". European Commission.
- Ley 21.719 (2024). Ley sobre Protección de Datos Personales. República de Chile.
- Schweizer, J. et al. (2020). "On the relation between avalanche occurrence and avalanche danger level". *The Cryosphere*, 14.

### Archivos relevantes
- `docs/marco_etico_legal.md` — Documento completo de marco ético-legal
- `agentes/salidas/schema_boletines.json` — 34 campos de trazabilidad
- `agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py` — Degradación conservadora

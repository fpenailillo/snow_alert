# Marco Ético y Legal — Sistema de Predicción de Avalanchas con IA

> Documento para la defensa de tesina
> Francisco Peñailillo — Magíster TI, UTFSM — Dr. Mauricio Solar
> Última actualización: 2026-03-17

---

## 1. Contexto Regulatorio Chileno

### 1.1 Normativa aplicable

| Normativa | Relevancia para el sistema |
|-----------|---------------------------|
| Ley 19.628 — Protección de la Vida Privada | Datos personales de autores de relatos (nombre, actividad) |
| Ley 21.719 — Protección de Datos Personales (2024) | Actualización con estándar GDPR; consentimiento, finalidad, proporcionalidad |
| Ley 20.285 — Acceso a la Información Pública | Datos meteorológicos de fuentes públicas (DMC, DGA) |
| DS 83/2017 — Norma Técnica para Sistemas del Estado | Estándares de seguridad para sistemas de información en entidades públicas |
| Ley 20.551 — Cierre de Faenas Mineras | Contexto de seguridad en montaña para operaciones cercanas a centros de esquí |
| SERNAGEOMIN — Reglamento de Seguridad Minera | Marco de referencia para gestión de riesgos geológicos |

### 1.2 Clasificación del sistema

El sistema snow_alert se clasifica como **herramienta de apoyo a la decisión** (decision support tool), NO como sistema autónomo de alerta temprana. Esta distinción es fundamental:

- **NO reemplaza** la evaluación de expertos en terreno
- **NO genera** alertas automáticas al público
- **Produce** boletines informativos para profesionales del área
- **Requiere** validación humana antes de cualquier difusión

---

## 2. Protección de Datos Personales

### 2.1 Datos personales procesados

| Dato | Fuente | Tratamiento |
|------|--------|-------------|
| Nombre autor relato | Andeshandbook (público) | Almacenado en `relatos_montanistas.autor` |
| Ubicaciones visitadas | Andeshandbook (público) | Almacenado en `relatos_montanistas.ubicacion_mencionada` |
| Texto narrativo | Andeshandbook (público) | Almacenado en `relatos_montanistas.texto_completo` |

### 2.2 Base legal del tratamiento

- **Fuente pública**: Los relatos son publicados voluntariamente por sus autores en Andeshandbook, una plataforma pública de montañismo.
- **Finalidad legítima**: Análisis de patrones históricos de riesgo para seguridad en montaña (interés público).
- **Proporcionalidad**: Solo se almacenan los campos necesarios para el análisis NLP. No se recopilan datos de contacto, perfiles sociales, ni datos de localización en tiempo real.

### 2.3 Medidas implementadas

```
✅ datos/relatos/cargar_relatos.py:
   - Genera id_relato con hash SHA-256 (seudonimización del identificador)
   - No almacena datos de contacto del autor
   - Solo campos necesarios para análisis NLP (12 campos)
   - Deduplicación por id_relato (minimización de datos)

✅ agentes/datos/consultor_bigquery.py:
   - Consultas con LIMIT (no extracción masiva)
   - Filtros por ubicación y fecha (acceso mínimo necesario)
   - Timeout de 30s por query (prevención de exfiltración)

✅ Infraestructura GCP:
   - BigQuery con IAM restrictivo (service account dedicada)
   - Sin acceso público a las tablas
   - Logs de auditoría de Cloud Logging
```

### 2.4 Derechos del titular (Ley 21.719)

| Derecho | Implementación |
|---------|---------------|
| Acceso | Consulta SQL directa en BQ por autor |
| Rectificación | Update en tabla relatos_montanistas |
| Cancelación | DELETE FROM relatos_montanistas WHERE autor = '...' |
| Oposición | Exclusión del pipeline NLP (filtro en consultor_bigquery) |

---

## 3. Responsabilidad y Limitaciones

### 3.1 Disclaimer del sistema

Todo boletín generado DEBE incluir el siguiente disclaimer (ya implementado en el prompt del SubagenteIntegrador):

> **AVISO**: Este boletín es generado automáticamente por un sistema experimental de inteligencia artificial. No constituye una evaluación profesional de riesgo de avalanchas. Las decisiones de seguridad en montaña deben basarse en la evaluación directa de las condiciones en terreno por personal calificado. El uso de esta información es responsabilidad exclusiva del usuario.

### 3.2 Niveles de confianza y trazabilidad

El sistema implementa mecanismos de transparencia para mitigar riesgos de responsabilidad:

| Mecanismo | Campo BQ | Propósito |
|-----------|----------|-----------|
| Confianza del boletín | `confianza` (Alta/Media/Baja) | Indica fiabilidad de la predicción |
| Disponibilidad de datos | `datos_satelitales_disponibles`, `datos_topograficos_ok`, `datos_meteorologicos_ok` | Transparenta qué datos estaban disponibles |
| Subagentes degradados | `subagentes_degradados` | Indica si el análisis fue parcial |
| Versión de prompts | `version_prompts` | Trazabilidad de la versión del modelo |
| Fuente del gradiente | `fuente_gradiente_pinn` | Origen del dato físico clave |
| Duración por subagente | `duracion_por_subagente` | Detecta anomalías de procesamiento |

### 3.3 Limitaciones documentadas

1. **Sin validación en terreno**: El sistema no tiene acceso a perfiles de manto nival (snow pits), que son el estándar de oro para evaluación de estabilidad.
2. **Cobertura satelital parcial**: MODIS tiene resolución de 500m-1km; las avalanchas pueden originarse en pendientes de escala métrica.
3. **Sin datos de precipitación local**: Las estaciones meteorológicas en la cordillera central chilena son escasas; se usan datos de pronóstico (GFS/ECMWF) que tienen incertidumbre inherente.
4. **Sesgo de los relatos NLP**: Los relatos de montañistas tienen sesgo de selección (sobre-representan eventos dramáticos y condiciones adversas).
5. **Sin datos históricos de avalanchas**: Chile no tiene un registro sistemático de eventos de avalancha como el que mantiene el SLF suizo.

---

## 4. Ética de la IA en Sistemas de Seguridad

### 4.1 Principios éticos aplicados

| Principio | Implementación |
|-----------|---------------|
| **Transparencia** | Trazabilidad completa: tools llamadas, iteraciones, duración, fuentes de datos, versión de prompts |
| **Explicabilidad** | Cada boletín incluye factores explicativos (estado PINN, alertas ViT, factores meteorológicos, patrones NLP) |
| **No maleficencia** | Degradación conservadora: nivel 72h ≥ nivel 24h (nunca predice menor peligro a mayor plazo) |
| **Justicia** | Cobertura de 25 ubicaciones (no sesgo geográfico), misma metodología para todas |
| **Autonomía humana** | Sistema de apoyo, no de decisión autónoma; requiere validación humana |
| **Robustez** | Reintentos con backoff, degradación graceful, fallbacks para datos faltantes |

### 4.2 Riesgos éticos identificados y mitigaciones

| Riesgo | Severidad | Mitigación |
|--------|-----------|------------|
| Falso negativo (predice seguro, hay avalancha) | ALTA | Degradación conservadora; boletín de baja confianza siempre advierte precaución |
| Falso positivo (predice peligro, no hay avalancha) | MEDIA | Análisis F1-macro por clase para detectar sesgo; preferible a falso negativo |
| Exceso de confianza del usuario | ALTA | Disclaimer obligatorio; campo `confianza` visible; documentar limitaciones |
| Sesgo de datos (más datos de centros de esquí) | MEDIA | Monitoreo de 25 ubicaciones incluyendo zonas remotas |
| Desactualización del modelo | MEDIA | Versionado SHA-256; métricas de validación continua |

### 4.3 Principio de precaución

El sistema implementa el **principio de precaución** a nivel de diseño:

```python
# agentes/subagentes/subagente_integrador/tools/tool_clasificar_eaws.py
# El nivel 72h NUNCA es menor que el nivel 24h
nivel_72h = max(nivel_48h, nivel_48h - 1)  # Degradación conservadora
```

Esto significa que ante incertidumbre creciente con el horizonte temporal, el sistema siempre mantiene o aumenta el nivel de peligro, nunca lo reduce. Esta es una decisión ética explícita: un falso negativo (predecir seguridad cuando hay peligro) tiene consecuencias potencialmente letales, mientras que un falso positivo (predecir peligro cuando es seguro) tiene costo económico pero no humano.

---

## 5. Gobernanza de Datos

### 5.1 Arquitectura de datos

```
┌─────────────────────────────────────────────────────────┐
│                   GCP: climas-chileno                    │
│                                                          │
│  ┌──────────────────┐  ┌──────────────────┐             │
│  │ Datos públicos    │  │ Datos personales │             │
│  │ (meteorológicos,  │  │ (relatos con     │             │
│  │  satelitales,     │  │  autor)          │             │
│  │  topográficos)    │  │                  │             │
│  └────────┬─────────┘  └────────┬─────────┘             │
│           │                      │                       │
│           ▼                      ▼                       │
│  ┌──────────────────────────────────────────┐           │
│  │        Pipeline Multi-Agente              │           │
│  │  (procesamiento en memoria, sin cache)    │           │
│  └────────────────────┬─────────────────────┘           │
│                       │                                  │
│                       ▼                                  │
│  ┌──────────────────────────────────────────┐           │
│  │  BigQuery: boletines_riesgo               │           │
│  │  (sin datos personales, solo predicciones)│           │
│  └──────────────────────────────────────────┘           │
│                                                          │
│  IAM: funciones-clima-sa (service account restringida)   │
│  Audit: Cloud Logging habilitado                         │
│  Región: us-central1 (datos no salen de GCP)            │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Retención de datos

| Tabla | Retención | Justificación |
|-------|-----------|---------------|
| `condiciones_actuales` | 90 días (partición) | Solo últimas condiciones relevantes |
| `pronostico_horas` | 48 horas | Se sobrescribe con cada actualización |
| `pronostico_dias` | 7 días | Se sobrescribe con cada actualización |
| `imagenes_satelitales` | Indefinida | Datos públicos de GEE, sin información personal |
| `zonas_avalancha` | Indefinida | Datos derivados de DEM público |
| `relatos_montanistas` | Indefinida | Datos públicos de Andeshandbook |
| `boletines_riesgo` | Indefinida | Output del sistema, sin datos personales |

### 5.3 Control de acceso

```
funciones-clima-sa@climas-chileno.iam.gserviceaccount.com
  ├── BigQuery Data Editor (clima dataset)
  ├── Storage Object Admin (bucket bronce)
  ├── Secret Manager Secret Accessor (claude-oauth-token)
  └── Cloud Functions Invoker (inter-function calls)

Principio de mínimo privilegio:
  - Service account NO tiene acceso a otros datasets
  - Service account NO tiene acceso a IAM admin
  - Service account NO tiene acceso a billing
```

---

## 6. Consideraciones para la Tesina

### 6.1 Sección recomendada: "Aspectos Éticos y Legales"

La tesina debe incluir una sección dedicada que cubra:

1. **Clasificación del sistema** como herramienta de apoyo (no sistema autónomo)
2. **Tratamiento de datos personales** bajo Ley 21.719 (base legal, proporcionalidad, derechos)
3. **Disclaimer y limitaciones** del sistema (transparencia)
4. **Principio de precaución** en la degradación conservadora
5. **Trazabilidad** como mecanismo de rendición de cuentas
6. **Comparación con servicios existentes**: SLF (Suiza), AEMET (España), AINEVA (Italia) — todos usan disclaimer similares

### 6.2 Referencias académicas sugeridas

- Floridi, L. et al. (2018). "AI4People—An Ethical Framework for a Good AI Society". *Minds and Machines*, 28(4), 689-707.
- Jobin, A., Ienca, M., & Vayena, E. (2019). "The global landscape of AI ethics guidelines". *Nature Machine Intelligence*, 1(9), 389-399.
- High-Level Expert Group on AI (2019). "Ethics Guidelines for Trustworthy AI". European Commission.
- Schweizer, J. et al. (2020). "On the relation between avalanche occurrence and avalanche danger level". *The Cryosphere*, 14, 737-750. — Discute las limitaciones inherentes de la predicción de avalanchas.
- Techel, F. et al. (2022). "Data-driven automated predictions of the avalanche danger level". — Sección de limitaciones y disclaimer.

### 6.3 Preguntas anticipadas del comité

| Pregunta probable | Respuesta preparada |
|-------------------|---------------------|
| "¿Quién es responsable si el sistema predice erróneamente?" | El sistema es herramienta de apoyo; la responsabilidad recae en quien toma la decisión operativa basándose en múltiples fuentes, no solo en este sistema. El disclaimer es obligatorio. |
| "¿Cómo manejan los datos personales de los relatos?" | Fuente pública (Andeshandbook), seudonimización con hash, minimización de datos (12 campos necesarios), cumplimiento Ley 21.719. |
| "¿Qué pasa si el sistema falla?" | Degradación graceful: pipeline continúa sin subagentes fallidos; reintentos con backoff; campo `subagentes_degradados` para trazabilidad. No genera alertas falsas por falla. |
| "¿Por qué no usan datos de estaciones meteorológicas reales?" | Chile tiene escasas estaciones en alta montaña; usamos datos de pronóstico GFS/ECMWF como proxy. La limitación está documentada y el campo `datos_meteorologicos_ok` indica la disponibilidad. |
| "¿Cómo garantizan que el sistema no da una falsa sensación de seguridad?" | Degradación conservadora (72h ≥ 24h), confianza explícita (Alta/Media/Baja), disclaimer obligatorio, clasificación como herramienta de apoyo. |

---

## 7. Cumplimiento Implementado

### Checklist de cumplimiento ético-legal

- [x] Disclaimer obligatorio en cada boletín
- [x] Campo `confianza` visible en output
- [x] Degradación conservadora (principio de precaución)
- [x] Trazabilidad completa (34 campos en BQ)
- [x] Versionado de prompts para reproducibilidad
- [x] Seudonimización de identificadores (hash SHA-256)
- [x] Minimización de datos personales
- [x] Control de acceso IAM restrictivo
- [x] Service account con mínimo privilegio
- [x] Timeout en queries (prevención de exfiltración)
- [x] Documentación de limitaciones
- [ ] Consentimiento explícito de autores de relatos (no aplicable: fuente pública)
- [ ] Evaluación de impacto de datos (EIPD) formal (recomendado para producción)
- [ ] Certificación de seguridad (no requerida para sistema académico piloto)

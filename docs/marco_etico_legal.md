# Marco Ético-Legal — Sistema Multi-Agente de Predicción de Avalanchas

> **AVISO IMPORTANTE**: Este sistema es una herramienta de apoyo a la decisión y NO reemplaza
> el criterio de expertos en seguridad de montaña. Los boletines generados son orientativos.
> El usuario asume plena responsabilidad por las decisiones tomadas en terreno.

---

## 1. Principio de precaución

Ante incertidumbre, el sistema escala el nivel de riesgo EAWS al nivel superior inmediato.
El modelo prioriza la seguridad de las personas sobre la precisión del pronóstico.

Cuando los datos de entrada son insuficientes o degradados:
- Los subagentes inactivos se registran en `subagentes_degradados`
- El nivel de confianza se reduce a "Baja"
- El boletín incluye advertencias explícitas sobre las limitaciones del análisis

---

## 2. Responsabilidad

El sistema no reemplaza a guías de montaña, rescatistas ni autoridades de seguridad.
Los boletines generados deben interpretarse en conjunto con observaciones en terreno.

Responsabilidades del operador:
- Verificar que los datos de entrada (ERA5, MODIS, DEM) sean actuales y confiables
- No distribuir boletines generados con datos insuficientes sin disclaimer explícito
- Mantener un registro auditado de todos los boletines emitidos (tabla `boletines_riesgo`)

---

## 3. Protección de Datos

El sistema opera bajo los principios de la **Ley 21.719** (Ley de Protección de Datos
Personales de Chile) y el Reglamento General de Protección de Datos (GDPR) europeo en
lo que aplique a datos de meteorología y recopilación de relatos.

### 3.1 Datos tratados

| Tipo | Clasificación | Retención |
|------|---------------|-----------|
| Datos meteorológicos ERA5 | Públicos (ECMWF) | Indefinida |
| Imágenes MODIS/Sentinel | Públicos (NASA/ESA) | 90 días en bronce |
| Relatos de montañistas | Anónimos | 5 años |
| Boletines de riesgo | Internos | Indefinida |
| Logs del sistema | Internos | 30 días |

### 3.2 Ley 21.719

Los relatos de montañistas procesados por el Subagente NLP son tratados de forma anónima.
No se almacena información identificable de personas. Conforme al artículo 3° de la Ley
21.719, el titular puede solicitar acceso, rectificación o eliminación de cualquier dato
que le concierna.

---

## 4. Transparencia algorítmica

El sistema implementa:

- **Explicabilidad**: cada boletín incluye `factores_determinantes` que describen qué
  variables influyeron en el nivel EAWS asignado
- **Incertidumbre cuantificada**: el Subagente Topográfico (PINNs) reporta intervalos de
  confianza IC 95% para el Factor de Seguridad via propagación de incertidumbre Taylor
- **Auditoría**: la tabla `boletines_riesgo` en BigQuery almacena 33 campos incluyendo
  `subagentes_activos`, `subagentes_degradados`, `confianza` y `metadatos_sistema`

---

## 5. Limitaciones conocidas

| Limitación | Mitigación |
|------------|-----------|
| Sin datos satelitales recientes (<48h) | S2 entra en modo degradado; pipeline continúa |
| Sin relatos NLP para la zona | Fallback a base de conocimiento andino estático (15 zonas) |
| ERA5 tiene resolución de 9km | Downscaling topográfico con DEM SRTM 30m |
| LLM puede alucionarse | Outputs validados contra esquema JSON de 33 campos |
| Sin datos de campo (nieve) en tiempo real | Explicitado en nivel de confianza "Baja" |

---

## 6. Cumplimiento normativo

- **Ley 21.719** — Protección de datos personales (Chile, 2024)
- **ISO 31000** — Gestión de riesgo
- **EAWS 2025** — Escala Europea de Peligro de Aludes (metodología de referencia)
- **GDPR** — Reglamento europeo aplicable a datos de investigación científica

---

## 7. Decisión de diseño D12 — No-autonomía en acciones críticas

El sistema **nunca** cierra pistas, activa evacuaciones ni emite alertas oficiales de forma
autónoma. Todos los boletines son de carácter informativo y requieren validación humana
antes de ser usados como base para decisiones que afecten la seguridad pública.

Esta restricción es intencional e irrenunciable en la arquitectura del sistema.

"""
AgenteSituationalBriefing (S4 v2) — Reemplazo del SubagenteNLP.

Genera un Situational Briefing estructurado usando Gemini 2.5 Flash vía Vertex AI.
No usa el agentic loop de BaseSubagente — ejecuta tools directamente y luego
llama a Gemini con JSON structured output para producir el briefing.

Fallback: si Vertex AI falla, genera briefing textual desde los datos crudos.

Interfaz pública:
    ejecutar(nombre_ubicacion, contexto_previo) → dict compatible con orquestador
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_NOMBRE = "AgenteSituationalBriefing"
_MODELO = "gemini-2.5-flash"
_PROYECTO = "climas-chileno"
_REGION = "us-central1"
_TEMPERATURA = 0.2  # Baja para reproducibilidad (briefing idempotente)


class AgenteSituationalBriefing:
    """
    S4 v2: Genera situational briefings estructurados con Gemini 2.5 Flash.

    Patrón de ejecución (diferente a BaseSubagente):
    1. Llama directamente las 4 tools (Python, deterministas)
    2. Construye prompt con todos los datos recolectados
    3. Llama Gemini 2.5 Flash con JSON structured output
    4. Valida schema Pydantic
    5. Formatea output compatible con orquestador

    Si Gemini falla → genera briefing textual sin LLM (fallback local).
    """

    NOMBRE = _NOMBRE
    MODELO = _MODELO

    def __init__(self):
        self._system_prompt = self._cargar_system_prompt()

    def _cargar_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent / "prompts" / "system_prompt.md"
        try:
            return prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (
                "Eres un experto en nivología andina. Genera situational briefings "
                "factuales en español de Chile para el sistema AndesAI EAWS."
            )

    def ejecutar(
        self,
        nombre_ubicacion: str,
        contexto_previo: Optional[str] = None,
    ) -> dict:
        """
        Genera el situational briefing para la ubicación.

        Args:
            nombre_ubicacion: Nombre exacto de la ubicación
            contexto_previo: Contexto acumulado de S1-S3 (referencia)

        Returns:
            dict compatible con orquestador:
              analisis, tools_llamadas, iteraciones, duracion_segundos,
              timestamp, modelo, nombre_subagente, ubicacion
        """
        inicio = time.time()
        tools_llamadas = []

        logger.info(f"{_NOMBRE}: iniciando para '{nombre_ubicacion}'")

        # ── Fase 1: Recolectar datos con tools ──────────────────────────────
        datos_recolectados = self._ejecutar_tools(nombre_ubicacion, tools_llamadas)

        # ── Fase 2: Generar briefing con Gemini ─────────────────────────────
        briefing_dict = None
        try:
            briefing_dict = self._generar_con_gemini(nombre_ubicacion, datos_recolectados)
        except Exception as exc:
            logger.warning(
                f"{_NOMBRE}: Gemini falló, usando fallback local — {exc}"
            )

        # ── Fase 3: Formatear output ─────────────────────────────────────────
        if briefing_dict:
            analisis = self._formatear_analisis(briefing_dict, nombre_ubicacion)
        else:
            analisis = self._fallback_textual(nombre_ubicacion, datos_recolectados)

        duracion = round(time.time() - inicio, 1)
        logger.info(f"{_NOMBRE}: completado en {duracion}s para '{nombre_ubicacion}'")

        return {
            "nombre_subagente": _NOMBRE,
            "ubicacion": nombre_ubicacion,
            "analisis": analisis,
            "tools_llamadas": tools_llamadas,
            "iteraciones": 1,
            "duracion_segundos": duracion,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "modelo": _MODELO,
        }

    def _ejecutar_tools(self, ubicacion: str, tools_llamadas: list) -> dict:
        """Ejecuta las 4 tools y retorna los datos recolectados."""
        from agentes.subagentes.subagente_situational_briefing.tools.tool_clima_reciente import (
            obtener_clima_reciente_72h,
        )
        from agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico import (
            obtener_contexto_historico,
        )
        from agentes.subagentes.subagente_situational_briefing.tools.tool_caracteristicas_zona import (
            obtener_caracteristicas_zona,
        )
        from agentes.subagentes.subagente_situational_briefing.tools.tool_eventos_pasados import (
            obtener_eventos_pasados,
        )

        datos = {}
        tools_config = [
            ("obtener_clima_reciente_72h", obtener_clima_reciente_72h, {"ubicacion": ubicacion}),
            ("obtener_contexto_historico", obtener_contexto_historico, {"ubicacion": ubicacion}),
            ("obtener_caracteristicas_zona", obtener_caracteristicas_zona, {"ubicacion": ubicacion}),
            ("obtener_eventos_pasados", obtener_eventos_pasados, {"ubicacion": ubicacion}),
        ]

        for nombre_tool, fn, kwargs in tools_config:
            t0 = time.time()
            try:
                resultado = fn(**kwargs)
                datos[nombre_tool] = resultado
                duracion_tool = round(time.time() - t0, 2)
                logger.info(f"{_NOMBRE} ✓ {nombre_tool} en {duracion_tool}s")
                tools_llamadas.append({
                    "tool": nombre_tool,
                    "iteracion": 0,
                    "inputs": kwargs,
                    "resultado": resultado,
                    "duracion_segundos": duracion_tool,
                    "subagente": _NOMBRE,
                })
            except Exception as exc:
                logger.error(f"{_NOMBRE} ✗ {nombre_tool}: {exc}")
                datos[nombre_tool] = {"disponible": False, "error": str(exc)}
                tools_llamadas.append({
                    "tool": nombre_tool,
                    "iteracion": 0,
                    "inputs": kwargs,
                    "resultado": {"error": str(exc)},
                    "duracion_segundos": round(time.time() - t0, 2),
                    "subagente": _NOMBRE,
                })

        return datos

    def _generar_con_gemini(self, ubicacion: str, datos: dict) -> Optional[dict]:
        """
        Llama Gemini 2.5 Flash con structured output para generar el briefing.

        Returns:
            dict con el briefing estructurado, o None si falla
        """
        import vertexai
        from vertexai.generative_models import GenerativeModel, GenerationConfig

        from agentes.subagentes.subagente_situational_briefing.schemas import SituationalBriefing

        vertexai.init(project=_PROYECTO, location=_REGION)
        model = GenerativeModel(
            _MODELO,
            system_instruction=self._system_prompt,
        )

        prompt = self._construir_prompt_gemini(ubicacion, datos)

        schema = SituationalBriefing.model_json_schema()

        generation_config = GenerationConfig(
            temperature=_TEMPERATURA,
            response_mime_type="application/json",
            response_schema=schema,
        )

        logger.info(f"{_NOMBRE}: llamando Gemini 2.5 Flash para '{ubicacion}'")
        response = model.generate_content(
            prompt,
            generation_config=generation_config,
        )

        raw_text = response.text
        briefing_raw = json.loads(raw_text)

        # Validar con Pydantic
        briefing = SituationalBriefing(**briefing_raw)
        logger.info(
            f"{_NOMBRE}: briefing generado — confianza={briefing.confianza}, "
            f"factores={len(briefing.factores_atencion_eaws)}"
        )
        return briefing.model_dump()

    def _construir_prompt_gemini(self, ubicacion: str, datos: dict) -> str:
        """Construye el prompt con todos los datos recolectados para Gemini."""
        clima = datos.get("obtener_clima_reciente_72h", {})
        historico = datos.get("obtener_contexto_historico", {})
        zona = datos.get("obtener_caracteristicas_zona", {})
        eventos = datos.get("obtener_eventos_pasados", {})

        timestamp_ahora = datetime.now(timezone.utc).isoformat()

        prompt = f"""Genera un Situational Briefing para la zona: **{ubicacion}**
Timestamp de generación: {timestamp_ahora}

## Datos de entrada

### 1. Condiciones Meteorológicas Recientes (72h)
```json
{json.dumps(clima, ensure_ascii=False, indent=2, default=str)}
```

### 2. Contexto Histórico-Climatológico
```json
{json.dumps(historico, ensure_ascii=False, indent=2, default=str)}
```

### 3. Características Topográficas de la Zona
```json
{json.dumps(zona, ensure_ascii=False, indent=2, default=str)}
```

### 4. Eventos Históricos Documentados
```json
{json.dumps(eventos, ensure_ascii=False, indent=2, default=str)}
```

## Instrucciones

Basándote EXCLUSIVAMENTE en los datos anteriores (no inventes valores):

1. Completa todos los campos del schema JSON
2. La `narrativa_integrada` debe ser una descripción fluida en español de Chile, 150-300 palabras
3. Los `factores_atencion_eaws` deben ser 3-6 puntos concisos y accionables para el integrador
4. El `indice_riesgo_cualitativo` y `tipo_problema_probable` deben derivarse de las condiciones reales
5. La `confianza` debe ser "alta" si hay datos completos, "media" si hay gaps menores, "baja" si faltan datos críticos
6. Las `fuentes_datos` deben listar las fuentes BQ realmente utilizadas

IMPORTANTE: El campo `timestamp_generacion` debe ser exactamente: {timestamp_ahora}
"""
        return prompt

    def _formatear_analisis(self, briefing: dict, ubicacion: str) -> str:
        """
        Formatea el dict del briefing como texto estructurado para S5.

        El texto mantiene compatibilidad con los campos que S5 espera
        de la versión anterior del S4 NLP.
        """
        cond = briefing.get("condiciones_recientes", {})
        hist = briefing.get("contexto_historico", {})
        zona = briefing.get("caracteristicas_zona", {})
        narrativa = briefing.get("narrativa_integrada", "Sin narrativa generada.")
        factores = briefing.get("factores_atencion_eaws", [])
        confianza = briefing.get("confianza", "baja")
        indice = briefing.get("indice_riesgo_cualitativo", "sin_datos")
        tipo_problema = briefing.get("tipo_problema_probable", "sin_datos")
        fuentes = briefing.get("fuentes_datos", [])

        # Mapeo cualitativo → numérico para compatibilidad con S5
        mapeo_indice = {
            "bajo": 0.1, "moderado": 0.35, "considerable": 0.55,
            "alto": 0.75, "muy_alto": 0.9,
        }
        indice_numerico = mapeo_indice.get(indice, 0.3)

        mapeo_tipo = {
            "placa_viento": "placa",
            "nieve_reciente": "nieve_reciente",
            "nieve_humeda": "nieve_humeda",
            "avalancha_fondo": "mixto",
            "mixto": "mixto",
            "sin_datos": "sin_datos",
        }
        tipo_compatible = mapeo_tipo.get(tipo_problema, "sin_datos")

        factores_texto = "\n".join(f"  • {f}" for f in factores) if factores else "  • Sin factores identificados"

        analisis = f"""## SITUATIONAL BRIEFING — {ubicacion}
Generado por: {_NOMBRE} (Gemini 2.5 Flash) | Confianza: {confianza.upper()}

### Contexto Estacional
- Época: {hist.get('epoca_estacional', 'sin_datos')} ({hist.get('mes_actual', '')})
- Patrón típico: {hist.get('patron_climatologico_tipico', 'sin_datos')}
- Desviación vs normal: {hist.get('desviacion_vs_normal', 'sin_datos')}
- Nivel nieve estacional: {hist.get('nivel_nieve_estacional', 'sin_datos')}

### Condiciones Recientes (72h)
- Temperatura: promedio {cond.get('temperatura_promedio_c', 'N/A')}°C, min {cond.get('temperatura_min_c', 'N/A')}°C, max {cond.get('temperatura_max_c', 'N/A')}°C
- Precipitación acumulada: {cond.get('precipitacion_acumulada_mm', 0):.1f} mm
- Viento máximo: {cond.get('viento_max_kmh', 0):.0f} km/h ({cond.get('direccion_viento_dominante', 'N/A')})
- Humedad relativa: {cond.get('humedad_relativa_pct', 'N/A')}%
- Condición predominante: {cond.get('condicion_predominante', 'sin_datos')}
- Eventos destacables: {', '.join(cond.get('eventos_destacables', [])) or 'ninguno'}

### Características Topográficas
- Altitud: {zona.get('altitud_minima_m', 'N/A')}–{zona.get('altitud_maxima_m', 'N/A')} m snm
- Orientaciones críticas: {', '.join(zona.get('orientaciones_criticas', []))}
- Índice riesgo topográfico: {zona.get('indice_riesgo_topografico', 'N/A')}

### Narrativa Integrada
{narrativa}

### Factores de Atención EAWS
{factores_texto}

### Metadatos (compatibilidad S5)
- indice_riesgo_historico: {indice_numerico:.2f}
- tipo_alud_predominante: {tipo_compatible}
- total_relatos_analizados: 0
- confianza_historica: {confianza.capitalize()}
- resumen_nlp: {narrativa[:200]}...
- fuentes: {', '.join(fuentes) if fuentes else 'BigQuery clima.*'}
"""
        return analisis

    def _fallback_textual(self, ubicacion: str, datos: dict) -> str:
        """
        Genera briefing textual sin LLM cuando Gemini falla.

        Produce un texto mínimo pero funcional con los datos disponibles.
        """
        clima = datos.get("obtener_clima_reciente_72h", {})
        historico = datos.get("obtener_contexto_historico", {})
        zona = datos.get("obtener_caracteristicas_zona", {})

        temp = clima.get("temperatura_promedio_c", "N/A")
        precip = clima.get("precipitacion_acumulada_mm", 0) or 0
        viento = clima.get("viento_max_kmh", 0) or 0
        epoca = historico.get("epoca_estacional", "sin_datos")
        nivel_nieve = historico.get("nivel_nieve_estacional", "sin_datos")

        # Estimación básica de riesgo sin LLM
        indice = 0.3
        if viento > 60 or precip > 20:
            indice = 0.55
        if viento > 80 or precip > 40:
            indice = 0.75

        return f"""## SITUATIONAL BRIEFING — {ubicacion}
Generado por: {_NOMBRE} (modo fallback — sin LLM) | Confianza: BAJA

### Contexto Estacional
- Época: {epoca}
- Nivel nieve estacional estimado: {nivel_nieve}

### Condiciones Recientes (72h)
- Temperatura promedio: {temp}°C
- Precipitación acumulada: {precip:.1f} mm
- Viento máximo: {viento:.0f} km/h

### Narrativa Integrada
Briefing generado en modo fallback por indisponibilidad de Gemini.
Las condiciones para {ubicacion} muestran temperatura de {temp}°C,
precipitación acumulada de {precip:.1f} mm y viento máximo de {viento:.0f} km/h
en las últimas 72 horas, en período {epoca}.

### Metadatos (compatibilidad S5)
- indice_riesgo_historico: {indice:.2f}
- tipo_alud_predominante: sin_datos
- total_relatos_analizados: 0
- confianza_historica: Baja
- resumen_nlp: Fallback sin LLM — datos limitados disponibles
"""

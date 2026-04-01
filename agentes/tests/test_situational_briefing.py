"""
Tests para el Subagente Situational Briefing (S4 v2).

Cubre:
- Schemas Pydantic (validación)
- Tools individuales (con BQ mockeado)
- Agente completo (con Gemini mockeado)
- Fallback textual sin LLM
- Compatibilidad con interfaz del orquestador
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ── Schemas ────────────────────────────────────────────────────────────────────

class TestSchemas:
    """Valida que el schema Pydantic acepta datos válidos y rechaza inválidos."""

    def test_situational_briefing_valido(self):
        from agentes.subagentes.subagente_situational_briefing.schemas import (
            SituationalBriefing, CondicionesRecientes, ContextoHistorico, CaracteristicasZona
        )
        briefing = SituationalBriefing(
            zona="La Parva",
            timestamp_generacion=datetime.now(timezone.utc).isoformat(),
            horizonte_validez_h=24,
            condiciones_recientes=CondicionesRecientes(
                temperatura_promedio_c=-2.5,
                temperatura_min_c=-5.0,
                temperatura_max_c=1.0,
                precipitacion_acumulada_mm=15.0,
                viento_max_kmh=65.0,
                direccion_viento_dominante="NW",
                humedad_relativa_pct=85.0,
                condicion_predominante="nevando",
                eventos_destacables=["Viento fuerte 65 km/h", "Precipitación 15mm en 72h"],
            ),
            contexto_historico=ContextoHistorico(
                epoca_estacional="mid-winter",
                mes_actual="julio 2026",
                patron_climatologico_tipico="Invierno austral activo con frentes desde el Pacífico",
                desviacion_vs_normal="dentro del rango histórico",
                nivel_nieve_estacional="alto",
            ),
            caracteristicas_zona=CaracteristicasZona(
                nombre_zona="La Parva",
                altitud_minima_m=2662,
                altitud_maxima_m=3630,
                orientaciones_criticas=["S", "SE", "NE"],
                rangos_pendiente_eaws=["30-35°: ~20%", "35-45°: ~30%"],
            ),
            narrativa_integrada=(
                "La zona de La Parva se encuentra en pleno invierno austral con "
                "condiciones activas de precipitación y viento."
            ),
            factores_atencion_eaws=[
                "Viento NW cargando pendientes SE con placa de viento",
                "Temperatura bajo cero favorece nieve seca y slab frágil",
            ],
            indice_riesgo_cualitativo="considerable",
            tipo_problema_probable="placa_viento",
            confianza="alta",
            fuentes_datos=["clima.condiciones_actuales", "clima.zonas_avalancha"],
        )
        assert briefing.zona == "La Parva"
        assert briefing.confianza == "alta"
        assert len(briefing.factores_atencion_eaws) == 2

    def test_schema_json_valido(self):
        from agentes.subagentes.subagente_situational_briefing.schemas import SituationalBriefing
        schema = SituationalBriefing.model_json_schema()
        assert "properties" in schema
        assert "narrativa_integrada" in schema["properties"]
        assert "factores_atencion_eaws" in schema["properties"]
        assert "confianza" in schema["properties"]

    def test_confianza_invalida(self):
        from agentes.subagentes.subagente_situational_briefing.schemas import (
            SituationalBriefing, CondicionesRecientes, ContextoHistorico, CaracteristicasZona
        )
        with pytest.raises(Exception):
            SituationalBriefing(
                zona="La Parva",
                timestamp_generacion="2026-07-15T12:00:00",
                condiciones_recientes=CondicionesRecientes(
                    temperatura_promedio_c=0.0, temperatura_min_c=-1.0,
                    temperatura_max_c=2.0, precipitacion_acumulada_mm=0.0,
                    viento_max_kmh=20.0, direccion_viento_dominante="W",
                    humedad_relativa_pct=70.0, condicion_predominante="despejado",
                ),
                contexto_historico=ContextoHistorico(
                    epoca_estacional="mid-winter", mes_actual="julio 2026",
                    patron_climatologico_tipico="test", desviacion_vs_normal="normal",
                    nivel_nieve_estacional="normal",
                ),
                caracteristicas_zona=CaracteristicasZona(
                    nombre_zona="La Parva", altitud_minima_m=2662, altitud_maxima_m=3630,
                    orientaciones_criticas=["S"], rangos_pendiente_eaws=["35-45°"],
                ),
                narrativa_integrada="test",
                factores_atencion_eaws=["test"],
                indice_riesgo_cualitativo="considerable",
                tipo_problema_probable="placa_viento",
                confianza="invalida",  # ← debe fallar
                fuentes_datos=["test"],
            )


# ── Tool: contexto histórico ────────────────────────────────────────────────────

class TestToolContextoHistorico:
    """Tests de la tool de contexto histórico (sin dependencias externas)."""

    def test_epoca_mid_winter(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico import (
            obtener_contexto_historico
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq:
            mock_bq.return_value.obtener_condiciones_actuales.return_value = {"disponible": False}
            with patch("agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
                result = obtener_contexto_historico("La Parva")
        assert result["disponible"] is True
        assert result["epoca_estacional"] == "mid-winter"
        assert result["nivel_nieve_estacional"] == "alto"

    def test_epoca_pre_temporada(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico import (
            obtener_contexto_historico
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq:
            mock_bq.return_value.obtener_condiciones_actuales.return_value = {"disponible": False}
            with patch("agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
                result = obtener_contexto_historico("La Parva")
        assert result["epoca_estacional"] == "pre-temporada"
        assert result["nivel_nieve_estacional"] == "bajo"

    def test_desviacion_calida(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico import (
            obtener_contexto_historico
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq:
            # Julio: promedio histórico -8°C. Temperatura actual +1°C → +9°C
            mock_bq.return_value.obtener_condiciones_actuales.return_value = {
                "disponible": True, "temperatura": 1.0
            }
            with patch("agentes.subagentes.subagente_situational_briefing.tools.tool_contexto_historico.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
                result = obtener_contexto_historico("La Parva")
        assert "sobre el promedio" in result["desviacion_vs_normal"]


# ── Tool: características zona ─────────────────────────────────────────────────

class TestToolCaracteristicasZona:
    """Tests de la tool de características topográficas."""

    def test_la_parva_constantes(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_caracteristicas_zona import (
            obtener_caracteristicas_zona
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq:
            mock_bq.return_value.obtener_perfil_topografico.return_value = {"zonas": []}
            result = obtener_caracteristicas_zona("La Parva")
        assert result["disponible"] is True
        assert result["altitud_minima_m"] == 2662
        assert result["altitud_maxima_m"] == 3630
        assert "S" in result["orientaciones_criticas"] or "SE" in result["orientaciones_criticas"]

    def test_valle_nevado_constantes(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_caracteristicas_zona import (
            obtener_caracteristicas_zona
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq:
            mock_bq.return_value.obtener_perfil_topografico.return_value = {"zonas": []}
            result = obtener_caracteristicas_zona("Valle Nevado")
        assert result["altitud_minima_m"] == 3025
        assert result["altitud_maxima_m"] == 4150

    def test_enriquecimiento_bq(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_caracteristicas_zona import (
            obtener_caracteristicas_zona
        )
        zonas_mock = [
            {"indice_riesgo_topografico": 65.5, "pendiente_media_inicio": 38.0,
             "zona_inicio_ha": 2.1, "clasificacion_riesgo": "ALTO",
             "frecuencia_estimada_eaws": "some", "tamano_estimado_eaws": 3},
            {"indice_riesgo_topografico": 70.0, "pendiente_media_inicio": 42.0,
             "zona_inicio_ha": 1.5, "clasificacion_riesgo": "MUY_ALTO",
             "frecuencia_estimada_eaws": "many", "tamano_estimado_eaws": 4},
        ]
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq:
            mock_bq.return_value.obtener_perfil_topografico.return_value = {"zonas": zonas_mock}
            result = obtener_caracteristicas_zona("La Parva")
        assert result["total_zonas_bq"] == 2
        assert result["indice_riesgo_topografico"] == pytest.approx(67.75, abs=0.1)
        assert result["frecuencia_estimada_eaws"] == "many"


# ── Tool: eventos pasados ──────────────────────────────────────────────────────

class TestToolEventosPasados:
    """Tests de la tool de eventos históricos."""

    def test_la_parva_tiene_eventos(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_eventos_pasados import (
            obtener_eventos_pasados
        )
        result = obtener_eventos_pasados("La Parva")
        assert result["disponible"] is True
        assert result["total_eventos"] >= 3
        assert isinstance(result["eventos_documentados"], list)

    def test_zona_desconocida(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_eventos_pasados import (
            obtener_eventos_pasados
        )
        result = obtener_eventos_pasados("Cerro Tupungato")
        assert result["disponible"] is False
        assert result["total_eventos"] == 0


# ── Tool: clima reciente ───────────────────────────────────────────────────────

class TestToolClimaReciente:
    """Tests de la tool de clima reciente con BQ mockeado."""

    def _condicion_mock(self, **kwargs):
        base = {
            "disponible": True,
            "temperatura": -3.5,
            "velocidad_viento": 18.0,  # m/s
            "direccion_viento": 315.0,  # NW
            "precipitacion_acumulada": 25.0,
            "humedad_relativa": 88.0,
            "condicion_clima": "nevando",
        }
        base.update(kwargs)
        return base

    def test_clima_disponible(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_clima_reciente import (
            obtener_clima_reciente_72h
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = self._condicion_mock()
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            result = obtener_clima_reciente_72h("La Parva")
        assert result["disponible"] is True
        assert result["temperatura_promedio_c"] == -3.5
        assert result["viento_max_kmh"] == pytest.approx(18.0 * 3.6, abs=0.5)
        assert result["direccion_viento_dominante"] == "NW"

    def test_sin_datos_devuelve_disponible_false(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_clima_reciente import (
            obtener_clima_reciente_72h
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {"disponible": False}
            result = obtener_clima_reciente_72h("Zona Inexistente")
        assert result["disponible"] is False

    def test_viento_fuerte_genera_evento(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_clima_reciente import (
            obtener_clima_reciente_72h
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = self._condicion_mock(
                velocidad_viento=25.0  # 90 km/h → fuerte
            )
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            result = obtener_clima_reciente_72h("La Parva")
        assert any("Ráfagas" in e or "Viento" in e for e in result["eventos_destacables"])

    def test_temperatura_sobre_cero_genera_evento(self):
        from agentes.subagentes.subagente_situational_briefing.tools.tool_clima_reciente import (
            obtener_clima_reciente_72h
        )
        with patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = self._condicion_mock(temperatura=8.0)
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            result = obtener_clima_reciente_72h("La Parva")
        assert any("fusión" in e.lower() or "cero" in e.lower() for e in result["eventos_destacables"])


# ── Agente completo ───────────────────────────────────────────────────────────

class TestAgenteSituationalBriefing:
    """Tests del agente completo con cliente Databricks mockeado."""

    _BRIEFING_TEXTO = """## SITUATIONAL BRIEFING — La Parva
Generado por: AgenteSituationalBriefing (Qwen3-80B/Databricks) | Confianza: MEDIA

### Contexto Estacional
- Época: pre-temporada (abril 2026)
- Patrón típico: Otoño con nevadas esporádicas
- Desviación vs normal: dentro del rango histórico
- Nivel nieve estacional: bajo

### Condiciones Recientes (72h)
- Temperatura: promedio -2.0°C, min -5.0°C, max 1.0°C
- Precipitación acumulada: 10.0 mm
- Viento máximo: 50 km/h (NW)
- Humedad relativa: 80%
- Condición predominante: nublado
- Eventos destacables: Viento moderado

### Características Topográficas
- Altitud: 2662–3630 m snm
- Orientaciones críticas: S, SE
- Índice riesgo topográfico: sin datos BQ

### Narrativa Integrada
La zona de La Parva se encuentra en período de pre-temporada con condiciones
meteorológicas de otoño tardío. Las temperaturas se mantienen bajo cero durante
la noche y el viento NW ha sido moderado.

### Factores de Atención EAWS
- Viento NW con potencial de formación de placas en pendientes SE
- Temperatura en umbral de fusión durante horas diurnas

### Metadatos (compatibilidad S5)
- indice_riesgo_historico: 0.35
- tipo_alud_predominante: placa_viento
- total_relatos_analizados: 0
- confianza_historica: Media
- resumen_nlp: Pre-temporada con viento NW y temperatura en umbral de fusión.
- fuentes: clima.condiciones_actuales, constantes_hardcodeadas
"""

    def _crear_mock_cliente(self, briefing_texto=None):
        """Crea un mock del cliente Databricks que simula el agentic loop.

        Primera respuesta: llama las 4 tools.
        Segunda respuesta: produce el briefing final.
        """
        from agentes.datos.cliente_llm import RespuestaNormalizada, BloqueTexto, BloqueToolUse, _Usage
        from openai import RateLimitError, APIConnectionError, APIStatusError

        texto = briefing_texto or self._BRIEFING_TEXTO

        respuesta_tools = RespuestaNormalizada(
            stop_reason="tool_use",
            content=[
                BloqueToolUse(id="t1", name="obtener_clima_reciente_72h", input={"ubicacion": "La Parva"}),
                BloqueToolUse(id="t2", name="obtener_contexto_historico", input={"ubicacion": "La Parva"}),
                BloqueToolUse(id="t3", name="obtener_caracteristicas_zona", input={"ubicacion": "La Parva"}),
                BloqueToolUse(id="t4", name="obtener_eventos_pasados", input={"ubicacion": "La Parva"}),
            ],
            usage=_Usage(input_tokens=500, output_tokens=100),
        )
        respuesta_final = RespuestaNormalizada(
            stop_reason="end_turn",
            content=[BloqueTexto(text=texto)],
            usage=_Usage(input_tokens=1000, output_tokens=400),
        )

        mock_cliente = MagicMock()
        mock_cliente.errores_recuperables = (RateLimitError, APIConnectionError)
        mock_cliente.error_servidor = APIStatusError
        mock_cliente.crear_mensaje.side_effect = [respuesta_tools, respuesta_final]
        return mock_cliente

    def test_ejecutar_con_databricks_ok(self):
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing

        _BQ = "agentes.datos.consultor_bigquery.ConsultorBigQuery"
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=self._crear_mock_cliente()), \
             patch(_BQ) as mock_bq_cls:

            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {"disponible": False}
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            mock_bq.obtener_perfil_topografico.return_value = {"zonas": []}

            agente = AgenteSituationalBriefing()
            resultado = agente.ejecutar("La Parva")

        assert "analisis" in resultado
        assert "tools_llamadas" in resultado
        assert "duracion_segundos" in resultado
        assert "nombre_subagente" in resultado
        assert resultado["nombre_subagente"] == "AgenteSituationalBriefing"
        assert resultado["ubicacion"] == "La Parva"

        analisis = resultado["analisis"]
        assert "SITUATIONAL BRIEFING" in analisis
        assert "La Parva" in analisis
        assert "indice_riesgo_historico" in analisis
        assert "tipo_alud_predominante" in analisis

    def test_tools_llamadas_registradas(self):
        """Verifica que las 4 tools quedan registradas en tools_llamadas."""
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing

        _BQ = "agentes.datos.consultor_bigquery.ConsultorBigQuery"
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=self._crear_mock_cliente()), \
             patch(_BQ) as mock_bq_cls:
            mock_bq_cls.return_value.obtener_condiciones_actuales.return_value = {"disponible": False}
            mock_bq_cls.return_value.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            mock_bq_cls.return_value.obtener_perfil_topografico.return_value = {"zonas": []}

            agente = AgenteSituationalBriefing()
            resultado = agente.ejecutar("La Parva")

        tools_nombres = [t["tool"] for t in resultado["tools_llamadas"]]
        assert "obtener_clima_reciente_72h" in tools_nombres
        assert "obtener_contexto_historico" in tools_nombres
        assert "obtener_caracteristicas_zona" in tools_nombres
        assert "obtener_eventos_pasados" in tools_nombres

    def test_compatibilidad_campos_s5(self):
        """Verifica que el analisis contiene los campos que S5 espera."""
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing

        _BQ = "agentes.datos.consultor_bigquery.ConsultorBigQuery"
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=self._crear_mock_cliente()), \
             patch(_BQ) as mock_bq_cls:
            mock_bq_cls.return_value.obtener_condiciones_actuales.return_value = {"disponible": False}
            mock_bq_cls.return_value.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            mock_bq_cls.return_value.obtener_perfil_topografico.return_value = {"zonas": []}

            agente = AgenteSituationalBriefing()
            resultado = agente.ejecutar("La Parva")

        analisis = resultado["analisis"]
        assert "indice_riesgo_historico:" in analisis
        assert "tipo_alud_predominante:" in analisis
        assert "total_relatos_analizados:" in analisis
        assert "confianza_historica:" in analisis
        assert "resumen_nlp:" in analisis

    def test_proveedor_databricks(self):
        """Verifica que el agente usa Databricks, no Anthropic ni Gemini."""
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing
        assert AgenteSituationalBriefing.PROVEEDOR == "databricks"
        assert "qwen" in AgenteSituationalBriefing.MODELO.lower() or "databricks" in AgenteSituationalBriefing.MODELO.lower()

    def test_tools_definidas(self):
        """Verifica que las 4 tools están correctamente registradas."""
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=MagicMock()):
            agente = AgenteSituationalBriefing()
        tools = [t["name"] for t in agente._cargar_tools()]
        assert "obtener_clima_reciente_72h" in tools
        assert "obtener_contexto_historico" in tools
        assert "obtener_caracteristicas_zona" in tools
        assert "obtener_eventos_pasados" in tools
        ejecutores = agente._cargar_ejecutores()
        for nombre in tools:
            assert nombre in ejecutores, f"Ejecutor faltante para '{nombre}'"

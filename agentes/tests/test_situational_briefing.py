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
    """Tests del agente completo con Gemini mockeado."""

    def _briefing_gemini_mock(self, zona="La Parva") -> str:
        """JSON válido que Gemini devolvería."""
        return json.dumps({
            "zona": zona,
            "timestamp_generacion": "2026-04-25T12:00:00+00:00",
            "horizonte_validez_h": 24,
            "condiciones_recientes": {
                "temperatura_promedio_c": -2.0,
                "temperatura_min_c": -5.0,
                "temperatura_max_c": 1.0,
                "precipitacion_acumulada_mm": 10.0,
                "viento_max_kmh": 50.0,
                "direccion_viento_dominante": "NW",
                "humedad_relativa_pct": 80.0,
                "condicion_predominante": "nublado",
                "eventos_destacables": ["Viento moderado"],
            },
            "contexto_historico": {
                "epoca_estacional": "pre-temporada",
                "mes_actual": "abril 2026",
                "patron_climatologico_tipico": "Otoño con nevadas esporádicas",
                "desviacion_vs_normal": "dentro del rango histórico",
                "nivel_nieve_estacional": "bajo",
            },
            "caracteristicas_zona": {
                "nombre_zona": zona,
                "altitud_minima_m": 2662,
                "altitud_maxima_m": 3630,
                "orientaciones_criticas": ["S", "SE"],
                "rangos_pendiente_eaws": ["35-45°: ~30%"],
                "caracteristicas_especiales": [],
            },
            "narrativa_integrada": (
                "La zona de La Parva se encuentra en período de pre-temporada con "
                "condiciones meteorológicas de otoño tardío. Las temperaturas se mantienen "
                "bajo cero durante la noche y el viento NW ha sido moderado. La cobertura "
                "de nieve es baja para la época. Las orientaciones sur y sureste concentran "
                "el mayor espesor de nieve disponible."
            ),
            "factores_atencion_eaws": [
                "Viento NW con potencial de formación de placas en pendientes SE",
                "Temperatura en umbral de fusión durante horas diurnas",
            ],
            "indice_riesgo_cualitativo": "bajo",
            "tipo_problema_probable": "placa_viento",
            "confianza": "media",
            "fuentes_datos": ["clima.condiciones_actuales"],
        })

    def test_ejecutar_con_gemini_ok(self):
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing

        mock_response = MagicMock()
        mock_response.text = self._briefing_gemini_mock("La Parva")

        with patch("vertexai.init"), \
             patch("vertexai.generative_models.GenerativeModel") as mock_model_cls, \
             patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:

            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {"disponible": False}
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            mock_bq.obtener_perfil_topografico.return_value = {"zonas": []}

            mock_model = mock_model_cls.return_value
            mock_model.generate_content.return_value = mock_response

            agente = AgenteSituationalBriefing()
            resultado = agente.ejecutar("La Parva")

        # Verificar interfaz orquestador
        assert "analisis" in resultado
        assert "tools_llamadas" in resultado
        assert "duracion_segundos" in resultado
        assert "nombre_subagente" in resultado
        assert resultado["nombre_subagente"] == "AgenteSituationalBriefing"
        assert resultado["ubicacion"] == "La Parva"

        # Verificar contenido del analisis
        analisis = resultado["analisis"]
        assert "SITUATIONAL BRIEFING" in analisis
        assert "La Parva" in analisis
        assert "indice_riesgo_historico" in analisis
        assert "tipo_alud_predominante" in analisis

    def test_ejecutar_fallback_cuando_gemini_falla(self):
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing

        with patch("vertexai.init"), \
             patch("vertexai.generative_models.GenerativeModel") as mock_model_cls, \
             patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:

            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {
                "disponible": True, "temperatura": -1.0, "velocidad_viento": 10.0,
                "direccion_viento": 270.0, "precipitacion_acumulada": 5.0,
                "humedad_relativa": 75.0, "condicion_clima": "nublado",
            }
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            mock_bq.obtener_perfil_topografico.return_value = {"zonas": []}

            # Gemini falla
            mock_model_cls.return_value.generate_content.side_effect = Exception("Vertex AI timeout")

            agente = AgenteSituationalBriefing()
            resultado = agente.ejecutar("Valle Nevado")

        assert resultado["analisis"] is not None
        assert "fallback" in resultado["analisis"].lower()
        assert "SITUATIONAL BRIEFING" in resultado["analisis"]
        # Sigue devolviendo dict compatible con orquestador
        assert "tools_llamadas" in resultado
        assert isinstance(resultado["tools_llamadas"], list)

    def test_tools_llamadas_registradas(self):
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing

        mock_response = MagicMock()
        mock_response.text = self._briefing_gemini_mock("Valle Nevado")

        with patch("vertexai.init"), \
             patch("vertexai.generative_models.GenerativeModel") as mock_model_cls, \
             patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:

            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {"disponible": False}
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            mock_bq.obtener_perfil_topografico.return_value = {"zonas": []}
            mock_model_cls.return_value.generate_content.return_value = mock_response

            agente = AgenteSituationalBriefing()
            resultado = agente.ejecutar("Valle Nevado")

        tools_nombres = [t["tool"] for t in resultado["tools_llamadas"]]
        assert "obtener_clima_reciente_72h" in tools_nombres
        assert "obtener_contexto_historico" in tools_nombres
        assert "obtener_caracteristicas_zona" in tools_nombres
        assert "obtener_eventos_pasados" in tools_nombres

    def test_compatibilidad_campos_s5(self):
        """Verifica que el analisis contiene los campos que S5 espera."""
        from agentes.subagentes.subagente_situational_briefing.agente import AgenteSituationalBriefing

        mock_response = MagicMock()
        mock_response.text = self._briefing_gemini_mock()

        with patch("vertexai.init"), \
             patch("vertexai.generative_models.GenerativeModel") as mock_model_cls, \
             patch("agentes.datos.consultor_bigquery.ConsultorBigQuery") as mock_bq_cls:

            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {"disponible": False}
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}
            mock_bq.obtener_perfil_topografico.return_value = {"zonas": []}
            mock_model_cls.return_value.generate_content.return_value = mock_response

            agente = AgenteSituationalBriefing()
            resultado = agente.ejecutar("La Parva")

        analisis = resultado["analisis"]
        # Campos que S5 extrae del texto
        assert "indice_riesgo_historico:" in analisis
        assert "tipo_alud_predominante:" in analisis
        assert "total_relatos_analizados:" in analisis
        assert "confianza_historica:" in analisis
        assert "resumen_nlp:" in analisis

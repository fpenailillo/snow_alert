"""
Tests para S2 v2: vía Earth AI paralela al ViT.

Cubre:
  - DeteccionSatelital schema y adapter ViT
  - tool_gemini_multispectral: flag desactivado (default) y activado
  - ComparadorS2: modo comparación, métricas delta
  - SubagenteSatelital: 5 tools registradas, regresión S2_VIA=vit_actual
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ─── TestDeteccionSatelitalSchema ─────────────────────────────────────────────

class TestDeteccionSatelitalSchema:

    def test_instancia_minima(self):
        from agentes.subagentes.subagente_satelital.schemas import DeteccionSatelital
        d = DeteccionSatelital(
            via="vit_actual",
            zona="La Parva",
            timestamp=datetime.now(timezone.utc),
            cobertura_nieve_pct=75.0,
        )
        assert d.via == "vit_actual"
        assert d.cobertura_nieve_pct == 75.0
        assert d.anomalia_detectada is False
        assert d.cornisas_detectadas is False

    def test_to_dict_tiene_campos_clave(self):
        from agentes.subagentes.subagente_satelital.schemas import DeteccionSatelital
        d = DeteccionSatelital(
            via="gemini_multispectral",
            zona="Valle Nevado",
            timestamp=datetime.now(timezone.utc),
            cobertura_nieve_pct=60.0,
            score_anomalia=0.7,
            anomalia_detectada=True,
        )
        d_dict = d.to_dict()
        assert "via" in d_dict
        assert "cobertura_nieve_pct" in d_dict
        assert "score_anomalia" in d_dict
        assert d_dict["anomalia_detectada"] is True

    def test_desde_resultado_vit(self):
        from agentes.subagentes.subagente_satelital.schemas import DeteccionSatelital
        resultado_vit = {
            "cobertura_nieve_pct": 82.0,
            "score_anomalia": 0.55,
            "anomalia_detectada": True,
            "tipos_anomalia": ["NEVADA_RECIENTE"],
            "snowline_elevacion_m": 2800.0,
            "confianza_global": 0.8,
        }
        d = DeteccionSatelital.desde_resultado_vit("La Parva", resultado_vit)
        assert d.via == "vit_actual"
        assert d.cobertura_nieve_pct == 82.0
        assert d.anomalia_detectada is True
        assert "NEVADA_RECIENTE" in d.tipos_anomalia
        assert d.snowline_elevacion_m == 2800.0


# ─── TestToolGeminiMultispectral ──────────────────────────────────────────────

class TestToolGeminiMultispectral:

    _BQ = "agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral.ConsultorBigQuery"

    def test_retorna_via_activa_false_cuando_s2_via_vit_actual(self):
        """Con S2_VIA=vit_actual (default), debe retornar sin llamar nada."""
        from agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral import (
            ejecutar_analizar_via_earth_ai,
        )
        with patch.dict(os.environ, {"S2_VIA": "vit_actual"}):
            # Reimportar para capturar el env var actualizado
            import importlib
            import agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral as mod
            importlib.reload(mod)
            resultado = mod.ejecutar_analizar_via_earth_ai("La Parva")

        assert resultado["via_activa"] is False
        assert "activar_con" in resultado

    def test_retorna_disponible_false_sin_datos_bq(self):
        """Con datos satelitales no disponibles, retorna disponible=False."""
        from agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral import (
            ejecutar_analizar_via_earth_ai,
        )
        with patch.dict(os.environ, {"S2_VIA": "ambas_consolidar_vit"}), \
             patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_estado_satelital.return_value = {
                "disponible": False,
                "razon": "sin datos <48h",
            }
            import importlib
            import agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral as mod
            importlib.reload(mod)
            resultado = mod.ejecutar_analizar_via_earth_ai("La Parva")

        assert resultado["via_activa"] is True
        assert resultado["disponible"] is False

    def test_tool_dict_correcto(self):
        from agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral import (
            TOOL_GEMINI_MULTISPECTRAL,
        )
        assert TOOL_GEMINI_MULTISPECTRAL["name"] == "analizar_via_earth_ai"
        assert "input_schema" in TOOL_GEMINI_MULTISPECTRAL
        props = TOOL_GEMINI_MULTISPECTRAL["input_schema"]["properties"]
        assert "nombre_ubicacion" in props
        assert "contexto_vit" in props

    def test_parsear_analisis_extrae_campos(self):
        """Test del parser de respuesta LLM."""
        from agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral import (
            _parsear_analisis,
        )
        texto = """## Análisis Multi-Spectral
**Score de anomalía** (0.0-1.0): 0.75
**Anomalía detectada** (sí/no): sí
**Tipos de anomalía**: NEVADA_RECIENTE, TRANSPORTE_EOLICO
**Cobertura nieve estimada**: 85.5%
**Nieve húmeda detectada** (sí/no): no
**Wind slabs indicados** (sí/no): sí
**Cornisas posibles** (sí/no): no

## Descripción cualitativa
Las señales NDSI elevadas combinadas con viento activo indican transporte de nieve reciente.

## Factores de riesgo EAWS observados
- TRANSPORTE_EOLICO_ACTIVO
- NEVADA_24H

## Confianza global (0.0-1.0): 0.80"""

        estado_sat = {"sar_pct_nieve_humeda": 15.0}
        resultado = _parsear_analisis(texto, estado_sat)

        assert resultado["score_anomalia"] == pytest.approx(0.75)
        assert resultado["anomalia_detectada"] is True
        assert "NEVADA_RECIENTE" in resultado["tipos_anomalia"]
        assert resultado["cobertura_nieve_pct"] == pytest.approx(85.5)
        assert resultado["wind_slabs_indicados"] is True
        assert resultado["cornisas_detectadas"] is False
        assert len(resultado["factores_riesgo_observados"]) >= 1
        assert resultado["confianza_global"] == pytest.approx(0.80)


# ─── TestComparadorS2 ─────────────────────────────────────────────────────────

class TestComparadorS2:

    def _crear_resultado_vit(self, score=0.5, anomalia=True):
        return {
            "disponible": True,
            "score_anomalia": score,
            "anomalia_detectada": anomalia,
            "cobertura_nieve_pct": 70.0,
            "latencia_ms": 100.0,
            "confianza_global": 0.7,
        }

    def _crear_resultado_ea(self, score=0.6, anomalia=True, disponible=True):
        return {
            "disponible": disponible,
            "via_activa": True,
            "score_anomalia": score,
            "anomalia_detectada": anomalia,
            "cobertura_nieve_pct": 72.0,
            "latencia_ms": 300.0,
            "confianza_global": 0.65,
        }

    def test_sin_comparacion_retorna_vit(self):
        with patch.dict(os.environ, {"S2_VIA": "vit_actual"}):
            from agentes.subagentes.subagente_satelital.comparador.ab_runner import ComparadorS2
            comparador = ComparadorS2()

        assert not comparador.modo_comparacion
        resultado = comparador.ejecutar_y_comparar(
            self._crear_resultado_vit(), self._crear_resultado_ea(), "La Parva"
        )
        assert resultado["comparacion_activa"] is False
        assert resultado["via_usada"] == "vit_actual"

    def test_modo_ambas_calcula_metricas(self):
        with patch.dict(os.environ, {"S2_VIA": "ambas_consolidar_vit"}):
            from agentes.subagentes.subagente_satelital.comparador.ab_runner import ComparadorS2
            comparador = ComparadorS2()

        assert comparador.modo_comparacion
        assert comparador.via_primaria == "vit_actual"

        with patch.object(comparador, "_persistir_comparacion_async"):
            resultado = comparador.ejecutar_y_comparar(
                self._crear_resultado_vit(score=0.5),
                self._crear_resultado_ea(score=0.7),
                "La Parva",
            )

        assert resultado["comparacion_activa"] is True
        assert resultado["via_usada"] == "vit_actual"
        metricas = resultado["metricas_comparacion"]
        assert "delta_score_anomalia" in metricas
        assert abs(metricas["delta_score_anomalia"] - 0.2) < 0.001

    def test_modo_ambas_consolidar_ea_usa_earth_ai(self):
        with patch.dict(os.environ, {"S2_VIA": "ambas_consolidar_ea"}):
            from agentes.subagentes.subagente_satelital.comparador.ab_runner import ComparadorS2
            comparador = ComparadorS2()

        assert comparador.via_primaria == "earth_ai"

        with patch.object(comparador, "_persistir_comparacion_async"):
            resultado = comparador.ejecutar_y_comparar(
                self._crear_resultado_vit(),
                self._crear_resultado_ea(),
                "Valle Nevado",
            )

        assert resultado["via_usada"] == "earth_ai"
        assert resultado["output_para_s5"] is not None

    def test_metricas_acuerdo_anomalia(self):
        with patch.dict(os.environ, {"S2_VIA": "ambas_consolidar_vit"}):
            from agentes.subagentes.subagente_satelital.comparador.ab_runner import ComparadorS2
            comparador = ComparadorS2()

        metricas_acuerdo = comparador._calcular_metricas(
            self._crear_resultado_vit(anomalia=True),
            self._crear_resultado_ea(anomalia=True),
        )
        assert metricas_acuerdo["acuerdo_anomalia"] is True

        metricas_desacuerdo = comparador._calcular_metricas(
            self._crear_resultado_vit(anomalia=True),
            self._crear_resultado_ea(anomalia=False),
        )
        assert metricas_desacuerdo["acuerdo_anomalia"] is False

    def test_ea_no_disponible_fallback_a_vit(self):
        """Si Earth AI no está disponible, usar ViT aunque via_primaria=ea."""
        with patch.dict(os.environ, {"S2_VIA": "ambas_consolidar_ea"}):
            from agentes.subagentes.subagente_satelital.comparador.ab_runner import ComparadorS2
            comparador = ComparadorS2()

        ea_sin_datos = self._crear_resultado_ea(disponible=False)
        with patch.object(comparador, "_persistir_comparacion_async"):
            resultado = comparador.ejecutar_y_comparar(
                self._crear_resultado_vit(),
                ea_sin_datos,
                "La Parva",
            )

        assert resultado["output_para_s5"] is not None


# ─── TestSubagenteSatelitalV2 ─────────────────────────────────────────────────

class TestSubagenteSatelitalV2:

    def test_seis_tools_registradas(self):
        """S2 ahora tiene 6 tools (REQ-02a agrega consultar_estado_manto)."""
        from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=MagicMock()):
            agente = SubagenteSatelital()
        tools = [t["name"] for t in agente._cargar_tools()]
        assert len(tools) == 6
        assert "consultar_estado_manto" in tools
        assert "procesar_ndsi" in tools
        assert "analizar_vit" in tools
        assert "detectar_anomalias_satelitales" in tools
        assert "calcular_snowline" in tools
        assert "analizar_via_earth_ai" in tools

    def test_todos_ejecutores_presentes(self):
        from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=MagicMock()):
            agente = SubagenteSatelital()
        tools = [t["name"] for t in agente._cargar_tools()]
        ejecutores = agente._cargar_ejecutores()
        for nombre in tools:
            assert nombre in ejecutores, f"Ejecutor faltante para '{nombre}'"

    def test_regresion_s2_via_vit_actual(self):
        """Con S2_VIA=vit_actual, analizar_via_earth_ai retorna via_activa=False."""
        import importlib
        with patch.dict(os.environ, {"S2_VIA": "vit_actual"}):
            import agentes.subagentes.subagente_satelital.tools.tool_gemini_multispectral as mod
            importlib.reload(mod)
            resultado = mod.ejecutar_analizar_via_earth_ai("La Parva")
        assert resultado["via_activa"] is False

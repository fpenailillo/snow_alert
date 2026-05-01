"""
Tests para REQ-02a — Feature de estado del manto (MODIS LST + ERA5 suelo) en S2.

Cubre:
- ConsultorBigQuery.obtener_estado_manto: estructura, manto_frio, dias_lst_positivo, error BQ
- tool_estado_manto: interpretaciones, degradación graceful, activación térmica
- SubagenteSatelital: tool registrada en primer lugar
- Constraint crítico: sin datos no interrumpe el flujo satelital
"""

import pytest
from unittest.mock import MagicMock, patch


# ── Tests ConsultorBigQuery.obtener_estado_manto ──────────────────────────────

class TestObtenerEstadoManto:

    def _mock_consultor(self, filas):
        """Crea un ConsultorBigQuery con BQ mockeado."""
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(return_value=filas)
        return consultor

    def test_sin_datos_retorna_estructura_segura(self):
        consultor = self._mock_consultor([])
        resultado = consultor.obtener_estado_manto("La Parva Sector Bajo", n_dias=7)

        assert resultado["disponible"] is False
        assert resultado["sin_datos"] is True
        assert resultado["lst_celsius_medio_7d"] is None
        assert resultado["dias_lst_positivo"] == 0
        assert resultado["gradiente_termico_medio"] is None

    def test_manto_frio_cuando_lst_bajo_cero(self):
        filas = [
            {"fecha": "2026-04-30", "lst_celsius": -8.5, "temp_suelo_l1_celsius": -2.0,
             "temp_suelo_l2_celsius": -1.0, "gradiente_termico": -1.0,
             "cobertura_nubosa_pct": 0.0, "fuente_lst": "MOD11A1"},
            {"fecha": "2026-04-29", "lst_celsius": -7.0, "temp_suelo_l1_celsius": -1.5,
             "temp_suelo_l2_celsius": -0.5, "gradiente_termico": -1.0,
             "cobertura_nubosa_pct": 0.0, "fuente_lst": "MOD11A1"},
            {"fecha": "2026-04-28", "lst_celsius": -9.1, "temp_suelo_l1_celsius": -3.0,
             "temp_suelo_l2_celsius": -1.0, "gradiente_termico": -2.0,
             "cobertura_nubosa_pct": 0.0, "fuente_lst": "MOD11A1"},
        ]
        consultor = self._mock_consultor(filas)
        resultado = consultor.obtener_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is True
        assert resultado["manto_frio"] is True
        lst_medio = resultado["lst_celsius_medio_7d"]
        assert lst_medio < -3.0
        assert resultado["dias_lst_positivo"] == 0  # todos negativos

    def test_dias_lst_positivo_consecutivos_correcto(self):
        filas = [
            {"fecha": "2026-04-30", "lst_celsius": 1.2, "temp_suelo_l1_celsius": 0.5,
             "temp_suelo_l2_celsius": 1.0, "gradiente_termico": -0.5,
             "cobertura_nubosa_pct": 10.0, "fuente_lst": "MOD11A1"},
            {"fecha": "2026-04-29", "lst_celsius": 0.8, "temp_suelo_l1_celsius": 0.3,
             "temp_suelo_l2_celsius": 0.8, "gradiente_termico": -0.5,
             "cobertura_nubosa_pct": 5.0, "fuente_lst": "MOD11A1"},
            {"fecha": "2026-04-28", "lst_celsius": -1.5, "temp_suelo_l1_celsius": -0.5,
             "temp_suelo_l2_celsius": 0.0, "gradiente_termico": -0.5,
             "cobertura_nubosa_pct": 0.0, "fuente_lst": "MOD11A1"},
        ]
        consultor = self._mock_consultor(filas)
        resultado = consultor.obtener_estado_manto("La Parva Sector Bajo")

        # Solo los 2 primeros días (más recientes) son positivos
        assert resultado["dias_lst_positivo"] == 2

    def test_gradiente_termico_medio_calculado(self):
        filas = [
            {"fecha": "2026-04-30", "lst_celsius": -5.0, "temp_suelo_l1_celsius": -3.0,
             "temp_suelo_l2_celsius": -1.0, "gradiente_termico": -2.0,
             "cobertura_nubosa_pct": 0.0, "fuente_lst": "MOD11A1"},
            {"fecha": "2026-04-29", "lst_celsius": -4.5, "temp_suelo_l1_celsius": -2.5,
             "temp_suelo_l2_celsius": -0.5, "gradiente_termico": -2.0,
             "cobertura_nubosa_pct": 0.0, "fuente_lst": "MOD11A1"},
        ]
        consultor = self._mock_consultor(filas)
        resultado = consultor.obtener_estado_manto("La Parva Sector Bajo")

        assert resultado["gradiente_termico_medio"] == pytest.approx(-2.0, abs=0.01)
        assert resultado["metamorfismo_cinetico_posible"] is True

    def test_metamorfismo_no_activo_cuando_gradiente_positivo(self):
        filas = [
            {"fecha": "2026-04-30", "lst_celsius": -2.0, "temp_suelo_l1_celsius": 1.0,
             "temp_suelo_l2_celsius": -1.0, "gradiente_termico": 2.0,
             "cobertura_nubosa_pct": 0.0, "fuente_lst": "MYD11A1"},
        ]
        consultor = self._mock_consultor(filas)
        resultado = consultor.obtener_estado_manto("La Parva Sector Bajo")

        assert resultado["metamorfismo_cinetico_posible"] is False

    def test_error_bq_retorna_estructura_segura(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(side_effect=Exception("BQ timeout"))

        resultado = consultor.obtener_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is False
        assert resultado["sin_datos"] is True
        assert "razon" in resultado
        assert resultado["lst_celsius_medio_7d"] is None


# ── Tests tool_estado_manto ───────────────────────────────────────────────────

class TestToolConsultarEstadoManto:

    _SAR_NO_DISPONIBLE = {
        "disponible": False,
        "razon": "sin datos SAR en este test",
        "sar_vv_db_reciente": None,
        "sar_baseline_vv": None,
        "sar_delta_baseline": None,
        "sar_pct_nieve_humeda": None,
        "humedad_activa": False,
    }

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_manto_frio_confirmado(self, MockConsultor):
        MockConsultor.return_value.obtener_sar_baseline.return_value = self._SAR_NO_DISPONIBLE
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": True,
            "sin_datos": False,
            "n_registros": 5,
            "lst_celsius_medio_7d": -7.5,
            "dias_lst_positivo": 0,
            "gradiente_termico_medio": -0.5,
            "temp_suelo_l1_celsius": -3.0,
            "temp_suelo_l2_celsius": -2.5,
            "manto_frio": True,
            "metamorfismo_cinetico_posible": False,
            "fuente_lst": "MOD11A1",
            "registros": [],
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is True
        assert resultado["manto_frio"] is True
        assert resultado["activacion_termica"] is False
        assert "Manto frío confirmado" in resultado["interpretacion"]

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_activacion_termica_cuando_tres_dias_positivos(self, MockConsultor):
        MockConsultor.return_value.obtener_sar_baseline.return_value = self._SAR_NO_DISPONIBLE
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": True,
            "sin_datos": False,
            "n_registros": 4,
            "lst_celsius_medio_7d": 1.5,
            "dias_lst_positivo": 3,
            "gradiente_termico_medio": -0.2,
            "temp_suelo_l1_celsius": 0.5,
            "temp_suelo_l2_celsius": 0.7,
            "manto_frio": False,
            "metamorfismo_cinetico_posible": False,
            "fuente_lst": "MOD11A1",
            "registros": [],
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["activacion_termica"] is True
        assert resultado["dias_lst_positivo"] == 3
        assert "Activación térmica" in resultado["interpretacion"]

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_metamorfismo_cinetico_en_interpretacion(self, MockConsultor):
        MockConsultor.return_value.obtener_sar_baseline.return_value = self._SAR_NO_DISPONIBLE
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": True,
            "sin_datos": False,
            "n_registros": 3,
            "lst_celsius_medio_7d": -1.5,
            "dias_lst_positivo": 0,
            "gradiente_termico_medio": -2.3,
            "temp_suelo_l1_celsius": -2.0,
            "temp_suelo_l2_celsius": 0.3,
            "manto_frio": False,
            "metamorfismo_cinetico_posible": True,
            "fuente_lst": "MYD11A1",
            "registros": [],
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["metamorfismo_cinetico_posible"] is True
        assert "Metamorfismo cinético" in resultado["interpretacion"]

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_sin_datos_no_falla_y_retorna_defaults(self, MockConsultor):
        """Constraint crítico: tabla vacía no debe interrumpir el flujo satelital."""
        MockConsultor.return_value.obtener_sar_baseline.return_value = self._SAR_NO_DISPONIBLE
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": False,
            "sin_datos": True,
            "razon": "sin registros en estado_manto_gee",
            "lst_celsius_medio_7d": None,
            "dias_lst_positivo": 0,
            "gradiente_termico_medio": None,
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is False
        assert resultado["manto_frio"] is False
        assert resultado["activacion_termica"] is False
        assert resultado["metamorfismo_cinetico_posible"] is False
        assert resultado["dias_lst_positivo"] == 0
        # No lanzó excepción — degradación graceful
        assert "interpretacion" in resultado

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_dos_dias_positivos_no_activa_activacion_termica(self, MockConsultor):
        """2 días no son suficientes para confirmar activación (umbral ≥ 3)."""
        MockConsultor.return_value.obtener_sar_baseline.return_value = self._SAR_NO_DISPONIBLE
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": True,
            "sin_datos": False,
            "n_registros": 2,
            "lst_celsius_medio_7d": 0.5,
            "dias_lst_positivo": 2,
            "gradiente_termico_medio": 0.1,
            "temp_suelo_l1_celsius": 0.3,
            "temp_suelo_l2_celsius": 0.2,
            "manto_frio": False,
            "metamorfismo_cinetico_posible": False,
            "fuente_lst": "MOD11A1",
            "registros": [],
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["activacion_termica"] is False


# ── Tests SubagenteSatelital registra la nueva tool ───────────────────────────

class TestAgenteSatelitalRegistraToolEstadoManto:

    def test_tool_registrada_en_primer_lugar(self):
        from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital
        agente  = SubagenteSatelital.__new__(SubagenteSatelital)
        tools   = agente._cargar_tools()
        nombres = [t["name"] for t in tools]

        assert "consultar_estado_manto" in nombres
        assert nombres[0] == "consultar_estado_manto"

    def test_tool_precede_a_procesar_ndsi(self):
        from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital
        agente  = SubagenteSatelital.__new__(SubagenteSatelital)
        tools   = agente._cargar_tools()
        nombres = [t["name"] for t in tools]

        assert nombres.index("consultar_estado_manto") < nombres.index("procesar_ndsi")

    def test_ejecutor_registrado(self):
        from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital
        agente     = SubagenteSatelital.__new__(SubagenteSatelital)
        ejecutores = agente._cargar_ejecutores()

        assert "consultar_estado_manto" in ejecutores

    def test_todas_las_tools_anteriores_siguen_presentes(self):
        """REQ-02a es aditivo — no debe romper tools existentes."""
        from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital
        agente  = SubagenteSatelital.__new__(SubagenteSatelital)
        tools   = agente._cargar_tools()
        nombres = [t["name"] for t in tools]

        for tool_esperada in [
            "procesar_ndsi",
            "analizar_vit",
            "detectar_anomalias_satelitales",
            "calcular_snowline",
            "analizar_via_earth_ai",
        ]:
            assert tool_esperada in nombres

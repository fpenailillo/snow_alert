"""
Tests para REQ-02b — SAR Sentinel-1 índice humedad superficial.

Cubre:
- ConsultorBigQuery.obtener_sar_baseline: estructura, delta, humedad_activa, error BQ
- tool_estado_manto extendida: integra LST + ERA5 + SAR; degradación graceful por fuente
- Constraint crítico: sin SAR el flujo continúa con señales LST/ERA5
- Constraint crítico: sin datos de ninguna fuente → disponible=False sin excepción
"""

import pytest
from unittest.mock import MagicMock, patch, call


# ── Tests ConsultorBigQuery.obtener_sar_baseline ──────────────────────────────

class TestObtenerSarBaseline:

    def _mock_consultor(self, filas_reciente, filas_baseline):
        """Crea ConsultorBigQuery con dos calls mockeados en secuencia."""
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(
            side_effect=[filas_reciente, filas_baseline]
        )
        return consultor

    def test_humedad_activa_cuando_delta_menor_menos_3(self):
        filas_reciente = [{
            "sar_vv_medio_db":    -18.5,
            "sar_pct_nieve_humeda": 45.0,
            "sar_pct_nieve_seca":  20.0,
            "fecha_captura":       "2026-04-28",
        }]
        filas_baseline = [{"baseline_vv": -14.0}]
        consultor = self._mock_consultor(filas_reciente, filas_baseline)

        resultado = consultor.obtener_sar_baseline("La Parva Sector Bajo")

        assert resultado["disponible"] is True
        assert resultado["sar_vv_db_reciente"] == pytest.approx(-18.5)
        assert resultado["sar_baseline_vv"]    == pytest.approx(-14.0)
        # delta = -18.5 - (-14.0) = -4.5 dB < -3 → humedad activa
        assert resultado["sar_delta_baseline"] == pytest.approx(-4.5, abs=0.01)
        assert resultado["humedad_activa"] is True

    def test_sin_humedad_cuando_delta_mayor_menos_3(self):
        filas_reciente = [{"sar_vv_medio_db": -13.0, "sar_pct_nieve_humeda": 5.0,
                           "sar_pct_nieve_seca": 60.0, "fecha_captura": "2026-04-28"}]
        filas_baseline = [{"baseline_vv": -13.5}]
        consultor = self._mock_consultor(filas_reciente, filas_baseline)

        resultado = consultor.obtener_sar_baseline("La Parva Sector Bajo")

        # delta = -13.0 - (-13.5) = +0.5 dB > -3 → sin humedad activa
        assert resultado["humedad_activa"] is False
        assert resultado["sar_delta_baseline"] == pytest.approx(0.5, abs=0.01)

    def test_sin_baseline_delta_es_none(self):
        """Sin datos de baseline (tabla vacía para el periodo), delta = None."""
        filas_reciente = [{"sar_vv_medio_db": -15.0, "sar_pct_nieve_humeda": 10.0,
                           "sar_pct_nieve_seca": 50.0, "fecha_captura": "2026-04-28"}]
        filas_baseline = [{"baseline_vv": None}]  # AVG retorna None si no hay filas
        consultor = self._mock_consultor(filas_reciente, filas_baseline)

        resultado = consultor.obtener_sar_baseline("La Parva Sector Bajo")

        assert resultado["disponible"] is True
        assert resultado["sar_baseline_vv"] is None
        assert resultado["sar_delta_baseline"] is None
        assert resultado["humedad_activa"] is False

    def test_sin_sar_reciente_retorna_no_disponible(self):
        filas_reciente = []  # sin datos SAR en los últimos 7 días
        filas_baseline = [{"baseline_vv": -14.0}]
        consultor = self._mock_consultor(filas_reciente, filas_baseline)

        resultado = consultor.obtener_sar_baseline("La Parva Sector Bajo")

        assert resultado["disponible"] is False
        assert resultado["humedad_activa"] is False
        assert resultado["sar_delta_baseline"] is None

    def test_error_bq_retorna_estructura_segura(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(side_effect=Exception("BQ timeout"))

        resultado = consultor.obtener_sar_baseline("La Parva Sector Bajo")

        assert resultado["disponible"] is False
        assert "razon" in resultado
        assert resultado["humedad_activa"] is False


# ── Tests tool_estado_manto con SAR integrado ─────────────────────────────────

class TestToolEstadoMantoConSAR:

    def _mock_consultor_completo(self, r_termico, r_sar):
        mock = MagicMock()
        mock.return_value.obtener_estado_manto.return_value  = r_termico
        mock.return_value.obtener_sar_baseline.return_value  = r_sar
        return mock

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_humedad_sar_en_interpretacion(self, MockConsultor):
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": True, "sin_datos": False, "n_registros": 5,
            "lst_celsius_medio_7d": -2.0, "dias_lst_positivo": 0,
            "gradiente_termico_medio": -0.5, "temp_suelo_l1_celsius": -1.0,
            "manto_frio": False, "metamorfismo_cinetico_posible": False,
            "fuente_lst": "MOD11A1", "registros": [],
        }
        MockConsultor.return_value.obtener_sar_baseline.return_value = {
            "disponible": True,
            "sar_vv_db_reciente": -19.0,
            "sar_baseline_vv": -14.5,
            "sar_delta_baseline": -4.5,
            "sar_pct_nieve_humeda": 55.0,
            "humedad_activa": True,
            "fecha_sar": "2026-04-28",
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is True
        assert resultado["humedad_sar_activa"] is True
        assert resultado["sar_delta_baseline"] == pytest.approx(-4.5)
        assert "Humedad superficial SAR" in resultado["interpretacion"]

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_sin_sar_flujo_continua_con_termico(self, MockConsultor):
        """Constraint: sin SAR, la tool retorna disponible=True con señales térmicas."""
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": True, "sin_datos": False, "n_registros": 3,
            "lst_celsius_medio_7d": -8.0, "dias_lst_positivo": 0,
            "gradiente_termico_medio": -1.5, "temp_suelo_l1_celsius": -3.0,
            "manto_frio": True, "metamorfismo_cinetico_posible": True,
            "fuente_lst": "MOD11A1", "registros": [],
        }
        MockConsultor.return_value.obtener_sar_baseline.return_value = {
            "disponible": False,
            "razon": "sin datos SAR recientes",
            "sar_vv_db_reciente": None,
            "sar_baseline_vv": None,
            "sar_delta_baseline": None,
            "sar_pct_nieve_humeda": None,
            "humedad_activa": False,
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is True  # datos térmicos disponibles
        assert resultado["manto_frio"] is True
        assert resultado["humedad_sar_activa"] is False
        assert resultado["sar_delta_baseline"] is None
        # Interpretación solo habla del manto frío, no del SAR
        assert "Manto frío confirmado" in resultado["interpretacion"]

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_sin_termico_flujo_continua_con_sar(self, MockConsultor):
        """Sin datos LST/ERA5, si hay SAR la tool igual retorna disponible=True."""
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": False, "sin_datos": True,
            "razon": "sin registros en estado_manto_gee",
            "lst_celsius_medio_7d": None, "dias_lst_positivo": 0,
            "gradiente_termico_medio": None,
        }
        MockConsultor.return_value.obtener_sar_baseline.return_value = {
            "disponible": True,
            "sar_vv_db_reciente": -17.0,
            "sar_baseline_vv": -13.0,
            "sar_delta_baseline": -4.0,
            "sar_pct_nieve_humeda": 40.0,
            "humedad_activa": True,
            "fecha_sar": "2026-04-27",
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is True
        assert resultado["humedad_sar_activa"] is True
        assert resultado["lst_celsius_medio_7d"] is None  # sin datos térmicos
        assert "Humedad superficial SAR" in resultado["interpretacion"]

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_sin_ninguna_fuente_retorna_no_disponible(self, MockConsultor):
        """Constraint crítico: sin datos de ninguna fuente → disponible=False, sin excepción."""
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": False, "sin_datos": True,
            "razon": "tabla vacía", "lst_celsius_medio_7d": None,
            "dias_lst_positivo": 0, "gradiente_termico_medio": None,
        }
        MockConsultor.return_value.obtener_sar_baseline.return_value = {
            "disponible": False,
            "razon": "sin SAR",
            "sar_vv_db_reciente": None,
            "sar_baseline_vv": None,
            "sar_delta_baseline": None,
            "sar_pct_nieve_humeda": None,
            "humedad_activa": False,
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["disponible"] is False
        assert resultado["humedad_sar_activa"] is False
        assert resultado["manto_frio"] is False
        assert "sin datos" in resultado["interpretacion"].lower()

    @patch("agentes.subagentes.subagente_satelital.tools.tool_estado_manto.ConsultorBigQuery")
    def test_multiples_señales_en_interpretacion(self, MockConsultor):
        """Cuando hay varias señales activas, la interpretación las lista todas."""
        MockConsultor.return_value.obtener_estado_manto.return_value = {
            "disponible": True, "sin_datos": False, "n_registros": 4,
            "lst_celsius_medio_7d": 1.5, "dias_lst_positivo": 3,
            "gradiente_termico_medio": -1.5, "temp_suelo_l1_celsius": 0.3,
            "manto_frio": False, "metamorfismo_cinetico_posible": True,
            "fuente_lst": "MOD11A1", "registros": [],
        }
        MockConsultor.return_value.obtener_sar_baseline.return_value = {
            "disponible": True,
            "sar_vv_db_reciente": -20.0,
            "sar_baseline_vv": -14.0,
            "sar_delta_baseline": -6.0,
            "sar_pct_nieve_humeda": 70.0,
            "humedad_activa": True,
            "fecha_sar": "2026-04-29",
        }
        from agentes.subagentes.subagente_satelital.tools.tool_estado_manto import (
            ejecutar_consultar_estado_manto,
        )
        resultado = ejecutar_consultar_estado_manto("La Parva Sector Bajo")

        assert resultado["activacion_termica"] is True
        assert resultado["humedad_sar_activa"] is True
        assert resultado["metamorfismo_cinetico_posible"] is True
        # Interpretación debe incluir al menos dos señales separadas por " | "
        assert "|" in resultado["interpretacion"]

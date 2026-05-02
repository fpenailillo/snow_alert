"""
Tests para REQ-01 — Feature de persistencia temporal en S5.

Cubre:
- obtener_historial_boletines: sin historial, con historial calmo, con historial activo
- tool_historial_ubicacion: features derivadas correctas
- clasificar_riesgo_eaws_integrado: cap en 'fair' cuando calma confirmada
- constraint crítico: MAE en tormentas no degradado (dias_nivel_bajo=0 no afecta)
"""

import pytest
from unittest.mock import MagicMock, patch


# ── Tests ConsultorBigQuery.obtener_historial_boletines ───────────────────────

class TestObtenerHistorialBoletines:

    def _mock_consultor(self, filas):
        """Crea un ConsultorBigQuery con BQ mockeado."""
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(return_value=filas)
        return consultor

    def test_sin_historial_retorna_estructura_correcta(self):
        consultor = self._mock_consultor([])
        resultado = consultor.obtener_historial_boletines("La Parva Sector Bajo", n_dias=7)

        assert resultado["disponible"] is True
        assert resultado["n_boletines"] == 0
        assert resultado["dias_consecutivos_nivel_bajo"] == 0
        assert resultado["sin_historial"] is True
        assert resultado["boletines"] == []

    def test_historial_calmo_computa_dias_consecutivos(self):
        filas = [
            {"fecha": "2026-04-30", "nivel_eaws_24h": 2, "factor_meteorologico": "ESTABLE", "confianza": "Alta"},
            {"fecha": "2026-04-29", "nivel_eaws_24h": 1, "factor_meteorologico": "ESTABLE", "confianza": "Alta"},
            {"fecha": "2026-04-28", "nivel_eaws_24h": 2, "factor_meteorologico": "ESTABLE", "confianza": "Media"},
            {"fecha": "2026-04-27", "nivel_eaws_24h": 2, "factor_meteorologico": "ESTABLE", "confianza": "Media"},
            {"fecha": "2026-04-26", "nivel_eaws_24h": 1, "factor_meteorologico": "ESTABLE", "confianza": "Alta"},
        ]
        consultor = self._mock_consultor(filas)
        resultado = consultor.obtener_historial_boletines("La Parva Sector Bajo")

        assert resultado["dias_consecutivos_nivel_bajo"] == 5
        assert resultado["nivel_promedio_7d"] == pytest.approx(1.6, abs=0.1)
        assert resultado["sin_historial"] is False

    def test_historial_interrumpido_cuenta_solo_desde_hoy(self):
        filas = [
            {"fecha": "2026-04-30", "nivel_eaws_24h": 2, "factor_meteorologico": "ESTABLE", "confianza": "Alta"},
            {"fecha": "2026-04-29", "nivel_eaws_24h": 4, "factor_meteorologico": "NEVADA_RECIENTE", "confianza": "Alta"},
            {"fecha": "2026-04-28", "nivel_eaws_24h": 1, "factor_meteorologico": "ESTABLE", "confianza": "Media"},
        ]
        consultor = self._mock_consultor(filas)
        resultado = consultor.obtener_historial_boletines("La Parva Sector Bajo")

        assert resultado["dias_consecutivos_nivel_bajo"] == 1  # se interrumpe en nivel 4

    def test_tendencia_historica_bajando(self):
        filas = [
            {"fecha": "2026-04-30", "nivel_eaws_24h": 2, "factor_meteorologico": "ESTABLE", "confianza": "Alta"},
            {"fecha": "2026-04-29", "nivel_eaws_24h": 3, "factor_meteorologico": "NEVADA_RECIENTE", "confianza": "Alta"},
            {"fecha": "2026-04-28", "nivel_eaws_24h": 4, "factor_meteorologico": "PRECIPITACION_CRITICA", "confianza": "Alta"},
        ]
        consultor = self._mock_consultor(filas)
        resultado = consultor.obtener_historial_boletines("La Parva Sector Bajo")

        assert resultado["tendencia_historica"] == -2  # 2 - 4 = -2 (bajando)

    def test_error_bq_retorna_estructura_segura(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(side_effect=Exception("BQ timeout"))
        resultado = consultor.obtener_historial_boletines("La Parva Sector Bajo")

        assert resultado["disponible"] is False
        assert resultado["dias_consecutivos_nivel_bajo"] == 0
        assert "razon" in resultado


# ── Tests tool_historial_ubicacion ────────────────────────────────────────────

class TestToolHistorialUbicacion:

    @patch("agentes.subagentes.subagente_integrador.tools.tool_historial_ubicacion.ConsultorBigQuery")
    def test_calma_confirmada_cuando_dias_bajos_gte_4(self, MockConsultor):
        MockConsultor.return_value.obtener_historial_boletines.return_value = {
            "disponible": True,
            "boletines": [{"fecha": f"2026-04-{30-i}", "nivel_eaws_24h": 1, "factor_meteorologico": "ESTABLE", "confianza": "Alta"} for i in range(5)],
            "n_boletines": 5,
            "dias_consecutivos_nivel_bajo": 5,
            "nivel_promedio_7d": 1.0,
            "tendencia_historica": 0,
            "sin_historial": False,
        }
        from agentes.subagentes.subagente_integrador.tools.tool_historial_ubicacion import (
            ejecutar_obtener_historial_ubicacion
        )
        resultado = ejecutar_obtener_historial_ubicacion("La Parva Sector Bajo")

        assert resultado["calma_confirmada"] is True
        assert resultado["dias_consecutivos_nivel_bajo"] == 5

    @patch("agentes.subagentes.subagente_integrador.tools.tool_historial_ubicacion.ConsultorBigQuery")
    def test_calma_no_confirmada_cuando_dias_bajos_lt_4(self, MockConsultor):
        MockConsultor.return_value.obtener_historial_boletines.return_value = {
            "disponible": True,
            "boletines": [],
            "n_boletines": 3,
            "dias_consecutivos_nivel_bajo": 3,
            "nivel_promedio_7d": 1.5,
            "tendencia_historica": 0,
            "sin_historial": False,
        }
        from agentes.subagentes.subagente_integrador.tools.tool_historial_ubicacion import (
            ejecutar_obtener_historial_ubicacion
        )
        resultado = ejecutar_obtener_historial_ubicacion("La Parva Sector Bajo")

        assert resultado["calma_confirmada"] is False

    @patch("agentes.subagentes.subagente_integrador.tools.tool_historial_ubicacion.ConsultorBigQuery")
    def test_sin_historial_retorna_calma_no_confirmada(self, MockConsultor):
        MockConsultor.return_value.obtener_historial_boletines.return_value = {
            "disponible": True,
            "boletines": [],
            "n_boletines": 0,
            "dias_consecutivos_nivel_bajo": 0,
            "nivel_promedio_7d": None,
            "tendencia_historica": 0,
            "sin_historial": True,
        }
        from agentes.subagentes.subagente_integrador.tools.tool_historial_ubicacion import (
            ejecutar_obtener_historial_ubicacion
        )
        resultado = ejecutar_obtener_historial_ubicacion("La Parva Sector Bajo")

        assert resultado["calma_confirmada"] is False
        assert resultado["sin_historial"] is True


# ── Tests clasificar_riesgo_eaws_integrado con persistencia ───────────────────

class TestClasificacionConPersistencia:

    def test_calma_confirmada_capa_estabilidad_en_fair(self):
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="poor",   # PINN daría nivel 3 normalmente
            estabilidad_satelital="fair",
            factor_meteorologico="ESTABLE",
            frecuencia_topografica="a_few",
            dias_consecutivos_nivel_bajo=5,   # calma confirmada
        )
        # Con calma confirmada la estabilidad se capa en 'fair' → nivel ≤ 2
        assert resultado["nivel_eaws_24h"] <= 2
        assert resultado["factores_eaws"]["estabilidad"] in ("good", "fair")

    def test_tormenta_activa_ignora_persistencia(self):
        """Con factor activo, dias_consecutivos_nivel_bajo no debe cambiar la estabilidad."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado_con_historia = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="poor",
            estabilidad_satelital="poor",
            factor_meteorologico="NEVADA_RECIENTE",
            frecuencia_topografica="some",
            dias_consecutivos_nivel_bajo=5,
        )
        resultado_sin_historia = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="poor",
            estabilidad_satelital="poor",
            factor_meteorologico="NEVADA_RECIENTE",
            frecuencia_topografica="some",
            dias_consecutivos_nivel_bajo=0,
        )
        # Factor activo: el historial calmo no debe cambiar el resultado
        assert resultado_con_historia["nivel_eaws_24h"] == resultado_sin_historia["nivel_eaws_24h"]
        assert resultado_con_historia["factores_eaws"]["estabilidad"] in ("poor", "very_poor")

    def test_sin_historial_comportamiento_identico_a_anterior(self):
        """dias_consecutivos_nivel_bajo=0 (default) reproduce el comportamiento original."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado_nuevo = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="poor",
            factor_meteorologico="ESTABLE",
            dias_consecutivos_nivel_bajo=0,
        )
        resultado_original = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="poor",
            factor_meteorologico="ESTABLE",
        )
        assert resultado_nuevo["nivel_eaws_24h"] == resultado_original["nivel_eaws_24h"]

    def test_constraint_critico_mae_tormenta_no_degradado(self):
        """
        Constraint crítico REQ-01: días calmos previos NO deben reducir el nivel
        cuando hay un evento activo. El nivel con historia calma debe ser igual
        al nivel sin historia.
        """
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        kwargs = dict(
            estabilidad_topografica="very_poor",
            estabilidad_satelital="poor",
            factor_meteorologico="PRECIPITACION_CRITICA",
            frecuencia_topografica="many",
            ventanas_criticas_detectadas=3,
        )
        sin_historia = ejecutar_clasificar_riesgo_eaws_integrado(**kwargs, dias_consecutivos_nivel_bajo=0)
        con_historia = ejecutar_clasificar_riesgo_eaws_integrado(**kwargs, dias_consecutivos_nivel_bajo=6)
        # La historia calma previa no debe reducir el nivel en tormenta activa
        assert con_historia["nivel_eaws_24h"] == sin_historia["nivel_eaws_24h"]

    def test_agente_registra_nueva_tool(self):
        from agentes.subagentes.subagente_integrador.agente import SubagenteIntegrador
        agente = SubagenteIntegrador.__new__(SubagenteIntegrador)
        tools = agente._cargar_tools()
        nombres = [t["name"] for t in tools]
        assert "obtener_historial_ubicacion" in nombres
        assert "clasificar_riesgo_eaws_integrado" in nombres
        assert nombres.index("obtener_historial_ubicacion") < nombres.index("clasificar_riesgo_eaws_integrado")

    def test_ciclo_diurno_normal_activa_cap_calma(self):
        """REQ-06: CICLO_DIURNO_NORMAL es neutro — activa cap de calma igual que ESTABLE."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="poor",
            estabilidad_satelital="fair",
            factor_meteorologico="CICLO_DIURNO_NORMAL",
            frecuencia_topografica="a_few",
            dias_consecutivos_nivel_bajo=5,
        )
        # Con calma confirmada y ciclo diurno normal, nivel debe capase en ≤ 2
        assert resultado["nivel_eaws_24h"] <= 2

    def test_fusion_activa_con_carga_no_activa_cap(self):
        """REQ-06: FUSION_ACTIVA_CON_CARGA es factor activo — días calmos no cambian nivel."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        kwargs = dict(
            estabilidad_topografica="poor",
            estabilidad_satelital="fair",
            factor_meteorologico="FUSION_ACTIVA_CON_CARGA",
            frecuencia_topografica="a_few",
        )
        sin_historia = ejecutar_clasificar_riesgo_eaws_integrado(**kwargs, dias_consecutivos_nivel_bajo=0)
        con_historia = ejecutar_clasificar_riesgo_eaws_integrado(**kwargs, dias_consecutivos_nivel_bajo=6)
        # Factor activo: historial calmo no debe cambiar el nivel
        assert con_historia["nivel_eaws_24h"] == sin_historia["nivel_eaws_24h"]

    def test_ciclo_diurno_normal_ajuste_meteo_es_none(self):
        """REQ-06: CICLO_DIURNO_NORMAL no ajusta la estabilidad base."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        res_diurno = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="good",
            estabilidad_satelital="good",
            factor_meteorologico="CICLO_DIURNO_NORMAL",
            frecuencia_topografica="nearly_none",
            dias_consecutivos_nivel_bajo=0,
        )
        res_estable = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="good",
            estabilidad_satelital="good",
            factor_meteorologico="ESTABLE",
            frecuencia_topografica="nearly_none",
            dias_consecutivos_nivel_bajo=0,
        )
        # Ambos factores neutros deben producir el mismo nivel
        assert res_diurno["nivel_eaws_24h"] == res_estable["nivel_eaws_24h"]

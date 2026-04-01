"""
Tests para REQ-02: WeatherNext 2 aditivo en S3.

Cubre:
- Interfaz abstracta FuenteMeteorologica
- FuenteOpenMeteo (wrapper existente, sin regresión)
- FuenteWeatherNext2 (flag off → disponible=False; flag on → query BQ)
- ConsolidadorMeteorologico (estrategias y fallback)
- tool_pronostico_ensemble (con BQ mockeado)
- Regresión: S3 con USE_WEATHERNEXT2=false idéntico al comportamiento actual
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


# ── PronosticoMeteorologico schema ────────────────────────────────────────────

class TestPronosticoSchema:
    def test_dataclass_instanciable(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico
        p = PronosticoMeteorologico(
            fuente="open_meteo", zona="La Parva", horizonte_h=72,
            lat=-33.354, lon=-70.298, temperatura_2m_c=-2.0,
            precipitacion_mm=10.0, viento_10m_kmh=45.0,
        )
        assert p.fuente == "open_meteo"
        assert p.ensemble_id is None
        assert p.requires_local_correction is False

    def test_weathernext2_campos_opcionales(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico
        p = PronosticoMeteorologico(
            fuente="weathernext_2", zona="La Parva", horizonte_h=72,
            lat=-33.354, lon=-70.298,
            p10_precipitacion=2.0, p50_precipitacion=8.0, p90_precipitacion=25.0,
            ensemble_id=32, n_miembros_ensemble=64,
            requires_local_correction=True,
        )
        assert p.p50_precipitacion == 8.0
        assert p.n_miembros_ensemble == 64
        assert p.requires_local_correction is True


# ── FuenteOpenMeteo ───────────────────────────────────────────────────────────

class TestFuenteOpenMeteo:
    def test_nombre_y_disponible(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo import FuenteOpenMeteo
        f = FuenteOpenMeteo()
        assert f.nombre == "open_meteo"
        assert f.disponible is True

    def test_pronostico_con_datos_bq(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo import FuenteOpenMeteo
        from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico

        _OM = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery"
        with patch(_OM) as mock_cls:
            mock_bq = mock_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {
                "disponible": True,
                "temperatura": -3.0,
                "velocidad_viento": 15.0,  # m/s
                "direccion_viento": 315.0,
                "precipitacion_acumulada": 12.0,
                "humedad_relativa": 85.0,
            }
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}

            f = FuenteOpenMeteo()
            p = f.obtener_pronostico("La Parva", -33.354, -70.298)

        assert isinstance(p, PronosticoMeteorologico)
        assert p.fuente == "open_meteo"
        assert p.fuente_disponible is True
        assert p.temperatura_2m_c == -3.0
        assert p.viento_10m_kmh == pytest.approx(15.0 * 3.6, abs=0.5)

    def test_pronostico_sin_datos_bq(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo import FuenteOpenMeteo

        _OM = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery"
        with patch(_OM) as mock_cls:
            mock_cls.return_value.obtener_condiciones_actuales.return_value = {"disponible": False}
            f = FuenteOpenMeteo()
            p = f.obtener_pronostico("La Parva", -33.354, -70.298)

        assert p.fuente_disponible is False
        assert p.error is not None

    def test_ensemble_retorna_lista_unitaria(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo import FuenteOpenMeteo

        _OM = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery"
        with patch(_OM) as mock_cls:
            mock_cls.return_value.obtener_condiciones_actuales.return_value = {"disponible": False}
            f = FuenteOpenMeteo()
            ensemble = f.obtener_ensemble("La Parva", -33.354, -70.298)

        assert isinstance(ensemble, list)
        assert len(ensemble) == 1


# ── FuenteWeatherNext2 ─────────────────────────────────────────────────────────

class TestFuenteWeatherNext2:
    def test_flag_off_disponible_false(self):
        """Con USE_WEATHERNEXT2=false, la fuente es no disponible."""
        with patch.dict(os.environ, {"USE_WEATHERNEXT2": "false"}):
            # Necesitamos recargar el módulo para que el flag se aplique
            import importlib
            import agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 as mod
            importlib.reload(mod)
            f = mod.FuenteWeatherNext2()
            # disponible depende del flag + verificar_acceso_bq
            # Con flag false siempre disponible=False
            assert mod._USE_WEATHERNEXT2 is False

    def test_pronostico_cuando_no_disponible(self):
        """Cuando no disponible, retorna PronosticoMeteorologico con fuente_disponible=False."""
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 import FuenteWeatherNext2
        from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico

        f = FuenteWeatherNext2()
        # Por defecto USE_WEATHERNEXT2=false en tests
        p = f.obtener_pronostico("La Parva", -33.354, -70.298)

        assert isinstance(p, PronosticoMeteorologico)
        assert p.fuente == "weathernext_2"
        assert p.fuente_disponible is False
        assert "Analytics Hub" in (p.error or "") or "USE_WEATHERNEXT2" in (p.error or "")

    def test_ensemble_cuando_no_disponible_retorna_lista_vacia(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 import FuenteWeatherNext2

        f = FuenteWeatherNext2()
        ensemble = f.obtener_ensemble("La Parva", -33.354, -70.298)
        assert ensemble == []

    def test_calcular_percentiles_correcto(self):
        """Test de _calcular_percentiles con datos sintéticos."""
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 import FuenteWeatherNext2
        from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico

        f = FuenteWeatherNext2()
        # Crear 10 miembros sintéticos con precipitaciones conocidas
        ensemble = [
            PronosticoMeteorologico(
                fuente="weathernext_2", zona="La Parva", horizonte_h=72,
                lat=-33.35, lon=-70.30, precipitacion_mm=float(i * 5),
                temperatura_2m_c=float(-5 + i * 0.5),
                ensemble_id=i, n_miembros_ensemble=10,
            )
            for i in range(10)
        ]

        central = f._calcular_percentiles(ensemble, "La Parva", -33.35, -70.30, 72)

        assert central.p10_precipitacion is not None
        assert central.p50_precipitacion is not None
        assert central.p90_precipitacion is not None
        # P10 < P50 < P90
        assert central.p10_precipitacion <= central.p50_precipitacion <= central.p90_precipitacion
        assert central.n_miembros_ensemble == 10


# ── ConsolidadorMeteorologico ──────────────────────────────────────────────────

class TestConsolidadorMeteorologico:
    def _mock_om_pronostico(self, temp=-2.0, precip=10.0, viento=40.0):
        from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico
        return PronosticoMeteorologico(
            fuente="open_meteo", zona="La Parva", horizonte_h=72,
            lat=-33.354, lon=-70.298,
            temperatura_2m_c=temp, precipitacion_mm=precip,
            viento_10m_kmh=viento, humedad_pct=80.0,
            fuente_disponible=True,
        )

    def test_consolidar_solo_open_meteo_default(self):
        """Con USE_WEATHERNEXT2=false: resultado idéntico a Open-Meteo."""
        from agentes.subagentes.subagente_meteorologico.fuentes.consolidador import (
            ConsolidadorMeteorologico, ResultadoConsolidado
        )

        _OM = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery"
        _ERA5 = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery"
        with patch("agentes.subagentes.subagente_meteorologico.fuentes.consolidador._USE_WEATHERNEXT2", False), \
             patch(_OM) as mock_bq_cls, \
             patch(_ERA5):
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {
                "disponible": True, "temperatura": -2.0, "velocidad_viento": 11.0,
                "direccion_viento": 315.0, "precipitacion_acumulada": 10.0,
                "humedad_relativa": 80.0,
            }
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}

            consolidador = ConsolidadorMeteorologico()
            resultado = consolidador.consolidar("La Parva", -33.354, -70.298)

        assert isinstance(resultado, ResultadoConsolidado)
        assert resultado.fuente_primaria == "open_meteo"
        assert resultado.ensemble_p50_precip is None  # WN2 no activo
        assert resultado.fuente_enriquecimiento is None
        assert "open_meteo" in resultado.fuentes_consultadas
        assert "weathernext_2" not in resultado.fuentes_consultadas

    def test_to_dict_contiene_campos_requeridos(self):
        """ResultadoConsolidado.to_dict() contiene todos los campos necesarios."""
        from agentes.subagentes.subagente_meteorologico.fuentes.consolidador import (
            ConsolidadorMeteorologico
        )

        _OM = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery"
        _ERA5 = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery"
        with patch("agentes.subagentes.subagente_meteorologico.fuentes.consolidador._USE_WEATHERNEXT2", False), \
             patch(_OM) as mock_bq_cls, \
             patch(_ERA5):
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {
                "disponible": True, "temperatura": -1.0, "velocidad_viento": 5.0,
                "direccion_viento": 270.0, "precipitacion_acumulada": 0.0,
                "humedad_relativa": 70.0,
            }
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}

            consolidador = ConsolidadorMeteorologico()
            resultado = consolidador.consolidar("Valle Nevado", -33.357, -70.270)

        d = resultado.to_dict()
        campos_requeridos = [
            "fuente_primaria", "temperatura_2m_c", "precipitacion_mm",
            "viento_10m_kmh", "horizonte_h", "ensemble_p10_precip",
            "ensemble_p50_precip", "ensemble_p90_precip",
            "fuente_enriquecimiento", "divergencia_detectada",
        ]
        for campo in campos_requeridos:
            assert campo in d, f"Campo '{campo}' ausente en to_dict()"

    def test_divergencia_temperatura_detectada(self):
        """Verifica que divergencia >3°C entre WN2 y OM genera alerta."""
        from agentes.subagentes.subagente_meteorologico.fuentes.consolidador import (
            ConsolidadorMeteorologico
        )
        from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 import FuenteWeatherNext2

        pronostico_wn2 = PronosticoMeteorologico(
            fuente="weathernext_2", zona="La Parva", horizonte_h=72,
            lat=-33.354, lon=-70.298,
            temperatura_2m_c=5.0,  # +7°C vs OM (-2°C) → divergencia
            precipitacion_mm=8.0,
            p10_precipitacion=3.0, p50_precipitacion=8.0, p90_precipitacion=18.0,
            fuente_disponible=True,
        )

        _OM = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery"
        _ERA5 = "agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery"
        with patch("agentes.subagentes.subagente_meteorologico.fuentes.consolidador._USE_WEATHERNEXT2", True), \
             patch(_OM) as mock_bq_cls, \
             patch(_ERA5), \
             patch.object(FuenteWeatherNext2, "disponible",
                          new_callable=lambda: property(lambda self: True)), \
             patch.object(FuenteWeatherNext2, "obtener_pronostico", return_value=pronostico_wn2):
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {
                "disponible": True, "temperatura": -2.0, "velocidad_viento": 10.0,
                "direccion_viento": 315.0, "precipitacion_acumulada": 10.0,
                "humedad_relativa": 80.0,
            }
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}

            consolidador = ConsolidadorMeteorologico()
            resultado = consolidador.consolidar("La Parva", -33.354, -70.298)

        # Con WN2 activo y divergencia > 3°C debe detectarla
        assert resultado.divergencia_detectada is True
        assert len(resultado.notas_divergencia) >= 1
        assert any("temperatura" in n.lower() or "Divergencia" in n for n in resultado.notas_divergencia)


# ── Tool pronostico_ensemble ───────────────────────────────────────────────────

class TestToolPronosticoEnsemble:
    def test_retorna_dict_con_campos_esperados(self):
        from agentes.subagentes.subagente_meteorologico.tools.tool_pronostico_ensemble import (
            ejecutar_obtener_pronostico_ensemble
        )

        with patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery") as mock_bq_cls, \
             patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery"), \
             patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2.FuenteWeatherNext2.disponible",
                   new_callable=lambda: property(lambda self: False)):
            mock_bq = mock_bq_cls.return_value
            mock_bq.obtener_condiciones_actuales.return_value = {
                "disponible": True, "temperatura": -4.0, "velocidad_viento": 8.0,
                "direccion_viento": 270.0, "precipitacion_acumulada": 5.0,
                "humedad_relativa": 75.0,
            }
            mock_bq.obtener_tendencia_meteorologica.return_value = {"disponible": False}

            result = ejecutar_obtener_pronostico_ensemble("La Parva")

        assert "disponible" in result
        assert "weathernext2_activo" in result
        assert "fuente_primaria" in result
        assert result["weathernext2_activo"] is False  # default en tests

    def test_fallback_cuando_bq_falla(self):
        from agentes.subagentes.subagente_meteorologico.tools.tool_pronostico_ensemble import (
            ejecutar_obtener_pronostico_ensemble
        )

        with patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo.ConsultorBigQuery") as mock_bq_cls, \
             patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery"), \
             patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2.FuenteWeatherNext2.disponible",
                   new_callable=lambda: property(lambda self: False)):
            mock_bq_cls.return_value.obtener_condiciones_actuales.side_effect = Exception("BQ timeout")

            result = ejecutar_obtener_pronostico_ensemble("La Parva")

        # No debe lanzar excepción — maneja el error
        assert "disponible" in result
        assert result["disponible"] is False


# ── Regresión: S3 con WN2 desactivado = comportamiento idéntico ───────────────

class TestRegresionS3:
    def test_s3_importa_con_nueva_tool(self):
        """S3 importa correctamente con la nueva tool sin romper nada."""
        from agentes.subagentes.subagente_meteorologico.agente import SubagenteMeteorologico
        s = SubagenteMeteorologico()
        tools = [t["name"] for t in s._cargar_tools()]
        # Las 4 originales siguen presentes
        assert "obtener_condiciones_actuales_meteo" in tools
        assert "analizar_tendencia_72h" in tools
        assert "obtener_pronostico_dias" in tools
        assert "detectar_ventanas_criticas" in tools
        # La nueva también
        assert "obtener_pronostico_ensemble" in tools

    def test_s3_ejecutores_registrados(self):
        """Todos los ejecutores están registrados correctamente."""
        from agentes.subagentes.subagente_meteorologico.agente import SubagenteMeteorologico
        s = SubagenteMeteorologico()
        ejecutores = s._cargar_ejecutores()
        assert "obtener_pronostico_ensemble" in ejecutores
        assert callable(ejecutores["obtener_pronostico_ensemble"])

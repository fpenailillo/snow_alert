"""
Tests para REQ-03 — Corrección orográfica ERA5 para precipitación.

Cubre:
- factor_correccion_orografica: por banda de altitud
- aplicar_correccion_orografica: casos normales, None, altitud negativa
- obtener_altitud_zona: zonas conocidas, alias, zona desconocida
- FuenteERA5Land: aplica corrección al construir PronosticoMeteorologico
- Constraint crítico: corrección no rompe pipeline en estaciones sin altitud registrada
"""

import pytest
from unittest.mock import MagicMock, patch


# ── Tests factor_correccion_orografica ────────────────────────────────────────

class TestFactorCorreccionOrografica:

    def test_bajo_1500m_factor_uno(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            factor_correccion_orografica,
        )
        assert factor_correccion_orografica(0)    == pytest.approx(1.0)
        assert factor_correccion_orografica(500)  == pytest.approx(1.0)
        assert factor_correccion_orografica(1499) == pytest.approx(1.0)

    def test_1500_2500m_factor_0_85(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            factor_correccion_orografica,
        )
        assert factor_correccion_orografica(1500) == pytest.approx(0.85)
        assert factor_correccion_orografica(2000) == pytest.approx(0.85)
        assert factor_correccion_orografica(2499) == pytest.approx(0.85)

    def test_2500_3500m_factor_0_75(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            factor_correccion_orografica,
        )
        assert factor_correccion_orografica(2500) == pytest.approx(0.75)
        assert factor_correccion_orografica(3000) == pytest.approx(0.75)
        assert factor_correccion_orografica(3499) == pytest.approx(0.75)

    def test_sobre_3500m_factor_0_65(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            factor_correccion_orografica,
        )
        assert factor_correccion_orografica(3500) == pytest.approx(0.65)
        assert factor_correccion_orografica(4500) == pytest.approx(0.65)

    def test_altitud_negativa_retorna_uno(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            factor_correccion_orografica,
        )
        assert factor_correccion_orografica(-100) == pytest.approx(1.0)


# ── Tests aplicar_correccion_orografica ──────────────────────────────────────

class TestAplicarCorreccionOrografica:

    def test_precip_reducida_en_altitud_alta(self):
        """REQ-03 unitario: 10mm a 3000m → valor < 10mm."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        resultado = aplicar_correccion_orografica(10.0, 3000)
        assert resultado < 10.0
        assert resultado == pytest.approx(7.5, abs=0.01)  # factor 0.75

    def test_precip_sin_cambio_bajo_1500m(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(10.0, 800) == pytest.approx(10.0)

    def test_none_retorna_none(self):
        """Constraint crítico: sin altitud/precip, no falla."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(None, 3000) is None

    def test_cero_mm_retorna_cero(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(0.0, 2700) == pytest.approx(0.0)

    def test_altitud_cero_sin_correccion(self):
        """Zona sin altitud registrada (default 0m) → factor 1.0."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(15.0, 0) == pytest.approx(15.0)

    def test_andes_2600m_factor_0_75(self):
        """Zona andina 2600m sin nombre → factor 0.75 (región andes por defecto)."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(20.0, 2600) == pytest.approx(15.0, abs=0.01)

    def test_alpes_zermatt_sin_correccion(self):
        """REQ-03: Matterhorn Zermatt (Alpes) → factor 1.0, sin reducción andina."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(20.0, 2600, zona="Matterhorn Zermatt") == pytest.approx(20.0, abs=0.01)

    def test_alpes_interlaken_sin_correccion(self):
        """REQ-03: Interlaken (Alpes) → factor 1.0."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(15.0, 1200, zona="Interlaken") == pytest.approx(15.0, abs=0.01)

    def test_alpes_st_moritz_sin_correccion(self):
        """REQ-03: St Moritz (Alpes) → factor 1.0."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            aplicar_correccion_orografica,
        )
        assert aplicar_correccion_orografica(10.0, 1900, zona="St Moritz") == pytest.approx(10.0, abs=0.01)


# ── Tests obtener_altitud_zona ────────────────────────────────────────────────

class TestObtenerAltitudZona:

    def test_zonas_chilenas_conocidas(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            obtener_altitud_zona,
        )
        assert obtener_altitud_zona("La Parva Sector Bajo")  == 2700
        assert obtener_altitud_zona("La Parva Sector Alto")  == 3600
        assert obtener_altitud_zona("Valle Nevado")           == 3200

    def test_zonas_suizas_conocidas(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            obtener_altitud_zona,
        )
        assert obtener_altitud_zona("Interlaken")         == 1200
        assert obtener_altitud_zona("Matterhorn Zermatt") == 2600
        assert obtener_altitud_zona("St Moritz")          == 1900

    def test_zona_desconocida_retorna_cero(self):
        """Zona sin registro → 0m → factor 1.0 → sin corrección (seguro)."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            obtener_altitud_zona,
        )
        assert obtener_altitud_zona("Estacion Desconocida XYZ") == 0


# ── Tests es_zona_alpes ───────────────────────────────────────────────────────

class TestEsZonaAlpes:

    def test_zonas_alpes_detectadas(self):
        """REQ-03: las tres zonas suizas deben reconocerse como Alpes."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import es_zona_alpes
        assert es_zona_alpes("Interlaken")         is True
        assert es_zona_alpes("Matterhorn Zermatt") is True
        assert es_zona_alpes("St Moritz")          is True

    def test_zonas_andes_no_son_alpes(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import es_zona_alpes
        assert es_zona_alpes("La Parva")              is False
        assert es_zona_alpes("Valle Nevado")           is False
        assert es_zona_alpes("La Parva Sector Alto")   is False

    def test_zona_desconocida_no_es_alpes(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import es_zona_alpes
        assert es_zona_alpes("Estacion Desconocida XYZ") is False


class TestFactorCorreccionOrograficaRegion:

    def test_region_alpes_retorna_uno(self):
        """REQ-03: factor siempre 1.0 para región alpes, independiente de altitud."""
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            factor_correccion_orografica,
        )
        assert factor_correccion_orografica(2600, region="alpes") == pytest.approx(1.0)
        assert factor_correccion_orografica(1200, region="alpes") == pytest.approx(1.0)
        assert factor_correccion_orografica(4000, region="alpes") == pytest.approx(1.0)

    def test_region_andes_aplica_tabla(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.correccion_orografica import (
            factor_correccion_orografica,
        )
        assert factor_correccion_orografica(3000, region="andes") == pytest.approx(0.75)
        assert factor_correccion_orografica(1800, region="andes") == pytest.approx(0.85)


# ── Tests FuenteERA5Land aplica corrección ────────────────────────────────────

class TestFuenteERA5LandConCorreccion:

    @patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery")
    def test_precipitacion_reducida_en_zona_alta(self, MockConsultor):
        """La Parva Sector Alto (3600m) → factor 0.65 → precip ERA5 reducida."""
        MockConsultor.return_value.obtener_estado_satelital.return_value = {
            "disponible": True,
            "lst_dia_celsius": -5.0,
            "lst_noche_celsius": -10.0,
            "era5_snow_depth_m": 0.5,
            "era5_snowfall_m": 0.01,  # 10mm de agua equivalente
        }
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land import FuenteERA5Land
        fuente = FuenteERA5Land()
        pronostico = fuente.obtener_pronostico("La Parva Sector Alto", -33.344, -70.280)

        assert pronostico.fuente_disponible is True
        assert pronostico.precipitacion_mm is not None
        # 10mm * factor(3600m=0.65) = 6.5mm
        assert pronostico.precipitacion_mm == pytest.approx(6.5, abs=0.1)
        # corrección ya aplicada → no requiere corrección local
        assert pronostico.requires_local_correction is False

    @patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery")
    def test_sin_snowfall_precipitacion_none(self, MockConsultor):
        """Si era5_snowfall_m es None, precipitacion_mm debe ser None (no falla)."""
        MockConsultor.return_value.obtener_estado_satelital.return_value = {
            "disponible": True,
            "lst_dia_celsius": -3.0,
            "lst_noche_celsius": -8.0,
            "era5_snow_depth_m": None,
            "era5_snowfall_m": None,
        }
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land import FuenteERA5Land
        fuente     = FuenteERA5Land()
        pronostico = fuente.obtener_pronostico("La Parva Sector Bajo", -33.363, -70.301)

        assert pronostico.fuente_disponible is True
        assert pronostico.precipitacion_mm is None

    @patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery")
    def test_zona_sin_altitud_usa_factor_uno(self, MockConsultor):
        """Zona desconocida → altitud=0m → factor=1.0 → precip sin corrección."""
        MockConsultor.return_value.obtener_estado_satelital.return_value = {
            "disponible": True,
            "lst_dia_celsius": 2.0,
            "lst_noche_celsius": -2.0,
            "era5_snow_depth_m": 0.0,
            "era5_snowfall_m": 0.005,  # 5mm
        }
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land import FuenteERA5Land
        fuente     = FuenteERA5Land()
        pronostico = fuente.obtener_pronostico("Estacion Sin Datos", 0.0, 0.0)

        assert pronostico.precipitacion_mm == pytest.approx(5.0, abs=0.1)

    @patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery")
    def test_alpes_interlaken_sin_reduccion(self, MockConsultor):
        """REQ-03: Interlaken (Alpes, 1200m) → factor=1.0 → precip ERA5 sin reducción."""
        MockConsultor.return_value.obtener_estado_satelital.return_value = {
            "disponible": True,
            "lst_dia_celsius": 4.0,
            "lst_noche_celsius": -1.0,
            "era5_snow_depth_m": 0.3,
            "era5_snowfall_m": 0.015,  # 15mm de agua equivalente
        }
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land import FuenteERA5Land
        fuente     = FuenteERA5Land()
        pronostico = fuente.obtener_pronostico("Interlaken", 46.686, 7.863)

        assert pronostico.fuente_disponible is True
        assert pronostico.precipitacion_mm is not None
        # 15mm * factor(Alpes=1.0) = 15mm — sin reducción andina
        assert pronostico.precipitacion_mm == pytest.approx(15.0, abs=0.1)

    @patch("agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land.ConsultorBigQuery")
    def test_bq_error_no_rompe_pipeline(self, MockConsultor):
        """Error en BQ → disponible=False sin propagar excepción."""
        MockConsultor.return_value.obtener_estado_satelital.side_effect = Exception("BQ timeout")
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land import FuenteERA5Land
        fuente     = FuenteERA5Land()
        pronostico = fuente.obtener_pronostico("La Parva Sector Bajo", -33.363, -70.301)

        assert pronostico.fuente_disponible is False
        assert pronostico.error is not None

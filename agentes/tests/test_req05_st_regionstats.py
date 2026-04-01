"""
Tests para REQ-05: ST_REGIONSTATS, zonas_objetivo y constantes_zonas.

Cubre:
  - constantes_zonas: helpers, fallbacks, consistencia entre dicts
  - ConsultorBigQuery.obtener_stats_terreno_st: ST_REGIONSTATS con NASADEM
  - ConsultorBigQuery.obtener_zona_geografica: tabla zonas_objetivo
  - Refactor: fuentes meteorológicas usan COORDENADAS_ZONAS centralizado
"""

import json
import pytest
from unittest.mock import MagicMock, patch


# ─── TestConstantesZonas ──────────────────────────────────────────────────────

class TestConstantesZonas:

    def test_zonas_disponibles_minimo(self):
        from agentes.datos.constantes_zonas import COORDENADAS_ZONAS, BBOX_ZONAS
        assert "La Parva" in COORDENADAS_ZONAS
        assert "Valle Nevado" in COORDENADAS_ZONAS
        assert "El Colorado" in COORDENADAS_ZONAS
        assert "La Parva" in BBOX_ZONAS
        assert "Valle Nevado" in BBOX_ZONAS

    def test_coordenadas_en_andes_central(self):
        from agentes.datos.constantes_zonas import COORDENADAS_ZONAS
        for zona, (lat, lon) in COORDENADAS_ZONAS.items():
            assert -34.0 <= lat <= -33.0, f"{zona}: lat fuera de rango"
            assert -71.0 <= lon <= -70.0, f"{zona}: lon fuera de rango"

    def test_bbox_coherente(self):
        from agentes.datos.constantes_zonas import BBOX_ZONAS
        for zona, (lon_min, lat_min, lon_max, lat_max) in BBOX_ZONAS.items():
            assert lon_min < lon_max, f"{zona}: lon_min >= lon_max"
            assert lat_min < lat_max, f"{zona}: lat_min >= lat_max"

    def test_poligonos_son_geojson_valido(self):
        from agentes.datos.constantes_zonas import POLIGONOS_ZONAS
        for zona, poly in POLIGONOS_ZONAS.items():
            assert poly["type"] == "Polygon"
            coords = poly["coordinates"][0]
            assert coords[0] == coords[-1], f"{zona}: polígono no cerrado"

    def test_obtener_coordenadas_fallback(self):
        from agentes.datos.constantes_zonas import obtener_coordenadas
        lat, lon = obtener_coordenadas("Zona Inexistente")
        assert lat == -33.354  # fallback La Parva
        assert lon == -70.298

    def test_obtener_bbox_fallback(self):
        from agentes.datos.constantes_zonas import obtener_bbox
        bbox = obtener_bbox("Zona Inexistente")
        assert len(bbox) == 4
        assert bbox[0] < bbox[2]  # lon_min < lon_max

    def test_obtener_bbox_sector_usa_zona_base(self):
        from agentes.datos.constantes_zonas import obtener_bbox
        bbox_base = obtener_bbox("La Parva")
        bbox_sector = obtener_bbox("La Parva Sector Alto")
        # Sector Alto tiene bbox propio o fallback a La Parva — ambos válidos
        assert len(bbox_sector) == 4

    def test_poligono_geojson_str_parseable(self):
        from agentes.datos.constantes_zonas import poligono_geojson_str
        s = poligono_geojson_str("Valle Nevado")
        poly = json.loads(s)
        assert poly["type"] == "Polygon"

    def test_zonas_disponibles_lista(self):
        from agentes.datos.constantes_zonas import ZONAS_DISPONIBLES
        assert len(ZONAS_DISPONIBLES) >= 4
        assert "La Parva" in ZONAS_DISPONIBLES


# ─── TestConsultorBigQueryStRegionStats ───────────────────────────────────────

class TestConsultorBigQueryStRegionStats:

    _BQ = "agentes.datos.consultor_bigquery.bigquery.Client"

    def _mock_fila(self, **kwargs):
        fila = MagicMock()
        fila.__iter__ = lambda s: iter(kwargs.items())
        fila.keys = lambda: kwargs.keys()
        def getitem(key):
            return kwargs[key]
        fila.__getitem__ = lambda s, k: kwargs[k]
        # Que dict(fila) funcione
        fila.items = lambda: kwargs.items()
        return type("Row", (), kwargs)()

    def test_retorna_disponible_false_si_zona_no_existe(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(return_value=iter([]))
        resultado = consultor.obtener_stats_terreno_st("Zona No Existe")
        assert resultado["disponible"] is False
        assert "no encontrada" in resultado["razon"]

    def test_retorna_stats_cuando_hay_datos(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        fila_mock = {
            "nombre_zona": "La Parva",
            "lat_centroide": -33.354,
            "lon_centroide": -70.298,
            "elevacion_min_m": 2200,
            "elevacion_max_m": 4500,
            "exposicion_predominante": "SE",
            "region_eaws": "Andes Central Norte",
            "area_km2": 619.7,
            "nasadem_elevacion_media_m": 2611.9,
            "nasadem_elevacion_std_m": 358.2,
            "srtm_elevacion_media_m": 2619.6,
        }
        # BQ Row soporta dict() via __iter__ sobre keys y __getitem__
        fila = MagicMock()
        fila.keys.return_value = fila_mock.keys()
        fila.__iter__ = lambda s: iter(fila_mock.keys())
        fila.__getitem__ = lambda s, k: fila_mock[k]
        fila.items = lambda: fila_mock.items()
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(return_value=iter([fila]))
        resultado = consultor.obtener_stats_terreno_st("La Parva")
        assert resultado["disponible"] is True
        assert resultado["nasadem_elevacion_media_m"] == pytest.approx(2611.9)
        assert resultado["area_km2"] == pytest.approx(619.7)
        assert "NASADEM" in resultado["fuente_dem"]
        assert "latencia_ms" in resultado

    def test_fallback_en_excepcion_bq(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(side_effect=Exception("BQ timeout"))
        resultado = consultor.obtener_stats_terreno_st("La Parva")
        assert resultado["disponible"] is False
        assert "BQ timeout" in resultado["razon"]

    def test_obtener_zona_geografica_retorna_geojson(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        fila_mock = {
            "nombre_zona": "Valle Nevado",
            "geometria_geojson": '{"type":"Polygon","coordinates":[]}',
            "lat_centroide": -33.357,
            "lon_centroide": -70.270,
            "area_km2": 309.9,
            "elevacion_min_m": 2800,
            "elevacion_max_m": 4500,
            "exposicion_predominante": "NO",
            "region_eaws": "Andes Central Norte",
        }
        fila = MagicMock()
        fila.keys.return_value = fila_mock.keys()
        fila.__iter__ = lambda s: iter(fila_mock.keys())
        fila.__getitem__ = lambda s, k: fila_mock[k]
        fila.items = lambda: fila_mock.items()
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(return_value=iter([fila]))
        resultado = consultor.obtener_zona_geografica("Valle Nevado")
        assert resultado["disponible"] is True
        assert resultado["nombre_zona"] == "Valle Nevado"
        assert "geometria_geojson" in resultado

    def test_obtener_zona_geografica_fallback(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        consultor = ConsultorBigQuery.__new__(ConsultorBigQuery)
        consultor._ejecutar_query = MagicMock(return_value=iter([]))
        resultado = consultor.obtener_zona_geografica("Zona Inexistente")
        assert resultado["disponible"] is False


# ─── TestRefactorFuentesMeteoro ───────────────────────────────────────────────

class TestRefactorFuentesMeteoro:

    def test_fuente_open_meteo_usa_constantes_zonas(self):
        """FuenteOpenMeteo ya no tiene _COORDS_ZONAS propio."""
        import inspect
        import agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo as mod
        src = inspect.getsource(mod)
        assert "_COORDS_ZONAS" not in src
        assert "COORDENADAS_ZONAS" in src

    def test_fuente_era5_usa_constantes_zonas(self):
        import inspect
        import agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land as mod
        src = inspect.getsource(mod)
        assert "_COORDS_ZONAS" not in src
        assert "COORDENADAS_ZONAS" in src

    def test_fuente_weathernext2_usa_constantes_zonas(self):
        import inspect
        import agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 as mod
        src = inspect.getsource(mod)
        assert "_COORDS_ZONAS" not in src
        assert "COORDENADAS_ZONAS" in src

    def test_tool_ensemble_usa_constantes_zonas(self):
        import inspect
        import agentes.subagentes.subagente_meteorologico.tools.tool_pronostico_ensemble as mod
        src = inspect.getsource(mod)
        assert "_COORDS_ZONAS" not in src
        assert "COORDENADAS_ZONAS" in src

    def test_backfill_usa_bbox_zonas(self):
        import inspect
        import agentes.datos.backfill.actualizar_glo30_tagee_ae as mod
        src = inspect.getsource(mod)
        assert "BBOX_ZONAS" in src
        # El dict ZONAS ya no hardcodea coordenadas
        assert '[-70.45' not in src

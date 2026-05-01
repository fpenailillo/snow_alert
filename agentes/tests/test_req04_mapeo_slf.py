"""
Tests para REQ-04 — Mapeo estación→sector SLF preciso.

Cubre:
- MAPEO_ESTACIONES_SLF: estructura, sector_ids únicos y válidos
- haversine_km: resultado conocido (Geneva → Zurich ≈ 225 km)
- obtener_sector_slf: lookup correcto
- sectores_por_distancia: orden correcto
- Integración 07_validacion_slf_suiza: usa MAPEO_ESTACIONES_SLF por defecto
"""

import math
import pytest


# ── Tests del mapeo estático ──────────────────────────────────────────────────

class TestMapeoEstacionesSLF:

    def test_tres_estaciones_registradas(self):
        from agentes.validacion.mapeo_estaciones_slf import MAPEO_ESTACIONES_SLF
        assert len(MAPEO_ESTACIONES_SLF) == 3
        assert "Interlaken" in MAPEO_ESTACIONES_SLF
        assert "Matterhorn Zermatt" in MAPEO_ESTACIONES_SLF
        assert "St Moritz" in MAPEO_ESTACIONES_SLF

    def test_todos_los_campos_presentes(self):
        from agentes.validacion.mapeo_estaciones_slf import MAPEO_ESTACIONES_SLF
        campos_requeridos = {"nombre_andesai", "sector_id", "lat", "lon",
                              "altitud_m", "canton", "prefix_canton", "descripcion"}
        for nombre, info in MAPEO_ESTACIONES_SLF.items():
            assert campos_requeridos == set(info.keys()), \
                f"Campos faltantes o extra en '{nombre}'"

    def test_sector_ids_son_enteros_positivos(self):
        from agentes.validacion.mapeo_estaciones_slf import MAPEO_ESTACIONES_SLF
        for nombre, info in MAPEO_ESTACIONES_SLF.items():
            sid = info["sector_id"]
            assert isinstance(sid, int), f"sector_id de '{nombre}' no es int"
            assert sid > 0, f"sector_id de '{nombre}' no es positivo"

    def test_sector_ids_son_distintos(self):
        from agentes.validacion.mapeo_estaciones_slf import MAPEO_ESTACIONES_SLF
        ids = [info["sector_id"] for info in MAPEO_ESTACIONES_SLF.values()]
        assert len(ids) == len(set(ids)), "Hay sector_ids duplicados en el mapeo"

    def test_prefix_canton_coincide_con_sector_id(self):
        """El prefix del cantón debe ser el primer dígito del sector_id."""
        from agentes.validacion.mapeo_estaciones_slf import MAPEO_ESTACIONES_SLF
        for nombre, info in MAPEO_ESTACIONES_SLF.items():
            prefix_esperado = str(info["sector_id"])[0]
            assert info["prefix_canton"] == prefix_esperado, \
                f"prefix_canton de '{nombre}' no coincide con sector_id"

    def test_coordenadas_en_suiza(self):
        """Verificación básica: coordenadas dentro del bounding box de Suiza."""
        from agentes.validacion.mapeo_estaciones_slf import MAPEO_ESTACIONES_SLF
        LAT_MIN, LAT_MAX = 45.8, 47.9
        LON_MIN, LON_MAX = 5.9, 10.6
        for nombre, info in MAPEO_ESTACIONES_SLF.items():
            assert LAT_MIN <= info["lat"] <= LAT_MAX, \
                f"Latitud de '{nombre}' fuera de Suiza: {info['lat']}"
            assert LON_MIN <= info["lon"] <= LON_MAX, \
                f"Longitud de '{nombre}' fuera de Suiza: {info['lon']}"

    def test_sectores_en_cantones_esperados(self):
        from agentes.validacion.mapeo_estaciones_slf import MAPEO_ESTACIONES_SLF
        assert MAPEO_ESTACIONES_SLF["Interlaken"]["canton"]         == "Bern"
        assert MAPEO_ESTACIONES_SLF["Matterhorn Zermatt"]["canton"] == "Valais"
        assert MAPEO_ESTACIONES_SLF["St Moritz"]["canton"]          == "Graubünden"


# ── Tests haversine_km ────────────────────────────────────────────────────────

class TestHaversineKm:

    def test_distancia_conocida_geneva_zurich(self):
        """Ginebra → Zürich: distancia real ≈ 225 km."""
        from agentes.validacion.mapeo_estaciones_slf import haversine_km
        d = haversine_km(46.2044, 6.1432, 47.3769, 8.5417)  # Geneva → Zurich
        assert 210 <= d <= 240, f"Distancia Ginebra-Zürich fuera de rango: {d:.1f} km"

    def test_distancia_mismo_punto_es_cero(self):
        from agentes.validacion.mapeo_estaciones_slf import haversine_km
        d = haversine_km(46.5, 7.5, 46.5, 7.5)
        assert d == pytest.approx(0.0, abs=1e-6)

    def test_distancia_es_simetrica(self):
        from agentes.validacion.mapeo_estaciones_slf import haversine_km
        d1 = haversine_km(46.2, 6.1, 47.3, 8.5)
        d2 = haversine_km(47.3, 8.5, 46.2, 6.1)
        assert d1 == pytest.approx(d2, abs=1e-6)

    def test_distancia_zermatt_interlaken(self):
        """Zermatt → Interlaken: distancia real ≈ 90-100 km."""
        from agentes.validacion.mapeo_estaciones_slf import haversine_km
        d = haversine_km(46.021, 7.749, 46.686, 7.863)
        assert 70 <= d <= 120, f"Distancia Zermatt-Interlaken fuera de rango: {d:.1f} km"


# ── Tests obtener_sector_slf ──────────────────────────────────────────────────

class TestObtenerSectorSlf:

    def test_estacion_conocida_retorna_info(self):
        from agentes.validacion.mapeo_estaciones_slf import obtener_sector_slf
        info = obtener_sector_slf("Interlaken")
        assert info is not None
        assert info["sector_id"] == 4113
        assert info["canton"]    == "Bern"

    def test_estacion_desconocida_retorna_none(self):
        from agentes.validacion.mapeo_estaciones_slf import obtener_sector_slf
        info = obtener_sector_slf("La Parva Sector Bajo")
        assert info is None

    def test_todas_las_estaciones_suizas(self):
        from agentes.validacion.mapeo_estaciones_slf import obtener_sector_slf
        for nombre in ["Interlaken", "Matterhorn Zermatt", "St Moritz"]:
            assert obtener_sector_slf(nombre) is not None


# ── Tests sectores_por_distancia ──────────────────────────────────────────────

class TestSectoresPorDistancia:

    def test_orden_correcto_por_distancia(self):
        from agentes.validacion.mapeo_estaciones_slf import sectores_por_distancia
        # Referencia: Bern (46.95, 7.44)
        sectores = [
            {"sector_id": 4113, "lat": 46.686, "lon": 7.863},  # Interlaken ~ 50km
            {"sector_id": 4221, "lat": 46.95,  "lon": 7.44},   # Bern ~ 0km
            {"sector_id": 4312, "lat": 46.50,  "lon": 8.20},   # Más lejos
        ]
        ordenados = sectores_por_distancia(46.95, 7.44, sectores)
        assert ordenados[0]["sector_id"] == 4221  # Bern es el más cercano
        assert ordenados[0]["distancia_km"] == pytest.approx(0.0, abs=1.0)

    def test_campo_distancia_km_agregado(self):
        from agentes.validacion.mapeo_estaciones_slf import sectores_por_distancia
        sectores = [{"sector_id": 4113, "lat": 46.686, "lon": 7.863}]
        resultado = sectores_por_distancia(46.686, 7.863, sectores)
        assert "distancia_km" in resultado[0]
        assert isinstance(resultado[0]["distancia_km"], float)


# ── Test que el notebook importa el mapeo nuevo ───────────────────────────────

class TestNotebookUsaMapeoPreciso:

    def test_notebook_importa_mapeo_estaciones_slf(self):
        """07_validacion_slf_suiza.py debe importar MAPEO_ESTACIONES_SLF."""
        import importlib.util, pathlib
        path = pathlib.Path(
            __file__
        ).parent.parent.parent / "notebooks_validacion" / "07_validacion_slf_suiza.py"
        spec   = importlib.util.spec_from_file_location("nb07", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert hasattr(module, "MAPEO_ESTACIONES_SLF")
        assert hasattr(module, "obtener_niveles_slf_preciso")

    def test_resumen_mapeo_retorna_string(self):
        from agentes.validacion.mapeo_estaciones_slf import resumen_mapeo
        texto = resumen_mapeo()
        assert isinstance(texto, str)
        assert "Interlaken" in texto
        assert "Zermatt" in texto or "Matterhorn" in texto
        assert "St Moritz" in texto

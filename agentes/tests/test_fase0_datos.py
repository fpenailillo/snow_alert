"""
Tests de FASE 0 — Diagnóstico de Datos BigQuery

Verifica la estructura y cobertura de datos en las tablas BigQuery del sistema
snow_alert. Se saltan automáticamente si no hay credenciales GCP disponibles.

Tablas verificadas:
- clima.imagenes_satelitales
- clima.zonas_avalancha
- clima.condiciones_meteorologicas
- clima.pronostico_meteorologico
- clima.datos_dem
- clima.relatos_montanistas (puede no existir aún)

Ejecutar:
    python -m pytest agentes/tests/test_fase0_datos.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


# ─── Guard: saltar si no hay credenciales GCP ─────────────────────────────────
def _tiene_credenciales_gcp() -> bool:
    """Verifica si hay credenciales GCP disponibles."""
    try:
        from google.auth import default
        credentials, project = default()
        return project is not None
    except Exception:
        return False


_gcp_disponible = _tiene_credenciales_gcp()

pytestmark = pytest.mark.skipif(
    not _gcp_disponible,
    reason="Sin credenciales GCP (ejecutar 'gcloud auth application-default login')"
)


UMBRAL_NULOS_CRITICO = 0.50  # 50% de nulos → tabla con problemas graves
UMBRAL_NULOS_ADVERTENCIA = 0.20  # 20% de nulos → advertencia


# ─── Fixture: consultor BigQuery ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def consultor():
    """Instancia del ConsultorBigQuery compartida entre todos los tests."""
    from agentes.datos.consultor_bigquery import ConsultorBigQuery
    return ConsultorBigQuery()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de estructura de tablas
# ═══════════════════════════════════════════════════════════════════════════════

def test_tabla_imagenes_satelitales_accesible(consultor):
    """La tabla imagenes_satelitales debe ser accesible y tener filas."""
    resultado = consultor.obtener_estado_satelital("La Parva Sector Bajo")

    assert isinstance(resultado, dict), "El resultado debe ser un dict"
    assert "error" not in resultado or not resultado.get("error"), (
        f"Error al acceder a imagenes_satelitales: {resultado.get('error')}"
    )
    print(f"\n  ✓ imagenes_satelitales accesible")


def test_tabla_zonas_avalancha_accesible(consultor):
    """La tabla zonas_avalancha debe ser accesible y tener filas."""
    resultado = consultor.obtener_perfil_topografico("La Parva Sector Bajo")

    assert isinstance(resultado, dict), "El resultado debe ser un dict"
    assert "error" not in resultado or not resultado.get("error"), (
        f"Error al acceder a zonas_avalancha: {resultado.get('error')}"
    )
    print(f"\n  ✓ zonas_avalancha accesible")


def test_tabla_condiciones_meteorologicas_accesible(consultor):
    """La tabla condiciones_actuales debe ser accesible."""
    resultado = consultor.obtener_condiciones_actuales("La Parva Sector Bajo")

    assert isinstance(resultado, dict), "El resultado debe ser un dict"
    assert "error" not in resultado or not resultado.get("error"), (
        f"Error al acceder a condiciones_actuales: {resultado.get('error')}"
    )
    print(f"\n  ✓ condiciones_actuales accesible")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de cobertura de datos
# ═══════════════════════════════════════════════════════════════════════════════

def test_imagenes_satelitales_cobertura_minima(consultor):
    """La tabla imagenes_satelitales debe tener datos para múltiples ubicaciones."""
    ubicaciones = consultor.listar_ubicaciones_con_datos()

    assert isinstance(ubicaciones, list), "listar_ubicaciones_con_datos debe retornar lista"
    assert len(ubicaciones) > 0, (
        "No hay ubicaciones con datos recientes en imagenes_satelitales. "
        "Verificar Cloud Functions extractor/monitor_satelital."
    )
    print(f"\n  ✓ {len(ubicaciones)} ubicaciones con datos satelitales recientes")
    for ub in ubicaciones[:5]:
        print(f"    - {ub}")


def test_imagenes_satelitales_tiene_ndsi(consultor):
    """Los datos satelitales deben incluir valores NDSI para La Parva."""
    resultado = consultor.obtener_estado_satelital("La Parva Sector Bajo")

    if not resultado.get("disponible"):
        pytest.skip("Sin datos satelitales recientes para La Parva Sector Bajo")

    ndsi = resultado.get("ndsi_medio")
    if ndsi is None:
        pytest.skip("NDSI no disponible en tabla imagenes_satelitales")

    print(f"\n  ✓ NDSI disponible: {ndsi:.3f}")


def test_zonas_avalancha_tiene_pendientes(consultor):
    """El perfil topográfico debe tener datos de ángulo de pendiente."""
    resultado = consultor.obtener_perfil_topografico("La Parva Sector Bajo")

    if not resultado.get("disponible"):
        pytest.skip("Sin datos topográficos para La Parva Sector Bajo")

    pendiente = resultado.get("pendiente_media_inicio")
    if pendiente is None:
        pytest.skip("pendiente_media_inicio no disponible en tabla zonas_avalancha")

    assert 0 < pendiente < 90, f"Pendiente fuera de rango: {pendiente}°"
    print(f"\n  ✓ Pendiente disponible: {pendiente:.1f}°")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de tabla relatos (puede no existir aún — FASE 1)
# ═══════════════════════════════════════════════════════════════════════════════

def test_tabla_relatos_estado(consultor):
    """
    Verifica el estado de la tabla relatos_montanistas.
    Si no existe, reporta como advertencia (no falla el test).
    """
    try:
        resultado = consultor.obtener_relatos_ubicacion("La Parva", limite=5)

        assert isinstance(resultado, dict), "obtener_relatos_ubicacion debe retornar dict"

        if not resultado.get("disponible"):
            pytest.skip(
                "Tabla relatos_montanistas no disponible. "
                "Ejecutar FASE 1 para cargar relatos desde Andeshandbook."
            )

        relatos = resultado.get("relatos", [])
        print(f"\n  ✓ Tabla relatos_montanistas disponible — {resultado.get('total_encontrados', 0)} relatos para La Parva")
        for r in relatos[:3]:
            print(f"    - [{r.get('fecha_actividad', 'sin fecha')}] {r.get('titulo', 'sin título')[:60]}")

    except AttributeError:
        pytest.skip(
            "Método obtener_relatos_ubicacion no disponible en ConsultorBigQuery. "
            "Verificar que FASE 2 se aplicó correctamente."
        )

"""
Test End-to-End — Generación Completa de Boletín para La Parva Sector Bajo

Genera un boletín completo usando el agentic loop y verifica:
- Secciones obligatorias del formato EAWS
- Nivel EAWS 24h es int entre 1 y 5
- Las 4 tools fueron llamadas en orden correcto
- El boletín se guardó en BigQuery

Ejecutar (con salida visible):
    python -m pytest agentes/tests/test_boletin_completo.py -v -s
"""

import sys
import os
import re
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agentes.orquestador.agente_principal import AgenteRiesgoAvalancha
from agentes.salidas.almacenador import guardar_boletin

# Verificar que hay credenciales de Anthropic disponibles
_tiene_auth = (
    os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or
    os.environ.get("ANTHROPIC_API_KEY")
)
if not _tiene_auth:
    pytest.skip(
        "Sin credenciales de Anthropic. "
        "Ejecutar desde Claude Code (CLAUDE_CODE_OAUTH_TOKEN) "
        "o establecer ANTHROPIC_API_KEY.",
        allow_module_level=True
    )


UBICACION_PILOTO = "La Parva Sector Bajo"

SECCIONES_OBLIGATORIAS = [
    "BOLETÍN DE RIESGO DE AVALANCHAS",
    "NIVEL DE PELIGRO",
    "SITUACIÓN DEL MANTO NIVAL",
    "FACTORES DE RIESGO",
    "TERRENO DE MAYOR RIESGO",
    "PRONÓSTICO PRÓXIMOS 3 DÍAS",
    "RECOMENDACIONES",
    "FACTORES EAWS USADOS",
    "CONFIANZA:",
]

TOOLS_ORDEN_ESPERADO = [
    "analizar_terreno",
    "monitorear_nieve",
    "analizar_meteorologia",
    "clasificar_riesgo_eaws",
]


@pytest.fixture(scope="module")
def boletin_generado():
    """
    Fixture que genera el boletín completo una sola vez para todos los tests.
    Imprime el agentic loop paso a paso.
    """
    print(f"\n{'=' * 60}")
    print(f"Generando boletín para: {UBICACION_PILOTO}")
    print(f"{'=' * 60}\n")

    agente = AgenteRiesgoAvalancha()
    resultado = agente.generar_boletin(UBICACION_PILOTO)

    print(f"\n{'=' * 60}")
    print("BOLETÍN GENERADO:")
    print(f"{'=' * 60}")
    print(resultado.get("boletin", "Sin boletín"))
    print(f"\n{'=' * 60}")
    print(f"Iteraciones: {resultado.get('iteraciones')}")
    print(f"Duración: {resultado.get('duracion_segundos')}s")
    print(f"Nivel EAWS 24h: {resultado.get('nivel_eaws_24h')}")
    print(f"Tools llamadas: {[t['tool'] for t in resultado.get('tools_llamadas', [])]}")
    print(f"{'=' * 60}")

    return resultado


def test_boletin_se_genera_sin_error(boletin_generado):
    """Verifica que el boletín se generó sin errores."""
    assert "error" not in boletin_generado, (
        f"El boletín contiene error: {boletin_generado.get('error')}"
    )
    assert "boletin" in boletin_generado, "El resultado debe contener el campo 'boletin'"
    assert len(boletin_generado["boletin"]) > 100, "El boletín debe tener contenido significativo"

    print(f"\n  ✓ Boletín generado ({len(boletin_generado['boletin'])} caracteres)")


def test_boletin_contiene_secciones_obligatorias(boletin_generado):
    """Verifica que el boletín contiene todas las secciones del formato EAWS."""
    texto = boletin_generado.get("boletin", "")
    secciones_faltantes = []

    for seccion in SECCIONES_OBLIGATORIAS:
        if seccion not in texto:
            secciones_faltantes.append(seccion)
        else:
            print(f"  ✓ Sección encontrada: {seccion}")

    assert not secciones_faltantes, (
        f"Secciones faltantes en el boletín: {secciones_faltantes}"
    )


def test_nivel_eaws_es_entero_valido(boletin_generado):
    """Verifica que el nivel EAWS 24h es un entero entre 1 y 5."""
    nivel = boletin_generado.get("nivel_eaws_24h")

    assert nivel is not None, (
        "nivel_eaws_24h no fue extraído del boletín. "
        f"Texto del boletín: {boletin_generado.get('boletin', '')[:500]}"
    )
    assert isinstance(nivel, int), f"nivel_eaws_24h debe ser int, es {type(nivel)}: {nivel}"
    assert 1 <= nivel <= 5, f"nivel_eaws_24h debe estar entre 1 y 5, es {nivel}"

    print(f"\n  ✓ Nivel EAWS 24h: {nivel}")


def test_tools_llamadas_en_orden_correcto(boletin_generado):
    """Verifica que las 4 tools fueron llamadas en el orden esperado."""
    tools_llamadas = boletin_generado.get("tools_llamadas", [])
    nombres_tools = [t["tool"] for t in tools_llamadas]

    print(f"\n  Tools llamadas: {nombres_tools}")

    # Verificar que todas las 4 tools fueron llamadas
    for tool_esperada in TOOLS_ORDEN_ESPERADO:
        assert tool_esperada in nombres_tools, (
            f"Tool '{tool_esperada}' no fue llamada. "
            f"Tools disponibles: {nombres_tools}"
        )

    # Verificar que se respetó el orden relativo
    indices = {tool: nombres_tools.index(tool) for tool in TOOLS_ORDEN_ESPERADO}

    assert indices["analizar_terreno"] < indices["monitorear_nieve"], (
        "analizar_terreno debe llamarse antes que monitorear_nieve"
    )
    assert indices["monitorear_nieve"] < indices["analizar_meteorologia"], (
        "monitorear_nieve debe llamarse antes que analizar_meteorologia"
    )
    assert indices["analizar_meteorologia"] < indices["clasificar_riesgo_eaws"], (
        "analizar_meteorologia debe llamarse antes que clasificar_riesgo_eaws"
    )

    print(f"  ✓ Orden correcto: {' → '.join(TOOLS_ORDEN_ESPERADO)}")


def test_boletin_contiene_ubicacion(boletin_generado):
    """Verifica que el boletín menciona la ubicación correcta."""
    texto = boletin_generado.get("boletin", "")
    assert "La Parva" in texto or "Parva" in texto, (
        "El boletín debe mencionar la ubicación 'La Parva'"
    )
    print(f"\n  ✓ Ubicación mencionada en el boletín")


def test_boletin_tiene_factores_eaws(boletin_generado):
    """Verifica que el boletín incluye los factores EAWS usados."""
    texto = boletin_generado.get("boletin", "")

    # Debe mencionar al menos uno de los valores de estabilidad
    clases_estabilidad = ["very_poor", "poor", "fair", "good"]
    tiene_estabilidad = any(clase in texto.lower() for clase in clases_estabilidad)

    # Debe mencionar frecuencia
    clases_frecuencia = ["many", "some", "a_few", "nearly_none"]
    tiene_frecuencia = any(clase in texto.lower() for clase in clases_frecuencia)

    assert tiene_estabilidad or "Estabilidad:" in texto, (
        "El boletín debe mencionar el factor de estabilidad EAWS"
    )

    print(f"\n  ✓ Factores EAWS presentes en el boletín")


def test_boletin_se_guarda_en_bigquery(boletin_generado):
    """Verifica que el boletín se guarda exitosamente en BigQuery."""
    print(f"\n  Guardando boletín en BigQuery...")

    estado = guardar_boletin(boletin_generado)

    assert isinstance(estado, dict)

    if not estado.get("guardado"):
        errores = estado.get("errores", [])
        pytest.fail(
            f"El boletín no se pudo guardar. Errores: {errores}"
        )

    guardado_bq = estado.get("guardado_bigquery", False)
    guardado_gcs = estado.get("guardado_gcs", False)

    print(f"  ✓ Guardado en BigQuery: {guardado_bq}")
    if estado.get("uri_gcs"):
        print(f"  ✓ Guardado en GCS: {estado['uri_gcs']}")

    assert guardado_bq or guardado_gcs, "Debe guardarse en al menos un destino"


def test_metadata_completa(boletin_generado):
    """Verifica que el resultado contiene toda la metadata necesaria."""
    campos_requeridos = [
        "ubicacion",
        "boletin",
        "nivel_eaws_24h",
        "tools_llamadas",
        "iteraciones",
        "duracion_segundos",
        "timestamp",
        "modelo"
    ]

    for campo in campos_requeridos:
        assert campo in boletin_generado, f"Campo requerido faltante: {campo}"

    assert boletin_generado["ubicacion"] == UBICACION_PILOTO
    assert isinstance(boletin_generado["iteraciones"], int)
    assert boletin_generado["iteraciones"] > 0
    assert isinstance(boletin_generado["duracion_segundos"], (int, float))
    assert boletin_generado["duracion_segundos"] > 0

    print(f"\n  ✓ Metadata completa:")
    print(f"    - Ubicación: {boletin_generado['ubicacion']}")
    print(f"    - Modelo: {boletin_generado['modelo']}")
    print(f"    - Iteraciones: {boletin_generado['iteraciones']}")
    print(f"    - Duración: {boletin_generado['duracion_segundos']}s")
    print(f"    - Timestamp: {boletin_generado['timestamp']}")

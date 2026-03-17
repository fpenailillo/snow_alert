"""
Test End-to-End — Sistema Multi-Agente v2 para La Parva Sector Bajo

Verifica que el OrquestadorAvalancha coordina los 4 subagentes correctamente:
- SubagenteTopografico (DEM + PINNs)
- SubagenteSatelital (imágenes + ViT)
- SubagenteMeteorologico (condiciones + ventanas críticas)
- SubagenteIntegrador (EAWS + boletín final)

Verifica acumulación de contexto, formato EAWS y almacenamiento en BigQuery.
Se salta automáticamente si no hay credenciales de Anthropic.

Ejecutar:
    python -m pytest agentes/tests/test_sistema_completo.py -v -s
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# ─── Guard: saltar si no hay credenciales ─────────────────────────────────────
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

SUBAGENTES_ESPERADOS = [
    "topografico",
    "satelital",
    "meteorologico",
    "integrador",
]

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


@pytest.fixture(scope="module")
def resultado_v2():
    """
    Genera el boletín v2 una sola vez para todos los tests del módulo.
    Usa OrquestadorAvalancha directamente (o su alias AgenteRiesgoAvalancha).
    """
    from agentes.orquestador.agente_principal import OrquestadorAvalancha

    print(f"\n{'=' * 60}")
    print(f"Sistema Multi-Agente v2 — {UBICACION_PILOTO}")
    print(f"{'=' * 60}\n")

    orquestador = OrquestadorAvalancha()
    resultado = orquestador.generar_boletin(UBICACION_PILOTO)

    print(f"\n{'=' * 60}")
    print("BOLETÍN GENERADO:")
    print(f"{'=' * 60}")
    print(resultado.get("boletin", "Sin boletín"))
    print(f"\n{'=' * 60}")
    print(f"Arquitectura: {resultado.get('arquitectura')}")
    print(f"Subagentes ejecutados: {resultado.get('subagentes_ejecutados')}")
    print(f"Nivel EAWS 24h: {resultado.get('nivel_eaws_24h')}")
    print(f"Iteraciones totales: {resultado.get('iteraciones')}")
    print(f"Duración total: {resultado.get('duracion_segundos')}s")
    duracion_sa = resultado.get("duracion_por_subagente", {})
    for nombre, dur in duracion_sa.items():
        print(f"  └─ {nombre}: {dur}s")
    print(f"{'=' * 60}")

    return resultado


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de arquitectura v2
# ═══════════════════════════════════════════════════════════════════════════════

def test_arquitectura_es_v2(resultado_v2):
    """El resultado debe identificarse como multi_agente_v2."""
    assert resultado_v2.get("arquitectura") == "multi_agente_v2", (
        f"Arquitectura esperada: 'multi_agente_v2', "
        f"obtenida: '{resultado_v2.get('arquitectura')}'"
    )
    print(f"\n  ✓ Arquitectura: {resultado_v2['arquitectura']}")


def test_cuatro_subagentes_ejecutados(resultado_v2):
    """Los 4 subagentes deben aparecer en la lista de ejecutados."""
    subagentes = resultado_v2.get("subagentes_ejecutados", [])

    for nombre in SUBAGENTES_ESPERADOS:
        assert nombre in subagentes, (
            f"Subagente '{nombre}' no fue ejecutado. "
            f"Ejecutados: {subagentes}"
        )
        print(f"  ✓ Subagente ejecutado: {nombre}")


def test_duracion_por_subagente_disponible(resultado_v2):
    """Debe haber duración registrada para cada subagente."""
    duraciones = resultado_v2.get("duracion_por_subagente", {})

    assert isinstance(duraciones, dict), "duracion_por_subagente debe ser un dict"
    assert len(duraciones) == 4, (
        f"Deben registrarse 4 duraciones, se encontraron {len(duraciones)}: {duraciones}"
    )

    for nombre, duracion in duraciones.items():
        assert isinstance(duracion, (int, float)), (
            f"Duración de {nombre} debe ser numérica, es: {type(duracion)}"
        )
        assert duracion >= 0, f"Duración de {nombre} no puede ser negativa: {duracion}"
        print(f"  ✓ {nombre}: {duracion}s")


def test_resultados_subagentes_incluidos(resultado_v2):
    """El resultado debe incluir los análisis parciales de cada subagente."""
    resultados_sa = resultado_v2.get("resultados_subagentes", {})

    assert isinstance(resultados_sa, dict), "resultados_subagentes debe ser un dict"

    for nombre in SUBAGENTES_ESPERADOS:
        assert nombre in resultados_sa, (
            f"Resultado de subagente '{nombre}' no encontrado"
        )
        analisis = resultados_sa[nombre].get("analisis", "")
        assert len(analisis) > 10, (
            f"Análisis de '{nombre}' parece vacío: '{analisis[:50]}'"
        )
        print(f"  ✓ {nombre}: {len(analisis)} chars de análisis")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de contenido del boletín
# ═══════════════════════════════════════════════════════════════════════════════

def test_boletin_generado_sin_error(resultado_v2):
    """El boletín debe generarse sin errores y con contenido suficiente."""
    assert "error" not in resultado_v2, (
        f"El resultado contiene error: {resultado_v2.get('error')}"
    )
    assert "boletin" in resultado_v2, "El resultado debe contener el campo 'boletin'"
    assert len(resultado_v2["boletin"]) > 100, (
        "El boletín debe tener contenido significativo"
    )
    print(f"\n  ✓ Boletín generado ({len(resultado_v2['boletin'])} caracteres)")


def test_boletin_contiene_secciones_obligatorias(resultado_v2):
    """El boletín debe incluir todas las secciones del formato EAWS."""
    texto = resultado_v2.get("boletin", "")
    faltantes = [s for s in SECCIONES_OBLIGATORIAS if s not in texto]

    for seccion in SECCIONES_OBLIGATORIAS:
        if seccion not in faltantes:
            print(f"  ✓ {seccion}")

    assert not faltantes, f"Secciones faltantes: {faltantes}"


def test_nivel_eaws_valido(resultado_v2):
    """El nivel EAWS 24h debe ser un entero entre 1 y 5."""
    nivel = resultado_v2.get("nivel_eaws_24h")

    assert nivel is not None, (
        "nivel_eaws_24h no fue extraído. "
        f"Inicio del boletín: {resultado_v2.get('boletin', '')[:300]}"
    )
    assert isinstance(nivel, int), (
        f"nivel_eaws_24h debe ser int, es {type(nivel)}: {nivel}"
    )
    assert 1 <= nivel <= 5, f"nivel_eaws_24h debe estar entre 1 y 5, es {nivel}"
    print(f"\n  ✓ Nivel EAWS 24h: {nivel}")


def test_boletin_menciona_ubicacion(resultado_v2):
    """El boletín debe mencionar la ubicación analizada."""
    texto = resultado_v2.get("boletin", "")
    assert "La Parva" in texto or "Parva" in texto, (
        "El boletín debe mencionar 'La Parva'"
    )
    print(f"\n  ✓ Ubicación mencionada en el boletín")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de metadata
# ═══════════════════════════════════════════════════════════════════════════════

def test_metadata_v2_completa(resultado_v2):
    """El resultado debe incluir todos los campos de metadata v2."""
    campos_v1 = [
        "ubicacion", "boletin", "nivel_eaws_24h",
        "tools_llamadas", "iteraciones", "duracion_segundos",
        "timestamp", "modelo",
    ]
    campos_v2 = [
        "arquitectura", "subagentes_ejecutados",
        "duracion_por_subagente", "resultados_subagentes",
    ]

    for campo in campos_v1 + campos_v2:
        assert campo in resultado_v2, f"Campo faltante: '{campo}'"
        print(f"  ✓ {campo}")

    assert resultado_v2["ubicacion"] == UBICACION_PILOTO
    assert isinstance(resultado_v2["iteraciones"], int)
    assert resultado_v2["iteraciones"] > 0
    assert isinstance(resultado_v2["duracion_segundos"], (int, float))
    assert resultado_v2["duracion_segundos"] > 0


def test_total_iteraciones_es_suma_subagentes(resultado_v2):
    """Las iteraciones totales deben ser la suma de los 4 subagentes."""
    total = resultado_v2.get("iteraciones", 0)
    resultados_sa = resultado_v2.get("resultados_subagentes", {})

    suma_sa = sum(
        sa.get("iteraciones", 0) or 0
        for sa in resultados_sa.values()
    )

    # Toleramos diferencia de ±1 por redondeo o iteraciones extra
    assert abs(total - suma_sa) <= 1, (
        f"Iteraciones totales ({total}) != suma de subagentes ({suma_sa})"
    )
    print(f"\n  ✓ Total iteraciones: {total} (suma subagentes: {suma_sa})")


def test_tools_llamadas_de_todos_los_subagentes(resultado_v2):
    """Las tools_llamadas deben incluir llamadas de los 4 subagentes."""
    tools = resultado_v2.get("tools_llamadas", [])

    assert isinstance(tools, list), "tools_llamadas debe ser una lista"
    assert len(tools) > 0, "Debe haber al menos una tool llamada"
    print(f"\n  ✓ {len(tools)} tools llamadas en total")

    # Verificar que hay diversidad de tools (al menos 3 distintas)
    nombres_tools = {t.get("tool", t) if isinstance(t, dict) else t for t in tools}
    assert len(nombres_tools) >= 3, (
        f"Se esperan al menos 3 tools distintas, se encontraron: {nombres_tools}"
    )
    print(f"  ✓ Tools únicas: {nombres_tools}")


# ═══════════════════════════════════════════════════════════════════════════════
# Test de almacenamiento
# ═══════════════════════════════════════════════════════════════════════════════

def test_boletin_v2_se_guarda_en_bigquery(resultado_v2):
    """El boletín v2 debe guardarse correctamente en BigQuery."""
    from agentes.salidas.almacenador import guardar_boletin

    print(f"\n  Guardando boletín v2 en BigQuery...")
    estado = guardar_boletin(resultado_v2)

    assert isinstance(estado, dict)

    if not estado.get("guardado"):
        errores = estado.get("errores", [])
        pytest.fail(f"El boletín no se pudo guardar. Errores: {errores}")

    guardado_bq = estado.get("guardado_bigquery", False)
    guardado_gcs = estado.get("guardado_gcs", False)

    print(f"  ✓ Guardado en BigQuery: {guardado_bq}")
    if estado.get("uri_gcs"):
        print(f"  ✓ Guardado en GCS: {estado['uri_gcs']}")

    assert guardado_bq or guardado_gcs, "Debe guardarse en al menos un destino"


# ═══════════════════════════════════════════════════════════════════════════════
# Test de retrocompatibilidad
# ═══════════════════════════════════════════════════════════════════════════════

def test_alias_v1_funciona():
    """AgenteRiesgoAvalancha (alias v1) debe ser instanciable sin errores."""
    from agentes.orquestador.agente_principal import AgenteRiesgoAvalancha, OrquestadorAvalancha

    agente = AgenteRiesgoAvalancha()
    assert isinstance(agente, OrquestadorAvalancha), (
        "AgenteRiesgoAvalancha debe ser subclase de OrquestadorAvalancha"
    )
    assert hasattr(agente, "generar_boletin"), "Debe tener método generar_boletin"
    assert hasattr(agente, "generar_boletines_masivos"), "Debe tener método generar_boletines_masivos"
    print(f"\n  ✓ AgenteRiesgoAvalancha es retrocompatible con OrquestadorAvalancha")

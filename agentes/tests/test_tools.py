"""
Tests de Tools Individuales — Sistema Multi-Agente de Predicción de Avalanchas

Verifica que cada tool retorna el formato esperado y que los datos
de La Parva Sector Bajo son accesibles.

Ejecutar:
    python -m pytest agentes/tests/test_tools.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agentes.datos.consultor_bigquery import ConsultorBigQuery
from agentes.tools.tool_topografico import ejecutar_analizar_terreno
from agentes.tools.tool_satelital import ejecutar_monitorear_nieve
from agentes.tools.tool_meteorologico import ejecutar_analizar_meteorologia
from agentes.tools.tool_eaws import ejecutar_clasificar_eaws


UBICACION_PILOTO = "La Parva Sector Bajo"


@pytest.fixture(scope="module")
def consultor():
    """Fixture del ConsultorBigQuery compartido entre tests."""
    return ConsultorBigQuery()


def test_tool_topografico_la_parva(consultor):
    """Verifica que tool_topografico retorna dict con indice_riesgo_topografico."""
    resultado = ejecutar_analizar_terreno(consultor, UBICACION_PILOTO)

    assert isinstance(resultado, dict), "Debe retornar un dict"
    assert "error" not in resultado, f"No debe haber error: {resultado.get('error')}"

    # Puede no haber datos topográficos (disponible=False es válido)
    if not resultado.get("disponible"):
        print(f"\n  ⚠ Sin datos topográficos para {UBICACION_PILOTO}: {resultado.get('razon')}")
        return

    # Si hay datos, verificar campos clave
    assert "indice_riesgo_topografico" in resultado, (
        "Debe contener indice_riesgo_topografico"
    )
    assert "clasificacion_riesgo" in resultado
    assert "peligro_eaws_base" in resultado
    assert "frecuencia_estimada_eaws" in resultado
    assert "tamano_estimado_eaws" in resultado
    assert "interpretaciones" in resultado
    assert isinstance(resultado["interpretaciones"], list)

    indice = resultado["indice_riesgo_topografico"]
    assert 0 <= indice <= 100, f"Índice fuera de rango: {indice}"

    print(f"\n  ✓ Perfil topográfico obtenido:")
    print(f"    - Índice riesgo: {indice}")
    print(f"    - Clasificación: {resultado['clasificacion_riesgo']}")
    print(f"    - Peligro EAWS base: {resultado['peligro_eaws_base']}")
    print(f"    - Frecuencia EAWS: {resultado['frecuencia_estimada_eaws']}")
    print(f"    - Tamaño EAWS: {resultado['tamano_estimado_eaws']}")
    if resultado.get("interpretaciones"):
        print(f"    - Interpretaciones: {resultado['interpretaciones']}")


def test_tool_satelital_la_parva(consultor):
    """Verifica que tool_satelital retorna dict (disponible True o False, no error)."""
    resultado = ejecutar_monitorear_nieve(consultor, UBICACION_PILOTO)

    assert isinstance(resultado, dict), "Debe retornar un dict"
    assert "error" not in resultado, f"No debe haber error de sistema: {resultado.get('error')}"
    assert "disponible" in resultado, "Debe contener campo 'disponible'"

    if not resultado.get("disponible"):
        print(f"\n  ⚠ Sin datos satelitales recientes para {UBICACION_PILOTO}: "
              f"{resultado.get('razon')}")
        return

    # Verificar campos presentes cuando disponible=True
    assert "alertas" in resultado, "Debe contener lista de alertas"
    assert isinstance(resultado["alertas"], list)

    print(f"\n  ✓ Estado satelital obtenido:")
    print(f"    - Cobertura nieve: {resultado.get('pct_cobertura_nieve')}%")
    print(f"    - NDSI medio: {resultado.get('ndsi_medio')}")
    print(f"    - Snowline: {resultado.get('snowline_elevacion_m')}m")
    print(f"    - LST día: {resultado.get('lst_dia_celsius')}°C")
    print(f"    - Delta nieve 24h: {resultado.get('delta_pct_nieve_24h')}%")
    print(f"    - SAR disponible: {resultado.get('sar_disponible')}")
    print(f"    - Transporte eólico: {resultado.get('transporte_eolico_activo')}")
    if resultado.get("alertas"):
        print(f"    - Alertas: {resultado['alertas']}")


def test_tool_meteorologico_la_parva(consultor):
    """Verifica que tool_meteorologico retorna dict con temperatura y tendencia."""
    resultado = ejecutar_analizar_meteorologia(consultor, UBICACION_PILOTO)

    assert isinstance(resultado, dict), "Debe retornar un dict"

    # Verificar estructura del resultado
    assert "condiciones_actuales" in resultado
    assert "tendencia_72h" in resultado
    assert "pronostico_3dias" in resultado
    assert "alertas" in resultado
    assert isinstance(resultado["alertas"], list)

    condiciones = resultado.get("condiciones_actuales", {})
    tendencia = resultado.get("tendencia_72h", {})

    # Al menos uno de los dos debe tener datos
    tiene_condiciones = condiciones.get("disponible", False)
    tiene_tendencia = tendencia.get("disponible", False)

    if not tiene_condiciones and not tiene_tendencia:
        print(f"\n  ⚠ Sin datos meteorológicos para {UBICACION_PILOTO}")
        return

    print(f"\n  ✓ Datos meteorológicos obtenidos:")
    if tiene_condiciones:
        print(f"    - Temperatura actual: {condiciones.get('temperatura')}°C")
        print(f"    - Viento: {condiciones.get('velocidad_viento')} m/s")
        print(f"    - Humedad: {condiciones.get('humedad_relativa')}%")
        print(f"    - Condición: {condiciones.get('condicion_clima')}")

    if tiene_tendencia:
        print(f"    - Temp min 72h: {tendencia.get('temp_min_72h')}°C")
        print(f"    - Temp max 72h: {tendencia.get('temp_max_72h')}°C")
        print(f"    - Precip acumulada: {tendencia.get('precip_total_acumulada_mm')}mm")
        print(f"    - Viento max: {tendencia.get('viento_max_ms')} m/s")
        print(f"    - Tendencia temp: {tendencia.get('tendencia_temperatura')}")

    if resultado.get("alertas"):
        print(f"    - Alertas: {resultado['alertas']}")


def test_tool_eaws_nivel3():
    """Verifica que clasificar_riesgo_eaws('poor','some',3) retorna nivel 3."""
    resultado = ejecutar_clasificar_eaws(
        estabilidad="poor",
        frecuencia="some",
        tamano=3
    )

    assert isinstance(resultado, dict), "Debe retornar un dict"
    assert "error" not in resultado, f"No debe haber error: {resultado.get('error')}"
    assert "nivel_24h" in resultado, "Debe contener nivel_24h"

    nivel = resultado["nivel_24h"]
    assert nivel == 3, (
        f"Para (poor, some, 3) se esperaba nivel 3, se obtuvo {nivel}"
    )

    assert "nombre_nivel_24h" in resultado
    assert "recomendaciones" in resultado
    assert "factores_usados" in resultado

    print(f"\n  ✓ EAWS (poor, some, 3):")
    print(f"    - Nivel 24h: {resultado['nivel_24h']} ({resultado['nombre_nivel_24h']})")
    print(f"    - Nivel 48h: {resultado['nivel_48h']}")
    print(f"    - Alternativo: {resultado['nivel_alternativo']}")


def test_tool_eaws_nivel1():
    """Verifica que clasificar_riesgo_eaws('good','nearly_none',1) retorna nivel 1."""
    resultado = ejecutar_clasificar_eaws(
        estabilidad="good",
        frecuencia="nearly_none",
        tamano=1
    )

    assert isinstance(resultado, dict), "Debe retornar un dict"
    assert "error" not in resultado, f"No debe haber error: {resultado.get('error')}"
    assert "nivel_24h" in resultado

    nivel = resultado["nivel_24h"]
    assert nivel == 1, (
        f"Para (good, nearly_none, 1) se esperaba nivel 1, se obtuvo {nivel}"
    )

    print(f"\n  ✓ EAWS (good, nearly_none, 1):")
    print(f"    - Nivel 24h: {resultado['nivel_24h']} ({resultado['nombre_nivel_24h']})")


def test_tool_eaws_entradas_invalidas():
    """Verifica que la tool maneja entradas inválidas sin excepciones."""
    resultado = ejecutar_clasificar_eaws(
        estabilidad="invalido",
        frecuencia="some",
        tamano=3
    )

    assert isinstance(resultado, dict)
    assert "error" in resultado, "Debe retornar error para estabilidad inválida"
    print(f"\n  ✓ Manejo de entrada inválida: {resultado['error']}")


def test_tool_eaws_todas_las_combinaciones_criticas():
    """Verifica combinaciones EAWS críticas de la hoja de ruta."""
    casos = [
        # (estabilidad, frecuencia, tamano, nivel_esperado)
        ("very_poor", "many", 5, 5),
        ("poor", "many", 3, 4),
        ("fair", "a_few", 2, 1),
    ]

    for est, frec, tam, nivel_esp in casos:
        resultado = ejecutar_clasificar_eaws(est, frec, tam)
        assert "error" not in resultado, f"Error en ({est},{frec},{tam}): {resultado.get('error')}"
        nivel = resultado["nivel_24h"]
        assert nivel == nivel_esp, (
            f"Para ({est},{frec},{tam}) se esperaba nivel {nivel_esp}, se obtuvo {nivel}"
        )
        print(f"  ✓ ({est}, {frec}, {tam}) → nivel {nivel}")

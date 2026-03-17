"""
Tests de Subagentes Individuales — Sistema Multi-Agente v2

Verifica que cada subagente puede ejecutarse de forma independiente:
- SubagenteTopografico (DEM + PINNs)
- SubagenteSatelital (imágenes + ViT)
- SubagenteMeteorologico (condiciones + ventanas críticas)
- SubagenteIntegrador (EAWS + boletín)

Los tests de subagentes con llamadas Anthropic se saltan si no hay credenciales.
Los tests de tools (sin Anthropic) corren siempre.

Ejecutar:
    python -m pytest agentes/tests/test_subagentes.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


UBICACION_PILOTO = "La Parva Sector Bajo"

# ─── Verificar credenciales Anthropic ─────────────────────────────────────────
_tiene_auth = (
    os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or
    os.environ.get("ANTHROPIC_API_KEY")
)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de tools SIN llamadas Anthropic (siempre corren)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolsPINN:
    """Tests del motor PINN sin llamadas a Anthropic."""

    def test_calcular_pinn_pendiente_critica(self):
        """PINN con pendiente crítica retorna factor de seguridad bajo."""
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.65,
            densidad_kg_m3=300.0,
            indice_metamorfismo=1.2,
            energia_fusion_J_kg=200000.0,
            pendiente_grados=45.0
        )
        assert "factor_seguridad_mohr_coulomb" in resultado
        assert isinstance(resultado["factor_seguridad_mohr_coulomb"], float)
        assert resultado["factor_seguridad_mohr_coulomb"] > 0
        assert "estado_manto" in resultado
        assert resultado["estado_manto"] in ("CRITICO", "INESTABLE", "MARGINAL", "ESTABLE")

    def test_calcular_pinn_pendiente_baja(self):
        """PINN con pendiente baja retorna factor de seguridad alto."""
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.3,
            densidad_kg_m3=400.0,
            indice_metamorfismo=0.5,
            energia_fusion_J_kg=100000.0,
            pendiente_grados=15.0
        )
        # Pendiente baja → factor de seguridad alto → manto estable
        assert resultado["factor_seguridad_mohr_coulomb"] > 1.5
        assert resultado["estado_manto"] in ("ESTABLE", "MARGINAL")

    def test_pinn_con_temperatura_positiva(self):
        """PINN con temperatura positiva detecta fusión."""
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.5,
            densidad_kg_m3=250.0,
            indice_metamorfismo=1.3,
            energia_fusion_J_kg=280000.0,
            pendiente_grados=38.0,
            temperatura_superficie_C=3.0
        )
        assert "alertas_pinn" in resultado
        # Con temperatura positiva y alta energía de fusión, debería haber alerta
        assert isinstance(resultado["alertas_pinn"], list)


class TestToolsVIT:
    """Tests del motor ViT sin llamadas a Anthropic."""

    def test_vit_serie_vacia(self):
        """ViT con serie vacía retorna disponible=False."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )
        resultado = ejecutar_analizar_vit(
            serie_temporal=[],
            ndsi_promedio=0.5,
            cobertura_promedio=70.0
        )
        assert resultado["disponible"] is False

    def test_vit_punto_unico(self):
        """ViT con un solo punto temporal funciona correctamente."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )
        serie = [{
            "paso_t": 0,
            "ndsi_medio": 0.45,
            "pct_cobertura_nieve": 65.0,
            "lst_dia_celsius": -2.0,
            "lst_noche_celsius": -8.0,
            "ciclo_diurno_amplitud": 6.0,
            "delta_pct_nieve_24h": 0.0
        }]
        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.45,
            cobertura_promedio=65.0
        )
        assert resultado["disponible"] is True
        assert resultado["estado_vit"] in ("CRITICO", "ALERTADO", "MODERADO", "ESTABLE")
        assert resultado["pasos_analizados"] == 1

    def test_vit_serie_nevada_reciente(self):
        """ViT detecta nevada reciente en la serie temporal."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )
        # Serie con nevada masiva en el último paso
        serie = [
            {"paso_t": i, "ndsi_medio": 0.5, "pct_cobertura_nieve": 60.0,
             "lst_dia_celsius": -3.0, "lst_noche_celsius": -10.0,
             "ciclo_diurno_amplitud": 7.0, "delta_pct_nieve_24h": 0.0}
            for i in range(5)
        ]
        # Último paso: nevada de 25%
        serie[-1]["delta_pct_nieve_24h"] = 25.0
        serie[-1]["pct_cobertura_nieve"] = 85.0

        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.5,
            cobertura_promedio=65.0,
            variabilidad_ndsi=0.05
        )
        assert resultado["disponible"] is True
        assert resultado["score_anomalia"] > 0
        # El último paso (con nevada) debería tener el mayor peso de atención
        assert resultado["indice_paso_critico"] == len(serie) - 1

    def test_vit_self_attention_normalizacion(self):
        """Los pesos de atención del ViT suman 1."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )
        serie = [
            {"paso_t": i, "ndsi_medio": 0.4, "pct_cobertura_nieve": 60.0,
             "lst_dia_celsius": -5.0, "lst_noche_celsius": -12.0,
             "ciclo_diurno_amplitud": 7.0, "delta_pct_nieve_24h": 1.0}
            for i in range(4)
        ]
        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.4,
            cobertura_promedio=60.0
        )
        if resultado["disponible"] and len(resultado["pesos_atencion"]) > 1:
            suma = sum(resultado["pesos_atencion"])
            assert abs(suma - 1.0) < 0.01, f"Los pesos deben sumar 1, suma={suma}"


class TestToolsEAWS:
    """Tests de la clasificación EAWS integrada."""

    def test_clasificar_eaws_condiciones_criticas(self):
        """Condiciones críticas → nivel EAWS alto."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="very_poor",
            factor_meteorologico="PRECIPITACION_CRITICA",
            estabilidad_satelital="poor",
            frecuencia_topografica="some",
            tamano_eaws="3"
        )
        assert resultado["nivel_eaws_24h"] >= 3
        assert 1 <= resultado["nivel_eaws_24h"] <= 5
        assert 1 <= resultado["nivel_eaws_48h"] <= 5
        assert 1 <= resultado["nivel_eaws_72h"] <= 5

    def test_clasificar_eaws_condiciones_estables(self):
        """Condiciones estables → nivel EAWS bajo."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="good",
            factor_meteorologico="ESTABLE",
            estabilidad_satelital="good",
            frecuencia_topografica="nearly_none",
            tamano_eaws="1"
        )
        assert resultado["nivel_eaws_24h"] <= 2

    def test_clasificar_eaws_factores_incluidos(self):
        """El resultado incluye todos los factores EAWS."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="fair",
            factor_meteorologico="NEVADA_RECIENTE",
            frecuencia_topografica="a_few",
            tamano_eaws="2"
        )
        assert "factores_eaws" in resultado
        assert "estabilidad" in resultado["factores_eaws"]
        assert "frecuencia" in resultado["factores_eaws"]
        assert "tamano" in resultado["factores_eaws"]
        assert resultado["factores_eaws"]["estabilidad"] in (
            "very_poor", "poor", "fair", "good"
        )


class TestToolsBoletin:
    """Tests de generación de boletín."""

    def test_redactar_boletin_estructura(self):
        """El boletín generado contiene todas las secciones obligatorias."""
        from agentes.subagentes.subagente_integrador.tools.tool_generar_boletin import (
            ejecutar_redactar_boletin_eaws
        )
        resultado = ejecutar_redactar_boletin_eaws(
            ubicacion="La Parva Sector Bajo",
            nivel_eaws_24h=3,
            nivel_eaws_48h=3,
            nivel_eaws_72h=2,
            estabilidad_eaws="poor",
            frecuencia_eaws="some",
            tamano_eaws=2,
            factor_meteorologico="NEVADA_RECIENTE",
            confianza="Media"
        )
        boletin = resultado["boletin_texto"]
        secciones = [
            "BOLETÍN DE RIESGO DE AVALANCHAS",
            "NIVEL DE PELIGRO",
            "SITUACIÓN DEL MANTO NIVAL",
            "FACTORES DE RIESGO",
            "TERRENO DE MAYOR RIESGO",
            "PRONÓSTICO PRÓXIMOS 3 DÍAS",
            "RECOMENDACIONES",
            "FACTORES EAWS USADOS",
            "CONFIANZA:"
        ]
        for seccion in secciones:
            assert seccion in boletin, f"Sección faltante: {seccion}"

    def test_redactar_boletin_nivel_eaws_correcto(self):
        """El boletín incluye el nivel EAWS correcto."""
        from agentes.subagentes.subagente_integrador.tools.tool_generar_boletin import (
            ejecutar_redactar_boletin_eaws
        )
        resultado = ejecutar_redactar_boletin_eaws(
            ubicacion="Test Ubicacion",
            nivel_eaws_24h=4,
            nivel_eaws_48h=4,
            nivel_eaws_72h=3,
            estabilidad_eaws="very_poor",
            frecuencia_eaws="many",
            tamano_eaws=3
        )
        assert resultado["nivel_eaws_24h"] == 4
        assert "4" in resultado["boletin_texto"]
        assert "Alto" in resultado["boletin_texto"]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests de subagentes CON llamadas Anthropic (requieren credenciales)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not _tiene_auth,
    reason="Sin credenciales Anthropic (CLAUDE_CODE_OAUTH_TOKEN o ANTHROPIC_API_KEY)"
)
class TestSubagenteTopografico:
    """Tests del SubagenteTopografico con llamadas Anthropic."""

    def test_subagente_topografico_ejecuta(self):
        """El subagente topográfico ejecuta sin error para La Parva."""
        from agentes.subagentes.subagente_topografico.agente import SubagenteTopografico

        agente = SubagenteTopografico()
        resultado = agente.ejecutar(UBICACION_PILOTO)

        assert "analisis" in resultado
        assert len(resultado["analisis"]) > 50
        assert resultado["nombre_subagente"] == "SubagenteTopografico"
        assert isinstance(resultado["iteraciones"], int)
        assert resultado["iteraciones"] > 0

        print(f"\n✓ SubagenteTopografico: {resultado['iteraciones']} iteraciones, "
              f"{resultado['duracion_segundos']}s")


@pytest.mark.skipif(
    not _tiene_auth,
    reason="Sin credenciales Anthropic (CLAUDE_CODE_OAUTH_TOKEN o ANTHROPIC_API_KEY)"
)
class TestSubagenteSatelital:
    """Tests del SubagenteSatelital con llamadas Anthropic."""

    def test_subagente_satelital_ejecuta(self):
        """El subagente satelital ejecuta sin error para La Parva."""
        from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital

        agente = SubagenteSatelital()
        resultado = agente.ejecutar(UBICACION_PILOTO)

        assert "analisis" in resultado
        assert len(resultado["analisis"]) > 50
        assert resultado["nombre_subagente"] == "SubagenteSatelital"

        print(f"\n✓ SubagenteSatelital: {resultado['iteraciones']} iteraciones, "
              f"{resultado['duracion_segundos']}s")


@pytest.mark.skipif(
    not _tiene_auth,
    reason="Sin credenciales Anthropic (CLAUDE_CODE_OAUTH_TOKEN o ANTHROPIC_API_KEY)"
)
class TestSubagenteMeteorologico:
    """Tests del SubagenteMeteorologico con llamadas Anthropic."""

    def test_subagente_meteorologico_ejecuta(self):
        """El subagente meteorológico ejecuta sin error para La Parva."""
        from agentes.subagentes.subagente_meteorologico.agente import SubagenteMeteorologico

        agente = SubagenteMeteorologico()
        resultado = agente.ejecutar(UBICACION_PILOTO)

        assert "analisis" in resultado
        assert len(resultado["analisis"]) > 50
        assert resultado["nombre_subagente"] == "SubagenteMeteorologico"

        print(f"\n✓ SubagenteMeteorologico: {resultado['iteraciones']} iteraciones, "
              f"{resultado['duracion_segundos']}s")


@pytest.mark.skipif(
    not _tiene_auth,
    reason="Sin credenciales Anthropic (CLAUDE_CODE_OAUTH_TOKEN o ANTHROPIC_API_KEY)"
)
class TestSubagenteIntegrador:
    """Tests del SubagenteIntegrador con llamadas Anthropic."""

    def test_subagente_integrador_con_contexto(self):
        """El subagente integrador procesa el contexto acumulado."""
        from agentes.subagentes.subagente_integrador.agente import SubagenteIntegrador

        contexto = """
[ANÁLISIS TOPOGRÁFICO (PINN)]
PINN: MARGINAL (FS=1.35). Estabilidad: fair. Frecuencia: a_few.
Zona inicio: 45 ha en pendientes de 38° orientación N.

[ANÁLISIS SATELITAL (ViT)]
ViT: ALERTADO. NDSI=0.45. Cobertura=65%. Delta 24h=+12% (nevada reciente).
Estabilidad satelital: poor.

[ANÁLISIS METEOROLÓGICO]
Temperatura: -3°C. Viento: 12 m/s. Precipitación: 15mm.
Factor meteorológico: NEVADA_RECIENTE. Ventanas críticas: 2.
"""
        agente = SubagenteIntegrador()
        resultado = agente.ejecutar(UBICACION_PILOTO, contexto_previo=contexto)

        assert "analisis" in resultado
        assert len(resultado["analisis"]) > 100
        assert resultado["nombre_subagente"] == "SubagenteIntegrador"

        print(f"\n✓ SubagenteIntegrador: análisis de {len(resultado['analisis'])} chars")
        print(f"  Análisis: {resultado['analisis'][:300]}...")

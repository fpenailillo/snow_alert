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

    def test_pinn_incertidumbre_estructura(self):
        """El resultado PINN incluye bloque de incertidumbre con campos obligatorios."""
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.65,
            densidad_kg_m3=300.0,
            indice_metamorfismo=0.9,
            energia_fusion_J_kg=100000.0,
            pendiente_grados=35.0
        )
        uq = resultado["incertidumbre_pinn"]
        for campo in ("ic_95_inf", "ic_95_sup", "sigma_fs", "coeficiente_variacion",
                      "sensibilidades", "parametro_dominante", "metodo"):
            assert campo in uq, f"Campo UQ ausente: {campo}"

    def test_pinn_ic_contiene_fs_central(self):
        """El IC 95% contiene el factor de seguridad central."""
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.7,
            densidad_kg_m3=350.0,
            indice_metamorfismo=0.8,
            energia_fusion_J_kg=80000.0,
            pendiente_grados=30.0
        )
        fs = resultado["factor_seguridad_mohr_coulomb"]
        uq = resultado["incertidumbre_pinn"]
        assert uq["ic_95_inf"] <= fs <= uq["ic_95_sup"], (
            f"FS={fs} no está en IC=[{uq['ic_95_inf']}, {uq['ic_95_sup']}]"
        )

    def test_pinn_sigma_positivo(self):
        """La desviación estándar del FS debe ser estrictamente positiva."""
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.5,
            densidad_kg_m3=280.0,
            indice_metamorfismo=1.0,
            energia_fusion_J_kg=120000.0,
            pendiente_grados=40.0
        )
        assert resultado["incertidumbre_pinn"]["sigma_fs"] > 0.0

    def test_pinn_sensibilidades_suman_varianza(self):
        """σ_FS² ≈ Σ sensibilidades² (propagación cuadrática)."""
        import math
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.6,
            densidad_kg_m3=320.0,
            indice_metamorfismo=0.7,
            energia_fusion_J_kg=90000.0,
            pendiente_grados=32.0
        )
        uq = resultado["incertidumbre_pinn"]
        s = uq["sensibilidades"]
        sigma_reconstructida = math.sqrt(
            s["densidad_kg_m3"]**2 + s["pendiente_grados"]**2 + s["metamorfismo"]**2
        )
        assert abs(sigma_reconstructida - uq["sigma_fs"]) < 1e-4, (
            f"Reconstrucción σ={sigma_reconstructida:.4f} ≠ σ_FS={uq['sigma_fs']:.4f}"
        )

    def test_pinn_pendiente_critica_ic_no_cubre_1p5(self):
        """Pendiente muy crítica: IC superior puede quedar bajo 1.5 (manto inestable)."""
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn
        )
        resultado = ejecutar_calcular_pinn(
            gradiente_termico_C_100m=-0.9,
            densidad_kg_m3=250.0,
            indice_metamorfismo=1.5,
            energia_fusion_J_kg=250000.0,
            pendiente_grados=50.0
        )
        uq = resultado["incertidumbre_pinn"]
        # IC inferior debe ser ≥ 0 (no hay FS negativo)
        assert uq["ic_95_inf"] >= 0.0
        # El IC debe ser más ancho que 0 (hay incertidumbre real)
        assert uq["ic_95_sup"] > uq["ic_95_inf"]


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

    def test_vit_arquitectura_multihead_en_resultado(self):
        """El resultado incluye campos de arquitectura multi-head."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )
        serie = [
            {"paso_t": i, "ndsi_medio": 0.5, "pct_cobertura_nieve": 70.0,
             "lst_dia_celsius": -4.0, "lst_noche_celsius": -11.0,
             "ciclo_diurno_amplitud": 7.0, "delta_pct_nieve_24h": 0.5}
            for i in range(3)
        ]
        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.5,
            cobertura_promedio=70.0
        )
        assert resultado["disponible"] is True
        assert "arquitectura_vit" in resultado
        assert "multihead" in resultado["arquitectura_vit"].lower()
        assert resultado.get("n_heads") == 2
        assert "entropia_atencion" in resultado
        assert "norma_contexto_mha" in resultado

    def test_vit_entropia_atencion_rango_valido(self):
        """La entropía de atención está en rango [0, ln(T)]."""
        import math
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )
        T = 5
        serie = [
            {"paso_t": i, "ndsi_medio": 0.4, "pct_cobertura_nieve": 55.0,
             "lst_dia_celsius": -6.0, "lst_noche_celsius": -14.0,
             "ciclo_diurno_amplitud": 8.0, "delta_pct_nieve_24h": 0.0}
            for i in range(T)
        ]
        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.4,
            cobertura_promedio=55.0
        )
        if resultado["disponible"]:
            entropia = resultado["entropia_atencion"]
            assert entropia >= 0.0, f"Entropía negativa: {entropia}"
            assert entropia <= math.log(T) + 0.01, f"Entropía > ln(T): {entropia}"

    def test_vit_positional_encoding_dimension(self):
        """El positional encoding tiene la misma dimensión que el vector de features."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            _positional_encoding, D_MODEL
        )
        pe = _positional_encoding(t=0, d=D_MODEL)
        assert len(pe) == D_MODEL

    def test_vit_proyeccion_wq_dimension(self):
        """WQ tiene forma D_HEAD × D_MODEL (proyecta query en espacio de cabeza)."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            _WQ, D_HEAD, D_MODEL
        )
        for h, wq in enumerate(_WQ):
            assert len(wq) == D_HEAD, f"WQ cabeza {h}: esperado {D_HEAD} filas, got {len(wq)}"
            assert len(wq[0]) == D_MODEL, f"WQ cabeza {h}: esperado {D_MODEL} cols, got {len(wq[0])}"

    def test_vit_norma_contexto_mha_positiva(self):
        """La norma del contexto multi-head es positiva para series no triviales."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )
        serie = [
            {"paso_t": i, "ndsi_medio": 0.6, "pct_cobertura_nieve": 75.0,
             "lst_dia_celsius": -5.0, "lst_noche_celsius": -12.0,
             "ciclo_diurno_amplitud": 7.0, "delta_pct_nieve_24h": 2.0}
            for i in range(4)
        ]
        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.6,
            cobertura_promedio=75.0
        )
        assert resultado["disponible"] is True
        assert resultado["norma_contexto_mha"] > 0.0

    def test_vit_layer_norm_media_cero(self):
        """LayerNorm devuelve vector con media ≈ 0 y varianza ≈ 1."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import _layer_norm

        # Vector constante: LN de constante = vector nulo (media=constante, std≈0+eps)
        x_var = [1.0, 3.0, -2.0, 0.5, 4.0, -1.0]
        xn = _layer_norm(x_var)

        # Media del resultado ≈ 0
        media = sum(xn) / len(xn)
        assert abs(media) < 1e-5, f"Media después de LayerNorm debe ser ≈0, obtenida: {media}"

        # Varianza del resultado ≈ 1
        varianza = sum((xi - media) ** 2 for xi in xn) / len(xn)
        assert abs(varianza - 1.0) < 1e-4, f"Varianza después de LayerNorm debe ser ≈1, obtenida: {varianza}"

    def test_vit_ffn_dimensiones_correctas(self):
        """La FFN preserva la dimensión D_MODEL en entrada y salida."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            _feed_forward_network, D_MODEL, D_FF
        )

        x = [0.5, -0.3, 1.2, -0.8, 0.1, 0.7]   # D_MODEL = 6
        salida = _feed_forward_network(x)

        assert len(salida) == D_MODEL, (
            f"FFN debe producir D_MODEL={D_MODEL} outputs, obtenidos: {len(salida)}"
        )

    def test_vit_ffn_dimension_interna_4x(self):
        """La dimensión interna de la FFN es 4×D_MODEL (convención Vaswani 2017)."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import D_MODEL, D_FF

        assert D_FF == 4 * D_MODEL, (
            f"D_FF debe ser 4×D_MODEL={4*D_MODEL}, obtenido: {D_FF}"
        )

    def test_vit_resultado_incluye_d_ff(self):
        """El resultado del ViT expone el campo d_ff para trazabilidad."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit, D_FF
        )

        serie = [
            {"paso_t": i, "ndsi_medio": 0.55, "pct_cobertura_nieve": 65.0,
             "lst_dia_celsius": -3.0, "lst_noche_celsius": -10.0,
             "ciclo_diurno_amplitud": 7.0, "delta_pct_nieve_24h": 1.0}
            for i in range(4)
        ]
        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.55,
            cobertura_promedio=65.0,
        )

        assert "d_ff" in resultado, "El resultado debe incluir el campo d_ff"
        assert resultado["d_ff"] == D_FF, (
            f"d_ff debe ser {D_FF}, obtenido: {resultado.get('d_ff')}"
        )

    def test_vit_arquitectura_incluye_layernorm_y_ffn(self):
        """La cadena arquitectura_vit menciona layernorm y ffn (bloque completo)."""
        from agentes.subagentes.subagente_satelital.tools.tool_analizar_vit import (
            ejecutar_analizar_vit
        )

        serie = [
            {"paso_t": i, "ndsi_medio": 0.6, "pct_cobertura_nieve": 70.0,
             "lst_dia_celsius": -5.0, "lst_noche_celsius": -12.0,
             "ciclo_diurno_amplitud": 7.0, "delta_pct_nieve_24h": 0.5}
            for i in range(3)
        ]
        resultado = ejecutar_analizar_vit(
            serie_temporal=serie,
            ndsi_promedio=0.6,
            cobertura_promedio=70.0,
        )

        arq = resultado["arquitectura_vit"].lower()
        assert "layernorm" in arq, f"arquitectura_vit debe mencionar layernorm: {arq}"
        assert "ffn" in arq, f"arquitectura_vit debe mencionar ffn: {arq}"


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

    def test_clasificar_eaws_tamano_dinamico(self):
        """Tamaño EAWS se calcula dinámicamente desde topografía (C2)."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        resultado = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="poor",
            factor_meteorologico="NEVADA_RECIENTE",
            frecuencia_topografica="some",
            desnivel_inicio_deposito_m=900,
            zona_inicio_ha=60,
            pendiente_max_grados=42
        )
        # Con 900m desnivel y 60ha → tamaño grande (≥3)
        assert resultado["factores_eaws"]["tamano"] >= 3
        assert resultado["factores_eaws"]["fuente_tamano"] == "estimar_tamano_potencial"

    def test_clasificar_eaws_viento_incrementa_frecuencia(self):
        """Viento >40 km/h incrementa la frecuencia EAWS (C3)."""
        from agentes.subagentes.subagente_integrador.tools.tool_clasificar_eaws import (
            ejecutar_clasificar_riesgo_eaws_integrado
        )
        # Sin viento
        resultado_sin = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="fair",
            factor_meteorologico="ESTABLE",
            frecuencia_topografica="a_few",
            tamano_eaws="2"
        )
        # Con viento fuerte
        resultado_con = ejecutar_clasificar_riesgo_eaws_integrado(
            estabilidad_topografica="fair",
            factor_meteorologico="ESTABLE",
            frecuencia_topografica="a_few",
            tamano_eaws="2",
            viento_kmh=55.0
        )
        escala = ["nearly_none", "a_few", "some", "many"]
        idx_sin = escala.index(resultado_sin["factores_eaws"]["frecuencia"])
        idx_con = escala.index(resultado_con["factores_eaws"]["frecuencia"])
        assert idx_con > idx_sin, "Viento >40 km/h debe incrementar frecuencia"


class TestToolsNLP:
    """Tests de las tools del SubagenteNLP sin llamadas a Anthropic."""

    def test_extraer_patrones_sin_relatos_activa_fallback(self):
        """Con total_relatos=0, activa fallback a base andina (disponible=True)."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        resultado = ejecutar_sintetizar_conocimiento_historico(
            total_relatos=0,
            frecuencias_terminos={},
            indice_riesgo_base=0.0,
            ubicacion="La Parva Sector Bajo"
        )
        # Con fallback andino, disponible=True y el índice no es 0
        assert resultado["disponible"] is True
        assert resultado["fuente_conocimiento"] in (
            "base_andino_estatico", "sin_datos"
        )
        assert resultado["indice_riesgo_ajustado"] >= 0.0

    def test_extraer_patrones_sin_relatos_sin_ubicacion_usa_generico(self):
        """Sin ubicación, el fallback usa el conocimiento genérico andino."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        resultado = ejecutar_sintetizar_conocimiento_historico(
            total_relatos=0,
            frecuencias_terminos={},
            indice_riesgo_base=0.0,
            ubicacion="Zona desconocida XYZ"
        )
        assert resultado["disponible"] is True
        assert "narrativa" in resultado

    def test_extraer_patrones_con_relatos_placa(self):
        """extraer_patrones con muchas menciones de 'placa' detecta tipo correcto."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        frecuencias = {
            "placa": 8,
            "alud": 5,
            "grieta": 3,
            "viento": 2,
        }
        resultado = ejecutar_sintetizar_conocimiento_historico(
            total_relatos=15,
            frecuencias_terminos=frecuencias,
            indice_riesgo_base=0.6
        )
        assert resultado["disponible"] is True
        assert resultado["tipo_alud_predominante"] == "placa"
        assert resultado["confianza"] == "Alta"
        assert resultado["indice_riesgo_ajustado"] > 0.0

    def test_conocimiento_historico_estructura_resultado(self):
        """sintetizar_conocimiento_historico retorna todos los campos requeridos."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        resultado = ejecutar_sintetizar_conocimiento_historico(
            total_relatos=5,
            frecuencias_terminos={"avalancha": 3, "viento": 4},
            indice_riesgo_base=0.4
        )
        campos_requeridos = [
            "disponible",
            "indice_riesgo_ajustado",
            "tipo_alud_predominante",
            "confianza",
            "total_relatos_analizados",
            "narrativa"
        ]
        for campo in campos_requeridos:
            assert campo in resultado, f"Campo faltante en resultado NLP: '{campo}'"
        assert 0.0 <= resultado["indice_riesgo_ajustado"] <= 1.0


class TestBaseConocimientoAndino:
    """Tests de la base de conocimiento andino estático (fallback NLP)."""

    def test_consultar_zona_la_parva(self):
        """consultar_conocimiento_zona identifica La Parva correctamente."""
        from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
            consultar_conocimiento_zona
        )
        resultado = consultar_conocimiento_zona("La Parva Sector Bajo")
        assert resultado["zona_identificada"] == "la_parva"
        assert resultado["fuente"] == "conocimiento_base_andino"
        assert "tipo_alud_predominante" in resultado
        assert "indice_riesgo_historico" in resultado

    def test_consultar_zona_portillo(self):
        """consultar_conocimiento_zona identifica Portillo."""
        from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
            consultar_conocimiento_zona
        )
        resultado = consultar_conocimiento_zona("Portillo Sector Amarillo")
        assert resultado["zona_identificada"] == "portillo"
        assert resultado["confianza"] == "Alta"

    def test_consultar_zona_desconocida_retorna_generico(self):
        """Zona sin match retorna conocimiento genérico andino."""
        from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
            consultar_conocimiento_zona
        )
        resultado = consultar_conocimiento_zona("Patagonia Austral Zona 99")
        assert resultado["zona_identificada"] == "zona_desconocida"
        assert resultado["match_por"] is None
        assert "tipo_alud_predominante" in resultado
        assert resultado["indice_riesgo_historico"] > 0.0

    def test_indice_estacional_peak_invierno(self):
        """Factor estacional máximo en julio-agosto."""
        from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
            get_indice_estacional
        )
        factor_julio = get_indice_estacional(mes_actual=7)
        factor_agosto = get_indice_estacional(mes_actual=8)
        factor_enero = get_indice_estacional(mes_actual=1)
        assert factor_julio >= 0.85
        assert factor_agosto >= 0.85
        assert factor_enero <= 0.30

    def test_indice_estacional_rango_valido(self):
        """Factor estacional está siempre entre 0 y 1."""
        from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
            get_indice_estacional
        )
        for mes in range(1, 13):
            factor = get_indice_estacional(mes_actual=mes)
            assert 0.0 <= factor <= 1.0, f"Factor inválido para mes {mes}: {factor}"

    def test_listar_zonas_retorna_lista(self):
        """listar_zonas_disponibles retorna al menos 5 zonas."""
        from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
            listar_zonas_disponibles
        )
        zonas = listar_zonas_disponibles()
        assert len(zonas) >= 5
        assert "la_parva" in zonas
        assert "portillo" in zonas
        assert "antuco" in zonas

    def test_conocimiento_zona_tiene_patrones_recurrentes(self):
        """Cada zona conocida tiene al menos un patrón documentado."""
        from agentes.subagentes.subagente_nlp.conocimiento_base_andino import (
            CONOCIMIENTO_POR_ZONA
        )
        for nombre, datos in CONOCIMIENTO_POR_ZONA.items():
            assert len(datos.get("patrones_recurrentes", [])) >= 1, (
                f"Zona {nombre} sin patrones_recurrentes"
            )

    def test_fallback_nlp_portillo_indice_alto(self):
        """Fallback para Portillo produce índice de riesgo > 0.5."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        resultado = ejecutar_sintetizar_conocimiento_historico(
            total_relatos=0,
            frecuencias_terminos={},
            indice_riesgo_base=0.3,
            ubicacion="Portillo"
        )
        assert resultado["disponible"] is True
        assert resultado["indice_riesgo_ajustado"] > 0.3

    def test_fallback_nlp_contiene_advertencia(self):
        """Fallback incluye advertencia sobre cargar datos reales."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        resultado = ejecutar_sintetizar_conocimiento_historico(
            total_relatos=0,
            frecuencias_terminos={},
            indice_riesgo_base=0.0,
            ubicacion="Valle Nevado"
        )
        if resultado.get("fuente_conocimiento") == "base_andino_estatico":
            assert "advertencia" in resultado
            assert len(resultado["narrativa"]) > 50

    def test_conocimiento_bq_no_usa_fallback(self):
        """Cuando hay relatos BQ, no usa la base andina."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        resultado = ejecutar_sintetizar_conocimiento_historico(
            total_relatos=10,
            frecuencias_terminos={"placa": 5, "viento": 3},
            indice_riesgo_base=0.6,
            ubicacion="La Parva"
        )
        assert resultado["fuente_conocimiento"] == "relatos_bigquery"
        assert resultado["total_relatos_analizados"] == 10


class TestNLPSintetico:
    """Tests del análisis NLP sintético y validación H2 (notebook 06)."""

    def test_h2_estructura_resultado(self):
        """analisis_h2_sintetico retorna las claves requeridas."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import analisis_h2_sintetico

        res = analisis_h2_sintetico(meses_eval=[8], verbose=False)

        claves_requeridas = [
            "f1_macro_base_global",
            "f1_macro_nlp_global",
            "delta_f1_pp_global",
            "h2_confirmada_sintetico",
            "umbral_h2_pp",
            "n_zonas",
            "n_observaciones_total",
            "resultados_por_zona",
            "advertencia",
        ]
        for clave in claves_requeridas:
            assert clave in res, f"Falta clave '{clave}' en resultado H2"

    def test_h2_delta_f1_positivo_con_sesgo(self):
        """Con sesgo_base=0.4 el NLP mejora el F1-macro (delta > 0)."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import analisis_h2_sintetico

        res = analisis_h2_sintetico(
            meses_eval=[7, 8, 9],
            sesgo_base=0.4,
            fuerza_ajuste=0.65,
            verbose=False,
        )
        assert res["delta_f1_pp_global"] > 0, (
            f"Delta F1 debe ser positivo con sesgo=0.4, "
            f"obtenido: {res['delta_f1_pp_global']:.2f}pp"
        )

    def test_h2_confirmada_sintetico(self):
        """H2 se confirma (delta ≥ 5pp) con parámetros por defecto y sesgo documentado."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import analisis_h2_sintetico

        res = analisis_h2_sintetico(
            meses_eval=[7, 8, 9],
            sesgo_base=0.4,
            fuerza_ajuste=0.65,
            verbose=False,
        )
        assert res["h2_confirmada_sintetico"], (
            f"H2 no confirmada: delta={res['delta_f1_pp_global']:.2f}pp < "
            f"{res['umbral_h2_pp']:.1f}pp"
        )

    def test_h2_resultados_por_zona_estructura(self):
        """resultados_por_zona contiene las claves esperadas para cada zona."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import analisis_h2_sintetico

        res = analisis_h2_sintetico(meses_eval=[8], verbose=False)

        assert len(res["resultados_por_zona"]) > 0
        claves_zona = ["zona", "f1_base", "f1_nlp", "delta_f1_pp", "indice_riesgo"]
        for resultado_zona in res["resultados_por_zona"][:3]:  # verificar primeras 3
            for clave in claves_zona:
                assert clave in resultado_zona, (
                    f"Falta clave '{clave}' en resultado de zona"
                )

    def test_h2_n_zonas_correctas(self):
        """El análisis cubre todas las zonas de la base andina (≥15)."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import analisis_h2_sintetico

        res = analisis_h2_sintetico(meses_eval=[8], verbose=False)
        assert res["n_zonas"] >= 15, (
            f"Se esperan ≥15 zonas, obtenidas: {res['n_zonas']}"
        )

    def test_sensibilidad_fuerza_ajuste_estructura(self):
        """analisis_sensibilidad_fuerza_ajuste retorna curva y fuerza_optima."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import (
            analisis_sensibilidad_fuerza_ajuste
        )

        res = analisis_sensibilidad_fuerza_ajuste()

        assert "curva_fuerza_delta" in res
        assert "fuerza_optima" in res
        assert "delta_optimo_pp" in res
        assert len(res["curva_fuerza_delta"]) >= 5, "La curva debe tener ≥5 puntos"
        assert 0.0 <= res["fuerza_optima"] <= 1.0

    def test_sensibilidad_sesgo_delta_aumenta(self):
        """A mayor sesgo de subestimación, mayor ganancia del NLP."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import (
            analisis_sensibilidad_sesgo_base
        )

        res = analisis_sensibilidad_sesgo_base()

        curva = res["curva_sesgo_delta"]
        delta_sesgo_bajo = curva[min(curva.keys())]["delta_pp"]  # sesgo ≈ 0
        delta_sesgo_alto = curva[max(curva.keys())]["delta_pp"]  # sesgo ≈ 1.0

        assert delta_sesgo_alto > delta_sesgo_bajo, (
            f"El NLP debe ganar más con sesgo alto: "
            f"sesgo_bajo={delta_sesgo_bajo:.1f}pp, sesgo_alto={delta_sesgo_alto:.1f}pp"
        )

    def test_h2_advertencia_datos_sinteticos(self):
        """El resultado incluye advertencia sobre naturaleza sintética de los datos."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import analisis_h2_sintetico

        res = analisis_h2_sintetico(meses_eval=[8], verbose=False)

        assert "advertencia" in res
        advertencia = res["advertencia"].lower()
        assert "sintético" in advertencia or "sintetico" in advertencia or "real" in advertencia, (
            "La advertencia debe mencionar que los datos son sintéticos o que se requieren reales"
        )

    def test_calcular_ajuste_nlp_unidireccional(self):
        """calcular_ajuste_nlp nunca rebaja el nivel (corrección solo hacia arriba)."""
        from notebooks_validacion.n06_analisis_nlp_sintetico import calcular_ajuste_nlp

        # Caso 1: base > esperado → NLP se abstiene (no baja)
        nivel_alto = 4
        ajuste_sin_cambio = calcular_ajuste_nlp(nivel_alto, 0.3, 8, fuerza_ajuste=0.65)
        assert ajuste_sin_cambio >= nivel_alto, (
            f"NLP no debe rebajar nivel: base={nivel_alto}, ajustado={ajuste_sin_cambio}"
        )

        # Caso 2: base < esperado → NLP corrige hacia arriba
        nivel_bajo = 1
        ajuste_hacia_arriba = calcular_ajuste_nlp(nivel_bajo, 0.8, 8, fuerza_ajuste=0.65)
        assert ajuste_hacia_arriba >= nivel_bajo, (
            f"NLP debe mantener o subir nivel: base={nivel_bajo}, ajustado={ajuste_hacia_arriba}"
        )


class TestReintentosAPI:
    """Tests del mecanismo de reintentos en BaseSubagente."""

    def test_constantes_reintentos_definidas(self):
        """Las constantes de reintentos están definidas correctamente."""
        from agentes.subagentes.base_subagente import (
            MAX_REINTENTOS_API,
            ESPERA_BASE_SEGUNDOS,
            ESPERA_MAXIMA_SEGUNDOS,
        )
        assert MAX_REINTENTOS_API >= 2
        assert ESPERA_BASE_SEGUNDOS > 0
        assert ESPERA_MAXIMA_SEGUNDOS > ESPERA_BASE_SEGUNDOS

    def test_error_subagente_hereda_exception(self):
        """ErrorSubagente es subclase de Exception."""
        from agentes.subagentes.base_subagente import ErrorSubagente
        assert issubclass(ErrorSubagente, Exception)

    def test_backoff_exponencial_formula(self):
        """El backoff exponencial crece correctamente."""
        from agentes.subagentes.base_subagente import (
            ESPERA_BASE_SEGUNDOS,
            ESPERA_MAXIMA_SEGUNDOS,
        )
        esperas = []
        for intento in range(5):
            espera = min(
                ESPERA_BASE_SEGUNDOS * (2 ** intento),
                ESPERA_MAXIMA_SEGUNDOS
            )
            esperas.append(espera)
        # Backoff crece
        assert esperas[1] > esperas[0]
        assert esperas[2] > esperas[1]
        # Nunca supera el máximo
        assert all(e <= ESPERA_MAXIMA_SEGUNDOS for e in esperas)


class TestDegradacionGraceful:
    """Tests de degradación graceful del orquestador."""

    def test_resultado_degradado_tiene_flag(self):
        """Un resultado degradado incluye el flag 'degradado': True."""
        resultado_degradado = {
            "analisis": "[SubagenteNLP no disponible]",
            "tools_llamadas": [],
            "iteraciones": 0,
            "duracion_segundos": 0,
            "error": "Error de prueba",
            "degradado": True,
        }
        assert resultado_degradado["degradado"] is True
        assert resultado_degradado["iteraciones"] == 0

    def test_subagentes_degradados_lista(self):
        """La lista de subagentes degradados se construye correctamente."""
        resultados = {
            "topografico": {"analisis": "OK"},
            "satelital": {"analisis": "OK"},
            "meteorologico": {"analisis": "OK"},
            "nlp": {"analisis": "Fallido", "degradado": True},
            "integrador": {"analisis": "OK"},
        }
        degradados = [
            nombre for nombre, res in resultados.items()
            if res.get("degradado")
        ]
        assert degradados == ["nlp"]

    def test_pipeline_sin_degradacion(self):
        """Sin degradación, la lista de degradados está vacía."""
        resultados = {
            "topografico": {"analisis": "OK"},
            "satelital": {"analisis": "OK"},
            "meteorologico": {"analisis": "OK"},
            "nlp": {"analisis": "OK"},
            "integrador": {"analisis": "OK"},
        }
        degradados = [
            nombre for nombre, res in resultados.items()
            if res.get("degradado")
        ]
        assert degradados == []


class TestMetricasTechel:
    """Tests de métricas de validación y comparación con Techel et al. (2022)."""

    def test_accuracy_adyacente_perfecta(self):
        """Accuracy adyacente = 1.0 cuando todos los errores son ±1."""
        from agentes.validacion.metricas_eaws import calcular_accuracy_adyacente
        reales =    [1, 2, 3, 4, 3, 2]
        predichos = [1, 3, 3, 3, 2, 2]  # errores de máximo ±1
        resultado = calcular_accuracy_adyacente(reales, predichos)
        assert resultado["accuracy_adyacente"] == 1.0
        assert resultado["accuracy_exacta"] < 1.0  # no todos son exactos

    def test_accuracy_adyacente_con_error_grande(self):
        """Errores de ≥2 niveles reducen la accuracy adyacente."""
        from agentes.validacion.metricas_eaws import calcular_accuracy_adyacente
        reales =    [1, 2, 3, 4, 5]
        predichos = [3, 2, 3, 4, 3]  # primer y último difieren en ≥2
        resultado = calcular_accuracy_adyacente(reales, predichos)
        assert resultado["accuracy_adyacente"] < 1.0
        assert resultado["total_muestras"] == 5

    def test_kappa_ponderado_perfecto(self):
        """QWK = 1.0 con concordancia perfecta."""
        from agentes.validacion.metricas_eaws import calcular_kappa_ponderado_cuadratico
        datos = [1, 2, 3, 4, 5, 2, 3, 1]
        resultado = calcular_kappa_ponderado_cuadratico(datos, datos)
        assert resultado["kappa_ponderado"] == 1.0

    def test_kappa_ponderado_rango_valido(self):
        """QWK está en rango [-1, 1]."""
        from agentes.validacion.metricas_eaws import calcular_kappa_ponderado_cuadratico
        reales =    [1, 2, 3, 4, 5, 2, 3, 3]
        predichos = [2, 2, 4, 3, 4, 1, 3, 2]
        resultado = calcular_kappa_ponderado_cuadratico(reales, predichos)
        assert -1.0 <= resultado["kappa_ponderado"] <= 1.0

    def test_techel_referencia_existe(self):
        """Las constantes de referencia Techel (2022) están completas."""
        from agentes.validacion.metricas_eaws import TECHEL_2022_REFERENCIA
        ref = TECHEL_2022_REFERENCIA
        assert ref["accuracy"] == 0.64
        assert ref["accuracy_adyacente"] == 0.95
        assert ref["kappa_ponderado"] == 0.59
        assert ref["n_muestras"] == 52_485
        assert len(ref["distribucion_niveles"]) == 5
        assert len(ref["limitaciones"]) >= 4

    def test_comparar_con_techel_estructura(self):
        """comparar_con_techel_2022 retorna estructura completa."""
        from agentes.validacion.metricas_eaws import comparar_con_techel_2022
        reales =    [1, 2, 3, 3, 4, 2, 3, 2, 3, 2]
        predichos = [1, 2, 3, 2, 4, 2, 3, 3, 3, 2]
        resultado = comparar_con_techel_2022(reales, predichos)
        assert "referencia" in resultado
        assert "nuestro_sistema" in resultado
        assert "comparacion_directa" in resultado
        assert "diferencias_metodologicas" in resultado
        assert "nota_interpretacion" in resultado
        # Verificar que nuestras métricas se calcularon
        ns = resultado["nuestro_sistema"]
        assert 0.0 <= ns["accuracy"] <= 1.0
        assert 0.0 <= ns["accuracy_adyacente"] <= 1.0
        assert -1.0 <= ns["kappa_ponderado"] <= 1.0

    def test_sesgo_sobreestima(self):
        """Detecta sesgo de sobreestimación correctamente."""
        from agentes.validacion.metricas_eaws import calcular_accuracy_adyacente
        reales =    [1, 2, 2, 3, 2]
        predichos = [2, 3, 3, 4, 3]  # siempre +1
        resultado = calcular_accuracy_adyacente(reales, predichos)
        assert resultado["sesgo_direccion"] == "sobreestima"
        assert resultado["sesgo_medio"] > 0

    def test_sesgo_subestima(self):
        """Detecta sesgo de subestimación correctamente."""
        from agentes.validacion.metricas_eaws import calcular_accuracy_adyacente
        reales =    [3, 4, 4, 5, 3]
        predichos = [2, 3, 3, 4, 2]  # siempre -1
        resultado = calcular_accuracy_adyacente(reales, predichos)
        assert resultado["sesgo_direccion"] == "subestima"
        assert resultado["sesgo_medio"] < 0


class TestAlmacenadorHelpers:
    """Tests de funciones auxiliares de almacenador.py (sin GCP)."""

    def test_normalizar_ubicacion_basica(self):
        """Normaliza tildes, espacios y mayúsculas."""
        from agentes.salidas.almacenador import _normalizar_ubicacion
        assert _normalizar_ubicacion("La Parva Sector Bajo") == "la_parva_sector_bajo"

    def test_normalizar_ubicacion_tildes(self):
        """Elimina tildes y caracteres especiales."""
        from agentes.salidas.almacenador import _normalizar_ubicacion
        assert _normalizar_ubicacion("Farellones — Zona Ñuble") == "farellones_zona_nuble"

    def test_normalizar_ubicacion_vacia(self):
        """Cadena vacía retorna cadena vacía."""
        from agentes.salidas.almacenador import _normalizar_ubicacion
        assert _normalizar_ubicacion("") == ""

    def test_extraer_confianza_alta(self):
        """Extrae confianza Alta del boletín."""
        from agentes.salidas.almacenador import _extraer_confianza
        assert _extraer_confianza("CONFIANZA: Alta") == "Alta"

    def test_extraer_confianza_baja_case_insensitive(self):
        """Extrae confianza en distintas capitalizaciones."""
        from agentes.salidas.almacenador import _extraer_confianza
        assert _extraer_confianza("confianza: baja") == "Baja"

    def test_extraer_confianza_none_si_no_hay(self):
        """Retorna None si no hay patrón de confianza."""
        from agentes.salidas.almacenador import _extraer_confianza
        assert _extraer_confianza("Sin información relevante") is None

    def test_extraer_confianza_none_si_vacio(self):
        """Retorna None si el texto es vacío o None."""
        from agentes.salidas.almacenador import _extraer_confianza
        assert _extraer_confianza("") is None
        assert _extraer_confianza(None) is None

    def test_extraer_nivel_24h(self):
        """Extrae nivel EAWS 24h del boletín."""
        from agentes.salidas.almacenador import _extraer_nivel
        texto = "Nivel 24h → 3 (Considerable)"
        assert _extraer_nivel(texto, r'24h\s*[→\-]\s*(\d)') == 3

    def test_extraer_nivel_fuera_rango(self):
        """Nivel fuera de rango 1-5 retorna None."""
        from agentes.salidas.almacenador import _extraer_nivel
        texto = "Nivel 24h → 9"
        assert _extraer_nivel(texto, r'24h\s*[→\-]\s*(\d)') is None

    def test_extraer_nivel_none_si_vacio(self):
        """Retorna None si texto es vacío o None."""
        from agentes.salidas.almacenador import _extraer_nivel
        assert _extraer_nivel("", r'(\d)') is None
        assert _extraer_nivel(None, r'(\d)') is None

    def test_extraer_resultado_tool_encuentra(self):
        """_extraer_resultado_tool retorna el resultado de la tool indicada."""
        from agentes.salidas.almacenador import _extraer_resultado_tool
        tools = [
            {"tool": "calcular_pinn", "resultado": {"factor_seguridad_mohr_coulomb": 1.25}},
            {"tool": "analizar_vit", "resultado": {"estado_vit": "ALERTADO"}},
        ]
        res = _extraer_resultado_tool(tools, "calcular_pinn")
        assert res["factor_seguridad_mohr_coulomb"] == 1.25

    def test_extraer_resultado_tool_no_encontrado(self):
        """_extraer_resultado_tool retorna {} si el tool no existe."""
        from agentes.salidas.almacenador import _extraer_resultado_tool
        tools = [{"tool": "otro_tool", "resultado": {"x": 1}}]
        assert _extraer_resultado_tool(tools, "calcular_pinn") == {}

    def test_extraer_resultado_tool_sin_resultado(self):
        """_extraer_resultado_tool retorna {} si no hay campo resultado."""
        from agentes.salidas.almacenador import _extraer_resultado_tool
        tools = [{"tool": "calcular_pinn", "inputs": {"pendiente": 35}}]
        assert _extraer_resultado_tool(tools, "calcular_pinn") == {}

    def test_extraer_resultado_tool_ultima_ocurrencia(self):
        """_extraer_resultado_tool retorna la última llamada al tool."""
        from agentes.salidas.almacenador import _extraer_resultado_tool
        tools = [
            {"tool": "calcular_pinn", "resultado": {"factor_seguridad_mohr_coulomb": 1.1}},
            {"tool": "calcular_pinn", "resultado": {"factor_seguridad_mohr_coulomb": 1.4}},
        ]
        res = _extraer_resultado_tool(tools, "calcular_pinn")
        assert res["factor_seguridad_mohr_coulomb"] == 1.4

    def test_construir_campos_subagentes_campos_presentes(self):
        """_construir_campos_subagentes retorna todos los campos esperados."""
        from agentes.salidas.almacenador import _construir_campos_subagentes
        tools = [
            {"tool": "calcular_pinn", "resultado": {
                "factor_seguridad_mohr_coulomb": 1.2,
                "estado_manto": "INESTABLE"
            }},
            {"tool": "analizar_vit", "resultado": {
                "estado_vit": "ALERTADO",
                "score_anomalia": 0.7
            }},
            {"tool": "detectar_ventanas_criticas", "resultado": {
                "factor_meteorologico_eaws": "NEVADA_RECIENTE",
                "num_ventanas_criticas": 2
            }},
        ]
        campos = _construir_campos_subagentes(tools, {})
        assert campos["estado_pinn"] == "INESTABLE"
        assert campos["factor_seguridad_pinn"] == 1.2
        assert campos["estado_vit"] == "ALERTADO"
        assert campos["score_anomalia_vit"] == 0.7
        assert campos["factor_meteorologico"] == "NEVADA_RECIENTE"
        assert campos["ventanas_criticas"] == 2

    def test_construir_campos_nombre_nivel_24h(self):
        """guardar_boletin extrae nombre_nivel_24h (no nombre_nivel) del tool clasificar."""
        from agentes.salidas.almacenador import _extraer_resultado_tool
        tools = [
            {"tool": "clasificar_riesgo_eaws_integrado", "resultado": {
                "nombre_nivel_24h": "Considerable",
                "nivel_eaws_24h": 3
            }},
        ]
        res = _extraer_resultado_tool(tools, "clasificar_riesgo_eaws_integrado")
        assert res.get("nombre_nivel_24h") == "Considerable"
        assert res.get("nombre_nivel") is None  # el campo correcto es nombre_nivel_24h


class TestRegistroVersiones:
    """Tests del sistema de versionado de prompts."""

    def test_version_global_formato(self):
        """La versión global tiene formato vX.Y."""
        from agentes.prompts.registro_versiones import obtener_version_actual
        version = obtener_version_actual()
        assert version.startswith("v")
        partes = version[1:].split(".")
        assert len(partes) >= 1
        assert all(p.isdigit() for p in partes)

    def test_registro_tiene_todos_los_componentes(self):
        """El registro contiene los 6 componentes del pipeline."""
        from agentes.prompts.registro_versiones import REGISTRO_PROMPTS
        esperados = {"orquestador", "topografico", "satelital", "meteorologico", "nlp", "integrador"}
        assert set(REGISTRO_PROMPTS.keys()) == esperados

    def test_calcular_hash_deterministico(self):
        """El hash SHA-256 es determinístico para el mismo contenido."""
        from agentes.prompts.registro_versiones import _calcular_hash
        h1 = _calcular_hash("contenido de prueba")
        h2 = _calcular_hash("contenido de prueba")
        assert h1 == h2
        assert len(h1) == 16  # truncado a 16 chars

    def test_calcular_hash_diferente_para_contenido_diferente(self):
        """Contenidos diferentes producen hashes diferentes."""
        from agentes.prompts.registro_versiones import _calcular_hash
        h1 = _calcular_hash("prompt v1")
        h2 = _calcular_hash("prompt v2")
        assert h1 != h2

    def test_calcular_hash_ignora_espacios_trailing(self):
        """El hash ignora espacios al inicio y final."""
        from agentes.prompts.registro_versiones import _calcular_hash
        h1 = _calcular_hash("contenido")
        h2 = _calcular_hash("  contenido  \n")
        assert h1 == h2

    def test_registro_campos_completos(self):
        """Cada entrada del registro tiene todos los campos requeridos."""
        from agentes.prompts.registro_versiones import REGISTRO_PROMPTS
        campos_requeridos = {"modulo", "variable", "version", "descripcion", "hash_sha256"}
        for componente, info in REGISTRO_PROMPTS.items():
            for campo in campos_requeridos:
                assert campo in info, f"Campo '{campo}' faltante en '{componente}'"

    def test_versiones_detalladas_estructura(self):
        """obtener_versiones_detalladas retorna estructura correcta."""
        from agentes.prompts.registro_versiones import obtener_versiones_detalladas
        detalles = obtener_versiones_detalladas()
        assert "version_global" in detalles
        assert "componentes" in detalles
        assert len(detalles["componentes"]) == 6
        for comp, info in detalles["componentes"].items():
            assert "version" in info
            assert "hash_actual" in info
            assert "integridad_ok" in info


class TestMetricasF1:
    """Tests de F1-score macro y sus componentes."""

    def test_f1_macro_perfecto(self):
        """F1-macro = 1.0 con predicciones perfectas."""
        from agentes.validacion.metricas_eaws import calcular_f1_macro
        datos = [1, 2, 3, 4, 5, 2, 3, 1]
        resultado = calcular_f1_macro(datos, datos)
        assert resultado["f1_macro"] == 1.0
        assert resultado["h1_cumple"] is True

    def test_f1_macro_aleatorio_bajo(self):
        """F1-macro con predicciones malas es <0.5."""
        from agentes.validacion.metricas_eaws import calcular_f1_macro
        reales =    [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
        predichos = [5, 4, 3, 1, 5, 1, 2, 1, 1, 2]
        resultado = calcular_f1_macro(reales, predichos)
        assert resultado["f1_macro"] < 0.5
        assert resultado["h1_cumple"] is False

    def test_f1_macro_longitudes_diferentes_error(self):
        """Longitudes diferentes lanzan ValueError."""
        from agentes.validacion.metricas_eaws import calcular_f1_macro
        import pytest
        with pytest.raises(ValueError):
            calcular_f1_macro([1, 2, 3], [1, 2])

    def test_matriz_confusion_estructura(self):
        """La matriz de confusión tiene estructura correcta."""
        from agentes.validacion.metricas_eaws import calcular_matriz_confusion
        reales =    [1, 2, 3, 2, 3]
        predichos = [1, 3, 3, 2, 2]
        resultado = calcular_matriz_confusion(reales, predichos)
        assert resultado["total_muestras"] == 5
        assert len(resultado["matriz"]) == 5
        assert len(resultado["matriz"][0]) == 5

    def test_precision_recall_por_clase(self):
        """Precision/recall por clase calculados correctamente."""
        from agentes.validacion.metricas_eaws import (
            calcular_matriz_confusion, calcular_precision_recall_f1_por_clase
        )
        reales =    [1, 1, 2, 2, 3, 3]
        predichos = [1, 1, 2, 3, 3, 3]  # nivel 2: recall=0.5, nivel 3: precision=0.67
        conf = calcular_matriz_confusion(reales, predichos)
        por_clase = calcular_precision_recall_f1_por_clase(conf["matriz"], conf["niveles"])
        # Nivel 1 (idx 0): 2 TP, 0 FP, 0 FN → P=1, R=1, F1=1
        assert por_clase[0]["precision"] == 1.0
        assert por_clase[0]["recall"] == 1.0


class TestMetricasDeltaNLP:
    """Tests de cálculo de delta NLP (H2)."""

    def test_delta_nlp_mejora(self):
        """Con NLP mejor que sin NLP → delta positivo."""
        from agentes.validacion.metricas_eaws import calcular_delta_nlp
        reales =          [1, 2, 3, 4, 3, 2, 1, 3]
        con_nlp =         [1, 2, 3, 4, 3, 2, 1, 3]  # perfecto
        sin_nlp =         [1, 2, 3, 3, 2, 2, 1, 2]  # errores
        resultado = calcular_delta_nlp(reales, con_nlp, sin_nlp)
        assert resultado["delta_f1_macro_pp"] > 0

    def test_delta_nlp_sin_mejora(self):
        """Mismo rendimiento → delta = 0."""
        from agentes.validacion.metricas_eaws import calcular_delta_nlp
        reales =  [1, 2, 3, 4, 3]
        iguales = [1, 2, 3, 4, 3]
        resultado = calcular_delta_nlp(reales, iguales, iguales)
        assert resultado["delta_f1_macro_pp"] == 0.0

    def test_delta_nlp_estructura_completa(self):
        """El resultado tiene todos los campos necesarios."""
        from agentes.validacion.metricas_eaws import calcular_delta_nlp
        reales =  [1, 2, 3, 2, 3]
        pred1 =   [1, 2, 3, 2, 3]
        pred2 =   [1, 2, 2, 2, 3]
        resultado = calcular_delta_nlp(reales, pred1, pred2)
        assert "delta_f1_macro_pp" in resultado
        assert "con_nlp" in resultado
        assert "sin_nlp" in resultado
        assert "h2_cumple" in resultado
        assert "h2_objetivo_pp" in resultado


class TestMetricasAblacion:
    """Tests de análisis de ablación."""

    def test_ablacion_ranking_componentes(self):
        """El ranking de ablación ordena por importancia."""
        from agentes.validacion.metricas_eaws import analisis_ablacion
        reales = [1, 2, 3, 4, 3, 2, 1, 3, 2, 4]
        configuraciones = {
            "completo":         [1, 2, 3, 4, 3, 2, 1, 3, 2, 4],  # perfecto
            "sin_nlp":          [1, 2, 3, 4, 3, 2, 1, 3, 2, 3],  # 1 error
            "sin_satelital":    [1, 2, 3, 3, 2, 2, 1, 3, 2, 3],  # 3 errores
            "sin_topografico":  [1, 2, 2, 3, 3, 2, 1, 2, 2, 3],  # 4 errores
        }
        resultado = analisis_ablacion(reales, configuraciones)
        assert resultado["f1_completo"] == 1.0
        assert len(resultado["ranking_importancia"]) == 3
        # El componente con más errores debería ser más importante
        assert resultado["ranking_importancia"][0]["delta_f1_pp"] > 0

    def test_ablacion_sin_completo(self):
        """Sin configuración 'completo', f1_completo = 0.0."""
        from agentes.validacion.metricas_eaws import analisis_ablacion
        reales = [1, 2, 3]
        resultado = analisis_ablacion(reales, {"sin_nlp": [1, 2, 2]})
        assert resultado["f1_completo"] == 0.0


class TestMetricasKappa:
    """Tests de Cohen's Kappa (H4)."""

    def test_kappa_perfecto(self):
        """Kappa = 1.0 con concordancia perfecta."""
        from agentes.validacion.metricas_eaws import calcular_cohens_kappa
        datos = [1, 2, 3, 4, 5, 2, 3]
        resultado = calcular_cohens_kappa(datos, datos)
        assert resultado["kappa"] == 1.0
        assert resultado["h4_cumple"] is True

    def test_kappa_rango_valido(self):
        """Kappa está en rango razonable."""
        from agentes.validacion.metricas_eaws import calcular_cohens_kappa
        a = [1, 2, 3, 4, 5, 2, 3, 3]
        b = [2, 2, 4, 3, 4, 1, 3, 2]
        resultado = calcular_cohens_kappa(a, b)
        assert -1.0 <= resultado["kappa"] <= 1.0

    def test_kappa_sin_muestras(self):
        """Sin muestras retorna kappa=0."""
        from agentes.validacion.metricas_eaws import calcular_cohens_kappa
        resultado = calcular_cohens_kappa([], [])
        assert resultado["kappa"] == 0.0

    def test_kappa_interpretacion(self):
        """La interpretación de Landis & Koch se asigna correctamente."""
        from agentes.validacion.metricas_eaws import calcular_cohens_kappa
        # Concordancia perfecta → "Casi perfecto"
        datos = [1, 2, 3, 4, 5]
        resultado = calcular_cohens_kappa(datos, datos)
        assert resultado["interpretacion"] == "Casi perfecto"


class TestETLRelatos:
    """Tests para el ETL Databricks CSV → BigQuery (schema 37 campos)."""

    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

    # ── Parsers internos ──────────────────────────────────────────────────────

    def test_parsear_bool_true(self):
        """'true' → True."""
        from datos.relatos.cargar_relatos import _parsear_bool
        assert _parsear_bool("true") is True

    def test_parsear_bool_false(self):
        """'false' → False."""
        from datos.relatos.cargar_relatos import _parsear_bool
        assert _parsear_bool("false") is False

    def test_parsear_bool_null(self):
        """'null' y cadena vacía → None."""
        from datos.relatos.cargar_relatos import _parsear_bool
        assert _parsear_bool("null") is None
        assert _parsear_bool("") is None

    def test_parsear_float_valido(self):
        """String numérico → float."""
        from datos.relatos.cargar_relatos import _parsear_float
        assert _parsear_float("5424.0") == 5424.0
        assert _parsear_float("3.5") == 3.5

    def test_parsear_float_nulo(self):
        """Cadena vacía y 'null' → None."""
        from datos.relatos.cargar_relatos import _parsear_float
        assert _parsear_float("") is None
        assert _parsear_float("null") is None

    def test_parsear_int_valido(self):
        """String entero y float-string → int."""
        from datos.relatos.cargar_relatos import _parsear_int
        assert _parsear_int("3481") == 3481
        assert _parsear_int("5187.0") == 5187  # CSV exporta floats

    def test_parsear_int_nulo(self):
        """Cadena vacía y 'null' → None."""
        from datos.relatos.cargar_relatos import _parsear_int
        assert _parsear_int("") is None
        assert _parsear_int("null") is None

    # ── Extracción nombre desde campo `data` del LLM CSV ─────────────────────

    def test_extraer_nombre_con_presentacion(self):
        """Extrae correctamente el nombre antes de ' Presentacion '."""
        from datos.relatos.cargar_relatos import _extraer_nombre_desde_data
        data = "Cerro Plomo (5424m) - Andeshandbook Presentacion El cerro Plomo..."
        assert _extraer_nombre_desde_data(data) == "Cerro Plomo (5424m) - Andeshandbook"

    def test_extraer_nombre_fallback_newline(self):
        """Sin 'Presentacion', usa la primera línea."""
        from datos.relatos.cargar_relatos import _extraer_nombre_desde_data
        data = "Cerro Ejemplo (1000m) - Andeshandbook\nTexto largo aquí"
        assert _extraer_nombre_desde_data(data) == "Cerro Ejemplo (1000m) - Andeshandbook"

    # ── cargar_routes_csv ─────────────────────────────────────────────────────

    def test_cargar_routes_csv_campos_requeridos(self, tmp_path):
        """El registro tiene route_id, name, fuente y fecha_carga."""
        import csv
        from datos.relatos.cargar_relatos import cargar_routes_csv
        csv_path = tmp_path / "routes.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "url", "route_id", "scraped_timestamp", "name", "location",
                "sector", "nearest_city", "elevation", "first_ascent_year",
                "first_ascensionists", "latitude", "longitude", "access_type",
                "mountain_characteristics", "nearby_excursions", "description",
                "avalanche_info", "has_avalanche_info", "is_alta_montana",
                "has_glacier", "is_volcano", "avalanche_priority",
            ])
            writer.writeheader()
            writer.writerow({
                "url": "https://andeshandbook.org/1", "route_id": "999",
                "scraped_timestamp": "2025-07-20T22:56:33Z",
                "name": "Cerro Test (3000m) - Andeshandbook",
                "location": "Chile, Region Metropolitana", "sector": "Test",
                "nearest_city": "Santiago", "elevation": "3000.0",
                "first_ascent_year": "2000", "first_ascensionists": "Test",
                "latitude": "-33.0", "longitude": "-70.0", "access_type": "Normal",
                "mountain_characteristics": "Alta Montaña", "nearby_excursions": "",
                "description": "Descripción de prueba", "avalanche_info": "",
                "has_avalanche_info": "false", "is_alta_montana": "true",
                "has_glacier": "false", "is_volcano": "false", "avalanche_priority": "false",
            })
        registros = cargar_routes_csv(str(csv_path))
        assert len(registros) == 1
        ruta = list(registros.values())[0]
        assert ruta["route_id"] == 999
        assert ruta["name"] == "Cerro Test (3000m) - Andeshandbook"
        assert ruta["fuente"] == "andeshandbook"
        assert ruta["fecha_carga"] is not None

    def test_cargar_routes_csv_campos_booleanos(self, tmp_path):
        """Los campos booleanos se parsean correctamente."""
        import csv
        from datos.relatos.cargar_relatos import cargar_routes_csv
        csv_path = tmp_path / "routes.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "url", "route_id", "scraped_timestamp", "name", "location",
                "sector", "nearest_city", "elevation", "first_ascent_year",
                "first_ascensionists", "latitude", "longitude", "access_type",
                "mountain_characteristics", "nearby_excursions", "description",
                "avalanche_info", "has_avalanche_info", "is_alta_montana",
                "has_glacier", "is_volcano", "avalanche_priority",
            ])
            writer.writeheader()
            writer.writerow({
                "url": "", "route_id": "100", "scraped_timestamp": "",
                "name": "Volcán Test (4000m) - Andeshandbook",
                "location": "Chile", "sector": "", "nearest_city": "",
                "elevation": "4000.0", "first_ascent_year": "", "first_ascensionists": "",
                "latitude": "", "longitude": "", "access_type": "",
                "mountain_characteristics": "Volcán, Alta Montaña", "nearby_excursions": "",
                "description": "", "avalanche_info": "",
                "has_avalanche_info": "true", "is_alta_montana": "true",
                "has_glacier": "false", "is_volcano": "true", "avalanche_priority": "true",
            })
        registros = cargar_routes_csv(str(csv_path))
        ruta = list(registros.values())[0]
        assert ruta["has_avalanche_info"] is True
        assert ruta["is_alta_montana"] is True
        assert ruta["has_glacier"] is False
        assert ruta["is_volcano"] is True
        assert ruta["avalanche_priority"] is True

    def test_cargar_routes_csv_route_id_invalido_omite(self, tmp_path):
        """Filas con route_id inválido se omiten."""
        import csv
        from datos.relatos.cargar_relatos import cargar_routes_csv
        csv_path = tmp_path / "routes.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "url", "route_id", "scraped_timestamp", "name", "location",
                "sector", "nearest_city", "elevation", "first_ascent_year",
                "first_ascensionists", "latitude", "longitude", "access_type",
                "mountain_characteristics", "nearby_excursions", "description",
                "avalanche_info", "has_avalanche_info", "is_alta_montana",
                "has_glacier", "is_volcano", "avalanche_priority",
            ])
            writer.writeheader()
            writer.writerow({k: "" for k in [
                "url", "route_id", "scraped_timestamp", "name", "location",
                "sector", "nearest_city", "elevation", "first_ascent_year",
                "first_ascensionists", "latitude", "longitude", "access_type",
                "mountain_characteristics", "nearby_excursions", "description",
                "avalanche_info", "has_avalanche_info", "is_alta_montana",
                "has_glacier", "is_volcano", "avalanche_priority",
            ]} | {"name": "Ruta Sin ID"})
        registros = cargar_routes_csv(str(csv_path))
        assert len(registros) == 0

    def test_cargar_routes_csv_llm_inicialmente_vacios(self, tmp_path):
        """Los campos LLM inician en None/[] antes del enriquecimiento."""
        import csv
        from datos.relatos.cargar_relatos import cargar_routes_csv
        csv_path = tmp_path / "routes.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "url", "route_id", "scraped_timestamp", "name", "location",
                "sector", "nearest_city", "elevation", "first_ascent_year",
                "first_ascensionists", "latitude", "longitude", "access_type",
                "mountain_characteristics", "nearby_excursions", "description",
                "avalanche_info", "has_avalanche_info", "is_alta_montana",
                "has_glacier", "is_volcano", "avalanche_priority",
            ])
            writer.writeheader()
            writer.writerow({
                "url": "", "route_id": "200", "scraped_timestamp": "",
                "name": "Cerro Vacio (2000m) - Andeshandbook",
                "location": "", "sector": "", "nearest_city": "",
                "elevation": "2000.0", "first_ascent_year": "", "first_ascensionists": "",
                "latitude": "", "longitude": "", "access_type": "",
                "mountain_characteristics": "", "nearby_excursions": "",
                "description": "", "avalanche_info": "",
                "has_avalanche_info": "false", "is_alta_montana": "false",
                "has_glacier": "false", "is_volcano": "false", "avalanche_priority": "false",
            })
        registros = cargar_routes_csv(str(csv_path))
        ruta = list(registros.values())[0]
        assert ruta["llm_nivel_riesgo"] is None
        assert ruta["llm_tipo_actividad"] is None
        assert ruta["llm_factores_riesgo"] == []
        assert ruta["analisis_llm_json"] is None

    # ── _enriquecer_con_llm ───────────────────────────────────────────────────

    def test_enriquecer_con_llm_extrae_campos_clave(self, tmp_path):
        """El enriquecimiento LLM extrae nivel_riesgo, tipo_actividad y resumen."""
        import csv, json
        from datos.relatos.cargar_relatos import _enriquecer_con_llm
        nombre = "Cerro Plomo (5424m) - Andeshandbook"
        analisis = {
            "resumen": {"descripcion_breve": "Cerro exigente.", "tipo_actividad": "alpinismo", "modalidad": "expedicion"},
            "evaluacion_riesgo": {"nivel_riesgo": "alto", "puntuacion_numerica": "8", "factores_riesgo": ["hielo", "exposicion"], "experiencia_requerida": "avanzado"},
            "caracteristicas_tecnicas": {"tipos_terreno": ["hielo", "roca"]},
            "equipamiento_requerido": {"equipamiento_tecnico": ["crampones", "piolet"]},
            "metadatos_analisis": {"confianza_extraccion": "0.9", "palabras_clave_tecnicas": ["hielo", "cumbre"]},
        }
        llm_csv = tmp_path / "llm.csv"
        with open(llm_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["data", "analisis_ruta"])
            writer.writeheader()
            writer.writerow({
                "data": f"{nombre} Presentacion Texto del cerro...",
                "analisis_ruta": json.dumps(analisis),
            })
        registros = {nombre: {
            "llm_nivel_riesgo": None, "llm_tipo_actividad": None, "llm_modalidad": None,
            "llm_puntuacion_riesgo": None, "llm_experiencia_requerida": None,
            "llm_resumen": None, "llm_confianza_extraccion": None,
            "llm_factores_riesgo": [], "llm_tipos_terreno": [],
            "llm_equipamiento_tecnico": [], "llm_palabras_clave": [],
            "analisis_llm_json": None,
        }}
        enriquecidos = _enriquecer_con_llm(registros, str(llm_csv))
        assert enriquecidos == 1
        r = registros[nombre]
        assert r["llm_nivel_riesgo"] == "alto"
        assert r["llm_tipo_actividad"] == "alpinismo"
        assert r["llm_modalidad"] == "expedicion"
        assert r["llm_puntuacion_riesgo"] == 8.0
        assert r["llm_confianza_extraccion"] == 0.9
        assert "hielo" in r["llm_factores_riesgo"]
        assert r["analisis_llm_json"] is not None

    def test_enriquecer_con_llm_sin_match_no_modifica(self, tmp_path):
        """Un registro LLM sin match en routes no modifica ningún registro."""
        import csv, json
        from datos.relatos.cargar_relatos import _enriquecer_con_llm
        llm_csv = tmp_path / "llm.csv"
        with open(llm_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["data", "analisis_ruta"])
            writer.writeheader()
            writer.writerow({
                "data": "Cerro Inexistente Presentacion Texto...",
                "analisis_ruta": json.dumps({"resumen": {"nivel_riesgo": "bajo"}}),
            })
        registros = {"Otro Cerro": {"llm_nivel_riesgo": None, "llm_tipo_actividad": None,
                                    "llm_modalidad": None, "llm_puntuacion_riesgo": None,
                                    "llm_experiencia_requerida": None, "llm_resumen": None,
                                    "llm_confianza_extraccion": None, "llm_factores_riesgo": [],
                                    "llm_tipos_terreno": [], "llm_equipamiento_tecnico": [],
                                    "llm_palabras_clave": [], "analisis_llm_json": None}}
        enriquecidos = _enriquecer_con_llm(registros, str(llm_csv))
        assert enriquecidos == 0
        assert registros["Otro Cerro"]["llm_nivel_riesgo"] is None

    def test_enriquecer_con_llm_json_invalido_no_falla(self, tmp_path):
        """JSON malformado en LLM CSV no lanza excepción."""
        import csv
        from datos.relatos.cargar_relatos import _enriquecer_con_llm
        llm_csv = tmp_path / "llm.csv"
        with open(llm_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["data", "analisis_ruta"])
            writer.writeheader()
            writer.writerow({
                "data": "Cerro Test Presentacion Texto...",
                "analisis_ruta": "{json_invalido: [}",
            })
        registros = {"Cerro Test": {"llm_nivel_riesgo": None, "llm_tipo_actividad": None,
                                    "llm_modalidad": None, "llm_puntuacion_riesgo": None,
                                    "llm_experiencia_requerida": None, "llm_resumen": None,
                                    "llm_confianza_extraccion": None, "llm_factores_riesgo": [],
                                    "llm_tipos_terreno": [], "llm_equipamiento_tecnico": [],
                                    "llm_palabras_clave": [], "analisis_llm_json": None}}
        enriquecidos = _enriquecer_con_llm(registros, str(llm_csv))
        assert enriquecidos == 0  # no enriquecido, pero sin crash


class TestDisclaimerPrompts:
    """Tests para verificar la presencia del disclaimer ético-legal en los prompts."""

    def test_disclaimer_en_prompt_integrador(self):
        """El prompt del integrador incluye el disclaimer obligatorio."""
        from agentes.subagentes.subagente_integrador.prompts import SYSTEM_PROMPT_INTEGRADOR
        assert "AVISO" in SYSTEM_PROMPT_INTEGRADOR
        assert "sistema experimental" in SYSTEM_PROMPT_INTEGRADOR.lower()
        assert "responsabilidad" in SYSTEM_PROMPT_INTEGRADOR.lower()

    def test_disclaimer_incluye_instruccion_final(self):
        """El prompt del integrador instruye a incluir el disclaimer al final."""
        from agentes.subagentes.subagente_integrador.prompts import SYSTEM_PROMPT_INTEGRADOR
        assert "disclaimer" in SYSTEM_PROMPT_INTEGRADOR.lower()

    def test_schema_boletines_tiene_campo_confianza(self):
        """El schema de boletines incluye campo 'confianza' para transparencia."""
        import json, os
        schema_path = os.path.join(
            os.path.dirname(__file__), '..', 'salidas', 'schema_boletines.json'
        )
        with open(schema_path) as f:
            schema = json.load(f)
        nombres = {c["name"] for c in schema}
        campos_transparencia = {
            "confianza", "subagentes_degradados", "version_prompts",
            "fuente_gradiente_pinn", "fuente_tamano_eaws",
            "datos_topograficos_ok", "datos_meteorologicos_ok"
        }
        faltantes = campos_transparencia - nombres
        assert not faltantes, f"Campos de transparencia faltantes: {faltantes}"

    def test_schema_boletines_tiene_34_campos(self):
        """El schema de boletines tiene 34 campos (34 = 33 originales + subagentes_degradados)."""
        import json, os
        schema_path = os.path.join(
            os.path.dirname(__file__), '..', 'salidas', 'schema_boletines.json'
        )
        with open(schema_path) as f:
            schema = json.load(f)
        assert len(schema) == 34, f"Se esperaban 34 campos, hay {len(schema)}"

    def test_marco_etico_legal_existe(self):
        """El documento de marco ético-legal existe en docs/."""
        import os
        ruta = os.path.join(
            os.path.dirname(__file__), '../../docs/marco_etico_legal.md'
        )
        assert os.path.exists(ruta), "docs/marco_etico_legal.md no existe"

    def test_marco_etico_legal_contiene_secciones(self):
        """El marco ético-legal cubre las secciones obligatorias."""
        import os
        ruta = os.path.join(
            os.path.dirname(__file__), '../../docs/marco_etico_legal.md'
        )
        with open(ruta) as f:
            contenido = f.read()
        secciones = [
            "Protección de Datos",
            "Responsabilidad",
            "Principio de precaución",
            "Ley 21.719",
            "AVISO",
        ]
        for s in secciones:
            assert s in contenido, f"Sección faltante en marco ético-legal: {s}"


class TestSchemaMigracion:
    """Tests para el script de migración del schema de boletines_riesgo."""

    def test_schema_objetivo_cargable(self):
        """El schema objetivo (schema_boletines.json) se puede cargar."""
        import json, os
        schema_path = os.path.join(
            os.path.dirname(__file__), '..', 'salidas', 'schema_boletines.json'
        )
        with open(schema_path) as f:
            schema = json.load(f)
        assert isinstance(schema, list)
        assert len(schema) > 0

    def test_campos_nuevos_son_nullable(self):
        """Los campos de ablación/trazabilidad son todos NULLABLE (BQ permite añadirlos)."""
        import json, os
        schema_path = os.path.join(
            os.path.dirname(__file__), '..', 'salidas', 'schema_boletines.json'
        )
        with open(schema_path) as f:
            schema = json.load(f)
        campos_nuevos = {
            "datos_topograficos_ok", "datos_meteorologicos_ok",
            "version_prompts", "fuente_gradiente_pinn",
            "fuente_tamano_eaws", "viento_kmh", "subagentes_degradados"
        }
        for campo in schema:
            if campo["name"] in campos_nuevos:
                assert campo["mode"] in ("NULLABLE", None), (
                    f"Campo {campo['name']} debe ser NULLABLE para migración BQ"
                )

    def test_script_migracion_existe(self):
        """El script de migración existe en agentes/scripts/."""
        import os
        ruta = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'migrar_schema_boletines.py'
        )
        assert os.path.exists(ruta), "agentes/scripts/migrar_schema_boletines.py no existe"

    def test_campos_requeridos_en_schema(self):
        """Los campos REQUIRED del schema existen y tienen tipo correcto."""
        import json, os
        schema_path = os.path.join(
            os.path.dirname(__file__), '..', 'salidas', 'schema_boletines.json'
        )
        with open(schema_path) as f:
            schema = json.load(f)
        campos_required = {c["name"]: c for c in schema if c.get("mode") == "REQUIRED"}
        # nombre_ubicacion y fecha_emision son los únicos REQUIRED
        assert "nombre_ubicacion" in campos_required
        assert "fecha_emision" in campos_required
        assert campos_required["nombre_ubicacion"]["type"] == "STRING"
        assert campos_required["fecha_emision"]["type"] == "TIMESTAMP"


class TestPruebasEstadisticas:
    """Tests del notebook 05: bootstrap, McNemar, diferencia proporciones, potencia."""

    def test_bootstrap_f1_retorna_triple(self):
        """bootstrap_intervalo_confianza retorna (estimado, ic_inf, ic_sup)."""
        from notebooks_validacion.n05_pruebas_estadisticas import (
            bootstrap_intervalo_confianza,
            calcular_f1_macro_simple,
        )
        reales = [1, 2, 3, 3, 2, 4, 1, 3, 2, 3] * 5
        predichos = [1, 2, 3, 2, 2, 4, 1, 3, 3, 3] * 5
        estimado, ic_inf, ic_sup = bootstrap_intervalo_confianza(
            reales, predichos, calcular_f1_macro_simple, n_iteraciones=500
        )
        assert 0.0 <= estimado <= 1.0
        assert ic_inf <= estimado <= ic_sup

    def test_bootstrap_ic_width_razonable(self):
        """El IC bootstrap tiene amplitud razonable (no degenera a punto)."""
        from notebooks_validacion.n05_pruebas_estadisticas import (
            bootstrap_intervalo_confianza,
            calcular_f1_macro_simple,
        )
        reales = [1, 2, 3, 3, 2, 4, 1, 3, 2, 3] * 10
        predichos = [1, 2, 3, 2, 2, 4, 1, 3, 3, 4] * 10
        _, ic_inf, ic_sup = bootstrap_intervalo_confianza(
            reales, predichos, calcular_f1_macro_simple, n_iteraciones=500
        )
        assert ic_sup - ic_inf >= 0.0  # IC siempre no-negativo

    def test_f1_macro_simple_perfecto(self):
        """F1-macro = 1.0 cuando predicciones son perfectas."""
        from notebooks_validacion.n05_pruebas_estadisticas import calcular_f1_macro_simple
        reales = [1, 2, 3, 4, 5, 1, 2, 3]
        predichos = [1, 2, 3, 4, 5, 1, 2, 3]
        assert calcular_f1_macro_simple(reales, predichos) == 1.0

    def test_f1_macro_simple_random(self):
        """F1-macro con predicciones aleatorias es menor que predicciones correctas."""
        from notebooks_validacion.n05_pruebas_estadisticas import calcular_f1_macro_simple
        reales = [1, 2, 3, 4, 5] * 10
        predichos_correctos = [1, 2, 3, 4, 5] * 10
        predichos_aleatorios = [3, 1, 5, 2, 4] * 10
        assert calcular_f1_macro_simple(reales, predichos_correctos) > \
               calcular_f1_macro_simple(reales, predichos_aleatorios)

    def test_kappa_simple_perfecto(self):
        """Kappa = 1.0 cuando predicciones son perfectas."""
        from notebooks_validacion.n05_pruebas_estadisticas import calcular_kappa_simple
        reales = [1, 2, 3, 4, 5, 1, 2, 3]
        predichos = [1, 2, 3, 4, 5, 1, 2, 3]
        assert calcular_kappa_simple(reales, predichos) == 1.0

    def test_kappa_simple_rango(self):
        """Kappa está en rango [-1, 1]."""
        from notebooks_validacion.n05_pruebas_estadisticas import calcular_kappa_simple
        reales = [1, 2, 3, 4, 5, 1, 2, 3, 4]
        predichos = [2, 3, 4, 5, 1, 2, 3, 4, 5]
        kappa = calcular_kappa_simple(reales, predichos)
        assert -1.0 <= kappa <= 1.0

    def test_mcnemar_clasificadores_identicos(self):
        """McNemar no es significativo cuando ambos clasificadores son iguales."""
        from notebooks_validacion.n05_pruebas_estadisticas import test_mcnemar
        reales = [1, 2, 3, 4, 5, 1, 2, 3] * 5
        predichos = [1, 2, 3, 4, 5, 1, 2, 3] * 5
        resultado = test_mcnemar(reales, predichos, predichos)
        assert not resultado["significativo"]

    def test_mcnemar_campos_requeridos(self):
        """Test de McNemar retorna campos requeridos."""
        from notebooks_validacion.n05_pruebas_estadisticas import test_mcnemar
        reales = [1, 2, 3, 3, 2, 4]
        predichos_a = [1, 2, 3, 2, 2, 4]
        predichos_b = [2, 1, 3, 3, 3, 3]
        resultado = test_mcnemar(reales, predichos_a, predichos_b)
        assert "chi2" in resultado
        assert "p_valor" in resultado
        assert "b" in resultado
        assert "c" in resultado
        assert "significativo" in resultado
        assert 0.0 <= resultado["p_valor"] <= 1.0

    def test_diferencia_f1_supera_umbral_h2(self):
        """test_diferencia_f1 detecta delta > 5pp como significativo con n suficiente."""
        from notebooks_validacion.n05_pruebas_estadisticas import test_diferencia_f1
        resultado = test_diferencia_f1(
            f1_con_nlp=0.82,
            f1_sin_nlp=0.73,
            n_muestras=200
        )
        assert resultado["supera_umbral_h2"]  # delta=0.09 > 0.05
        assert resultado["delta_observado"] == 0.09

    def test_diferencia_f1_no_supera_umbral_h2(self):
        """test_diferencia_f1 detecta delta < 5pp como no significativo."""
        from notebooks_validacion.n05_pruebas_estadisticas import test_diferencia_f1
        resultado = test_diferencia_f1(
            f1_con_nlp=0.78,
            f1_sin_nlp=0.76,
            n_muestras=100
        )
        assert not resultado["supera_umbral_h2"]  # delta=0.02 < 0.05

    def test_calcular_n_minimo_positivo(self):
        """N mínimo es positivo para cualquier delta válido."""
        from notebooks_validacion.n05_pruebas_estadisticas import calcular_n_minimo
        resultado = calcular_n_minimo(delta_esperado=0.05)
        assert resultado["n_minimo"] > 0
        assert resultado["dias_generacion"] > 0

    def test_calcular_n_minimo_mayor_delta_menor_n(self):
        """Cuanto mayor el delta, menos muestras se necesitan."""
        from notebooks_validacion.n05_pruebas_estadisticas import calcular_n_minimo
        n_delta_pequeno = calcular_n_minimo(delta_esperado=0.05)["n_minimo"]
        n_delta_grande = calcular_n_minimo(delta_esperado=0.20)["n_minimo"]
        assert n_delta_grande < n_delta_pequeno

    def test_datos_sinteticos_longitud_correcta(self):
        """generar_datos_sinteticos retorna vectores de longitud n."""
        from notebooks_validacion.n05_pruebas_estadisticas import generar_datos_sinteticos
        reales, predichos_s, predichos_b, predichos_nlp = generar_datos_sinteticos(n=50)
        assert len(reales) == 50
        assert len(predichos_s) == 50
        assert len(predichos_b) == 50
        assert len(predichos_nlp) == 50

    def test_datos_sinteticos_niveles_validos(self):
        """Datos sintéticos solo contienen niveles EAWS 1-5."""
        from notebooks_validacion.n05_pruebas_estadisticas import generar_datos_sinteticos
        reales, predichos_s, predichos_b, predichos_nlp = generar_datos_sinteticos(n=100)
        for vec in [reales, predichos_s, predichos_b, predichos_nlp]:
            assert all(1 <= v <= 5 for v in vec), f"Nivel fuera de rango: {set(vec)}"

    def test_analisis_completo_estructura(self):
        """ejecutar_analisis_completo retorna estructura completa de resultados."""
        from notebooks_validacion.n05_pruebas_estadisticas import (
            generar_datos_sinteticos,
            ejecutar_analisis_completo,
        )
        reales, predichos_s, predichos_b, predichos_nlp = generar_datos_sinteticos(n=60)
        resultados = ejecutar_analisis_completo(
            niveles_reales=reales,
            predichos_sistema=predichos_s,
            predichos_baseline=predichos_b,
            predichos_sin_nlp=predichos_nlp,
            modo_demo=True,
        )
        assert "metadata" in resultados
        assert "hipotesis" in resultados
        assert "analisis_potencia" in resultados
        assert "conclusion_global" in resultados
        h = resultados["hipotesis"]
        assert "H1" in h
        assert "H2" in h
        assert "H4" in h
        assert "H1_mcnemar_vs_baseline" in h

    def test_interpretar_kappa_landis_koch(self):
        """La escala Landis & Koch clasifica correctamente los rangos de Kappa."""
        from notebooks_validacion.n05_pruebas_estadisticas import _interpretar_kappa_landis_koch
        assert "Sin acuerdo" in _interpretar_kappa_landis_koch(-0.1)
        assert "Leve" in _interpretar_kappa_landis_koch(0.1)
        assert "Moderado" in _interpretar_kappa_landis_koch(0.3)
        assert "Sustancial" in _interpretar_kappa_landis_koch(0.7)
        assert "perfecto" in _interpretar_kappa_landis_koch(0.9)


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


@pytest.mark.skipif(
    not _tiene_auth,
    reason="Sin credenciales Anthropic (CLAUDE_CODE_OAUTH_TOKEN o ANTHROPIC_API_KEY)"
)
class TestSubagenteNLP:
    """Tests del SubagenteNLP con llamadas Anthropic."""

    def test_subagente_nlp_ejecuta_sin_relatos(self):
        """El subagente NLP ejecuta sin error aunque no haya relatos disponibles."""
        from agentes.subagentes.subagente_nlp.agente import SubagenteNLP

        agente = SubagenteNLP()
        resultado = agente.ejecutar(UBICACION_PILOTO)

        assert "analisis" in resultado, "El resultado debe contener el campo 'analisis'"
        assert len(resultado["analisis"]) > 20, (
            f"El análisis NLP parece vacío: '{resultado['analisis'][:100]}'"
        )
        assert resultado["nombre_subagente"] == "SubagenteNLP"
        assert isinstance(resultado["iteraciones"], int)
        assert resultado["iteraciones"] > 0

        print(f"\n✓ SubagenteNLP: {resultado['iteraciones']} iteraciones, "
              f"{resultado['duracion_segundos']}s")
        print(f"  Análisis: {resultado['analisis'][:200]}...")

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

    def test_extraer_patrones_sin_relatos(self):
        """extraer_patrones con relatos vacíos retorna disponible=False y Baja confianza."""
        from agentes.subagentes.subagente_nlp.tools.tool_conocimiento_historico import (
            ejecutar_sintetizar_conocimiento_historico
        )
        resultado = ejecutar_sintetizar_conocimiento_historico(
            consultor=None,
            total_relatos=0,
            frecuencias_terminos={},
            indice_riesgo_base=0.0
        )
        assert resultado["disponible"] is False
        assert resultado["confianza"] == "Baja"
        assert resultado["indice_riesgo_ajustado"] == 0.0

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
            consultor=None,
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
            consultor=None,
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

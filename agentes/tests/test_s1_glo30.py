"""
Tests para S1 v2: GLO-30 + TAGEE + AlphaEarth.

Cubre:
  - tool_tagee_terreno: datos disponibles y fallback cuando no hay datos BQ
  - tool_alphaearth: análisis de embedding y drift interanual
  - tool_calcular_pinn: features TAGEE/AE opcionales + retro-compatibilidad
  - SubagenteTopografico: 6 tools registradas, ejecutores presentes
  - ConsultorBigQuery.obtener_atributos_tagee_ae: retorno gracioso
"""

import pytest
from unittest.mock import MagicMock, patch


# ─── TestToolTageeTerreno ─────────────────────────────────────────────────────

class TestToolTageeTerreno:

    _BQ = "agentes.subagentes.subagente_topografico.tools.tool_tagee_terreno.ConsultorBigQuery"

    def test_retorna_disponible_false_sin_datos_bq(self):
        from agentes.subagentes.subagente_topografico.tools.tool_tagee_terreno import (
            ejecutar_analizar_terreno_tagee,
        )
        with patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_atributos_tagee_ae.return_value = {
                "disponible": False,
                "razon": "Columnas TAGEE/AE no existen aún"
            }
            resultado = ejecutar_analizar_terreno_tagee("La Parva")

        assert resultado["disponible"] is False
        assert "razon" in resultado
        assert "dem_fuente" in resultado  # informa fuente activa

    def test_retorna_atributos_cuando_datos_disponibles(self):
        from agentes.subagentes.subagente_topografico.tools.tool_tagee_terreno import (
            ejecutar_analizar_terreno_tagee,
        )
        with patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_atributos_tagee_ae.return_value = {
                "disponible": True,
                "curvatura_horizontal_promedio": 0.42,
                "curvatura_vertical_promedio": -0.28,
                "zonas_convergencia_runout": 45,
                "northness_promedio": 0.75,
                "eastness_promedio": 0.12,
                "dem_fuente": "COPERNICUS/DEM/GLO30",
                "fecha_analisis": "2026-01-15T00:00:00",
            }
            resultado = ejecutar_analizar_terreno_tagee("La Parva")

        assert resultado["disponible"] is True
        assert resultado["dem_fuente"] == "COPERNICUS/DEM/GLO30"
        assert "curvatura" in resultado
        assert "zonas_convergencia_runout" in resultado
        assert "riesgo_runout" in resultado
        assert "factores_eaws" in resultado

    def test_interpreta_convergencia_alta(self):
        from agentes.subagentes.subagente_topografico.tools.tool_tagee_terreno import (
            ejecutar_analizar_terreno_tagee,
        )
        with patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_atributos_tagee_ae.return_value = {
                "disponible": True,
                "curvatura_horizontal_promedio": 0.65,  # alta convergencia
                "curvatura_vertical_promedio": -0.35,   # convexa = zona inicio
                "zonas_convergencia_runout": 80,
                "northness_promedio": 0.85,
                "eastness_promedio": 0.05,
                "dem_fuente": "COPERNICUS/DEM/GLO30",
            }
            resultado = ejecutar_analizar_terreno_tagee("La Parva")

        assert resultado["riesgo_runout"] in ("muy_alto", "alto")
        interp_h = resultado["curvatura"]["interpretacion_horizontal"]
        assert "convergencia" in interp_h
        factores = resultado["factores_eaws"]
        assert any("CONVERGENCIA" in f for f in factores)

    def test_curvatura_convexa_genera_factor_inicio(self):
        from agentes.subagentes.subagente_topografico.tools.tool_tagee_terreno import (
            ejecutar_analizar_terreno_tagee,
        )
        with patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_atributos_tagee_ae.return_value = {
                "disponible": True,
                "curvatura_horizontal_promedio": 0.0,
                "curvatura_vertical_promedio": -0.50,  # muy convexa
                "zonas_convergencia_runout": 5,
                "northness_promedio": 0.1,
                "eastness_promedio": 0.0,
                "dem_fuente": "COPERNICUS/DEM/GLO30",
            }
            resultado = ejecutar_analizar_terreno_tagee("Valle Nevado")

        interp_v = resultado["curvatura"]["interpretacion_vertical"]
        assert "inicio" in interp_v or "convexa" in interp_v
        assert any("CURVATURA_CONVEXA" in f or "inicio" in f.lower() for f in resultado["factores_eaws"])

    def test_tool_dict_correcto(self):
        from agentes.subagentes.subagente_topografico.tools.tool_tagee_terreno import (
            TOOL_TAGEE_TERRENO,
        )
        assert TOOL_TAGEE_TERRENO["name"] == "analizar_terreno_tagee"
        assert "input_schema" in TOOL_TAGEE_TERRENO
        props = TOOL_TAGEE_TERRENO["input_schema"]["properties"]
        assert "nombre_ubicacion" in props


# ─── TestToolAlphaEarth ───────────────────────────────────────────────────────

class TestToolAlphaEarth:

    _BQ = "agentes.subagentes.subagente_topografico.tools.tool_alphaearth.ConsultorBigQuery"

    def test_retorna_disponible_false_sin_datos(self):
        from agentes.subagentes.subagente_topografico.tools.tool_alphaearth import (
            ejecutar_analizar_embedding_alphaearth,
        )
        with patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_atributos_tagee_ae.return_value = {
                "disponible": False,
                "razon": "Datos no disponibles",
            }
            resultado = ejecutar_analizar_embedding_alphaearth("La Parva")

        assert resultado["disponible"] is False
        assert "nota_uso" in resultado  # aviso sobre uso correcto

    def test_retorna_analisis_con_embedding(self):
        import json
        from agentes.subagentes.subagente_topografico.tools.tool_alphaearth import (
            ejecutar_analizar_embedding_alphaearth,
        )
        embedding_64 = [0.1 * (i % 10) for i in range(64)]
        similitudes = {"2021": 0.95, "2022": 0.97, "2023": 0.88, "2024": 0.91}
        with patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_atributos_tagee_ae.return_value = {
                "disponible": True,
                "embedding_centroide_zona": embedding_64,
                "similitud_anios_previos": similitudes,
                "dem_fuente": "COPERNICUS/DEM/GLO30",
            }
            resultado = ejecutar_analizar_embedding_alphaearth("La Parva")

        assert resultado["disponible"] is True
        assert resultado["embedding_dimensiones"] == 64
        assert "drift_interanual" in resultado
        assert resultado["drift_interanual"]["disponible"] is True
        assert "cambios_detectados" in resultado
        assert "implicaciones_eaws" in resultado

    def test_detecta_drift_alto(self):
        from agentes.subagentes.subagente_topografico.tools.tool_alphaearth import (
            ejecutar_analizar_embedding_alphaearth,
        )
        embedding_64 = [0.5] * 64
        # Similitud baja = drift alto
        similitudes = {"2022": 0.60, "2023": 0.70, "2024": 0.65}
        with patch(self._BQ) as mock_bq:
            mock_bq.return_value.obtener_atributos_tagee_ae.return_value = {
                "disponible": True,
                "embedding_centroide_zona": embedding_64,
                "similitud_anios_previos": similitudes,
                "dem_fuente": "COPERNICUS/DEM/GLO30",
            }
            resultado = ejecutar_analizar_embedding_alphaearth("La Parva")

        drift = resultado["drift_interanual"]
        assert drift["drift_maximo"] > 0.1
        assert "cambio" in drift["tendencia"].lower() or "significativo" in drift["tendencia"].lower()
        impl = resultado["implicaciones_eaws"]
        assert any("CAMBIO_TERRENO" in i or "start zones" in i.lower() for i in impl)

    def test_tool_dict_correcto(self):
        from agentes.subagentes.subagente_topografico.tools.tool_alphaearth import (
            TOOL_ALPHAEARTH,
        )
        assert TOOL_ALPHAEARTH["name"] == "analizar_embedding_alphaearth"
        assert "input_schema" in TOOL_ALPHAEARTH


# ─── TestCalcularPinnConFeaturesGLO30 ─────────────────────────────────────────

class TestCalcularPinnConFeaturesGLO30:

    def _pinn_base(self, **kwargs):
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            ejecutar_calcular_pinn,
        )
        defaults = dict(
            gradiente_termico_C_100m=-0.65,
            densidad_kg_m3=280.0,
            indice_metamorfismo=1.0,
            energia_fusion_J_kg=200000.0,
            pendiente_grados=38.0,
        )
        defaults.update(kwargs)
        return ejecutar_calcular_pinn(**defaults)

    def test_retro_compatible_sin_features_glo30(self):
        """Sin features TAGEE/AE, el resultado debe ser idéntico al PINN baseline."""
        resultado = self._pinn_base()
        assert "factor_seguridad_mohr_coulomb" in resultado
        assert "estado_manto" in resultado
        assert "riesgo_falla" in resultado
        assert "features_glo30_tagee_ae" in resultado

    def test_convergencia_alta_reduce_factor_seguridad(self):
        """Curvatura horizontal positiva (convergencia) debe reducir FS."""
        sin_tagee = self._pinn_base()
        con_tagee = self._pinn_base(curvatura_horizontal=0.60)
        assert con_tagee["factor_seguridad_mohr_coulomb"] <= sin_tagee["factor_seguridad_mohr_coulomb"]

    def test_curvatura_vertical_convexa_reduce_fs(self):
        """Curvatura vertical negativa (convexa = zona inicio) debe reducir FS."""
        sin_tagee = self._pinn_base()
        con_tagee = self._pinn_base(curvatura_vertical=-0.40)
        assert con_tagee["factor_seguridad_mohr_coulomb"] <= sin_tagee["factor_seguridad_mohr_coulomb"]

    def test_fs_ajustado_nunca_negativo(self):
        """El FS ajustado nunca debe ser negativo aunque haya muchos ajustes."""
        resultado = self._pinn_base(
            curvatura_horizontal=1.0,
            curvatura_vertical=-1.0,
            drift_embedding_ae=0.50,
        )
        assert resultado["factor_seguridad_mohr_coulomb"] > 0

    def test_drift_ae_genera_alerta_sin_modificar_fs(self):
        """Drift AlphaEarth alto debe generar alerta pero no cambiar FS."""
        sin_ae = self._pinn_base()
        con_ae = self._pinn_base(drift_embedding_ae=0.25)
        # FS no cambia por drift AE (es incertidumbre, no efecto físico)
        assert abs(
            sin_ae["factor_seguridad_mohr_coulomb"] - con_ae["factor_seguridad_mohr_coulomb"]
        ) < 0.01
        alertas_ae = con_ae["features_glo30_tagee_ae"]["alertas_alphaearth"]
        assert len(alertas_ae) > 0

    def test_features_glo30_reporta_si_esta_activo(self):
        """El campo usando_glo30_tagee debe ser True cuando se pasan features."""
        resultado = self._pinn_base(curvatura_horizontal=0.3)
        assert resultado["features_glo30_tagee_ae"]["usando_glo30_tagee"] is True

    def test_features_glo30_false_sin_curvatura(self):
        """Sin features TAGEE, usando_glo30_tagee debe ser False."""
        resultado = self._pinn_base()
        assert resultado["features_glo30_tagee_ae"]["usando_glo30_tagee"] is False

    def test_tool_dict_tiene_nuevos_campos_opcionales(self):
        from agentes.subagentes.subagente_topografico.tools.tool_calcular_pinn import (
            TOOL_CALCULAR_PINN,
        )
        props = TOOL_CALCULAR_PINN["input_schema"]["properties"]
        assert "curvatura_horizontal" in props
        assert "curvatura_vertical" in props
        assert "drift_embedding_ae" in props
        # Los nuevos campos NO deben ser required
        requeridos = TOOL_CALCULAR_PINN["input_schema"].get("required", [])
        assert "curvatura_horizontal" not in requeridos
        assert "drift_embedding_ae" not in requeridos


# ─── TestSubagenteTopograficoV2 ───────────────────────────────────────────────

class TestSubagenteTopograficoV2:

    def test_seis_tools_registradas(self):
        """S1 ahora debe tener 6 tools (2 nuevas: TAGEE y AlphaEarth)."""
        from agentes.subagentes.subagente_topografico.agente import SubagenteTopografico
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=MagicMock()):
            agente = SubagenteTopografico()
        tools = [t["name"] for t in agente._cargar_tools()]
        assert len(tools) == 6
        assert "analizar_dem" in tools
        assert "analizar_terreno_tagee" in tools
        assert "analizar_embedding_alphaearth" in tools
        assert "calcular_pinn" in tools
        assert "identificar_zonas_riesgo" in tools
        assert "evaluar_estabilidad_manto" in tools

    def test_todos_ejecutores_presentes(self):
        from agentes.subagentes.subagente_topografico.agente import SubagenteTopografico
        with patch("agentes.subagentes.base_subagente.crear_cliente", return_value=MagicMock()):
            agente = SubagenteTopografico()
        tools = [t["name"] for t in agente._cargar_tools()]
        ejecutores = agente._cargar_ejecutores()
        for nombre in tools:
            assert nombre in ejecutores, f"Ejecutor faltante para '{nombre}'"

    def test_max_iteraciones_aumentado(self):
        """Con más tools, el límite de iteraciones debe haberse aumentado."""
        from agentes.subagentes.subagente_topografico.agente import SubagenteTopografico
        assert SubagenteTopografico.MAX_ITERACIONES >= 10


# ─── TestConsultorBigQueryTageeAe ─────────────────────────────────────────────

class TestConsultorBigQueryTageeAe:

    _BQ_CLIENT = "agentes.datos.consultor_bigquery.bigquery.Client"

    def test_retorna_disponible_false_si_no_hay_filas(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        with patch(self._BQ_CLIENT) as mock_client:
            mock_client.return_value.query.return_value.result.return_value = iter([])
            consultor = ConsultorBigQuery()
            resultado = consultor.obtener_atributos_tagee_ae("La Parva")

        assert resultado["disponible"] is False
        assert "Ejecutar" in resultado.get("razon", "")

    def test_retorna_disponible_false_si_columnas_no_existen(self):
        from agentes.datos.consultor_bigquery import ConsultorBigQuery
        from google.api_core.exceptions import BadRequest

        with patch(self._BQ_CLIENT) as mock_client:
            mock_client.return_value.query.side_effect = BadRequest(
                "Unrecognized name: curvatura_horizontal_promedio"
            )
            consultor = ConsultorBigQuery()
            resultado = consultor.obtener_atributos_tagee_ae("La Parva")

        assert resultado["disponible"] is False

    def test_deserializa_embedding_json_string(self):
        import json
        from agentes.datos.consultor_bigquery import ConsultorBigQuery

        embedding_64 = [float(i) / 64 for i in range(64)]
        fila_mock = {
            "curvatura_horizontal_promedio": 0.3,
            "curvatura_vertical_promedio": -0.2,
            "zonas_convergencia_runout": 25,
            "northness_promedio": 0.6,
            "eastness_promedio": 0.1,
            "embedding_centroide_zona": json.dumps(embedding_64),
            "similitud_anios_previos": json.dumps({"2023": 0.95}),
            "dem_fuente": "COPERNICUS/DEM/GLO30",
            "fecha_analisis": None,
        }

        with patch(self._BQ_CLIENT) as mock_client:
            mock_result = MagicMock()
            mock_result.__iter__ = MagicMock(return_value=iter([fila_mock]))
            mock_client.return_value.query.return_value.result.return_value = mock_result
            consultor = ConsultorBigQuery()
            resultado = consultor.obtener_atributos_tagee_ae("La Parva")

        assert resultado["disponible"] is True
        assert isinstance(resultado["embedding_centroide_zona"], list)
        assert len(resultado["embedding_centroide_zona"]) == 64
        assert isinstance(resultado["similitud_anios_previos"], dict)

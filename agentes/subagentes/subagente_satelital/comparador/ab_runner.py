"""
Comparador A/B S2: ViT actual vs Vía Earth AI.

Ejecuta ambas vías sobre el mismo input y registra métricas comparativas
en BigQuery para análisis posterior (material de tesis).

Activar con: S2_VIA=ambas_consolidar_vit  (output→S5 = ViT)
              S2_VIA=ambas_consolidar_ea   (output→S5 = Earth AI)

Tabla BQ de resultados: clima.s2_comparaciones
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

GCP_PROJECT = "climas-chileno"


class ComparadorS2:
    """
    Orquesta la ejecución paralela de ambas vías satelitales y persiste
    las métricas comparativas en BigQuery.
    """

    def __init__(self):
        self._via_activa = os.environ.get("S2_VIA", "vit_actual")

    @property
    def modo_comparacion(self) -> bool:
        return self._via_activa.startswith("ambas_")

    @property
    def via_primaria(self) -> str:
        """Determina qué vía alimenta a S5."""
        if self._via_activa == "ambas_consolidar_ea":
            return "earth_ai"
        return "vit_actual"

    def ejecutar_y_comparar(
        self,
        resultado_vit: dict,
        resultado_earth_ai: dict,
        ubicacion: str,
    ) -> dict:
        """
        Compara outputs de ambas vías y persiste métricas en BQ.

        Args:
            resultado_vit: dict del ViT actual (tools existentes)
            resultado_earth_ai: dict de la vía Earth AI
            ubicacion: nombre de la ubicación

        Returns:
            dict con comparación y el output primario para S5
        """
        if not self.modo_comparacion:
            return {
                "comparacion_activa": False,
                "output_para_s5": resultado_vit,
                "via_usada": "vit_actual",
            }

        comparacion = self._calcular_metricas(resultado_vit, resultado_earth_ai)

        self._persistir_comparacion_async(
            ubicacion=ubicacion,
            resultado_vit=resultado_vit,
            resultado_earth_ai=resultado_earth_ai,
            metricas=comparacion,
        )

        output_primario = (
            resultado_earth_ai
            if self.via_primaria == "earth_ai" and resultado_earth_ai.get("disponible")
            else resultado_vit
        )

        return {
            "comparacion_activa": True,
            "via_usada": self.via_primaria,
            "output_para_s5": output_primario,
            "metricas_comparacion": comparacion,
            "s2_via_config": self._via_activa,
        }

    def _calcular_metricas(self, vit: dict, ea: dict) -> dict:
        """Calcula métricas de comparación entre ambas vías."""
        metricas = {
            "timestamp_comparacion": datetime.now(timezone.utc).isoformat(),
            "vit_disponible": bool(vit.get("disponible")),
            "ea_disponible": bool(ea.get("disponible") and ea.get("via_activa")),
        }

        if not metricas["vit_disponible"] or not metricas["ea_disponible"]:
            metricas["nota"] = "Comparación incompleta — una o ambas vías sin datos"
            return metricas

        # Diferencia en score de anomalía
        score_vit = vit.get("score_anomalia", 0.0) or 0.0
        score_ea = ea.get("score_anomalia", 0.0) or 0.0
        metricas["delta_score_anomalia"] = round(score_ea - score_vit, 4)

        # Acuerdo en anomalía detectada
        anomalia_vit = vit.get("anomalia_detectada", False)
        anomalia_ea = ea.get("anomalia_detectada", False)
        metricas["acuerdo_anomalia"] = (anomalia_vit == anomalia_ea)

        # Diferencia cobertura nieve
        cob_vit = vit.get("cobertura_nieve_pct", 0.0) or 0.0
        cob_ea = ea.get("cobertura_nieve_pct", 0.0) or 0.0
        metricas["delta_cobertura_pct"] = round(cob_ea - cob_vit, 2)

        # Latencia relativa
        lat_vit = vit.get("latencia_ms", 0.0) or 0.0
        lat_ea = ea.get("latencia_ms", 0.0) or 0.0
        metricas["latencia_vit_ms"] = lat_vit
        metricas["latencia_ea_ms"] = lat_ea
        metricas["ratio_latencia"] = round(lat_ea / max(lat_vit, 1), 2)

        # Confianza relativa
        conf_vit = vit.get("confianza_global", 0.5) or 0.5
        conf_ea = ea.get("confianza_global", 0.5) or 0.5
        metricas["delta_confianza"] = round(conf_ea - conf_vit, 4)

        return metricas

    def _persistir_comparacion_async(
        self,
        ubicacion: str,
        resultado_vit: dict,
        resultado_earth_ai: dict,
        metricas: dict,
    ):
        """Persiste la comparación en BQ de forma no bloqueante."""
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=GCP_PROJECT)
            tabla_id = f"{GCP_PROJECT}.clima.s2_comparaciones"

            fila = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ubicacion": ubicacion,
                "s2_via_config": self._via_activa,
                "vit_score_anomalia": resultado_vit.get("score_anomalia"),
                "vit_cobertura_pct": resultado_vit.get("cobertura_nieve_pct"),
                "vit_anomalia": resultado_vit.get("anomalia_detectada"),
                "vit_latencia_ms": resultado_vit.get("latencia_ms"),
                "ea_score_anomalia": resultado_earth_ai.get("score_anomalia"),
                "ea_cobertura_pct": resultado_earth_ai.get("cobertura_nieve_pct"),
                "ea_anomalia": resultado_earth_ai.get("anomalia_detectada"),
                "ea_latencia_ms": resultado_earth_ai.get("latencia_ms"),
                "delta_score": metricas.get("delta_score_anomalia"),
                "acuerdo_anomalia": metricas.get("acuerdo_anomalia"),
            }

            fila_limpia = {k: v for k, v in fila.items() if v is not None}
            errors = client.insert_rows_json(tabla_id, [fila_limpia])
            if errors:
                logger.warning(f"ComparadorS2: error persistiendo en BQ — {errors}")
            else:
                logger.debug(f"ComparadorS2: comparación persistida para {ubicacion}")

        except Exception as exc:
            # Nunca bloquear el pipeline por fallo del comparador
            logger.warning(f"ComparadorS2: no se pudo persistir comparación — {exc}")

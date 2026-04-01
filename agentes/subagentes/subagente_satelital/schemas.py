"""
Schemas comunes para S2 — vía ViT actual y vía Earth AI.

Ambas vías producen un DeteccionSatelital con el mismo schema,
lo que permite comparación directa A/B en el comparador.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class DeteccionSatelital:
    """
    Output unificado de S2 (ViT actual y/o Earth AI).

    Diseñado para que ambas vías sean comparables directamente.
    Solo los campos *qualitativo_ea (Earth AI) pueden venir de Gemini.
    """
    via: Literal["vit_actual", "gemini_multispectral", "rsfm"]
    zona: str
    timestamp: datetime

    # Detecciones cuantitativas (ambas vías)
    cobertura_nieve_pct: float
    nieve_humeda_pct: Optional[float] = None
    nieve_seca_pct: Optional[float] = None

    # Señales de riesgo avalancha
    score_anomalia: float = 0.0
    anomalia_detectada: bool = False
    tipos_anomalia: list = field(default_factory=list)
    snowline_elevacion_m: Optional[float] = None

    # Solo Earth AI (VLM qualitative)
    descripcion_cualitativa: Optional[str] = None
    factores_riesgo_observados: list = field(default_factory=list)
    cornisas_detectadas: bool = False
    wind_slabs_indicados: bool = False

    # Metadatos
    fuentes_satelite: list = field(default_factory=list)  # ["GOES-19", "MODIS", "S2"]
    confianza_global: float = 0.5
    flags_calidad: list = field(default_factory=list)
    latencia_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "via": self.via,
            "zona": self.zona,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "cobertura_nieve_pct": self.cobertura_nieve_pct,
            "nieve_humeda_pct": self.nieve_humeda_pct,
            "nieve_seca_pct": self.nieve_seca_pct,
            "score_anomalia": self.score_anomalia,
            "anomalia_detectada": self.anomalia_detectada,
            "tipos_anomalia": self.tipos_anomalia,
            "snowline_elevacion_m": self.snowline_elevacion_m,
            "descripcion_cualitativa": self.descripcion_cualitativa,
            "factores_riesgo_observados": self.factores_riesgo_observados,
            "cornisas_detectadas": self.cornisas_detectadas,
            "wind_slabs_indicados": self.wind_slabs_indicados,
            "fuentes_satelite": self.fuentes_satelite,
            "confianza_global": self.confianza_global,
            "flags_calidad": self.flags_calidad,
            "latencia_ms": self.latencia_ms,
        }

    @classmethod
    def desde_resultado_vit(cls, zona: str, resultado_vit: dict) -> "DeteccionSatelital":
        """Adapta el output del ViT actual al schema unificado."""
        from datetime import timezone
        return cls(
            via="vit_actual",
            zona=zona,
            timestamp=datetime.now(timezone.utc),
            cobertura_nieve_pct=resultado_vit.get("cobertura_nieve_pct", 0.0),
            nieve_humeda_pct=resultado_vit.get("nieve_humeda_pct"),
            score_anomalia=resultado_vit.get("score_anomalia", 0.0),
            anomalia_detectada=resultado_vit.get("anomalia_detectada", False),
            tipos_anomalia=resultado_vit.get("tipos_anomalia", []),
            snowline_elevacion_m=resultado_vit.get("snowline_elevacion_m"),
            fuentes_satelite=resultado_vit.get("fuentes_satelite", ["MODIS", "GOES"]),
            confianza_global=resultado_vit.get("confianza_global", 0.7),
            flags_calidad=resultado_vit.get("flags_calidad", []),
        )

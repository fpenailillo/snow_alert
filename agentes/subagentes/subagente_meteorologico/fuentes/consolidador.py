"""
ConsolidadorMeteorologico — Fusión multi-fuente de datos meteorológicos.

Estrategias disponibles (controladas por variable de entorno):
  USE_WEATHERNEXT2=false  → solo_open_meteo (default, comportamiento actual)
  USE_WEATHERNEXT2=true   → enriquecido_con_wn2 (shadow/producción)

El consolidador siempre retorna el resultado de Open-Meteo como primario
hasta que USE_WEATHERNEXT2_AS_PRIMARY=true (fase futura post-validación).

Logging de divergencia: si WN2 P50 difiere >3°C o >50% de precip vs Open-Meteo,
se registra un WARNING para análisis posterior (material de tesis).
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from agentes.subagentes.subagente_meteorologico.fuentes.base import PronosticoMeteorologico

logger = logging.getLogger(__name__)

_USE_WEATHERNEXT2 = os.environ.get("USE_WEATHERNEXT2", "false").lower() == "true"
_USE_WN2_AS_PRIMARY = os.environ.get("USE_WEATHERNEXT2_AS_PRIMARY", "false").lower() == "true"

# Umbrales de divergencia para alertas de tesis
_UMBRAL_DIVERGENCIA_TEMP_C = 3.0
_UMBRAL_DIVERGENCIA_PRECIP_PCT = 50.0


@dataclass
class ResultadoConsolidado:
    """Resultado de la consolidación multi-fuente."""
    # Pronóstico principal (el que S3 usa para el bulletin)
    pronostico_principal: PronosticoMeteorologico
    fuente_primaria: str

    # Enriquecimiento WN2 (percentiles, None si WN2 no disponible)
    ensemble_p10_precip: Optional[float] = None
    ensemble_p50_precip: Optional[float] = None
    ensemble_p90_precip: Optional[float] = None
    ensemble_p10_temp: Optional[float] = None
    ensemble_p90_temp: Optional[float] = None
    n_miembros_ensemble: Optional[int] = None

    # Metadatos
    fuente_enriquecimiento: Optional[str] = None
    divergencia_detectada: bool = False
    notas_divergencia: list[str] = field(default_factory=list)
    fuentes_consultadas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serializa para persistir en BQ o pasar como contexto a S3."""
        p = self.pronostico_principal
        return {
            "fuente_primaria": self.fuente_primaria,
            "temperatura_2m_c": p.temperatura_2m_c,
            "precipitacion_mm": p.precipitacion_mm,
            "viento_10m_kmh": p.viento_10m_kmh,
            "direccion_viento_deg": p.direccion_viento_deg,
            "humedad_pct": p.humedad_pct,
            "horizonte_h": p.horizonte_h,
            # Enriquecimiento WN2
            "ensemble_p10_precip": self.ensemble_p10_precip,
            "ensemble_p50_precip": self.ensemble_p50_precip,
            "ensemble_p90_precip": self.ensemble_p90_precip,
            "ensemble_p10_temp": self.ensemble_p10_temp,
            "ensemble_p90_temp": self.ensemble_p90_temp,
            "n_miembros_ensemble": self.n_miembros_ensemble,
            "fuente_enriquecimiento": self.fuente_enriquecimiento,
            "divergencia_detectada": self.divergencia_detectada,
            "notas_divergencia": self.notas_divergencia,
            "fuentes_consultadas": self.fuentes_consultadas,
        }


class ConsolidadorMeteorologico:
    """
    Consolida múltiples fuentes meteorológicas en un pronóstico unificado.

    Estrategias:
    - solo_open_meteo: comportamiento actual, sin cambios (default)
    - enriquecido_con_wn2: Open-Meteo primario + percentiles WN2 como metadatos
    - wn2_primario: WN2 como fuente principal (fase futura)
    """

    def __init__(self):
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo import FuenteOpenMeteo
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land import FuenteERA5Land
        from agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 import FuenteWeatherNext2

        self.open_meteo = FuenteOpenMeteo()
        self.era5 = FuenteERA5Land()
        self.weathernext2 = FuenteWeatherNext2()

    def consolidar(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int = 72,
    ) -> ResultadoConsolidado:
        """
        Consolida las fuentes disponibles para la zona.

        Con USE_WEATHERNEXT2=false (default): idéntico a solo Open-Meteo.
        Con USE_WEATHERNEXT2=true: enriquece con percentiles WN2 pero usa OM como primario.
        """
        fuentes_consultadas = []

        # ── Fuente primaria: Open-Meteo (SIEMPRE) ─────────────────────────
        pronostico_om = self.open_meteo.obtener_pronostico(zona, lat, lon, horizonte_h)
        fuentes_consultadas.append("open_meteo")

        resultado = ResultadoConsolidado(
            pronostico_principal=pronostico_om,
            fuente_primaria="open_meteo",
            fuentes_consultadas=fuentes_consultadas,
        )

        # ── Enriquecimiento WeatherNext 2 (solo si flag activo) ───────────
        if _USE_WEATHERNEXT2 and self.weathernext2.disponible:
            resultado = self._enriquecer_con_wn2(resultado, zona, lat, lon, horizonte_h, pronostico_om)
            fuentes_consultadas.append("weathernext_2")

        resultado.fuentes_consultadas = fuentes_consultadas
        return resultado

    def _enriquecer_con_wn2(
        self,
        resultado: ResultadoConsolidado,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int,
        pronostico_om: PronosticoMeteorologico,
    ) -> ResultadoConsolidado:
        """Enriquece el resultado con percentiles del ensemble WN2."""
        try:
            pronostico_wn2 = self.weathernext2.obtener_pronostico(zona, lat, lon, horizonte_h)

            if not pronostico_wn2.fuente_disponible:
                logger.warning(f"ConsolidadorMeteorologico: WN2 no disponible — {pronostico_wn2.error}")
                return resultado

            # Detectar divergencia (material de tesis)
            notas = []
            divergencia = False

            if (pronostico_om.temperatura_2m_c is not None
                    and pronostico_wn2.p50_precipitacion is not None):
                diff_temp = abs((pronostico_wn2.temperatura_2m_c or 0) - pronostico_om.temperatura_2m_c)
                if diff_temp > _UMBRAL_DIVERGENCIA_TEMP_C:
                    nota = (
                        f"Divergencia temperatura: OM={pronostico_om.temperatura_2m_c:.1f}°C, "
                        f"WN2={pronostico_wn2.temperatura_2m_c:.1f}°C (diff={diff_temp:.1f}°C)"
                    )
                    logger.warning(f"ConsolidadorMeteorologico: {nota}")
                    notas.append(nota)
                    divergencia = True

            if (pronostico_om.precipitacion_mm is not None
                    and pronostico_om.precipitacion_mm > 0
                    and pronostico_wn2.p50_precipitacion is not None):
                diff_pct = abs(
                    (pronostico_wn2.p50_precipitacion - pronostico_om.precipitacion_mm)
                    / pronostico_om.precipitacion_mm * 100
                )
                if diff_pct > _UMBRAL_DIVERGENCIA_PRECIP_PCT:
                    nota = (
                        f"Divergencia precipitación: OM={pronostico_om.precipitacion_mm:.1f}mm, "
                        f"WN2_P50={pronostico_wn2.p50_precipitacion:.1f}mm (diff={diff_pct:.0f}%)"
                    )
                    logger.warning(f"ConsolidadorMeteorologico: {nota}")
                    notas.append(nota)
                    divergencia = True

            # Enriquecer resultado con percentiles WN2
            resultado.ensemble_p10_precip = pronostico_wn2.p10_precipitacion
            resultado.ensemble_p50_precip = pronostico_wn2.p50_precipitacion
            resultado.ensemble_p90_precip = pronostico_wn2.p90_precipitacion
            resultado.ensemble_p10_temp = pronostico_wn2.p10_temperatura
            resultado.ensemble_p90_temp = pronostico_wn2.p90_temperatura
            resultado.n_miembros_ensemble = pronostico_wn2.n_miembros_ensemble
            resultado.fuente_enriquecimiento = "weathernext_2"
            resultado.divergencia_detectada = divergencia
            resultado.notas_divergencia = notas

            logger.info(
                f"ConsolidadorMeteorologico: enriquecido con WN2 — "
                f"P10={pronostico_wn2.p10_precipitacion}, "
                f"P50={pronostico_wn2.p50_precipitacion}, "
                f"P90={pronostico_wn2.p90_precipitacion} mm precip"
            )

        except Exception as exc:
            logger.warning(f"ConsolidadorMeteorologico: error enriqueciendo con WN2 — {exc}")

        return resultado

"""
FuenteOpenMeteo — Fuente meteorológica primaria.

Wrappea los datos existentes de BigQuery (condiciones_actuales + pronostico_horas)
que provienen de Open-Meteo, sin cambiar el comportamiento actual de ConsultorBigQuery.

Esta fuente es la que S3 ha estado usando desde el inicio y es la fuente primaria.
NO se modificó ningún comportamiento existente.
"""

import logging
from agentes.datos.consultor_bigquery import ConsultorBigQuery
from agentes.datos.constantes_zonas import COORDENADAS_ZONAS
from agentes.subagentes.subagente_meteorologico.fuentes.base import (
    FuenteMeteorologica,
    PronosticoMeteorologico,
)

logger = logging.getLogger(__name__)


class FuenteOpenMeteo(FuenteMeteorologica):
    """
    Fuente Open-Meteo: datos de condiciones_actuales y pronostico_horas en BQ.

    Fuente primaria del sistema. Siempre disponible mientras BQ funcione.
    """

    @property
    def nombre(self) -> str:
        return "open_meteo"

    @property
    def disponible(self) -> bool:
        return True  # Siempre intentar; fallback en obtener_pronostico si falla

    def obtener_pronostico(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int = 72,
    ) -> PronosticoMeteorologico:
        """
        Obtiene pronóstico desde condiciones_actuales + pronostico_horas en BQ.

        Usa los mismos métodos de ConsultorBigQuery que usa S3 actualmente.
        Sin cambios en comportamiento.
        """
        consultor = ConsultorBigQuery()

        coords = COORDENADAS_ZONAS.get(zona, (lat, lon))

        try:
            # Condición actual (Open-Meteo)
            actuales = consultor.obtener_condiciones_actuales(zona)
            if actuales.get("disponible") is False:
                return PronosticoMeteorologico(
                    fuente=self.nombre, zona=zona, horizonte_h=horizonte_h,
                    lat=coords[0], lon=coords[1],
                    fuente_disponible=False,
                    error="Sin condiciones actuales en BQ",
                )

            # Tendencia 72h (Open-Meteo via pronostico_horas)
            tendencia = consultor.obtener_tendencia_meteorologica(zona)

            temp_actual = actuales.get("temperatura")
            precip = actuales.get("precipitacion_acumulada") or 0.0
            viento_ms = actuales.get("velocidad_viento") or 0.0
            dir_viento = actuales.get("direccion_viento")
            humedad = actuales.get("humedad_relativa")

            # Enriquecer con tendencia si disponible
            if tendencia.get("disponible") is not False:
                precip = max(precip, tendencia.get("precip_total_acumulada_mm") or 0.0)
                viento_ms = max(viento_ms, tendencia.get("viento_max_ms") or 0.0)

            return PronosticoMeteorologico(
                fuente=self.nombre,
                zona=zona,
                horizonte_h=horizonte_h,
                lat=coords[0],
                lon=coords[1],
                temperatura_2m_c=temp_actual,
                precipitacion_mm=round(precip, 1),
                viento_10m_kmh=round(viento_ms * 3.6, 1),
                direccion_viento_deg=dir_viento,
                humedad_pct=humedad,
                fuente_disponible=True,
            )

        except Exception as exc:
            logger.error(f"FuenteOpenMeteo: error para '{zona}' — {exc}")
            return PronosticoMeteorologico(
                fuente=self.nombre, zona=zona, horizonte_h=horizonte_h,
                lat=coords[0], lon=coords[1],
                fuente_disponible=False, error=str(exc),
            )

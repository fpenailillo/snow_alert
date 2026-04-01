"""
FuenteERA5Land — Fuente meteorológica secundaria (reanálisis).

Wrappea datos ERA5-Land disponibles en BigQuery.
ERA5-Land es reanálisis (datos pasados), no pronóstico.
Útil para contextualizar condiciones recientes vs histórico.

Sin cambio de comportamiento existente.
"""

import logging
from agentes.datos.consultor_bigquery import ConsultorBigQuery
from agentes.subagentes.subagente_meteorologico.fuentes.base import (
    FuenteMeteorologica,
    PronosticoMeteorologico,
)

logger = logging.getLogger(__name__)

_COORDS_ZONAS = {
    "La Parva": (-33.354, -70.298),
    "Valle Nevado": (-33.357, -70.270),
    "El Colorado": (-33.360, -70.289),
}


class FuenteERA5Land(FuenteMeteorologica):
    """
    Fuente ERA5-Land: reanálisis ECMWF via BigQuery.

    Fuente secundaria para contextualizar condiciones recientes.
    Latencia de ~5 días (no es pronóstico en tiempo real).
    """

    @property
    def nombre(self) -> str:
        return "era5_land"

    @property
    def disponible(self) -> bool:
        return True

    def obtener_pronostico(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int = 72,
    ) -> PronosticoMeteorologico:
        """
        Obtiene datos ERA5-Land recientes para la zona.

        Nota: ERA5 tiene latencia de ~5 días — representa condiciones
        pasadas, no futuras. Se usa para validación y contexto.
        """
        consultor = ConsultorBigQuery()

        coords = _COORDS_ZONAS.get(zona, (lat, lon))

        try:
            # Obtener tendencia que puede incluir datos ERA5 embebidos en imagenes_satelitales
            satelital = consultor.obtener_estado_satelital(zona)

            if satelital.get("disponible") is False:
                return PronosticoMeteorologico(
                    fuente=self.nombre, zona=zona, horizonte_h=0,
                    lat=coords[0], lon=coords[1],
                    fuente_disponible=False,
                    error="Sin datos ERA5 en BQ (imagenes_satelitales)",
                )

            # ERA5 variables disponibles via imagenes_satelitales
            era5_snow = satelital.get("era5_snow_depth_m")
            lst_dia = satelital.get("lst_dia_celsius")
            lst_noche = satelital.get("lst_noche_celsius")

            # Temperatura estimada como promedio LST día/noche
            temp_est = None
            if lst_dia is not None and lst_noche is not None:
                temp_est = round((lst_dia + lst_noche) / 2, 1)
            elif lst_dia is not None:
                temp_est = lst_dia

            return PronosticoMeteorologico(
                fuente=self.nombre,
                zona=zona,
                horizonte_h=0,  # ERA5 es reanálisis, no pronóstico
                lat=coords[0],
                lon=coords[1],
                temperatura_2m_c=temp_est,
                fuente_disponible=True,
                requires_local_correction=False,
            )

        except Exception as exc:
            logger.error(f"FuenteERA5Land: error para '{zona}' — {exc}")
            return PronosticoMeteorologico(
                fuente=self.nombre, zona=zona, horizonte_h=0,
                lat=coords[0], lon=coords[1],
                fuente_disponible=False, error=str(exc),
            )

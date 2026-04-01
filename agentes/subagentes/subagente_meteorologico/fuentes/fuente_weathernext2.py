"""
FuenteWeatherNext2 — Fuente meteorológica opcional (ensemble 64 miembros).

WeatherNext 2 (DeepMind, GA noviembre 2025): ensemble de 64 miembros,
15 días de horizonte, 6.5% mejor CRPS. Disponible via:
  - BigQuery Analytics Hub (recomendado para producción)
  - Earth Engine (asset no disponible actualmente)

ESTADO: Requiere suscripción manual en Analytics Hub de GCP.
  1. Ir a: console.cloud.google.com/bigquery/analytics-hub
  2. Buscar "WeatherNext 2"
  3. Suscribir dataset al proyecto climas-chileno
  4. El dataset quedará en: `climas-chileno.weathernext_2`
  5. Activar con: USE_WEATHERNEXT2=true (variable de entorno)

CAVEATS CHILE-ESPECÍFICOS (documentados para tesis):
  - Resolución 0.25° (~28km): La Parva y Valle Nevado caen en misma celda
  - Sin snow depth, SWE ni nieve nueva — solo precipitación líquido-equivalente
  - Sesgo cálido sistemático en altitudes de ski (orografía suavizada)
  - Subestimación de precipitación orográfica en ladera windward chilena
  - Subrepresentación de ráfagas en cumbres (señal crítica para wind slab)
  Todo esto se registra con requires_local_correction=True

Mientras no haya acceso → disponible=False, retorna PronosticoMeteorologico con error.
"""

import logging
import os
from typing import Optional
from agentes.subagentes.subagente_meteorologico.fuentes.base import (
    FuenteMeteorologica,
    PronosticoMeteorologico,
)

logger = logging.getLogger(__name__)

# Flag de activación
_USE_WEATHERNEXT2 = os.environ.get("USE_WEATHERNEXT2", "false").lower() == "true"

# Dataset en BigQuery (después de suscripción en Analytics Hub)
_BQ_DATASET = "climas-chileno.weathernext_2"
_BQ_TABLE = f"{_BQ_DATASET}.forecasts"

_COORDS_ZONAS = {
    "La Parva": (-33.354, -70.298),
    "Valle Nevado": (-33.357, -70.270),
    "El Colorado": (-33.360, -70.289),
}

# Celda 0.25° que cubre ambas zonas
_BBOX_ANDES_CENTRAL = {
    "lat_min": -33.5, "lat_max": -33.25,
    "lon_min": -70.5, "lon_max": -70.25,
}


class FuenteWeatherNext2(FuenteMeteorologica):
    """
    Fuente WeatherNext 2: ensemble 64 miembros via BigQuery Analytics Hub.

    NOTA: Requiere suscripción manual antes de activar.
    Mientras USE_WEATHERNEXT2=false (default), retorna disponible=False.
    """

    @property
    def nombre(self) -> str:
        return "weathernext_2"

    @property
    def disponible(self) -> bool:
        return _USE_WEATHERNEXT2 and self._verificar_acceso_bq()

    def _verificar_acceso_bq(self) -> bool:
        """Verifica que el dataset esté suscrito y accesible."""
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project="climas-chileno")
            dataset = client.get_dataset("climas-chileno.weathernext_2")
            return dataset is not None
        except Exception:
            return False

    def obtener_pronostico(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int = 72,
    ) -> PronosticoMeteorologico:
        """
        Obtiene pronóstico determinista de WeatherNext 2 (mediana del ensemble).

        Usa el miembro P50 del ensemble de 64 para el pronóstico principal.
        Para el ensemble completo, usar obtener_ensemble().
        """
        if not self.disponible:
            return PronosticoMeteorologico(
                fuente=self.nombre, zona=zona, horizonte_h=horizonte_h,
                lat=lat, lon=lon,
                fuente_disponible=False,
                error=(
                    "WeatherNext 2 no disponible. "
                    "Requiere suscripción en Analytics Hub y USE_WEATHERNEXT2=true. "
                    "Ver docstring de fuente_weathernext2.py para instrucciones."
                ),
            )

        try:
            ensemble = self._query_ensemble(zona, lat, lon, horizonte_h)
            if not ensemble:
                return PronosticoMeteorologico(
                    fuente=self.nombre, zona=zona, horizonte_h=horizonte_h,
                    lat=lat, lon=lon, fuente_disponible=False,
                    error="Sin datos WN2 para la zona/horizonte solicitado",
                )
            return self._calcular_percentiles(ensemble, zona, lat, lon, horizonte_h)

        except Exception as exc:
            logger.error(f"FuenteWeatherNext2: error para '{zona}' — {exc}")
            return PronosticoMeteorologico(
                fuente=self.nombre, zona=zona, horizonte_h=horizonte_h,
                lat=lat, lon=lon, fuente_disponible=False, error=str(exc),
            )

    def obtener_ensemble(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int = 72,
    ) -> list[PronosticoMeteorologico]:
        """
        Obtiene los 64 miembros del ensemble de WeatherNext 2.

        Returns:
            Lista de PronosticoMeteorologico, uno por miembro del ensemble.
            Lista vacía si no disponible.
        """
        if not self.disponible:
            logger.warning("FuenteWeatherNext2.obtener_ensemble: fuente no disponible")
            return []

        try:
            return self._query_ensemble(zona, lat, lon, horizonte_h)
        except Exception as exc:
            logger.error(f"FuenteWeatherNext2.obtener_ensemble: {exc}")
            return []

    def _query_ensemble(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int,
    ) -> list[PronosticoMeteorologico]:
        """
        Query BigQuery para obtener los 64 miembros del ensemble.

        Schema de forecasts WN2 (documentado en colab oficial Google):
        - init_time: TIMESTAMP (hora de inicialización del modelo)
        - valid_time: TIMESTAMP (hora para la que aplica el pronóstico)
        - latitude, longitude: FLOAT64 (celda 0.25°)
        - member: INT64 (0-63, miembro del ensemble)
        - 2m_temperature: FLOAT64 (Kelvin)
        - total_precipitation_6hr: FLOAT64 (mm)
        - 10m_u_component_of_wind: FLOAT64 (m/s)
        - 10m_v_component_of_wind: FLOAT64 (m/s)
        - relative_humidity_2m: FLOAT64 (%)
        """
        from google.cloud import bigquery
        import math

        client = bigquery.Client(project="climas-chileno")

        # Celda WN2 más cercana (0.25° grid)
        lat_celda = round(lat * 4) / 4
        lon_celda = round(lon * 4) / 4

        sql = f"""
        SELECT
            member,
            valid_time,
            `2m_temperature` - 273.15 AS temperatura_c,
            `total_precipitation_6hr` AS precip_6h_mm,
            SQRT(POW(`10m_u_component_of_wind`, 2) + POW(`10m_v_component_of_wind`, 2)) * 3.6
                AS viento_kmh,
            ATAN2(`10m_u_component_of_wind`, `10m_v_component_of_wind`) * 180 / ACOS(-1) + 180
                AS direccion_viento_deg,
            `relative_humidity_2m` AS humedad_pct
        FROM `{_BQ_TABLE}`
        WHERE latitude = @lat_celda
          AND longitude = @lon_celda
          AND init_time = (
              SELECT MAX(init_time) FROM `{_BQ_TABLE}`
              WHERE latitude = @lat_celda AND longitude = @lon_celda
          )
          AND valid_time <= TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL @horizonte_h HOUR)
        ORDER BY member, valid_time
        """

        params = [
            bigquery.ScalarQueryParameter("lat_celda", "FLOAT64", lat_celda),
            bigquery.ScalarQueryParameter("lon_celda", "FLOAT64", lon_celda),
            bigquery.ScalarQueryParameter("horizonte_h", "INT64", horizonte_h),
        ]

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        rows = list(client.query(sql, job_config=job_config).result())

        if not rows:
            return []

        # Agrupar por miembro y agregar en el horizonte
        miembros: dict[int, dict] = {}
        for row in rows:
            m = row["member"]
            if m not in miembros:
                miembros[m] = {"precip_total": 0.0, "temps": [], "vientos": [], "humedades": []}
            miembros[m]["precip_total"] += row["precip_6h_mm"] or 0.0
            if row["temperatura_c"] is not None:
                miembros[m]["temps"].append(row["temperatura_c"])
            if row["viento_kmh"] is not None:
                miembros[m]["vientos"].append(row["viento_kmh"])
            if row["humedad_pct"] is not None:
                miembros[m]["humedades"].append(row["humedad_pct"])

        coords = _COORDS_ZONAS.get(zona, (lat_celda, lon_celda))
        pronosticos = []
        for m_id, datos in miembros.items():
            temp_media = sum(datos["temps"]) / len(datos["temps"]) if datos["temps"] else None
            viento_max = max(datos["vientos"]) if datos["vientos"] else None
            humedad = sum(datos["humedades"]) / len(datos["humedades"]) if datos["humedades"] else None

            pronosticos.append(PronosticoMeteorologico(
                fuente=self.nombre,
                zona=zona,
                horizonte_h=horizonte_h,
                lat=lat_celda,
                lon=lon_celda,
                temperatura_2m_c=round(temp_media, 1) if temp_media is not None else None,
                precipitacion_mm=round(datos["precip_total"], 1),
                viento_10m_kmh=round(viento_max, 1) if viento_max is not None else None,
                humedad_pct=round(humedad, 1) if humedad is not None else None,
                ensemble_id=m_id,
                n_miembros_ensemble=len(miembros),
                fuente_disponible=True,
                requires_local_correction=True,  # Sesgo orográfico chileno
            ))

        logger.info(
            f"FuenteWeatherNext2: '{zona}' — {len(pronosticos)} miembros ensemble, "
            f"celda ({lat_celda}, {lon_celda})"
        )
        return pronosticos

    def _calcular_percentiles(
        self,
        ensemble: list[PronosticoMeteorologico],
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int,
    ) -> PronosticoMeteorologico:
        """Calcula P10/P50/P90 del ensemble y retorna el pronóstico central."""
        precips = sorted([p.precipitacion_mm for p in ensemble if p.precipitacion_mm is not None])
        temps = sorted([p.temperatura_2m_c for p in ensemble if p.temperatura_2m_c is not None])

        n = len(precips)
        p10_p = precips[int(n * 0.1)] if precips else None
        p50_p = precips[int(n * 0.5)] if precips else None
        p90_p = precips[int(n * 0.9)] if precips else None

        n_t = len(temps)
        p10_t = temps[int(n_t * 0.1)] if temps else None
        p90_t = temps[int(n_t * 0.9)] if temps else None

        # Miembro central (P50)
        central = ensemble[len(ensemble) // 2]
        central.p10_precipitacion = p10_p
        central.p50_precipitacion = p50_p
        central.p90_precipitacion = p90_p
        central.p10_temperatura = p10_t
        central.p90_temperatura = p90_t
        central.n_miembros_ensemble = len(ensemble)
        return central

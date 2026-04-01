"""
FuenteMeteorologica — Interfaz abstracta para fuentes de datos meteorológicos.

Todas las fuentes (Open-Meteo, ERA5-Land, WeatherNext 2) implementan esta interfaz.
El consolidador las trata de forma uniforme para producir el pronóstico final.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PronosticoMeteorologico:
    """
    Pronóstico meteorológico normalizado al schema común.

    Todas las fuentes producen este schema. Los campos opcionales
    son None cuando la fuente no los provee.
    """
    # Identificación
    fuente: str                           # "open_meteo" | "era5_land" | "weathernext_2"
    zona: str
    horizonte_h: int                      # Horas de pronóstico adelante
    lat: float
    lon: float

    # Variables EAWS-críticas (todas las fuentes deben proveer)
    temperatura_2m_c: Optional[float] = None
    precipitacion_mm: Optional[float] = None    # Acumulada en el horizonte
    viento_10m_kmh: Optional[float] = None
    direccion_viento_deg: Optional[float] = None
    humedad_pct: Optional[float] = None

    # Solo WeatherNext 2 (None para otras fuentes)
    ensemble_id: Optional[int] = None
    n_miembros_ensemble: Optional[int] = None

    # Probabilísticos derivados (de ensemble o estimados)
    p10_precipitacion: Optional[float] = None
    p50_precipitacion: Optional[float] = None
    p90_precipitacion: Optional[float] = None
    p10_temperatura: Optional[float] = None
    p90_temperatura: Optional[float] = None

    # Flags de calidad
    requires_local_correction: bool = False  # Sesgo orográfico conocido
    fuente_disponible: bool = True
    error: Optional[str] = None


class FuenteMeteorologica(ABC):
    """
    Interfaz abstracta para fuentes de datos meteorológicos.

    Implementaciones:
    - FuenteOpenMeteo: Open-Meteo API via BigQuery (primaria)
    - FuenteERA5Land: ERA5-Land via BigQuery (secundaria)
    - FuenteWeatherNext2: WeatherNext 2 via BQ Analytics Hub (opcional)
    """

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Identificador de la fuente: 'open_meteo', 'era5_land', 'weathernext_2'."""
        ...

    @property
    @abstractmethod
    def disponible(self) -> bool:
        """True si la fuente tiene datos accesibles en este ciclo."""
        ...

    @abstractmethod
    def obtener_pronostico(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int = 72,
    ) -> PronosticoMeteorologico:
        """
        Obtiene el pronóstico determinista para la zona.

        Args:
            zona: Nombre de la ubicación (para lookup en BQ)
            lat: Latitud del punto de interés
            lon: Longitud del punto de interés
            horizonte_h: Horas de pronóstico adelante

        Returns:
            PronosticoMeteorologico con datos de la fuente
        """
        ...

    def obtener_ensemble(
        self,
        zona: str,
        lat: float,
        lon: float,
        horizonte_h: int = 72,
    ) -> list[PronosticoMeteorologico]:
        """
        Obtiene los miembros del ensemble (solo WeatherNext 2).

        Por defecto retorna lista con un solo miembro (el pronóstico determinista).
        Las fuentes sin ensemble sobreescriben si necesitan.
        """
        return [self.obtener_pronostico(zona, lat, lon, horizonte_h)]

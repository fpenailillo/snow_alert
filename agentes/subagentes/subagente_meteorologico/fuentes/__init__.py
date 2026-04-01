"""
Fuentes meteorológicas para S3.

Patrón Strategy: cada fuente implementa FuenteMeteorologica.
El consolidador decide qué fuentes usar según USE_WEATHERNEXT2_AS_PRIMARY.

Fuentes disponibles:
  - FuenteOpenMeteo    (primaria, siempre activa)
  - FuenteERA5Land     (secundaria, siempre activa)
  - FuenteWeatherNext2 (opcional, flag USE_WEATHERNEXT2=true — requiere suscripción Analytics Hub)
"""

from agentes.subagentes.subagente_meteorologico.fuentes.base import FuenteMeteorologica
from agentes.subagentes.subagente_meteorologico.fuentes.fuente_open_meteo import FuenteOpenMeteo
from agentes.subagentes.subagente_meteorologico.fuentes.fuente_era5_land import FuenteERA5Land
from agentes.subagentes.subagente_meteorologico.fuentes.fuente_weathernext2 import FuenteWeatherNext2

__all__ = [
    "FuenteMeteorologica",
    "FuenteOpenMeteo",
    "FuenteERA5Land",
    "FuenteWeatherNext2",
]

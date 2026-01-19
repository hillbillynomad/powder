"""Weather forecast providers.

See MODELS.md for documentation on the underlying weather models,
their strengths, weaknesses, and optimal use cases.
"""

from .base import ForecastProvider
from .bom import BOMProvider
from .ecmwf import ECMWFProvider
from .icon import ICONProvider
from .jma import JMAProvider
from .nws import NWSProvider
from .open_meteo import OpenMeteoProvider

# European countries for ICON provider
EUROPEAN_COUNTRIES = {
    "AD", "AT", "BG", "CH", "CZ", "DE", "ES", "FI", "FR", "IT",
    "NO", "PL", "RO", "SE", "SI", "SK"
}

__all__ = [
    "ForecastProvider",
    "BOMProvider",
    "ECMWFProvider",
    "EUROPEAN_COUNTRIES",
    "ICONProvider",
    "JMAProvider",
    "NWSProvider",
    "OpenMeteoProvider",
]

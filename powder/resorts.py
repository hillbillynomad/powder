"""Ski resort data and configuration."""

from dataclasses import dataclass


@dataclass
class SkiResort:
    """Represents a ski resort with location data."""
    name: str
    state: str
    latitude: float
    longitude: float
    elevation_ft: int


# Park City, UT coordinates (base area)
PARK_CITY = SkiResort(
    name="Park City Mountain",
    state="UT",
    latitude=40.6514,
    longitude=-111.5080,
    elevation_ft=6900,
)

# All supported resorts (initially just Park City)
RESORTS = {
    "park_city": PARK_CITY,
}

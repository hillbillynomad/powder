"""Ski resort data and configuration."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkiResort:
    """Represents a ski resort with location data."""
    name: str
    country: str  # ISO 3166-1 alpha-2 (e.g., "US", "FR", "JP")
    region: str  # State/province/region (e.g., "Utah", "Savoie", "Hokkaido")
    latitude: float
    longitude: float
    elevation_ft: int
    lift_count: int = 0  # Total lifts (chairs, gondolas, trams, T-bars)
    avg_snowfall_inches: int | None = None
    pass_type: str | None = None  # "EPIC", "IKON", or None
    timezone: str = "UTC"  # IANA timezone (e.g., "America/Denver", "Europe/Paris")

    @property
    def state(self) -> str:
        """Alias for region (backward compatibility)."""
        return self.region


def get_default_config_path() -> Path:
    """Get the path to the default resorts config file."""
    return Path(__file__).parent / "data" / "resorts.json"


def load_resorts(config_path: Path | None = None) -> list[SkiResort]:
    """Load ski resorts from a JSON configuration file.

    Args:
        config_path: Path to the JSON config file. If None, uses the default
                     package data file.

    Returns:
        List of SkiResort objects.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        json.JSONDecodeError: If the config file is invalid JSON.
        KeyError: If required fields are missing from a resort entry.
    """
    if config_path is None:
        config_path = get_default_config_path()

    with open(config_path, "r") as f:
        data = json.load(f)

    resorts = []
    for entry in data.get("resorts", []):
        # Support both old "state" and new "region" field names
        region = entry.get("region") or entry.get("state", "")
        resort = SkiResort(
            name=entry["name"],
            country=entry.get("country", "US"),
            region=region,
            latitude=entry["latitude"],
            longitude=entry["longitude"],
            elevation_ft=entry["elevation_ft"],
            lift_count=entry.get("lift_count", 0),
            avg_snowfall_inches=entry.get("avg_snowfall_inches"),
            pass_type=entry.get("pass_type"),
            timezone=entry.get("timezone", "UTC"),
        )
        resorts.append(resort)

    return resorts


def filter_resorts(
    resorts: list[SkiResort],
    name_filter: str | None = None,
    country_filter: str | None = None,
    region_filter: str | None = None,
    pass_filter: str | None = None,
    state_filter: str | None = None,  # Deprecated alias for region_filter
) -> list[SkiResort]:
    """Filter resorts by name, country, region, and/or pass type.

    Args:
        resorts: List of resorts to filter.
        name_filter: Partial match on resort name (case-insensitive).
        country_filter: Exact match on country code (case-insensitive).
        region_filter: Exact match on region/state (case-insensitive).
        pass_filter: Exact match on pass type (case-insensitive).
        state_filter: Deprecated alias for region_filter.

    Returns:
        Filtered list of resorts.
    """
    # Support deprecated state_filter as alias for region_filter
    if state_filter and not region_filter:
        region_filter = state_filter

    result = resorts

    if name_filter:
        name_lower = name_filter.lower()
        result = [r for r in result if name_lower in r.name.lower()]

    if country_filter:
        country_upper = country_filter.upper()
        result = [r for r in result if r.country.upper() == country_upper]

    if region_filter:
        region_upper = region_filter.upper()
        result = [r for r in result if r.region.upper() == region_upper]

    if pass_filter:
        pass_upper = pass_filter.upper()
        result = [r for r in result if r.pass_type and r.pass_type.upper() == pass_upper]

    return result


# Keep PARK_CITY for backward compatibility
PARK_CITY = SkiResort(
    name="Park City Mountain",
    country="US",
    region="UT",
    latitude=40.6514,
    longitude=-111.5080,
    elevation_ft=6900,
    lift_count=41,
    avg_snowfall_inches=355,
    pass_type="EPIC",
    timezone="America/Denver",
)

# Legacy dict - deprecated, use load_resorts() instead
RESORTS = {
    "park_city": PARK_CITY,
}

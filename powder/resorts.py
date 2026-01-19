"""Ski resort data and configuration."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkiResort:
    """Represents a ski resort with location data."""
    name: str
    state: str
    latitude: float
    longitude: float
    elevation_ft: int
    avg_snowfall_inches: int | None = None
    pass_type: str | None = None  # "EPIC", "IKON", or None
    country: str = "US"  # "US" or "CA"


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
        resort = SkiResort(
            name=entry["name"],
            state=entry["state"],
            latitude=entry["latitude"],
            longitude=entry["longitude"],
            elevation_ft=entry["elevation_ft"],
            avg_snowfall_inches=entry.get("avg_snowfall_inches"),
            pass_type=entry.get("pass_type"),
            country=entry.get("country", "US"),
        )
        resorts.append(resort)

    return resorts


def filter_resorts(
    resorts: list[SkiResort],
    name_filter: str | None = None,
    state_filter: str | None = None,
    pass_filter: str | None = None,
) -> list[SkiResort]:
    """Filter resorts by name, state, and/or pass type.

    Args:
        resorts: List of resorts to filter.
        name_filter: Partial match on resort name (case-insensitive).
        state_filter: Exact match on state abbreviation (case-insensitive).
        pass_filter: Exact match on pass type (case-insensitive).

    Returns:
        Filtered list of resorts.
    """
    result = resorts

    if name_filter:
        name_lower = name_filter.lower()
        result = [r for r in result if name_lower in r.name.lower()]

    if state_filter:
        state_upper = state_filter.upper()
        result = [r for r in result if r.state.upper() == state_upper]

    if pass_filter:
        pass_upper = pass_filter.upper()
        result = [r for r in result if r.pass_type and r.pass_type.upper() == pass_upper]

    return result


# Keep PARK_CITY for backward compatibility
PARK_CITY = SkiResort(
    name="Park City Mountain",
    state="UT",
    latitude=40.6514,
    longitude=-111.5080,
    elevation_ft=6900,
    avg_snowfall_inches=355,
    pass_type="EPIC",
)

# Legacy dict - deprecated, use load_resorts() instead
RESORTS = {
    "park_city": PARK_CITY,
}

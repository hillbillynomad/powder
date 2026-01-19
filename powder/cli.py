"""Command-line interface for Powder snowfall forecast tracker."""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from .cache import set_cache_enabled
from .forecast import DailyForecast, ForecastResult, calculate_avg_forecasts
from .providers import ECMWFProvider, NWSProvider, OpenMeteoProvider
from .resorts import SkiResort, filter_resorts, load_resorts


def fetch_historical_snowfall(resort: SkiResort) -> list[DailyForecast]:
    """Fetch 14-day historical snowfall for a resort.

    Uses only Open-Meteo Archive API (no averaging needed since it's
    actual measured data, not forecasts).
    """
    provider = OpenMeteoProvider()
    print(f"Fetching historical data from {provider.name} Archive...")
    return provider.get_historical_snowfall(resort, days=14)


def fetch_all_forecasts(resort: SkiResort) -> dict[date, list[DailyForecast]]:
    """Fetch forecasts from all providers and organize by date.

    Each provider is queried for its maximum supported forecast range.
    Returns all dates that have at least one forecast.
    """
    # Three providers using different underlying models:
    # - Open-Meteo/GFS: up to 16 days
    # - NWS: ~7 days (US only)
    # - ECMWF: up to 10 days
    # See providers/MODELS.md for details
    providers_with_max_days = [
        (OpenMeteoProvider(), 16),
        (ECMWFProvider(), 10),
    ]

    # NWS only covers the US
    if resort.country == "US":
        providers_with_max_days.append((NWSProvider(), 7))

    all_forecasts: dict[date, list[DailyForecast]] = defaultdict(list)

    for provider, max_days in providers_with_max_days:
        print(f"Fetching forecast from {provider.name}...")
        forecasts = provider.get_snowfall_forecast(resort, max_days)
        for forecast in forecasts:
            all_forecasts[forecast.date].append(forecast)

    return all_forecasts


def display_forecasts(resort: SkiResort) -> None:
    """Display snowfall forecasts for a resort."""
    print(f"\n{'=' * 60}")
    print(f"  Snowfall Forecast: {resort.name}, {resort.state}")
    print(f"  Elevation: {resort.elevation_ft:,} ft")
    print(f"{'=' * 60}\n")

    all_forecasts = fetch_all_forecasts(resort)

    if not all_forecasts:
        print("No forecast data available.")
        return

    results = calculate_avg_forecasts(all_forecasts)

    # Print header (models: GFS, NWS Blend, ECMWF IFS)
    print(f"{'Date':<12} {'Avg':>8} {'GFS':>8} {'NWS':>8} {'ECMWF':>8}")
    print("-" * 46)

    for result in results:
        date_str = result.date.strftime("%a %m/%d")

        # Get individual source values
        source_values = {f.source: f.snowfall_inches for f in result.forecasts}
        gfs = source_values.get("Open-Meteo", "-")
        nws = source_values.get("NWS", "-")
        ecmwf = source_values.get("ECMWF", "-")

        # Format values
        def fmt(val):
            if val == "-":
                return "-"
            return f"{val:.1f}\""

        avg_str = f"{result.avg_snowfall_inches:.1f}\""

        print(
            f"{date_str:<12} {avg_str:>8} {fmt(gfs):>8} {fmt(nws):>8} {fmt(ecmwf):>8}"
        )

    # Print summary
    total_avg = sum(r.avg_snowfall_inches for r in results)
    print("-" * 46)
    print(f"{'Total'::<12} {total_avg:.1f}\"")
    print()


def build_resort_forecast_data(resort: SkiResort) -> dict:
    """Build forecast data for a single resort in JSON-serializable format."""
    all_forecasts = fetch_all_forecasts(resort)
    results = calculate_avg_forecasts(all_forecasts)

    daily_forecasts = []
    for result in results:
        source_values = {f.source: f.snowfall_inches for f in result.forecasts}
        daily_forecasts.append({
            "date": result.date.isoformat(),
            "avg_inches": round(result.avg_snowfall_inches, 1),
            "sources": {
                "Open-Meteo": round(source_values.get("Open-Meteo", 0), 1),
                "NWS": round(source_values.get("NWS", 0), 1),
                "ECMWF": round(source_values.get("ECMWF", 0), 1),
            }
        })

    # Fetch historical data
    historical = fetch_historical_snowfall(resort)
    historical_data = []
    for h in historical:
        historical_data.append({
            "date": h.date.isoformat(),
            "snowfall_inches": h.snowfall_inches,
        })

    total_forecast = sum(r.avg_snowfall_inches for r in results)
    total_historical = sum(h.snowfall_inches for h in historical)

    return {
        "name": resort.name,
        "state": resort.state,
        "latitude": resort.latitude,
        "longitude": resort.longitude,
        "elevation_ft": resort.elevation_ft,
        "pass_type": resort.pass_type,
        "total_snowfall_inches": round(total_forecast, 1),
        "daily_forecasts": daily_forecasts,
        "total_historical_inches": round(total_historical, 1),
        "historical_snowfall": historical_data,
    }


def export_json(resorts: list[SkiResort], output_path: Path) -> None:
    """Export forecast data for all resorts to JSON file."""
    print(f"Exporting forecasts for {len(resorts)} resorts...")

    resort_data = []
    for i, resort in enumerate(resorts, 1):
        print(f"[{i}/{len(resorts)}] {resort.name}...")
        resort_data.append(build_resort_forecast_data(resort))

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "resorts": resort_data,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nExported to {output_path}")


def list_resorts(resorts: list[SkiResort]) -> None:
    """Display a list of available resorts."""
    print(f"\n{'Available Ski Resorts':^60}")
    print("=" * 60)
    print(f"{'Resort Name':<30} {'State':>5} {'Elev':>8} {'Pass':>8}")
    print("-" * 60)

    # Sort by state, then by name
    sorted_resorts = sorted(resorts, key=lambda r: (r.state, r.name))

    for resort in sorted_resorts:
        pass_str = resort.pass_type if resort.pass_type else "-"
        print(f"{resort.name:<30} {resort.state:>5} {resort.elevation_ft:>7}' {pass_str:>8}")

    print("-" * 60)
    print(f"Total: {len(resorts)} resorts")
    print()


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Powder - Ski Resort Snowfall Forecast Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  powder                      Show forecast for all resorts
  powder --resort "Park City" Show forecast for Park City
  powder --state CO           Show forecasts for Colorado resorts
  powder --pass EPIC          Show forecasts for EPIC pass resorts
  powder --list               List all available resorts
  powder --list --state UT    List Utah resorts only
        """,
    )
    parser.add_argument(
        "--resort", "-r",
        type=str,
        help="Filter by resort name (partial match, case-insensitive)",
    )
    parser.add_argument(
        "--state", "-s",
        type=str,
        help="Filter by state abbreviation (e.g., UT, CO)",
    )
    parser.add_argument(
        "--pass", "-p",
        dest="pass_type",
        type=str,
        choices=["EPIC", "IKON", "epic", "ikon"],
        help="Filter by pass type (EPIC or IKON)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available resorts without fetching forecasts",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass cache and fetch fresh data from APIs",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Export forecast data to JSON for web UI",
    )

    args = parser.parse_args()

    # Configure caching based on --no-cache flag
    if args.no_cache:
        set_cache_enabled(False)

    # Load resorts from config
    try:
        resorts = load_resorts()
    except FileNotFoundError:
        print("Error: Resort configuration file not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading resort configuration: {e}", file=sys.stderr)
        sys.exit(1)

    # Apply filters
    filtered_resorts = filter_resorts(
        resorts,
        name_filter=args.resort,
        state_filter=args.state,
        pass_filter=args.pass_type,
    )

    if not filtered_resorts:
        print("No resorts match the specified filters.")
        sys.exit(0)

    # List mode - just show resorts without fetching forecasts
    if args.list:
        list_resorts(filtered_resorts)
        return

    # Export JSON mode - generate data for web UI
    if args.export_json:
        output_path = Path(__file__).parent / "web" / "data" / "forecasts.json"
        export_json(filtered_resorts, output_path)
        return

    # Fetch and display forecasts for each resort
    for resort in filtered_resorts:
        display_forecasts(resort)


if __name__ == "__main__":
    main()

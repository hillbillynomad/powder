"""Command-line interface for Powder snowfall forecast tracker."""

import argparse
from collections import defaultdict
from datetime import date

from .forecast import DailyForecast, calculate_median_forecasts
from .providers import NWSProvider, OpenMeteoProvider, WeatherAPIProvider
from .resorts import PARK_CITY, SkiResort


def fetch_all_forecasts(resort: SkiResort, days: int = 7) -> dict[date, list[DailyForecast]]:
    """Fetch forecasts from all providers and organize by date."""
    providers = [
        OpenMeteoProvider(),
        NWSProvider(),
        WeatherAPIProvider(),
    ]

    all_forecasts: dict[date, list[DailyForecast]] = defaultdict(list)

    for provider in providers:
        print(f"Fetching forecast from {provider.name}...")
        forecasts = provider.get_snowfall_forecast(resort, days)
        for forecast in forecasts:
            all_forecasts[forecast.date].append(forecast)

    return all_forecasts


def display_forecasts(resort: SkiResort, days: int = 7) -> None:
    """Display snowfall forecasts for a resort."""
    print(f"\n{'=' * 60}")
    print(f"  Snowfall Forecast: {resort.name}, {resort.state}")
    print(f"  Elevation: {resort.elevation_ft:,} ft")
    print(f"{'=' * 60}\n")

    all_forecasts = fetch_all_forecasts(resort, days)

    if not all_forecasts:
        print("No forecast data available.")
        return

    results = calculate_median_forecasts(all_forecasts)

    # Print header
    print(f"{'Date':<12} {'Median':>8} {'Open-Meteo':>12} {'NWS':>8} {'wttr.in':>10}")
    print("-" * 52)

    for result in results:
        date_str = result.date.strftime("%a %m/%d")

        # Get individual source values
        source_values = {f.source: f.snowfall_inches for f in result.forecasts}
        open_meteo = source_values.get("Open-Meteo", "-")
        nws = source_values.get("NWS", "-")
        wttr = source_values.get("wttr.in", "-")

        # Format values
        def fmt(val):
            if val == "-":
                return "-"
            return f"{val:.1f}\""

        median_str = f"{result.median_snowfall_inches:.1f}\""

        print(
            f"{date_str:<12} {median_str:>8} {fmt(open_meteo):>12} {fmt(nws):>8} {fmt(wttr):>10}"
        )

    # Print summary
    total_median = sum(r.median_snowfall_inches for r in results)
    print("-" * 52)
    print(f"{'Total'::<12} {total_median:.1f}\"")
    print()


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Powder - Ski Resort Snowfall Forecast Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  powder                  Show 7-day forecast for Park City
  powder --days 3         Show 3-day forecast
        """,
    )
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=7,
        help="Number of days to forecast (default: 7)",
    )

    args = parser.parse_args()

    # For now, only support Park City
    display_forecasts(PARK_CITY, args.days)


if __name__ == "__main__":
    main()

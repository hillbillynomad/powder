"""Validate the exported forecast JSON before it is deployed.

Fails (exit 1) if the export is missing resorts or too many resorts have no
weather data, e.g. when an upstream provider was down or rate limiting.

Usage:
    python scripts/validate_export.py [forecasts.json] [--max-missing-pct 3]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPORT = ROOT / "powder" / "web" / "data" / "forecasts.json"
RESORTS = ROOT / "powder" / "data" / "resorts.json"


def validate(export_path: Path, max_missing_pct: float) -> list[str]:
    """Return a list of problems; empty means the export is healthy."""
    problems: list[str] = []
    exported = json.loads(export_path.read_text(encoding="utf-8"))["resorts"]
    expected = json.loads(RESORTS.read_text(encoding="utf-8"))["resorts"]

    exported_names = {r["name"] for r in exported}
    missing_resorts = sorted({r["name"] for r in expected} - exported_names)
    if missing_resorts:
        problems.append(f"{len(missing_resorts)} resorts missing from export: {missing_resorts}")

    no_data = sorted(
        r["name"] for r in exported if not r["daily_forecasts"] or not r["historical_snowfall"]
    )
    pct = 100 * len(no_data) / max(len(exported), 1)
    if pct > max_missing_pct:
        problems.append(
            f"{len(no_data)} resorts ({pct:.1f}%) lack forecast or historical data "
            f"(limit {max_missing_pct}%): {no_data}"
        )
    elif no_data:
        print(f"warning: {len(no_data)} resorts lack data: {no_data}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", nargs="?", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--max-missing-pct", type=float, default=3.0)
    args = parser.parse_args()

    problems = validate(args.export, args.max_missing_pct)
    for p in problems:
        print(f"ERROR: {p}")
    if not problems:
        print("Export OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

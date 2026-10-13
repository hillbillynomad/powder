"""Integrity checks for the bundled resorts.json dataset."""

import json
import re
from pathlib import Path

import pytest

from powder.resorts import get_default_config_path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "powder" / "web" / "js" / "app.js"


@pytest.fixture(scope="module")
def raw_resorts():
    with open(get_default_config_path(), encoding="utf-8") as f:
        return json.load(f)["resorts"]


@pytest.mark.unit
@pytest.mark.resorts
class TestResortDataIntegrity:
    def test_names_are_unique(self, raw_resorts):
        names = [r["name"].lower() for r in raw_resorts]
        assert len(names) == len(set(names))

    def test_required_fields_and_ranges(self, raw_resorts):
        for r in raw_resorts:
            assert -90 <= r["latitude"] <= 90, r["name"]
            assert -180 <= r["longitude"] <= 180, r["name"]
            assert r["elevation_peak_ft"] > r["elevation_base_ft"] > 0, r["name"]
            assert r["timezone"] and r["timezone"] != "UTC", r["name"]

    def test_pass_type_values(self, raw_resorts):
        assert {r["pass_type"] for r in raw_resorts} <= {None, "EPIC", "IKON"}

    def test_every_country_has_a_display_name_in_web_ui(self, raw_resorts):
        """The map UI falls back to the raw ISO code if a country is missing."""
        js = APP_JS.read_text(encoding="utf-8")
        block = re.search(r"COUNTRY_NAMES\s*=\s*\{(.*?)\};", js, re.S).group(1)
        known = set(re.findall(r"'([A-Z]{2})'\s*:", block))
        countries = {r["country"] for r in raw_resorts}
        assert countries <= known, f"Missing in COUNTRY_NAMES: {sorted(countries - known)}"

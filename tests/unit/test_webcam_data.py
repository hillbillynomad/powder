"""Integrity checks for powder/data/webcams.json (offline; live link checks are in tools/webcams/check.py)."""

import json

import pytest

from powder import webcams
from powder.resorts import get_default_config_path
from powder.webcams import load_webcams, webcams_for


@pytest.fixture(scope="module")
def data():
    with open(webcams.WEBCAMS_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def resort_names():
    with open(get_default_config_path(), encoding="utf-8") as f:
        return {r["name"] for r in json.load(f)["resorts"]}


@pytest.mark.unit
@pytest.mark.resorts
class TestWebcamDataIntegrity:
    def test_every_key_is_a_resort(self, data, resort_names):
        unknown = sorted(set(data) - resort_names)
        assert not unknown, f"webcams.json names not in resorts.json: {unknown}"

    def test_links_are_well_formed(self, data):
        for name, links in data.items():
            assert isinstance(links, list), name
            for link in links:
                assert set(link) == {"label", "url"}, name
                assert link["label"].strip(), name
                assert link["url"].startswith("https://"), f"{name}: {link['url']}"
                assert " " not in link["url"], f"{name}: {link['url']}"

    def test_no_duplicate_links_within_resort(self, data):
        for name, links in data.items():
            urls = [link["url"] for link in links]
            assert len(urls) == len(set(urls)), name


@pytest.mark.unit
class TestWebcamsFor:
    def test_northstar(self):
        assert webcams_for("Northstar") == [{
            "label": "Mountain cams",
            "url": "https://www.northstarcalifornia.com/the-mountain/mountain-conditions/mountain-cams.aspx",
        }]

    def test_unknown_resort_has_none(self):
        assert webcams_for("No Such Resort") == []

    def test_missing_file_is_empty(self, tmp_path):
        load_webcams.cache_clear()
        try:
            assert load_webcams(tmp_path / "nope.json") == {}
        finally:
            load_webcams.cache_clear()

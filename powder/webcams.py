"""Links to each resort's official webcam page(s) (powder/data/webcams.json).

Format: {resort name: [{"label": ..., "url": ...}, ...]}. An empty list means we
looked and found no public webcams. Links are checked by tools/webcams/check.py.
"""

import json
from functools import lru_cache
from pathlib import Path

WEBCAMS_PATH = Path(__file__).parent / "data" / "webcams.json"


@lru_cache(maxsize=1)
def load_webcams(path: Path = WEBCAMS_PATH) -> dict[str, list[dict]]:
    """Return {resort name: links}; empty if the file is missing."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def webcams_for(resort_name: str) -> list[dict]:
    """The webcam page links for one resort (possibly none)."""
    return [
        {"label": link["label"], "url": link["url"]}
        for link in load_webcams().get(resort_name, [])
    ]

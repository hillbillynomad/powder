"""Check every webcam link in powder/data/webcams.json, so no broken links ship.

usage:
  poetry run python tools/webcams/check.py [resort name ...] [--browser "<playwright path>"]

A link passes if it loads (2xx after redirects), isn't a 404 page and doesn't bounce
to the site's home page. Some sites block scripts (Vail's serve a ~2 KB placeholder):
those are NEEDS-BROWSER and, with --browser, are rechecked in Playwright, where they
must load and show a cam (an iframe, a video or a large image).

Network errors are retried, then reported UNREACHABLE. Exits 1 unless every link is OK.
Writes a report to tools/webcams/cache/check-report.json.
"""

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
WEBCAMS_PATH = ROOT / "powder" / "data" / "webcams.json"
CACHE = Path(__file__).parent / "cache"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 PowderLinkCheck")
TIMEOUT = 30
RETRIES = 3
MIN_PAGE_BYTES = 3000  # smaller "pages" are usually bot-block placeholders
PER_HOST = 2

OK, BROKEN, NEEDS_BROWSER, UNREACHABLE = "OK", "BROKEN", "NEEDS-BROWSER", "UNREACHABLE"

_host_slots: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(PER_HOST))
_guard = threading.Lock()


def _slot(url: str) -> threading.Semaphore:
    with _guard:
        return _host_slots[urlparse(url).hostname or ""]


def fetch(url: str) -> requests.Response | Exception:
    """GET with retries and backoff; the last error is returned rather than raised."""
    last: requests.Response | Exception = RuntimeError("no attempt")
    for attempt in range(RETRIES):
        try:
            with _slot(url):
                last = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"},
                                    timeout=TIMEOUT, allow_redirects=True)
            if last.status_code < 500 and last.status_code != 429:
                return last
        except requests.RequestException as e:
            last = e
        time.sleep(2 ** attempt)
    return last


def _is_home(url: str) -> bool:
    return urlparse(url).path.rstrip("/") in ("", "/index.html", "/en", "/fr", "/de", "/it", "/ja")


def check_link(url: str) -> tuple[str, str]:
    r = fetch(url)
    if isinstance(r, Exception):
        return UNREACHABLE, f"error: {type(r).__name__}"
    if r.status_code in (404, 410):
        return BROKEN, f"HTTP {r.status_code}"
    if r.status_code in (401, 403, 429) or r.status_code >= 500:
        return NEEDS_BROWSER, f"HTTP {r.status_code} (may be blocking scripts)"
    if r.status_code >= 400:
        return BROKEN, f"HTTP {r.status_code}"
    if _is_home(r.url) and not _is_home(url):
        return BROKEN, f"redirected to home page {r.url}"
    m = re.search(r"<title[^>]*>(.*?)</title>", r.text[:200_000], re.S | re.I)
    title = m.group(1).strip() if m else ""
    if re.search(r"\b404\b|not found|nicht gefunden|introuvable|non trovata", title, re.I):
        return BROKEN, f"404 page: {title!r}"
    if len(r.content) < MIN_PAGE_BYTES or not title:
        return NEEDS_BROWSER, f"{len(r.content)} bytes, title {title!r} (looks blocked)"
    return OK, f"HTTP {r.status_code}, {title[:60]!r}"


def browser_check(rows: list[dict], playwright: str) -> None:
    """Recheck rows in a real browser via check_browser.cjs."""
    CACHE.mkdir(exist_ok=True)
    todo = CACHE / "browser-todo.json"
    todo.write_text(json.dumps([r["url"] for r in rows]))
    out = subprocess.run(["node", str(Path(__file__).parent / "check_browser.cjs"), playwright, str(todo)],
                         capture_output=True, text=True, timeout=60 * 30)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(f"check_browser.cjs failed:\n{out.stderr}")
    results = json.loads(out.stdout)
    for r in rows:
        res = results.get(r["url"], {"ok": False, "detail": "not checked"})
        r["status"] = OK if res["ok"] else BROKEN
        r["detail"] = f"browser: {res['detail']}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resorts", nargs="*", help="only these resort names")
    ap.add_argument("--browser", metavar="PLAYWRIGHT",
                    help="path to the playwright package, to recheck pages that block scripts")
    args = ap.parse_args(argv)

    data = json.loads(WEBCAMS_PATH.read_text(encoding="utf-8"))
    if args.resorts:
        missing = set(args.resorts) - set(data)
        if missing:
            raise SystemExit(f"not in webcams.json: {sorted(missing)}")
        data = {k: v for k, v in data.items() if k in args.resorts}

    rows = [{"resort": name, "label": link["label"], "url": link["url"]}
            for name, links in data.items() for link in links]
    with ThreadPoolExecutor(max_workers=12) as pool:
        for row, (status, detail) in zip(rows, pool.map(lambda r: check_link(r["url"]), rows)):
            row["status"], row["detail"] = status, detail

    retry = [r for r in rows if r["status"] == UNREACHABLE]
    if retry:
        print(f"Retrying {len(retry)} unreachable links in 15 s...")
        time.sleep(15)
        for r in retry:
            r["status"], r["detail"] = check_link(r["url"])

    blocked = [r for r in rows if r["status"] == NEEDS_BROWSER]
    if blocked and args.browser:
        browser_check(blocked, args.browser)

    for r in rows:
        if r["status"] != OK:
            print(f"{r['status']:<13} {r['resort']} / {r['label']}: {r['url']}  [{r['detail']}]")
    counts = Counter(r["status"] for r in rows)
    print(f"\n{len(rows)} links in {len(data)} resorts: " +
          ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))

    CACHE.mkdir(exist_ok=True)
    (CACHE / "check-report.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0 if counts[OK] == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

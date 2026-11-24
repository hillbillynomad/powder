# Snowfall calibration

Fits the factors in `powder/data/snow_calibration.json` by running the app's own snowfall code
(`appmodel.py` -> `open_meteo_common.daily_snowfall`) on the raw archive of the models the
providers pin (GFS global, ECMWF IFS, GEM global) and comparing Nov-Apr season totals with
resort-reported totals. What is fitted is what ships.

```bash
poetry run python tools/calibrate/reported.py                 # OnTheSnow season totals -> reported_seasons.json
poetry run python tools/calibrate/raw.py fetch                # raw precipitation / temperature / humidity per model (~40 min)
poetry run python tools/calibrate/factors.py [--write]        # per provider + region, leave-one-resort-out (rewrites the table)
poetry run python tools/calibrate/anchor.py fetch && poetry run python tools/calibrate/anchor.py write   # other regions: tie GFS/GEM to ECMWF
poetry run python tools/calibrate/resort_factors.py [--write] # per-resort factors; prints the out-of-time gate
poetry run python tools/calibrate/verify.py                   # shipped table through the app code, in-sample
poetry run python tools/calibrate/check_export.py 2026-11-16 5 # sanity-check forecasts.json after an export
```

Run them in that order (`factors.py --write` starts the table afresh). Refit once a year in
spring on the latest seasons and ship only if `resort_factors.py`'s out-of-time score holds
(14% per season with resort factors, 19% without, for the 2026 fit). Don't tune on a few weeks of
weather.

- Raw responses cache in `.cache/` (gitignored). Open-Meteo's free daily limit counts each
  location and each two weeks of data; the fetchers retry on 429 and network errors.
- Seasons with snowfall days under 70% of the resort's median are treated as incomplete reports
  and skipped (`reported.complete`).
- `hindcast.py`, `optimize.py`, `diagnose.py`, `fit.py`, `terrain.py`, `tune.py` belong to the first
  version (each provider's own `snowfall`, `gfs_seamless` / `gem_seamless`): they fitted the snow-
  ratio constants and explored terrain predictors. Keep them for that history; the shipped
  factors come from the scripts above.
- When you change `snow_ratio` or the phase rule in `powder/providers/open_meteo_common.py`,
  rerun the whole sequence above.

## Daily snow log

Season totals can't say how error grows with lead time, or whether the snow-ratio error that
depends on temperature shows up in resort reports too. The daily log records both sides going
forward; it reads the export and never changes the forecasts.

```bash
poetry run powder --export-json
poetry run python tools/calibrate/daily_log.py           # -> tools/calibrate/.cache/snow-log/<date>.jsonl
poetry run python tools/calibrate/daily_score.py         # scores whatever days that folder has

git fetch origin snow-log                                # the CI log
poetry run python tools/calibrate/daily_score.py --git origin/snow-log [--sources] [--align prev] [--min 2]
```

- `daily_log.py` writes one line per resort: every `daily_forecasts[]` day with its lead (days
  after the resort-local issue date), `avg_inches`, per-model `sources`, `snow_temp_f`,
  `freezing_level_ft` and the temperature range, the last 3 historical days, and, for the 46
  resorts in `reported.SLUGS`, the OnTheSnow `skireport` (24/48/72 h new snow, report date and
  post time, mid depth, open flag, the last 8 daily reports). The page is a Next.js app; the
  numbers come from its embedded data (centimetres, converted to inches). About 1 request a
  second; robots.txt allows everything (checked on each run). The forecasts are written even if
  the scrape fails. A day's file is not overwritten without `--force`.
- CI: the 17:30 UTC run of `.github/workflows/pages.yml` (or a manual run with `snow_log`
  ticked) hands the deployed `forecasts.json` to the `snow-log` job, which commits
  `log/<date>.jsonl` to the `snow-log` branch (created on first run). The job runs after the
  deploy and is `continue-on-error`.
- `daily_score.py` compares the report dated D (the 24 h to that morning) with 0.75 x forecast(D-1)
  + 0.25 x forecast(D), both from the log made N days before D, for N = 1, 2, 3, 5, 7. It prints
  median |error|, median and mean bias (forecast - reported) and the forecast/reported ratio by
  lead, then by storm temperature: the snowfall-weighted `snow_temp_f` of the same days from the
  latest log (cold < 18 F, mid 18-27 F, warm > 27 F). Only events where either side reaches 1"
  count. `--backfill` adds days no run caught on the day, from later reports' `recent` lists.
- Off season, a page keeps its last report (`report_date` months back); those never match a
  forecast, so they drop out on their own.

## Prototype model and what the archives really hold (2026-11, research only)

```bash
poetry run python tools/calibrate/raw.py fetch     # raw precipitation / temperature / humidity per underlying model (~40 min)
poetry run python tools/calibrate/raw.py cells     # each model's grid-cell centre and terrain height per resort
poetry run python tools/calibrate/raw.py hrrr      # HRRR as forecast a day ahead (previous-runs archive), US resorts
poetry run python tools/calibrate/snotel.py        # SNOTEL daily snow water / depth / gauge (NCEI GHCN-Daily)
poetry run python tools/calibrate/model2.py        # ladder of model variants vs resort reports, leave-one-resort-out
poetry run python tools/calibrate/model2.py --snotel   # precipitation step and snow ratio vs SNOTEL
```

Findings (46 resorts, 2022-26; `.cache/model2_out.txt` after a run):

- **The app's providers are several models.** `gfs_seamless` is HRRR 3 km for hours 0-46 and GFS
  global after; `gem_seamless` is HRDPS (Canada, 46 h) / GEM regional (to ~82 h) and then GEM
  global. Each has its own grid cell, terrain height and bias, so each needs its own factor.
- **The historical-forecast archive is not what HRRR forecasts.** It stitches HRRR's first
  forecast hours, before precipitation spins up: 1.4-4x less than the same model forecasts a day
  ahead (Palisades 1.4x, Alta 2.2x, Vail 2.5x, Big Sky 4.2x, Dec-Mar 2025-26). The shipped
  `Open-Meteo` factors for US / Canadian regions (x1.3-3.7) are that deficit, and the live
  forecast then applies them to real HRRR / GFS values: its GFS column runs ~2.4x ECMWF in the US.
  GFS global, ECMWF and GEM archives are within ~15% of their own 1-3 day forecasts. Calibrate
  HRRR on `raw.py hrrr`, never on the archive.
- **Where resorts measure** (`report_sites.json`): one sheltered plot, usually mid-to-upper
  mountain (median 0.63 of the vertical, range 0.33-0.84); no standard, and OnTheSnow carries only
  that number. Reports test the model at the plot, not at base / summit separately.
- **Physics refinements do not move the match to resort reports**: wet-bulb snow fraction, the
  plot's elevation, a terrain-height gradient per model cell and a PRISM 800 m climatological
  ratio all leave leave-one-resort-out error at ~20%. Against SNOTEL the height gradient is real
  (+30-50% precipitation per km of unresolved terrain) and ECMWF places precipitation best (10%
  miss on an unseen station; GFS 17%, GEM 24-29%), but resort-to-resort differences in reports are
  mostly reporting practice.
- **What does move it**: the right factor per underlying model (GFS + ECMWF + GEM global with their
  own region factors: 16% per resort with no history, vs +23% bias with today's factors) and the
  per-resort factor (10% per season).

### Over-fitting, altitude and interpolation checks

```bash
poetry run python tools/calibrate/model2.py --checks      # out-of-time split, shrinkage, altitude sweep
poetry run python tools/calibrate/neighbours.py fetch     # 3x3 grid cells round every point (daily precipitation)
poetry run python tools/calibrate/neighbours.py score     # cell choices vs SNOTEL and resort reports
```

- **Out of time** (fit on 2022-24, score 2024-26): region factors 19% per season, with the resort
  factor 15%. Leave-one-season-out (10-12%) flatters it: it borrows later seasons. A resort's
  factor from one pair of seasons correlates 0.66 with the other pair, so about half of it is
  noise; shrinking it by n / (n + 1) costs nothing and is safer for resorts with 1-2 seasons.
- **Altitude**: base is clearly worse (22% per season), 0.5-0.75 of the vertical is flat
  (16-17%), summit 19%. Known plot elevations do no better than mid-mountain: by mid-mountain
  84-99% of winter precipitation is already snow, and the API does not change the precipitation
  amount with height.
- **Interpolation** (four cells round each point, Nov-Apr 2023-25, `.cache/neighbours_out.txt`):
  against SNOTEL, averaging cells helps the coarse GEM global a lot (unseen-station miss 29% for
  the matched cell, 15% for the mean of four) and GFS a little (17% to 15% bilinear), while ECMWF's
  elevation-matched cell is already best (10%). In the three-model blend, GEM's four-cell mean
  takes the SNOTEL miss from 14% to 10%. Against resort reports nothing beats the matched cell
  (16% per resort with no history; other choices 16-22%), because reports differ by measuring
  practice more than by where precipitation falls.
- **ENSO** (`enso.py`; 2023-24 strong El Nino, other seasons La Nina): with factors fitted on the
  other seasons, the El Nino winter was the best predicted (8% median per season, 85% within 20%;
  La Nina seasons 10-19%), and resort factors moved less in it (typical 8%) than in the La Nina
  seasons (10-18%). Whole regions do swing +/-20% in some seasons (CA, UT, MT +20-28% in
  2024-25), unrelated to ENSO phase. Biggest El Nino mover: Whistler (x0.62 -> x1.11), a warm,
  maritime, low-elevation plot. Caveat: one El Nino, and few resorts where El Nino matters most
  (Southern California, the Southwest, the Pacific Northwest).

### Ground truth: the method against NWS cooperative observers (`coop.py`)

```bash
poetry run python tools/calibrate/coop.py select && poetry run python tools/calibrate/coop.py obs
poetry run python tools/calibrate/coop.py model && poetry run python tools/calibrate/coop.py score
poetry run python tools/calibrate/coop.py compare
```

74-77 mountain COOP stations in 11 western states (once-daily cleared board, melted water), 2022-26:

- Same method, same correction ladder as resorts (blend of GFS, ECMWF, GEM global): no history
  23% per station / 26% per season; with state factors 22% / 25%; with the station's own factor
  18-19% per season. Resorts do better at every step (16-20% no history, 10-15% with their own
  factor), so resort reports are not the hard target: COOP sites sit in valleys and rain-shadows
  the 9-25 km models can't see (below 2,000 m ECMWF overpredicts snowfall x1.6, spread 0.47 log).
- Station factors are as persistent as resort factors (r = 0.73 between 2022-24 and 2024-26) and
  larger (spread 0.36 log vs 0.22): a steady local bias against coarse models is a property of any
  site, not a resort fudge.
- The snow ratio is unbiased on average (COOP 11.2:1 on snow days, app 11.8:1; 12.4 vs 11.4 on
  days with 3 in or more) but weak day to day (r = 0.34). Precipitation explains about a third of
  the station-to-station snowfall miss; 3-day storm totals correlate r = 0.58.
- Resorts report 1.4-2.4x what the COOP observer at their base measures, season after season
  (Brighton 1.7-2.4x at the same elevation; Winter Park 1.4-1.8x; Breckenridge 1.5-2.1x; Big Bear
  4-5x against the town). ECMWF needs x0.70 to match COOP but ~x1.0 to match resorts.

### Do site factors hold when the temperature changes? (`temp_regime.py`, `slope_sweep.py`)

Run from the repo root after `coop.py model`. COOP snowy days split by the model's storm
temperature (cold < -8 C, mid -8..-3 C, warm > -3 C):

- With today's snow ratio the model's bias depends on storm temperature: obs/model snowfall
  x0.41-0.53 in cold storms, x0.81-1.03 in warm ones, while precipitation is much flatter (ECMWF
  water x0.58 cold, x0.72 warm). A site factor fitted on all days misses by 30-61% in cold spells,
  18-27% in warm ones and 10-14% in between; cold-storm and warm-storm factors correlate only
  r = 0.09-0.36. A season total mixes temperatures much the same way every year, so season-level
  factors look stable while a two-week cold or warm spell can be well off.
- Flattening the cold slope of the ratio (`slope_sweep.py`) makes the COOP bias flat across
  temperatures (x0.84 in every band at cold slope 0, warm slope 1, rate exponent -0.15) but costs
  resorts 2-4 points (16% -> 18-20% per season with no history, 10% -> 11-12% with their own factor).
  COOP's once-daily boards let fluffy cold snow settle before it is read; resorts' fresher readings
  favour the steeper Kuchera slope. Which is right for resort-style reporting needs daily resort
  reports to settle.
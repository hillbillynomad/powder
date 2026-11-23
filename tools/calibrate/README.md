# Snowfall calibration

Hindcasts the app's snowfall method on archived model runs and fits the shared snow ratio and
per-provider regional bias factors against resort-reported season totals.

```bash
poetry run python tools/calibrate/reported.py                          # OnTheSnow season totals -> reported_seasons.json
poetry run python tools/calibrate/hindcast.py fetch 0.5                # GFS (best_match) + ECMWF hourly, 2022-10..2026-05 (~20 min)
poetry run python tools/calibrate/hindcast.py fetch 0.5 --models=gem_seamless
poetry run python tools/calibrate/hindcast.py score 0.5 --models=ecmwf_ifs,gem_seamless   # raw comparison
poetry run python tools/calibrate/optimize.py --form=kuchera ecmwf_ifs # fit snow-ratio constants
poetry run python tools/calibrate/factors.py --ratio=0.84,0.92,-0.31 [--write]   # LOO score, write powder/data/snow_calibration.json
poetry run python tools/calibrate/anchor.py fetch && poetry run python tools/calibrate/anchor.py write   # other regions: tie GFS/GEM to ECMWF
poetry run python tools/calibrate/resort_factors.py [--write]          # per-resort factors, leave-one-season-out score
poetry run python tools/calibrate/verify.py                            # app code + shipped table vs reports
poetry run python tools/calibrate/check_export.py 2026-11-16 5         # sanity-check forecasts.json after an export
```

- Raw responses cache in `.cache/` (gitignored). The full fetch is heavy for Open-Meteo's free
  limits: it retries on 429 and network errors, but expect to wait.
- `fraction` is where between base (0) and summit (1) the forecast is made; the app uses 0.5.
- Seasons with snowfall days under 70% of the resort's median are treated as incomplete reports
  and skipped (`reported.complete`).
- `diagnose.py`, `fit.py` and `terrain.py` were exploration: implied ratios per resort,
  season-level regressions, and DEM relief (from the Terrarium tiles) as a predictor (it didn't help).
- When you change `snow_ratio` constants in `powder/providers/open_meteo_common.py`, refit the
  factors with the same constants and rerun `verify.py`.

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

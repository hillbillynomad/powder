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

// Powder snow helpers: model agreement, snow-quality labels and fresh snow for flyovers.
// Pure functions only (unit-tested against this file); app.js does the DOM work.

(function () {
    const MODEL_NAMES = {
        'Open-Meteo': 'GFS', ECMWF: 'ECMWF', NWS: 'NWS', ICON: 'ICON', JMA: 'JMA', BOM: 'BOM',
    };
    const LAPSE_F_PER_FT = 6.5 * 1.8 / 3280.84; // 6.5 °C per km, in °F per foot

    // ---- Model agreement ------------------------------------------------------------

    // How far apart the models are for one day (or one total): agree / mixed / split
    function modelSpread(sources) {
        const values = Object.values(sources || {}).filter(v => typeof v === 'number' && isFinite(v));
        if (values.length < 2) return null;
        const lo = Math.min(...values);
        const hi = Math.max(...values);
        const gap = hi - lo;
        let level = 'mixed';
        if (hi < 1 || gap <= Math.max(1, 0.35 * hi)) level = 'agree';
        else if (gap >= 4 && hi >= 2.5 * Math.max(lo, 0.5)) level = 'split';
        return { lo, hi, n: values.length, level };
    }

    // Agreement over the next `days` forecast days that have two or more models (the first
    // "forecast" day can be a past day with only GFS): how many days agree, and the range of
    // per-model totals, counting only models that cover every one of those days
    function agreementSummary(dailyForecasts, days = 7) {
        const window = [...(dailyForecasts || [])]
            .filter(d => Object.keys(d.sources || {}).length >= 2)
            .sort((a, b) => a.date.localeCompare(b.date))
            .slice(0, days);
        let agreeDays = 0;
        let totalDays = 0;
        for (const day of window) {
            const spread = modelSpread(day.sources);
            if (!spread) continue;
            totalDays++;
            if (spread.level === 'agree') agreeDays++;
        }
        const names = new Set();
        window.forEach(d => Object.keys(d.sources || {}).forEach(n => names.add(n)));
        const totals = {};
        for (const name of names) {
            if (window.every(d => d.sources && typeof d.sources[name] === 'number')) {
                totals[name] = window.reduce((sum, d) => sum + d.sources[name], 0);
            }
        }
        const total = modelSpread(totals);
        return {
            days: window.length,
            agreeDays,
            totalDays,
            totalLo: total ? total.lo : null,
            totalHi: total ? total.hi : null,
            level: total ? total.level : null,
        };
    }

    // "GFS 18″ · ECMWF 4″"
    function modelTooltip(sources) {
        return Object.entries(sources || {})
            .map(([name, v]) => `${MODEL_NAMES[name] || name} ${v}″`)
            .join(' · ');
    }

    const AGREEMENT_TEXT = {
        agree: 'Models agree',
        mixed: 'Models differ a little',
        split: 'Models disagree',
    };

    // ---- Snow quality ---------------------------------------------------------------

    const QUALITY = {
        champagne: { label: 'Champagne powder', short: 'Champagne', icon: '❄',
            hint: 'Very cold, light and dry snow (about 15°F or colder on the mountain)' },
        powder: { label: 'Powder', short: 'Powder', icon: '❄',
            hint: 'Soft, cold snow (about 15 to 27°F on the mountain)' },
        heavy: { label: 'Heavy snow', short: 'Heavy', icon: '💧',
            hint: 'Wet, dense snow that falls near freezing' },
        mixed: { label: 'Snow up top, rain at base', short: 'Mixed', icon: '🌨',
            hint: 'Freezing level is partway up the mountain: snow above it, rain below' },
        rain: { label: 'Rain', short: 'Rain', icon: '🌧',
            hint: 'Freezing level is above the summit' },
    };

    function qualityLabel(quality) {
        return QUALITY[quality] || null;
    }

    // Biggest upcoming day that has a quality rating
    function bestDay(dailyForecasts) {
        let best = null;
        for (const day of dailyForecasts || []) {
            const q = day.conditions && day.conditions.quality;
            if (!q || q === 'rain') continue;
            if (!best || day.avg_inches > best.avg_inches) best = day;
        }
        return best;
    }

    // ---- Fresh snow on the flyover --------------------------------------------------

    function addDays(iso, n) {
        const d = new Date(`${iso}T00:00:00Z`);
        d.setUTCDate(d.getUTCDate() + n);
        return d.toISOString().slice(0, 10);
    }

    // New snow over the last 72 h (two past days + today) and the lowest elevation it reached.
    // Returns null when there is too little to show.
    function freshSnowCover(resort, todayIso) {
        if (!resort) return null;
        const from = addDays(todayIso, -2);
        // The export splits past / forecast by its own clock, not the resort's, so take any
        // day in the window from either list (once per date)
        const byDate = new Map();
        for (const d of resort.historical_snowfall || []) {
            byDate.set(d.date, { inches: d.snowfall_inches || 0, cond: d.conditions });
        }
        for (const d of resort.daily_forecasts || []) {
            if (!byDate.has(d.date)) byDate.set(d.date, { inches: d.avg_inches || 0, cond: d.conditions });
        }
        const days = [...byDate].filter(([date]) => date >= from && date <= todayIso).map(([, v]) => v);
        const inches72 = days.reduce((sum, d) => sum + d.inches, 0);
        const lines = days
            .map(d => d.cond && d.cond.snow_line_ft)
            .filter(v => typeof v === 'number');
        if (inches72 < 1 || lines.length === 0) return null;
        const opacity = Math.min(0.7, Math.max(0.3, 0.35 + (inches72 - 2) * 0.035));
        return { inches72: Math.round(inches72 * 10) / 10, snowLineFt: Math.min(...lines), opacity };
    }

    // Temperature moved from one elevation to another (standard lapse rate)
    function lapseTempF(tempF, fromFt, toFt) {
        return tempF - (toFt - fromFt) * LAPSE_F_PER_FT;
    }

    function todayIsoIn(timeZone, nowMs = Date.now()) {
        try {
            return new Date(nowMs).toLocaleDateString('en-CA', { timeZone }); // YYYY-MM-DD
        } catch (e) {
            return new Date(nowMs).toISOString().slice(0, 10);
        }
    }

    // MapLibre color-relief ramp (real metres): clear below the snow line, then whiter with
    // height, as cover deepens up the mountain; a flat white reads as haze on the valleys
    function freshSnowColor(snowLineFt, opacity) {
        const lineM = snowLineFt / 3.28084;
        const white = (a) => `rgba(255, 255, 255, ${+(a * opacity).toFixed(3)})`;
        return ['interpolate', ['linear'], ['elevation'],
            lineM - 100, white(0),
            lineM + 100, white(0.3),
            lineM + 500, white(0.7),
            lineM + 1000, white(1)];
    }

    const api = {
        MODEL_NAMES, AGREEMENT_TEXT, QUALITY,
        modelSpread, agreementSummary, modelTooltip, qualityLabel, bestDay,
        freshSnowCover, lapseTempF, todayIsoIn, freshSnowColor, addDays,
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else window.PowderSnow = api;
})();

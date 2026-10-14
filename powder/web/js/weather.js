// Powder weather overlays: hourly NOAA GFS temperature / snow depth / new snow frames.
//
// `powder --export-overlays` writes data/overlays/manifest.json plus one grayscale PNG per
// field per hour on a 0.5 degree lat/lon grid, where each pixel is an 8-bit code for the
// physical value (encodings are in the manifest). Here we decode those, colour them through
// a ramp, reproject to Web Mercator and drape the result over the globe as a MapLibre image
// source. Colouring + PNG encoding run in weather-worker.js so dragging the time slider never
// blocks the page. (MapLibre's canvas source would skip the encode, but it renders black on
// the globe.) The same decoded grids answer click-to-inspect.

(function () {
    const OVERLAY_DIR = 'data/overlays/';
    const WORKER_URL = 'js/weather-worker.js';
    const SOURCE_ID = 'wx-overlay';
    const LAYER_ID = 'wx-overlay'; // wx-* layers are managed here, not by the layer menu
    const MAX_LAT = 85.05112878; // Web Mercator limit
    const MERC_SIZE = 768; // output image side, px: ~1 px per 0.5 degree grid column
    const PLAY_STEP_MS = 600;
    const FOLLOW_NOW_CHECK_MS = 60 * 1000;
    const GRID_CACHE_LIMIT = 64;
    const HOUR_MS = 3600 * 1000;
    const MIN_SNOW_IN = 0.1; // below this a cell counts as bare ground

    // Colour stops are [value, [r, g, b, alpha 0-255]] in the field's units
    const OVERLAYS = {
        temp: {
            field: 'temp_f', label: 'Temperature', units: '°F', opacity: 0.6,
            stops: [
                [-40, [230, 230, 230, 255]], [-20, [200, 80, 200, 255]], [0, [120, 40, 160, 255]],
                [15, [60, 60, 170, 255]], [32, [70, 130, 220, 255]], [40, [60, 170, 160, 255]],
                [50, [90, 180, 80, 255]], [60, [190, 200, 60, 255]], [70, [230, 180, 60, 255]],
                [80, [220, 110, 60, 255]], [95, [180, 50, 80, 255]], [110, [110, 20, 50, 255]],
            ],
            ticks: [-20, 0, 32, 50, 70, 90, 110],
        },
        depth: {
            field: 'depth_in', label: 'Snow depth', units: 'in', opacity: 0.85,
            stops: [
                [0, [0, 0, 0, 0]], [0.4, [180, 220, 255, 0]], [1, [160, 210, 255, 170]],
                [6, [90, 150, 255, 210]], [24, [130, 90, 230, 230]], [60, [220, 120, 230, 240]],
                [120, [255, 255, 255, 250]],
            ],
            ticks: [1, 6, 24, 60, 120],
        },
        fresh: {
            field: 'new_in', label: 'New snow (24h)', units: 'in', opacity: 0.9,
            stops: [
                [0, [0, 0, 0, 0]], [0.3, [120, 220, 255, 0]], [1, [120, 220, 255, 190]],
                [4, [60, 140, 255, 220]], [8, [150, 80, 240, 235]], [16, [240, 70, 200, 245]],
                [30, [255, 255, 255, 250]],
            ],
            ticks: [1, 4, 8, 16, 30],
        },
    };

    // ---- Pure helpers (unit-tested) -------------------------------------------------

    // 8-bit code -> physical value, per the manifest's field encoding
    function decodeCode(enc, code) {
        if (enc.kind === 'linear') return enc.offset + code * enc.scale;
        return enc.max * Math.pow(code / 255, 2);
    }

    function interpolateStops(stops, value) {
        if (value <= stops[0][0]) return stops[0][1];
        for (let i = 1; i < stops.length; i++) {
            const [v1, c1] = stops[i];
            if (value <= v1) {
                const [v0, c0] = stops[i - 1];
                const t = (value - v0) / (v1 - v0);
                return c0.map((c, k) => c + (c1[k] - c) * t);
            }
        }
        return stops[stops.length - 1][1];
    }

    // Code -> RGBA lookup table (256 entries), so rendering never decodes per pixel
    function buildLut(enc, stops) {
        const lut = new Uint8ClampedArray(256 * 4);
        for (let code = 0; code < 256; code++) {
            const rgba = interpolateStops(stops, decodeCode(enc, code));
            for (let k = 0; k < 4; k++) lut[code * 4 + k] = Math.round(rgba[k]);
        }
        return lut;
    }

    // Index of the frame nearest to now (frames are hourly, ascending)
    function nearestFrameIndex(frames, nowMs) {
        let best = 0;
        let bestDiff = Infinity;
        frames.forEach((f, i) => {
            const diff = Math.abs(Date.parse(f.time) - nowMs);
            if (diff < bestDiff) { best = i; bestDiff = diff; }
        });
        return best;
    }

    // "Wed Oct 15, 2 PM" in the viewer's time zone, plus how far from now ("now", "+5h", "-1d 3h")
    function frameLabel(timeMs, nowMs, timeZone) {
        // Each part formatted separately: engines disagree on the punctuation between them
        const zone = timeZone ? { timeZone } : {};
        const date = new Date(timeMs);
        const part = (opts) => date.toLocaleString('en-US', { ...opts, ...zone });
        const when = `${part({ weekday: 'short' })} ${part({ month: 'short' })} ${part({ day: 'numeric' })}, ` +
            part({ hour: 'numeric' });
        const hours = Math.round((timeMs - nowMs) / HOUR_MS);
        if (hours === 0) return { when, rel: 'now' };
        const sign = hours > 0 ? '+' : '-';
        const abs = Math.abs(hours);
        const rel = abs < 24 ? `${sign}${abs}h` : `${sign}${Math.floor(abs / 24)}d${abs % 24 ? ` ${abs % 24}h` : ''}`;
        return { when, rel };
    }

    // Fractional source row/column for every output pixel row/column of a square
    // Web Mercator image covering lng -180..180, lat +-MAX_LAT
    function mercatorLookup(grid, size) {
        const rows = new Float32Array(size);
        const cols = new Float32Array(size);
        for (let y = 0; y < size; y++) {
            const merc = Math.PI * (1 - (2 * (y + 0.5)) / size);
            const lat = (Math.atan(Math.sinh(merc)) * 180) / Math.PI;
            rows[y] = Math.min(Math.max((grid.lat0 - lat) / grid.step, 0), grid.nj - 1);
        }
        for (let x = 0; x < size; x++) {
            const lng = -180 + ((x + 0.5) / size) * 360;
            cols[x] = (((lng - grid.lon0) / grid.step) % grid.ni + grid.ni) % grid.ni;
        }
        return { rows, cols };
    }

    // Bilinear-sample codes onto the Mercator canvas, colouring through the LUT
    function renderCodes(codes, grid, lut, lookup, out) {
        const { ni, nj } = grid;
        const { rows, cols } = lookup;
        const size = rows.length;
        let p = 0;
        for (let y = 0; y < size; y++) {
            const fy = rows[y];
            const y0 = Math.min(Math.floor(fy), nj - 2);
            const wy = fy - y0;
            const r0 = y0 * ni;
            const r1 = r0 + ni;
            for (let x = 0; x < size; x++) {
                const fx = cols[x];
                const x0 = Math.floor(fx);
                const x1 = x0 + 1 === ni ? 0 : x0 + 1; // wrap across the antimeridian
                const wx = fx - x0;
                const top = codes[r0 + x0] + (codes[r0 + x1] - codes[r0 + x0]) * wx;
                const bot = codes[r1 + x0] + (codes[r1 + x1] - codes[r1 + x0]) * wx;
                const c = ((top + (bot - top) * wy) + 0.5) | 0;
                const l = c * 4;
                out[p++] = lut[l];
                out[p++] = lut[l + 1];
                out[p++] = lut[l + 2];
                out[p++] = lut[l + 3];
            }
        }
    }

    // Physical value at a point: bilinear, or nearest cell when blending makes no sense
    function sampleGrid(codes, grid, enc, lat, lng, nearest) {
        const { ni, nj, lat0, lon0, step } = grid;
        const fy = Math.min(Math.max((lat0 - lat) / step, 0), nj - 1);
        const fx = (((lng - lon0) / step) % ni + ni) % ni;
        if (nearest) {
            const y = Math.round(fy);
            const x = Math.round(fx) % ni;
            return decodeCode(enc, codes[y * ni + x]);
        }
        const y0 = Math.min(Math.floor(fy), nj - 2);
        const x0 = Math.floor(fx);
        const x1 = (x0 + 1) % ni;
        const wy = fy - y0;
        const wx = fx - x0;
        const v = (y, x) => decodeCode(enc, codes[y * ni + x]);
        const top = v(y0, x0) * (1 - wx) + v(y0, x1) * wx;
        const bot = v(y0 + 1, x0) * (1 - wx) + v(y0 + 1, x1) * wx;
        return top * (1 - wy) + bot * wy;
    }

    function formatInches(value) {
        return value < MIN_SNOW_IN ? '0 in' : `${value < 10 ? value.toFixed(1) : Math.round(value)} in`;
    }

    // Popup body for a click: the active overlay's value large, the rest as rows
    function readoutHtml(active, values, label) {
        const rows = {
            temp: ['Temperature', `${Math.round(values.temp_f)}°F`],
            depth: ['Snow depth', formatInches(values.depth_in)],
            fresh: ['New snow (24h)', formatInches(values.new_in)],
        };
        const [title, big] = rows[active];
        const extra = Object.keys(rows).filter(k => k !== active).map(k => rows[k]);
        if (values.depth_in >= MIN_SNOW_IN && values.density > 0) {
            extra.splice(active === 'depth' ? 0 : 1, 0, ['Snow density', `${Math.round(values.density)} kg/m³`]);
        }
        return `<div class="wx-readout">
            <div class="wx-readout-title">${title}</div>
            <div class="wx-readout-value">${big}</div>
            ${extra.map(([k, v]) => `<div class="wx-readout-row"><span>${k}</span><b>${v}</b></div>`).join('')}
            <div class="wx-readout-meta">${label}</div>
        </div>`;
    }

    function legendGradient(stops) {
        const n = stops.length - 1;
        return `linear-gradient(90deg, ${stops.map(([, c], i) =>
            `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${Math.max(c[3], 60) / 255}) ${((i / n) * 100).toFixed(1)}%`).join(', ')})`;
    }

    // Tick position (0-100%) on the legend, matching the evenly spaced stops
    function legendTickPosition(stops, value) {
        for (let i = 1; i < stops.length; i++) {
            if (value <= stops[i][0]) {
                const t = (value - stops[i - 1][0]) / (stops[i][0] - stops[i - 1][0]);
                return ((i - 1 + t) / (stops.length - 1)) * 100;
            }
        }
        return 100;
    }

    // ---- Frame encoding -------------------------------------------------------------

    // codes + LUT -> coloured Web Mercator PNG blob. Runs in a worker where the browser has
    // OffscreenCanvas; otherwise on the main thread.
    function createFrameEncoder(grid, size) {
        if (typeof Worker !== 'undefined' && typeof OffscreenCanvas !== 'undefined') {
            try {
                return createWorkerEncoder(grid, size);
            } catch (e) {
                console.debug('Weather worker unavailable; rendering on the main thread', e);
            }
        }
        const lookup = mercatorLookup(grid, size);
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = size;
        const ctx = canvas.getContext('2d');
        return (codes, lut) => {
            const image = ctx.createImageData(size, size);
            renderCodes(codes, grid, lut, lookup, image.data);
            ctx.putImageData(image, 0, 0);
            return new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
        };
    }

    function createWorkerEncoder(grid, size) {
        const worker = new Worker(WORKER_URL);
        const pending = new Map();
        let nextId = 0;
        worker.onmessage = (e) => {
            const { id, blob, error } = e.data;
            const job = pending.get(id);
            pending.delete(id);
            if (job) (error ? job.reject(new Error(error)) : job.resolve(blob));
        };
        worker.onerror = (e) => {
            pending.forEach(job => job.reject(new Error(e.message || 'weather worker failed')));
            pending.clear();
        };
        return (codes, lut) => new Promise((resolve, reject) => {
            const id = nextId++;
            pending.set(id, { resolve, reject });
            // Copy: the cached codes stay usable on this side for click readouts
            worker.postMessage({ id, codes: codes.slice(), grid, lut, size });
        });
    }

    // ---- Controller -----------------------------------------------------------------

    function createController(map, maplibre) {
        const ui = {
            radios: [...document.querySelectorAll('input[name="wx-overlay"]')],
            status: document.getElementById('wx-status'),
            bar: document.getElementById('wx-timebar'),
            play: document.getElementById('wx-play'),
            slider: document.getElementById('wx-slider'),
            when: document.getElementById('wx-time-when'),
            rel: document.getElementById('wx-time-rel'),
            now: document.getElementById('wx-now'),
            legend: document.getElementById('wx-legend'),
        };
        const state = {
            manifest: null, active: 'none', frame: 0, followNow: true,
            playTimer: null, renderToken: 0, popup: null, objectUrl: null,
        };
        const grids = new Map(); // url -> Promise<Uint8Array>
        let encodeFrame = null;
        let luts = {};

        function setAvailable(ok, message) {
            ui.radios.forEach(r => { r.disabled = !ok && r.value !== 'none'; });
            if (ui.status) ui.status.textContent = message;
        }

        async function loadManifest() {
            try {
                const response = await fetch(`${OVERLAY_DIR}manifest.json`, { cache: 'no-cache' });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                state.manifest = await response.json();
            } catch (e) {
                console.debug('Weather overlays unavailable', e);
                setAvailable(false, 'Weather overlays are unavailable right now.');
                return;
            }
            const { grid, fields, frames } = state.manifest;
            encodeFrame = createFrameEncoder(grid, MERC_SIZE);
            luts = Object.fromEntries(Object.entries(OVERLAYS).map(([k, o]) => [k, buildLut(fields[o.field], o.stops)]));
            ui.slider.max = String(frames.length - 1);
            state.frame = nearestFrameIndex(frames, Date.now());
            setAvailable(true, 'NOAA GFS model, hourly. Tap the map for values.');
        }

        function fileUrl(frameIndex, field) {
            const { dir, frames } = state.manifest;
            return `${OVERLAY_DIR}${dir}/${frames[frameIndex].files[field]}`;
        }

        // Decoded codes for one field/frame; cached, oldest evicted first
        function getCodes(frameIndex, field) {
            const url = fileUrl(frameIndex, field);
            if (!grids.has(url)) {
                if (grids.size >= GRID_CACHE_LIMIT) grids.delete(grids.keys().next().value);
                grids.set(url, loadCodes(url).catch((e) => { grids.delete(url); throw e; }));
            }
            return grids.get(url);
        }

        async function loadCodes(url) {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
            // No colour management: pixel values are data, not colours
            const bitmap = await createImageBitmap(await response.blob(),
                { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
            const { ni, nj } = state.manifest.grid;
            const scratch = document.createElement('canvas');
            scratch.width = ni;
            scratch.height = nj;
            const sctx = scratch.getContext('2d', { willReadFrequently: true });
            sctx.drawImage(bitmap, 0, 0);
            const rgba = sctx.getImageData(0, 0, ni, nj).data;
            const codes = new Uint8Array(ni * nj);
            for (let i = 0; i < codes.length; i++) codes[i] = rgba[i * 4];
            return codes;
        }

        function showImage(url) {
            const source = map.getSource(SOURCE_ID);
            if (source) {
                source.updateImage({ url });
                return;
            }
            map.addSource(SOURCE_ID, {
                type: 'image', url,
                coordinates: [[-180, MAX_LAT], [180, MAX_LAT], [180, -MAX_LAT], [-180, -MAX_LAT]],
            });
            // Under every label layer, over imagery and map fills
            const firstSymbol = map.getStyle().layers.find(l => l.type === 'symbol' && !l.id.startsWith('wx-'));
            map.addLayer({
                id: LAYER_ID, type: 'raster', source: SOURCE_ID,
                paint: { 'raster-opacity': 0, 'raster-fade-duration': 0, 'raster-resampling': 'linear' },
            }, firstSymbol ? firstSymbol.id : 'resorts');
        }

        // Draw the current overlay/frame; superseded renders are dropped
        async function render() {
            if (state.active === 'none' || !state.manifest) return;
            const token = ++state.renderToken;
            const overlay = OVERLAYS[state.active];
            let codes;
            try {
                codes = await getCodes(state.frame, overlay.field);
            } catch (e) {
                console.warn('Weather frame failed to load', e);
                return;
            }
            if (token !== state.renderToken) return;
            let blob;
            try {
                blob = await encodeFrame(codes, luts[state.active]);
            } catch (e) {
                console.warn('Weather frame failed to render', e);
                return;
            }
            if (token !== state.renderToken || state.active === 'none') return;
            const url = URL.createObjectURL(blob);
            showImage(url);
            map.setPaintProperty(LAYER_ID, 'raster-opacity', overlay.opacity);
            // MapLibre has already decoded the previous frame; release its blob
            if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
            state.objectUrl = url;
            prefetch(state.frame + 1, overlay.field);
        }

        function prefetch(frameIndex, field) {
            if (frameIndex < state.manifest.frames.length) getCodes(frameIndex, field).catch(() => {});
        }

        function syncTimeLabel() {
            const t = Date.parse(state.manifest.frames[state.frame].time);
            const { when, rel } = frameLabel(t, Date.now());
            ui.when.textContent = when;
            ui.rel.textContent = rel;
            ui.now.hidden = state.followNow;
        }

        function syncLegend() {
            const o = OVERLAYS[state.active];
            if (!o) return;
            ui.legend.innerHTML = `<div class="wx-legend-bar" style="background:${legendGradient(o.stops)}"></div>
                <div class="wx-legend-ticks">${o.ticks.map(v =>
                    `<span style="left:${legendTickPosition(o.stops, v).toFixed(1)}%">${v}</span>`).join('')}
                    <span class="wx-legend-units">${o.units}</span></div>`;
        }

        function setFrame(index, { follow = false } = {}) {
            const frames = state.manifest.frames;
            state.frame = Math.max(0, Math.min(frames.length - 1, index));
            state.followNow = follow || state.frame === nearestFrameIndex(frames, Date.now());
            ui.slider.value = String(state.frame);
            syncTimeLabel();
            if (state.popup) state.popup.remove();
            render();
        }

        function setOverlay(key) {
            state.active = OVERLAYS[key] ? key : 'none';
            ui.radios.forEach(r => { r.checked = r.value === state.active; });
            const on = state.active !== 'none' && !!state.manifest;
            ui.bar.hidden = !on;
            if (state.popup) state.popup.remove();
            if (!on) {
                stop();
                if (map.getLayer(LAYER_ID)) map.setPaintProperty(LAYER_ID, 'raster-opacity', 0);
                return;
            }
            syncLegend();
            setFrame(state.followNow ? nearestFrameIndex(state.manifest.frames, Date.now()) : state.frame);
        }

        function stop() {
            clearInterval(state.playTimer);
            state.playTimer = null;
            ui.play.textContent = '▶';
            ui.play.setAttribute('aria-label', 'Play');
        }

        function togglePlay() {
            if (state.playTimer) { stop(); return; }
            const last = state.manifest.frames.length - 1;
            if (state.frame >= last) setFrame(0);
            ui.play.textContent = '❚❚';
            ui.play.setAttribute('aria-label', 'Pause');
            state.playTimer = setInterval(() => {
                if (state.frame >= last) { stop(); return; }
                setFrame(state.frame + 1);
            }, PLAY_STEP_MS);
        }

        // Values at a clicked point for the frame on screen
        async function showReadout(lngLat) {
            if (state.active === 'none' || !state.manifest) return false;
            const { grid, fields, frames } = state.manifest;
            const frame = state.frame;
            const names = ['temp_f', 'depth_in', 'new_in', 'density'];
            let codes;
            try {
                codes = await Promise.all(names.map(n => getCodes(frame, n)));
            } catch (e) {
                return false;
            }
            const values = {};
            names.forEach((n, i) => {
                // Density only means something inside the snowpack: don't blend with bare ground
                values[n] = sampleGrid(codes[i], grid, fields[n], lngLat.lat, lngLat.lng, n === 'density');
            });
            const { when, rel } = frameLabel(Date.parse(frames[frame].time), Date.now());
            const label = `${lngLat.lat.toFixed(2)}, ${lngLat.lng.toFixed(2)} · ${when} (${rel})`;
            if (state.popup) state.popup.remove();
            state.popup = new maplibre.Popup({ className: 'wx-popup', maxWidth: '260px' })
                .setLngLat(lngLat).setHTML(readoutHtml(state.active, values, label)).addTo(map);
            return true;
        }

        ui.radios.forEach(r => r.addEventListener('change', () => { if (r.checked) setOverlay(r.value); }));
        // The readout belongs to the spot that was tapped: drop it once the map moves away
        map.on('movestart', () => { if (state.popup) state.popup.remove(); });
        ui.slider.addEventListener('input', () => { stop(); setFrame(Number(ui.slider.value)); });
        ui.play.addEventListener('click', togglePlay);
        ui.now.addEventListener('click', () => {
            stop();
            setFrame(nearestFrameIndex(state.manifest.frames, Date.now()), { follow: true });
        });
        // Keep "now" current while the page stays open: move to the new hour's frame
        setInterval(() => {
            if (!state.manifest || state.active === 'none') return;
            if (state.followNow && !state.playTimer) {
                const now = nearestFrameIndex(state.manifest.frames, Date.now());
                if (now !== state.frame) setFrame(now, { follow: true });
                else syncTimeLabel();
            } else {
                syncTimeLabel();
            }
        }, FOLLOW_NOW_CHECK_MS);

        const ready = loadManifest();
        return {
            ready,
            setOverlay,
            setFrame,
            showReadout,
            isActive: () => state.active !== 'none',
            getState: () => ({ active: state.active, frame: state.frame, followNow: state.followNow,
                frames: state.manifest ? state.manifest.frames.length : 0, playing: !!state.playTimer }),
        };
    }

    const api = {
        OVERLAYS, decodeCode, interpolateStops, buildLut, nearestFrameIndex, frameLabel,
        mercatorLookup, renderCodes, sampleGrid, readoutHtml, legendGradient, legendTickPosition,
        createController,
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else self.PowderWeather = api; // window on the page, the global scope in the worker
})();

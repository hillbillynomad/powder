// Resort flyover tours: a looping low-altitude flight over a resort's lifts and terrain.
//
// A tour (tours/<slug>.json, listed in tours/index.json) is a closed ring of waypoints, each
// a camera position and a look-at target in real metres above sea level, plus the seconds it
// takes to fly from that waypoint to the next. Positions are smoothed with a closed
// Catmull-Rom spline, so the camera glides and turns gently instead of stopping at each
// point; looking at an interpolated target (rather than interpolating angles) means headings
// never spin the long way round. Altitudes are scaled by the terrain exaggeration at runtime
// so the flight stays the same height above the rendered mountains.
(function () {
    const TOUR_DIR = 'tours/';
    const APPROACH_MS = 6000; // fly-in from wherever the map is to the tour's first pose
    const RESUME_MS = 2500;

    // "Val d'Isère" -> "val-d-isere"
    function slugify(name) {
        return String(name || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
            .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    }

    function catmullRom(p0, p1, p2, p3, t) {
        const t2 = t * t, t3 = t2 * t;
        return p1.map((_, i) => 0.5 * (2 * p1[i] + (-p0[i] + p2[i]) * t +
            (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t2 + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * t3));
    }

    function tourDuration(tour) {
        return tour.points.reduce((sum, p) => sum + p.seconds, 0);
    }

    // Camera + target at `seconds` into the loop (wraps)
    function poseAt(tour, seconds) {
        const pts = tour.points;
        const n = pts.length;
        let t = ((seconds % tourDuration(tour)) + tourDuration(tour)) % tourDuration(tour);
        let i = 0;
        while (t >= pts[i].seconds && i < n - 1) { t -= pts[i].seconds; i++; }
        const u = Math.min(1, t / pts[i].seconds);
        const at = (k) => pts[((i + k) % n + n) % n];
        return {
            camera: catmullRom(at(-1).camera, at(0).camera, at(1).camera, at(2).camera, u),
            target: catmullRom(at(-1).target, at(0).target, at(1).target, at(2).target, u),
        };
    }

    function createController(map, maplibre, { exaggeration = 1, onChange = () => {} } = {}) {
        let index = null; // Promise<Set<slug>>
        const tours = new Map(); // slug -> Promise<tour|null>
        const state = { tour: null, playing: false, clock: 0, startedAt: 0, frame: 0, flying: false };

        function loadIndex() {
            if (!index) {
                index = fetch(`${TOUR_DIR}index.json`)
                    .then(r => (r.ok ? r.json() : { tours: [] }))
                    .then(data => new Set(data.tours || []))
                    .catch(() => new Set());
            }
            return index;
        }

        async function getTour(resortName) {
            const slug = slugify(resortName);
            if (!(await loadIndex()).has(slug)) return null;
            if (!tours.has(slug)) {
                tours.set(slug, fetch(`${TOUR_DIR}${slug}.json`).then(r => (r.ok ? r.json() : null)).catch(() => null));
            }
            return tours.get(slug);
        }

        function cameraFor(pose) {
            const [cLng, cLat, cAlt] = pose.camera;
            const [tLng, tLat, tAlt] = pose.target;
            return map.calculateCameraOptionsFromTo(
                new maplibre.LngLat(cLng, cLat), cAlt * exaggeration,
                new maplibre.LngLat(tLng, tLat), tAlt * exaggeration);
        }

        function tick(now) {
            if (!state.playing) return;
            const seconds = state.clock + (now - state.startedAt) / 1000;
            map.jumpTo(cameraFor(poseAt(state.tour, seconds)));
            state.frame = requestAnimationFrame(tick);
        }

        function startLoop() {
            state.flying = false;
            state.startedAt = performance.now();
            state.frame = requestAnimationFrame(tick);
        }

        // Fly to where the loop is (its start, or where it was paused), then keep flying
        function play({ approachMs = RESUME_MS } = {}) {
            if (!state.tour || state.playing) return;
            state.playing = true;
            state.flying = true;
            onChange(getState());
            const pose = cameraFor(poseAt(state.tour, state.clock));
            map.once('moveend', () => { if (state.playing && state.flying) startLoop(); });
            map.flyTo({ ...pose, duration: approachMs, essential: true });
        }

        function pause() {
            if (!state.playing) return;
            if (!state.flying) state.clock += (performance.now() - state.startedAt) / 1000;
            state.playing = false;
            state.flying = false;
            cancelAnimationFrame(state.frame);
            if (map.isMoving()) map.stop();
            onChange(getState());
        }

        function start(tour, { autoplay = true } = {}) {
            stop();
            state.tour = tour;
            state.clock = 0;
            if (autoplay) play({ approachMs: APPROACH_MS });
            else onChange(getState());
        }

        function stop() {
            pause();
            state.tour = null;
            state.clock = 0;
            onChange(getState());
        }

        // Any hands-on map gesture takes the controls back
        const canvas = map.getCanvasContainer();
        for (const type of ['pointerdown', 'wheel', 'touchstart']) {
            canvas.addEventListener(type, () => pause(), { passive: true });
        }

        function getState() {
            return { hasTour: !!state.tour, playing: state.playing, resort: state.tour ? state.tour.resort : null };
        }

        return { getTour, start, stop, play, pause, getState };
    }

    const api = { slugify, poseAt, tourDuration, catmullRom, createController };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else window.PowderFlyby = api;
})();

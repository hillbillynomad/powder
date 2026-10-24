// Resort flyover tours: a looping low-altitude flight over a resort's lifts and terrain.
//
// A tour (tours/<slug>.json, listed in tours/index.json) is a closed ring of waypoints: a
// camera position in real metres above sea level and the seconds it takes to fly on to the
// next waypoint. Positions are smoothed with a closed Catmull-Rom spline so the camera glides
// instead of stopping at each point. Altitudes are scaled by the terrain exaggeration at
// runtime so the flight stays the same height above the rendered mountains.
//
// Two ways to aim the camera:
//  - "bird" (no targets): face the way you're flying, tilted down by each point's `pitch`, and
//    bank gently into turns. The heading looks a little ahead along the path, so turns start
//    smoothly before the corner, like a bird leaning into one.
//  - look-at: each point also has a `target` the camera keeps looking at (interpolated as a
//    position, so headings never spin the long way round).
//  - mixed: bird flight with some points flagged `orbit: 1` (every point then also carries a
//    `target`). The aim point blends from the bird's line of sight to the target as the camera
//    moves onto an orbit point, so a route can circle a spot before flying on.
(function () {
    const TOUR_DIR = 'tours/';
    const APPROACH_MS = 6000; // fly-in from wherever the map is to the tour's first pose
    const RESUME_MS = 2500;
    const DEFAULT_PITCH = 68; // degrees from straight down: ~22 degrees below the horizon
    const HEADING_LOOK = [2.5, 4.5]; // seconds behind / ahead whose chord sets the heading
    const MAX_ROLL = 10; // degrees of bank in the tightest turn
    const ROLL_PER_TURN = 0.5; // degrees of bank per degree/second of turning
    const LOOK_DISTANCE = 1500; // metres to the aim point when a tour has no ground heights
    const MIN_LOOK_DISTANCE = 300;

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

    // 83.4 -> "1:23"
    function formatClock(seconds) {
        const s = Math.max(0, Math.round(seconds));
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
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
        const pitch = (k) => [at(k).pitch ?? DEFAULT_PITCH];
        const pose = {
            camera: catmullRom(at(-1).camera, at(0).camera, at(1).camera, at(2).camera, u),
            pitch: catmullRom(pitch(-1), pitch(0), pitch(1), pitch(2), u)[0],
        };
        if (pts[0].ground !== undefined) {
            const ground = (k) => [at(k).ground];
            pose.ground = catmullRom(ground(-1), ground(0), ground(1), ground(2), u)[0];
        }
        if (pts[0].target) pose.target = catmullRom(at(-1).target, at(0).target, at(1).target, at(2).target, u);
        return pose;
    }

    // 0 (bird) .. 1 (look at the target): how far into a mixed tour's orbit the camera is
    function orbitWeight(tour, seconds) {
        const pts = tour.points;
        const n = pts.length;
        const total = tourDuration(tour);
        let t = ((seconds % total) + total) % total;
        let i = 0;
        while (t >= pts[i].seconds && i < n - 1) { t -= pts[i].seconds; i++; }
        const u = Math.min(1, t / pts[i].seconds);
        const w0 = pts[i].orbit ? 1 : 0, w1 = pts[(i + 1) % n].orbit ? 1 : 0;
        return w0 + (w1 - w0) * u * u * (3 - 2 * u);
    }

    // Compass bearing (degrees) from a to b, both [lng, lat, ...]
    function bearingBetween(a, b) {
        const dx = (b[0] - a[0]) * Math.cos((a[1] * Math.PI) / 180);
        const dy = b[1] - a[1];
        return ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360;
    }

    // Signed smallest difference b - a in degrees (-180, 180]
    function angleDiff(a, b) {
        const d = ((b - a) % 360 + 540) % 360 - 180;
        return d === -180 ? 180 : d;
    }

    function headingAt(tour, seconds) {
        return bearingBetween(poseAt(tour, seconds - HEADING_LOOK[0]).camera, poseAt(tour, seconds + HEADING_LOOK[1]).camera);
    }

    // The point `distance` metres along a camera's line of sight ([lng, lat, alt]). Aiming at a
    // fixed-distance point (rather than wherever the ray meets the terrain) keeps zoom constant
    // and the camera exactly where we put it, whatever terrain tiles have loaded.
    function lookPoint(camera, bearing, pitch, distance) {
        const b = (bearing * Math.PI) / 180, p = (pitch * Math.PI) / 180;
        const ahead = distance * Math.sin(p);
        return [
            camera[0] + (ahead * Math.sin(b)) / (111320 * Math.cos((camera[1] * Math.PI) / 180)),
            camera[1] + (ahead * Math.cos(b)) / 110540,
            camera[2] - distance * Math.cos(p),
        ];
    }

    // Bird mode: position, heading along the flight, pitch, and a bank into the turn
    function birdPose(tour, seconds) {
        const pose = poseAt(tour, seconds);
        const bearing = headingAt(tour, seconds);
        const turnRate = angleDiff(headingAt(tour, seconds - 0.25), headingAt(tour, seconds + 0.25)) / 0.5;
        const roll = Math.max(-MAX_ROLL, Math.min(MAX_ROLL, turnRate * ROLL_PER_TURN));
        return { camera: pose.camera, bearing, pitch: pose.pitch, roll, ground: pose.ground };
    }

    function createController(map, maplibre, { exaggeration = 1, onChange = () => {} } = {}) {
        let index = null; // Promise<{ slugs: Set<slug>, versions: {slug: hash} }>
        const tours = new Map(); // slug -> Promise<tour|null>
        const state = { tour: null, playing: false, clock: 0, startedAt: 0, frame: 0, glideFrame: 0, flying: false };

        function loadIndex() {
            if (!index) {
                // Revalidate the index so a re-exported tour (new content hash) is always seen
                index = fetch(`${TOUR_DIR}index.json`, { cache: 'no-cache' })
                    .then(r => (r.ok ? r.json() : { tours: [] }))
                    .then(data => ({ slugs: new Set(data.tours || []), versions: data.versions || {} }))
                    .catch(() => ({ slugs: new Set(), versions: {} }));
            }
            return index;
        }

        async function getTour(resortName) {
            const slug = slugify(resortName);
            const { slugs, versions } = await loadIndex();
            if (!slugs.has(slug)) return null;
            if (!tours.has(slug)) {
                // The content hash in the URL means an edited tour can never be served stale
                const v = versions[slug] ? `?v=${versions[slug]}` : '';
                tours.set(slug, fetch(`${TOUR_DIR}${slug}.json${v}`).then(r => (r.ok ? r.json() : null)).catch(() => null));
            }
            return tours.get(slug);
        }

        function cameraAt(seconds) {
            const tour = state.tour;
            const mixed = tour.points.some(p => p.orbit);
            if (!tour.points[0].target || mixed) {
                const b = birdPose(tour, seconds);
                const cam = [b.camera[0], b.camera[1], b.camera[2] * exaggeration];
                // Aim where the line of sight meets the tour's smoothed ground (authored from the
                // DEM), so the view centre sits on the surface without reading live terrain
                const drop = b.ground === undefined ? null : cam[2] - b.ground * exaggeration;
                const distance = drop === null ? LOOK_DISTANCE
                    : Math.max(MIN_LOOK_DISTANCE, drop / Math.cos((b.pitch * Math.PI) / 180));
                let aim = lookPoint(cam, b.bearing, b.pitch, distance);
                let roll = b.roll;
                if (mixed) {
                    const w = orbitWeight(tour, seconds);
                    const t = poseAt(tour, seconds).target;
                    aim = aim.map((v, k) => v + ((k === 2 ? t[2] * exaggeration : t[k]) - v) * w);
                    roll *= 1 - w;
                }
                const options = map.calculateCameraOptionsFromTo(
                    new maplibre.LngLat(cam[0], cam[1]), cam[2], new maplibre.LngLat(aim[0], aim[1]), aim[2]);
                return { ...options, roll };
            }
            const pose = poseAt(tour, seconds);
            const [cLng, cLat, cAlt] = pose.camera;
            const [tLng, tLat, tAlt] = pose.target;
            return map.calculateCameraOptionsFromTo(
                new maplibre.LngLat(cLng, cLat), cAlt * exaggeration,
                new maplibre.LngLat(tLng, tLat), tAlt * exaggeration);
        }

        function tick(now) {
            if (!state.playing) return;
            const seconds = state.clock + (now - state.startedAt) / 1000;
            map.jumpTo(cameraAt(seconds));
            state.frame = requestAnimationFrame(tick);
        }

        function startLoop() {
            state.flying = false;
            state.startedAt = performance.now();
            state.frame = requestAnimationFrame(tick);
        }

        // Fly to where the loop is (its start, or where it was paused), then keep flying
        // MapLibre normally re-glues the view centre to the terrain whenever a terrain tile
        // loads, which moves the camera between our frames: on a first pass, while tiles
        // stream in, that is a constant up-and-down shake. We place the camera ourselves.
        function holdCamera(hold) {
            if (map.setCenterClampedToGround) map.setCenterClampedToGround(!hold);
        }

        // The approach used to be one flyTo straight to the tour's first pose. flyTo ignores the
        // pose's `elevation` and ends with the view centre at sea level, so the camera arrived
        // ~2.8 km lower than the loop's first frame wants, and the first loop frame popped it
        // upward. Now flyTo only brings the camera to a point straight above the first pose
        // (sea level, pitch 0, where that is exact), and we glide from there to the pose
        // frame by frame, so the camera path is continuous into the loop.
        const EARTH_CIRCUMFERENCE = 40075016.686;

        function lowZoomForAltitude(lat, altitude) {
            // camera-to-centre distance (px) * metres per pixel at the zoom = altitude, pitch 0
            const ctc = map.transform.cameraToCenterDistance;
            return Math.log2((ctc * EARTH_CIRCUMFERENCE * Math.cos((lat * Math.PI) / 180)) / (512 * altitude));
        }

        // Glide between two sets of camera options (the same fields flyTo animates, plus the
        // elevation and roll it drops). Both ends are exact: `from` is where flyTo stops (sea
        // level, pitch 0) and `to` is the loop's first frame.
        function glide(from, to, ms, done) {
            const t0 = performance.now();
            const lerp = (a, b, u) => a + (b - a) * u;
            const ease = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
            const step = (now) => {
                if (!state.playing) return;
                const u = Math.min(1, (now - t0) / ms);
                const e = ease(u);
                map.jumpTo({
                    center: [lerp(from.center.lng, to.center.lng, e), lerp(from.center.lat, to.center.lat, e)],
                    zoom: lerp(from.zoom, to.zoom, e),
                    pitch: lerp(from.pitch, to.pitch, e),
                    bearing: from.bearing + angleDiff(from.bearing, to.bearing) * e,
                    elevation: lerp(from.elevation, to.elevation, e),
                    roll: lerp(from.roll, to.roll || 0, e),
                });
                if (u < 1) state.glideFrame = requestAnimationFrame(step);
                else {
                    map.jumpTo(to); // land exactly on the loop's first frame
                    done();
                }
            };
            state.glideFrame = requestAnimationFrame(step);
        }

        function play({ approachMs = RESUME_MS } = {}) {
            if (!state.tour || state.playing) return;
            state.playing = true;
            state.flying = true;
            holdCamera(true);
            onChange(getState());
            const pose = cameraAt(state.clock);
            // Resuming exactly where it paused: nothing to fly
            const c = map.getCenter();
            const metres = Math.hypot((c.lng - pose.center.lng) * 111320 * Math.cos((c.lat * Math.PI) / 180), (c.lat - pose.center.lat) * 110540);
            if (state.clock > 0 && metres < 30 && Math.abs(map.getZoom() - pose.zoom) < 0.05 && Math.abs(angleDiff(map.getBearing(), pose.bearing)) < 2) {
                startLoop();
                return;
            }
            const altW = map.getZoom() < 9 ? 40000 : 15000; // looking straight down at the start's view centre
            const wZoom = lowZoomForAltitude(pose.center.lat, altW);
            const above = { center: pose.center, zoom: wZoom, pitch: 0, bearing: pose.bearing, elevation: 0, roll: 0 };
            map.once('moveend', () => {
                if (!state.playing || !state.flying) return;
                glide(above, pose, approachMs * 0.45, () => { if (state.playing && state.flying) startLoop(); });
            });
            map.flyTo({ center: pose.center, zoom: wZoom, pitch: 0, bearing: pose.bearing, duration: approachMs * 0.55, essential: true });
        }

        function pause() {
            if (!state.playing) return;
            if (!state.flying) state.clock += (performance.now() - state.startedAt) / 1000;
            state.playing = false;
            state.flying = false;
            cancelAnimationFrame(state.frame);
            cancelAnimationFrame(state.glideFrame);
            if (map.isMoving()) map.stop();
            holdCamera(false);
            if (map.getRoll && map.getRoll()) map.easeTo({ roll: 0, duration: 600 }); // level the wings
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

        function getDuration() {
            return state.tour ? tourDuration(state.tour) : 0;
        }

        // Where the camera is in the loop, in seconds (0 .. duration)
        function getTime() {
            if (!state.tour) return 0;
            const total = tourDuration(state.tour);
            const t = state.playing && !state.flying ? state.clock + (performance.now() - state.startedAt) / 1000 : state.clock;
            return ((t % total) + total) % total;
        }

        // Jump to a point in the loop: straight there (no fly-in), then keep going if it was playing
        function seek(seconds) {
            if (!state.tour) return;
            const total = tourDuration(state.tour);
            state.clock = Math.max(0, Math.min(total - 0.05, seconds));
            const wasPlaying = state.playing;
            if (state.flying) { // still on the way in: drop the approach
                cancelAnimationFrame(state.glideFrame);
                if (map.isMoving()) map.stop();
                state.flying = false;
            }
            holdCamera(true);
            map.jumpTo(cameraAt(state.clock));
            if (wasPlaying) {
                cancelAnimationFrame(state.frame);
                startLoop();
            }
            onChange(getState());
        }

        return { getTour, start, stop, play, pause, getState, getTime, getDuration, seek };
    }

    const api = { slugify, formatClock, poseAt, birdPose, lookPoint, bearingBetween, angleDiff, tourDuration, orbitWeight, catmullRom, createController };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else window.PowderFlyby = api;
})();

// Powder Web UI - Interactive Snowfall Map

const BUBBLE_COLOR = '#3b82f6';
const BUBBLE_FILL_OPACITY = 0.75;
const MIN_RADIUS = 5;
const NO_SNOW_THRESHOLD = 1; // inches; below this a resort is drawn as a hollow ring
const MIN_ZOOM = 1; // MapLibre zoom (512px tiles); bubbles are base-sized here
const MAX_ZOOM = 18;
const ZOOM_SCALE_RATE = 0.1; // markers grow at 0.1x the map's zoom rate
const TILE_SIZE = 512;
const GLOBE_FILL = 0.9; // fraction of the smaller viewport side the whole globe may occupy
const FOCUS_ZOOM = 9;
const SEARCH_LIMIT = 50;
const TOP_LIMIT = 10;
const HORIZON_DEG = 88; // on the globe, resorts further than this from the centre are round the back
const TERRAIN_3D_MIN_ZOOM = 7; // 3D relief on a globe is only worth its cost once zoomed in
const TERRAIN_EXAGGERATION = 1.4;
const FEET_PER_METER = 3.28084;

// Side panel: 'collapsed' | 'peek' | 'full'. 'full' is kept only so previously saved
// state still loads; peek and full are both simply "open" in either layout.
const BOTTOM_PANEL_QUERY = '(max-width: 700px), (max-aspect-ratio: 1/1)'; // keep in sync with style.css
const PANEL_STATE_KEY = 'powder.panelState';
let panelState = 'peek';
let lastOpenPanelState = 'peek';

// Map layer preferences (persisted per browser)
const LAYER_PREFS_KEY = 'powder.layerPrefs';
const BASE_MODES = ['sat', 'map', 'topo'];
const DEFAULT_LAYER_PREFS = { mode: 'sat', labels: true, terrain: false, threeD: false, trails: true };
let layerPrefs = { ...DEFAULT_LAYER_PREFS };

// Free, key-less map sources. Everything swappable lives here.
const MAP_SOURCES = {
    satellite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    topo: 'https://tile.opentopomap.org/{z}/{x}/{y}.png',
    dem: 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
    vectorStyle: 'https://tiles.openfreemap.org/styles/liberty',
    vectorTiles: 'https://tiles.openfreemap.org/planet',
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
};
const DEM_MAX_ZOOM = 13;
// Resort names show once zoomed in on a region, then fade out as you zoom in on the resort
const RESORT_NAME_MIN_ZOOM = 7;
const RESORT_NAME_FADE_ZOOM = [11, 12];
// Contour spacing in feet by source zoom: [minor, major]
const CONTOUR_THRESHOLDS_FT = {
    8: [1000, 5000], 10: [500, 2500], 11: [250, 1000], 12: [100, 500],
    13: [100, 500], 14: [40, 200], 15: [20, 100],
};

// Touch device detection - skip hover popups on mobile
const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

let map;
let mapReady = false;
let demSource = null; // maplibre-contour DemSource shared by hillshade, 3D relief and contours
let markers = []; // [{ resort, baseRadius, isRing }] for the currently displayed resorts
let weather = null; // weather.js overlay controller, once the map is up
let flyby = null; // flyby.js resort flyover controller, once the map is up
let tourPrefsBackup = null; // the user's layer settings while a flyover forces its own
let resortData = [];
let currentDetailResort = null;

// Side panel list: 'view' (resorts on screen), 'top10' or 'search'. Search is only
// available while the box has a query; clearing it returns to the last browse mode.
const LIST_MODE_LABELS = { view: 'In view', top10: 'Top 10', search: 'Search results' };
let listMode = 'view';
let browseMode = 'view';
let searchQuery = '';
let inViewResorts = null; // null until the map can tell us what's on screen
let inViewKey = '';

// Hover popup state
let hoverPopup = null;
let hoverPopupChart = null;
let hoverHideTimeout = null;
let currentHoverResort = null;
const HOVER_HIDE_DELAY = 150;

// Country code to name mapping
const COUNTRY_NAMES = {
    'AD': 'Andorra', 'AR': 'Argentina', 'AT': 'Austria', 'AU': 'Australia',
    'BG': 'Bulgaria', 'CA': 'Canada', 'CH': 'Switzerland', 'CL': 'Chile', 'CN': 'China',
    'CZ': 'Czech Republic', 'DE': 'Germany', 'ES': 'Spain', 'FI': 'Finland',
    'FR': 'France', 'IN': 'India', 'IT': 'Italy', 'JP': 'Japan', 'KR': 'South Korea',
    'NO': 'Norway', 'NZ': 'New Zealand', 'PL': 'Poland', 'RO': 'Romania',
    'SE': 'Sweden', 'SI': 'Slovenia', 'SK': 'Slovakia', 'US': 'United States'
};

// ---- Layer preferences -------------------------------------------------------------

function sanitizeLayerPrefs(raw) {
    const prefs = { ...DEFAULT_LAYER_PREFS };
    if (raw && typeof raw === 'object') {
        if (BASE_MODES.includes(raw.mode)) prefs.mode = raw.mode;
        for (const key of ['labels', 'terrain', 'threeD', 'trails']) {
            if (typeof raw[key] === 'boolean') prefs[key] = raw[key];
        }
    }
    return prefs;
}

function loadLayerPrefs() {
    try {
        return sanitizeLayerPrefs(JSON.parse(localStorage.getItem(LAYER_PREFS_KEY)));
    } catch (e) {
        return { ...DEFAULT_LAYER_PREFS }; // storage unavailable or corrupt
    }
}

function saveLayerPrefs(prefs) {
    try { localStorage.setItem(LAYER_PREFS_KEY, JSON.stringify(prefs)); } catch (e) { /* storage unavailable */ }
}

// Layer ids are grouped by prefix: base-*, osm-*, lbl-*, terrain-*, trails-*; anything else is always on
function getLayerGroup(id) {
    const prefix = id.split('-')[0];
    return ['base', 'osm', 'lbl', 'terrain', 'trails'].includes(prefix) ? prefix : null;
}

function isLayerVisible(id, prefs) {
    if (id === 'base-sat') return prefs.mode === 'sat';
    if (id === 'base-topo') return prefs.mode === 'topo';
    switch (getLayerGroup(id)) {
        case 'osm': return prefs.mode === 'map';
        case 'lbl': return prefs.mode === 'sat' && prefs.labels;
        case 'terrain': return prefs.terrain;
        case 'trails': return prefs.trails;
        default: return true; // background, resorts
    }
}

// ---- Share links -------------------------------------------------------------------
// A share URL carries the camera, layer settings, filters and selected resort. It is only
// read on first landing; the address bar is not kept in sync afterwards.

const SHARE_SNOW_VALUES = ['forecast', 'historical', 'total'];
const SHARE_DEFAULT_ZOOM = 4;
// First view: whole globe visible (zoom = the fit-the-globe minimum), centred on California
const DEFAULT_CENTER = [-119.5, 37.5];
const SHARE_MAX_TEXT = 120;
const TOAST_MS = 2200;

function parseShareBool(value) {
    if (value === '1' || value === 'true') return true;
    if (value === '0' || value === 'false') return false;
    return undefined;
}

function parseShareNumber(value, min, max) {
    if (value === null || value === undefined || value.trim() === '') return undefined;
    const n = Number(value);
    return Number.isFinite(n) && n >= min && n <= max ? n : undefined;
}

function parseShareText(value) {
    if (typeof value !== 'string') return undefined;
    const text = value.trim();
    return text && text.length <= SHARE_MAX_TEXT ? text : undefined;
}

// Parse and validate a location.search string. Anything malformed is dropped silently.
function parseShareParams(search) {
    const params = new URLSearchParams(search || '');
    const result = { camera: null, prefs: {}, filters: {}, resort: null, fly: false };

    const lat = parseShareNumber(params.get('lat'), -90, 90);
    const lng = parseShareNumber(params.get('lng'), -180, 180);
    if (lat !== undefined && lng !== undefined) {
        result.camera = {
            lat, lng,
            zoom: parseShareNumber(params.get('z'), 0, MAX_ZOOM) ?? SHARE_DEFAULT_ZOOM,
            bearing: parseShareNumber(params.get('b'), -360, 360) ?? 0,
            pitch: parseShareNumber(params.get('p'), 0, 85) ?? 0,
        };
    }

    const base = params.get('base');
    if (BASE_MODES.includes(base)) result.prefs.mode = base;
    for (const [key, pref] of [['labels', 'labels'], ['terrain', 'terrain'], ['3d', 'threeD'], ['trails', 'trails']]) {
        const value = parseShareBool(params.get(key));
        if (value !== undefined) result.prefs[pref] = value;
    }

    if (SHARE_SNOW_VALUES.includes(params.get('snow'))) result.filters.snow = params.get('snow');

    result.resort = parseShareText(params.get('resort')) || null;
    result.fly = !!result.resort && parseShareBool(params.get('fly')) === true;
    return result;
}

// state: { camera: {lat,lng,zoom,bearing,pitch}|null, prefs, filters, resort, fly }
// A flyover link (fly) carries the resort but no camera: the friend gets the whole flight in.
function buildShareUrl(base, state) {
    const params = new URLSearchParams();
    if (state.camera) {
        params.set('lat', state.camera.lat.toFixed(4));
        params.set('lng', state.camera.lng.toFixed(4));
        params.set('z', state.camera.zoom.toFixed(2));
        if (Math.round(state.camera.bearing)) params.set('b', String(Math.round(state.camera.bearing)));
        if (Math.round(state.camera.pitch)) params.set('p', String(Math.round(state.camera.pitch)));
    }
    const prefs = state.prefs || DEFAULT_LAYER_PREFS;
    params.set('base', prefs.mode);
    params.set('labels', prefs.labels ? '1' : '0');
    params.set('terrain', prefs.terrain ? '1' : '0');
    params.set('3d', prefs.threeD ? '1' : '0');
    params.set('trails', prefs.trails ? '1' : '0');

    const filters = state.filters || {};
    if (filters.snow && filters.snow !== 'forecast') params.set('snow', filters.snow);
    if (state.resort) params.set('resort', state.resort);
    if (state.resort && state.fly) params.set('fly', '1');

    return `${base}?${params.toString()}`;
}

function getShareState() {
    const value = (id) => {
        const el = document.getElementById(id);
        return el ? el.value : '';
    };
    // On a resort with a flyover, share the flyover rather than the current camera, and the
    // user's own layer choices rather than the ones the flyover forces
    const fly = !!(currentDetailResort && flyby && flyby.getState().hasTour);
    const state = {
        camera: null,
        prefs: { ...(tourPrefsBackup || layerPrefs) },
        filters: { snow: value('snow-filter') },
        resort: currentDetailResort ? currentDetailResort.name : null,
        fly,
    };
    if (map && mapReady && !fly) {
        const c = map.getCenter();
        state.camera = { lat: c.lat, lng: c.lng, zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() };
    }
    return state;
}

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (e) { /* insecure context or permission denied: fall through */ }
    try {
        const field = document.createElement('textarea');
        field.value = text;
        field.setAttribute('readonly', '');
        field.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
        document.body.appendChild(field);
        field.select();
        const ok = document.execCommand('copy');
        field.remove();
        return ok;
    } catch (e) {
        return false;
    }
}

let toastTimer = null;
function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), TOAST_MS);
}

async function shareCurrentView() {
    const base = window.location.origin + window.location.pathname;
    const state = getShareState();
    const url = buildShareUrl(base, state);
    if (await copyToClipboard(url)) {
        showToast(state.fly ? `Flyover link copied: ${state.resort}` : 'URL copied to clipboard');
    } else {
        window.prompt('Copy this link to share this view:', url);
    }
}

// ---- Map style ---------------------------------------------------------------------

// The OpenFreeMap "Liberty" style supplies the labelled Map mode and the label overlay
// used on top of satellite imagery. If it can't be fetched the raster modes still work.
async function loadVectorStyle() {
    try {
        const response = await fetch(MAP_SOURCES.vectorStyle);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const style = await response.json();
        return { layers: style.layers || [], sprite: style.sprite, glyphs: style.glyphs };
    } catch (e) {
        console.warn('Vector map style unavailable; labelled Map mode disabled', e);
        return null;
    }
}

// Liberty symbol layers worth drawing over satellite imagery (names only, no icons/shields)
const LABEL_SOURCE_LAYERS = ['place', 'water_name', 'waterway', 'transportation_name', 'aerodrome_label'];

function buildLabelOverlayLayers(vectorLayers) {
    return vectorLayers
        .filter(l => l.type === 'symbol' && LABEL_SOURCE_LAYERS.includes(l['source-layer']) &&
            !/shield|one_way|poi/.test(l.id))
        .map(l => ({
            ...l,
            id: `lbl-${l.id}`,
            // Latin names only: Liberty's default stacks the local script on top of it
            layout: { ...l.layout, 'text-field': ['coalesce', ['get', 'name:latin'], ['get', 'name']] },
            paint: {
                ...(l.paint || {}),
                'text-color': '#ffffff',
                'text-halo-color': 'rgba(0, 0, 0, 0.8)',
                'text-halo-width': 1.6,
                'text-halo-blur': 0.5,
            },
        }));
}

// Lift lines and names from OpenMapTiles data, shown with the lifts & trails toggle
function buildLiftLayers() {
    return [
        {
            id: 'trails-lifts', type: 'line', source: 'openmaptiles', 'source-layer': 'transportation',
            minzoom: 10, filter: ['==', ['get', 'class'], 'aerialway'],
            paint: {
                'line-color': '#ff4d4d',
                'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1, 16, 3],
                'line-dasharray': [2, 1],
            },
        },
        {
            id: 'trails-lift-labels', type: 'symbol', source: 'openmaptiles', 'source-layer': 'transportation_name',
            minzoom: 12, filter: ['==', ['get', 'class'], 'aerialway'],
            layout: {
                'symbol-placement': 'line', 'text-field': ['get', 'name'],
                'text-font': ['Noto Sans Regular'], 'text-size': 11,
            },
            paint: { 'text-color': '#ffffff', 'text-halo-color': 'rgba(0,0,0,0.85)', 'text-halo-width': 1.6 },
        },
    ];
}

function buildMapStyle(vector, prefs) {
    const sources = {
        'sat': {
            type: 'raster', tiles: [MAP_SOURCES.satellite], tileSize: 256, maxzoom: 18,
            attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
        },
        'topo': {
            type: 'raster', tiles: [MAP_SOURCES.topo], tileSize: 256, maxzoom: 17,
            attribution: '&copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
        },
    };
    const layers = [
        { id: 'background', type: 'background', paint: { 'background-color': '#0b1d33' } },
        { id: 'base-sat', type: 'raster', source: 'sat' },
        { id: 'base-topo', type: 'raster', source: 'topo' },
    ];

    if (vector) {
        sources.openmaptiles = {
            type: 'vector', url: MAP_SOURCES.vectorTiles,
            attribution: '&copy; <a href="https://openfreemap.org">OpenFreeMap</a> ' +
                '&copy; <a href="https://www.openmaptiles.org/">OpenMapTiles</a> ' +
                'Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        };
        sources.ne2_shaded = {
            type: 'raster', tileSize: 256, maxzoom: 6,
            tiles: ['https://tiles.openfreemap.org/natural_earth/ne2sr/{z}/{x}/{y}.png'],
        };
        for (const l of vector.layers) layers.push({ ...l, id: `osm-${l.id}` });
    }

    if (demSource) {
        sources.dem = {
            type: 'raster-dem', tiles: [demSource.sharedDemProtocolUrl], encoding: 'terrarium',
            tileSize: 256, maxzoom: DEM_MAX_ZOOM,
            attribution: 'Terrain &copy; <a href="https://registry.opendata.aws/terrain-tiles/">AWS Terrain Tiles</a>',
        };
        sources['dem-hillshade'] = { ...sources.dem };
        sources.contours = {
            type: 'vector', maxzoom: 15,
            tiles: [demSource.contourProtocolUrl({
                multiplier: FEET_PER_METER,
                thresholds: CONTOUR_THRESHOLDS_FT,
                contourLayer: 'contours', elevationKey: 'ele', levelKey: 'level',
                extent: 4096, buffer: 1,
            })],
        };
        layers.push(
            {
                id: 'terrain-hillshade', type: 'hillshade', source: 'dem-hillshade',
                paint: {
                    'hillshade-exaggeration': 0.4, 'hillshade-shadow-color': '#0a1a2a',
                    'hillshade-highlight-color': '#ffffff', 'hillshade-accent-color': '#33445a',
                },
            },
            {
                id: 'terrain-contours-minor', type: 'line', source: 'contours', 'source-layer': 'contours',
                filter: ['==', ['get', 'level'], 0],
                paint: { 'line-color': 'rgba(255,255,255,0.3)', 'line-width': 0.5 },
            },
            {
                id: 'terrain-contours-major', type: 'line', source: 'contours', 'source-layer': 'contours',
                filter: ['==', ['get', 'level'], 1],
                paint: { 'line-color': 'rgba(255,255,255,0.75)', 'line-width': 1.1 },
            },
            {
                id: 'terrain-contour-labels', type: 'symbol', source: 'contours', 'source-layer': 'contours',
                filter: ['>', ['get', 'level'], 0],
                layout: {
                    'symbol-placement': 'line', 'symbol-spacing': 450,
                    'text-size': ['interpolate', ['linear'], ['zoom'], 10, 8, 15, 10],
                    'text-font': ['Noto Sans Regular'],
                    'text-field': ['concat', ['to-string', ['get', 'ele']], ' ft'],
                },
                paint: { 'text-color': '#ffffff', 'text-halo-color': 'rgba(0,0,0,0.8)', 'text-halo-width': 1.2 },
            },
        );
    }

    if (vector) {
        layers.push(...buildLiftLayers());
        layers.push(...buildLabelOverlayLayers(vector.layers));
    }

    for (const layer of layers) {
        layer.layout = {
            ...(layer.layout || {}),
            visibility: isLayerVisible(layer.id, prefs) ? 'visible' : 'none',
        };
    }

    return {
        version: 8,
        projection: { type: 'globe' },
        sources,
        layers,
        sprite: vector ? vector.sprite : undefined,
        glyphs: vector ? vector.glyphs : MAP_SOURCES.glyphs,
        sky: { 'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0] },
    };
}

// ---- Map lifecycle -----------------------------------------------------------------

// Whole-globe minimum zoom: the largest 0.5-step zoom at which the globe still fits the
// smaller viewport side (a globe's diameter is 512 * 2^z / PI px).
function computeMinZoom(width, height) {
    const size = Math.min(width, height);
    if (!(size > 0)) return MIN_ZOOM;
    const zoom = Math.log2((Math.PI * GLOBE_FILL * size) / TILE_SIZE);
    return Math.max(0, Math.floor(zoom * 2) / 2);
}

// Marker radius multiplier at a zoom level (grows at ZOOM_SCALE_RATE of the map's own rate)
function zoomScaleAt(zoom) {
    return Math.pow(2, ZOOM_SCALE_RATE * (zoom - MIN_ZOOM));
}

// circle-radius expression: per-feature base radius times the zoom scale. MapLibre only
// allows zoom at the top of an interpolate, so sample the exponential at each whole zoom.
function buildRadiusExpression(extra = 0) {
    const expr = ['interpolate', ['linear'], ['zoom']];
    for (let z = 0; z <= MAX_ZOOM; z++) {
        const radius = ['*', ['get', 'r'], zoomScaleAt(z)];
        expr.push(z, extra ? ['+', radius, extra] : radius);
    }
    return expr;
}

function resortToFeature(resort, index, baseRadius, isRing) {
    return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [resort.longitude, resort.latitude] },
        properties: { idx: index, r: baseRadius, ring: isRing, name: resort.name },
    };
}

async function initMap(shared) {
    // Shared-link settings win for this visit; they are only saved if the user changes something
    layerPrefs = { ...loadLayerPrefs(), ...(shared ? shared.prefs : {}) };
    syncMenuInputs();
    if (window.maplibregl && window.mlcontour) {
        demSource = new window.mlcontour.DemSource({
            url: MAP_SOURCES.dem, encoding: 'terrarium', maxzoom: DEM_MAX_ZOOM, worker: true,
        });
        demSource.setupMaplibre(window.maplibregl);
    }
    const vector = await loadVectorStyle();
    const size = document.getElementById('map').getBoundingClientRect();
    const minZoom = computeMinZoom(size.width, size.height);
    const camera = shared ? shared.camera : null;

    map = new maplibregl.Map({
        container: 'map',
        style: buildMapStyle(vector, layerPrefs),
        center: camera ? [camera.lng, camera.lat] : DEFAULT_CENTER,
        zoom: camera ? Math.max(camera.zoom, minZoom) : minZoom,
        bearing: camera ? camera.bearing : 0,
        pitch: camera ? camera.pitch : 0,
        minZoom,
        maxZoom: MAX_ZOOM,
        maxPitch: layerPrefs.threeD ? 85 : 60,
        fadeDuration: 100,
        maxTileCacheSize: 400,
        refreshExpiredTiles: false,
        attributionControl: { compact: true },
    });
    setLayerAvailability(!!vector, !!demSource);
    window.__map = map; // exposed for e2e tests / debugging

    window.__powder = createTestHooks();
    map.on('zoomend', syncTerrain3d);
    map.on('error', (e) => {
        // Tile fetch failures are routine on flaky networks; keep them out of the user's face
        if (e && e.error) console.debug('map error', e.error.message || e.error);
    });
    // Resort bubbles only need the style; don't wait for every visible tile ('load') first
    if (!map.isStyleLoaded()) await new Promise(resolve => map.once('style.load', resolve));
    mapReady = true;
    collapseAttribution();
    // MapLibre re-opens it on resize (e.g. the side panel settling), so keep it closed
    // until the user first touches the map.
    const keepClosed = () => collapseAttribution();
    map.on('resize', keepClosed);
    map.getCanvas().addEventListener('pointerdown', () => map.off('resize', keepClosed), { once: true });
    addResortLayer();
    syncTerrain3d();
    watchMapSize();
    installMapInteractions();
    map.on('moveend', () => updateInView());
    map.on('resize', () => updateInView());
    if (window.PowderWeather) weather = window.PowderWeather.createController(map, window.maplibregl);
    if (window.PowderFlyby) {
        flyby = window.PowderFlyby.createController(map, window.maplibregl, {
            exaggeration: TERRAIN_EXAGGERATION, onChange: syncFlybyButton,
        });
    }
}

// Read-only introspection plus one navigation helper for e2e tests; bubbles are drawn on a
// WebGL canvas so there are no DOM nodes to select.
function createTestHooks() {
    return {
        markerCount: () => (mapReady ? markers.length : 0),
        // Centre on the first displayed resort and return where it sits on the page
        revealFirstMarker() {
            const entry = markers[0];
            if (!entry) return null;
            map.jumpTo({ center: [entry.resort.longitude, entry.resort.latitude], zoom: 5, pitch: 0, bearing: 0 });
            const rect = document.getElementById('map').getBoundingClientRect();
            const pt = map.project([entry.resort.longitude, entry.resort.latitude]);
            return { name: entry.resort.name, x: rect.left + pt.x, y: rect.top + pt.y };
        },
        // Is the first displayed resort's bubble currently rendered (hit-testable) on screen?
        firstMarkerRendered() {
            const entry = markers[0];
            if (!entry) return false;
            const pt = map.project([entry.resort.longitude, entry.resort.latitude]);
            return map.queryRenderedFeatures([pt.x, pt.y], { layers: ['resorts'] }).length > 0;
        },
        layerVisibility: (id) => (map.getLayer(id) ? map.getLayoutProperty(id, 'visibility') : null),
        hasTerrain: () => !!map.getTerrain(),
        weather: () => (weather ? weather.getState() : null),
        weatherReady: () => (weather ? weather.ready.then(() => true) : Promise.resolve(false)),
        setWeatherFrame: (i) => weather && weather.setFrame(i),
        flyby: () => (flyby ? flyby.getState() : null),
        flybyTime: () => (flyby ? flyby.getTime() : 0),
        flybyDuration: () => (flyby ? flyby.getDuration() : 0),
    };
}

// MapLibre opens the compact attribution until the first map move; on a small map that
// covers a third of the view. Start it collapsed behind its (i) button instead.
function collapseAttribution() {
    const attribution = document.querySelector('#map .maplibregl-ctrl-attrib');
    if (!attribution) return;
    attribution.classList.remove('maplibregl-compact-show');
    attribution.removeAttribute('open');
}

// Keep the canvas size in step with its container (side panel collapse, rotate, etc.).
// Resizing clears the WebGL canvas and MapLibre would only repaint next frame, so during
// the sheet's slide every frame flashed blank; redraw synchronously instead.
function syncMapSize() {
    if (!map) return;
    map.resize();
    map.redraw();
    const size = document.getElementById('map').getBoundingClientRect();
    map.setMinZoom(computeMinZoom(size.width, size.height));
}

function watchMapSize() {
    let pending = false;
    const schedule = () => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => { pending = false; syncMapSize(); });
    };
    if (typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(schedule).observe(document.getElementById('map'));
    }
    window.addEventListener('resize', schedule);
    window.addEventListener('orientationchange', schedule);
    if (window.visualViewport) window.visualViewport.addEventListener('resize', schedule);
}

// The app shell must never scroll; undo any scroll the browser applies to it.
const NON_SCROLLING_CLASSES = ['main-container', 'content-wrapper', 'map-wrapper', 'side-panel', 'maplibregl-map'];
function installScrollGuard() {
    document.addEventListener('scroll', (e) => {
        const t = e.target;
        if (t === document || t === document.documentElement || t === document.body) {
            if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
        } else if (t.classList && NON_SCROLLING_CLASSES.some(c => t.classList.contains(c))) {
            t.scrollLeft = 0;
            t.scrollTop = 0;
        }
    }, true);
}

// ---- Layer switcher ----------------------------------------------------------------

function applyLayerPrefs({ save = true } = {}) {
    if (!map || !mapReady) return;
    for (const layer of map.getStyle().layers) {
        if (RESORT_BUBBLE_LAYERS.includes(layer.id) || layer.id.startsWith('wx-')) continue; // managed elsewhere
        const want = isLayerVisible(layer.id, layerPrefs) ? 'visible' : 'none';
        if (map.getLayoutProperty(layer.id, 'visibility') !== want) {
            map.setLayoutProperty(layer.id, 'visibility', want);
        }
    }
    map.setMaxPitch(layerPrefs.threeD ? 85 : 60);
    syncTerrain3d();
    if (save) saveLayerPrefs(layerPrefs);
}

// 3D relief only once zoomed in; setTerrain is skipped when nothing changes
function syncTerrain3d() {
    if (!map || !mapReady || !map.getSource('dem')) return;
    const want = layerPrefs.threeD && map.getZoom() >= TERRAIN_3D_MIN_ZOOM;
    const has = !!map.getTerrain();
    if (want && !has) {
        map.setTerrain({ source: 'dem', exaggeration: TERRAIN_EXAGGERATION });
    } else if (!want && has) {
        map.setTerrain(null);
    }
}

// The menu (filters + map layers + share) is static markup in index.html so it still works
// when WebGL is unavailable; these functions only wire it up.

function syncMenuInputs() {
    document.querySelectorAll('input[name="base-mode"]').forEach(i => { i.checked = i.value === layerPrefs.mode; });
    document.querySelectorAll('input[data-pref]').forEach(i => { i.checked = !!layerPrefs[i.dataset.pref]; });
}

// Grey out layers whose sources didn't load (vector style fetch failed, contour plugin missing)
function setLayerAvailability(hasVector, hasTerrain) {
    const disable = (selector, off) => document.querySelectorAll(selector).forEach(i => { i.disabled = off; });
    disable('input[name="base-mode"][value="map"]', !hasVector);
    disable('input[data-pref="labels"]', !hasVector);
    disable('input[data-pref="terrain"]', !hasTerrain);
    disable('input[data-pref="threeD"]', !hasTerrain);
}

function onLayerInputChange(e) {
    const input = e.target;
    if (input.name === 'base-mode') layerPrefs.mode = input.value;
    else if (input.dataset && input.dataset.pref) layerPrefs[input.dataset.pref] = input.checked;
    else return;
    tourPrefsBackup = null; // an explicit choice outlives the flyover
    if (mapReady) applyLayerPrefs();
    else saveLayerPrefs(layerPrefs);
}

function setMenuOpen(open) {
    const panel = document.getElementById('menu-panel');
    const toggle = document.getElementById('menu-toggle');
    if (!panel || !toggle) return;
    panel.classList.toggle('visible', open);
    toggle.setAttribute('aria-expanded', String(open));
}

function toggleMenu() {
    const panel = document.getElementById('menu-panel');
    setMenuOpen(!panel.classList.contains('visible'));
}

// ---- Resort layer ------------------------------------------------------------------

function addResortLayer() {
    map.addSource('resorts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
        id: 'resorts',
        type: 'circle',
        source: 'resorts',
        paint: {
            'circle-radius': buildRadiusExpression(),
            'circle-color': BUBBLE_COLOR,
            'circle-opacity': ['case', ['get', 'ring'], 0, BUBBLE_FILL_OPACITY],
            'circle-stroke-color': BUBBLE_COLOR,
            'circle-stroke-width': 2,
            'circle-pitch-alignment': 'map',
        },
    });
    // White ring around the selected / list-hovered resort
    map.addLayer({
        id: 'resorts-highlight',
        type: 'circle',
        source: 'resorts',
        filter: ['==', ['get', 'name'], ''],
        paint: {
            'circle-radius': buildRadiusExpression(3),
            'circle-color': 'rgba(0, 0, 0, 0)',
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 2.5,
            'circle-pitch-alignment': 'map',
        },
    });
    map.addLayer(buildResortNameLayer());
    refreshResortSource();
}

function setMapHighlight(name) {
    if (!map || !mapReady || !map.getLayer('resorts-highlight')) return;
    map.setFilter('resorts-highlight', ['==', ['get', 'name'], name || '']);
}

// Blue resort names under the bubbles, shown with the lifts & names toggle
function buildResortNameLayer() {
    const [fadeStart, fadeEnd] = RESORT_NAME_FADE_ZOOM;
    return {
        id: 'trails-resort-names',
        type: 'symbol',
        source: 'resorts',
        minzoom: RESORT_NAME_MIN_ZOOM,
        maxzoom: fadeEnd,
        layout: {
            'text-field': ['get', 'name'],
            'text-font': ['Noto Sans Regular'],
            'text-size': 13,
            'text-anchor': 'top',
            'text-offset': [0, 1.4],
            'text-max-width': 9,
            visibility: isLayerVisible('trails-resort-names', layerPrefs) ? 'visible' : 'none',
        },
        paint: {
            'text-color': '#1d4ed8',
            'text-halo-color': 'rgba(255, 255, 255, 0.9)',
            'text-halo-width': 1.6,
            'text-opacity': ['interpolate', ['linear'], ['zoom'], fadeStart, 1, fadeEnd, 0],
        },
    };
}

function refreshResortSource() {
    if (!map || !mapReady) return;
    const source = map.getSource('resorts');
    if (!source) return;
    const features = markers.map((m, i) => resortToFeature(m.resort, i, m.baseRadius, m.isRing));
    source.setData({ type: 'FeatureCollection', features });
}

function installMapInteractions() {
    map.on('mouseenter', 'resorts', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'resorts', () => {
        map.getCanvas().style.cursor = '';
        if (!isTouchDevice) scheduleHideHoverPopup();
    });
    if (!isTouchDevice) {
        map.on('mousemove', 'resorts', (e) => {
            const feature = e.features && e.features[0];
            const entry = feature && markers[feature.properties.idx];
            if (entry) showHoverPopup(entry.resort);
        });
    }
    map.on('click', (e) => {
        setMenuOpen(false);
        const hits = map.queryRenderedFeatures(e.point, { layers: ['resorts'] });
        const entry = hits.length ? markers[hits[0].properties.idx] : null;
        if (entry) {
            if (isTouchDevice) hideHoverPopup();
            toggleDetail(entry.resort);
            if (currentDetailResort === entry.resort) startTourIfAny(entry.resort);
        } else {
            hideDetail();
            if (weather) weather.showReadout(e.lngLat);
        }
    });
    // The popup is anchored in screen space: drop it as soon as the map moves under it
    map.on('movestart', hideHoverPopup);
}

// Base bubble radius (at min zoom) based on total snowfall
function getRadius(totalInches) {
    return MIN_RADIUS + (totalInches / 2);
}

// Get snowfall value based on current filter selection
function getSnowfallForFilter(resort) {
    const filter = document.getElementById('snow-filter').value;
    switch (filter) {
        case 'forecast': return resort.total_snowfall_inches || 0;
        case 'historical': return resort.total_historical_inches || 0;
        case 'total': return (resort.total_snowfall_inches || 0) + (resort.total_historical_inches || 0);
        default: return resort.total_snowfall_inches || 0;
    }
}

// Get display label for the current filter
function getFilterLabel() {
    const filter = document.getElementById('snow-filter').value;
    switch (filter) {
        case 'forecast': return 'Forecasted';
        case 'historical': return 'Recent (14 days)';
        case 'total': return 'Total';
        default: return 'Forecasted';
    }
}

// Format a date string for display
function formatDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

// Get country display name
function getCountryName(code) {
    return COUNTRY_NAMES[code] || code;
}

// Calculate days between two date strings (YYYY-MM-DD format)
function daysBetween(date1, date2) {
    const d1 = new Date(date1 + 'T00:00:00');
    const d2 = new Date(date2 + 'T00:00:00');
    return Math.round((d1 - d2) / (1000 * 60 * 60 * 24));
}

// Get cumulative snowfall data for charts
function getCumulativeChartData(resort) {
    const today = new Date().toISOString().split('T')[0];
    const allDays = [];
    
    for (const h of resort.historical_snowfall || []) {
        allDays.push({ date: h.date, value: h.snowfall_inches || 0 });
    }
    for (const f of resort.daily_forecasts || []) {
        allDays.push({ date: f.date, value: f.avg_inches || 0 });
    }
    
    allDays.sort((a, b) => a.date.localeCompare(b.date));
    
    const points = [];
    let cumulative = 0;
    for (const day of allDays) {
        cumulative += day.value;
        points.push({
            date: day.date,
            dayOffset: daysBetween(day.date, today),
            daily: day.value,
            cumulative: cumulative
        });
    }
    
    return points;
}

// Minimum y-axis span (inches) for the cumulative snowfall charts
const CHART_MIN_SCALE_INCHES = 36;

// ApexCharts configuration for snowfall graphs
function getChartConfig(data, options = {}) {
    const { width = 280, height = 100, interactive = true, onDataPointHover = null, onMouseLeave = null } = options;
    
    const seriesData = data.map(d => ({
        x: new Date(d.date + 'T00:00:00').getTime(),
        y: d.cumulative,
        daily: d.daily
    }));
    
    return {
        series: [{ name: 'Cumulative Snow', data: seriesData }],
        chart: {
            type: 'area',
            height: height,
            width: width,
            toolbar: { show: false },
            zoom: { enabled: false },
            animations: { enabled: false },
            background: 'transparent',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            events: {
                mouseLeave: function() { if (onMouseLeave) onMouseLeave(); }
            }
        },
        theme: { mode: 'dark' },
        colors: ['#3b82f6'],
        fill: { type: 'solid', opacity: 0.4 },
        stroke: { curve: 'straight', width: 2 },
        markers: { size: 0, hover: { size: 5 } },
        dataLabels: { enabled: false },
        xaxis: {
            type: 'datetime',
            labels: { 
                style: { colors: '#888', fontSize: '9px' },
                datetimeUTC: false,
                datetimeFormatter: { day: 'MMM dd' }
            },
            axisBorder: { show: true, color: '#333' },
            axisTicks: { show: true, color: '#333' },
            crosshairs: { show: interactive, stroke: { color: '#fff', width: 1, dashArray: 3 } },
            tooltip: { enabled: false }
        },
        // Absolute scale: the axis spans at least CHART_MIN_SCALE_INCHES so a
        // 0.2" trace stays flat and a 36" storm reads as a big climb. Only a
        // total beyond that grows the axis.
        yaxis: { show: false, min: 0, max: Math.max(CHART_MIN_SCALE_INCHES, ...seriesData.map(d => d.y)) },
        grid: { show: false, padding: { left: 0, right: 0, top: 0, bottom: 0 } },
        tooltip: {
            enabled: interactive,
            shared: true,
            intersect: false,
            custom: function({ dataPointIndex }) {
                if (onDataPointHover && dataPointIndex >= 0) {
                    onDataPointHover(seriesData[dataPointIndex]);
                }
                return '<div style="display:none"></div>';
            }
        },
        annotations: {
            xaxis: [{
                x: new Date().setHours(0, 0, 0, 0),
                borderColor: 'rgba(255,255,255,0.5)',
                strokeDashArray: 3,
                label: {
                    text: 'Today',
                    borderColor: 'transparent',
                    style: { color: '#fff', background: 'transparent', fontSize: '9px', fontWeight: 600 },
                    position: 'bottom',
                    offsetY: 15
                }
            }]
        }
    };
}

// Render ApexCharts detail graph in detail panel
let detailChart = null;
function renderDetailChart(resort) {
    const container = document.getElementById('detail-chart-container');
    if (!container) return;
    
    if (detailChart) {
        detailChart.destroy();
        detailChart = null;
    }
    
    const data = getCumulativeChartData(resort);
    if (data.length === 0) return;
    
    detailChart = new ApexCharts(container, getChartConfig(data, {
        width: '100%',
        height: 120,
        interactive: true,
        onDataPointHover: updateDetailSnowfall,
        onMouseLeave: restoreDetailSnowfall
    }));
    detailChart.render();
}

// Get elevation display text
function getElevationText(resort) {
    const base = resort.elevation_base_ft || resort.elevation_ft || 0;
    const peak = resort.elevation_peak_ft;
    const vert = resort.vertical_drop_ft;
    if (peak && vert) {
        return `${base.toLocaleString()}'-${peak.toLocaleString()}' (${vert.toLocaleString()}' vert)`;
    }
    return `${base.toLocaleString()}' elev`;
}

// Build hover popup content
function buildHoverPopupContent(resort) {
    const snowfall = getSnowfallForFilter(resort);
    const label = getFilterLabel();
    const region = resort.region || resort.state || '';
    const countryName = getCountryName(resort.country);
    const location = region ? `${region}, ${countryName}` : countryName;
    const lifts = resort.lift_count ? `${resort.lift_count} lifts` : '';
    const originalSnowfallText = `${label}: ${snowfall.toFixed(1)}"`;

    // Build elevation line
    const base = resort.elevation_base_ft || resort.elevation_ft || 0;
    const peak = resort.elevation_peak_ft;
    const vert = resort.vertical_drop_ft;
    const elevationLine = (peak && vert)
        ? `${base.toLocaleString()}' base | ${peak.toLocaleString()}' peak | ${vert.toLocaleString()}' vert`
        : `${base.toLocaleString()}' elev`;

    return `
        <div class="hover-popup-header">
            <h3 class="hover-popup-name">${resort.name}</h3>
            <div class="hover-popup-meta">${location}${lifts ? ' | ' + lifts : ''}</div>
            <div class="hover-popup-meta">${elevationLine}</div>
        </div>
        <div class="hover-popup-snowfall" id="hover-popup-snowfall" data-original="${originalSnowfallText}">${originalSnowfallText}</div>
        <div id="hover-popup-chart"></div>
    `;
}

// Create hover popup element
function createHoverPopup() {
    if (hoverPopup) return;

    hoverPopup = document.createElement('div');
    hoverPopup.id = 'hover-popup';
    hoverPopup.className = 'hover-popup';
    hoverPopup.style.display = 'none';
    
    hoverPopup.addEventListener('mouseenter', () => {
        if (hoverHideTimeout) {
            clearTimeout(hoverHideTimeout);
            hoverHideTimeout = null;
        }
    });
    
    hoverPopup.addEventListener('mouseleave', () => hideHoverPopup());
    
    document.body.appendChild(hoverPopup);
}

// Show hover popup for a resort
function showHoverPopup(resort) {
    if (hoverHideTimeout) {
        clearTimeout(hoverHideTimeout);
        hoverHideTimeout = null;
    }
    
    if (currentHoverResort && currentHoverResort.name === resort.name) {
        hoverPopup.style.display = 'block';
        return;
    }
    
    currentHoverResort = resort;
    hoverPopup.innerHTML = buildHoverPopupContent(resort);
    hoverPopup.style.display = 'block';
    positionHoverPopup(resort);
    renderHoverPopupChart(resort);
}

// Position hover popup relative to the resort's marker
function positionHoverPopup(resort) {
    const point = map.project([resort.longitude, resort.latitude]);
    const mapContainer = document.getElementById('map');
    const mapRect = mapContainer.getBoundingClientRect();
    
    const popupWidth = 300;
    const popupHeight = 220;
    const margin = 10; // Minimum margin from viewport edges
    
    // Calculate marker position in viewport coordinates
    const markerX = mapRect.left + point.x;
    const markerY = mapRect.top + point.y;
    
    // Try positioning to the right of the marker first
    let left = markerX + 15;
    let top = markerY - popupHeight - 10;
    
    // Check right edge - if popup goes off right, position to the left of marker
    if (left + popupWidth > window.innerWidth - margin) {
        left = markerX - popupWidth - 15;
    }
    
    // Check left edge - ensure popup doesn't go off left side
    if (left < margin) {
        left = margin;
    }
    
    // Check top edge - if popup goes off top, position below marker
    if (top < margin) {
        top = markerY + 20;
    }
    
    // Check bottom edge - ensure popup doesn't go off bottom
    if (top + popupHeight > window.innerHeight - margin) {
        top = window.innerHeight - popupHeight - margin;
    }
    
    // Final safety check - if screen is too narrow, center horizontally
    if (window.innerWidth < popupWidth + margin * 2) {
        left = (window.innerWidth - popupWidth) / 2;
    }
    
    hoverPopup.style.left = `${left}px`;
    hoverPopup.style.top = `${top}px`;
}

// Update chart snowfall info display
function updateChartSnowfallInfo(elementId, point) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    const date = new Date(point.x);
    const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const isToday = date.toDateString() === new Date().toDateString();
    const label = isToday ? 'Today' : dateStr;
    
    el.innerHTML = `<span class="hover-date">${label}</span> <span class="hover-daily">Daily: ${point.daily.toFixed(1)}"</span> <span class="hover-total">Total: ${point.y.toFixed(1)}"</span>`;
}

// Restore chart snowfall info
function restoreChartSnowfallInfo(elementId) {
    const el = document.getElementById(elementId);
    if (el && el.dataset.original) {
        el.textContent = el.dataset.original;
    }
}

function updateHoverPopupSnowfall(point) { updateChartSnowfallInfo('hover-popup-snowfall', point); }
function restoreHoverPopupSnowfall() { restoreChartSnowfallInfo('hover-popup-snowfall'); }
function updateDetailSnowfall(point) { updateChartSnowfallInfo('detail-chart-info', point); }
function restoreDetailSnowfall() { restoreChartSnowfallInfo('detail-chart-info'); }

// Render hover popup chart
let hoverPopupChartInstance = null;
function renderHoverPopupChart(resort) {
    const container = document.getElementById('hover-popup-chart');
    if (!container) return;
    
    if (hoverPopupChart) {
        hoverPopupChart.destroy();
        hoverPopupChart = null;
    }
    
    const data = getCumulativeChartData(resort);
    if (data.length === 0) return;
    
    hoverPopupChart = new ApexCharts(container, getChartConfig(data, {
        width: 280,
        height: 100,
        interactive: true,
        onDataPointHover: updateHoverPopupSnowfall,
        onMouseLeave: restoreHoverPopupSnowfall
    }));
    hoverPopupChart.render();
}

// Schedule hiding hover popup
function scheduleHideHoverPopup() {
    if (hoverHideTimeout) clearTimeout(hoverHideTimeout);
    hoverHideTimeout = setTimeout(() => hideHoverPopup(), HOVER_HIDE_DELAY);
}

// Hide hover popup
function hideHoverPopup() {
    if (hoverHideTimeout) {
        clearTimeout(hoverHideTimeout);
        hoverHideTimeout = null;
    }
    if (hoverPopup) hoverPopup.style.display = 'none';
    if (hoverPopupChart) {
        hoverPopupChart.destroy();
        hoverPopupChart = null;
    }
    currentHoverResort = null;
}

// Get unique sources from daily forecasts
function getSourcesFromForecasts(dailyForecasts) {
    const sources = new Set();
    for (const day of dailyForecasts) {
        if (day.sources) {
            Object.keys(day.sources).forEach(s => sources.add(s));
        }
    }
    return Array.from(sources).sort();
}

// Build detail panel content
function buildDetailContent(resort) {
    const passDisplay = resort.pass_type || 'Independent';
    const filter = document.getElementById('snow-filter').value;
    const displaySnowfall = getSnowfallForFilter(resort);
    const displayLabel = getFilterLabel() + ' Snowfall';
    const region = resort.region || resort.state || '';
    const countryName = getCountryName(resort.country);
    const lifts = resort.lift_count ? `${resort.lift_count} lifts` : '';

    const sources = getSourcesFromForecasts(resort.daily_forecasts || []);
    const sourceHeaders = sources.map(s => `<th>${s}</th>`).join('');
    const numSourceCols = sources.length || 1;

    let forecastRows = '';
    if (filter === 'forecast' || filter === 'total') {
        if (filter === 'total') {
            forecastRows = `<tr class="section-header"><td colspan="${2 + numSourceCols}">Upcoming Forecast</td></tr>`;
        }
        const sortedForecasts = [...(resort.daily_forecasts || [])].sort((a, b) => b.date.localeCompare(a.date));
        for (const day of sortedForecasts) {
            const sourceCells = sources.map(s => {
                const val = day.sources && day.sources[s] !== undefined ? day.sources[s] : '-';
                return `<td class="source">${val !== '-' ? val + '"' : val}</td>`;
            }).join('');
            forecastRows += `<tr><td class="date">${formatDate(day.date)}</td><td class="avg">${day.avg_inches}"</td>${sourceCells}</tr>`;
        }
    }

    let historicalRows = '';
    if ((filter === 'historical' || filter === 'total') && resort.historical_snowfall) {
        if (filter === 'total') {
            historicalRows = `<tr class="section-header"><td colspan="${2 + numSourceCols}">Recent Snowfall (Past 14 Days)</td></tr>`;
        }
        const sortedHistorical = [...resort.historical_snowfall].sort((a, b) => b.date.localeCompare(a.date));
        for (const day of sortedHistorical) {
            historicalRows += `<tr class="historical"><td class="date">${formatDate(day.date)}</td><td class="avg">${day.snowfall_inches}"</td><td class="source" colspan="${numSourceCols}">Archive</td></tr>`;
        }
    }

    const elevationText = getElevationText(resort);

    return `
        <div class="detail-header">
            <h2>${resort.name}</h2>
            <div class="detail-meta">
                <span>${region}${region ? ', ' : ''}${countryName}</span>
                <span>${elevationText}</span>
                ${lifts ? `<span>${lifts}</span>` : ''}
                <span>${passDisplay}</span>
            </div>
        </div>
        <div class="detail-total">
            <div class="value">${displaySnowfall.toFixed(1)}"</div>
            <div class="label">${displayLabel}</div>
        </div>
        <div id="detail-chart-container"></div>
        <div class="detail-chart-info" id="detail-chart-info" data-original="${displayLabel}: ${displaySnowfall.toFixed(1)}&quot;">${displayLabel}: ${displaySnowfall.toFixed(1)}"</div>
        <table class="forecast-table">
            <thead><tr><th>Date</th><th>Snow</th>${sourceHeaders}</tr></thead>
            <tbody>${forecastRows}${historicalRows}</tbody>
        </table>
    `;
}

function isBottomPanelLayout() {
    return typeof window !== 'undefined' && !!window.matchMedia &&
        window.matchMedia(BOTTOM_PANEL_QUERY).matches;
}

// Next state when the user taps the collapse/expand control. Open and collapsed only:
// the bottom sheet has a single open height, so peek and full look identical.
function nextPanelState(state) {
    return state === 'collapsed' ? (lastOpenPanelState || 'peek') : 'collapsed';
}

// Single source of truth for panel state: class, data-snap, aria and reopen handle
function setPanelState(state) {
    if (!['collapsed', 'peek', 'full'].includes(state)) state = 'peek';
    panelState = state;
    if (state !== 'collapsed') lastOpenPanelState = state;

    const panel = document.getElementById('side-panel');
    const collapseBtn = document.getElementById('panel-collapse');
    const reopenBtn = document.getElementById('panel-reopen');
    const collapsed = state === 'collapsed';

    panel.classList.toggle('collapsed', collapsed);
    panel.dataset.snap = state;
    if (collapseBtn) collapseBtn.setAttribute('aria-expanded', String(!collapsed));
    if (reopenBtn) {
        reopenBtn.hidden = !collapsed;
        reopenBtn.setAttribute('aria-expanded', 'false');
    }

    try { localStorage.setItem(PANEL_STATE_KEY, state); } catch (e) { /* storage unavailable */ }
}

function restorePanelState() {
    let saved = null;
    try { saved = localStorage.getItem(PANEL_STATE_KEY); } catch (e) { /* storage unavailable */ }
    if (saved === 'collapsed' || saved === 'peek' || saved === 'full') {
        if (saved !== 'collapsed') lastOpenPanelState = saved;
        setPanelState(saved);
    } else {
        setPanelState('peek');
    }
}

// ---- Side panel: resort list + details ---------------------------------------------

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Great-circle distance in degrees
function angularDistance(lat1, lng1, lat2, lng2) {
    const rad = Math.PI / 180;
    const cos = Math.sin(lat1 * rad) * Math.sin(lat2 * rad) +
        Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.cos((lng2 - lng1) * rad);
    return Math.acos(Math.min(1, Math.max(-1, cos))) / rad;
}

// Resorts on the visible side of the globe and inside the map's pixel box.
// view: { project([lng, lat]) -> {x, y}, center: {lat, lng}, width, height }
function filterInView(resorts, view) {
    return resorts.filter(r => {
        if (angularDistance(view.center.lat, view.center.lng, r.latitude, r.longitude) > HORIZON_DEG) return false;
        const pt = view.project([r.longitude, r.latitude]);
        return !!pt && pt.x >= 0 && pt.y >= 0 && pt.x <= view.width && pt.y <= view.height;
    });
}

function bySnowfallDesc(resorts) {
    return [...resorts].sort((a, b) => getSnowfallForFilter(b) - getSnowfallForFilter(a) || a.name.localeCompare(b.name));
}

// Recompute what's on screen; re-render only when that set changed (keeps scroll position)
function updateInView(force = false) {
    if (!map || !mapReady) return;
    const rect = map.getCanvas().getBoundingClientRect();
    const resorts = filterInView(resortData, {
        project: (lngLat) => map.project(lngLat),
        center: map.getCenter(),
        width: rect.width,
        height: rect.height,
    });
    const key = resorts.map(r => r.name).join('|');
    if (!force && inViewResorts && key === inViewKey) return;
    inViewKey = key;
    inViewResorts = resorts;
    syncModeButtons();
    if (listMode === 'view') renderList();
}

function getListResorts() {
    if (listMode === 'search') return searchResorts(resortData, searchQuery);
    if (listMode === 'top10') return bySnowfallDesc(resortData).slice(0, TOP_LIMIT);
    return bySnowfallDesc(inViewResorts || resortData);
}

function syncModeButtons() {
    document.querySelectorAll('.panel-mode').forEach(btn => {
        const active = btn.dataset.mode === listMode;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-selected', String(active));
        if (btn.dataset.mode === 'search') btn.hidden = !searchQuery;
    });
    const viewCount = document.getElementById('view-count');
    if (viewCount) viewCount.textContent = inViewResorts ? String(inViewResorts.length) : '';
    const searchCount = document.getElementById('search-count');
    if (searchCount) searchCount.textContent = searchQuery ? String(searchResorts(resortData, searchQuery).length) : '';
}

function buildListSummary(count) {
    const sortNote = `<span>${escapeHtml(getFilterLabel())} snow</span>`;
    if (listMode === 'search') {
        const q = escapeHtml(searchQuery);
        const text = count
            ? `<span><strong>${count}</strong> ${count === 1 ? 'match' : 'matches'} for “${q}”</span>`
            : `<span class="list-empty">No resorts match “${q}”.</span>`;
        return `${text}<button type="button" class="link-button" data-action="clear-search">Clear search</button>`;
    }
    if (listMode === 'top10') {
        return `<span><strong>Most snow</strong> worldwide</span>${sortNote}`;
    }
    if (!count) {
        return `<span class="list-empty">No resorts in view. Zoom out, or see the
            <button type="button" class="link-button" data-action="top10">Top 10</button>.</span>`;
    }
    return `<span><strong>${count}</strong> ${count === 1 ? 'resort' : 'resorts'} on the map</span>${sortNote}`;
}

function buildResortItem(resort, rank, maxSnow) {
    const snowfall = getSnowfallForFilter(resort);
    const region = resort.region || resort.state || '';
    const place = `${region ? region + ', ' : ''}${getCountryName(resort.country)}`;
    const width = maxSnow > 0 ? Math.max(0, Math.min(100, (snowfall / maxSnow) * 100)) : 0;
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'resort-item';
    item.dataset.name = resort.name;
    if (currentDetailResort && currentDetailResort.name === resort.name) item.classList.add('selected');
    item.innerHTML = `
        ${rank ? `<span class="rank">#${rank}</span>` : ''}
        <span class="main">
            <span class="name">${escapeHtml(resort.name)}</span>
            <span class="place">${escapeHtml(place)}</span>
        </span>
        <span class="snowfall${snowfall < NO_SNOW_THRESHOLD ? ' none' : ''}">${snowfall.toFixed(1)}"</span>
        ${width ? `<span class="bar" style="width:${width.toFixed(1)}%"></span>` : ''}
    `;
    item.addEventListener('click', () => selectResort(resort));
    item.addEventListener('mouseenter', () => setMapHighlight(resort.name));
    item.addEventListener('mouseleave', () => setMapHighlight(currentDetailResort ? currentDetailResort.name : ''));
    return item;
}

function renderList() {
    const container = document.getElementById('resort-list');
    if (!container) return;
    const resorts = getListResorts();
    const maxSnow = resorts.reduce((max, r) => Math.max(max, getSnowfallForFilter(r)), 0);
    container.innerHTML = '';
    resorts.forEach((resort, i) => container.appendChild(buildResortItem(resort, listMode === 'top10' ? i + 1 : 0, maxSnow)));
    const summary = document.getElementById('list-summary');
    if (summary) summary.innerHTML = buildListSummary(resorts.length);
}

function setListMode(mode) {
    if (!LIST_MODE_LABELS[mode] || (mode === 'search' && !searchQuery)) mode = browseMode;
    if (mode !== 'search') browseMode = mode;
    listMode = mode;
    if (currentDetailResort) hideDetail();
    syncModeButtons();
    renderList();
}

// Show a resort's details in place of the list
function showDetail(resort) {
    document.getElementById('detail-content').innerHTML = buildDetailContent(resort);
    const back = document.getElementById('detail-back-label');
    if (back) back.textContent = LIST_MODE_LABELS[listMode];
    document.getElementById('list-content').classList.add('hidden');
    document.getElementById('details-content').classList.remove('hidden');
    if (panelState === 'collapsed') setPanelState(lastOpenPanelState);
    currentDetailResort = resort;
    setMapHighlight(resort.name);
    const content = document.querySelector('.panel-content');
    if (content) content.scrollTop = 0;

    requestAnimationFrame(() => {
        requestAnimationFrame(() => renderDetailChart(resort));
    });
}

// Deselect the resort and go back to the list. Collapsing is always an explicit user action.
function hideDetail() {
    document.getElementById('details-content').classList.add('hidden');
    document.getElementById('list-content').classList.remove('hidden');
    currentDetailResort = null;
    endTour();
    setMapHighlight('');
    document.querySelectorAll('.resort-item.selected').forEach(el => el.classList.remove('selected'));
}

// Toggle detail for a resort
function toggleDetail(resort) {
    if (currentDetailResort && currentDetailResort.name === resort.name) {
        hideDetail();
        return;
    }
    showDetail(resort);
}

// Open a resort's details and fly there: into its flyover tour when it has one
async function selectResort(resort) {
    showDetail(resort);
    if (await startTourIfAny(resort)) return;
    if (map && currentDetailResort === resort) {
        map.flyTo({ center: [resort.longitude, resort.latitude], zoom: Math.max(map.getZoom(), FOCUS_ZOOM), essential: true });
    }
}

// ---- Flyover tours (flyby.js) --------------------------------------------------------

const FLYOVER_LAYERS = { mode: 'sat', threeD: true, trails: true }; // satellite, 3D relief, lift names
const RESORT_BUBBLE_LAYERS = ['resorts', 'resorts-highlight'];

// Bubbles mean nothing at resort scale (and balloon when that close), so a flyover hides them
function setResortBubblesVisible(visible) {
    if (!map || !mapReady) return;
    for (const id of RESORT_BUBBLE_LAYERS) {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    }
}

// Labelled places a tour passes (camps, summits...), drawn only while it flies. The ids start
// with `tourmarks-` so applyLayerPrefs leaves them alone; emptying the source hides them.
function ensureTourMarkerLayers() {
    if (!map || !mapReady || map.getSource('tour-markers')) return;
    map.addSource('tour-markers', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
        id: 'tourmarks-dots', type: 'circle', source: 'tour-markers',
        paint: { 'circle-radius': 7, 'circle-color': '#f97316', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 },
    });
    map.addLayer({
        id: 'tourmarks-labels', type: 'symbol', source: 'tour-markers',
        layout: {
            'text-field': ['get', 'label'], 'text-font': ['Noto Sans Regular'], 'text-size': 17,
            'text-anchor': 'bottom', 'text-offset': [0, -0.8], 'text-max-width': 14,
            'text-allow-overlap': true, 'text-ignore-placement': true,
        },
        paint: { 'text-color': '#fff', 'text-halo-color': 'rgba(0, 0, 0, 0.85)', 'text-halo-width': 2 },
    });
}

function setTourMarkers(markers) {
    if (!markers || !markers.length) { clearTourMarkers(); return; }
    ensureTourMarkerLayers();
    const src = map && map.getSource('tour-markers');
    if (!src) return;
    src.setData({
        type: 'FeatureCollection',
        features: markers.map(m => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: m.at },
            properties: { label: `${m.name}
${Math.round(m.ele_m).toLocaleString()} m (${Math.round(m.ele_m * 3.28084).toLocaleString()} ft)` },
        })),
    });
}

function clearTourMarkers() {
    const src = map && mapReady && map.getSource('tour-markers');
    if (src) src.setData({ type: 'FeatureCollection', features: [] });
}

async function startTourIfAny(resort) {
    if (!flyby || !mapReady) return false;
    if (flyby.getState().resort !== resort.name) endTour();
    const tour = await flyby.getTour(resort.name);
    if (!tour || currentDetailResort !== resort) return false; // none, or the user moved on
    if (!tourPrefsBackup) tourPrefsBackup = { ...layerPrefs };
    layerPrefs = { ...layerPrefs, ...FLYOVER_LAYERS };
    applyLayerPrefs({ save: false });
    syncMenuInputs();
    setResortBubblesVisible(false);
    setTourMarkers(tour.markers);
    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    flyby.start(tour, { autoplay: !reduceMotion });
    return true;
}

// Stop flying and give the user back their own layer settings
function endTour() {
    if (flyby) flyby.stop();
    clearTourMarkers();
    setResortBubblesVisible(true);
    if (tourPrefsBackup) {
        layerPrefs = tourPrefsBackup;
        tourPrefsBackup = null;
        applyLayerPrefs({ save: false });
        syncMenuInputs();
    }
}

function syncFlybyButton(state) {
    const bar = document.getElementById('flyby-bar');
    if (!bar) return;
    bar.hidden = !state.hasTour;
    const button = document.getElementById('flyby-toggle');
    button.classList.toggle('playing', state.playing);
    button.textContent = state.playing ? '❚❚' : '▶';
    button.setAttribute('aria-label', state.playing ? 'Pause flyover' : 'Fly over');
    const slider = document.getElementById('flyby-slider');
    const duration = flyby ? flyby.getDuration() : 0;
    slider.max = String(Math.round(duration * 10));
    if (state.hasTour) startFlybyClock();
}

// Keep the slider and time readout moving with the camera while a tour is up
let flybyClockFrame = 0;
let flybyScrubbing = false;
function startFlybyClock() {
    cancelAnimationFrame(flybyClockFrame);
    const tick = () => {
        if (!flyby || !flyby.getState().hasTour) return;
        updateFlybyClock();
        flybyClockFrame = requestAnimationFrame(tick);
    };
    tick();
}

function updateFlybyClock() {
    const slider = document.getElementById('flyby-slider');
    const time = flyby.getTime(), duration = flyby.getDuration();
    if (!flybyScrubbing) slider.value = String(Math.round(time * 10));
    const shown = flybyScrubbing ? Number(slider.value) / 10 : time;
    document.getElementById('flyby-time').textContent =
        `${window.PowderFlyby.formatClock(shown)} / ${window.PowderFlyby.formatClock(duration)}`;
}

function wireFlybyBar() {
    const slider = document.getElementById('flyby-slider');
    slider.addEventListener('pointerdown', () => { flybyScrubbing = true; });
    const release = () => { flybyScrubbing = false; };
    slider.addEventListener('pointerup', release);
    slider.addEventListener('change', release);
    slider.addEventListener('blur', release);
    slider.addEventListener('input', () => {
        if (!flyby) return;
        flyby.seek(Number(slider.value) / 10);
        updateFlybyClock();
    });
    document.getElementById('flyby-restart').addEventListener('click', () => { if (flyby) { flyby.seek(0); updateFlybyClock(); } });
    document.getElementById('flyby-end').addEventListener('click', () => { if (flyby) { flyby.seek(flyby.getDuration() - 6); updateFlybyClock(); } });
}

function toggleFlyby() {
    if (!flyby) return;
    if (flyby.getState().playing) flyby.pause();
    else flyby.play();
}

// Lowercase and strip accents so "val d'isere" finds "Val d'Isère"
function normalizeSearchText(text) {
    return String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

// Resorts whose name contains the query: name-prefix matches first, then word-prefix, then anywhere
function searchResorts(resorts, query, limit = SEARCH_LIMIT) {
    const q = normalizeSearchText(query);
    if (!q) return [];
    const rank = name => {
        if (name.startsWith(q)) return 0;
        if (name.includes(' ' + q)) return 1;
        return name.includes(q) ? 2 : -1;
    };
    return resorts
        .map(resort => ({ resort, name: normalizeSearchText(resort.name) }))
        .map(entry => ({ ...entry, rank: rank(entry.name) }))
        .filter(entry => entry.rank >= 0)
        .sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name))
        .slice(0, limit)
        .map(entry => entry.resort);
}

function syncSearchClear() {
    document.getElementById('search-clear').hidden = !document.getElementById('search-input').value;
}

// Live search: results replace the panel list as you type
function onSearchInput() {
    const input = document.getElementById('search-input');
    syncSearchClear();
    searchQuery = normalizeSearchText(input.value) ? input.value.trim() : '';
    if (!searchQuery) {
        if (listMode === 'search') setListMode(browseMode);
        else syncModeButtons();
        return;
    }
    if (panelState === 'collapsed') setPanelState(lastOpenPanelState);
    setListMode('search');
}

function clearSearch({ focus = true } = {}) {
    const input = document.getElementById('search-input');
    input.value = '';
    onSearchInput();
    if (focus) input.focus();
}

// Enter: open the best match (Back returns to the results)
function runSearch(e) {
    e.preventDefault();
    onSearchInput();
    const results = searchQuery ? searchResorts(resortData, searchQuery) : [];
    if (results.length > 0) {
        // Dismiss the on-screen keyboard so the map and details are visible on phones
        document.getElementById('search-input').blur();
        selectResort(results[0]);
    }
}

// Logo: back to the opening view (whole globe, resorts in view, nothing selected)
function goHome() {
    setMenuOpen(false);
    hideHoverPopup();
    if (document.getElementById('search-input').value) clearSearch({ focus: false });
    setListMode('view');
    if (map && mapReady) {
        map.flyTo({ center: DEFAULT_CENTER, zoom: map.getMinZoom(), bearing: 0, pitch: 0, essential: true });
    }
    if (window.location.search && window.history && window.history.replaceState) {
        window.history.replaceState(null, '', window.location.pathname);
    }
}

// Rebuild the displayed resort bubbles from the current filters
function createMarkers() {
    hideHoverPopup();

    markers = resortData.map(resort => {
        const snowfall = getSnowfallForFilter(resort);
        const isRing = snowfall < NO_SNOW_THRESHOLD;
        return { resort, baseRadius: isRing ? MIN_RADIUS : getRadius(snowfall), isRing };
    });
    refreshResortSource();

    // The sort order follows the snowfall filter, so always re-render
    updateInView(true);
    syncModeButtons();
    renderList();
}

// Collapse / expand control inside the panel (cycles snaps on the bottom sheet)
function togglePanelCollapse() {
    setPanelState(nextPanelState(panelState));
}

// Reopen handle shown on the map edge while collapsed
function reopenPanel() {
    setPanelState(lastOpenPanelState || 'peek');
}

// Set up event listeners
function setupEventListeners() {
    // Filter listeners: rebuild bubbles + list, and refresh open details for the new filter
    document.getElementById('snow-filter').addEventListener('change', () => {
        createMarkers();
        if (currentDetailResort) showDetail(currentDetailResort);
    });

    // Panel list modes, back bar and links inside the list summary
    document.querySelectorAll('.panel-mode').forEach(btn => {
        btn.addEventListener('click', () => setListMode(btn.dataset.mode));
    });
    document.getElementById('detail-back').addEventListener('click', hideDetail);
    document.getElementById('list-summary').addEventListener('click', (e) => {
        const action = e.target.closest('[data-action]');
        if (!action) return;
        if (action.dataset.action === 'clear-search') clearSearch({ focus: false });
        else setListMode(action.dataset.action);
    });

    // Controls
    document.getElementById('home-button').addEventListener('click', goHome);
    document.getElementById('flyby-toggle').addEventListener('click', toggleFlyby);
    wireFlybyBar();
    document.getElementById('panel-collapse').addEventListener('click', togglePanelCollapse);
    document.getElementById('panel-reopen').addEventListener('click', reopenPanel);
    document.getElementById('menu-toggle').addEventListener('click', toggleMenu);
    document.getElementById('share-button').addEventListener('click', shareCurrentView);
    document.getElementById('menu-panel').addEventListener('change', onLayerInputChange);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') setMenuOpen(false);
    });

    // Search
    const searchInput = document.getElementById('search-input');
    document.getElementById('search-form').addEventListener('submit', runSearch);
    searchInput.addEventListener('input', onSearchInput);
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && searchInput.value) {
            e.preventDefault();
            clearSearch({ focus: false });
            searchInput.blur();
        }
    });
    document.getElementById('search-clear').addEventListener('click', () => clearSearch());
}

// Initialize
async function init() {
    installScrollGuard();
    restorePanelState();
    createHoverPopup();
    setupEventListeners();
    registerServiceWorker();
    const shared = parseShareParams(window.location.search);
    const mapInit = initMap(shared).catch(error => console.error('Map failed to initialise:', error));

    try {
        const response = await fetch('data/forecasts.json');
        if (!response.ok) throw new Error('Failed to load forecast data');
        const data = await response.json();
        resortData = data.resorts;

        applyShareFilters(shared.filters);
        await mapInit; // markers need the map's source to exist
        createMarkers();
        applySharedSelection(shared);

        console.log(`Loaded ${resortData.length} resorts, generated at ${data.generated_at}`);
    } catch (error) {
        console.error('Error loading forecast data:', error);
        alert('Failed to load forecast data. Please run: poetry run powder --export-json');
    }
}

// Select a dropdown option only if it exists (a shared link may name a stale region)
function setSelectIfValid(id, value) {
    const el = document.getElementById(id);
    if (el && [...el.options].some(o => o.value === value)) el.value = value;
}

function applyShareFilters(filters) {
    if (filters.snow) setSelectIfValid('snow-filter', filters.snow);
}

// Open the shared resort's details; frame the resort if the link had no camera
function applySharedSelection(shared) {
    const resort = shared.resort ? resortData.find(r => r.name === shared.resort) : null;
    if (resort && shared.fly) {
        selectResort(resort); // flies in and starts its flyover (or just flies there if none)
        return;
    }
    if (!shared.camera && map && mapReady) {
        if (resort) {
            map.jumpTo({ center: [resort.longitude, resort.latitude], zoom: FOCUS_ZOOM });
        }
    }
    if (resort) showDetail(resort);
}

// Tile/asset cache: repeat visits and panning back over seen areas skip the network
function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    // Automated browsers and local development skip it (stale JS while editing is confusing
    // and cached tiles would leak between tests); ?sw=1 opts back in.
    const optIn = new URLSearchParams(window.location.search).has('sw');
    const isLocal = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
    if ((navigator.webdriver || isLocal) && !optIn) return;
    navigator.serviceWorker.register('sw.js').catch(e => console.debug('Service worker unavailable', e));
}

if (typeof module !== 'undefined' && module.exports) {
    // Test environment: expose logic without booting the app
    module.exports = {
        computeMinZoom, zoomScaleAt, buildRadiusExpression, resortToFeature,
        sanitizeLayerPrefs, loadLayerPrefs, saveLayerPrefs, isLayerVisible, getLayerGroup,
        buildLabelOverlayLayers, buildMapStyle, parseShareParams, buildShareUrl,
        nextPanelState, setPanelState, restorePanelState, searchResorts,
        showDetail, hideDetail, togglePanelCollapse, reopenPanel,
        filterInView, angularDistance, escapeHtml, setListMode, onSearchInput, clearSearch, renderList,
        getPanelState: () => panelState,
        getListMode: () => listMode,
        setResortData: (data) => { resortData = data; },
    };
} else {
    document.addEventListener('DOMContentLoaded', init);
}

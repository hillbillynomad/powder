// Powder service worker: caches map tiles and static assets so panning back over seen
// areas and repeat visits skip the network. Forecast data is always network-first.

const VERSION = 'v1';
const TILE_CACHE = `powder-tiles-${VERSION}`;
const SHELL_CACHE = `powder-shell-${VERSION}`;
const MAX_TILE_ENTRIES = 4000;
const TRIM_EVERY = 100; // puts between trims

const TILE_HOSTS = [
    'server.arcgisonline.com',
    's3.amazonaws.com', // elevation-tiles-prod terrarium DEM
    'tiles.openfreemap.org',
    'tile.opentopomap.org',
    'tiles.opensnowmap.org',
];
const STATIC_HOSTS = ['unpkg.com', 'cdn.jsdelivr.net'];

let putsSinceTrim = 0;

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const keep = new Set([TILE_CACHE, SHELL_CACHE]);
        for (const name of await caches.keys()) {
            if (name.startsWith('powder-') && !keep.has(name)) await caches.delete(name);
        }
        await self.clients.claim();
    })());
});

// Oldest entries first (Cache keys come back in insertion order)
async function trimCache(cache, max) {
    const keys = await cache.keys();
    for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function cacheFirst(request) {
    const cache = await caches.open(TILE_CACHE);
    const hit = await cache.match(request);
    if (hit) return hit;
    const response = await fetch(request);
    if (response.ok && response.status === 200) {
        cache.put(request, response.clone()).then(() => {
            if (++putsSinceTrim >= TRIM_EVERY) {
                putsSinceTrim = 0;
                return trimCache(cache, MAX_TILE_ENTRIES);
            }
        }).catch(() => { /* quota exceeded etc: caching is best-effort */ });
    }
    return response;
}

async function staleWhileRevalidate(request, cacheName) {
    const cache = await caches.open(cacheName);
    // Share links add a query string to the page URL; they all map to the same document
    const cached = await cache.match(request, { ignoreSearch: request.mode === 'navigate' });
    const refresh = fetch(request).then((response) => {
        if (response.ok) cache.put(request, response.clone()).catch(() => {});
        return response;
    });
    if (cached) {
        refresh.catch(() => {}); // revalidate quietly
        return cached;
    }
    return refresh;
}

async function networkFirst(request, cacheName) {
    const cache = await caches.open(cacheName);
    try {
        const response = await fetch(request);
        if (response.ok) cache.put(request, response.clone()).catch(() => {});
        return response;
    } catch (e) {
        const cached = await cache.match(request);
        if (cached) return cached;
        throw e;
    }
}

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;
    const url = new URL(request.url);

    if (TILE_HOSTS.includes(url.hostname)) {
        // The Liberty style JSON can change; tiles and fonts/sprites are safe to keep
        if (url.pathname.startsWith('/styles/')) {
            event.respondWith(networkFirst(request, SHELL_CACHE));
        } else {
            event.respondWith(cacheFirst(request));
        }
    } else if (url.origin === self.location.origin) {
        if (url.pathname.endsWith('.json')) {
            event.respondWith(networkFirst(request, SHELL_CACHE));
        } else {
            event.respondWith(staleWhileRevalidate(request, SHELL_CACHE));
        }
    } else if (STATIC_HOSTS.includes(url.hostname)) {
        event.respondWith(staleWhileRevalidate(request, SHELL_CACHE));
    }
});

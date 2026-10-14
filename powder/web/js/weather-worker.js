// Off-main-thread renderer for weather overlays (see weather.js): grid codes + colour LUT
// -> coloured Web Mercator PNG, so the page stays responsive while frames are drawn.
importScripts('weather.js');

const { mercatorLookup, renderCodes } = self.PowderWeather;
let cache = null; // { key, lookup, canvas } reused while the grid/size stay the same

self.onmessage = async (e) => {
    const { id, codes, grid, lut, size } = e.data;
    try {
        const key = `${grid.ni}x${grid.nj}@${size}`;
        if (!cache || cache.key !== key) {
            cache = { key, lookup: mercatorLookup(grid, size), canvas: new OffscreenCanvas(size, size) };
        }
        const image = new ImageData(size, size);
        renderCodes(codes, grid, lut, cache.lookup, image.data);
        cache.canvas.getContext('2d').putImageData(image, 0, 0);
        const blob = await cache.canvas.convertToBlob({ type: 'image/png' });
        self.postMessage({ id, blob });
    } catch (err) {
        self.postMessage({ id, error: String(err) });
    }
};

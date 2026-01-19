// Powder Web UI - Interactive Snowfall Map

const BUBBLE_COLOR = '#3b82f6';
const BUBBLE_FILL_OPACITY = 0.6;
const MIN_RADIUS = 5;  // Minimum radius for zero-snow resorts

let map;
let markers = [];
let resortData = [];

// Country code to name mapping
const COUNTRY_NAMES = {
    'AD': 'Andorra', 'AR': 'Argentina', 'AT': 'Austria', 'AU': 'Australia',
    'BG': 'Bulgaria', 'CA': 'Canada', 'CH': 'Switzerland', 'CL': 'Chile',
    'CZ': 'Czech Republic', 'DE': 'Germany', 'ES': 'Spain', 'FI': 'Finland',
    'FR': 'France', 'IT': 'Italy', 'JP': 'Japan', 'KR': 'South Korea',
    'NO': 'Norway', 'NZ': 'New Zealand', 'PL': 'Poland', 'RO': 'Romania',
    'SE': 'Sweden', 'SI': 'Slovenia', 'SK': 'Slovakia', 'US': 'United States'
};

// Initialize the map
function initMap() {
    map = L.map('map', {
        minZoom: 2,
        maxBoundsViscosity: 1.0,
        maxBounds: [[-90, -180], [90, 180]],
        zoomControl: false  // Disable default zoom control
    }).setView([30, 0], 2);  // World view

    // Add zoom control to top-right
    L.control.zoom({ position: 'topright' }).addTo(map);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 18,
    }).addTo(map);
}

// Calculate bubble radius based on total snowfall
function getRadius(totalInches) {
    if (totalInches <= 0) return MIN_RADIUS;
    return MIN_RADIUS + (totalInches / 2);
}

// Get snowfall value based on current filter selection
function getSnowfallForFilter(resort) {
    const filter = document.getElementById('snow-filter').value;
    switch (filter) {
        case 'forecast':
            return resort.total_snowfall_inches || 0;
        case 'historical':
            return resort.total_historical_inches || 0;
        case 'total':
            return (resort.total_snowfall_inches || 0) + (resort.total_historical_inches || 0);
        default:
            return resort.total_snowfall_inches || 0;
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

// Build tooltip content (basic info on hover)
function buildTooltip(resort) {
    const snowfall = getSnowfallForFilter(resort);
    const label = getFilterLabel();
    const region = resort.region || resort.state || '';
    const countryName = getCountryName(resort.country);
    const location = region ? `${region}, ${countryName}` : countryName;
    return `
        <div class="tooltip-name">${resort.name}</div>
        <div class="tooltip-info">${location} | ${resort.elevation_ft.toLocaleString()}' elev</div>
        <div class="tooltip-total">${label}: ${snowfall.toFixed(1)}"</div>
    `;
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

// Build detail panel content (full info on click)
function buildDetailContent(resort) {
    const passDisplay = resort.pass_type || 'Independent';
    const filter = document.getElementById('snow-filter').value;
    const displaySnowfall = getSnowfallForFilter(resort);
    const displayLabel = getFilterLabel() + ' Snowfall';
    const region = resort.region || resort.state || '';
    const countryName = getCountryName(resort.country);

    // Get dynamic sources from the forecast data
    const sources = getSourcesFromForecasts(resort.daily_forecasts || []);
    const sourceHeaders = sources.map(s => `<th>${s}</th>`).join('');
    const numSourceCols = sources.length || 1;

    // Build historical rows if showing historical or total
    let historicalRows = '';
    if ((filter === 'historical' || filter === 'total') && resort.historical_snowfall) {
        if (filter === 'total') {
            historicalRows = `<tr class="section-header"><td colspan="${2 + numSourceCols}">Recent Snowfall (Past 14 Days)</td></tr>`;
        }
        for (const day of resort.historical_snowfall) {
            historicalRows += `
                <tr class="historical">
                    <td class="date">${formatDate(day.date)}</td>
                    <td class="avg">${day.snowfall_inches}"</td>
                    <td class="source" colspan="${numSourceCols}">Archive</td>
                </tr>
            `;
        }
    }

    // Build forecast rows if showing forecast or total
    let forecastRows = '';
    if (filter === 'forecast' || filter === 'total') {
        if (filter === 'total') {
            forecastRows = `<tr class="section-header"><td colspan="${2 + numSourceCols}">Upcoming Forecast</td></tr>`;
        }
        for (const day of resort.daily_forecasts || []) {
            const sourceCells = sources.map(s => {
                const val = day.sources && day.sources[s] !== undefined ? day.sources[s] : '-';
                return `<td class="source">${val !== '-' ? val + '"' : val}</td>`;
            }).join('');
            forecastRows += `
                <tr>
                    <td class="date">${formatDate(day.date)}</td>
                    <td class="avg">${day.avg_inches}"</td>
                    ${sourceCells}
                </tr>
            `;
        }
    }

    return `
        <div class="detail-header">
            <h2>${resort.name}</h2>
            <div class="detail-meta">
                <span>${region}${region ? ', ' : ''}${countryName}</span>
                <span>${resort.elevation_ft.toLocaleString()}' elevation</span>
                <span>${passDisplay}</span>
            </div>
        </div>
        <div class="detail-total">
            <div class="value">${displaySnowfall.toFixed(1)}"</div>
            <div class="label">${displayLabel}</div>
        </div>
        <table class="forecast-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Snow</th>
                    ${sourceHeaders}
                </tr>
            </thead>
            <tbody>
                ${historicalRows}
                ${forecastRows}
            </tbody>
        </table>
    `;
}

// Show detail panel for a resort
function showDetail(resort) {
    const panel = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');
    content.innerHTML = buildDetailContent(resort);
    panel.classList.remove('hidden');
    panel.classList.add('visible');
}

// Hide detail panel
function hideDetail() {
    const panel = document.getElementById('detail-panel');
    panel.classList.remove('visible');
    panel.classList.add('hidden');
}

// Center map on resort and open detail panel
function focusResort(resort) {
    map.setView([resort.latitude, resort.longitude], 10);
    showDetail(resort);
}

// Get filtered resorts based on current filters
function getFilteredResorts() {
    const countryFilter = document.getElementById('country-filter').value;
    const regionFilter = document.getElementById('region-filter').value;
    const passFilter = document.getElementById('pass-filter').value;

    return resortData.filter(resort => {
        if (countryFilter && resort.country !== countryFilter) return false;
        const region = resort.region || resort.state || '';
        if (regionFilter && region !== regionFilter) return false;
        if (passFilter === 'none' && resort.pass_type) return false;
        if (passFilter && passFilter !== 'none' && resort.pass_type !== passFilter) return false;
        return true;
    });
}

// Update Top 10 sidebar
function updateTop10() {
    const filtered = getFilteredResorts();

    // Sort by snowfall based on current filter
    const sorted = [...filtered].sort((a, b) => {
        return getSnowfallForFilter(b) - getSnowfallForFilter(a);
    });

    const top10 = sorted.slice(0, 10);
    const container = document.getElementById('top-resorts-list');
    container.innerHTML = '';

    top10.forEach((resort, index) => {
        const snowfall = getSnowfallForFilter(resort);
        const region = resort.region || resort.state || '';
        const countryName = getCountryName(resort.country);

        const item = document.createElement('div');
        item.className = 'top-resort-item';
        item.innerHTML = `
            <div class="rank">#${index + 1}</div>
            <div class="name">${resort.name}</div>
            <div class="info">
                <span>${region ? region + ', ' : ''}${countryName}</span>
                <span class="snowfall">${snowfall.toFixed(1)}"</span>
            </div>
        `;
        item.addEventListener('click', () => focusResort(resort));
        container.appendChild(item);
    });
}

// Create markers for all resorts
function createMarkers() {
    // Clear existing markers
    markers.forEach(m => map.removeLayer(m.marker));
    markers = [];

    const filtered = getFilteredResorts();

    for (const resort of filtered) {
        const snowfall = getSnowfallForFilter(resort);
        const radius = getRadius(snowfall);

        const marker = L.circleMarker([resort.latitude, resort.longitude], {
            radius: radius,
            fillColor: BUBBLE_COLOR,
            fillOpacity: BUBBLE_FILL_OPACITY,
            color: BUBBLE_COLOR,
            weight: 2,
        });

        marker.bindTooltip(buildTooltip(resort), {
            direction: 'top',
            offset: [0, -radius],
        });

        marker.on('click', () => showDetail(resort));

        marker.addTo(map);
        markers.push({ marker, resort });
    }

    // Update Top 10 sidebar when markers change
    updateTop10();
}

// Populate country filter dropdown
function populateCountryFilter() {
    const countries = [...new Set(resortData.map(r => r.country))].sort();
    const select = document.getElementById('country-filter');

    // Clear existing options except "All Countries"
    select.innerHTML = '<option value="">All Countries</option>';

    for (const country of countries) {
        const option = document.createElement('option');
        option.value = country;
        option.textContent = getCountryName(country);
        select.appendChild(option);
    }
}

// Populate region filter dropdown based on selected country
function populateRegionFilter() {
    const countryFilter = document.getElementById('country-filter').value;
    const select = document.getElementById('region-filter');

    // Clear existing options
    select.innerHTML = '<option value="">All Regions</option>';

    let regions;
    if (countryFilter) {
        // Only regions for selected country
        regions = [...new Set(
            resortData
                .filter(r => r.country === countryFilter)
                .map(r => r.region || r.state || '')
                .filter(r => r)
        )].sort();
    } else {
        // All regions
        regions = [...new Set(
            resortData
                .map(r => r.region || r.state || '')
                .filter(r => r)
        )].sort();
    }

    for (const region of regions) {
        const option = document.createElement('option');
        option.value = region;
        option.textContent = region;
        select.appendChild(option);
    }
}

// Handle country filter change
function onCountryChange() {
    populateRegionFilter();
    createMarkers();

    // Fit map to selected country's resorts
    const countryFilter = document.getElementById('country-filter').value;
    if (countryFilter) {
        const countryResorts = resortData.filter(r => r.country === countryFilter);
        if (countryResorts.length > 0) {
            const bounds = L.latLngBounds(
                countryResorts.map(r => [r.latitude, r.longitude])
            );
            map.fitBounds(bounds, { padding: [50, 50] });
        }
    } else {
        // Reset to world view
        map.setView([30, 0], 2);
    }
}

// Set up event listeners
function setupEventListeners() {
    document.getElementById('country-filter').addEventListener('change', onCountryChange);
    document.getElementById('region-filter').addEventListener('change', createMarkers);
    document.getElementById('pass-filter').addEventListener('change', createMarkers);
    document.getElementById('snow-filter').addEventListener('change', createMarkers);
    document.getElementById('close-panel').addEventListener('click', hideDetail);

    // Close panel when clicking outside
    document.getElementById('map').addEventListener('click', (e) => {
        // Only close if clicking on the map itself, not a marker
        if (e.target.classList.contains('leaflet-container') ||
            e.target.classList.contains('leaflet-tile')) {
            hideDetail();
        }
    });
}

// Load forecast data and initialize
async function init() {
    initMap();
    setupEventListeners();

    try {
        const response = await fetch('data/forecasts.json');
        if (!response.ok) {
            throw new Error('Failed to load forecast data');
        }
        const data = await response.json();
        resortData = data.resorts;

        populateCountryFilter();
        populateRegionFilter();
        createMarkers();

        console.log(`Loaded ${resortData.length} resorts, generated at ${data.generated_at}`);
    } catch (error) {
        console.error('Error loading forecast data:', error);
        alert('Failed to load forecast data. Please run: poetry run powder --export-json');
    }
}

// Start the app
document.addEventListener('DOMContentLoaded', init);

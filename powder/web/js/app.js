// Powder Web UI - Interactive Snowfall Map

const BUBBLE_COLOR = '#3b82f6';
const BUBBLE_FILL_OPACITY = 0.6;
const MIN_RADIUS = 5;  // Minimum radius for zero-snow resorts

let map;
let markers = [];
let resortData = [];

// Initialize the map
function initMap() {
    map = L.map('map').setView([39.5, -98.5], 4);

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

// Build tooltip content (basic info on hover)
function buildTooltip(resort) {
    const snowfall = getSnowfallForFilter(resort);
    const label = getFilterLabel();
    return `
        <div class="tooltip-name">${resort.name}</div>
        <div class="tooltip-info">${resort.state} | ${resort.elevation_ft.toLocaleString()}' elev</div>
        <div class="tooltip-total">${label}: ${snowfall.toFixed(1)}"</div>
    `;
}

// Build detail panel content (full info on click)
function buildDetailContent(resort) {
    const passDisplay = resort.pass_type || 'Independent';
    const filter = document.getElementById('snow-filter').value;
    const displaySnowfall = getSnowfallForFilter(resort);
    const displayLabel = getFilterLabel() + ' Snowfall';

    // Build historical rows if showing historical or total
    let historicalRows = '';
    if ((filter === 'historical' || filter === 'total') && resort.historical_snowfall) {
        if (filter === 'total') {
            historicalRows = '<tr class="section-header"><td colspan="5">Recent Snowfall (Past 14 Days)</td></tr>';
        }
        for (const day of resort.historical_snowfall) {
            historicalRows += `
                <tr class="historical">
                    <td class="date">${formatDate(day.date)}</td>
                    <td class="avg">${day.snowfall_inches}"</td>
                    <td class="source" colspan="3">Archive</td>
                </tr>
            `;
        }
    }

    // Build forecast rows if showing forecast or total
    let forecastRows = '';
    if (filter === 'forecast' || filter === 'total') {
        if (filter === 'total') {
            forecastRows = '<tr class="section-header"><td colspan="5">Upcoming Forecast</td></tr>';
        }
        for (const day of resort.daily_forecasts) {
            forecastRows += `
                <tr>
                    <td class="date">${formatDate(day.date)}</td>
                    <td class="avg">${day.avg_inches}"</td>
                    <td class="source">${day.sources['Open-Meteo']}"</td>
                    <td class="source">${day.sources['NWS']}"</td>
                    <td class="source">${day.sources['ECMWF']}"</td>
                </tr>
            `;
        }
    }

    return `
        <div class="detail-header">
            <h2>${resort.name}</h2>
            <div class="detail-meta">
                <span>${resort.state}</span>
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
                    <th>GFS</th>
                    <th>NWS</th>
                    <th>ECMWF</th>
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

// Create markers for all resorts
function createMarkers() {
    // Clear existing markers
    markers.forEach(m => map.removeLayer(m.marker));
    markers = [];

    const stateFilter = document.getElementById('state-filter').value;
    const passFilter = document.getElementById('pass-filter').value;

    for (const resort of resortData) {
        // Apply filters
        if (stateFilter && resort.state !== stateFilter) continue;
        if (passFilter === 'none' && resort.pass_type) continue;
        if (passFilter && passFilter !== 'none' && resort.pass_type !== passFilter) continue;

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
}

// Populate state filter dropdown
function populateStateFilter() {
    const states = [...new Set(resortData.map(r => r.state))].sort();
    const select = document.getElementById('state-filter');

    for (const state of states) {
        const option = document.createElement('option');
        option.value = state;
        option.textContent = state;
        select.appendChild(option);
    }
}

// Set up event listeners
function setupEventListeners() {
    document.getElementById('state-filter').addEventListener('change', createMarkers);
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

        populateStateFilter();
        createMarkers();

        console.log(`Loaded ${resortData.length} resorts, generated at ${data.generated_at}`);
    } catch (error) {
        console.error('Error loading forecast data:', error);
        alert('Failed to load forecast data. Please run: poetry run powder --export-json');
    }
}

// Start the app
document.addEventListener('DOMContentLoaded', init);

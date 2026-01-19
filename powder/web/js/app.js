// Powder Web UI - Interactive Snowfall Map

const BUBBLE_COLOR = '#3b82f6';
const BUBBLE_FILL_OPACITY = 0.6;
const MIN_RADIUS = 5;

// Touch device detection - skip hover popups on mobile
const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

let map;
let markers = [];
let resortData = [];
let currentDetailResort = null;

// Hover popup state
let hoverPopup = null;
let hoverPopupChart = null;
let hoverHideTimeout = null;
let currentHoverResort = null;
const HOVER_HIDE_DELAY = 150;

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
        zoomControl: false
    }).setView([30, 0], 2);

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
        yaxis: { show: false, min: 0 },
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

// Build hover popup content
function buildHoverPopupContent(resort) {
    const snowfall = getSnowfallForFilter(resort);
    const label = getFilterLabel();
    const region = resort.region || resort.state || '';
    const countryName = getCountryName(resort.country);
    const location = region ? `${region}, ${countryName}` : countryName;
    const lifts = resort.lift_count ? `${resort.lift_count} lifts` : '';
    const originalSnowfallText = `${label}: ${snowfall.toFixed(1)}"`;
    
    return `
        <div class="hover-popup-header">
            <h3 class="hover-popup-name">${resort.name}</h3>
            <div class="hover-popup-meta">${location} | ${resort.elevation_ft.toLocaleString()}' elev${lifts ? ' | ' + lifts : ''}</div>
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
function showHoverPopup(resort, marker) {
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
    positionHoverPopup(marker);
    renderHoverPopupChart(resort);
}

// Position hover popup relative to marker
function positionHoverPopup(marker) {
    const point = map.latLngToContainerPoint(marker.getLatLng());
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

    return `
        <div class="detail-header">
            <h2>${resort.name}</h2>
            <div class="detail-meta">
                <span>${region}${region ? ', ' : ''}${countryName}</span>
                <span>${resort.elevation_ft.toLocaleString()}' elevation</span>
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

// Show detail panel for a resort
function showDetail(resort) {
    document.getElementById('detail-content').innerHTML = buildDetailContent(resort);
    switchPanelTab('details');
    document.getElementById('side-panel').classList.remove('collapsed');
    currentDetailResort = resort;
    
    requestAnimationFrame(() => {
        requestAnimationFrame(() => renderDetailChart(resort));
    });
}

// Hide detail panel
function hideDetail() {
    document.getElementById('side-panel').classList.add('collapsed');
    switchPanelTab('top10');
    currentDetailResort = null;
}

// Toggle detail for a resort
function toggleDetail(resort) {
    if (currentDetailResort && currentDetailResort.name === resort.name) {
        hideDetail();
        return;
    }
    showDetail(resort);
}

// Switch panel tab
function switchPanelTab(tabName) {
    document.querySelectorAll('.panel-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    document.getElementById('top10-content').classList.toggle('hidden', tabName !== 'top10');
    document.getElementById('details-content').classList.toggle('hidden', tabName !== 'details');
}

// Toggle filter drawer
function toggleFilterDrawer() {
    const drawer = document.getElementById('filter-drawer');
    drawer.classList.toggle('visible');
    drawer.classList.toggle('hidden');
}

// Update filter badge count
function updateFilterBadge() {
    let count = 0;
    if (document.getElementById('country-filter').value) count++;
    if (document.getElementById('region-filter').value) count++;
    if (document.getElementById('pass-filter').value) count++;

    const badge = document.getElementById('filter-badge');
    if (count > 0) {
        badge.textContent = count;
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

// Center map on resort and open detail panel
function focusResort(resort) {
    map.setView([resort.latitude, resort.longitude], 10);
    toggleDetail(resort);
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

// Update Top 10 list
function updateTop10() {
    const filtered = getFilteredResorts();
    const sorted = [...filtered].sort((a, b) => getSnowfallForFilter(b) - getSnowfallForFilter(a));
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
    markers.forEach(m => map.removeLayer(m.marker));
    markers = [];
    hideHoverPopup();

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

        // Only add hover events on non-touch devices
        if (!isTouchDevice) {
            marker.on('mouseover', () => showHoverPopup(resort, marker));
            marker.on('mouseout', () => scheduleHideHoverPopup());
        }
        
        marker.on('click', () => {
            if (isTouchDevice) {
                hideHoverPopup(); // Ensure hover popup is hidden on touch devices
            }
            toggleDetail(resort);
        });

        marker.addTo(map);
        markers.push({ marker, resort });
    }

    updateTop10();
    updateFilterBadge();
}

// Populate filter dropdown
function populateFilter(selector, options, allLabel) {
    document.querySelectorAll(selector).forEach(select => {
        select.innerHTML = `<option value="">${allLabel}</option>`;
        options.forEach(opt => {
            const option = document.createElement('option');
            option.value = opt.value;
            option.textContent = opt.label;
            select.appendChild(option);
        });
    });
}

// Populate country filter
function populateCountryFilter() {
    const countries = [...new Set(resortData.map(r => r.country))].sort();
    const options = countries.map(c => ({ value: c, label: getCountryName(c) }));
    populateFilter('.country-filter', options, 'All Countries');
}

// Populate region filter based on selected country
function populateRegionFilter() {
    const countryFilter = document.getElementById('country-filter').value;
    const filtered = countryFilter 
        ? resortData.filter(r => r.country === countryFilter)
        : resortData;
    
    const regions = [...new Set(
        filtered.map(r => r.region || r.state || '').filter(r => r)
    )].sort();
    
    const options = regions.map(r => ({ value: r, label: r }));
    populateFilter('.region-filter', options, 'All Regions');
}

// Handle country filter change
function onCountryChange() {
    populateRegionFilter();
    createMarkers();

    const countryFilter = document.getElementById('country-filter').value;
    if (countryFilter) {
        const countryResorts = resortData.filter(r => r.country === countryFilter);
        if (countryResorts.length > 0) {
            const bounds = L.latLngBounds(countryResorts.map(r => [r.latitude, r.longitude]));
            map.fitBounds(bounds, { padding: [50, 50] });
        }
    } else {
        map.setView([30, 0], 2);
    }
}

// Handle other filter changes
function onFilterChange() {
    createMarkers();
}

// Toggle panel collapse
function togglePanelCollapse() {
    document.getElementById('side-panel').classList.toggle('collapsed');
}

// Set up event listeners
function setupEventListeners() {
    // Filter listeners
    document.getElementById('country-filter').addEventListener('change', onCountryChange);
    document.getElementById('region-filter').addEventListener('change', onFilterChange);
    document.getElementById('pass-filter').addEventListener('change', onFilterChange);
    document.getElementById('snow-filter').addEventListener('change', onFilterChange);

    // Panel tab listeners
    document.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => switchPanelTab(tab.dataset.tab));
    });

    // Controls
    document.getElementById('panel-collapse').addEventListener('click', togglePanelCollapse);
    document.getElementById('menu-toggle').addEventListener('click', toggleFilterDrawer);

    // Close details when clicking on map
    map.on('click', (e) => {
        if (e.originalEvent.target.classList.contains('leaflet-container') ||
            e.originalEvent.target.classList.contains('leaflet-tile-pane') ||
            e.originalEvent.target.classList.contains('leaflet-tile')) {
            hideDetail();
        }
    });
}

// Initialize
async function init() {
    initMap();
    createHoverPopup();
    setupEventListeners();

    try {
        const response = await fetch('data/forecasts.json');
        if (!response.ok) throw new Error('Failed to load forecast data');
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

document.addEventListener('DOMContentLoaded', init);

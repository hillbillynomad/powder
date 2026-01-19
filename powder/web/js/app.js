// Powder Web UI - Interactive Snowfall Map

const BUBBLE_COLOR = '#3b82f6';
const BUBBLE_FILL_OPACITY = 0.6;
const MIN_RADIUS = 5;  // Minimum radius for zero-snow resorts

let map;
let markers = [];
let resortData = [];
let currentDetailResort = null;  // Track currently displayed resort for toggle behavior
let isMobile = false;  // Track if we're in mobile view

// Hover popup state
let hoverPopup = null;
let hoverPopupChart = null;
let hoverHideTimeout = null;
let currentHoverResort = null;
const HOVER_HIDE_DELAY = 150;  // ms delay before hiding popup

// Country code to name mapping
const COUNTRY_NAMES = {
    'AD': 'Andorra', 'AR': 'Argentina', 'AT': 'Austria', 'AU': 'Australia',
    'BG': 'Bulgaria', 'CA': 'Canada', 'CH': 'Switzerland', 'CL': 'Chile',
    'CZ': 'Czech Republic', 'DE': 'Germany', 'ES': 'Spain', 'FI': 'Finland',
    'FR': 'France', 'IT': 'Italy', 'JP': 'Japan', 'KR': 'South Korea',
    'NO': 'Norway', 'NZ': 'New Zealand', 'PL': 'Poland', 'RO': 'Romania',
    'SE': 'Sweden', 'SI': 'Slovenia', 'SK': 'Slovakia', 'US': 'United States'
};

// Check if we're in mobile view
function checkMobile() {
    isMobile = window.innerWidth <= 900;
    return isMobile;
}

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
    const filter = getFilterValue('snow-filter');
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

// Get filter value (works for both desktop and mobile)
function getFilterValue(filterClass) {
    const desktopEl = document.getElementById(filterClass);
    const mobileEl = document.getElementById('mobile-' + filterClass);

    // Use desktop value if visible, otherwise mobile
    if (desktopEl && window.getComputedStyle(desktopEl.closest('.desktop-controls') || desktopEl).display !== 'none') {
        return desktopEl.value;
    }
    return mobileEl ? mobileEl.value : (desktopEl ? desktopEl.value : '');
}

// Get display label for the current filter
function getFilterLabel() {
    const filter = getFilterValue('snow-filter');
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
// Returns negative if date1 is before date2, positive if after
function daysBetween(date1, date2) {
    const d1 = new Date(date1 + 'T00:00:00');
    const d2 = new Date(date2 + 'T00:00:00');
    const diffTime = d1 - d2;
    return Math.round(diffTime / (1000 * 60 * 60 * 24));
}

// Get cumulative snowfall data for mini-graph
// Returns array of {date, dayOffset, daily, cumulative} sorted chronologically
function getCumulativeChartData(resort) {
    const today = new Date().toISOString().split('T')[0];
    
    // Collect all daily values
    const allDays = [];
    
    for (const h of resort.historical_snowfall || []) {
        allDays.push({ date: h.date, value: h.snowfall_inches || 0 });
    }
    for (const f of resort.daily_forecasts || []) {
        allDays.push({ date: f.date, value: f.avg_inches || 0 });
    }
    
    // Sort chronologically
    allDays.sort((a, b) => a.date.localeCompare(b.date));
    
    // Build cumulative values
    const points = [];
    let cumulative = 0;
    for (const day of allDays) {
        cumulative += day.value;
        points.push({
            date: day.date,
            dayOffset: daysBetween(day.date, today),
            daily: day.value,      // Daily snowfall for this day
            cumulative: cumulative
        });
    }
    
    return points;
}

// ApexCharts configuration for snowfall graphs
function getChartConfig(data, options = {}) {
    const { width = 280, height = 100, interactive = true, onDataPointHover = null, onMouseLeave = null } = options;
    
    // Convert data to ApexCharts format with timestamps
    const seriesData = data.map(d => ({
        x: new Date(d.date + 'T00:00:00').getTime(),
        y: d.cumulative,
        daily: d.daily
    }));
    
    return {
        series: [{
            name: 'Cumulative Snow',
            data: seriesData
        }],
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
                mouseLeave: function() {
                    if (onMouseLeave) onMouseLeave();
                }
            }
        },
        theme: { mode: 'dark' },
        colors: ['#3b82f6'],
        fill: {
            type: 'solid',
            opacity: 0.4
        },
        stroke: { curve: 'straight', width: 2 },
        markers: {
            size: 0,  // Hidden by default
            hover: { size: 5 }  // Show on hover
        },
        dataLabels: { enabled: false },
        xaxis: {
            type: 'datetime',
            labels: { 
                style: { colors: '#888', fontSize: '9px' },
                datetimeUTC: false,
                datetimeFormatter: {
                    day: 'MMM dd'
                }
            },
            axisBorder: { show: true, color: '#333' },
            axisTicks: { show: true, color: '#333' },
            crosshairs: { 
                show: interactive,
                stroke: { color: '#fff', width: 1, dashArray: 3 }
            },
            tooltip: { enabled: false }  // Disable the black x-axis tooltip
        },
        yaxis: { 
            show: false,
            min: 0
        },
        grid: { 
            show: false,
            padding: { left: 0, right: 0, top: 0, bottom: 0 }
        },
        tooltip: {
            enabled: interactive,
            shared: true,
            intersect: false,
            custom: function({ series, seriesIndex, dataPointIndex, w }) {
                // Update the snowfall line with hover data
                if (onDataPointHover && dataPointIndex >= 0) {
                    const point = seriesData[dataPointIndex];
                    onDataPointHover(point);
                }
                return '<div style="display:none"></div>';  // Hidden tooltip element
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
                    style: { 
                        color: '#fff', 
                        background: 'transparent',
                        fontSize: '9px',
                        fontWeight: 600
                    },
                    position: 'bottom',
                    offsetY: 15
                }
            }]
        }
    };
}

// Render ApexCharts mini graph in tooltip container
function renderMiniChart(container, resort) {
    if (!container || container.dataset.rendered) return;
    
    const data = getCumulativeChartData(resort);
    if (data.length === 0) return;
    
    const chart = new ApexCharts(container, getChartConfig(data, {
        width: 200,
        height: 70,
        interactive: false
    }));
    chart.render();
    container.dataset.rendered = 'true';
}

// Render ApexCharts detail graph in detail panel
let detailChart = null;
function renderDetailChart(resort) {
    const container = document.getElementById('detail-chart-container');
    if (!container) return;
    
    // Destroy existing chart if any
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

// Build hover popup content (with interactive chart)
function buildHoverPopupContent(resort) {
    const snowfall = getSnowfallForFilter(resort);
    const label = getFilterLabel();
    const region = resort.region || resort.state || '';
    const countryName = getCountryName(resort.country);
    const location = region ? `${region}, ${countryName}` : countryName;
    const lifts = resort.lift_count ? `${resort.lift_count} lifts` : '';
    
    // Store original snowfall text for restoration
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

// Create and initialize the hover popup element
function createHoverPopup() {
    if (hoverPopup) return;
    
    hoverPopup = document.createElement('div');
    hoverPopup.id = 'hover-popup';
    hoverPopup.className = 'hover-popup';
    hoverPopup.style.display = 'none';
    
    // Hover intent: keep popup visible when mouse enters it
    hoverPopup.addEventListener('mouseenter', () => {
        if (hoverHideTimeout) {
            clearTimeout(hoverHideTimeout);
            hoverHideTimeout = null;
        }
    });
    
    // Hide popup when mouse leaves it
    hoverPopup.addEventListener('mouseleave', () => {
        hideHoverPopup();
    });
    
    document.body.appendChild(hoverPopup);
}

// Show hover popup for a resort at the marker position
function showHoverPopup(resort, marker) {
    if (isMobile) return;  // Don't show hover popup on mobile
    
    // Cancel any pending hide
    if (hoverHideTimeout) {
        clearTimeout(hoverHideTimeout);
        hoverHideTimeout = null;
    }
    
    // If same resort, just ensure it's visible
    if (currentHoverResort && currentHoverResort.name === resort.name) {
        hoverPopup.style.display = 'block';
        return;
    }
    
    currentHoverResort = resort;
    
    // Update content
    hoverPopup.innerHTML = buildHoverPopupContent(resort);
    hoverPopup.style.display = 'block';
    
    // Position popup near the marker
    positionHoverPopup(marker);
    
    // Render interactive chart
    renderHoverPopupChart(resort);
}

// Position the hover popup relative to the marker
function positionHoverPopup(marker) {
    const point = map.latLngToContainerPoint(marker.getLatLng());
    const mapContainer = document.getElementById('map');
    const mapRect = mapContainer.getBoundingClientRect();
    
    // Calculate popup position (above and to the right of marker)
    const popupWidth = 300;
    const popupHeight = 220;  // Taller to accommodate fixed tooltip below chart
    
    let left = mapRect.left + point.x + 15;
    let top = mapRect.top + point.y - popupHeight - 10;
    
    // Adjust if popup would go off screen
    if (left + popupWidth > window.innerWidth) {
        left = mapRect.left + point.x - popupWidth - 15;
    }
    if (top < 0) {
        top = mapRect.top + point.y + 20;
    }
    
    hoverPopup.style.left = `${left}px`;
    hoverPopup.style.top = `${top}px`;
}

// Generic function to update chart snowfall info display
function updateChartSnowfallInfo(elementId, point) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    const date = new Date(point.x);
    const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const today = new Date().toDateString();
    const isToday = date.toDateString() === today;
    const label = isToday ? 'Today' : dateStr;
    
    el.innerHTML = `<span class="hover-date">${label}</span> <span class="hover-daily">Daily: ${point.daily.toFixed(1)}"</span> <span class="hover-total">Total: ${point.y.toFixed(1)}"</span>`;
}

// Generic function to restore chart snowfall info to original value
function restoreChartSnowfallInfo(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    const original = el.dataset.original;
    if (original) {
        el.textContent = original;
    }
}

// Update hover popup snowfall line with interactive data
function updateHoverPopupSnowfall(point) {
    updateChartSnowfallInfo('hover-popup-snowfall', point);
}

// Restore hover popup snowfall line to original value
function restoreHoverPopupSnowfall() {
    restoreChartSnowfallInfo('hover-popup-snowfall');
}

// Update detail panel snowfall line with interactive data
function updateDetailSnowfall(point) {
    updateChartSnowfallInfo('detail-chart-info', point);
}

// Restore detail panel snowfall line to original value
function restoreDetailSnowfall() {
    restoreChartSnowfallInfo('detail-chart-info');
}

// Render interactive chart in hover popup
function renderHoverPopupChart(resort) {
    const container = document.getElementById('hover-popup-chart');
    if (!container) return;
    
    // Destroy existing chart
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

// Schedule hiding the hover popup (with delay for hover intent)
function scheduleHideHoverPopup() {
    if (hoverHideTimeout) {
        clearTimeout(hoverHideTimeout);
    }
    hoverHideTimeout = setTimeout(() => {
        hideHoverPopup();
    }, HOVER_HIDE_DELAY);
}

// Hide the hover popup immediately
function hideHoverPopup() {
    if (hoverHideTimeout) {
        clearTimeout(hoverHideTimeout);
        hoverHideTimeout = null;
    }
    
    if (hoverPopup) {
        hoverPopup.style.display = 'none';
    }
    
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

// Build detail panel content (full info on click)
function buildDetailContent(resort) {
    const passDisplay = resort.pass_type || 'Independent';
    const filter = getFilterValue('snow-filter');
    const displaySnowfall = getSnowfallForFilter(resort);
    const displayLabel = getFilterLabel() + ' Snowfall';
    const region = resort.region || resort.state || '';
    const countryName = getCountryName(resort.country);
    const lifts = resort.lift_count ? `${resort.lift_count} lifts` : '';

    // Get dynamic sources from the forecast data
    const sources = getSourcesFromForecasts(resort.daily_forecasts || []);
    const sourceHeaders = sources.map(s => `<th>${s}</th>`).join('');
    const numSourceCols = sources.length || 1;

    // Build forecast rows if showing forecast or total (sorted descending - future first)
    let forecastRows = '';
    if (filter === 'forecast' || filter === 'total') {
        if (filter === 'total') {
            forecastRows = `<tr class="section-header"><td colspan="${2 + numSourceCols}">Upcoming Forecast</td></tr>`;
        }
        // Sort descending (furthest future first, then toward today)
        const sortedForecasts = [...(resort.daily_forecasts || [])].sort((a, b) => b.date.localeCompare(a.date));
        for (const day of sortedForecasts) {
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

    // Build historical rows if showing historical or total (sorted descending - most recent first)
    let historicalRows = '';
    if ((filter === 'historical' || filter === 'total') && resort.historical_snowfall) {
        if (filter === 'total') {
            historicalRows = `<tr class="section-header"><td colspan="${2 + numSourceCols}">Recent Snowfall (Past 14 Days)</td></tr>`;
        }
        // Sort descending (most recent first, going back in time)
        const sortedHistorical = [...resort.historical_snowfall].sort((a, b) => b.date.localeCompare(a.date));
        for (const day of sortedHistorical) {
            historicalRows += `
                <tr class="historical">
                    <td class="date">${formatDate(day.date)}</td>
                    <td class="avg">${day.snowfall_inches}"</td>
                    <td class="source" colspan="${numSourceCols}">Archive</td>
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
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Snow</th>
                    ${sourceHeaders}
                </tr>
            </thead>
            <tbody>
                ${forecastRows}
                ${historicalRows}
            </tbody>
        </table>
    `;
}

// Show detail panel for a resort (desktop)
function showDesktopDetail(resort) {
    const content = document.getElementById('detail-content');
    content.innerHTML = buildDetailContent(resort);

    // Switch to details tab
    switchPanelTab('details');

    // Ensure panel is not collapsed
    const panel = document.getElementById('side-panel');
    panel.classList.remove('collapsed');

    currentDetailResort = resort;

    // Render interactive chart after DOM is updated and panel is visible
    // Use requestAnimationFrame to ensure container dimensions are available
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            renderDetailChart(resort);
        });
    });
}

// Hide detail panel (desktop) - collapse panel and switch back to Top 10
function hideDesktopDetail() {
    const panel = document.getElementById('side-panel');
    panel.classList.add('collapsed');
    switchPanelTab('top10');
    currentDetailResort = null;
}

// Show detail panel for a resort (mobile)
function showMobileDetail(resort) {
    let panel = document.getElementById('mobile-detail-panel');

    if (!panel) {
        // Create mobile detail panel if it doesn't exist
        createMobileDetailPanel();
        panel = document.getElementById('mobile-detail-panel');
    }

    document.getElementById('mobile-detail-content').innerHTML = buildDetailContent(resort);
    panel.classList.add('visible');
    
    currentDetailResort = resort;
    
    // Render interactive chart after DOM is updated and panel is visible
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            renderDetailChart(resort);
        });
    });
}

// Create mobile detail panel dynamically
function createMobileDetailPanel() {
    const panel = document.createElement('div');
    panel.id = 'mobile-detail-panel';
    panel.className = 'mobile-detail-panel';
    panel.innerHTML = `
        <div class="mobile-detail-header">
            <span>Resort Details</span>
            <button class="mobile-detail-close" id="mobile-detail-close">&times;</button>
        </div>
        <div class="mobile-detail-content" id="mobile-detail-content"></div>
    `;
    document.body.appendChild(panel);

    // Add close handler
    document.getElementById('mobile-detail-close').addEventListener('click', hideMobileDetail);
}

// Hide mobile detail panel
function hideMobileDetail() {
    const panel = document.getElementById('mobile-detail-panel');
    if (panel) {
        panel.classList.remove('visible');
    }
    currentDetailResort = null;
}

// Toggle detail for a resort (handles click on same bubble)
function toggleDetail(resort) {
    checkMobile();

    // If clicking the same resort, hide details
    if (currentDetailResort && currentDetailResort.name === resort.name) {
        if (isMobile) {
            hideMobileDetail();
        } else {
            hideDesktopDetail();
        }
        return;
    }

    // Show details for the new resort
    if (isMobile) {
        showMobileDetail(resort);
    } else {
        showDesktopDetail(resort);
    }
}

// Switch panel tab (desktop)
function switchPanelTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.panel-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });

    // Update tab content
    document.getElementById('top10-content').classList.toggle('hidden', tabName !== 'top10');
    document.getElementById('details-content').classList.toggle('hidden', tabName !== 'details');
}

// Switch drawer tab (mobile)
function switchDrawerTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.drawer-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });

    // Update panel content
    document.getElementById('drawer-filters').classList.toggle('hidden', tabName !== 'filters');
    document.getElementById('drawer-top10').classList.toggle('hidden', tabName !== 'top10');
}

// Toggle mobile drawer
function toggleDrawer() {
    const drawer = document.getElementById('mobile-drawer');
    drawer.classList.toggle('visible');
    drawer.classList.toggle('hidden');
}

// Update filter badge count
function updateFilterBadge() {
    let count = 0;
    const countryFilter = getFilterValue('country-filter');
    const regionFilter = getFilterValue('region-filter');
    const passFilter = getFilterValue('pass-filter');

    if (countryFilter) count++;
    if (regionFilter) count++;
    if (passFilter) count++;

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
    const countryFilter = getFilterValue('country-filter');
    const regionFilter = getFilterValue('region-filter');
    const passFilter = getFilterValue('pass-filter');

    return resortData.filter(resort => {
        if (countryFilter && resort.country !== countryFilter) return false;
        const region = resort.region || resort.state || '';
        if (regionFilter && region !== regionFilter) return false;
        if (passFilter === 'none' && resort.pass_type) return false;
        if (passFilter && passFilter !== 'none' && resort.pass_type !== passFilter) return false;
        return true;
    });
}

// Update Top 10 list (both desktop and mobile)
function updateTop10() {
    const filtered = getFilteredResorts();

    // Sort by snowfall based on current filter
    const sorted = [...filtered].sort((a, b) => {
        return getSnowfallForFilter(b) - getSnowfallForFilter(a);
    });

    const top10 = sorted.slice(0, 10);

    // Update both desktop and mobile lists
    const containers = [
        document.getElementById('top-resorts-list'),
        document.getElementById('mobile-top-resorts-list')
    ].filter(c => c);

    containers.forEach(container => {
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
    });
}

// Create markers for all resorts
function createMarkers() {
    // Clear existing markers
    markers.forEach(m => map.removeLayer(m.marker));
    markers = [];
    
    // Hide any existing hover popup
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

        // Show hover popup on mouseenter (desktop only)
        marker.on('mouseover', () => {
            showHoverPopup(resort, marker);
        });

        // Schedule hide on mouseleave (gives time to move to popup)
        marker.on('mouseout', () => {
            scheduleHideHoverPopup();
        });

        // Click still shows detail panel (and works for mobile tap)
        marker.on('click', () => toggleDetail(resort));

        marker.addTo(map);
        markers.push({ marker, resort });
    }

    // Update Top 10 list when markers change
    updateTop10();

    // Update filter badge
    updateFilterBadge();
}

// Populate country filter dropdown (both desktop and mobile)
function populateCountryFilter() {
    const countries = [...new Set(resortData.map(r => r.country))].sort();
    const selects = document.querySelectorAll('.country-filter');

    selects.forEach(select => {
        // Clear existing options except "All Countries"
        select.innerHTML = '<option value="">All Countries</option>';

        for (const country of countries) {
            const option = document.createElement('option');
            option.value = country;
            option.textContent = getCountryName(country);
            select.appendChild(option);
        }
    });
}

// Populate region filter dropdown based on selected country (both desktop and mobile)
function populateRegionFilter() {
    const countryFilter = getFilterValue('country-filter');
    const selects = document.querySelectorAll('.region-filter');

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

    selects.forEach(select => {
        select.innerHTML = '<option value="">All Regions</option>';

        for (const region of regions) {
            const option = document.createElement('option');
            option.value = region;
            option.textContent = region;
            select.appendChild(option);
        }
    });
}

// Sync filter values between desktop and mobile
function syncFilters(sourceId) {
    const sourceEl = document.getElementById(sourceId);
    if (!sourceEl) return;

    const value = sourceEl.value;
    const filterType = sourceId.replace('mobile-', '');

    // Sync to the other version
    const desktopEl = document.getElementById(filterType);
    const mobileEl = document.getElementById('mobile-' + filterType);

    if (desktopEl && desktopEl !== sourceEl) desktopEl.value = value;
    if (mobileEl && mobileEl !== sourceEl) mobileEl.value = value;
}

// Handle country filter change
function onCountryChange(e) {
    syncFilters(e.target.id);
    populateRegionFilter();
    createMarkers();

    // Fit map to selected country's resorts
    const countryFilter = getFilterValue('country-filter');
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

// Handle other filter changes
function onFilterChange(e) {
    syncFilters(e.target.id);
    createMarkers();
}

// Toggle panel collapse (desktop)
function togglePanelCollapse() {
    const panel = document.getElementById('side-panel');
    panel.classList.toggle('collapsed');
}

// Set up event listeners
function setupEventListeners() {
    // Desktop filter listeners
    document.getElementById('country-filter').addEventListener('change', onCountryChange);
    document.getElementById('region-filter').addEventListener('change', onFilterChange);
    document.getElementById('pass-filter').addEventListener('change', onFilterChange);
    document.getElementById('snow-filter').addEventListener('change', onFilterChange);

    // Mobile filter listeners
    document.getElementById('mobile-country-filter').addEventListener('change', onCountryChange);
    document.getElementById('mobile-region-filter').addEventListener('change', onFilterChange);
    document.getElementById('mobile-pass-filter').addEventListener('change', onFilterChange);
    document.getElementById('mobile-snow-filter').addEventListener('change', onFilterChange);

    // Desktop panel tab listeners
    document.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => switchPanelTab(tab.dataset.tab));
    });

    // Desktop panel collapse
    document.getElementById('panel-collapse').addEventListener('click', togglePanelCollapse);

    // Mobile menu toggle
    document.getElementById('menu-toggle').addEventListener('click', toggleDrawer);

    // Mobile drawer tab listeners
    document.querySelectorAll('.drawer-tab').forEach(tab => {
        tab.addEventListener('click', () => switchDrawerTab(tab.dataset.tab));
    });

    // Close details when clicking on map (not markers)
    map.on('click', (e) => {
        // Check if click was on the map itself (not a marker)
        if (e.originalEvent.target.classList.contains('leaflet-container') ||
            e.originalEvent.target.classList.contains('leaflet-tile-pane') ||
            e.originalEvent.target.classList.contains('leaflet-tile')) {
            checkMobile();
            if (isMobile) {
                hideMobileDetail();
            } else {
                hideDesktopDetail();
            }
        }
    });

    // Handle window resize
    window.addEventListener('resize', () => {
        checkMobile();
    });
}

// Load forecast data and initialize
async function init() {
    checkMobile();
    initMap();
    createHoverPopup();  // Create the hover popup element
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

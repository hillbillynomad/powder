// Powder Web UI - Interactive Snowfall Map

const BUBBLE_COLOR = '#3b82f6';
const BUBBLE_FILL_OPACITY = 0.6;
const MIN_RADIUS = 5;  // Minimum radius for zero-snow resorts

let map;
let markers = [];
let resortData = [];
let currentDetailResort = null;  // Track currently displayed resort for toggle behavior
let isMobile = false;  // Track if we're in mobile view

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

// Format date for mini-graph labels (short format like "Jan 5")
function formatShortDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Build mini cumulative snowfall graph as SVG
function buildMiniGraph(resort) {
    const data = getCumulativeChartData(resort);
    if (data.length === 0) return '';
    
    // Graph dimensions - increased height for axis labels
    const width = 200;
    const height = 70;
    const paddingTop = 4;
    const paddingBottom = 18; // Space for axis labels
    const paddingLeft = 4;
    const paddingRight = 4;
    const chartHeight = height - paddingTop - paddingBottom;
    
    // Find data range
    const minDay = data[0].dayOffset;
    const maxDay = data[data.length - 1].dayOffset;
    const maxCumulative = Math.max(...data.map(d => d.cumulative), 1);
    
    // Calculate scale factors
    const dayRange = maxDay - minDay || 1;
    const xScale = (width - paddingLeft - paddingRight) / dayRange;
    const yScale = chartHeight / maxCumulative;
    
    // Convert data point to SVG coordinates
    const toX = (dayOffset) => paddingLeft + (dayOffset - minDay) * xScale;
    const toY = (cumulative) => paddingTop + chartHeight - cumulative * yScale;
    const baseY = paddingTop + chartHeight; // Bottom of chart area
    
    // Find today's X position (day 0)
    const todayX = toX(0);
    
    // Build path points
    const linePoints = data.map(d => `${toX(d.dayOffset).toFixed(1)},${toY(d.cumulative).toFixed(1)}`).join(' ');
    
    // Split data into historical (dayOffset < 0) and forecast (dayOffset >= 0)
    const historicalData = data.filter(d => d.dayOffset < 0);
    const forecastData = data.filter(d => d.dayOffset >= 0);
    
    // Find the cumulative value at day 0 (or interpolate)
    let cumulativeAtToday = 0;
    const todayPoint = data.find(d => d.dayOffset === 0);
    if (todayPoint) {
        cumulativeAtToday = todayPoint.cumulative;
    } else if (historicalData.length > 0) {
        cumulativeAtToday = historicalData[historicalData.length - 1].cumulative;
    }
    
    // Build historical area path
    let historicalPath = '';
    if (historicalData.length > 0) {
        const startX = toX(historicalData[0].dayOffset);
        const endX = Math.min(todayX, toX(historicalData[historicalData.length - 1].dayOffset));
        historicalPath = `M${startX.toFixed(1)},${baseY}`;
        for (const d of historicalData) {
            historicalPath += ` L${toX(d.dayOffset).toFixed(1)},${toY(d.cumulative).toFixed(1)}`;
        }
        historicalPath += ` L${endX.toFixed(1)},${toY(cumulativeAtToday).toFixed(1)}`;
        historicalPath += ` L${endX.toFixed(1)},${baseY} Z`;
    }
    
    // Build forecast area path
    let forecastPath = '';
    if (forecastData.length > 0) {
        const startX = toX(forecastData[0].dayOffset);
        const prevCumulative = historicalData.length > 0 
            ? historicalData[historicalData.length - 1].cumulative 
            : 0;
        
        forecastPath = `M${startX.toFixed(1)},${baseY}`;
        forecastPath += ` L${startX.toFixed(1)},${toY(prevCumulative).toFixed(1)}`;
        for (const d of forecastData) {
            forecastPath += ` L${toX(d.dayOffset).toFixed(1)},${toY(d.cumulative).toFixed(1)}`;
        }
        const endX = toX(forecastData[forecastData.length - 1].dayOffset);
        forecastPath += ` L${endX.toFixed(1)},${baseY} Z`;
    }
    
    // Today marker
    const showTodayMarker = minDay <= 0 && maxDay >= 0;
    const todayMarker = showTodayMarker 
        ? `<line class="today-marker" x1="${todayX.toFixed(1)}" y1="${paddingTop}" x2="${todayX.toFixed(1)}" y2="${baseY}"/>`
        : '';
    
    // Build tick marks and labels for X axis
    // Show: first date, today (if in range), last date
    const tickMarks = [];
    const labels = [];
    const tickY = baseY;
    const labelY = baseY + 12;
    
    // First date tick
    const firstX = toX(minDay);
    tickMarks.push(`<line class="tick" x1="${firstX.toFixed(1)}" y1="${tickY}" x2="${firstX.toFixed(1)}" y2="${tickY + 4}"/>`);
    labels.push(`<text class="axis-label" x="${firstX.toFixed(1)}" y="${labelY}" text-anchor="start">${formatShortDate(data[0].date)}</text>`);
    
    // Today tick (if in range)
    if (showTodayMarker) {
        tickMarks.push(`<line class="tick" x1="${todayX.toFixed(1)}" y1="${tickY}" x2="${todayX.toFixed(1)}" y2="${tickY + 4}"/>`);
        labels.push(`<text class="axis-label today-label" x="${todayX.toFixed(1)}" y="${labelY}" text-anchor="middle">Today</text>`);
    }
    
    // Last date tick
    const lastX = toX(maxDay);
    tickMarks.push(`<line class="tick" x1="${lastX.toFixed(1)}" y1="${tickY}" x2="${lastX.toFixed(1)}" y2="${tickY + 4}"/>`);
    labels.push(`<text class="axis-label" x="${lastX.toFixed(1)}" y="${labelY}" text-anchor="end">${formatShortDate(data[data.length - 1].date)}</text>`);
    
    // X axis line
    const axisLine = `<line class="axis-line" x1="${paddingLeft}" y1="${baseY}" x2="${width - paddingRight}" y2="${baseY}"/>`;
    
    // Build interactive hover points with tooltips
    const hoverPoints = data.map(d => {
        const x = toX(d.dayOffset);
        const y = toY(d.cumulative);
        const dateLabel = d.dayOffset === 0 ? 'Today' : formatShortDate(d.date);
        const tooltipText = `${dateLabel}: ${d.cumulative.toFixed(1)}" total`;
        return `<circle class="hover-point" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6">
            <title>${tooltipText}</title>
        </circle>`;
    }).join('');
    
    return `
        <svg class="mini-graph" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
            ${historicalPath ? `<path class="area historical" d="${historicalPath}"/>` : ''}
            ${forecastPath ? `<path class="area forecast" d="${forecastPath}"/>` : ''}
            ${axisLine}
            ${tickMarks.join('')}
            ${todayMarker}
            <polyline class="cumulative-line" points="${linePoints}" fill="none"/>
            ${labels.join('')}
            ${hoverPoints}
        </svg>
    `;
}

// Build larger interactive graph for detail panel
function buildDetailGraph(resort) {
    const data = getCumulativeChartData(resort);
    if (data.length === 0) return '';
    
    // Larger dimensions for detail panel
    const width = 280;
    const height = 100;
    const paddingTop = 6;
    const paddingBottom = 20;
    const paddingLeft = 6;
    const paddingRight = 6;
    const chartHeight = height - paddingTop - paddingBottom;
    
    // Find data range
    const minDay = data[0].dayOffset;
    const maxDay = data[data.length - 1].dayOffset;
    const maxCumulative = Math.max(...data.map(d => d.cumulative), 1);
    
    // Calculate scale factors
    const dayRange = maxDay - minDay || 1;
    const xScale = (width - paddingLeft - paddingRight) / dayRange;
    const yScale = chartHeight / maxCumulative;
    
    // Convert data point to SVG coordinates
    const toX = (dayOffset) => paddingLeft + (dayOffset - minDay) * xScale;
    const toY = (cumulative) => paddingTop + chartHeight - cumulative * yScale;
    const baseY = paddingTop + chartHeight;
    
    // Find today's X position
    const todayX = toX(0);
    
    // Build path points
    const linePoints = data.map(d => `${toX(d.dayOffset).toFixed(1)},${toY(d.cumulative).toFixed(1)}`).join(' ');
    
    // Split data into historical and forecast
    const historicalData = data.filter(d => d.dayOffset < 0);
    const forecastData = data.filter(d => d.dayOffset >= 0);
    
    // Find cumulative value at today
    let cumulativeAtToday = 0;
    const todayPoint = data.find(d => d.dayOffset === 0);
    if (todayPoint) {
        cumulativeAtToday = todayPoint.cumulative;
    } else if (historicalData.length > 0) {
        cumulativeAtToday = historicalData[historicalData.length - 1].cumulative;
    }
    
    // Build historical area path
    let historicalPath = '';
    if (historicalData.length > 0) {
        const startX = toX(historicalData[0].dayOffset);
        const endX = Math.min(todayX, toX(historicalData[historicalData.length - 1].dayOffset));
        historicalPath = `M${startX.toFixed(1)},${baseY}`;
        for (const d of historicalData) {
            historicalPath += ` L${toX(d.dayOffset).toFixed(1)},${toY(d.cumulative).toFixed(1)}`;
        }
        historicalPath += ` L${endX.toFixed(1)},${toY(cumulativeAtToday).toFixed(1)}`;
        historicalPath += ` L${endX.toFixed(1)},${baseY} Z`;
    }
    
    // Build forecast area path
    let forecastPath = '';
    if (forecastData.length > 0) {
        const startX = toX(forecastData[0].dayOffset);
        const prevCumulative = historicalData.length > 0 
            ? historicalData[historicalData.length - 1].cumulative 
            : 0;
        
        forecastPath = `M${startX.toFixed(1)},${baseY}`;
        forecastPath += ` L${startX.toFixed(1)},${toY(prevCumulative).toFixed(1)}`;
        for (const d of forecastData) {
            forecastPath += ` L${toX(d.dayOffset).toFixed(1)},${toY(d.cumulative).toFixed(1)}`;
        }
        const endX = toX(forecastData[forecastData.length - 1].dayOffset);
        forecastPath += ` L${endX.toFixed(1)},${baseY} Z`;
    }
    
    // Today marker
    const showTodayMarker = minDay <= 0 && maxDay >= 0;
    const todayMarker = showTodayMarker 
        ? `<line class="today-marker" x1="${todayX.toFixed(1)}" y1="${paddingTop}" x2="${todayX.toFixed(1)}" y2="${baseY}"/>`
        : '';
    
    // Build more tick marks for larger graph (~5 labels)
    const tickMarks = [];
    const labels = [];
    const tickY = baseY;
    const labelY = baseY + 14;
    
    // Calculate tick positions: first, 1/4, 1/2 (today if applicable), 3/4, last
    const tickDays = [minDay];
    const quarterDay = Math.round(minDay + dayRange * 0.25);
    const midDay = 0; // Today
    const threeQuarterDay = Math.round(minDay + dayRange * 0.75);
    
    // Add quarter mark if not too close to edges
    if (quarterDay > minDay + 2 && quarterDay < maxDay - 2) {
        tickDays.push(quarterDay);
    }
    
    // Add today if in range
    if (showTodayMarker && midDay > minDay + 2 && midDay < maxDay - 2) {
        tickDays.push(midDay);
    }
    
    // Add three-quarter mark if not too close to edges or today
    if (threeQuarterDay > minDay + 2 && threeQuarterDay < maxDay - 2 && Math.abs(threeQuarterDay - midDay) > 2) {
        tickDays.push(threeQuarterDay);
    }
    
    tickDays.push(maxDay);
    
    // Remove duplicates and sort
    const uniqueTickDays = [...new Set(tickDays)].sort((a, b) => a - b);
    
    // Find the data point closest to each tick day for the date label
    for (const tickDay of uniqueTickDays) {
        const x = toX(tickDay);
        const closestPoint = data.reduce((prev, curr) => 
            Math.abs(curr.dayOffset - tickDay) < Math.abs(prev.dayOffset - tickDay) ? curr : prev
        );
        
        tickMarks.push(`<line class="tick" x1="${x.toFixed(1)}" y1="${tickY}" x2="${x.toFixed(1)}" y2="${tickY + 4}"/>`);
        
        const labelText = tickDay === 0 ? 'Today' : formatShortDate(closestPoint.date);
        const anchor = tickDay === minDay ? 'start' : (tickDay === maxDay ? 'end' : 'middle');
        const labelClass = tickDay === 0 ? 'axis-label today-label' : 'axis-label';
        labels.push(`<text class="${labelClass}" x="${x.toFixed(1)}" y="${labelY}" text-anchor="${anchor}">${labelText}</text>`);
    }
    
    // X axis line
    const axisLine = `<line class="axis-line" x1="${paddingLeft}" y1="${baseY}" x2="${width - paddingRight}" y2="${baseY}"/>`;
    
    // Build chart metadata for interactive hover (x positions and values)
    const chartPoints = data.map(d => ({
        x: parseFloat(toX(d.dayOffset).toFixed(1)),
        date: d.dayOffset === 0 ? 'Today' : formatShortDate(d.date),
        daily: d.daily.toFixed(1),
        cumulative: d.cumulative.toFixed(1)
    }));
    const chartMeta = JSON.stringify(chartPoints);
    
    // Tracking line (hidden by default, follows cursor)
    const trackingLine = `<line class="tracking-line" x1="0" y1="${paddingTop}" x2="0" y2="${baseY}" style="display: none;"/>`;
    
    // Invisible overlay to capture mouse events across entire chart area
    const hoverOverlay = `<rect class="hover-overlay" x="${paddingLeft}" y="${paddingTop}" width="${width - paddingLeft - paddingRight}" height="${chartHeight}" fill="transparent"/>`;
    
    return `
        <div class="detail-graph-container" data-chart='${chartMeta}'>
            <svg class="detail-graph" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
                ${historicalPath ? `<path class="area historical" d="${historicalPath}"/>` : ''}
                ${forecastPath ? `<path class="area forecast" d="${forecastPath}"/>` : ''}
                ${axisLine}
                ${tickMarks.join('')}
                ${todayMarker}
                <polyline class="cumulative-line" points="${linePoints}" fill="none"/>
                ${labels.join('')}
                ${trackingLine}
                ${hoverOverlay}
            </svg>
            <div class="graph-info-bar">
                <span class="info-date">Hover over graph</span>
                <span class="info-daily">Daily: --</span>
                <span class="info-cumulative">Total: --</span>
            </div>
        </div>
    `;
}

// Set up interactive hover for detail graph
function setupDetailGraphInteraction() {
    const container = document.querySelector('.detail-graph-container');
    if (!container) return;
    
    const svg = container.querySelector('.detail-graph');
    const overlay = svg.querySelector('.hover-overlay');
    const trackingLine = svg.querySelector('.tracking-line');
    const infoBar = container.querySelector('.graph-info-bar');
    if (!infoBar || !overlay) return;
    
    const dateEl = infoBar.querySelector('.info-date');
    const dailyEl = infoBar.querySelector('.info-daily');
    const cumulativeEl = infoBar.querySelector('.info-cumulative');
    
    // Parse embedded chart data
    const chartPoints = JSON.parse(container.dataset.chart || '[]');
    if (chartPoints.length === 0) return;
    
    // Store default text
    const defaultDate = 'Hover over graph';
    const defaultDaily = 'Daily: --';
    const defaultCumulative = 'Total: --';
    
    // Handle mouse move over the chart area
    overlay.addEventListener('mousemove', (e) => {
        // Get mouse X position relative to SVG
        const rect = svg.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        
        // Find the nearest data point by X position
        const nearest = chartPoints.reduce((prev, curr) => 
            Math.abs(curr.x - mouseX) < Math.abs(prev.x - mouseX) ? curr : prev
        );
        
        // Update tracking line position
        trackingLine.setAttribute('x1', nearest.x);
        trackingLine.setAttribute('x2', nearest.x);
        trackingLine.style.display = 'block';
        
        // Update info bar
        dateEl.textContent = nearest.date;
        dailyEl.textContent = `Daily: ${nearest.daily}"`;
        cumulativeEl.textContent = `Total: ${nearest.cumulative}"`;
    });
    
    // Reset when mouse leaves the overlay
    overlay.addEventListener('mouseleave', () => {
        trackingLine.style.display = 'none';
        dateEl.textContent = defaultDate;
        dailyEl.textContent = defaultDaily;
        cumulativeEl.textContent = defaultCumulative;
    });
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
        ${buildMiniGraph(resort)}
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
    const filter = getFilterValue('snow-filter');
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
        ${buildDetailGraph(resort)}
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

// Show detail panel for a resort (desktop)
function showDesktopDetail(resort) {
    const content = document.getElementById('detail-content');
    content.innerHTML = buildDetailContent(resort);

    // Switch to details tab
    switchPanelTab('details');

    // Ensure panel is not collapsed
    const panel = document.getElementById('side-panel');
    panel.classList.remove('collapsed');

    // Set up interactive graph hover
    setupDetailGraphInteraction();

    currentDetailResort = resort;
}

// Hide detail panel (desktop) - switch back to Top 10
function hideDesktopDetail() {
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
    
    // Set up interactive graph hover
    setupDetailGraphInteraction();
    
    currentDetailResort = resort;
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

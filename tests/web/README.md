# Web UI Tests

JavaScript tests for Powder's web interface, including unit tests (Vitest) and browser E2E tests (Playwright).

## Overview

| Test Type | Tool | Location | Description |
|-----------|------|----------|-------------|
| Unit Tests | Vitest | `unit/` | Pure function testing |
| E2E Tests | Playwright | `e2e/` | Browser automation |

## Quick Start

```bash
cd tests/web

# Install dependencies
npm install

# Run unit tests
npm test

# Run unit tests with coverage
npm run test:coverage

# Run E2E tests (requires Playwright install)
npx playwright install  # First time only
npm run test:e2e
```

## Unit Tests (Vitest)

### Configuration

**[vitest.config.js](unit/vitest.config.js)**
- Environment: `jsdom` (browser-like DOM)
- Coverage: 75% threshold enforced
- Setup: `setup.js` injects global functions from `app.js`

### Functions Tested

From `powder/web/js/app.js`:

| Function | Test Count | Description |
|----------|-----------|-------------|
| `getRadius()` | 4 | Bubble size calculation from snowfall |
| `formatDate()` | 3 | Date string formatting |
| `getCountryName()` | 3 | Country code to full name |
| `daysBetween()` | 5 | Date difference calculation |
| `getSnowfallForFilter()` | 6 | Snowfall value by filter type |
| `getCumulativeChartData()` | 8 | Chart data generation |
| `getElevationText()` | 4 | Elevation display formatting |
| `getSourcesFromForecasts()` | 4 | Extract unique forecast sources |

### Running Unit Tests

```bash
# All tests
npm test

# Watch mode
npm run test:watch

# With coverage report
npm run test:coverage

# Specific test file
npx vitest run unit/app.test.js
```

### Coverage Requirements

Vitest enforces 75% minimum coverage:

```javascript
// vitest.config.js
thresholds: {
  statements: 75,
  branches: 75,
  functions: 75,
  lines: 75,
}
```

## E2E Tests (Playwright)

### Configuration

**[playwright.config.ts](playwright.config.ts)**
- Browsers: Chrome, Firefox, Safari, Mobile Chrome, Mobile Safari
- Web Server: Auto-starts `python -m http.server` on port 8000
- Parallel: Full parallelization enabled

### Test Files

| File | Tests | Description |
|------|-------|-------------|
| `map.spec.ts` | 7 | Map loading, markers, panel toggle |
| `filters.spec.ts` | 8 | Filter controls and functionality |
| `detail_panel.spec.ts` | 10 | Side panel, tabs, resort details |
| `mobile.spec.ts` | 7 | Mobile/tablet layouts and touch |

### Test Coverage

**Map Tests** (`map.spec.ts`)
- Page loads with correct title
- Map container is visible
- Header displays "Powder"
- Side panel exists
- Filter drawer toggle works
- Markers display on map
- Clicking marker opens detail panel

**Filter Tests** (`filters.spec.ts`)
- Country, region, pass, snowfall filters are present
- Filter options are correct
- Selecting country reduces markers
- Filter badge shows active count

**Detail Panel Tests** (`detail_panel.spec.ts`)
- Tab buttons (Top 10, Details) are visible
- Tab switching works
- Panel can be collapsed
- Clicking marker shows resort details
- Detail shows elevation info
- Detail shows forecast table
- Top 10 list is populated
- Clicking Top 10 item focuses resort

**Mobile Tests** (`mobile.spec.ts`)
- Page loads on mobile (iPhone 13)
- Menu toggle is visible
- Filter drawer opens on mobile
- Map takes full width
- Tapping marker opens detail (no hover)
- Page loads on tablet (iPad Mini)
- Side panel visible on tablet

### Running E2E Tests

```bash
# All browsers
npm run test:e2e

# Specific browser
npx playwright test --project=chromium

# Headed mode (visible browser)
npx playwright test --headed

# Debug mode
npx playwright test --debug

# Specific test file
npx playwright test e2e/map.spec.ts

# Mobile only
npx playwright test --project="Mobile Chrome"
```

### Prerequisites

E2E tests require:
1. **Forecast data**: Run `poetry run powder --export-json` to generate `powder/web/data/forecasts.json`
2. **Playwright browsers**: Run `npx playwright install` (first time only)

Tests gracefully skip if forecast data is unavailable.

## Project Structure

```
tests/web/
├── README.md              # This file
├── package.json           # npm dependencies
├── playwright.config.ts   # Playwright configuration
├── unit/
│   ├── vitest.config.js   # Vitest configuration
│   ├── setup.js           # Test setup (injects globals)
│   └── app.test.js        # Unit tests
└── e2e/
    ├── map.spec.ts        # Map functionality tests
    ├── filters.spec.ts    # Filter control tests
    ├── detail_panel.spec.ts # Detail panel tests
    └── mobile.spec.ts     # Mobile/responsive tests
```

## Differences from Python Tests

| Aspect | Python Tests | Web Tests |
|--------|-------------|-----------|
| Runtime | pytest | Node.js |
| Unit Testing | pytest + responses | Vitest + jsdom |
| E2E Testing | Live API calls | Playwright browsers |
| Coverage | pytest-cov | Vitest coverage |
| Parallel | pytest-xdist | Vitest/Playwright workers |

## Test Dependencies

```json
{
  "devDependencies": {
    "vitest": "^2.0.0",
    "jsdom": "^24.0.0",
    "@playwright/test": "^1.42.0"
  }
}
```

## Adding New Tests

### Unit Tests

1. Add tests to `unit/app.test.js` or create new test file
2. Import functions from setup or test file
3. Use `describe` and `it` blocks

```javascript
describe('newFunction', () => {
  it('does something expected', () => {
    expect(newFunction(input)).toBe(expected);
  });
});
```

### E2E Tests

1. Create `.spec.ts` file in `e2e/`
2. Use Playwright's test API
3. Handle cases where data may not be available

```typescript
import { test, expect } from '@playwright/test';

test.describe('New Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map');
  });

  test('feature works', async ({ page }) => {
    const element = page.locator('#element');
    await expect(element).toBeVisible();
  });
});
```

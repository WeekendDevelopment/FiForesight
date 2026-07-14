import { test, expect, type Page } from '@playwright/test';

/**
 * Command Palette (Feature 33) — open + search smoke test.
 *
 * Open path per viewport (all four project widths):
 *   320 / 768  (below MUI md): bottom-nav Search button → full-width top sheet.
 *   1280 / 2560 (md+):         Ctrl+K → centered modal.
 * Each: type "AAP", assert an AAPL ticker result renders, assert the open
 * palette introduces NO horizontal overflow (the responsive build standard),
 * and Esc closes. A separate test covers the analysis-page search trigger +
 * live multi-exchange results (route-mocked).
 *
 * Static results come from the shared ticker universe (lib/tickerSearch.ts) —
 * no network involved, so these can't flake on a data outage.
 */

async function expectNoHorizontalOverflow(page: Page, label: string) {
  const metrics = await page.evaluate(() => ({
    docScrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(
    metrics.docScrollWidth,
    `Horizontal overflow with palette open (${label}): ` +
      `scrollWidth=${metrics.docScrollWidth} > innerWidth=${metrics.innerWidth}`,
  ).toBeLessThanOrEqual(metrics.innerWidth + 1);
}

async function typeAndAssertTickerResult(page: Page, label: string) {
  const input = page.getByTestId('palette-input');
  await expect(input, `palette input visible (${label})`).toBeVisible();
  await input.fill('AAP');

  // AAPL is a symbol-prefix match in the static universe — always rank #1.
  await expect(
    page.locator('#palette-listbox [role="option"]', { hasText: 'AAPL' }).first(),
    `AAPL ticker result visible (${label})`,
  ).toBeVisible();
}

// All four project viewports (mirrors responsive.spec.ts). Below MUI's md
// breakpoint (900px) the palette is a top sheet opened from the bottom-nav
// Search button; at md+ it's a centered modal opened with Ctrl+K.
const OPEN_VIEWPORTS = [
  { w: 320,  h: 740,  name: 'phone',   via: 'button'   },
  { w: 768,  h: 1024, name: 'tablet',  via: 'button'   },
  { w: 1280, h: 900,  name: 'desktop', via: 'keyboard' },
  { w: 2560, h: 1440, name: '4k',      via: 'keyboard' },
] as const;

for (const vp of OPEN_VIEWPORTS) {
  test(`opens via ${vp.via} @ ${vp.name} (${vp.w}px), finds AAPL, no overflow`, async ({ page }) => {
    await page.setViewportSize({ width: vp.w, height: vp.h });
    try {
      await page.goto('/', { waitUntil: 'networkidle', timeout: 30_000 });
    } catch { /* layout-only — proceed */ }
    await expect(page.getByTestId('app-shell')).toBeVisible({ timeout: 15_000 });

    if (vp.via === 'keyboard') {
      await page.keyboard.press('Control+k');
    } else {
      await page.getByTestId('palette-search-button').click();
    }
    await expect(page.getByTestId('command-palette')).toBeVisible();

    await typeAndAssertTickerResult(page, vp.name);
    await expectNoHorizontalOverflow(page, `${vp.name} ${vp.w}px`);

    // Esc closes (hardware keyboards exist on tablets too).
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('command-palette')).not.toBeVisible();
  });
}

test('home hero search trigger opens the palette', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  try {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 30_000 });
  } catch { /* layout-only — proceed */ }
  await expect(page.getByTestId('app-shell')).toBeVisible({ timeout: 15_000 });

  // The landing hero's search bar is a palette trigger too (no inline
  // Autocomplete / exchange dropdown any more).
  await page.getByTestId('home-search-trigger').click();
  await expect(page.getByTestId('command-palette')).toBeVisible();
  await expect(page.getByTestId('palette-input')).toBeFocused();
});

test('analysis search trigger opens the palette; live search lists exchange listings', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });

  // Mock the live symbol search (F33) so this never depends on the backend or
  // Yahoo — the point is the palette UI: one name, multiple exchange listings.
  await page.route('**/api/symbols/search**', route =>
    route.fulfill({
      json: [
        { symbol: 'BP',   name: 'BP p.l.c.', exchange: 'NYSE',   type: 'EQUITY' },
        { symbol: 'BP.L', name: 'BP PLC',    exchange: 'London', type: 'EQUITY' },
      ],
    }));

  try {
    await page.goto('/analysis', { waitUntil: 'networkidle', timeout: 30_000 });
  } catch { /* layout-only — proceed */ }
  await expect(page.getByTestId('app-shell')).toBeVisible({ timeout: 15_000 });

  // The analysis page's search bar is now a palette trigger (no inline
  // Autocomplete / exchange dropdown any more).
  await page.getByTestId('analysis-search-trigger').click();
  await expect(page.getByTestId('command-palette')).toBeVisible();

  await page.getByTestId('palette-input').fill('BP');
  const options = page.locator('#palette-listbox [role="option"]');
  await expect(options.filter({ hasText: 'NYSE' }).first()).toBeVisible();
  await expect(options.filter({ hasText: 'London' }).first()).toBeVisible();
  await expect(options.filter({ hasText: 'BP.L' }).first()).toBeVisible();

  await expectNoHorizontalOverflow(page, 'analysis trigger 1280px');
});

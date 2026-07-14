import { test, expect, type Page } from '@playwright/test';

/**
 * Command Palette (Feature 33) — open + search smoke test.
 *
 * Desktop (1280px): open via Ctrl+K keyboard shortcut.
 * Phone (320px):    open via the bottom-nav Search button (no keyboard on phones).
 * Both: type "AAP", assert an AAPL ticker result renders, and assert the open
 * palette introduces NO horizontal overflow (the responsive build standard).
 *
 * Results come from the static shared ticker universe (lib/tickerSearch.ts) —
 * no network involved, so this can't flake on a data outage.
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

test('opens via Ctrl+K on desktop (1280px), finds AAPL, no overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  try {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 30_000 });
  } catch { /* layout-only — proceed */ }
  await expect(page.getByTestId('app-shell')).toBeVisible({ timeout: 15_000 });

  await page.keyboard.press('Control+k');
  await expect(page.getByTestId('command-palette')).toBeVisible();

  await typeAndAssertTickerResult(page, 'desktop');
  await expectNoHorizontalOverflow(page, 'desktop 1280px');

  // Esc closes.
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('command-palette')).not.toBeVisible();
});

test('opens via the Search button on phone (320px), finds AAPL, no overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  try {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 30_000 });
  } catch { /* layout-only — proceed */ }
  await expect(page.getByTestId('app-shell')).toBeVisible({ timeout: 15_000 });

  await page.getByTestId('palette-search-button').click();
  await expect(page.getByTestId('command-palette')).toBeVisible();

  await typeAndAssertTickerResult(page, 'phone');
  await expectNoHorizontalOverflow(page, 'phone 320px');
});

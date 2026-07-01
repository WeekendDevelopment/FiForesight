import { defineConfig, devices } from '@playwright/test';

/**
 * Responsive QA harness — see tests/e2e/responsive.spec.ts.
 *
 * Loads every app route at four viewports (phone/tablet/desktop/4K) and fails on
 * horizontal overflow or a missing app shell. This is the enforcement mechanism
 * for FiForesight's "multi-screen responsive" build standard.
 *
 * The webServer runs a production build (`pnpm run build && pnpm run start`) so the
 * harness exercises the same bundle that ships. Pages fetch live yfinance/Groq data
 * that may be slow or empty — the harness tests LAYOUT only, tolerating empty/error
 * states, so it never depends on live network success.
 */
export default defineConfig({
  testDir: './tests/e2e',
  // Per-test budget must exceed the 30s goto timeout so the layout assertions
  // still run after a data-heavy page (e.g. /earnings) never reaches networkidle
  // and the goto times out.
  timeout: 60_000,
  // Fail the build on an accidental test.only left in source.
  forbidOnly: !!process.env.CI,
  // A single prod server is the bottleneck — keep concurrency modest so slow,
  // data-heavy pages don't time out fighting each other for resources.
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'pnpm run build && pnpm run start',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});

import { test, expect } from '@playwright/test';

/**
 * Responsive QA harness.
 *
 * For every app route × every supported viewport this asserts two things:
 *   1. NO HORIZONTAL OVERFLOW — the page never grows wider than the viewport
 *      (1px slack for sub-pixel rounding). This is the core enforcement of the
 *      "multi-screen responsive" build standard.
 *   2. KEY ELEMENT VISIBLE — the app shell rendered, i.e. the page actually
 *      mounted rather than crashing into a blank/error boundary.
 *
 * Layout-only: pages fetch live yfinance/Groq data that may be slow or empty.
 * We tolerate empty/error states and never assert on fetched content, so the
 * harness can't flake on a third-party outage. Auth-gated routes (/portfolio,
 * /alerts, /simulation) are tested LOGGED OUT — the AuthGate they render must
 * also be responsive.
 *
 * Keeping ROUTES in sync: every entry below must exist as a page under
 * frontend/app — the list mirrors the NAV_ITEMS array in
 * frontend/app/(app)/layout.tsx (plus '/simulation', which lives outside the
 * (app) route group but is still a nav item). If a route is added/removed in
 * NAV_ITEMS, update this list so the harness can't silently drift.
 */
const ROUTES = [
  '/',           // Home
  '/analysis',   // Analysis
  '/options',    // Options
  '/earnings',   // Earnings
  '/ipo',        // IPO Tracker
  '/macro',      // Macro
  '/sectors',    // Sectors
  '/rotation',   // Rotation
  '/screener',   // Screener
  '/backtest',   // Backtest
  '/watchlist',  // Watchlist
  '/insights',   // Insights
  '/simulation', // Simulator (auth-gated; outside the (app) group)
  '/portfolio',  // My Portfolio (auth-gated)
  '/alerts',     // Alerts (auth-gated)
] as const;

const VIEWPORTS = [
  { w: 320,  h: 740,  name: 'phone'   },
  { w: 768,  h: 1024, name: 'tablet'  },
  { w: 1280, h: 900,  name: 'desktop' },
  { w: 2560, h: 1440, name: '4k'      },
] as const;

for (const route of ROUTES) {
  for (const vp of VIEWPORTS) {
    test(`${route} @ ${vp.name} (${vp.w}px)`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: vp.w, height: vp.h });

      // networkidle can never settle on pages with polling/long-poll fetches;
      // treat a timeout as "loaded enough" and proceed to the layout assertions.
      try {
        await page.goto(route, { waitUntil: 'networkidle', timeout: 30_000 });
      } catch {
        // proceed — we test layout, not load completion.
      }

      // Optional debug artifact (not asserted).
      await page
        .screenshot({
          path: testInfo.outputPath(`${route.replace(/\W+/g, '_') || 'home'}-${vp.name}.png`),
          fullPage: false,
        })
        .catch(() => { /* screenshots are best-effort */ });

      // 1. KEY ELEMENT VISIBLE — the shell mounted.
      await expect(
        page.getByTestId('app-shell'),
        `app-shell should be visible on ${route} @ ${vp.name}`,
      ).toBeVisible({ timeout: 15_000 });

      // 2. NO HORIZONTAL OVERFLOW.
      //
      // Two complementary checks (1px slack for sub-pixel rounding):
      //   a. document level — the page never grows wider than the viewport.
      //      Catches overflow that escapes to the page (e.g. a fixed-position
      //      mobile bar wider than the screen).
      //   b. content container — the app shell's <main> scroll region is not
      //      wider than its own client box. The (app) layout gives <main>
      //      `overflowY: auto`, which CSS resolves to `overflow-x: auto` too, so
      //      content overflow is absorbed by main's own scrollbar and never
      //      reaches documentElement — check (a) alone would miss it. Intentional
      //      `overflowX: auto` sub-panels (option chains, heatmaps) clip inside
      //      themselves and don't widen <main>, so they don't false-positive.
      const metrics = await page.evaluate(() => {
        const main = document.querySelector('main');
        return {
          docScrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
          mainScrollWidth: main?.scrollWidth ?? null,
          mainClientWidth: main?.clientWidth ?? null,
        };
      });

      expect(
        metrics.docScrollWidth,
        `Horizontal overflow (document) on ${route} @ ${vp.name} (${vp.w}px): ` +
          `scrollWidth=${metrics.docScrollWidth} > innerWidth=${metrics.innerWidth}`,
      ).toBeLessThanOrEqual(metrics.innerWidth + 1);

      if (metrics.mainScrollWidth !== null && metrics.mainClientWidth !== null) {
        expect(
          metrics.mainScrollWidth,
          `Horizontal overflow (content) on ${route} @ ${vp.name} (${vp.w}px): ` +
            `main.scrollWidth=${metrics.mainScrollWidth} > main.clientWidth=${metrics.mainClientWidth}`,
        ).toBeLessThanOrEqual(metrics.mainClientWidth + 1);
      }
    });
  }
}

import { expect, test } from "@playwright/test";

// EEI-F06/F09 (docs/28): the home visual-coverage gate, finally automated
// against the real app instead of only the prototype. At every required
// viewport the [data-visual-surface] union must carry >= 90% of the
// [data-information-workspace] area visible in the first screen, and the
// page must not overflow horizontally.
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 }
];

for (const viewport of VIEWPORTS) {
  test(`home visual coverage >=90% and no overflow at ${viewport.width}x${viewport.height}`, async ({
    page
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByTestId("workspace-shell")).toBeVisible();
    await expect(page.getByTestId("ecosystem-map-surface")).toBeVisible();

    const measurement = await page.evaluate(() => {
      const workspace = document.querySelector("[data-information-workspace]");
      if (!workspace) throw new Error("information workspace marker missing");
      const workspaceRect = workspace.getBoundingClientRect();
      const bounds = {
        left: Math.max(workspaceRect.left, 0),
        right: Math.min(workspaceRect.right, window.innerWidth),
        top: Math.max(workspaceRect.top, 0),
        bottom: Math.min(workspaceRect.bottom, window.innerHeight)
      };
      const surfaces = [...document.querySelectorAll("[data-visual-surface]")]
        .filter((el) => {
          const style = getComputedStyle(el);
          return style.display !== "none" && style.visibility !== "hidden";
        })
        .map((el) => {
          const r = el.getBoundingClientRect();
          return {
            left: Math.max(bounds.left, r.left),
            right: Math.min(bounds.right, r.right),
            top: Math.max(bounds.top, r.top),
            bottom: Math.min(bounds.bottom, r.bottom)
          };
        })
        .filter((r) => r.right > r.left && r.bottom > r.top);

      // Rectangle-union sweep over x slabs (same approach as
      // scripts/validate_visual_coverage.py; no double counting).
      const xs = [
        ...new Set([bounds.left, bounds.right, ...surfaces.flatMap((r) => [r.left, r.right])])
      ].sort((a, b) => a - b);
      let union = 0;
      for (let i = 0; i < xs.length - 1; i += 1) {
        const x1 = xs[i];
        const x2 = xs[i + 1];
        if (x2 <= x1) continue;
        const intervals = surfaces
          .filter((r) => r.left < x2 && r.right > x1)
          .map((r) => [r.top, r.bottom] as [number, number])
          .sort((a, b) => a[0] - b[0]);
        let covered = 0;
        let cursor = -Infinity;
        for (const [top, bottom] of intervals) {
          const start = Math.max(top, cursor);
          if (bottom > start) {
            covered += bottom - start;
            cursor = bottom;
          }
        }
        union += covered * (x2 - x1);
      }
      const workspaceArea =
        Math.max(bounds.right - bounds.left, 0) * Math.max(bounds.bottom - bounds.top, 0);
      return {
        ratio: workspaceArea > 0 ? union / workspaceArea : 0,
        surfaceCount: surfaces.length,
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
        svgTop: document
          .querySelector('[data-testid="ecosystem-map-svg"]')
          ?.getBoundingClientRect().top ?? Number.NaN
      };
    });

    expect(measurement.surfaceCount, "visual-surface markers present").toBeGreaterThan(0);
    expect(
      measurement.scrollWidth,
      `no horizontal overflow (scrollWidth ${measurement.scrollWidth} vs ${measurement.innerWidth})`
    ).toBeLessThanOrEqual(measurement.innerWidth);
    expect(
      measurement.ratio,
      `visual surface union ratio ${measurement.ratio.toFixed(3)}`
    ).toBeGreaterThanOrEqual(0.9);
    // The map must start in the upper half of the first viewport (EEI-F09
    // observed svg beginning at y=502 on a 900px viewport).
    expect(measurement.svgTop).toBeLessThan(viewport.height / 2);
  });
}

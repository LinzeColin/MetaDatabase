import { expect, test, type Page } from "@playwright/test";

// P0-3 标签防压叠验收（UX_SPEC_EEI §F.5）：
// 任意两个可见 SVG <text> 的 bbox 相交面积必须为 0——聚合（F.1）+
// 分级显隐（F.2）+ 贪心占位（F.3 最小版）+ 渲染修正（F.4）共同保证。
// 覆盖默认图与一次 reroot 后的图；L1 缩放下可读标签 ≤12。

type Box = { left: number; right: number; top: number; bottom: number; text: string };

async function visibleSvgTextBoxes(page: Page): Promise<Box[]> {
  return page.evaluate(() => {
    const svg = document.querySelector('[data-testid="ecosystem-map-svg"]');
    if (!svg) return [];
    return [...svg.querySelectorAll("text")]
      .filter((el) => {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      })
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return {
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          text: el.textContent ?? ""
        };
      });
  });
}

function overlapArea(a: Box, b: Box): number {
  const width = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const height = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return Math.max(0, width) * Math.max(0, height);
}

function assertZeroOverlap(boxes: Box[], context: string) {
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const area = overlapArea(boxes[i], boxes[j]);
      expect(
        area,
        `${context}: "${boxes[i].text}" 与 "${boxes[j].text}" 的 bbox 相交面积 ${area.toFixed(1)}px² 应为 0`
      ).toBe(0);
    }
  }
}

test("default graph renders zero overlapping text labels at L1", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
  // 等待入场编排结束再量测（stagger 总预算 ≤600ms + 余量）。
  await page.waitForTimeout(1200);

  const boxes = await visibleSvgTextBoxes(page);
  expect(boxes.length).toBeGreaterThan(0);
  assertZeroOverlap(boxes, "默认图 L1");

  // §F.5 主观口径落硬指标：L1 下可读节点标签 ≤12（边标签另计）。
  const nodeLabelCount = await page.evaluate(() => {
    const svg = document.querySelector('[data-testid="ecosystem-map-svg"]');
    if (!svg) return 0;
    return [...svg.querySelectorAll(".node > text")].filter((el) => {
      const style = getComputedStyle(el);
      return style.display !== "none" && style.visibility !== "hidden";
    }).length;
  });
  expect(nodeLabelCount).toBeLessThanOrEqual(12);

  // §F.4：不存在重复的类型说明常显文本（nodeStage/nodeRole 已废除）。
  expect(await page.locator(".nodeStage").count()).toBe(0);
  expect(await page.locator(".nodeRole").count()).toBe(0);
});

test("rerooted graph keeps zero overlapping text labels", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
  await page.getByTestId("search-reroot-tsmc").click();
  await expect(page.getByTestId("current-focus-title")).toHaveText("Synthetic Advanced Foundry");
  await page.waitForTimeout(1200);

  const boxes = await visibleSvgTextBoxes(page);
  expect(boxes.length).toBeGreaterThan(0);
  assertZeroOverlap(boxes, "reroot 后");
});

test("L2 and L3 zoom levels also keep labels overlap-free", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
  await page.waitForTimeout(1200);
  for (const zoom of ["L2", "L3"]) {
    await page.getByTestId(`zoom-${zoom}`).click();
    await page.waitForTimeout(250);
    const boxes = await visibleSvgTextBoxes(page);
    assertZeroOverlap(boxes, `缩放 ${zoom}`);
  }
});

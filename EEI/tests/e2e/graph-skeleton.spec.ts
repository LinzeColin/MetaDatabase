import { expect, test } from "@playwright/test";

// P2-12 图谱骨架补全 e2e 契约（UX_SPEC_EEI v1.0 §G-P2-12）。
// minimap 大图定位 + Undo/Redo 探索回退栈 + 「按关系类型/方向展开」子菜单。
// 本机 dev 走本地样例图（CLOUD_MODE off）：reroot 经 setCenter → recordNav。

test("undo/redo steps back and forward through the exploration trail", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });

  const title = page.getByTestId("current-focus-title");
  const initial = (await title.textContent())?.trim() ?? "";

  // 初始焦点无上一步：undo 禁用。
  await expect(page.getByTestId("graph-undo")).toBeDisabled();

  // reroot 到 TSMC 代工。
  await page.getByTestId("search-reroot-tsmc").click();
  await expect(title).toHaveText("Synthetic Advanced Foundry");
  await expect(page.getByTestId("graph-undo")).toBeEnabled();

  // Undo → 回到初始焦点。
  await page.getByTestId("graph-undo").click();
  await expect(title).toHaveText(initial);
  await expect(page.getByTestId("graph-redo")).toBeEnabled();

  // Redo → 前进回 TSMC 代工。
  await page.getByTestId("graph-redo").click();
  await expect(title).toHaveText("Synthetic Advanced Foundry");
});

test("minimap renders the graph and reroots on node click", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
  await page.waitForTimeout(700);

  const minimap = page.getByTestId("graph-minimap");
  await expect(minimap).toBeVisible();
  // 缩略图节点与主图同构（数量 > 1）。
  const dots = minimap.locator('[data-testid^="minimap-node-"]');
  expect(await dots.count()).toBeGreaterThan(1);
  // 焦点节点有高亮环。
  await expect(minimap.locator(".minimapNode.isFocus")).toHaveCount(1);

  // 点缩略图上的代工节点 → 换中心（走同一 reroot 漏斗，undo 随之可用）。
  await minimap.getByTestId("minimap-node-foundry").click();
  await expect(page.getByTestId("graph-undo")).toBeEnabled();
});

test("expand-by-relationship submenu focuses a type and highlights its edges", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });

  const toggle = page.getByTestId("expand-menu-toggle");
  await expect(toggle).toBeEnabled();
  await toggle.click();

  const list = page.getByTestId("expand-menu-list");
  await expect(list).toBeVisible();
  const firstType = list.locator('[data-testid^="expand-type-"]').first();
  await expect(firstType).toBeVisible();

  await firstType.click();
  await expect(firstType).toHaveAttribute("data-active", "true");
  await expect(page.getByTestId("expand-focus-note")).toBeVisible();
  // 至少一条匹配边被标记高亮。
  await expect(page.locator('.edgeGroup[data-expand-active="true"]').first()).toBeVisible();

  // 清除聚焦。
  await page.getByTestId("expand-focus-clear").click();
  await expect(page.getByTestId("expand-focus-note")).toHaveCount(0);
});

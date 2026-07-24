import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const savedViewApiBaseStorageKey = "eei.apiBaseUrl.v1";
const productionDataApiBaseStorageKey = "eei.productionDataApiBaseUrl.v1";
const modelApiBaseStorageKey = "eei.modelApiBaseUrl.v1";
const savedViewStorageKey = "eei.savedView.current.v1";
const liveApiBaseUrl = process.env.EEI_LIVE_API_BASE_URL ?? "http://127.0.0.1:8000";

test.describe.configure({ mode: "serial" });

async function configureApiBase(context: BrowserContext) {
  await context.addInitScript(
    ({ storageKey, apiBaseUrl }: { storageKey: string; apiBaseUrl: string }) =>
      window.localStorage.setItem(storageKey, apiBaseUrl),
    { storageKey: savedViewApiBaseStorageKey, apiBaseUrl: liveApiBaseUrl }
  );
  await context.addInitScript(
    ({ storageKey, apiBaseUrl }: { storageKey: string; apiBaseUrl: string }) =>
      window.localStorage.setItem(storageKey, apiBaseUrl),
    { storageKey: productionDataApiBaseStorageKey, apiBaseUrl: liveApiBaseUrl }
  );
  await context.addInitScript(
    ({ storageKey, apiBaseUrl }: { storageKey: string; apiBaseUrl: string }) =>
      window.localStorage.setItem(storageKey, apiBaseUrl),
    { storageKey: modelApiBaseStorageKey, apiBaseUrl: liveApiBaseUrl }
  );
}

async function seedSavedView(context: BrowserContext, savedViewPayload: string) {
  await context.addInitScript(
    ({ storageKey, payload }: { storageKey: string; payload: string }) =>
      window.localStorage.setItem(storageKey, payload),
    { storageKey: savedViewStorageKey, payload: savedViewPayload }
  );
}

async function expectCloudState(page: Page) {
  await expect(page.getByTestId("current-focus-title")).toHaveText("Synthetic Cloud Customer");
  await expect(page.getByTestId("selected-node-title")).toHaveText("Synthetic AI Data Center Campus");
  await expect(page.getByTestId("workspace-shell")).toHaveAttribute("data-semantic-zoom", "L2");
  await expect(page.getByTestId("workspace-shell")).toHaveAttribute("data-active-time", "2026-06-12");
}

test("A207 live multi-session saved-view conflict resolves from FastAPI PostgreSQL", async ({
  browser
}) => {
  const firstContext = await browser.newContext();
  await configureApiBase(firstContext);
  const firstPage = await firstContext.newPage();

  await firstPage.goto(
    "/?subject=cloud&selected=datacenter&lens=supply_chain&zoom=L2&asOf=2026-06-12&path=nvidia.cloud"
  );
  await expectCloudState(firstPage);
  await firstPage.getByTestId("save-current-view").click();
  await expect(firstPage.getByTestId("saved-view-status")).toHaveText("已保存（云端）");
  await expect(firstPage.getByTestId("saved-view-panel")).toHaveAttribute("data-sync-mode", "server");
  await expect(firstPage.getByTestId("saved-view-panel")).toHaveAttribute("data-server-version", "1");
  const serverId = await firstPage.getByTestId("saved-view-panel").getAttribute("data-server-id");
  expect(serverId).toMatch(/^[0-9a-f-]{36}$/);

  const savedViewPayload = await firstPage.evaluate((storageKey) => {
    const payload = window.localStorage.getItem(storageKey);
    if (!payload) throw new Error("missing saved view payload");
    return payload;
  }, savedViewStorageKey);

  const secondContext = await browser.newContext();
  await configureApiBase(secondContext);
  await seedSavedView(secondContext, savedViewPayload);
  const secondPage = await secondContext.newPage();
  await secondPage.goto(
    "/?subject=cloud&selected=datacenter&lens=supply_chain&zoom=L2&asOf=2026-06-12&path=nvidia.cloud"
  );
  await expectCloudState(secondPage);
  await secondPage.getByTestId("lens-policy_risk").click();
  await secondPage.getByTestId("save-current-view").click();
  await expect(secondPage.getByTestId("saved-view-status")).toHaveText("已保存（云端）");
  await expect(secondPage.getByTestId("saved-view-panel")).toHaveAttribute(
    "data-server-version",
    "2"
  );

  await firstPage.getByTestId("lens-business_segments").click();
  await firstPage.getByTestId("save-current-view").click();
  await expect(firstPage.getByTestId("saved-view-status")).toHaveText("云端版本冲突");
  await expect(firstPage.getByTestId("saved-view-panel")).toHaveAttribute(
    "data-sync-reason",
    "stale_saved_view_version"
  );
  await expect(firstPage.getByTestId("resolve-saved-view-conflict")).toBeVisible();

  await firstPage.getByTestId("resolve-saved-view-conflict").click();
  await expect(firstPage.getByTestId("saved-view-status")).toHaveText(
    "server-conflict-resolved"
  );
  await expect(firstPage.getByTestId("saved-view-panel")).toHaveAttribute(
    "data-server-version",
    "2"
  );
  await expect(firstPage.getByTestId("saved-view-panel")).toHaveAttribute(
    "data-sync-reason",
    "resolved_latest"
  );
  await expect(firstPage.getByTestId("workspace-shell")).toHaveAttribute(
    "data-active-lens",
    "policy_risk"
  );

  await firstContext.close();
  await secondContext.close();
});

test("A204 and A205 live model activation refreshes and rolls back through FastAPI PostgreSQL", async ({
  browser
}) => {
  const context = await browser.newContext();
  await configureApiBase(context);
  const page = await context.newPage();
  const uuidPattern = /^[0-9a-f-]{36}$/;

  await page.goto("/");
  const panel = page.getByTestId("model-preview-panel");
  const status = page.getByTestId("model-activation-status");
  const workspace = page.getByTestId("workspace-shell");

  await expect(status).toHaveText("server-current");
  await expect(panel).toHaveAttribute("data-model-sync-mode", "server");
  await expect(panel).toHaveAttribute("data-active-profile-id", uuidPattern);
  await expect(panel).toHaveAttribute("data-target-profile-id", uuidPattern);
  await expect(workspace).toHaveAttribute("data-active-profile-version", "balanced-v2@2");

  const initialActiveProfileId = await panel.getAttribute("data-active-profile-id");
  const targetProfileId = await panel.getAttribute("data-target-profile-id");
  const initialRefreshGeneration = Number(
    await panel.getAttribute("data-model-refresh-generation")
  );
  if (!initialActiveProfileId || !targetProfileId) {
    throw new Error("missing model activation profile ids");
  }
  expect(initialActiveProfileId).toMatch(uuidPattern);
  expect(targetProfileId).toMatch(uuidPattern);
  expect(targetProfileId).not.toBe(initialActiveProfileId);

  await page.getByTestId("activate-model-profile").click();
  await expect(status).toHaveText("server-activated");
  await expect(panel).toHaveAttribute("data-active-profile-id", targetProfileId);
  await expect(panel).toHaveAttribute("data-rollback-profile-id", initialActiveProfileId);
  await expect(panel).toHaveAttribute(
    "data-model-refresh-generation",
    String(initialRefreshGeneration + 1)
  );
  await expect(workspace).toHaveAttribute(
    "data-active-model-version",
    "business-empire-model-v3@3"
  );
  await expect(workspace).toHaveAttribute("data-active-profile-version", "supply-chain-v3@3");
  await expect(workspace).toHaveAttribute("data-active-score-snapshot", uuidPattern);
  const activatedScoreSnapshot = await workspace.getAttribute("data-active-score-snapshot");

  await page.getByTestId("check-model-refresh").click();
  await expect(status).toHaveText("server-refreshed");
  await expect(panel).toHaveAttribute("data-client-state", "stale");
  await expect(panel).toHaveAttribute("data-model-sync-reason", "stale_client_refetched");
  await expect(panel).toHaveAttribute("data-active-profile-id", targetProfileId);

  await page.getByTestId("rollback-model-activation").click();
  await expect(status).toHaveText("server-activated");
  await expect(panel).toHaveAttribute("data-active-profile-id", initialActiveProfileId);
  await expect(panel).toHaveAttribute("data-rollback-profile-id", targetProfileId);
  await expect(panel).toHaveAttribute(
    "data-model-refresh-generation",
    String(initialRefreshGeneration + 2)
  );
  await expect(workspace).toHaveAttribute("data-active-profile-version", "balanced-v2@2");
  await expect(workspace).toHaveAttribute("data-active-score-snapshot", uuidPattern);
  const rollbackScoreSnapshot = await workspace.getAttribute("data-active-score-snapshot");
  expect(rollbackScoreSnapshot).not.toBe(activatedScoreSnapshot);

  await context.close();
});

test("A211 live production routes and data controls hydrate from FastAPI PostgreSQL", async ({
  browser
}) => {
  const context = await browser.newContext();
  await configureApiBase(context);
  const page = await context.newPage();

  await page.goto("/");

  const graphPanel = page.getByTestId("production-graph-context");
  const dataPanel = page.getByTestId("production-data-context");
  const freshnessPanel = page.getByTestId("home-freshness");

  await expect(page.getByTestId("workspace-context-contract")).toHaveAttribute(
    "data-context-version",
    "workspace-context-v1"
  );
  await expect(page.getByTestId("production-graph-status")).toHaveText(
    "server-hydrated",
    { timeout: 20_000 }
  );
  await expect(graphPanel).toHaveAttribute("data-graph-sync-mode", "server");
  await expect(graphPanel).toHaveAttribute("data-graph-endpoint", /\/v1\/explore$/);
  await expect(graphPanel).toHaveAttribute("data-server-node-count", /^[1-9]\d*$/);
  await expect(graphPanel).toHaveAttribute("data-server-edge-count", /^[1-9]\d*$/);
  await expect(graphPanel).toHaveAttribute("data-candidate-total-count", /^[1-9]\d*$/);
  await expect(graphPanel).toHaveAttribute("data-relationship-candidates-in-graph", "false");
  await expect(graphPanel).toHaveAttribute("data-min-independent-sources", "2");
  await expect(page.getByTestId("production-graph-publication-gate")).toContainText(
    "candidates-in-graph=false"
  );

  await expect(page.getByTestId("production-data-status")).toHaveText(
    "server-hydrated / server-hydrated / server-hydrated",
    { timeout: 20_000 }
  );
  await expect(dataPanel).toHaveAttribute("data-catalog-sync-mode", "server");
  await expect(dataPanel).toHaveAttribute("data-score-sync-mode", "server");
  await expect(dataPanel).toHaveAttribute("data-evidence-sync-mode", "server");
  await expect(dataPanel).toHaveAttribute("data-catalog-count", /^[1-9]\d*$/);
  await expect(dataPanel).toHaveAttribute("data-score-evidence-count", /^[1-9]\d*$/);
  await expect(dataPanel).toHaveAttribute("data-evidence-detail-count", /^[1-9]\d*$/);
  await expect(page.getByTestId("production-score-candidate")).toContainText("GV-FACT-001");
  await expect(page.getByTestId("production-score-candidate")).toContainText("ready_for_review");
  // S9PBT02 V5 → P0-2 §E.1：KPI 条改业务量（本图规模/全库关系/数据版本）；
  // 治理流水线状态仍以 production-score-* 契约（上两行）断言。
  await expect(page.getByTestId("context-kpi-bar")).toBeVisible();
  await expect(page.getByTestId("kpi-entities")).toContainText("实体");
  await expect(page.getByTestId("kpi-relationships")).toContainText("条关系");
  await expect(page.getByTestId("kpi-published")).toContainText("全库已核实关系");
  await expect(page.getByTestId("context-kpi-bar")).toHaveAttribute(
    "data-kpi-source",
    "production-graph-context"
  );
  await expect(page.getByTestId("production-evidence-snippets")).toContainText("SEC EDGAR");
  await expect(freshnessPanel).toHaveAttribute("data-sync-mode", "server");
  await expect(freshnessPanel).toHaveAttribute("data-endpoint", /\/v1\/sources\/freshness$/);
  await expect(freshnessPanel).toHaveAttribute("data-last-attempt-at", /T/);
  await expect(freshnessPanel).toHaveAttribute("data-last-success-at", /T/);
  await expect(freshnessPanel).toHaveAttribute("data-last-failure-at", "none");
  await expect(freshnessPanel).toHaveAttribute("data-document-date", "2025-02-10T00:00:00Z");
  await expect(freshnessPanel).toHaveAttribute("data-report-period-end", "2024-12-31");
  await expect(freshnessPanel).toContainText("sec_edgar_synthetic_fixture");

  // P0-1 导航收敛：supply_chain 是六个一级 route 入口之一；
  // 证据中心不再是导航项（右栏常驻）。
  await expect(page.getByTestId("main-nav-supply_chain")).toHaveAttribute(
    "href",
    "/supply-chain"
  );
  await expect(page.getByTestId("main-nav-supply_chain")).toHaveAttribute(
    "data-control-kind",
    "route"
  );
  await expect(page.getByTestId("evidence-center")).toBeVisible();
  await page.getByTestId("hydrate-production-data").click();
  await expect(dataPanel).toHaveAttribute("data-score-sync-reason", "manual_refresh");
  await expect(dataPanel).toHaveAttribute("data-evidence-sync-reason", "manual_refresh");

  await page.getByTestId("main-nav-data_center").click();
  await expect(page).toHaveURL(/\/objects-scope$/);
  await expect(page.getByTestId("objects-scope-screen")).toBeVisible();

  await page.goto("/industries");
  await expect(page.getByTestId("industry-landscape-page")).toBeVisible();

  // P0-1：系统状态并入「数据与来源」，路由直达仍可用。
  await page.goto("/development-status");
  await expect(page.getByTestId("development-status-screen")).toBeVisible();

  await context.close();
});

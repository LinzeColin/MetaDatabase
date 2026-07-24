import { expect, test, type Page, type Route } from "@playwright/test";

// P2-9 「我的」抽屉 e2e 契约（UX_SPEC_EEI v1.0 §G-P2-9）。
// 本机 dev 无生产 API：注入 localStorage API base 并 mock 用户态端点，
// 验证「开合 / 三 tab 加载 / 铃铛未读角标 / 关注乐观更新 + 失败回滚」全链。
// e2e 稳定性：先等触发钮水合再交互；关注走事件桥后用 toPass 收敛断言。

const ENTITY_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

type MockOptions = {
  watchlists?: unknown;
  savedViews?: unknown;
  explorationLog?: unknown;
  changes?: unknown;
  followStatus?: number;
  unfollowStatus?: number;
};

async function installMocks(page: Page, options: MockOptions = {}): Promise<void> {
  const {
    watchlists = [],
    savedViews = [],
    explorationLog = [],
    changes = [],
    followStatus = 201,
    unfollowStatus = 204
  } = options;

  await page.addInitScript(() => {
    window.localStorage.setItem("eei.apiBaseUrl.v1", "http://127.0.0.1:3000");
  });

  // 单一路由处理器按 method + pathname 分流，避免 glob 歧义（更稳）。
  await page.route("**/v1/**", (route: Route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname;

    const json = (status: number, body: unknown) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body)
      });

    if (path === "/v1/changes") {
      return json(200, changes);
    }
    if (path === "/v1/watchlists" && method === "GET") {
      return json(200, watchlists);
    }
    if (path === "/v1/watchlists" && method === "POST") {
      return json(201, { id: "list-created", name: "我的关注", items: [] });
    }
    if (/\/v1\/watchlists\/[^/]+\/items$/.test(path) && method === "POST") {
      return json(followStatus, { watchlist_id: "list-1", entity_id: ENTITY_ID });
    }
    if (/\/v1\/watchlists\/[^/]+\/items/.test(path) && method === "DELETE") {
      return unfollowStatus >= 400
        ? json(unfollowStatus, { error: "delete_failed" })
        : route.fulfill({ status: unfollowStatus, body: "" });
    }
    if (path === "/v1/saved-views") {
      return json(200, savedViews);
    }
    if (path === "/v1/exploration-log") {
      return json(200, explorationLog);
    }
    // 其余 /v1 一律返回空数组，杜绝 dev server 404 干扰。
    return json(200, []);
  });
}

async function openDrawer(page: Page): Promise<void> {
  const trigger = page.getByTestId("my-drawer-trigger");
  await expect(trigger).toBeVisible();
  await expect(async () => {
    if ((await page.getByTestId("my-drawer-overlay").count()) === 0) {
      await trigger.click();
    }
    await expect(page.getByTestId("my-drawer-panel")).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 15000 });
}

test("opens and closes the drawer", async ({ page }) => {
  await installMocks(page);
  await page.goto("/");
  await openDrawer(page);
  await page.getByTestId("my-drawer-close").click();
  await expect(page.getByTestId("my-drawer-panel")).toHaveCount(0);
});

test("bell badge reflects unread change count", async ({ page }) => {
  await installMocks(page, { changes: [{ id: "c1" }, { id: "c2" }, { id: "c3" }] });
  await page.goto("/");
  const badge = page.getByTestId("my-drawer-unread-badge");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("3");
});

test("watchlist tab lists followed entities from the API", async ({ page }) => {
  await installMocks(page, {
    watchlists: [
      { id: "list-1", name: "我的关注", items: [{ entity_id: ENTITY_ID, added_at: null }] }
    ]
  });
  await page.goto("/");
  await openDrawer(page);
  await expect(page.getByTestId(`my-drawer-watch-item-${ENTITY_ID}`)).toBeVisible();
});

test("saved views tab loads and history tab loads on demand", async ({ page }) => {
  await installMocks(page, {
    savedViews: [{ id: "sv-1", name: "半导体焦点", updated_at: "2026-07-17T05:50:00Z" }],
    explorationLog: [
      { id: "log-1", action: "reroot", focus_entity_id: ENTITY_ID, created_at: "2026-07-17T05:50:00Z" }
    ]
  });
  await page.goto("/");
  await openDrawer(page);

  await page.getByTestId("my-drawer-tab-saved").click();
  await expect(page.getByTestId("my-drawer-saved-item-sv-1")).toBeVisible();
  await expect(page.getByTestId("my-drawer-saved-item-sv-1")).toContainText("半导体焦点");

  await page.getByTestId("my-drawer-tab-history").click();
  await expect(page.getByTestId("my-drawer-hist-item-log-1")).toBeVisible();
  await expect(page.getByTestId("my-drawer-hist-item-log-1")).toContainText("换中心");
});

test("empty watchlist shows the honest not-created state", async ({ page }) => {
  await installMocks(page, { watchlists: [] });
  await page.goto("/");
  await openDrawer(page);
  const empty = page.getByTestId("my-drawer-watchlist-empty");
  await expect(empty).toBeVisible();
  await expect(empty).toContainText("还没有关注");
});

// 事件桥：图谱「加入关注」在云模式派发 eei:watchlist-follow；此处直接派发以解耦。
// SSR 按钮先可见、客户端稍后才水合并挂监听——一次性 CustomEvent 若早于挂载即丢失
// （同 command-search 键盘监听 race）。故用 toPass 重试派发，直到抽屉打开为证。
async function dispatchFollowUntilOpen(page: Page): Promise<void> {
  await expect(page.getByTestId("my-drawer-trigger")).toBeVisible();
  await expect(async () => {
    await page.evaluate((id) => {
      window.dispatchEvent(
        new CustomEvent("eei:watchlist-follow", { detail: { entity_id: id, label: "NVIDIA" } })
      );
    }, ENTITY_ID);
    await expect(page.getByTestId("my-drawer-panel")).toBeVisible({ timeout: 800 });
  }).toPass({ timeout: 15000 });
}

test("optimistic follow adds the entity and persists on success", async ({ page }) => {
  await installMocks(page, {
    watchlists: [{ id: "list-1", name: "我的关注", items: [] }],
    followStatus: 201
  });
  await page.goto("/");
  await dispatchFollowUntilOpen(page);
  // 乐观插入；POST 成功后条目保留。
  await expect(page.getByTestId(`my-drawer-watch-item-${ENTITY_ID}`)).toBeVisible();
  await page.waitForTimeout(400);
  await expect(page.getByTestId(`my-drawer-watch-item-${ENTITY_ID}`)).toBeVisible();
});

test("optimistic follow rolls back and surfaces an error on failure", async ({ page }) => {
  await installMocks(page, {
    watchlists: [{ id: "list-1", name: "我的关注", items: [] }],
    followStatus: 500
  });
  await page.goto("/");
  await dispatchFollowUntilOpen(page);
  // 乐观插入后 POST 失败 → 回滚（条目消失）+ 错误反馈（ErrorState）。
  await expect(page.getByTestId("my-drawer-action-error")).toBeVisible();
  await expect(page.getByTestId(`my-drawer-watch-item-${ENTITY_ID}`)).toHaveCount(0);
});

test("optimistic unfollow removes the entity on success", async ({ page }) => {
  await installMocks(page, {
    watchlists: [
      { id: "list-1", name: "我的关注", items: [{ entity_id: ENTITY_ID, added_at: null }] }
    ],
    unfollowStatus: 204
  });
  await page.goto("/");
  await openDrawer(page);
  const item = page.getByTestId(`my-drawer-watch-item-${ENTITY_ID}`);
  await expect(item).toBeVisible();
  await page.getByTestId(`my-drawer-unfollow-${ENTITY_ID}`).click();
  await expect(item).toHaveCount(0);
});

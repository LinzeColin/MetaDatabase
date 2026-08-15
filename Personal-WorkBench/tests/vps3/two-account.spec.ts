import { expect, test, type APIRequestContext, type Browser, type BrowserContext } from "@playwright/test";

const accountA = {
  email: process.env.PWB_TEST_ACCOUNT_A_EMAIL || "",
  password: process.env.PWB_TEST_ACCOUNT_A_PASSWORD || "",
};
const origin = (process.env.PWB_BASE_URL || "http://127.0.0.1:3000").replace(/\/$/, "");

const accountB = {
  email: process.env.PWB_TEST_ACCOUNT_B_EMAIL || "",
  password: process.env.PWB_TEST_ACCOUNT_B_PASSWORD || "",
};

async function signIn(browser: Browser, account: { email: string; password: string }): Promise<BrowserContext> {
  const context = await browser.newContext();
  const page = await context.newPage();
  // The sign-in screen keeps third-party challenge connectivity alive, so
  // `networkidle` is not a meaningful readiness signal here.  Wait for the
  // document and let the accessible controls below prove the form is ready.
  await page.goto("/auth/sign-in", { waitUntil: "domcontentloaded" });
  await page.getByLabel("邮箱").fill(account.email);
  await page.getByLabel("密码").fill(account.password);
  // A real Turnstile token is required in VPS3.  Do not submit before the
  // challenge has actually completed, or the page correctly rejects the
  // request without starting an authentication transaction.
  await expect(page.locator('input[name="cf-turnstile-response"]')).not.toHaveValue("", { timeout: 30_000 });
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(/view=home/, { timeout: 30_000 });
  return context;
}

async function json(request: APIRequestContext, method: "get" | "post" | "patch" | "delete", url: string, data?: object) {
  const mutation = method !== "get";
  const requestUrl = mutation
    ? `${url}${url.includes("?") ? "&" : "?"}request_id=${encodeURIComponent(crypto.randomUUID())}`
    : url;
  const response = await request[method](requestUrl, {
    data,
    headers: {
      ...(data ? { "content-type": "application/json" } : {}),
      ...(mutation ? { origin } : {}),
    },
  });
  expect(response.ok(), `${method.toUpperCase()} ${requestUrl}: ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

test.describe("real production two-account transaction", () => {
  test.beforeAll(() => {
    if (!accountA.email || !accountA.password || !accountB.email || !accountB.password) {
      throw new Error("Provide two verified disposable production accounts before Phase C acceptance.");
    }
  });

  test("account A persists a todo across refresh and a second browser; account B cannot see it", async ({ browser }) => {
    test.setTimeout(90_000);
    const marker = `PWB-${Date.now()}`;
    const contextA = await signIn(browser, accountA);
    const pageA = await contextA.newPage();
    await pageA.goto("/?view=todo", { waitUntil: "networkidle" });
    const title = pageA.locator('input').first();
    await title.fill(marker);
    await pageA.getByRole("button", { name: /添加|保存/ }).last().click();
    await expect(pageA.getByText(marker)).toBeVisible();
    await pageA.reload({ waitUntil: "networkidle" });
    await expect(pageA.getByText(marker)).toBeVisible();

    const storage = await contextA.storageState();
    const secondDeviceA = await browser.newContext({ storageState: storage });
    const secondPageA = await secondDeviceA.newPage();
    await secondPageA.goto("/?view=todo", { waitUntil: "networkidle" });
    await expect(secondPageA.getByText(marker)).toBeVisible();

    const contextB = await signIn(browser, accountB);
    const pageB = await contextB.newPage();
    await pageB.goto("/?view=todo", { waitUntil: "networkidle" });
    await expect(pageB.getByText(marker)).toHaveCount(0);

    await contextB.close();
    await secondDeviceA.close();
    await contextA.close();
  });

  test("all existing resource APIs enforce account isolation", async ({ browser }) => {
    test.setTimeout(90_000);
    const contextA = await signIn(browser, accountA);
    const contextB = await signIn(browser, accountB);
    const requestA = contextA.request;
    const requestB = contextB.request;
    const today = new Date().toISOString().slice(0, 10);
    const slot = Date.now();
    const uniqueMonth = String((Math.floor(slot / 1000) % 12) + 1).padStart(2, "0");
    const uniqueDay = String((Math.floor(slot / 12000) % 28) + 1).padStart(2, "0");
    const uniqueDate = `2099-${uniqueMonth}-${uniqueDay}`;
    const now = Date.now();

    const cases: Array<[string, Record<string, unknown>]> = [
      ["habits", { title: "验收习惯", iconKey: "habit_read.png", sortOrder: 1, active: true }],
      ["todos", { title: "验收待办", note: "", dueDate: today, priority: "normal", completed: false, completedAt: null }],
      ["ledger", { kind: "expense", amountCents: 123, currency: "CNY", localDate: today, category: "验收", note: "" }],
      ["food", { foodName: "验收食物", calories: 10, meal: "breakfast", localDate: today, note: "", photoObjectId: null, source: "manual" }],
      ["exercise", { activity: "验收运动", durationMinutes: 10, caloriesBurned: 1, localDate: today, note: "" }],
      ["weights", { weightGrams: 60000, localDate: uniqueDate, note: "" }],
      ["schedule", { title: "验收日程", note: "", startsAt: now, endsAt: now + 3_600_000, allDay: false }],
      ["anniversaries", { title: "验收纪念", localDate: today, repeatYearly: true, note: "" }],
      ["diary", { localDate: today, mood: "好", title: "验收日记", body: "实际环境事务", photoObjectId: null }],
      ["savings-goals", { title: "验收存钱", targetCents: 10000, currency: "CNY", targetDate: today, archived: false }],
      ["periods", { startDate: uniqueDate, endDate: uniqueDate, note: "" }],
    ];

    for (const [resource, payload] of cases) {
      const created = await json(requestA, "post", `/api/mydairy/${resource}`, payload);
      const id = created.data.id as string;
      const listA = await json(requestA, "get", `/api/mydairy/${resource}`);
      expect(listA.data.some((row: { id: string }) => row.id === id)).toBeTruthy();
      const listB = await json(requestB, "get", `/api/mydairy/${resource}`);
      expect(listB.data.some((row: { id: string }) => row.id === id)).toBeFalsy();
      await json(requestA, "delete", `/api/mydairy/${resource}/${encodeURIComponent(id)}`);
    }

    await contextB.close();
    await contextA.close();
  });
});

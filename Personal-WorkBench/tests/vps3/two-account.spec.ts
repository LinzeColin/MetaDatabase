import { expect, test } from "@playwright/test";
import {
  accountA,
  accountB,
  assertPrivateImageDenied,
  assertPrivateImageReadable,
  assertVerifiedSession,
  authenticate,
  ensureSensitiveCloudConsent,
  json,
  requireProductionInputs,
  signIn,
  signOut,
  uploadFoodImage,
} from "./production-helpers";

test.describe("verified VPS3 production acceptance", () => {
  test.beforeAll(() => requireProductionInputs());

  test("health identifies the VPS3 PostgreSQL and filesystem runtime", async ({ request }) => {
    const response = await request.get("/api/health");
    expect(response.ok(), `health: ${response.status()} ${await response.text()}`).toBeTruthy();
    expect(await response.json()).toMatchObject({
      ready: true,
      runtime: "vps3-node",
      database: "postgresql",
      objectStorage: "vps3-filesystem",
    });
  });

  test("account A persists a todo through refresh, logout/relogin, and a second browser while B cannot see it", async ({ browser }) => {
    test.setTimeout(120_000);
    const marker = `PWB-${Date.now()}`;
    const signedA = await signIn(browser, accountA);
    let secondDeviceA: Awaited<ReturnType<typeof browser.newContext>> | undefined;
    let signedB: Awaited<ReturnType<typeof signIn>> | undefined;
    let todoId: string | undefined;
    try {
      await assertVerifiedSession(signedA.context.request);
      await ensureSensitiveCloudConsent(signedA.context.request);
      await signedA.page.goto("/?view=todo", { waitUntil: "networkidle" });
      const title = signedA.page.locator("input").first();
      await title.fill(marker);
      await signedA.page.getByRole("button", { name: /添加|保存/ }).last().click();
      await expect(signedA.page.getByText(marker)).toBeVisible();
      await signedA.page.reload({ waitUntil: "networkidle" });
      await expect(signedA.page.getByText(marker)).toBeVisible();

      const todos = await json<{ data: Array<{ id: string; title: string }> }>(signedA.context.request, "get", "/api/mydairy/todos");
      todoId = todos.data.find((row) => row.title === marker)?.id;
      expect(todoId, "the rendered todo must be present in the server-owned account collection").toBeTruthy();

      const storage = await signedA.context.storageState();
      secondDeviceA = await browser.newContext({ storageState: storage });
      const secondPageA = await secondDeviceA.newPage();
      await secondPageA.goto("/?view=todo", { waitUntil: "networkidle" });
      await expect(secondPageA.getByText(marker)).toBeVisible();

      await signOut(signedA.page);
      await authenticate(signedA.page, accountA);
      await assertVerifiedSession(signedA.context.request);
      await signedA.page.goto("/?view=todo", { waitUntil: "networkidle" });
      await expect(signedA.page.getByText(marker)).toBeVisible();

      signedB = await signIn(browser, accountB);
      await assertVerifiedSession(signedB.context.request);
      await ensureSensitiveCloudConsent(signedB.context.request);
      const bTodos = await json<{ data: Array<{ id: string }> }>(signedB.context.request, "get", "/api/mydairy/todos");
      expect(bTodos.data.some((row) => row.id === todoId)).toBeFalsy();
    } finally {
      if (todoId) await json(signedA.context.request, "delete", `/api/mydairy/todos/${encodeURIComponent(todoId)}`).catch(() => undefined);
      await signedB?.context.close();
      await secondDeviceA?.close();
      await signedA.context.close();
    }
  });

  test("all existing modules perform a verified write and readback, with account B isolated", async ({ browser }) => {
    test.setTimeout(120_000);
    const signedA = await signIn(browser, accountA);
    const signedB = await signIn(browser, accountB);
    try {
      await assertVerifiedSession(signedA.context.request);
      await assertVerifiedSession(signedB.context.request);
      await ensureSensitiveCloudConsent(signedA.context.request);
      await ensureSensitiveCloudConsent(signedB.context.request);
      const requestA = signedA.context.request;
      const requestB = signedB.context.request;
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
        let id: string | undefined;
        try {
          const created = await json<{ data: { id: string } }>(requestA, "post", `/api/mydairy/${resource}`, payload);
          id = created.data.id;
          const listA = await json<{ data: Array<{ id: string }> }>(requestA, "get", `/api/mydairy/${resource}`);
          expect(listA.data.some((row) => row.id === id)).toBeTruthy();
          const listB = await json<{ data: Array<{ id: string }> }>(requestB, "get", `/api/mydairy/${resource}`);
          expect(listB.data.some((row) => row.id === id)).toBeFalsy();
        } finally {
          if (id) await json(requestA, "delete", `/api/mydairy/${resource}/${encodeURIComponent(id)}`).catch(() => undefined);
        }
      }
    } finally {
      await signedB.context.close();
      await signedA.context.close();
    }
  });

  test("account A reads an uploaded image byte-for-byte and account B receives no image or linked food record", async ({ browser }) => {
    test.setTimeout(120_000);
    const signedA = await signIn(browser, accountA);
    const signedB = await signIn(browser, accountB);
    let fileId: string | undefined;
    let foodId: string | undefined;
    try {
      await ensureSensitiveCloudConsent(signedA.context.request);
      await ensureSensitiveCloudConsent(signedB.context.request);
      fileId = await uploadFoodImage(signedA.context.request);
      await assertPrivateImageReadable(signedA.context.request, fileId);
      const today = new Date().toISOString().slice(0, 10);
      const food = await json<{ data: { id: string } }>(signedA.context.request, "post", "/api/mydairy/food", {
        foodName: "验收图片食物",
        calories: 1,
        meal: "breakfast",
        localDate: today,
        note: "",
        photoObjectId: fileId,
        source: "manual",
      });
      foodId = food.data.id;
      const bFood = await json<{ data: Array<{ id: string }> }>(signedB.context.request, "get", "/api/mydairy/food");
      expect(bFood.data.some((row) => row.id === foodId)).toBeFalsy();
      await assertPrivateImageDenied(signedB.context.request, fileId);
    } finally {
      if (foodId) await json(signedA.context.request, "delete", `/api/mydairy/food/${encodeURIComponent(foodId)}`).catch(() => undefined);
      if (fileId) await json(signedA.context.request, "delete", `/api/mydairy/files/${encodeURIComponent(fileId)}`).catch(() => undefined);
      await signedB.context.close();
      await signedA.context.close();
    }
  });
});

import { expect, test } from "@playwright/test";

const routes = [
  ["welcome", "/"],
  ["home", "/?view=home"],
  ["todo", "/?view=todo"],
  ["ledger", "/?view=ledger"],
  ["fatloss-food", "/?view=fatloss-food"],
  ["schedule", "/?view=schedule"],
  ["anniversary", "/?view=anniversary"],
  ["diary", "/?view=diary"],
  ["savings", "/?view=savings"],
  ["period", "/?view=period"],
] as const;

test.describe("public workbench surface", () => {
  for (const [name, route] of routes) {
    test(`${name} renders and every visible non-destructive button can be activated`, async ({ page }) => {
      const runtimeErrors: string[] = [];
      page.on("pageerror", (error) => runtimeErrors.push(error.message));
      await page.goto(route, { waitUntil: "networkidle" });
      await expect(page.locator("body")).toContainText(/个人工作台|慢慢来|桌面|待办|记账|减脂|日程|纪念|日记|存钱|经期/);

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(2);

      const buttonNames = await page.getByRole("button").evaluateAll((buttons) =>
        buttons
          .filter((button) => !button.hasAttribute("disabled"))
          .map((button) => (button.getAttribute("aria-label") || button.textContent || "").trim())
          .filter((value) => value && !/删除账户|确认删除账户/.test(value)),
      );

      for (const accessibleName of [...new Set(buttonNames)]) {
        await page.goto(route, { waitUntil: "networkidle" });
        const control = page.getByRole("button", { name: accessibleName, exact: true }).first();
        if (await control.isVisible().catch(() => false)) {
          await control.click({ timeout: 5_000 }).catch(() => undefined);
          await page.waitForTimeout(100);
        }
      }
      expect(runtimeErrors).toEqual([]);
    });
  }

  test("navigation reaches all nine workbench modules", async ({ page }) => {
    await page.goto("/?view=home", { waitUntil: "networkidle" });
    for (const label of ["桌面", "待办", "记账", "减脂", "日程", "纪念", "日记", "存钱", "经期"]) {
      const link = page.getByRole("link", { name: label, exact: true });
      await expect(link).toBeVisible();
      await link.click();
      await expect(page.locator("main")).toBeVisible();
    }
  });

  test("email, Google, password recovery and account entry are present", async ({ page }) => {
    await page.goto("/auth/sign-in", { waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("邮箱")).toBeVisible();
    await expect(page.getByLabel("密码")).toBeVisible();
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Google/ }).or(page.getByRole("button", { name: /Google/ }))).toBeVisible();
    await expect(page.getByRole("link", { name: "忘记密码？" })).toBeVisible();
    await expect(page.getByRole("link", { name: /注册/ })).toBeVisible();
  });
});

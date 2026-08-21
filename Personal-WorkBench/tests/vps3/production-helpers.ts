import { expect, type APIRequestContext, type Browser, type BrowserContext, type Page } from "@playwright/test";

type Account = { email: string; password: string };

export const accountA: Account = {
  email: process.env.PWB_TEST_ACCOUNT_A_EMAIL || "",
  password: process.env.PWB_TEST_ACCOUNT_A_PASSWORD || "",
};

export const accountB: Account = {
  email: process.env.PWB_TEST_ACCOUNT_B_EMAIL || "",
  password: process.env.PWB_TEST_ACCOUNT_B_PASSWORD || "",
};

export const origin = (process.env.PWB_BASE_URL || "http://127.0.0.1:3000").replace(/\/$/, "");

// A complete, harmless 1×1 PNG. It verifies the actual multipart upload and
// byte-for-byte private readback path rather than only file metadata.
export const tinyPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9F5lQAAAAASUVORK5CYII=",
  "base64",
);

function requireTimestamp(name: string) {
  const value = process.env[name]?.trim() || "";
  if (!value || Number.isNaN(Date.parse(value))) {
    throw new Error(`${name} must be the ISO timestamp recorded after the real registration and email-verification flow.`);
  }
}

export function requireProductionInputs() {
  if (!accountA.email || !accountA.password || !accountB.email || !accountB.password) {
    throw new Error("Provide two verified disposable production accounts before VPS3 production acceptance.");
  }
  requireTimestamp("PWB_TEST_ACCOUNT_A_VERIFIED_AT");
  requireTimestamp("PWB_TEST_ACCOUNT_B_VERIFIED_AT");
}

function mutationUrl(url: string) {
  return `${url}${url.includes("?") ? "&" : "?"}request_id=${encodeURIComponent(crypto.randomUUID())}`;
}

export async function json<T>(
  request: APIRequestContext,
  method: "get" | "post" | "patch" | "delete",
  url: string,
  data?: object,
): Promise<T> {
  const mutation = method !== "get";
  const requestUrl = mutation ? mutationUrl(url) : url;
  const response = await request[method](requestUrl, {
    data,
    headers: {
      ...(data ? { "content-type": "application/json" } : {}),
      ...(mutation ? { origin } : {}),
    },
  });
  expect(response.ok(), `${method.toUpperCase()} ${requestUrl}: ${response.status()} ${await response.text()}`).toBeTruthy();
  return (await response.json()) as T;
}

export async function authenticate(page: Page, account: Account) {
  // Turnstile keeps a third-party connection open, so DOM readiness and the
  // accessible controls are the stable readiness contract for this page.
  await page.goto("/auth/sign-in", { waitUntil: "domcontentloaded" });
  await page.getByLabel("邮箱").fill(account.email);
  await page.getByLabel("密码").fill(account.password);
  await expect(page.locator('input[name="cf-turnstile-response"]')).not.toHaveValue("", { timeout: 30_000 });
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(/view=home/, { timeout: 30_000 });
}

export async function signIn(browser: Browser, account: Account): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await authenticate(page, account);
  return { context, page };
}

export async function signOut(page: Page) {
  const response = await page.request.post(mutationUrl("/api/auth/sign-out"), {
    data: {},
    headers: { "content-type": "application/json", origin },
  });
  expect(response.ok(), `sign-out: ${response.status()} ${await response.text()}`).toBeTruthy();
  await page.goto("/auth/sign-in?signed_out=1", { waitUntil: "domcontentloaded" });
  await expect(page.getByLabel("邮箱")).toBeVisible();
}

export async function assertVerifiedSession(request: APIRequestContext) {
  const response = await request.get("/api/auth/get-session?disableCookieCache=true");
  expect(response.ok(), `get-session: ${response.status()} ${await response.text()}`).toBeTruthy();
  const session = (await response.json()) as { user?: { emailVerified?: boolean } };
  expect(session.user?.emailVerified, "the production session must confirm email verification").toBe(true);
}

export async function ensureSensitiveCloudConsent(request: APIRequestContext) {
  const snapshot = await json<{
    state: string;
    policyVersion: string | null;
    currentVersion: string;
    noticeSha256: string | null;
    deletionState: string | null;
  }>(request, "get", "/api/account/privacy");
  if (snapshot.state === "accepted" && snapshot.policyVersion === snapshot.currentVersion && snapshot.deletionState === "active") {
    return;
  }
  expect(snapshot.noticeSha256, "privacy notice hash must be supplied by the live service").toBeTruthy();
  const updated = await json<{ state: string; policyVersion: string | null }>(request, "post", "/api/account/privacy", {
    decision: "accepted",
    policyVersion: snapshot.currentVersion,
    noticeSha256: snapshot.noticeSha256,
  });
  expect(updated.state).toBe("accepted");
  expect(updated.policyVersion).toBe(snapshot.currentVersion);
}

export async function uploadFoodImage(request: APIRequestContext): Promise<string> {
  const response = await request.post(mutationUrl("/api/mydairy/files"), {
    multipart: {
      module: "food",
      file: {
        name: "third-party-acceptance.png",
        mimeType: "image/png",
        buffer: tinyPng,
      },
    },
    headers: { origin },
  });
  expect(response.ok(), `file upload: ${response.status()} ${await response.text()}`).toBeTruthy();
  const payload = (await response.json()) as { data?: { id?: string } };
  expect(payload.data?.id).toBeTruthy();
  return payload.data!.id!;
}

export async function assertPrivateImageReadable(request: APIRequestContext, id: string) {
  const response = await request.get(`/api/mydairy/files/${encodeURIComponent(id)}`);
  expect(response.ok(), `private file read: ${response.status()} ${await response.text()}`).toBeTruthy();
  expect(response.headers()["content-type"] || "").toContain("image/png");
  expect(Buffer.compare(await response.body(), tinyPng)).toBe(0);
}

export async function assertPrivateImageDenied(request: APIRequestContext, id: string) {
  const response = await request.get(`/api/mydairy/files/${encodeURIComponent(id)}`);
  expect(response.status()).toBe(404);
}

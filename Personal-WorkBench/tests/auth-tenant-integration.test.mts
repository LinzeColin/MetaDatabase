import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import {
  createDeviceLocalRecord,
  createDeviceLocalRecoveryOutboxAction,
} from "../app/_components/workbench/local-record-cache.ts";

const origin = "http://127.0.0.1:4310";
const alphaEmail = "alpha@example.test";
const betaEmail = "beta@example.test";
const initialPassword = "LocalHarnessPassword-2026";
const resetPassword = "LocalHarnessReset-2026";

function normalizeBindingValue(value: unknown): unknown {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "boolean") return Number(value);
  return value;
}

function d1Result(changes = 0) {
  return {
    success: true,
    results: [],
    meta: {
      changed_db: changes > 0,
      changes,
      duration: 0,
      last_row_id: 0,
      rows_read: 0,
      rows_written: 0,
      size_after: 0,
    },
  };
}

/** Isolated D1-compatible adapter backed by Node's in-memory SQLite. */
function createIsolatedD1(sqlite: DatabaseSync): D1Database {
  const prepare = (sql: string) => {
    const statement = sqlite.prepare(sql);
    const bind = (...boundValues: unknown[]) => {
      const values = boundValues.map(normalizeBindingValue);
      return {
        bind: (...nextValues: unknown[]) => bind(...nextValues),
        run: async () => {
          const result = statement.run(...(values as Parameters<typeof statement.run>));
          return d1Result(Number(result.changes ?? 0));
        },
        first: async () =>
          (statement.get(...(values as Parameters<typeof statement.get>)) as Record<string, unknown> | undefined) ?? null,
        all: async () => ({
          ...d1Result(0),
          results: statement.all(...(values as Parameters<typeof statement.all>)) as Record<string, unknown>[],
        }),
        raw: async () =>
          (statement.all(...(values as Parameters<typeof statement.all>)) as Record<string, unknown>[]).map((row) => Object.values(row)),
      };
    };
    return bind();
  };

  return {
    prepare,
    batch: async (statements: Array<{ run: () => Promise<unknown> }>) => Promise.all(statements.map((statement) => statement.run())),
    exec: async (sql: string) => {
      sqlite.exec(sql);
      return { count: 0, duration: 0 };
    },
    dump: async () => new ArrayBuffer(0),
  } as unknown as D1Database;
}

function messageLink(body: unknown): string | null {
  if (typeof body !== "string") return null;
  const match = body.match(/https?:\/\/[^\s<>]+/);
  return match?.[0] ?? null;
}

function cookieHeader(response: Response): string {
  const headers = response.headers as Headers & { getSetCookie?: () => string[] };
  const values = headers.getSetCookie?.() ?? [response.headers.get("set-cookie")].filter((value): value is string => Boolean(value));
  const cookie = values.map((value) => value.split(";", 1)[0]).filter(Boolean).join("; ");
  assert.ok(cookie.length > 0, "expected a session cookie");
  return cookie;
}

function requestHeaders(cookie?: string, includeCaptcha = false): Headers {
  const value = new Headers({
    origin,
    "content-type": "application/json",
    "cf-connecting-ip": "127.0.0.1",
    "user-agent": "personal-workbench-local-harness",
  });
  if (cookie) value.set("cookie", cookie);
  if (includeCaptcha) value.set("x-captcha-response", "local-harness-response");
  return value;
}

test("local auth-to-tenant chain verifies two accounts, isolated history, and password reset", async () => {
  const sqlite = new DatabaseSync(":memory:");
  const originalFetch = globalThis.fetch;
  const capturedLinks = new Map<string, string>();
  let unexpectedOutbound = false;
  let workerEnv: Record<string, unknown> | null = null;

  try {
    globalThis.fetch = async (input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url === "https://challenges.cloudflare.com/turnstile/v0/siteverify") {
        return Response.json({ success: true, action: "workbench_auth", hostname: "127.0.0.1" });
      }
      if (url === "https://api.resend.com/emails") {
        const payload = JSON.parse(String(init?.body ?? "{}")) as { to?: unknown; text?: unknown };
        const recipient = Array.isArray(payload.to) && typeof payload.to[0] === "string" ? payload.to[0] : null;
        const link = messageLink(payload.text);
        if (!recipient || !link) throw new Error("LOCAL_MAIL_CAPTURE_INVALID");
        capturedLinks.set(recipient, link);
        return Response.json({ accepted: true }, { status: 200 });
      }
      unexpectedOutbound = true;
      throw new Error("LOCAL_HARNESS_OUTBOUND_DENIED");
    };

    sqlite.exec(await readFile(new URL("../drizzle/0001_auth_and_product.sql", import.meta.url), "utf8"));
    sqlite.exec(await readFile(new URL("../drizzle/0002_s2_tenant_indexes.sql", import.meta.url), "utf8"));
    const DB = createIsolatedD1(sqlite);
    const env = {
      DB,
      APP_ORIGIN: origin,
      APP_TRUSTED_ORIGINS: origin,
      BETTER_AUTH_SECRET: "local-harness-auth-secret-with-sufficient-length",
      GOOGLE_CLIENT_ID: "local-google-client-id",
      GOOGLE_CLIENT_SECRET: "local-google-client-secret",
      RESEND_API_KEY: "local-resend-key",
      MAIL_PROVIDER: "resend",
      MAIL_FROM: "noreply@local.test",
      TURNSTILE_SECRET_KEY: "local-turnstile-secret",
      TURNSTILE_SITE_KEY: "local-turnstile-site-key",
      LEGAL_OPERATOR_NAME: "Local Harness Operator",
      PRIVACY_CONTACT_EMAIL: "privacy@local.test",
    };

    const { createAuth } = await import("../server/auth/index.ts");
    const workerModule = await import("cloudflare:workers");
    workerEnv = workerModule.env as unknown as Record<string, unknown>;
    Object.assign(workerEnv, env);
    const googleFallbackRoute = await import("../app/auth/google/route.ts");
    const legacyLoginRoute = await import("../app/auth/login/route.ts");
    const privacyRoute = await import("../app/api/account/privacy/route.ts");
    const resourceRoute = await import("../app/api/mydairy/[resource]/route.ts");
    const { ACCOUNT_PRIVACY_NOTICE_SHA256, ACCOUNT_PRIVACY_POLICY_VERSION } = await import("../server/data/account-lifecycle.ts");
    const auth = createAuth(env);

    const fallbackGoogleStart = await googleFallbackRoute.GET(new Request(`${origin}/auth/google`, {
      headers: new Headers({ "cf-connecting-ip": "127.0.0.1" }),
    }));
    assert.equal(fallbackGoogleStart.status, 302);
    assert.equal(fallbackGoogleStart.headers.get("location"), `${origin}/auth/sign-in?google=1`);
    assert.equal(fallbackGoogleStart.headers.get("set-cookie"), null);
    assert.equal(fallbackGoogleStart.headers.get("cache-control"), "no-store");

    const retiredGoogleStart = await googleFallbackRoute.GET(new Request(
      "https://huchuliang-workbench.linzezhang35.chatgpt.site/auth/google",
    ));
    assert.equal(retiredGoogleStart.status, 302);
    assert.equal(retiredGoogleStart.headers.get("location"), "https://mydairy.linzezhang.com/auth/sign-in?google=1");
    assert.equal(retiredGoogleStart.headers.get("set-cookie"), null);

    const legacyLogin = legacyLoginRoute.GET(new Request(`${origin}/auth/login?return_to=https://invalid.example`));
    assert.equal(legacyLogin.status, 302);
    assert.equal(legacyLogin.headers.get("location"), `${origin}/auth/sign-in`);
    assert.equal(legacyLogin.headers.get("cache-control"), "no-store");
    assert.equal(legacyLogin.headers.get("referrer-policy"), "no-referrer");
    assert.equal(legacyLogin.headers.get("set-cookie"), null);

    const callAuth = (path: string, body: Record<string, unknown>, cookie?: string) =>
      auth.handler(
        new Request(`${origin}/api/auth${path}`, {
          method: "POST",
          headers: requestHeaders(cookie, true),
          body: JSON.stringify(body),
        }),
      );
    const signUp = async (email: string, name: string) => {
      const response = await callAuth("/sign-up/email", {
        name,
        email,
        password: initialPassword,
        callbackURL: `${origin}/auth/verify-email`,
      });
      assert.equal(response.status, 200);
    };
    const verify = async (email: string) => {
      const link = capturedLinks.get(email);
      assert.ok(link, "expected an intercepted verification message");
      const response = await auth.handler(new Request(link, { headers: requestHeaders() }));
      assert.ok(response.status === 200 || response.status === 302);
    };
    const signIn = async (email: string, password: string) => {
      const response = await callAuth("/sign-in/email", { email, password });
      assert.equal(response.status, 200);
      const payload = await response.json() as { token?: unknown; user?: { email?: unknown; emailVerified?: unknown } };
      assert.equal(typeof payload.token, "string");
      assert.equal(payload.user?.email, email);
      assert.equal(payload.user?.emailVerified, true);
      return cookieHeader(response);
    };
    const privacyConsent = async (cookie: string) => {
      const response = await privacyRoute.POST(
        new Request(`${origin}/api/account/privacy`, {
          method: "POST",
          headers: requestHeaders(cookie),
          body: JSON.stringify({
            decision: "accepted",
            policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
            noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
          }),
        }),
      );
      assert.equal(response.status, 200);
    };
    const context = { params: Promise.resolve({ resource: "ledger" }) };
    const createLedger = async (cookie: string, idempotencyKey: string, kind: "expense" | "income") => {
      const headers = requestHeaders(cookie);
      headers.set("idempotency-key", idempotencyKey);
      const response = await resourceRoute.POST(
        new Request(`${origin}/api/mydairy/ledger`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            kind,
            amountCents: kind === "expense" ? 1200 : 3400,
            currency: "CNY",
            localDate: "2026-08-11",
            category: "本机验证",
            note: "isolated-local-history",
          }),
        }),
        context,
      );
      assert.equal(response.status, 200);
    };
    const listLedger = async (cookie: string) => {
      const response = await resourceRoute.GET(
        new Request(`${origin}/api/mydairy/ledger`, { headers: requestHeaders(cookie) }),
        context,
      );
      assert.equal(response.status, 200);
      const payload = await response.json() as { data?: unknown[] };
      assert.ok(Array.isArray(payload.data));
      return payload.data;
    };
    const createResource = async (
      cookie: string,
      resourceName: string,
      idempotencyKey: string,
      body: Record<string, unknown>,
    ) => {
      const headers = requestHeaders(cookie);
      headers.set("idempotency-key", idempotencyKey);
      const response = await resourceRoute.POST(
        new Request(`${origin}/api/mydairy/${resourceName}`, {
          method: "POST",
          headers,
          body: JSON.stringify(body),
        }),
        { params: Promise.resolve({ resource: resourceName }) },
      );
      assert.equal(response.status, 200, resourceName);
      const payload = await response.json() as { data?: unknown };
      assert.ok(payload.data && typeof payload.data === "object" && !Array.isArray(payload.data), resourceName);
      assert.equal(typeof (payload.data as { id?: unknown }).id, "string", resourceName);
      return payload.data as { id: string };
    };
    const listResource = async (cookie: string, resourceName: string) => {
      const response = await resourceRoute.GET(
        new Request(`${origin}/api/mydairy/${resourceName}`, { headers: requestHeaders(cookie) }),
        { params: Promise.resolve({ resource: resourceName }) },
      );
      assert.equal(response.status, 200, resourceName);
      const payload = await response.json() as { data?: unknown };
      assert.ok(Array.isArray(payload.data), resourceName);
      return payload.data as Array<{ id?: unknown }>;
    };
    const createRecoveredSensitiveRecord = async (
      cookie: string,
      resourceName: "ledger" | "weights" | "diary" | "periods",
      payload: Record<string, unknown>,
    ) => {
      const local = createDeviceLocalRecord(payload, 900, `local_recovery_${resourceName}`);
      const action = createDeviceLocalRecoveryOutboxAction(resourceName, local);
      assert.ok(action);
      const headers = requestHeaders(cookie);
      headers.set("idempotency-key", action.idempotencyKey);
      const response = await resourceRoute.POST(
        new Request(`${origin}${action.endpoint}`, {
          method: "POST",
          headers,
          body: JSON.stringify(action.payload),
        }),
        { params: Promise.resolve({ resource: resourceName }) },
      );
      assert.equal(response.status, 200, resourceName);
      return action;
    };

    await signUp(alphaEmail, "Alpha");
    await signUp(betaEmail, "Beta");
    assert.equal((await callAuth("/sign-in/email", { email: alphaEmail, password: initialPassword })).status, 403);

    await verify(alphaEmail);
    await verify(betaEmail);
    const verifiedRows = sqlite.prepare('SELECT emailVerified FROM "user" WHERE email IN (?, ?)').all(alphaEmail, betaEmail) as Array<{ emailVerified: number }>;
    assert.deepEqual(verifiedRows.map((row) => row.emailVerified).sort(), [1, 1]);

    const alphaDeviceOne = await signIn(alphaEmail, initialPassword);
    const alphaDeviceTwo = await signIn(alphaEmail, initialPassword);
    const betaDevice = await signIn(betaEmail, initialPassword);
    await privacyConsent(alphaDeviceOne);
    await privacyConsent(betaDevice);

    // The account endpoint must expose the stored consent version, not mask a
    // stale consent as current. Otherwise the UI can say "enabled" while the
    // resource API correctly rejects a sensitive write.
    sqlite.prepare("UPDATE profile_settings SET privacy_policy_version = ? WHERE user_id = (SELECT id FROM \"user\" WHERE email = ?)")
      .run("2026-08-02.v1", alphaEmail);
    const stalePrivacy = await privacyRoute.GET(new Request(`${origin}/api/account/privacy`, { headers: requestHeaders(alphaDeviceOne) }));
    assert.equal(stalePrivacy.status, 200);
    const stalePrivacyPayload = await stalePrivacy.json() as {
      currentVersion?: unknown;
      policyVersion?: unknown;
      state?: unknown;
    };
    assert.equal(stalePrivacyPayload.state, "accepted");
    assert.equal(stalePrivacyPayload.policyVersion, "2026-08-02.v1");
    assert.equal(stalePrivacyPayload.currentVersion, ACCOUNT_PRIVACY_POLICY_VERSION);
    await privacyConsent(alphaDeviceOne);

    const recoveredLedger = await createRecoveredSensitiveRecord(alphaDeviceOne, "ledger", {
      amountCents: 4567,
      category: "恢复记录",
      currency: "CNY",
      kind: "expense",
      localDate: "2026-08-12",
      note: "pre-consent device history",
    });
    await createRecoveredSensitiveRecord(alphaDeviceOne, "weights", {
      localDate: "2026-08-12",
      note: "pre-consent device history",
      weightGrams: 52300,
    });
    await createRecoveredSensitiveRecord(alphaDeviceOne, "diary", {
      body: "pre-consent device history",
      localDate: "2026-08-12",
      mood: "平静",
      title: "恢复",
    });
    await createRecoveredSensitiveRecord(alphaDeviceOne, "periods", {
      endDate: "2026-08-12",
      note: "pre-consent device history",
      startDate: "2026-08-10",
    });
    const retryHeaders = requestHeaders(alphaDeviceOne);
    retryHeaders.set("idempotency-key", recoveredLedger.idempotencyKey);
    const retry = await resourceRoute.POST(
      new Request(`${origin}${recoveredLedger.endpoint}`, {
        method: "POST",
        headers: retryHeaders,
        body: JSON.stringify(recoveredLedger.payload),
      }),
      { params: Promise.resolve({ resource: "ledger" }) },
    );
    assert.equal(retry.status, 200);
    assert.equal((await listLedger(alphaDeviceTwo)).length, 1);
    assert.equal((await listLedger(betaDevice)).length, 0);

    await createLedger(alphaDeviceOne, "local-alpha-ledger-0001", "expense");
    assert.equal((await listLedger(alphaDeviceTwo)).length, 2);
    assert.equal((await listLedger(betaDevice)).length, 0);
    await createLedger(betaDevice, "local-beta-ledger-0001", "income");
    assert.equal((await listLedger(alphaDeviceTwo)).length, 2);
    assert.equal((await listLedger(betaDevice)).length, 1);

    // The product must not be a ledger-only SaaS: every normal workbench
    // module has to create cloud history for the current verified account and
    // surface that same history to a second session, while the other account
    // cannot discover any of those rows. This exercises the real route gate,
    // resource whitelist, consent guard, tenant store, and session-derived
    // owner together instead of testing those layers in isolation.
    const habit = await createResource(alphaDeviceOne, "habits", "full-chain-habit-0001", {
      active: true,
      iconKey: "habit_early.png",
      sortOrder: 1,
      title: "早起",
    });
    const fullChainRecords = [
      { resourceName: "habits", id: habit.id },
      {
        resourceName: "habit-checkins",
        id: (await createResource(alphaDeviceOne, "habit-checkins", "full-chain-checkin-0001", {
          habitId: habit.id,
          localDate: "2026-08-13",
        })).id,
      },
      {
        resourceName: "todos",
        id: (await createResource(alphaDeviceOne, "todos", "full-chain-todo-0001", {
          completed: false,
          completedAt: null,
          dueDate: "2026-08-14",
          note: "跨设备回读",
          priority: "normal",
          title: "喝水",
        })).id,
      },
      {
        resourceName: "food",
        id: (await createResource(alphaDeviceOne, "food", "full-chain-food-0001", {
          calories: 320,
          foodName: "早餐",
          localDate: "2026-08-13",
          meal: "breakfast",
          note: "",
          photoObjectId: null,
          source: "manual",
        })).id,
      },
      {
        resourceName: "exercise",
        id: (await createResource(alphaDeviceOne, "exercise", "full-chain-exercise-0001", {
          activity: "散步",
          caloriesBurned: null,
          durationMinutes: 30,
          localDate: "2026-08-13",
          note: "",
        })).id,
      },
      {
        resourceName: "weights",
        id: (await createResource(alphaDeviceOne, "weights", "full-chain-weight-0001", {
          localDate: "2026-08-13",
          note: "",
          weightGrams: 52300,
        })).id,
      },
      {
        resourceName: "schedule",
        id: (await createResource(alphaDeviceOne, "schedule", "full-chain-schedule-0001", {
          allDay: false,
          endsAt: null,
          note: "",
          startsAt: 1786579200000,
          title: "日程",
        })).id,
      },
      {
        resourceName: "anniversaries",
        id: (await createResource(alphaDeviceOne, "anniversaries", "full-chain-anniversary-0001", {
          localDate: "2026-08-13",
          note: "",
          repeatYearly: true,
          title: "纪念日",
        })).id,
      },
      {
        resourceName: "diary",
        id: (await createResource(alphaDeviceOne, "diary", "full-chain-diary-0001", {
          body: "跨设备回读",
          localDate: "2026-08-13",
          mood: "平静",
          photoObjectId: null,
          title: "日记",
        })).id,
      },
      {
        resourceName: "periods",
        id: (await createResource(alphaDeviceOne, "periods", "full-chain-period-0001", {
          endDate: "2026-08-13",
          note: "",
          startDate: "2026-08-11",
        })).id,
      },
    ];
    const savingsGoal = await createResource(alphaDeviceOne, "savings-goals", "full-chain-goal-0001", {
      archived: false,
      currency: "CNY",
      targetCents: 300000,
      targetDate: null,
      title: "应急金",
    });
    fullChainRecords.push(
      { resourceName: "savings-goals", id: savingsGoal.id },
      {
        resourceName: "savings-transactions",
        id: (await createResource(alphaDeviceOne, "savings-transactions", "full-chain-transaction-0001", {
          amountCents: 5000,
          goalId: savingsGoal.id,
          localDate: "2026-08-13",
          note: "存入",
        })).id,
      },
    );
    for (const record of fullChainRecords) {
      const alphaHistory = await listResource(alphaDeviceTwo, record.resourceName);
      assert.equal(alphaHistory.some((value) => value.id === record.id), true, `${record.resourceName}: second device`);
      const betaHistory = await listResource(betaDevice, record.resourceName);
      assert.equal(betaHistory.some((value) => value.id === record.id), false, `${record.resourceName}: cross-account leak`);
    }

    const resetRequest = await callAuth("/request-password-reset", {
      email: alphaEmail,
      redirectTo: `${origin}/auth/reset-password`,
    });
    assert.equal(resetRequest.status, 200);
    const resetLink = capturedLinks.get(alphaEmail);
    assert.ok(resetLink, "expected an intercepted reset message");
    const resetToken = new URL(resetLink).pathname.split("/reset-password/")[1];
    assert.ok(resetToken);
    assert.equal((await callAuth("/reset-password", { token: resetToken, newPassword: resetPassword })).status, 200);

    const revoked = await resourceRoute.GET(
      new Request(`${origin}/api/mydairy/ledger`, { headers: requestHeaders(alphaDeviceOne) }),
      context,
    );
    assert.equal(revoked.status, 401);
    assert.equal((await listLedger(await signIn(alphaEmail, resetPassword))).length, 2);
    assert.equal(unexpectedOutbound, false);
  } finally {
    globalThis.fetch = originalFetch;
    if (workerEnv) {
      for (const key of Object.keys(workerEnv)) delete workerEnv[key];
    }
    sqlite.close();
  }
});

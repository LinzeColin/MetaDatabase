import assert from "node:assert/strict";
import test from "node:test";

import {
  createDeviceLocalRecord,
  deriveDeviceOutboxParentReferences,
  invalidateBrowserRecordScope,
  isDeviceLocalRecord,
  mergeWithDeviceLocalRecords,
  readDeviceLocalRecords,
  removeDeviceLocalRecord,
  resolveBrowserRecordScope,
  resolveDeviceOutboxActionWithAliases,
  writeDeviceLocalRecord,
  type DeviceOutboxAction,
} from "../app/_components/workbench/local-record-cache.ts";

test("device-local records retain display fields while excluding client tenant identifiers", () => {
  const record = createDeviceLocalRecord(
    {
      amountCents: 1234,
      localDate: "2026-08-10",
      note: "device-only",
      tenantId: "must-not-persist",
      user_id: "must-not-persist",
    },
    42,
    "local_fixed",
  );

  assert.equal(record.id, "local_fixed");
  assert.equal(record.amount_cents, 1234);
  assert.equal(record.local_date, "2026-08-10");
  assert.equal(record.created_at, 42);
  assert.equal(record.updated_at, 42);
  assert.equal(record.tenant_id, undefined);
  assert.equal(record.user_id, undefined);
  assert.equal(isDeviceLocalRecord(record), true);
});

test("device-local records remain visible beside remote history without replacing a remote row", () => {
  const local = createDeviceLocalRecord({ title: "current device" }, 2, "local_device");
  const remote: Array<Record<string, unknown> & { id: string }> = [
    { id: "rec_remote", title: "cloud" },
    { id: "local_device", title: "authoritative cloud replacement" },
  ];

  const merged = mergeWithDeviceLocalRecords(remote, [local]);

  assert.equal(merged.length, 2);
  assert.equal(merged[0].id, "rec_remote");
  assert.equal(merged[1].id, "local_device");
  assert.equal(merged[1].title, "authoritative cloud replacement");
});

test("device-local account scope is reused briefly and re-evaluated after an explicit account switch check", async () => {
  const runtime = globalThis as typeof globalThis & {
    window?: unknown;
  };
  const originalWindow = runtime.window;
  const originalFetch = globalThis.fetch;
  let activeUserId = "account-a";
  const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  invalidateBrowserRecordScope();
  Object.defineProperty(runtime, "window", { configurable: true, value: {} });
  globalThis.fetch = async (input, init) => {
    requests.push({ input, init });
    return new Response(JSON.stringify({ user: { id: activeUserId } }), { status: 200 });
  };

  try {
    const firstScope = await resolveBrowserRecordScope();
    const cachedScope = await resolveBrowserRecordScope();
    activeUserId = "account-b";
    invalidateBrowserRecordScope();
    const secondScope = await resolveBrowserRecordScope();

    assert.match(firstScope, /^account:/);
    assert.equal(cachedScope, firstScope);
    assert.match(secondScope, /^account:/);
    assert.notEqual(firstScope, secondScope);
    assert.doesNotMatch(firstScope, /account-a/);
    assert.doesNotMatch(secondScope, /account-b/);
    assert.deepEqual(requests.map(({ input }) => input), [
      "/api/auth/get-session?disableCookieCache=true",
      "/api/auth/get-session?disableCookieCache=true",
    ]);
    assert.ok(requests.every(({ init }) => init?.credentials === "same-origin"));
  } finally {
    invalidateBrowserRecordScope();
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) Reflect.deleteProperty(runtime, "window");
    else Object.defineProperty(runtime, "window", { configurable: true, value: originalWindow });
  }
});

test("a failed session lookup is never cached as a guest scope", async () => {
  const runtime = globalThis as typeof globalThis & { window?: unknown };
  const originalWindow = runtime.window;
  const originalFetch = globalThis.fetch;
  let calls = 0;
  invalidateBrowserRecordScope();
  Object.defineProperty(runtime, "window", { configurable: true, value: {} });
  globalThis.fetch = (async () => {
    calls += 1;
    if (calls === 1) return new Response(null, { status: 429 });
    return new Response(JSON.stringify({ user: { id: "account-a" } }), { status: 200 });
  }) as typeof fetch;

  try {
    assert.equal(await resolveBrowserRecordScope(), "guest");
    assert.match(await resolveBrowserRecordScope(), /^account:/);
    assert.equal(calls, 2);
  } finally {
    invalidateBrowserRecordScope();
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) Reflect.deleteProperty(runtime, "window");
    else Object.defineProperty(runtime, "window", { configurable: true, value: originalWindow });
  }
});

test("an authoritative signed-out session is briefly cached and an explicit recheck can enter an account scope", async () => {
  const runtime = globalThis as typeof globalThis & { window?: unknown };
  const originalWindow = runtime.window;
  const originalFetch = globalThis.fetch;
  let calls = 0;
  let signedIn = false;
  invalidateBrowserRecordScope();
  Object.defineProperty(runtime, "window", { configurable: true, value: {} });
  globalThis.fetch = (async () => {
    calls += 1;
    if (!signedIn) return new Response(null, { status: 401 });
    return new Response(JSON.stringify({ user: { id: "account-a" } }), { status: 200 });
  }) as typeof fetch;

  try {
    assert.equal(await resolveBrowserRecordScope(), "guest");
    assert.equal(await resolveBrowserRecordScope(), "guest");
    assert.equal(calls, 1);

    signedIn = true;
    invalidateBrowserRecordScope();
    assert.match(await resolveBrowserRecordScope(), /^account:/);
    assert.equal(calls, 2);
  } finally {
    invalidateBrowserRecordScope();
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) Reflect.deleteProperty(runtime, "window");
    else Object.defineProperty(runtime, "window", { configurable: true, value: originalWindow });
  }
});

test("session scope falls back to the guest partition when the session request stalls", async () => {
  const runtime = globalThis as typeof globalThis & {
    window?: unknown;
  };
  const originalWindow = runtime.window;
  const originalFetch = globalThis.fetch;
  let requestWasAborted = false;
  invalidateBrowserRecordScope();
  Object.defineProperty(runtime, "window", { configurable: true, value: {} });
  globalThis.fetch = ((_: RequestInfo | URL, init?: RequestInit) => new Promise<Response>(() => {
    init?.signal?.addEventListener("abort", () => {
      requestWasAborted = true;
    });
  })) as typeof fetch;

  try {
    assert.equal(await resolveBrowserRecordScope(20), "guest");
    assert.equal(requestWasAborted, true);
  } finally {
    invalidateBrowserRecordScope();
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) Reflect.deleteProperty(runtime, "window");
    else Object.defineProperty(runtime, "window", { configurable: true, value: originalWindow });
  }
});

test("device-local history falls back to an opaque same-origin partition when IndexedDB rejects opening", async () => {
  const runtime = globalThis as typeof globalThis & { window?: unknown };
  const originalWindow = runtime.window;
  const entries = new Map<string, string>();
  const storage = {
    getItem(key: string) {
      return entries.get(key) ?? null;
    },
    removeItem(key: string) {
      entries.delete(key);
    },
    setItem(key: string, value: string) {
      entries.set(key, value);
    },
  };
  Object.defineProperty(runtime, "window", {
    configurable: true,
    value: {
      indexedDB: { open() { throw new Error("embedded browser cache unavailable"); } },
      localStorage: storage,
    },
  });

  try {
    const alpha = createDeviceLocalRecord({ title: "alpha" }, 20, "local_alpha");
    const beta = createDeviceLocalRecord({ title: "beta" }, 30, "local_beta");
    await writeDeviceLocalRecord("account:alpha", "schedule", alpha);
    await writeDeviceLocalRecord("account:beta", "schedule", beta);

    assert.deepEqual((await readDeviceLocalRecords("account:alpha", "schedule")).map((record) => record.id), ["local_alpha"]);
    assert.deepEqual((await readDeviceLocalRecords("account:beta", "schedule")).map((record) => record.id), ["local_beta"]);

    await removeDeviceLocalRecord("account:alpha", "schedule", alpha.id);
    assert.deepEqual(await readDeviceLocalRecords("account:alpha", "schedule"), []);
    assert.deepEqual((await readDeviceLocalRecords("account:beta", "schedule")).map((record) => record.id), ["local_beta"]);
  } finally {
    if (originalWindow === undefined) Reflect.deleteProperty(runtime, "window");
    else Object.defineProperty(runtime, "window", { configurable: true, value: originalWindow });
  }
});

test("local parent references wait for a same-account alias instead of sending a local identifier", async () => {
  const habitReferences = deriveDeviceOutboxParentReferences("habit-checkins", { habitId: "local_habit" });
  const savingsReferences = deriveDeviceOutboxParentReferences("savings-transactions", { goalId: "local_goal" });

  assert.deepEqual(habitReferences, [{ field: "habitId", localRecordId: "local_habit", resource: "habits" }]);
  assert.deepEqual(savingsReferences, [{ field: "goalId", localRecordId: "local_goal", resource: "savings-goals" }]);
  assert.deepEqual(deriveDeviceOutboxParentReferences("habit-checkins", { habitId: "rec_habit" }), []);
  assert.deepEqual(deriveDeviceOutboxParentReferences("ledger", { habitId: "local_habit" }), []);

  const action: DeviceOutboxAction = {
    createdAt: 1,
    endpoint: "/api/mydairy/habit-checkins",
    idempotencyKey: "habit-checkin-local-parent-v1",
    localRecordId: "local_checkin",
    method: "POST",
    parentReferences: habitReferences,
    payload: { habitId: "local_habit", completedAt: 1 },
    queuedAt: 1,
  };

  const waiting = await resolveDeviceOutboxActionWithAliases(action, async () => null);
  assert.equal(waiting, null);

  const resolved = await resolveDeviceOutboxActionWithAliases(action, async (reference) => {
    assert.deepEqual(reference, habitReferences[0]);
    return "rec_habit";
  });
  assert.ok(resolved);
  assert.equal(resolved.payload.habitId, "rec_habit");
  assert.equal(action.payload.habitId, "local_habit");
});

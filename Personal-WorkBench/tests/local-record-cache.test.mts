import assert from "node:assert/strict";
import test from "node:test";

import {
  createDeviceLocalRecord,
  buildGuestDeviceHistoryEnvelope,
  countGuestDeviceHistoryRecords,
  createDeviceLocalRecoveryOutboxAction,
  deviceLocalRecordRequestPayload,
  appendDeviceOutbox,
  deriveDeviceOutboxParentReferences,
  invalidateBrowserRecordScope,
  isDeviceLocalRecord,
  mergeWithDeviceLocalRecords,
  readDeviceLocalRecords,
  readDeviceOutbox,
  removeDeviceOutboxActions,
  removeDeviceLocalRecord,
  rememberDeviceOutboxRecordAlias,
  resolveBrowserRecordScope,
  resolveDeviceOutboxAction,
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

test("legacy sensitive device records recover a stable API action without cache metadata or tenant fields", () => {
  const record = createDeviceLocalRecord(
    {
      amountCents: 4567,
      localDate: "2026-08-12",
      note: "existing device history",
      tenantId: "must-not-leave-device",
    },
    123,
    "local_legacy_ledger",
  );

  assert.deepEqual(deviceLocalRecordRequestPayload(record), {
    amountCents: 4567,
    localDate: "2026-08-12",
    note: "existing device history",
  });
  assert.deepEqual(createDeviceLocalRecoveryOutboxAction("ledger", record), {
    createdAt: 123,
    endpoint: "/api/mydairy/ledger",
    idempotencyKey: "local-recovery-ledger-local_legacy_ledger",
    localRecordId: "local_legacy_ledger",
    method: "POST",
    payload: {
      amountCents: 4567,
      localDate: "2026-08-12",
      note: "existing device history",
    },
    queuedAt: 123,
    requiresSensitiveConsent: true,
  });
  assert.equal(createDeviceLocalRecoveryOutboxAction("ledger", { ...record, id: "rec_not_device" }), null);
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

test("an explicit guest-device import candidate includes every supported module without reading account scopes or moving image bytes", async () => {
  const runtime = globalThis as typeof globalThis & { window?: unknown };
  const originalWindow = runtime.window;
  const entries = new Map<string, string>();
  const storage = {
    getItem(key: string) { return entries.get(key) ?? null; },
    removeItem(key: string) { entries.delete(key); },
    setItem(key: string, value: string) { entries.set(key, value); },
  };
  Object.defineProperty(runtime, "window", {
    configurable: true,
    value: {
      indexedDB: { open() { throw new Error("embedded browser cache unavailable"); } },
      localStorage: storage,
    },
  });

  try {
    await writeDeviceLocalRecord("guest", "habits", createDeviceLocalRecord({ title: "晨起", iconKey: "sun" }, 1, "local_habit_guest"));
    await writeDeviceLocalRecord("guest", "habit-checkins", createDeviceLocalRecord({ habitId: "local_habit_guest", localDate: "2026-08-13" }, 2, "local_checkin_guest"));
    await writeDeviceLocalRecord("guest", "food", createDeviceLocalRecord({
      foodName: "早餐", calories: 300, meal: "breakfast", localDate: "2026-08-13", note: "", photoObjectId: "private-photo-id", source: "manual",
    }, 3, "local_food_guest"));
    await writeDeviceLocalRecord("guest", "savings-goals", createDeviceLocalRecord({ title: "旅行", targetCents: 10000, currency: "CNY", targetDate: null, archived: false }, 4, "local_goal_guest"));
    await writeDeviceLocalRecord("guest", "savings-transactions", createDeviceLocalRecord({ goalId: "local_goal_guest", amountCents: 500, localDate: "2026-08-13", note: "" }, 5, "local_transaction_guest"));
    await writeDeviceLocalRecord("account:other", "ledger", createDeviceLocalRecord({ kind: "expense", amountCents: 999, currency: "CNY", localDate: "2026-08-13", category: "不应读取", note: "" }, 6, "local_account_only"));

    const first = await buildGuestDeviceHistoryEnvelope(new Date("2026-08-13T00:00:00.000Z"));
    const second = await buildGuestDeviceHistoryEnvelope(new Date("2026-08-13T00:01:00.000Z"));

    assert.match(first.sourceInstanceId, /^guest-device-/);
    assert.equal(second.sourceInstanceId, first.sourceInstanceId);
    assert.equal(first.exportedAt, "2026-08-13T00:00:00.000Z");
    assert.equal(second.exportedAt, first.exportedAt);
    assert.equal(first.sourceSchemaVersion, 1);
    assert.deepEqual(first.imageManifest, []);
    assert.deepEqual(first.modules.habitCheckins, [{ id: "local_checkin_guest", habitId: "local_habit_guest", localDate: "2026-08-13" }]);
    assert.deepEqual(first.modules.savingsTransactions, [{ id: "local_transaction_guest", goalId: "local_goal_guest", amountCents: 500, localDate: "2026-08-13", note: "" }]);
    assert.equal(first.modules.food?.[0]?.photoObjectId, undefined);
    assert.equal(first.modules.ledger, undefined);
    assert.equal(await countGuestDeviceHistoryRecords(), 5);
  } finally {
    if (originalWindow === undefined) Reflect.deleteProperty(runtime, "window");
    else Object.defineProperty(runtime, "window", { configurable: true, value: originalWindow });
  }
});

test("sensitive consent-pending outbox actions survive an embedded-browser fallback without crossing account scopes", async () => {
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

  const action: DeviceOutboxAction = {
    createdAt: 40,
    endpoint: "/api/mydairy/periods",
    idempotencyKey: "period-consent-pending",
    localRecordId: "local_period",
    method: "POST",
    payload: { startDate: "2026-08-12" },
    queuedAt: 40,
    requiresSensitiveConsent: true,
  };

  try {
    await appendDeviceOutbox("account:alpha", action);
    const alpha = await readDeviceOutbox("account:alpha");
    const beta = await readDeviceOutbox("account:beta");

    assert.deepEqual(alpha.map((entry) => entry.idempotencyKey), ["period-consent-pending"]);
    assert.equal(alpha[0].requiresSensitiveConsent, true);
    assert.deepEqual(beta, []);

    await removeDeviceOutboxActions("account:alpha", [action.idempotencyKey]);
    assert.deepEqual(await readDeviceOutbox("account:alpha"), []);
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

test("embedded-browser alias fallback resolves a child only in the originating account scope", async () => {
  const runtime = globalThis as typeof globalThis & { window?: unknown };
  const originalWindow = runtime.window;
  const entries = new Map<string, string>();
  const storage = {
    getItem(key: string) { return entries.get(key) ?? null; },
    removeItem(key: string) { entries.delete(key); },
    setItem(key: string, value: string) { entries.set(key, value); },
  };
  Object.defineProperty(runtime, "window", {
    configurable: true,
    value: {
      dispatchEvent() { return true; },
      indexedDB: { open() { throw new Error("embedded browser cache unavailable"); } },
      localStorage: storage,
    },
  });

  const parent: DeviceOutboxAction = {
    createdAt: 1,
    endpoint: "/api/mydairy/habits",
    idempotencyKey: "parent-habit-v1",
    localRecordId: "local_habit",
    method: "POST",
    payload: { label: "早起" },
    queuedAt: 1,
  };
  const child: DeviceOutboxAction = {
    createdAt: 2,
    endpoint: "/api/mydairy/habit-checkins",
    idempotencyKey: "child-checkin-v1",
    localRecordId: "local_checkin",
    method: "POST",
    parentReferences: [{ field: "habitId", localRecordId: "local_habit", resource: "habits" }],
    payload: { habitId: "local_habit", completedAt: 2 },
    queuedAt: 2,
  };

  try {
    await rememberDeviceOutboxRecordAlias("account:alpha", parent, "rec_alpha_habit");
    const sameAccount = await resolveDeviceOutboxAction("account:alpha", child);
    const otherAccount = await resolveDeviceOutboxAction("account:beta", child);

    assert.equal(sameAccount?.payload.habitId, "rec_alpha_habit");
    assert.equal(child.payload.habitId, "local_habit");
    assert.equal(otherAccount, null);
  } finally {
    if (originalWindow === undefined) Reflect.deleteProperty(runtime, "window");
    else Object.defineProperty(runtime, "window", { configurable: true, value: originalWindow });
  }
});

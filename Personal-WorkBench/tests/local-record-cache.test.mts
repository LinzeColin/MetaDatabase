import assert from "node:assert/strict";
import test from "node:test";

import {
  createDeviceLocalRecord,
  deriveDeviceOutboxParentReferences,
  isDeviceLocalRecord,
  mergeWithDeviceLocalRecords,
  resolveBrowserRecordScope,
  resolveDeviceOutboxActionWithAliases,
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

test("device-local account scope is re-evaluated after an account switch", async () => {
  const runtime = globalThis as typeof globalThis & {
    window?: unknown;
  };
  const originalWindow = runtime.window;
  const originalFetch = globalThis.fetch;
  let activeUserId = "account-a";
  Object.defineProperty(runtime, "window", { configurable: true, value: {} });
  globalThis.fetch = async () => new Response(JSON.stringify({ user: { id: activeUserId } }), { status: 200 });

  try {
    const firstScope = await resolveBrowserRecordScope();
    activeUserId = "account-b";
    const secondScope = await resolveBrowserRecordScope();

    assert.match(firstScope, /^account:/);
    assert.match(secondScope, /^account:/);
    assert.notEqual(firstScope, secondScope);
    assert.doesNotMatch(firstScope, /account-a/);
    assert.doesNotMatch(secondScope, /account-b/);
  } finally {
    globalThis.fetch = originalFetch;
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

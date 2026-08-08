import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import type { D1PreparedStatement } from "@cloudflare/workers-types";
import {
  AccountDeleteStateError,
  AccountInputError,
  getAccountExport,
  getDeletionState,
  processDeleteRequest,
} from "../server/data/account-lifecycle.ts";

type AccountLifecycleDb = Pick<Parameters<typeof getAccountExport>[0], "prepare">;
type BoundResult = Pick<D1PreparedStatement, "bind" | "run" | "first" | "all" | "raw">;
type D1Mock = Pick<AccountLifecycleDb, "prepare">;

function asD1Mock(db: DatabaseSync): D1Mock {
  const normalize = (value: unknown) => (typeof value === "boolean" ? (value ? 1 : 0) : value);
  const emptyMeta = (changes = 0) => ({
    duration: 0,
    size_after: 0,
    rows_read: 0,
    rows_written: 0,
    last_row_id: 0,
    changes,
    changed_db: true,
  } as const);
  return {
    prepare(sql) {
      const statement = db.prepare(sql);
      const executeBound = (...values: unknown[]): BoundResult => ({
        bind: (...nextValues: unknown[]) => executeBound(...nextValues),
        run: (async () => {
          const normalized = values.map(normalize) as Parameters<(typeof statement)["run"]>;
          const result = statement.run(...normalized);
          return { success: true, results: [], meta: emptyMeta(Number(result.changes ?? 0)) };
        }) as BoundResult["run"],
        first: (async () => {
          const cast = values as Parameters<(typeof statement)["get"]>;
          return (statement.get(...cast) as Record<string, unknown> | null) ?? null;
        }) as BoundResult["first"],
        all: (async () => {
          const cast = values as Parameters<(typeof statement)["all"]>;
          return { success: true, results: statement.all(...cast) as Record<string, unknown>[], meta: emptyMeta(0) };
        }) as BoundResult["all"],
        raw: (() => Promise.resolve([[],] as [string[], ...unknown[]])) as BoundResult["raw"],
      });
      return executeBound();
    },
  };
}

async function setupDb() {
  const db = new DatabaseSync(":memory:");
  db.exec(await readFile("drizzle/0001_auth_and_product.sql", "utf8"));
  db.exec(await readFile("drizzle/0002_s2_tenant_indexes.sql", "utf8"));
  const now = Date.now();
  db.prepare('INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt) VALUES (?, ?, ?, 1, ?, ?)')
    .run("user_lifecycle", "Life User", "life@example.test", now, now);
  return db;
}

test("getAccountExport collects profile, module rows, files and consent events", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    const now = Date.now();
    db.prepare(
      `INSERT INTO profile_settings
        (user_id, display_name, timezone, locale, show_welcome, privacy_consent_state, privacy_policy_version, privacy_consented_at, privacy_revoked_at, data_version, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, 'accepted', 'policy-2026-08-05-v1', ?, NULL, 1, ?, ?)`,
    )
      .run("user_lifecycle", "Life User", "Asia/Shanghai", "zh-CN", now, now, now);

    db.prepare(
      "INSERT INTO habit_definitions (id, user_id, title, icon_key, sort_order, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
    )
      .run("h1", "user_lifecycle", "晨跑", "icon-sun", 1, now, now);
    db.prepare(
      "INSERT INTO file_objects (id, user_id, object_key, module, content_type, byte_size, sha256, width, height, created_at, updated_at, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
    )
      .run("f1", "user_lifecycle", "users/user_lifecycle/food/f1", "food", "image/png", 111, "a".repeat(64), 16, 16, now, now);
    db.prepare(
      "INSERT INTO privacy_consent_events (id, user_id, policy_version, notice_sha256, decision, decided_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    )
      .run("e1", "user_lifecycle", "policy-2026-08-05-v1", "e".repeat(64), "accepted", now, now);

    const snapshot = await getAccountExport(d1, "user_lifecycle");
    assert.equal(snapshot.user.id, "user_lifecycle");
    assert.equal(snapshot.profile.displayName, "Life User");
    assert.equal(snapshot.profile.privacyState, "accepted");
    assert.equal(snapshot.profile.privacyPolicyVersion, "policy-2026-08-05-v1");
    assert.equal(snapshot.modules.habits?.length, 1);
    assert.equal(snapshot.modules.habits?.[0].title, "晨跑");
    assert.equal(snapshot.files.length, 1);
    assert.equal(snapshot.files[0].id, "f1");
    assert.equal(snapshot.privacyEvents.length, 1);
    assert.equal(snapshot.privacyEvents[0].decision, "accepted");
  } finally {
    db.close();
  }
});

test("processDeleteRequest request + confirm deletes account data and files", async () => {
  const db = await setupDb();
  const deleted: string[] = [];
  const mockFileEnv = {
    FILES: {
      delete: async (key: string) => {
        deleted.push(key);
      },
    },
  };
  const d1 = asD1Mock(db);
  try {
    const now = Date.now();
    db.prepare(
      `INSERT INTO profile_settings
        (user_id, display_name, timezone, locale, show_welcome, privacy_consent_state, data_version, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, 'not_requested', 1, ?, ?)`,
    )
      .run("user_lifecycle", "Life User", "UTC", "zh-CN", now, now);
    db.prepare("INSERT INTO habit_definitions (id, user_id, title, icon_key, sort_order, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)")
      .run("h1", "user_lifecycle", "冥想", "icon-moon", 1, now, now);
    db.prepare(
      "INSERT INTO file_objects (id, user_id, object_key, module, content_type, byte_size, sha256, width, height, created_at, updated_at, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
    )
      .run("f1", "user_lifecycle", "users/user_lifecycle/food/f1", "food", "image/png", 120, "b".repeat(64), null, null, now, now);

    const request = await processDeleteRequest(d1, mockFileEnv, "user_lifecycle", { action: "request" });
    assert.equal(request.action, "request");
    assert.equal(typeof request.recoveryToken, "string");
    assert.equal(typeof request.exportHash, "string");
    const stateAfterRequest = await getDeletionState(d1, "user_lifecycle");
    assert.equal(stateAfterRequest.state, "pending");
    assert.equal(stateAfterRequest.tokenExpiresAt !== null, true);

    await processDeleteRequest(d1, mockFileEnv, "user_lifecycle", { action: "confirm", recoveryToken: request.recoveryToken as string });
    const userRow = db
      .prepare('SELECT id FROM "user" WHERE id = ? LIMIT 1')
      .get("user_lifecycle") as { id: string } | undefined | null;
    assert.equal(userRow, undefined);
    assert.equal(deleted.includes("users/user_lifecycle/food/f1"), true);
    const stateAfterConfirm = await getDeletionState(d1, "user_lifecycle");
    assert.equal(stateAfterConfirm.state, "active");
    assert.equal(stateAfterConfirm.tokenExpiresAt, null);
  } finally {
    db.close();
  }
});

test("processDeleteRequest undo恢复和错误令牌重试", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  const now = Date.now();
  db.prepare(
    `INSERT INTO profile_settings
      (user_id, display_name, timezone, locale, show_welcome, privacy_consent_state, data_version, created_at, updated_at)
      VALUES (?, ?, ?, ?, 1, 'not_requested', 1, ?, ?)`,
  )
    .run("user_lifecycle", "Life User", "UTC", "zh-CN", now, now);
  try {
    const first = await processDeleteRequest(d1, {}, "user_lifecycle", { action: "request" });
    assert.equal(first.action, "request");

    const retryRequest = await processDeleteRequest(d1, {}, "user_lifecycle", { action: "request" });
    assert.equal(retryRequest.action, "request");

    await assert.rejects(
      () => processDeleteRequest(d1, {}, "user_lifecycle", { action: "confirm", recoveryToken: first.recoveryToken! }),
      (error): error is AccountDeleteStateError => error instanceof AccountDeleteStateError,
    );

    await processDeleteRequest(d1, {}, "user_lifecycle", { action: "confirm", recoveryToken: retryRequest.recoveryToken! });
    const deleted = db.prepare('SELECT id FROM "user" WHERE id = ? LIMIT 1').get("user_lifecycle") as { id: string } | undefined;
    assert.equal(deleted, undefined);
  } finally {
    db.close();
  }
});

test("processDeleteRequest input format rejects missing token for confirm", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    await assert.rejects(
      () => processDeleteRequest(d1, {}, "user_lifecycle", { action: "confirm" } as { action: "confirm" }),
      (error): error is AccountInputError => error instanceof AccountInputError,
    );
  } finally {
    db.close();
  }
});

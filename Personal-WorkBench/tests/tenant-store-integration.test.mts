import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import type { D1PreparedStatement } from "@cloudflare/workers-types";
import {
  createTenantRecord,
  deleteTenantRecord,
  getTenantRecord,
  listTenantRecords,
  updateTenantRecord,
} from "../server/data/tenant-store.ts";
import { getTenantResource, normalizeResourceInput } from "../server/data/resources.ts";
import { NotAccessibleError } from "../server/security/tenant.ts";

type TenantDb = Pick<D1Database, "prepare">;
type BoundResult = Pick<D1PreparedStatement, "bind" | "run" | "first" | "all" | "raw">;

function emptyMeta(changes = 0) {
  return {
    duration: 0,
    size_after: 0,
    rows_read: 0,
    rows_written: 0,
    last_row_id: 0,
    changes,
    changed_db: true,
  } as const;
}

function asTenantDb(db: DatabaseSync): TenantDb {
  return {
    prepare(sql) {
      const statement = db.prepare(sql);
      const executeBound = (...values: unknown[]): BoundResult => {
        const castRun = values as Parameters<(typeof statement)["run"]>;
        const castGet = values as Parameters<(typeof statement)["get"]>;
        const castAll = values as Parameters<(typeof statement)["all"]>;
        const normalizedValues = castRun.map((value) => (typeof value === "boolean" ? Number(value) : value)) as Parameters<(typeof statement)["run"]>;

        return {
          bind: (...nextValues: unknown[]) => executeBound(...nextValues),
          run: (async () => {
            const result = statement.run(...normalizedValues);
            return { success: true, results: [], meta: emptyMeta(Number(result.changes ?? 0)) };
          }) as BoundResult["run"],
          first: (async () => (statement.get(...castGet) as Record<string, unknown> | undefined) ?? null) as BoundResult["first"],
          all: (async () => ({
            success: true,
            results: statement.all(...castAll) as Record<string, unknown>[],
            meta: emptyMeta(),
          })) as BoundResult["all"],
          raw: (() => Promise.resolve([[]] as [string[]])) as BoundResult["raw"],
        };
      };

      return executeBound();
    },
  };
}

function resource(name: string) {
  const value = getTenantResource(name);
  if (!value) throw new Error(`missing test resource: ${name}`);
  return value;
}

async function setupDb() {
  const db = new DatabaseSync(":memory:");
  db.exec("PRAGMA foreign_keys = ON");
  for (const file of ["drizzle/0001_auth_and_product.sql", "drizzle/0002_s2_tenant_indexes.sql"]) {
    db.exec(await readFile(file, "utf8"));
  }
  const now = Date.now();
  for (const [id, email] of [["user_a", "a@example.test"], ["user_b", "b@example.test"]]) {
    db.prepare('INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt) VALUES (?, ?, ?, 1, ?, ?)')
      .run(id, id, email, now, now);
  }
  return db;
}

async function create(
  db: TenantDb,
  resourceName: string,
  userId: string,
  id: string,
  input: Record<string, unknown>,
) {
  const target = resource(resourceName);
  const values = normalizeResourceInput(target, input, "create");
  await createTenantRecord(db, target, userId, id, values);
}

test("tenant store keeps a user record invisible and immutable to another signed-in account", async () => {
  const sqlite = await setupDb();
  const db = asTenantDb(sqlite);
  const ledger = resource("ledger");
  try {
    await create(db, "ledger", "user_a", "ledger-a", {
      kind: "expense",
      amountCents: 1200,
      currency: "CNY",
      localDate: "2026-08-11",
      category: "餐饮",
      note: "午餐",
    });

    assert.equal((await listTenantRecords(db, ledger, "user_a")).length, 1);
    assert.deepEqual(await listTenantRecords(db, ledger, "user_b"), []);
    assert.equal(await getTenantRecord(db, ledger, "user_b", "ledger-a"), null);
    await assert.rejects(
      () => updateTenantRecord(db, ledger, "user_b", "ledger-a", { note: "cross-account" }),
      NotAccessibleError,
    );
    await assert.rejects(() => deleteTenantRecord(db, ledger, "user_b", "ledger-a"), NotAccessibleError);
    assert.equal((await getTenantRecord(db, ledger, "user_a", "ledger-a"))?.note, "午餐");
  } finally {
    sqlite.close();
  }
});

test("tenant store rejects cross-account habit and savings parent references before they become history", async () => {
  const sqlite = await setupDb();
  const db = asTenantDb(sqlite);
  const checkins = resource("habit-checkins");
  const transactions = resource("savings-transactions");
  try {
    await create(db, "habits", "user_a", "habit-a", {
      title: "早起",
      iconKey: "habit_early.png",
      sortOrder: 1,
      active: true,
    });
    await assert.rejects(
      () => create(db, "habit-checkins", "user_b", "checkin-b", { habitId: "habit-a", localDate: "2026-08-11" }),
    );
    await create(db, "habit-checkins", "user_a", "checkin-a", { habitId: "habit-a", localDate: "2026-08-11" });
    assert.deepEqual(await listTenantRecords(db, checkins, "user_b"), []);

    await create(db, "savings-goals", "user_a", "goal-a", {
      title: "应急金",
      targetCents: 300000,
      currency: "CNY",
      targetDate: null,
      archived: false,
    });
    await assert.rejects(
      () => create(db, "savings-transactions", "user_b", "transaction-b", {
        goalId: "goal-a",
        amountCents: 5000,
        localDate: "2026-08-11",
        note: "cross-account",
      }),
    );
    await create(db, "savings-transactions", "user_a", "transaction-a", {
      goalId: "goal-a",
      amountCents: 5000,
      localDate: "2026-08-11",
      note: "本账户",
    });
    assert.deepEqual(await listTenantRecords(db, transactions, "user_b"), []);
    assert.equal((await listTenantRecords(db, transactions, "user_a")).length, 1);
  } finally {
    sqlite.close();
  }
});

test("every tenant record resource keeps create, history, update, and delete inside its signed-in account", async () => {
  const sqlite = await setupDb();
  const db = asTenantDb(sqlite);
  try {
    const fixtures: Array<{
      id: string;
      input: Record<string, unknown>;
      name: string;
    }> = [
      {
        id: "habit-alpha",
        name: "habits",
        input: { active: true, iconKey: "habit_early.png", sortOrder: 1, title: "早起" },
      },
      {
        id: "checkin-alpha",
        name: "habit-checkins",
        input: { habitId: "habit-alpha", localDate: "2026-08-12" },
      },
      {
        id: "todo-alpha",
        name: "todos",
        input: { completed: false, completedAt: null, dueDate: "2026-08-13", note: "alpha only", priority: "normal", title: "待办" },
      },
      {
        id: "ledger-alpha",
        name: "ledger",
        input: { amountCents: 1200, category: "餐饮", currency: "CNY", kind: "expense", localDate: "2026-08-12", note: "午餐" },
      },
      {
        id: "food-alpha",
        name: "food",
        input: { calories: 320, foodName: "早餐", localDate: "2026-08-12", meal: "breakfast", note: "", photoObjectId: null, source: "manual" },
      },
      {
        id: "exercise-alpha",
        name: "exercise",
        input: { activity: "散步", caloriesBurned: null, durationMinutes: 30, localDate: "2026-08-12", note: "" },
      },
      {
        id: "weight-alpha",
        name: "weights",
        input: { localDate: "2026-08-12", note: "", weightGrams: 52300 },
      },
      {
        id: "schedule-alpha",
        name: "schedule",
        input: { allDay: false, endsAt: null, note: "", startsAt: 1786492800000, title: "日程" },
      },
      {
        id: "anniversary-alpha",
        name: "anniversaries",
        input: { localDate: "2026-08-12", note: "", repeatYearly: true, title: "纪念日" },
      },
      {
        id: "diary-alpha",
        name: "diary",
        input: { body: "alpha only", localDate: "2026-08-12", mood: "平静", photoObjectId: null, title: "日记" },
      },
      {
        id: "goal-alpha",
        name: "savings-goals",
        input: { archived: false, currency: "CNY", targetCents: 300000, targetDate: null, title: "应急金" },
      },
      {
        id: "transaction-alpha",
        name: "savings-transactions",
        input: { amountCents: 5000, goalId: "goal-alpha", localDate: "2026-08-12", note: "存入" },
      },
      {
        id: "period-alpha",
        name: "periods",
        input: { endDate: "2026-08-12", note: "", startDate: "2026-08-10" },
      },
    ];

    for (const fixture of fixtures) {
      const target = resource(fixture.name);
      await create(db, fixture.name, "user_a", fixture.id, fixture.input);

      assert.equal((await getTenantRecord(db, target, "user_a", fixture.id))?.id, fixture.id, fixture.name);
      assert.deepEqual(await listTenantRecords(db, target, "user_b"), [], fixture.name);
      assert.equal(await getTenantRecord(db, target, "user_b", fixture.id), null, fixture.name);
      await assert.rejects(() => updateTenantRecord(db, target, "user_b", fixture.id, {}), NotAccessibleError, fixture.name);
      await assert.rejects(() => deleteTenantRecord(db, target, "user_b", fixture.id), NotAccessibleError, fixture.name);
      assert.equal((await getTenantRecord(db, target, "user_a", fixture.id))?.id, fixture.id, fixture.name);
    }
  } finally {
    sqlite.close();
  }
});

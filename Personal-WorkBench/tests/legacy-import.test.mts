import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import type { D1PreparedStatement } from "@cloudflare/workers-types";
import {
  LegacyImportConflictError,
  LegacyImportError,
  applyLegacyImport,
  getLegacyImportDebugState,
  previewLegacyImport,
} from "../server/data/legacy-import.ts";
import {
  ACCOUNT_PRIVACY_NOTICE_SHA256,
  ACCOUNT_PRIVACY_POLICY_VERSION,
  setPrivacyConsent,
} from "../server/data/account-lifecycle.ts";
import { SensitiveCloudConsentRequiredError } from "../server/security/privacy-consent.ts";

type LegacyImportDb = Parameters<typeof previewLegacyImport>[0];

type BoundResult = Pick<D1PreparedStatement, "bind" | "run" | "first" | "all" | "raw">;

type D1Mock = Pick<LegacyImportDb, "batch" | "prepare">;
type BatchableStatement = BoundResult & {
  __runLegacyImportBatch?: () => Promise<{ success: boolean; results: unknown[]; meta: ReturnType<typeof emptyMeta> }>;
};

function emptyMeta(changes = 0, changedDb = false) {
  return {
    duration: 0,
    size_after: 0,
    rows_read: 0,
    rows_written: 0,
    last_row_id: 0,
    changes,
    changed_db: changedDb,
  } as const;
}

function asD1Mock(db: DatabaseSync, options: { failBatchStatementAt?: number } = {}): D1Mock {
  const normalizeValue = (value: unknown) => {
    if (typeof value === "boolean") return value ? 1 : 0;
    return value;
  };

  const prepare = (sql: string) => {
    const statement = db.prepare(sql);
    const executeBound = (...values: unknown[]): BatchableStatement => {
      const run = async () => {
        const castValues = values as Parameters<(typeof statement)["run"]>;
        const normalizedValues = castValues.map(normalizeValue) as Parameters<(typeof statement)["run"]>;
        const result = statement.run(...normalizedValues);
        return {
          success: true,
          results: [],
          meta: emptyMeta(Number(result.changes ?? 0), true),
        };
      };
      return {
        bind: (...nextValues: unknown[]) => executeBound(...nextValues),
        run: run as BoundResult["run"],
        first: (async () => {
          const castValues = values as Parameters<(typeof statement)["get"]>;
          const row = statement.get(...castValues) as Record<string, unknown> | null;
          return row ?? null;
        }) as BoundResult["first"],
        all: (async () => {
          const castValues = values as Parameters<(typeof statement)["all"]>;
          return {
            success: true,
            results: statement.all(...castValues) as Record<string, unknown>[],
            meta: emptyMeta(0, false),
          };
        }) as BoundResult["all"],
        raw: (() => Promise.resolve([[],] as [string[], ...unknown[]])) as BoundResult["raw"],
        __runLegacyImportBatch: run,
      };
    };
    const bindless: BoundResult = {
      bind: (...values: unknown[]) => executeBound(...values),
      run: (async () => {
        const result = statement.run();
        return {
          success: true,
          results: [],
          meta: emptyMeta(Number(result.changes ?? 0)),
        };
      }) as BoundResult["run"],
      first: (async () => {
        const row = statement.get() as Record<string, unknown> | null;
        return row ?? null;
      }) as BoundResult["first"],
      all: (async () => {
        return {
          success: true,
          results: statement.all() as Record<string, unknown>[],
          meta: emptyMeta(0, false),
        };
      }) as BoundResult["all"],
      raw: (() => Promise.resolve([[],] as [string[], ...unknown[]])) as BoundResult["raw"],
    };
    return {
      bind: (...values: unknown[]) => executeBound(...values),
      run: bindless.run,
      first: bindless.first,
      all: bindless.all,
      raw: bindless.raw,
    } as D1PreparedStatement;
  };

  return {
    prepare,
    async batch<T = unknown>(statements: D1PreparedStatement[]): Promise<D1Result<T>[]> {
      db.exec("SAVEPOINT legacy_import_batch");
      try {
        const results = [];
        for (let index = 0; index < statements.length; index += 1) {
          if (options.failBatchStatementAt === index + 1) throw new Error("simulated batch interruption");
          const run = (statements[index] as unknown as BatchableStatement).__runLegacyImportBatch;
          if (!run) throw new Error("missing test batch runner");
          results.push(await run());
        }
        db.exec("RELEASE SAVEPOINT legacy_import_batch");
        return results as D1Result<T>[];
      } catch (error) {
        db.exec("ROLLBACK TO SAVEPOINT legacy_import_batch");
        db.exec("RELEASE SAVEPOINT legacy_import_batch");
        throw error;
      }
    },
  };
}

async function setupDb() {
  const db = new DatabaseSync(":memory:");
  const migrationOne = await readFile("drizzle/0001_auth_and_product.sql", "utf8");
  const migrationTwo = await readFile("drizzle/0002_s2_tenant_indexes.sql", "utf8");
  db.exec(migrationOne);
  db.exec(migrationTwo);
  const now = Date.now();
  db.prepare("INSERT INTO user (id, name, email, emailVerified, createdAt, updatedAt) VALUES (?, ?, ?, 1, ?, ?)")
    .run("user_legacy", "Legacy", "legacy@example.test", now, now);
  return db;
}

function legacyEnvelope(overrides: Record<string, unknown> = {}) {
  return {
    sourceInstanceId: "device_legacy_01",
    sourceSchemaVersion: 1,
    exportedAt: "2026-08-05T00:00:00.000Z",
    modules: {
      habits: [
        { id: "habit_0000001", title: "晨起", iconKey: "sun" },
      ],
      habitCheckins: [
        { id: "habit_checkin_001", habitId: "habit_0000001", localDate: "2026-08-05" },
      ],
      todos: [
        { id: "todo_00000001", title: "喝水", dueDate: "2026-08-05" },
      ],
      ledger: [
        { id: "ledger_000001", kind: "expense", amountCents: 1200, currency: "CNY", localDate: "2026-08-05", category: "餐饮" },
      ],
      food: [
        { id: "food_0000001", foodName: "米饭", calories: 230, meal: "lunch", localDate: "2026-08-05" },
      ],
      exercise: [
        { id: "exercise_001", activity: "快走", durationMinutes: 30, localDate: "2026-08-05" },
      ],
      weight: [
        { id: "weight_001", weightGrams: 65000, localDate: "2026-08-05" },
      ],
      schedule: [
        { id: "schedule_1", title: "复盘", startsAt: 1722828000000, allDay: true },
      ],
      anniversaries: [
        { id: "anniv_001", title: "朋友生日", localDate: "2026-08-05", repeatYearly: false },
      ],
      diary: [
        { id: "diary_001", localDate: "2026-08-05", body: "今天状态不错" },
      ],
      savings: [
        { id: "savings_01", title: "应急金", targetCents: 100000, currency: "CNY" },
      ],
      savingsTransactions: [
        { id: "savings_transaction_001", goalId: "savings_01", amountCents: 1000, localDate: "2026-08-05" },
      ],
      period: [
        { id: "period_01", startDate: "2026-08-01", endDate: "2026-08-05" },
      ],
    },
    imageManifest: [
      { localId: "file_001", module: "food", contentType: "image/jpeg", byteSize: 123, sha256: "a".repeat(64) },
    ],
    ...overrides,
  };
}

test("legacy import preview and apply are idempotent and resumable", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    const payload = legacyEnvelope();
    await setPrivacyConsent(d1, "user_legacy", {
      decision: "accepted",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    });

    const preview = await previewLegacyImport(d1, "user_legacy", payload);
    assert.equal(preview.state, "previewed");
    assert.equal(preview.preview.canApply, true);
    assert.equal(preview.preview.counts.habits, 1);
    assert.equal(preview.replayed, false);

    const applyResult = await applyLegacyImport(d1, "user_legacy", payload);
    assert.equal(applyResult.state, "completed");
    assert.equal(applyResult.replayed, false);
    assert.equal(applyResult.insertedCounts?.habits, 1);
    assert.equal(applyResult.insertedCounts?.habitCheckins, 1);
    assert.equal(applyResult.insertedCounts?.savingsTransactions, 1);
    assert.equal(applyResult.insertedCounts?.period, 1);
    assert.equal(applyResult.totalInserted, 13);

    const habitsCount = db
      .prepare("SELECT COUNT(1) AS count FROM habit_definitions WHERE user_id = ?")
      .get("user_legacy") as { count: number };
    assert.equal(habitsCount.count, 1);

    const foodsCount = db
      .prepare("SELECT COUNT(1) AS count FROM food_entries WHERE user_id = ?")
      .get("user_legacy") as { count: number };
    assert.equal(foodsCount.count, 1);

    const checkinsCount = db
      .prepare("SELECT COUNT(1) AS count FROM habit_checkins WHERE user_id = ?")
      .get("user_legacy") as { count: number };
    assert.equal(checkinsCount.count, 1);

    const transactionsCount = db
      .prepare("SELECT COUNT(1) AS count FROM savings_transactions WHERE user_id = ?")
      .get("user_legacy") as { count: number };
    assert.equal(transactionsCount.count, 1);

    const replay = await applyLegacyImport(d1, "user_legacy", payload);
    assert.equal(replay.state, "completed");
    assert.equal(replay.replayed, true);
    assert.equal(replay.totalInserted, 13);

    const habitsCountAfterReplay = db
      .prepare("SELECT COUNT(1) AS count FROM habit_definitions WHERE user_id = ?")
      .get("user_legacy") as { count: number };
    assert.equal(habitsCountAfterReplay.count, 1);
  } finally {
    db.close();
  }
});

test("legacy import rolls an interrupted D1 batch back, preserves the source, and resumes safely", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    const payload = legacyEnvelope();
    const sourceBeforeAttempt = JSON.stringify(payload);
    await setPrivacyConsent(d1, "user_legacy", {
      decision: "accepted",
      policyVersion: ACCOUNT_PRIVACY_POLICY_VERSION,
      noticeSha256: ACCOUNT_PRIVACY_NOTICE_SHA256,
    });

    const preview = await previewLegacyImport(d1, "user_legacy", payload);
    await assert.rejects(
      () => applyLegacyImport(asD1Mock(db, { failBatchStatementAt: 2 }), "user_legacy", payload),
      /simulated batch interruption/,
    );

    assert.equal(JSON.stringify(payload), sourceBeforeAttempt);
    assert.equal(
      (db.prepare("SELECT COUNT(1) AS count FROM habit_definitions WHERE user_id = ?").get("user_legacy") as { count: number }).count,
      0,
    );
    assert.equal(
      (db.prepare("SELECT COUNT(1) AS count FROM todos WHERE user_id = ?").get("user_legacy") as { count: number }).count,
      0,
    );

    const failed = await getLegacyImportDebugState(d1, "user_legacy", payload.sourceInstanceId, preview.payloadSha256);
    assert.equal(failed?.state, "failed");

    const resumed = await applyLegacyImport(d1, "user_legacy", payload);
    assert.equal(resumed.state, "completed");
    assert.equal(resumed.totalInserted, 13);
    assert.equal(
      (db.prepare("SELECT COUNT(1) AS count FROM habit_definitions WHERE user_id = ?").get("user_legacy") as { count: number }).count,
      1,
    );
    assert.equal(
      (db.prepare("SELECT COUNT(1) AS count FROM ledger_entries WHERE user_id = ?").get("user_legacy") as { count: number }).count,
      1,
    );

    const completed = await getLegacyImportDebugState(d1, "user_legacy", payload.sourceInstanceId, preview.payloadSha256);
    assert.equal(completed?.state, "completed");
  } finally {
    db.close();
  }
});

test("legacy import leaves sensitive payload local until cross-device consent is accepted", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    await assert.rejects(
      () => previewLegacyImport(d1, "user_legacy", legacyEnvelope()),
      (error): error is SensitiveCloudConsentRequiredError => error instanceof SensitiveCloudConsentRequiredError,
    );
    assert.equal(
      (db.prepare("SELECT COUNT(1) AS count FROM legacy_imports WHERE user_id = ?").get("user_legacy") as { count: number }).count,
      0,
    );

    const ordinaryOnly = legacyEnvelope({
      modules: {
        todos: [{ id: "todo_plain_01", title: "普通本地记录", dueDate: "2026-08-05" }],
      },
      imageManifest: [],
    });
    const preview = await previewLegacyImport(d1, "user_legacy", ordinaryOnly);
    assert.equal(preview.state, "previewed");
    assert.equal(preview.preview.counts.todos, 1);
  } finally {
    db.close();
  }
});

test("legacy import rejects conflicting payloads before apply", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    const duplicateIds = legacyEnvelope({
      modules: {
        habits: [
          { id: "dup_000001", title: "A", iconKey: "icon1" },
          { id: "dup_000001", title: "B", iconKey: "icon2" },
        ],
      },
    });
    const duplicatePreview = await previewLegacyImport(d1, "user_legacy", duplicateIds);
    assert.equal(duplicatePreview.preview.canApply, false);
    assert.equal(duplicatePreview.preview.duplicateIds.length, 1);
    await assert.rejects(() => applyLegacyImport(d1, "user_legacy", duplicateIds), (error): error is LegacyImportConflictError => {
      return error instanceof LegacyImportConflictError;
    });

    const missingId = legacyEnvelope({
      modules: {
        habits: [{ title: "bad-row", iconKey: "icon1" }],
      },
    });
    const invalidPreview = await previewLegacyImport(d1, "user_legacy", missingId);
    assert.equal(invalidPreview.preview.canApply, false);
    assert.equal(invalidPreview.preview.invalidItems.length, 1);
    await assert.rejects(() => applyLegacyImport(d1, "user_legacy", missingId), (error): error is LegacyImportConflictError => {
      return error instanceof LegacyImportConflictError;
    });
  } finally {
    db.close();
  }
});

test("legacy import rejects unsupported schema and module payload", async () => {
  const db = await setupDb();
  const d1 = asD1Mock(db);
  try {
    const invalidVersion = legacyEnvelope({ sourceSchemaVersion: 2 });
    await assert.rejects(
      () => applyLegacyImport(d1, "user_legacy", invalidVersion),
      (error): error is LegacyImportError => error instanceof LegacyImportError,
    );

    const invalidModule = legacyEnvelope({
      modules: {
        unknown: [{ id: "x", title: "bad-module" }],
      } as Record<string, unknown>,
    });
    await assert.rejects(
      () => previewLegacyImport(d1, "user_legacy", invalidModule),
      (error): error is LegacyImportError => error instanceof LegacyImportError,
    );
  } finally {
    db.close();
  }
});

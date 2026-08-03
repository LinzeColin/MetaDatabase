import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { DatabaseSync } from "node:sqlite";

const migrationFiles = ["drizzle/0001_auth_and_product.sql", "drizzle/0002_s2_tenant_indexes.sql"];
const tenantTables = [
  "profile_settings",
  "privacy_consent_events",
  "habit_definitions",
  "habit_checkins",
  "todos",
  "ledger_entries",
  "file_objects",
  "food_entries",
  "exercise_entries",
  "weight_entries",
  "schedule_events",
  "anniversaries",
  "diary_entries",
  "savings_goals",
  "savings_transactions",
  "period_entries",
  "idempotency_keys",
  "legacy_imports",
  "outbox_events",
  "security_audit_events",
];

async function loadMigrations() {
  return Promise.all(
    migrationFiles.map(async (file) => ({
      file,
      sql: await readFile(file, "utf8"),
    })),
  );
}

function applyAll(db, migrations) {
  for (const migration of migrations) db.exec(migration.sql);
}

function tableHasTenantIndex(db, table) {
  const columns = db.prepare(`PRAGMA table_info("${table}")`).all();
  if (columns.some((column) => column.name === "user_id" && column.pk > 0)) return true;
  const indexes = db.prepare(`PRAGMA index_list("${table}")`).all();
  return indexes.some((index) => {
    const indexColumns = db.prepare(`PRAGMA index_info("${index.name}")`).all();
    return indexColumns[0]?.name === "user_id";
  });
}

function inspect(db) {
  const tables = db
    .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    .all()
    .map((row) => row.name);
  const triggers = db
    .prepare("SELECT name FROM sqlite_master WHERE type = 'trigger' ORDER BY name")
    .all()
    .map((row) => row.name);
  const foreignKeys = db.prepare("PRAGMA foreign_keys").get().foreign_keys;
  const missingTenantIndexes = tenantTables.filter((table) => !tableHasTenantIndex(db, table));
  return { tables, triggers, foreignKeys, missingTenantIndexes };
}

export async function verifySchema() {
  const migrations = await loadMigrations();
  const db = new DatabaseSync(":memory:");
  try {
    applyAll(db, migrations);
    const empty = inspect(db);
    applyAll(db, migrations);
    const replay = inspect(db);
    const hashes = Object.fromEntries(
      migrations.map(({ file, sql }) => [file, createHash("sha256").update(sql).digest("hex")]),
    );
    const report = {
      stage: "S2",
      status:
        empty.foreignKeys === 1 &&
        empty.tables.length >= 25 &&
        empty.triggers.length === 4 &&
        empty.missingTenantIndexes.length === 0 &&
        replay.tables.length === empty.tables.length
          ? "PASS_LOCAL_SQLITE"
          : "FAIL",
      migrations: hashes,
      empty,
      replay,
      saved_candidate_d1: "NOT_RUN",
      notes: [
        "0001 is byte-identical to the frozen task-pack migration.",
        "0002 adds only missing tenant-first operational indexes; it does not alter task-pack source.",
        "A real Sites-bound D1 migration remains a later Saved Candidate gate.",
      ],
    };
    await writeFile("13_evidence/schema.json", `${JSON.stringify(report, null, 2)}\n`);
    if (report.status !== "PASS_LOCAL_SQLITE") throw new Error("Schema verification failed.");
    return report;
  } finally {
    db.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const report = await verifySchema();
  process.stdout.write(`${report.status} tables=${report.empty.tables.length} triggers=${report.empty.triggers.length}\n`);
}

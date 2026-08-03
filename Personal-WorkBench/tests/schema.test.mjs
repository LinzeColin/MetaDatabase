import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFile } from "node:fs/promises";
import { verifySchema } from "../scripts/verify-schema.mjs";

const migrationFiles = ["drizzle/0001_auth_and_product.sql", "drizzle/0002_s2_tenant_indexes.sql"];

async function database() {
  const db = new DatabaseSync(":memory:");
  for (const file of migrationFiles) db.exec(await readFile(file, "utf8"));
  return db;
}

test("frozen schema migrates cleanly and replay is idempotent", async () => {
  const report = await verifySchema();
  assert.equal(report.status, "PASS_LOCAL_SQLITE");
  assert.equal(report.migrations["drizzle/0001_auth_and_product.sql"], "9e353bf3148267cd3b6e86654643a202321b1c3ef361b6590944e0d237fee497");
});

test("tenant composite foreign keys and image triggers reject cross-user records", async () => {
  const db = await database();
  try {
    const now = Date.now();
    db.prepare('INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt) VALUES (?, ?, ?, 1, ?, ?)')
      .run("user_a", "A", "a@example.test", now, now);
    db.prepare('INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt) VALUES (?, ?, ?, 1, ?, ?)')
      .run("user_b", "B", "b@example.test", now, now);
    db.prepare('INSERT INTO habit_definitions (id, user_id, title, icon_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)')
      .run("habit_a", "user_a", "Walk", "walk", now, now);
    assert.throws(() => {
      db.prepare('INSERT INTO habit_checkins (id, user_id, habit_id, local_date, checked_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)')
        .run("check_b", "user_b", "habit_a", "2026-08-03", now, now, now);
    });
    assert.throws(() => {
      db.prepare('INSERT INTO file_objects (id, user_id, object_key, module, content_type, byte_size, sha256, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
        .run("file_bad", "user_b", "users/user_a/food/file_bad", "food", "image/png", 1, "0".repeat(64), now, now);
    });
    db.prepare('INSERT INTO file_objects (id, user_id, object_key, module, content_type, byte_size, sha256, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
      .run("file_a", "user_a", "users/user_a/food/file_a", "food", "image/png", 1, "0".repeat(64), now, now);
    assert.throws(() => {
      db.prepare('INSERT INTO food_entries (id, user_id, food_name, calories, meal, local_date, photo_object_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
        .run("food_b", "user_b", "rice", 100, "lunch", "2026-08-03", "file_a", now, now);
    });
  } finally {
    db.close();
  }
});

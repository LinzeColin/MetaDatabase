import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

async function database() {
  const db = new DatabaseSync(":memory:");
  db.exec(await readFile("drizzle/0001_auth_and_product.sql", "utf8"));
  db.exec(await readFile("drizzle/0002_s2_tenant_indexes.sql", "utf8"));
  const now = Date.now();
  for (const [id, email] of [["user_a", "a@example.test"], ["user_b", "b@example.test"]]) {
    db.prepare('INSERT INTO "user" (id, name, email, emailVerified, createdAt, updatedAt) VALUES (?, ?, ?, 1, ?, ?)')
      .run(id, id, email, now, now);
  }
  db.prepare('INSERT INTO todos (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)')
    .run("todo_a", "user_a", "A only", now, now);
  return db;
}

test("user-scoped SQL returns no cross-tenant record", async () => {
  const db = await database();
  try {
    const own = db.prepare("SELECT id FROM todos WHERE id = ? AND user_id = ?").get("todo_a", "user_a");
    const foreign = db.prepare("SELECT id FROM todos WHERE id = ? AND user_id = ?").get("todo_a", "user_b");
    assert.equal(own.id, "todo_a");
    assert.equal(foreign, undefined);
  } finally {
    db.close();
  }
});

test("a user cannot rewrite another tenant's row with a scoped update", async () => {
  const db = await database();
  try {
    db.prepare("UPDATE todos SET title = ? WHERE id = ? AND user_id = ?").run("changed", "todo_a", "user_b");
    const row = db.prepare("SELECT title FROM todos WHERE id = ? AND user_id = ?").get("todo_a", "user_a");
    assert.equal(row.title, "A only");
  } finally {
    db.close();
  }
});

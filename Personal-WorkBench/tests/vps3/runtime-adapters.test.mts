import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import Database from "better-sqlite3";
import {
  configureSqlite,
  SqliteD1Database,
} from "../../server/runtime/vps3/sqlite-d1.ts";
import { qualifyObjectKey } from "../../server/runtime/vps3/r2-s3.ts";

test("SQLite adapter executes the D1 methods used by the workbench", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "personal-workbench-vps3-"));
  const sqlite = new Database(path.join(directory, "runtime.sqlite3"));
  configureSqlite(sqlite);
  const db = new SqliteD1Database(sqlite);

  await db.exec("CREATE TABLE records (id TEXT PRIMARY KEY, owner TEXT NOT NULL, value INTEGER NOT NULL)");
  const insert = await db.prepare("INSERT INTO records (id, owner, value) VALUES (?, ?, ?)")
    .bind("a", "owner-a", 1)
    .run();
  assert.equal(insert.meta.changes, 1);

  const row = await db.prepare("SELECT id, owner, value FROM records WHERE id = ?")
    .bind("a")
    .first<{ id: string; owner: string; value: number }>();
  assert.deepEqual(row, { id: "a", owner: "owner-a", value: 1 });

  const list = await db.prepare("SELECT id, owner, value FROM records ORDER BY id").all();
  assert.equal(list.results.length, 1);

  const results = await db.batch([
    db.prepare("UPDATE records SET value = ? WHERE id = ?").bind(2, "a"),
    db.prepare("INSERT INTO records (id, owner, value) VALUES (?, ?, ?)").bind("b", "owner-b", 3),
  ]);
  assert.deepEqual(results.map((result) => result.meta.changes), [1, 1]);

  const value = await db.prepare("SELECT value FROM records WHERE id = ?").bind("a").first<number>("value");
  assert.equal(value, 2);

  sqlite.close();
  await rm(directory, { recursive: true, force: true });
});

test("R2 prefix keeps Personal Workbench objects inside its own namespace", () => {
  assert.equal(qualifyObjectKey("personal-workbench", "users/u1/diary/a"), "personal-workbench/users/u1/diary/a");
  assert.equal(qualifyObjectKey("personal-workbench/", "/users/u2/profile/b"), "personal-workbench/users/u2/profile/b");
});

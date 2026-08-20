import assert from "node:assert/strict";
import test from "node:test";
import {
  normalizeSqlBindValue,
  placeholderSql,
  PostgresPreparedStatement,
  translateSql,
} from "../../server/runtime/vps3/postgres-sql.ts";

test("question placeholders become PostgreSQL parameters without touching quoted text", () => {
  assert.equal(
    placeholderSql(`SELECT '?' AS literal, "?" AS identifier, value FROM items WHERE a = ? AND b = ?`),
    `SELECT '?' AS literal, "?" AS identifier, value FROM items WHERE a = $1 AND b = $2`,
  );
});

test("legacy INSERT OR IGNORE is translated to PostgreSQL conflict handling", () => {
  assert.equal(
    translateSql("INSERT OR IGNORE INTO items (id, value) VALUES (?, ?)") ,
    "INSERT INTO items (id, value) VALUES ($1, $2) ON CONFLICT DO NOTHING",
  );
  assert.equal(
    translateSql("INSERT OR IGNORE INTO items (id, value) VALUES (?, ?) RETURNING id"),
    "INSERT INTO items (id, value) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING id",
  );
});

test("boolean and binary bind values retain the existing application contract", () => {
  assert.equal(normalizeSqlBindValue(true), 1);
  assert.equal(normalizeSqlBindValue(false), 0);
  const bytes = normalizeSqlBindValue(new Uint8Array([1, 2, 3]));
  assert.ok(Buffer.isBuffer(bytes));
  assert.deepEqual([...bytes as Buffer], [1, 2, 3]);
});

test("prepared statement exposes D1-compatible results over a PostgreSQL executor", async () => {
  const calls: Array<{ text: string; values: unknown[] }> = [];
  const executor = {
    async query(text: string, values: unknown[]) {
      calls.push({ text, values });
      return {
        rows: [{ id: "row-1", value: 7 }],
        rowCount: 1,
        fields: [{ name: "id" }, { name: "value" }],
      };
    },
  };
  const statement = new PostgresPreparedStatement(executor as never, "SELECT id, value FROM records WHERE id = ?")
    .bind("row-1");
  assert.deepEqual(await statement.first(), { id: "row-1", value: 7 });
  assert.equal(calls[0]?.text, "SELECT id, value FROM records WHERE id = $1");
  assert.deepEqual(calls[0]?.values, ["row-1"]);
});

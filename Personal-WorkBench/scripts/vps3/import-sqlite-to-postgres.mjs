import Database from "better-sqlite3";
import { Pool } from "pg";
import process from "node:process";

const source = process.argv[2];
const connectionString = process.env.DATABASE_URL?.trim();
if (!source || !connectionString) {
  throw new Error("usage: DATABASE_URL=... node scripts/vps3/import-sqlite-to-postgres.mjs /path/to/source.sqlite3");
}

const sqlite = new Database(source, { readonly: true });
const pool = new Pool({ connectionString, max: 2, connectionTimeoutMillis: 10_000 });
const client = await pool.connect();
const tables = sqlite.prepare(`
  SELECT name FROM sqlite_master
  WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name NOT IN ('vps3_migrations')
  ORDER BY name
`).all().map((row) => String(row.name));

const quote = (name) => `"${String(name).replaceAll('"', '""')}"`;
const report = {};
try {
  await client.query("BEGIN");
  await client.query("SET CONSTRAINTS ALL DEFERRED").catch(() => undefined);
  for (const table of tables) {
    const columns = sqlite.prepare(`PRAGMA table_info(${quote(table)})`).all().map((row) => String(row.name));
    if (!columns.length) continue;
    const rows = sqlite.prepare(`SELECT * FROM ${quote(table)}`).all();
    let inserted = 0;
    for (const row of rows) {
      const values = columns.map((column) => row[column]);
      const placeholders = values.map((_, index) => `$${index + 1}`).join(", ");
      const sql = `INSERT INTO ${quote(table)} (${columns.map(quote).join(", ")}) VALUES (${placeholders}) ON CONFLICT DO NOTHING`;
      const result = await client.query(sql, values);
      inserted += result.rowCount ?? 0;
    }
    const count = await client.query(`SELECT COUNT(*)::bigint AS count FROM ${quote(table)}`);
    report[table] = { source: rows.length, inserted, target: Number(count.rows[0]?.count ?? 0) };
  }
  await client.query("COMMIT");
  console.log(JSON.stringify({ ok: true, tables: report }, null, 2));
} catch (error) {
  await client.query("ROLLBACK");
  throw error;
} finally {
  sqlite.close();
  client.release();
  await pool.end();
}

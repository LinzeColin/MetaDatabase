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
  const foreignKeys = await client.query(`
    SELECT
      constraint.table_name AS table_name,
      referenced.table_name AS referenced_table
    FROM information_schema.table_constraints AS constraint
    JOIN information_schema.referential_constraints AS relation
      ON relation.constraint_catalog = constraint.constraint_catalog
      AND relation.constraint_schema = constraint.constraint_schema
      AND relation.constraint_name = constraint.constraint_name
    JOIN information_schema.constraint_column_usage AS referenced
      ON referenced.constraint_catalog = relation.unique_constraint_catalog
      AND referenced.constraint_schema = relation.unique_constraint_schema
      AND referenced.constraint_name = relation.unique_constraint_name
    WHERE constraint.constraint_type = 'FOREIGN KEY'
      AND constraint.table_schema = current_schema()
      AND referenced.table_schema = current_schema()
  `);
  const remaining = new Set(tables);
  const dependencies = new Map(tables.map((table) => [table, new Set()]));
  for (const row of foreignKeys.rows) {
    const table = String(row.table_name);
    const referenced = String(row.referenced_table);
    if (table !== referenced && remaining.has(table) && remaining.has(referenced)) {
      dependencies.get(table)?.add(referenced);
    }
  }
  const importOrder = [];
  while (remaining.size) {
    const ready = [...remaining]
      .filter((table) => [...(dependencies.get(table) ?? [])].every((dependency) => !remaining.has(dependency)))
      .sort();
    if (!ready.length) {
      importOrder.push(...[...remaining].sort());
      break;
    }
    importOrder.push(...ready);
    for (const table of ready) remaining.delete(table);
  }

  for (const table of importOrder) {
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

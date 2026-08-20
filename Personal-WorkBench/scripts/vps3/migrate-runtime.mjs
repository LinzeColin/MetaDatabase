import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { Pool } from "pg";

const connectionString = process.env.DATABASE_URL?.trim();
if (!connectionString) throw new Error("DATABASE_URL is required.");

const pool = new Pool({ connectionString, max: 2, connectionTimeoutMillis: 10_000 });
const migrationsPath = path.resolve(process.cwd(), "drizzle/postgres");
const client = await pool.connect();
try {
  await client.query(`
    CREATE TABLE IF NOT EXISTS pwb_schema_migrations (
      name TEXT PRIMARY KEY,
      applied_at BIGINT NOT NULL
    )
  `);
  const files = (await readdir(migrationsPath))
    .filter((name) => /^\d+.*\.sql$/.test(name))
    .sort((left, right) => left.localeCompare(right, "en"));

  for (const name of files) {
    const existing = await client.query(
      "SELECT 1 FROM pwb_schema_migrations WHERE name = $1 LIMIT 1",
      [name],
    );
    if (existing.rowCount) continue;
    const sql = await readFile(path.join(migrationsPath, name), "utf8");
    await client.query("BEGIN");
    try {
      await client.query(sql);
      await client.query(
        "INSERT INTO pwb_schema_migrations (name, applied_at) VALUES ($1, $2)",
        [name, Date.now()],
      );
      await client.query("COMMIT");
      console.log(`migration_applied=${name}`);
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    }
  }

  const count = await client.query(
    "SELECT COUNT(*)::bigint AS count FROM information_schema.tables WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'",
  );
  console.log("database_ready=postgresql");
  console.log(`table_count=${count.rows[0]?.count ?? 0}`);
} finally {
  client.release();
  await pool.end();
}

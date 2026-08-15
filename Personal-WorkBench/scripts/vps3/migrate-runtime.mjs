import Database from "better-sqlite3";
import { mkdir, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const databasePath = path.resolve(process.env.RUNTIME_DB_PATH || "./.runtime/personal-workbench.sqlite3");
const migrationsPath = path.resolve(process.cwd(), "drizzle");
await mkdir(path.dirname(databasePath), { recursive: true });

const database = new Database(databasePath);
database.pragma("foreign_keys = ON");
database.pragma("journal_mode = WAL");
database.pragma("synchronous = NORMAL");
database.pragma("busy_timeout = 5000");
database.exec(`
  CREATE TABLE IF NOT EXISTS vps3_migrations (
    name TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL
  );
`);

const applied = database.prepare("SELECT 1 FROM vps3_migrations WHERE name = ? LIMIT 1");
const record = database.prepare("INSERT INTO vps3_migrations (name, applied_at) VALUES (?, ?)");
const files = (await readdir(migrationsPath))
  .filter((name) => /^\d+.*\.sql$/.test(name))
  .sort((left, right) => left.localeCompare(right, "en"));

for (const name of files) {
  if (applied.get(name)) continue;
  const sql = await readFile(path.join(migrationsPath, name), "utf8");
  const migrate = database.transaction(() => {
    database.exec(sql);
    record.run(name, Date.now());
  });
  migrate();
  console.log(`migration_applied=${name}`);
}

const tableCount = database
  .prepare("SELECT COUNT(*) AS count FROM sqlite_master WHERE type = 'table'")
  .get().count;
console.log(`database_ready=${databasePath}`);
console.log(`table_count=${tableCount}`);
database.close();

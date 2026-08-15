import Database from "better-sqlite3";
import { mkdir, readdir, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const databasePath = path.resolve(process.env.RUNTIME_DB_PATH || "/data/personal-workbench.sqlite3");
const backupDirectory = path.resolve(process.env.RUNTIME_BACKUP_DIR || "/data/backups");
const keep = 3;
await mkdir(backupDirectory, { recursive: true });

const stamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
const destination = path.join(backupDirectory, `personal-workbench-${stamp}.sqlite3`);
const database = new Database(databasePath);
await database.backup(destination);
database.close();

const backups = (await readdir(backupDirectory))
  .filter((name) => name.startsWith("personal-workbench-") && name.endsWith(".sqlite3"))
  .sort()
  .reverse();
for (const stale of backups.slice(keep)) {
  await rm(path.join(backupDirectory, stale), { force: true });
}
console.log(`backup_created=${destination}`);
console.log(`backup_retained=${Math.min(backups.length, keep)}`);

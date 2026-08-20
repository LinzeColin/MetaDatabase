import { mkdir, readdir, rm } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";

const connectionString = process.env.DATABASE_URL?.trim();
if (!connectionString) throw new Error("DATABASE_URL is required.");
const backupDirectory = path.resolve(process.env.RUNTIME_BACKUP_DIR || "/data/backups");
const keep = Math.max(1, Number(process.env.BACKUP_KEEP || 3));
await mkdir(backupDirectory, { recursive: true });

const stamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
const destination = path.join(backupDirectory, `personal-workbench-${stamp}.dump`);
const command = spawn("pg_dump", ["--format=custom", "--no-owner", "--file", destination, connectionString], {
  stdio: "inherit",
  env: process.env,
});
const exitCode = await new Promise((resolve) => command.once("exit", resolve));
if (exitCode !== 0) process.exit(Number(exitCode ?? 1));

const backups = (await readdir(backupDirectory))
  .filter((name) => name.startsWith("personal-workbench-") && name.endsWith(".dump"))
  .sort()
  .reverse();
for (const stale of backups.slice(keep)) {
  await rm(path.join(backupDirectory, stale), { force: true });
}
console.log(`backup_created=${destination}`);
console.log(`backup_retained=${Math.min(backups.length, keep)}`);

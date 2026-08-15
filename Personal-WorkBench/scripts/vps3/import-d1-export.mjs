import fs from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";

const [source, target] = process.argv.slice(2);
if (!source || !target) throw new Error("usage: node scripts/vps3/import-d1-export.mjs <d1-export.sql> <target.sqlite3>");
if (fs.existsSync(target)) throw new Error("target sqlite already exists; import must start from a new path");
fs.mkdirSync(path.dirname(target), { recursive: true });
const db = new Database(target);
db.pragma("foreign_keys = OFF");
db.exec(fs.readFileSync(source, "utf8"));
db.pragma("foreign_keys = ON");
const fk = db.pragma("foreign_key_check");
const integrity = db.pragma("integrity_check", { simple: true });
const tableRows = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all();
const counts = Object.fromEntries(tableRows.map(({ name }) => [name, db.prepare(`SELECT count(*) AS n FROM \"${String(name).replaceAll('"','""')}\"`).get().n]));
if (fk.length || integrity !== "ok") throw new Error("import verification failed");
console.log(JSON.stringify({ ok: true, tableCounts: counts }, null, 2));
db.close();

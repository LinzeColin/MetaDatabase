#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

EMBEDDED_OVERLAY = {'Personal-WorkBench/server/runtime/vps3/sqlite-d1.ts': 'import Database from "better-sqlite3";\n\ntype BindValue = string | number | bigint | boolean | null | ArrayBuffer | ArrayBufferView;\n\ntype D1MetaShape = {\n  changed_db: boolean;\n  changes: number;\n  duration: number;\n  last_row_id?: number | bigint;\n  rows_read: number;\n  rows_written: number;\n  size_after: number;\n};\n\nfunction normalizeValue(value: BindValue): string | number | bigint | null | Buffer {\n  if (typeof value === "boolean") return value ? 1 : 0;\n  if (value instanceof ArrayBuffer) return Buffer.from(value);\n  if (ArrayBuffer.isView(value)) {\n    return Buffer.from(value.buffer, value.byteOffset, value.byteLength);\n  }\n  return value;\n}\n\nfunction isRowStatement(sql: string): boolean {\n  return /^\\s*(?:SELECT|PRAGMA|WITH\\b[\\s\\S]*?\\bSELECT|EXPLAIN)/i.test(sql)\n    || /\\bRETURNING\\b/i.test(sql);\n}\n\nfunction meta(changes: number, rowsRead = 0, lastRowId?: number | bigint): D1MetaShape {\n  return {\n    changed_db: changes > 0,\n    changes,\n    duration: 0,\n    ...(lastRowId === undefined ? {} : { last_row_id: lastRowId }),\n    rows_read: rowsRead,\n    rows_written: changes,\n    size_after: 0,\n  };\n}\n\nexport class SqliteD1PreparedStatement {\n  constructor(\n    private readonly database: Database.Database,\n    readonly sql: string,\n    readonly values: Array<string | number | bigint | null | Buffer> = [],\n  ) {}\n\n  bind(...values: BindValue[]): SqliteD1PreparedStatement {\n    return new SqliteD1PreparedStatement(this.database, this.sql, values.map(normalizeValue));\n  }\n\n  async first<T = Record<string, unknown>>(columnName?: string): Promise<T | null> {\n    const row = this.database.prepare(this.sql).get(...this.values) as Record<string, unknown> | undefined;\n    if (!row) return null;\n    if (columnName) return (row[columnName] ?? null) as T | null;\n    return row as T;\n  }\n\n  async all<T = Record<string, unknown>>() {\n    const results = this.database.prepare(this.sql).all(...this.values) as T[];\n    return { success: true, results, meta: meta(0, results.length) };\n  }\n\n  async raw<T = unknown[]>(options?: { columnNames?: boolean }): Promise<T[]> {\n    const statement = this.database.prepare(this.sql).raw(true);\n    const rows = statement.all(...this.values) as unknown[][];\n    if (options?.columnNames) {\n      rows.unshift(statement.columns().map((column) => column.name));\n    }\n    return rows as T[];\n  }\n\n  executeSync<T = Record<string, unknown>>() {\n    if (isRowStatement(this.sql)) {\n      const results = this.database.prepare(this.sql).all(...this.values) as T[];\n      return { success: true, results, meta: meta(0, results.length) };\n    }\n    const result = this.database.prepare(this.sql).run(...this.values);\n    return {\n      success: true,\n      results: [] as T[],\n      meta: meta(result.changes, 0, result.lastInsertRowid),\n    };\n  }\n\n  async run<T = Record<string, unknown>>() {\n    return this.executeSync<T>();\n  }\n}\n\nexport class SqliteD1Database {\n  constructor(readonly sqlite: Database.Database) {}\n\n  prepare(sql: string): SqliteD1PreparedStatement {\n    return new SqliteD1PreparedStatement(this.sqlite, sql);\n  }\n\n  async batch<T = Record<string, unknown>>(statements: SqliteD1PreparedStatement[]) {\n    const execute = this.sqlite.transaction((items: SqliteD1PreparedStatement[]) =>\n      items.map((statement) => {\n        if (!(statement instanceof SqliteD1PreparedStatement)) {\n          throw new TypeError("The batch contains a statement from another database adapter.");\n        }\n        return statement.executeSync<T>();\n      }),\n    );\n    return execute(statements);\n  }\n\n  async exec(sql: string) {\n    const started = performance.now();\n    this.sqlite.exec(sql);\n    const count = sql.split(";").filter((statement) => statement.trim()).length;\n    return { count, duration: performance.now() - started };\n  }\n}\n\nexport function configureSqlite(database: Database.Database): void {\n  database.pragma("foreign_keys = ON");\n  database.pragma("journal_mode = WAL");\n  database.pragma("synchronous = NORMAL");\n  database.pragma("busy_timeout = 5000");\n}\n\nlet runtimeDatabase: SqliteD1Database | null = null;\n\nexport function getVps3Database(): D1Database {\n  if (!runtimeDatabase) {\n    const databasePath = process.env.RUNTIME_DB_PATH?.trim() || "./.runtime/personal-workbench.sqlite3";\n    const sqlite = new Database(databasePath);\n    configureSqlite(sqlite);\n    runtimeDatabase = new SqliteD1Database(sqlite);\n  }\n  return runtimeDatabase as unknown as D1Database;\n}\n', 'Personal-WorkBench/server/runtime/vps3/r2-s3.ts': 'import {\n  DeleteObjectCommand,\n  GetObjectCommand,\n  HeadObjectCommand,\n  PutObjectCommand,\n  S3Client,\n} from "@aws-sdk/client-s3";\n\ntype ObjectStoreConfig = {\n  endpoint: string | null;\n  accountId: string | null;\n  accessKeyId: string | null;\n  secretAccessKey: string | null;\n  bucket: string | null;\n  prefix: string;\n};\n\nexport class ObjectStoreNotReadyError extends Error {\n  code = "OBJECT_STORE_NOT_READY";\n\n  constructor() {\n    super("Personal Workbench object storage is not configured.");\n  }\n}\n\nfunction value(name: string): string | null {\n  return process.env[name]?.trim() || null;\n}\n\nfunction normalizePrefix(prefix: string | null): string {\n  const trimmed = prefix?.replace(/^\\/+|\\/+$/g, "") ?? "";\n  return trimmed ? `${trimmed}/` : "";\n}\n\nfunction isNotFound(error: unknown): boolean {\n  if (!error || typeof error !== "object") return false;\n  const status = (error as { $metadata?: { httpStatusCode?: number } }).$metadata?.httpStatusCode;\n  const name = (error as { name?: string }).name;\n  return status === 404 || name === "NoSuchKey" || name === "NotFound";\n}\n\nexport function qualifyObjectKey(prefix: string, key: string): string {\n  return `${normalizePrefix(prefix)}${key.replace(/^\\/+/, "")}`;\n}\n\nexport class R2S3Bucket {\n  private client: S3Client | null = null;\n\n  constructor(private readonly config: ObjectStoreConfig) {}\n\n  private ready(): { client: S3Client; bucket: string } {\n    const endpoint = this.config.endpoint\n      || (this.config.accountId ? `https://${this.config.accountId}.r2.cloudflarestorage.com` : null);\n    if (!endpoint || !this.config.accessKeyId || !this.config.secretAccessKey || !this.config.bucket) {\n      throw new ObjectStoreNotReadyError();\n    }\n    if (!this.client) {\n      this.client = new S3Client({\n        endpoint,\n        region: "auto",\n        credentials: {\n          accessKeyId: this.config.accessKeyId,\n          secretAccessKey: this.config.secretAccessKey,\n        },\n      });\n    }\n    return { client: this.client, bucket: this.config.bucket };\n  }\n\n  private key(key: string): string {\n    return qualifyObjectKey(this.config.prefix, key);\n  }\n\n  async put(\n    key: string,\n    body: ArrayBuffer | ArrayBufferView | Blob | string,\n    options?: { httpMetadata?: { contentType?: string }; customMetadata?: Record<string, string> },\n  ) {\n    const { client, bucket } = this.ready();\n    let bytes: Uint8Array | string;\n    if (typeof body === "string") bytes = body;\n    else if (body instanceof Blob) bytes = new Uint8Array(await body.arrayBuffer());\n    else if (body instanceof ArrayBuffer) bytes = new Uint8Array(body);\n    else bytes = new Uint8Array(body.buffer, body.byteOffset, body.byteLength);\n\n    const result = await client.send(new PutObjectCommand({\n      Bucket: bucket,\n      Key: this.key(key),\n      Body: bytes,\n      ContentType: options?.httpMetadata?.contentType,\n      Metadata: options?.customMetadata,\n    }));\n    return {\n      key,\n      size: typeof bytes === "string" ? Buffer.byteLength(bytes) : bytes.byteLength,\n      etag: result.ETag?.replaceAll(\'"\', "") ?? "",\n      httpEtag: result.ETag ?? "",\n      uploaded: new Date(),\n    } as unknown as R2Object;\n  }\n\n  async get(key: string): Promise<R2ObjectBody | null> {\n    const { client, bucket } = this.ready();\n    try {\n      const result = await client.send(new GetObjectCommand({ Bucket: bucket, Key: this.key(key) }));\n      if (!result.Body) return null;\n      const body = result.Body.transformToWebStream() as ReadableStream<Uint8Array>;\n      return {\n        key,\n        body,\n        size: Number(result.ContentLength ?? 0),\n        etag: result.ETag?.replaceAll(\'"\', "") ?? "",\n        httpEtag: result.ETag ?? "",\n        uploaded: result.LastModified ?? new Date(0),\n        httpMetadata: { contentType: result.ContentType },\n        customMetadata: result.Metadata,\n        bodyUsed: false,\n        writeHttpMetadata(headers: Headers) {\n          if (result.ContentType) headers.set("content-type", result.ContentType);\n        },\n      } as unknown as R2ObjectBody;\n    } catch (error) {\n      if (isNotFound(error)) return null;\n      throw error;\n    }\n  }\n\n  async head(key: string): Promise<R2Object | null> {\n    const { client, bucket } = this.ready();\n    try {\n      const result = await client.send(new HeadObjectCommand({ Bucket: bucket, Key: this.key(key) }));\n      return {\n        key,\n        size: Number(result.ContentLength ?? 0),\n        etag: result.ETag?.replaceAll(\'"\', "") ?? "",\n        httpEtag: result.ETag ?? "",\n        uploaded: result.LastModified ?? new Date(0),\n        httpMetadata: { contentType: result.ContentType },\n        customMetadata: result.Metadata,\n        writeHttpMetadata(headers: Headers) {\n          if (result.ContentType) headers.set("content-type", result.ContentType);\n        },\n      } as unknown as R2Object;\n    } catch (error) {\n      if (isNotFound(error)) return null;\n      throw error;\n    }\n  }\n\n  async delete(key: string | string[]): Promise<void> {\n    const { client, bucket } = this.ready();\n    const keys = Array.isArray(key) ? key : [key];\n    for (const item of keys) {\n      await client.send(new DeleteObjectCommand({ Bucket: bucket, Key: this.key(item) }));\n    }\n  }\n}\n\nlet runtimeBucket: R2S3Bucket | null = null;\n\nexport function getVps3ObjectStore(): R2Bucket {\n  if (!runtimeBucket) {\n    runtimeBucket = new R2S3Bucket({\n      endpoint: value("R2_ENDPOINT"),\n      accountId: value("R2_ACCOUNT_ID"),\n      accessKeyId: value("R2_ACCESS_KEY_ID"),\n      secretAccessKey: value("R2_SECRET_ACCESS_KEY"),\n      bucket: value("R2_BUCKET_NAME"),\n      prefix: normalizePrefix(value("R2_OBJECT_PREFIX") || "personal-workbench"),\n    });\n  }\n  return runtimeBucket as unknown as R2Bucket;\n}\n', 'Personal-WorkBench/server/runtime/vps3/env.ts': 'import type { AuthRuntimeEnv } from "@/server/auth/runtime";\nimport { getVps3Database } from "./sqlite-d1";\nimport { getVps3ObjectStore } from "./r2-s3";\n\ntype Vps3RuntimeEnv = AuthRuntimeEnv & {\n  DB: D1Database;\n  FILES: R2Bucket;\n  APP_TRUSTED_ORIGINS?: string;\n};\n\nconst values = new Proxy({} as Vps3RuntimeEnv, {\n  get(_target, property: string | symbol) {\n    if (property === "DB") return getVps3Database();\n    if (property === "FILES") return getVps3ObjectStore();\n    if (typeof property !== "string") return undefined;\n    return process.env[property];\n  },\n});\n\nexport const env = values;\n', 'Personal-WorkBench/scripts/vps3/migrate-runtime.mjs': 'import Database from "better-sqlite3";\nimport { mkdir, readdir, readFile } from "node:fs/promises";\nimport path from "node:path";\nimport process from "node:process";\n\nconst databasePath = path.resolve(process.env.RUNTIME_DB_PATH || "./.runtime/personal-workbench.sqlite3");\nconst migrationsPath = path.resolve(process.cwd(), "drizzle");\nawait mkdir(path.dirname(databasePath), { recursive: true });\n\nconst database = new Database(databasePath);\ndatabase.pragma("foreign_keys = ON");\ndatabase.pragma("journal_mode = WAL");\ndatabase.pragma("synchronous = NORMAL");\ndatabase.pragma("busy_timeout = 5000");\ndatabase.exec(`\n  CREATE TABLE IF NOT EXISTS vps3_migrations (\n    name TEXT PRIMARY KEY,\n    applied_at INTEGER NOT NULL\n  );\n`);\n\nconst applied = database.prepare("SELECT 1 FROM vps3_migrations WHERE name = ? LIMIT 1");\nconst record = database.prepare("INSERT INTO vps3_migrations (name, applied_at) VALUES (?, ?)");\nconst files = (await readdir(migrationsPath))\n  .filter((name) => /^\\d+.*\\.sql$/.test(name))\n  .sort((left, right) => left.localeCompare(right, "en"));\n\nfor (const name of files) {\n  if (applied.get(name)) continue;\n  const sql = await readFile(path.join(migrationsPath, name), "utf8");\n  const migrate = database.transaction(() => {\n    database.exec(sql);\n    record.run(name, Date.now());\n  });\n  migrate();\n  console.log(`migration_applied=${name}`);\n}\n\nconst tableCount = database\n  .prepare("SELECT COUNT(*) AS count FROM sqlite_master WHERE type = \'table\'")\n  .get().count;\nconsole.log(`database_ready=${databasePath}`);\nconsole.log(`table_count=${tableCount}`);\ndatabase.close();\n', 'Personal-WorkBench/scripts/vps3/backup-runtime.mjs': 'import Database from "better-sqlite3";\nimport { mkdir, readdir, rm } from "node:fs/promises";\nimport path from "node:path";\nimport process from "node:process";\n\nconst databasePath = path.resolve(process.env.RUNTIME_DB_PATH || "/data/personal-workbench.sqlite3");\nconst backupDirectory = path.resolve(process.env.RUNTIME_BACKUP_DIR || "/data/backups");\nconst keep = 3;\nawait mkdir(backupDirectory, { recursive: true });\n\nconst stamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");\nconst destination = path.join(backupDirectory, `personal-workbench-${stamp}.sqlite3`);\nconst database = new Database(databasePath);\nawait database.backup(destination);\ndatabase.close();\n\nconst backups = (await readdir(backupDirectory))\n  .filter((name) => name.startsWith("personal-workbench-") && name.endsWith(".sqlite3"))\n  .sort()\n  .reverse();\nfor (const stale of backups.slice(keep)) {\n  await rm(path.join(backupDirectory, stale), { force: true });\n}\nconsole.log(`backup_created=${destination}`);\nconsole.log(`backup_retained=${Math.min(backups.length, keep)}`);\n', 'Personal-WorkBench/scripts/vps3/entrypoint.mjs': 'import { spawn } from "node:child_process";\nimport process from "node:process";\n\nconst migrate = spawn(process.execPath, ["scripts/vps3/migrate-runtime.mjs"], {\n  stdio: "inherit",\n  env: process.env,\n});\nconst migrationExit = await new Promise((resolve) => migrate.once("exit", resolve));\nif (migrationExit !== 0) process.exit(Number(migrationExit ?? 1));\n\nconst server = spawn(process.execPath, ["server.js"], {\n  stdio: "inherit",\n  env: process.env,\n});\nfor (const signal of ["SIGTERM", "SIGINT"]) {\n  process.on(signal, () => server.kill(signal));\n}\nserver.once("exit", (code, signal) => {\n  if (signal) process.kill(process.pid, signal);\n  else process.exit(Number(code ?? 0));\n});\n', 'Personal-WorkBench/app/api/health/route.ts': 'import { env } from "@/server/runtime/vps3/env";\n\nexport const runtime = "nodejs";\nexport const dynamic = "force-dynamic";\n\nexport async function GET(): Promise<Response> {\n  try {\n    const result = await env.DB.prepare("SELECT 1 AS ready").first<{ ready: number }>();\n    if (result?.ready !== 1) throw new Error("database not ready");\n    return Response.json(\n      { service: "personal-workbench", ready: true },\n      { headers: { "Cache-Control": "no-store" } },\n    );\n  } catch {\n    return Response.json(\n      { service: "personal-workbench", ready: false },\n      { status: 503, headers: { "Cache-Control": "no-store" } },\n    );\n  }\n}\n', 'Personal-WorkBench/Dockerfile.vps3': '# syntax=docker/dockerfile:1.7\nFROM node:22-bookworm-slim AS dependencies\nWORKDIR /app\nRUN apt-get update \\\n && apt-get install -y --no-install-recommends python3 make g++ ca-certificates \\\n && rm -rf /var/lib/apt/lists/*\nCOPY package.json package-lock.json ./\nRUN npm ci --no-audit --no-fund\n\nFROM dependencies AS builder\nWORKDIR /app\nARG APP_ORIGIN=https://mydairy.linzezhang.com\nENV NEXT_TELEMETRY_DISABLED=1 \\\n    APP_ORIGIN=${APP_ORIGIN} \\\n    RUNTIME_DB_PATH=/tmp/personal-workbench-build.sqlite3\nCOPY . .\nRUN npm run build:vps3\n\nFROM node:22-bookworm-slim AS runtime\nWORKDIR /app\nENV NODE_ENV=production \\\n    NEXT_TELEMETRY_DISABLED=1 \\\n    HOSTNAME=0.0.0.0 \\\n    PORT=3000 \\\n    RUNTIME_DB_PATH=/data/personal-workbench.sqlite3 \\\n    RUNTIME_BACKUP_DIR=/data/backups \\\n    R2_OBJECT_PREFIX=personal-workbench \\\n    WORKBENCH_REQUIRE_SENSITIVE_CONSENT=0\nRUN mkdir -p /data/backups \\\n && chown -R node:node /data /app\nCOPY --from=builder --chown=node:node /app/.next/standalone ./\nCOPY --from=builder --chown=node:node /app/.next/static ./.next/static\nCOPY --from=builder --chown=node:node /app/public ./public\nCOPY --from=builder --chown=node:node /app/drizzle ./drizzle\nCOPY --from=builder --chown=node:node /app/scripts/vps3 ./scripts/vps3\nUSER node\nEXPOSE 3000\nVOLUME ["/data"]\nHEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=5 \\\n  CMD node -e "fetch(\'http://127.0.0.1:3000/api/health\').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"\nCMD ["node", "scripts/vps3/entrypoint.mjs"]\n', 'Personal-WorkBench/.dockerignore.vps3': 'node_modules\n.next\ndist\n.runtime\n.env*\nplaywright-report\ntest-results\nvps3-acceptance-output\n13_evidence/visual/round-*\n', 'Personal-WorkBench/compose.vps3.yml': 'services:\n  personal-workbench:\n    build:\n      context: .\n      dockerfile: Dockerfile.vps3\n      args:\n        APP_ORIGIN: ${APP_ORIGIN}\n    image: personal-workbench:vps3\n    restart: unless-stopped\n    env_file:\n      - .env.vps3\n    environment:\n      NODE_ENV: production\n      PORT: 3000\n      HOSTNAME: 0.0.0.0\n      RUNTIME_DB_PATH: /data/personal-workbench.sqlite3\n      RUNTIME_BACKUP_DIR: /data/backups\n      WORKBENCH_REQUIRE_SENSITIVE_CONSENT: "0"\n    volumes:\n      - personal_workbench_data:/data\n    expose:\n      - "3000"\n\nvolumes:\n  personal_workbench_data:\n    name: personal_workbench_data\n', 'Personal-WorkBench/.env.vps3.example': 'APP_ORIGIN=https://mydairy.linzezhang.com\nAPP_TRUSTED_ORIGINS=https://mydairy.linzezhang.com\nBETTER_AUTH_SECRET=\nGOOGLE_CLIENT_ID=\nGOOGLE_CLIENT_SECRET=\nMAIL_PROVIDER=resend\nRESEND_API_KEY=\nAUTH_FROM_EMAIL=\nTURNSTILE_SECRET_KEY=\nTURNSTILE_SITE_KEY=\nLEGAL_OPERATOR_NAME=\nPRIVACY_CONTACT_EMAIL=\nRUNTIME_DB_PATH=/data/personal-workbench.sqlite3\nRUNTIME_BACKUP_DIR=/data/backups\nR2_ACCOUNT_ID=\nR2_ENDPOINT=\nR2_ACCESS_KEY_ID=\nR2_SECRET_ACCESS_KEY=\nR2_BUCKET_NAME=primary-objects\nR2_OBJECT_PREFIX=personal-workbench\nWORKBENCH_REQUIRE_SENSITIVE_CONSENT=0\n', 'Personal-WorkBench/tests/vps3/runtime-adapters.test.mts': 'import assert from "node:assert/strict";\nimport { mkdtemp, rm } from "node:fs/promises";\nimport os from "node:os";\nimport path from "node:path";\nimport test from "node:test";\nimport Database from "better-sqlite3";\nimport {\n  configureSqlite,\n  SqliteD1Database,\n} from "../../server/runtime/vps3/sqlite-d1.ts";\nimport { qualifyObjectKey } from "../../server/runtime/vps3/r2-s3.ts";\n\ntest("SQLite adapter executes the D1 methods used by the workbench", async () => {\n  const directory = await mkdtemp(path.join(os.tmpdir(), "personal-workbench-vps3-"));\n  const sqlite = new Database(path.join(directory, "runtime.sqlite3"));\n  configureSqlite(sqlite);\n  const db = new SqliteD1Database(sqlite);\n\n  await db.exec("CREATE TABLE records (id TEXT PRIMARY KEY, owner TEXT NOT NULL, value INTEGER NOT NULL)");\n  const insert = await db.prepare("INSERT INTO records (id, owner, value) VALUES (?, ?, ?)")\n    .bind("a", "owner-a", 1)\n    .run();\n  assert.equal(insert.meta.changes, 1);\n\n  const row = await db.prepare("SELECT id, owner, value FROM records WHERE id = ?")\n    .bind("a")\n    .first<{ id: string; owner: string; value: number }>();\n  assert.deepEqual(row, { id: "a", owner: "owner-a", value: 1 });\n\n  const list = await db.prepare("SELECT id, owner, value FROM records ORDER BY id").all();\n  assert.equal(list.results.length, 1);\n\n  const results = await db.batch([\n    db.prepare("UPDATE records SET value = ? WHERE id = ?").bind(2, "a"),\n    db.prepare("INSERT INTO records (id, owner, value) VALUES (?, ?, ?)").bind("b", "owner-b", 3),\n  ]);\n  assert.deepEqual(results.map((result) => result.meta.changes), [1, 1]);\n\n  const value = await db.prepare("SELECT value FROM records WHERE id = ?").bind("a").first<number>("value");\n  assert.equal(value, 2);\n\n  sqlite.close();\n  await rm(directory, { recursive: true, force: true });\n});\n\ntest("R2 prefix keeps Personal Workbench objects inside its own namespace", () => {\n  assert.equal(qualifyObjectKey("personal-workbench", "users/u1/diary/a"), "personal-workbench/users/u1/diary/a");\n  assert.equal(qualifyObjectKey("personal-workbench/", "/users/u2/profile/b"), "personal-workbench/users/u2/profile/b");\n});\n', 'Personal-WorkBench/tests/vps3/brand-contract.test.mjs': 'import assert from "node:assert/strict";\nimport { readFile } from "node:fs/promises";\nimport test from "node:test";\n\nconst layout = await readFile(new URL("../../app/layout.tsx", import.meta.url), "utf8");\nconst home = await readFile(new URL("../../app/page.tsx", import.meta.url), "utf8");\nconst packageJson = JSON.parse(await readFile(new URL("../../package.json", import.meta.url), "utf8"));\n\ntest("public brand is Personal Workbench while technical compatibility paths remain unchanged", () => {\n  assert.equal(packageJson.name, "personal-workbench");\n  assert.match(layout, /个人工作台/);\n  assert.match(home, /个人工作台/);\n  assert.doesNotMatch(layout, /个人日程/);\n  assert.doesNotMatch(home, /个人日程/);\n  assert.match(home, /\\/api\\/mydairy|hrefFor/);\n});\n', 'Personal-WorkBench/playwright.vps3.config.ts': 'import { defineConfig, devices } from "@playwright/test";\n\nconst baseURL = process.env.PWB_BASE_URL || "http://127.0.0.1:3000";\n\nexport default defineConfig({\n  testDir: "./tests/vps3",\n  testMatch: ["ui-inventory.spec.ts", "two-account.spec.ts"],\n  timeout: 45_000,\n  expect: { timeout: 10_000 },\n  fullyParallel: false,\n  forbidOnly: true,\n  retries: 0,\n  reporter: [["list"], ["json", { outputFile: "vps3-acceptance-output/results.json" }]],\n  use: {\n    baseURL,\n    trace: "retain-on-failure",\n    screenshot: "only-on-failure",\n    video: "retain-on-failure",\n  },\n  projects: [\n    { name: "desktop", use: { ...devices["Desktop Chrome"] } },\n    { name: "mobile-360", use: { ...devices["Galaxy S9+"] } },\n  ],\n});\n', 'Personal-WorkBench/tests/vps3/ui-inventory.spec.ts': 'import { expect, test } from "@playwright/test";\n\nconst routes = [\n  ["welcome", "/"],\n  ["home", "/?view=home"],\n  ["todo", "/?view=todo"],\n  ["ledger", "/?view=ledger"],\n  ["fatloss-food", "/?view=fatloss-food"],\n  ["schedule", "/?view=schedule"],\n  ["anniversary", "/?view=anniversary"],\n  ["diary", "/?view=diary"],\n  ["savings", "/?view=savings"],\n  ["period", "/?view=period"],\n] as const;\n\ntest.describe("public workbench surface", () => {\n  for (const [name, route] of routes) {\n    test(`${name} renders and every visible non-destructive button can be activated`, async ({ page }) => {\n      const runtimeErrors: string[] = [];\n      page.on("pageerror", (error) => runtimeErrors.push(error.message));\n      await page.goto(route, { waitUntil: "networkidle" });\n      await expect(page.locator("body")).toContainText(/个人工作台|慢慢来|桌面|待办|记账|减脂|日程|纪念|日记|存钱|经期/);\n\n      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);\n      expect(overflow).toBeLessThanOrEqual(2);\n\n      const buttonNames = await page.getByRole("button").evaluateAll((buttons) =>\n        buttons\n          .filter((button) => !button.hasAttribute("disabled"))\n          .map((button) => (button.getAttribute("aria-label") || button.textContent || "").trim())\n          .filter((value) => value && !/删除账户|确认删除账户/.test(value)),\n      );\n\n      for (const accessibleName of [...new Set(buttonNames)]) {\n        await page.goto(route, { waitUntil: "networkidle" });\n        const control = page.getByRole("button", { name: accessibleName, exact: true }).first();\n        if (await control.isVisible().catch(() => false)) {\n          await control.click({ timeout: 5_000 }).catch(() => undefined);\n          await page.waitForTimeout(100);\n        }\n      }\n      expect(runtimeErrors).toEqual([]);\n    });\n  }\n\n  test("navigation reaches all nine workbench modules", async ({ page }) => {\n    await page.goto("/?view=home", { waitUntil: "networkidle" });\n    for (const label of ["桌面", "待办", "记账", "减脂", "日程", "纪念", "日记", "存钱", "经期"]) {\n      const link = page.getByRole("link", { name: label, exact: true });\n      await expect(link).toBeVisible();\n      await link.click();\n      await expect(page.locator("main")).toBeVisible();\n    }\n  });\n\n  test("email, Google, password recovery and account entry are present", async ({ page }) => {\n    await page.goto("/auth/sign-in", { waitUntil: "domcontentloaded" });\n    await expect(page.getByLabel("邮箱")).toBeVisible();\n    await expect(page.getByLabel("密码")).toBeVisible();\n    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();\n    await expect(page.getByRole("link", { name: /Google/ }).or(page.getByRole("button", { name: /Google/ }))).toBeVisible();\n    await expect(page.getByRole("link", { name: "忘记密码？" })).toBeVisible();\n    await expect(page.getByRole("link", { name: /注册/ })).toBeVisible();\n  });\n});\n', 'Personal-WorkBench/tests/vps3/two-account.spec.ts': 'import { expect, test, type APIRequestContext, type Browser, type BrowserContext } from "@playwright/test";\n\nconst accountA = {\n  email: process.env.PWB_TEST_ACCOUNT_A_EMAIL || "",\n  password: process.env.PWB_TEST_ACCOUNT_A_PASSWORD || "",\n};\nconst origin = (process.env.PWB_BASE_URL || "http://127.0.0.1:3000").replace(/\\/$/, "");\n\nconst accountB = {\n  email: process.env.PWB_TEST_ACCOUNT_B_EMAIL || "",\n  password: process.env.PWB_TEST_ACCOUNT_B_PASSWORD || "",\n};\n\nasync function signIn(browser: Browser, account: { email: string; password: string }): Promise<BrowserContext> {\n  const context = await browser.newContext();\n  const page = await context.newPage();\n  await page.goto("/auth/sign-in", { waitUntil: "networkidle" });\n  await page.getByLabel("邮箱").fill(account.email);\n  await page.getByLabel("密码").fill(account.password);\n  await page.getByRole("button", { name: "登录" }).click();\n  await page.waitForURL(/view=home/, { timeout: 30_000 });\n  return context;\n}\n\nasync function json(request: APIRequestContext, method: "get" | "post" | "patch" | "delete", url: string, data?: object) {\n  const mutation = method !== "get";\n  const requestUrl = mutation\n    ? `${url}${url.includes("?") ? "&" : "?"}request_id=${encodeURIComponent(crypto.randomUUID())}`\n    : url;\n  const response = await request[method](requestUrl, {\n    data,\n    headers: {\n      ...(data ? { "content-type": "application/json" } : {}),\n      ...(mutation ? { origin } : {}),\n    },\n  });\n  expect(response.ok(), `${method.toUpperCase()} ${requestUrl}: ${response.status()} ${await response.text()}`).toBeTruthy();\n  return response.json();\n}\n\ntest.describe("real production two-account transaction", () => {\n  test.beforeAll(() => {\n    if (!accountA.email || !accountA.password || !accountB.email || !accountB.password) {\n      throw new Error("Provide two verified disposable production accounts before Phase C acceptance.");\n    }\n  });\n\n  test("account A persists a todo across refresh and a second browser; account B cannot see it", async ({ browser }) => {\n    const marker = `PWB-${Date.now()}`;\n    const contextA = await signIn(browser, accountA);\n    const pageA = await contextA.newPage();\n    await pageA.goto("/?view=todo", { waitUntil: "networkidle" });\n    const title = pageA.locator(\'input\').first();\n    await title.fill(marker);\n    await pageA.getByRole("button", { name: /添加|保存/ }).last().click();\n    await expect(pageA.getByText(marker)).toBeVisible();\n    await pageA.reload({ waitUntil: "networkidle" });\n    await expect(pageA.getByText(marker)).toBeVisible();\n\n    const storage = await contextA.storageState();\n    const secondDeviceA = await browser.newContext({ storageState: storage });\n    const secondPageA = await secondDeviceA.newPage();\n    await secondPageA.goto("/?view=todo", { waitUntil: "networkidle" });\n    await expect(secondPageA.getByText(marker)).toBeVisible();\n\n    const contextB = await signIn(browser, accountB);\n    const pageB = await contextB.newPage();\n    await pageB.goto("/?view=todo", { waitUntil: "networkidle" });\n    await expect(pageB.getByText(marker)).toHaveCount(0);\n\n    await contextB.close();\n    await secondDeviceA.close();\n    await contextA.close();\n  });\n\n  test("all existing resource APIs enforce account isolation", async ({ browser }) => {\n    const contextA = await signIn(browser, accountA);\n    const contextB = await signIn(browser, accountB);\n    const requestA = contextA.request;\n    const requestB = contextB.request;\n    const today = new Date().toISOString().slice(0, 10);\n    const slot = Date.now();\n    const uniqueMonth = String((Math.floor(slot / 1000) % 12) + 1).padStart(2, "0");\n    const uniqueDay = String((Math.floor(slot / 12000) % 28) + 1).padStart(2, "0");\n    const uniqueDate = `2099-${uniqueMonth}-${uniqueDay}`;\n    const now = Date.now();\n\n    const cases: Array<[string, Record<string, unknown>]> = [\n      ["habits", { title: "验收习惯", iconKey: "habit_read.png", sortOrder: 1, active: true }],\n      ["todos", { title: "验收待办", note: "", dueDate: today, priority: "normal", completed: false, completedAt: null }],\n      ["ledger", { kind: "expense", amountCents: 123, currency: "CNY", localDate: today, category: "验收", note: "" }],\n      ["food", { foodName: "验收食物", calories: 10, meal: "breakfast", localDate: today, note: "", photoObjectId: null, source: "manual" }],\n      ["exercise", { activity: "验收运动", durationMinutes: 10, caloriesBurned: 1, localDate: today, note: "" }],\n      ["weights", { weightGrams: 60000, localDate: uniqueDate, note: "" }],\n      ["schedule", { title: "验收日程", note: "", startsAt: now, endsAt: now + 3_600_000, allDay: false }],\n      ["anniversaries", { title: "验收纪念", localDate: today, repeatYearly: true, note: "" }],\n      ["diary", { localDate: today, mood: "好", title: "验收日记", body: "实际环境事务", photoObjectId: null }],\n      ["savings-goals", { title: "验收存钱", targetCents: 10000, currency: "CNY", targetDate: today, archived: false }],\n      ["periods", { startDate: uniqueDate, endDate: uniqueDate, note: "" }],\n    ];\n\n    for (const [resource, payload] of cases) {\n      const created = await json(requestA, "post", `/api/mydairy/${resource}`, payload);\n      const id = created.data.id as string;\n      const listA = await json(requestA, "get", `/api/mydairy/${resource}`);\n      expect(listA.data.some((row: { id: string }) => row.id === id)).toBeTruthy();\n      const listB = await json(requestB, "get", `/api/mydairy/${resource}`);\n      expect(listB.data.some((row: { id: string }) => row.id === id)).toBeFalsy();\n      await json(requestA, "delete", `/api/mydairy/${resource}/${encodeURIComponent(id)}`);\n    }\n\n    await contextB.close();\n    await contextA.close();\n  });\n});\n', 'repository/.github/workflows/personal-workbench-vps3.yml': 'name: Personal Workbench VPS3\n\non:\n  workflow_dispatch:\n    inputs:\n      action:\n        description: validate, deploy, or accept\n        required: true\n        default: validate\n        type: choice\n        options:\n          - validate\n          - deploy\n          - accept\n  push:\n    branches: [main]\n    paths:\n      - Personal-WorkBench/**\n      - .github/workflows/personal-workbench-vps3.yml\n\npermissions:\n  contents: read\n\nconcurrency:\n  group: personal-workbench-vps3\n  cancel-in-progress: false\n\nenv:\n  PROJECT_DIR: Personal-WorkBench\n\njobs:\n  validate:\n    runs-on: ubuntu-latest\n    timeout-minutes: 35\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: 22.16.0\n          cache: npm\n          cache-dependency-path: Personal-WorkBench/package-lock.json\n      - name: Install\n        working-directory: ${{ env.PROJECT_DIR }}\n        run: npm ci --no-audit --no-fund\n      - name: Current-tree checks\n        working-directory: ${{ env.PROJECT_DIR }}\n        run: npm run check:vps3\n      - name: Build the VPS3 image\n        working-directory: ${{ env.PROJECT_DIR }}\n        run: docker build -f Dockerfile.vps3 -t personal-workbench:${{ github.run_id }} .\n\n  deploy:\n    if: github.event_name == \'workflow_dispatch\' && inputs.action == \'deploy\'\n    needs: validate\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n    env:\n      COOLIFY_BASE_URL: ${{ secrets.COOLIFY_BASE_URL }}\n      COOLIFY_API_TOKEN: ${{ secrets.COOLIFY_API_TOKEN }}\n      COOLIFY_APP_UUID: ${{ secrets.PWB_COOLIFY_APP_UUID }}\n    steps:\n      - name: Request the current main deployment\n        shell: bash\n        run: |\n          set -euo pipefail\n          test -n "${COOLIFY_BASE_URL:-}"\n          test -n "${COOLIFY_API_TOKEN:-}"\n          test -n "${COOLIFY_APP_UUID:-}"\n          base="${COOLIFY_BASE_URL%/}"\n          base="${base%/api/v1}/api/v1"\n          receipt="$(mktemp)"\n          curl --fail --silent --show-error --max-time 30 \\\n            -X POST \\\n            -H "Authorization: Bearer ${COOLIFY_API_TOKEN}" \\\n            "${base}/deploy?uuid=${COOLIFY_APP_UUID}&force=false" \\\n            -o "$receipt"\n          deployment="$(python3 - "$receipt" <<\'PY\'\n          import json,sys\n          value=json.load(open(sys.argv[1]))\n          print(value.get(\'deployment_uuid\') or value.get(\'uuid\') or \'\')\n          PY\n          )"\n          test -n "$deployment"\n          echo "deployment_uuid=$deployment" >> "$GITHUB_ENV"\n          rm -f "$receipt"\n      - name: Wait for the bounded deployment result\n        shell: bash\n        run: |\n          set -euo pipefail\n          base="${COOLIFY_BASE_URL%/}"\n          base="${base%/api/v1}/api/v1"\n          for attempt in $(seq 1 60); do\n            status="$(curl --fail --silent --show-error --max-time 15 \\\n              -H "Authorization: Bearer ${COOLIFY_API_TOKEN}" \\\n              "${base}/deployments/${deployment_uuid}" \\\n              | python3 -c \'import json,sys; print(str(json.load(sys.stdin).get("status", "unknown")).lower())\')"\n            case "$status" in\n              finished|success) echo "deployment_status=$status"; exit 0 ;;\n              failed|cancelled|canceled) echo "deployment_status=$status"; exit 1 ;;\n            esac\n            sleep 10\n          done\n          echo "deployment_status=timeout"\n          exit 1\n      - name: Public URL transaction entrance\n        run: |\n          curl --fail --silent --show-error --max-time 30 \\\n            "${{ secrets.PWB_PUBLIC_URL }}/api/health" \\\n            | python3 -c \'import json,sys; v=json.load(sys.stdin); assert v.get("ready") is True\'\n\n  accept:\n    if: github.event_name == \'workflow_dispatch\' && inputs.action == \'accept\'\n    needs: validate\n    runs-on: ubuntu-latest\n    timeout-minutes: 35\n    env:\n      PWB_BASE_URL: ${{ secrets.PWB_PUBLIC_URL }}\n      PWB_TEST_ACCOUNT_A_EMAIL: ${{ secrets.PWB_TEST_ACCOUNT_A_EMAIL }}\n      PWB_TEST_ACCOUNT_A_PASSWORD: ${{ secrets.PWB_TEST_ACCOUNT_A_PASSWORD }}\n      PWB_TEST_ACCOUNT_B_EMAIL: ${{ secrets.PWB_TEST_ACCOUNT_B_EMAIL }}\n      PWB_TEST_ACCOUNT_B_PASSWORD: ${{ secrets.PWB_TEST_ACCOUNT_B_PASSWORD }}\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: 22.16.0\n          cache: npm\n          cache-dependency-path: Personal-WorkBench/package-lock.json\n      - name: Install\n        working-directory: ${{ env.PROJECT_DIR }}\n        run: npm ci --no-audit --no-fund\n      - name: Install Chromium\n        working-directory: ${{ env.PROJECT_DIR }}\n        run: npx playwright install --with-deps chromium\n      - name: Real browser acceptance\n        working-directory: ${{ env.PROJECT_DIR }}\n        run: npm run accept:vps3\n      - uses: actions/upload-artifact@v4\n        if: always()\n        with:\n          name: personal-workbench-vps3-acceptance\n          path: |\n            Personal-WorkBench/vps3-acceptance-output\n            Personal-WorkBench/playwright-report\n            Personal-WorkBench/test-results\n          if-no-files-found: ignore\n          retention-days: 7\n'}

def ensure_embedded_overlay(taskpack_root: Path) -> None:
    overlay_root = taskpack_root / "overlay"
    if overlay_root.is_dir():
        return
    for relative, content in EMBEDDED_OVERLAY.items():
        destination = overlay_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

PRODUCT_DIR = "Personal-WorkBench"
PRODUCT_NAME_ZH = "个人工作台"
PRODUCT_NAME_EN = "Personal Workbench"
TECHNICAL_NAMESPACE = "mydairy"


def locate_project(target: Path) -> tuple[Path, Path]:
    target = target.resolve()
    if (target / "package.json").is_file() and (target / "app").is_dir():
        return target.parent, target
    project = target / PRODUCT_DIR
    if (project / "package.json").is_file() and (project / "app").is_dir():
        return target, project
    raise SystemExit(
        "ADAPT_REQUIRED: 未找到当前 Personal-WorkBench 项目。"
        "开发 Agent 应在最新 MetaDatabase worktree 上执行本脚本，或把项目路径直接传入。"
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_package(project: Path) -> list[str]:
    path = project / "package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    changed: list[str] = []

    if package.get("name") != "personal-workbench":
        package["name"] = "personal-workbench"
        changed.append("package.name")

    scripts = package.setdefault("scripts", {})
    script_values = {
        "dev:vps3": "next dev",
        "build:vps3": "next build",
        "start:vps3": "next start -H 0.0.0.0 -p 3000",
        "db:migrate:vps3": "node scripts/vps3/migrate-runtime.mjs",
        "db:backup:vps3": "node scripts/vps3/backup-runtime.mjs",
        "test:vps3": "node --experimental-strip-types --test tests/vps3/runtime-adapters.test.mts tests/vps3/brand-contract.test.mjs",
        "accept:vps3": "playwright test -c playwright.vps3.config.ts",
        "check:vps3": "npm run lint && npm run typecheck && npm run test:vps3 && npm run test:modules && npm run test:workbench-data && npm run build:vps3",
    }
    for key, value in script_values.items():
        if scripts.get(key) != value:
            scripts[key] = value
            changed.append(f"scripts.{key}")

    dependencies = package.setdefault("dependencies", {})
    dependency_values = {
        "@aws-sdk/client-s3": "3.1090.0",
        "better-sqlite3": "12.11.1",
    }
    for key, value in dependency_values.items():
        if dependencies.get(key) != value:
            dependencies[key] = value
            changed.append(f"dependencies.{key}")

    dev_dependencies = package.setdefault("devDependencies", {})
    dev_dependency_values = {
        "@playwright/test": "1.55.0",
        "@types/better-sqlite3": "7.6.13",
    }
    for key, value in dev_dependency_values.items():
        if dev_dependencies.get(key) != value:
            dev_dependencies[key] = value
            changed.append(f"devDependencies.{key}")

    write_json(path, package)
    return changed


def patch_next_config(project: Path) -> list[str]:
    path = project / "next.config.ts"
    if not path.is_file():
        raise SystemExit("ADAPT_REQUIRED: 当前项目缺少 next.config.ts，开发 Agent 需将同等配置合入最新 Next 配置。")
    text = path.read_text(encoding="utf-8")
    changed: list[str] = []

    if not re.search(r"\boutput\s*:\s*[\"']standalone[\"']", text):
        marker = re.search(r"const\s+nextConfig\s*:\s*NextConfig\s*=\s*\{", text)
        if not marker:
            raise SystemExit("ADAPT_REQUIRED: 无法识别 nextConfig 对象；不得覆盖最新上游配置。")
        insert = marker.end()
        text = text[:insert] + '\n  output: "standalone",' + text[insert:]
        changed.append("nextConfig.output")

    package_match = re.search(r"serverExternalPackages\s*:\s*\[([^\]]*)\]", text, flags=re.S)
    if package_match:
        body = package_match.group(1)
        if "better-sqlite3" not in body:
            replacement = body.rstrip()
            if replacement and not replacement.rstrip().endswith(","):
                replacement += ","
            replacement += '\n    "better-sqlite3",\n  '
            text = text[: package_match.start(1)] + replacement + text[package_match.end(1) :]
            changed.append("nextConfig.serverExternalPackages")
    else:
        marker = re.search(r"const\s+nextConfig\s*:\s*NextConfig\s*=\s*\{", text)
        assert marker is not None
        insert = marker.end()
        text = text[:insert] + '\n  serverExternalPackages: ["better-sqlite3"],' + text[insert:]
        changed.append("nextConfig.serverExternalPackages")

    path.write_text(text, encoding="utf-8")
    return changed


def patch_drizzle_config(project: Path) -> list[str]:
    path = project / "drizzle.config.ts"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    if "RUNTIME_DB_PATH" in text or "dbCredentials" in text:
        return []
    marker = re.search(r"dialect\s*:\s*[\"']sqlite[\"']\s*,?", text)
    if not marker:
        return []
    insert = marker.end()
    text = text[:insert] + '\n  dbCredentials: {\n    url: process.env.RUNTIME_DB_PATH || "./.runtime/personal-workbench.sqlite3",\n  },' + text[insert:]
    path.write_text(text, encoding="utf-8")
    return ["drizzle.dbCredentials"]


def patch_source(project: Path) -> dict[str, object]:
    import_changes: list[str] = []
    runtime_changes: list[str] = []
    brand_changes: list[str] = []
    greeting_changes: list[str] = []

    source_roots = [project / "app", project / "server", project / "db"]
    suffixes = {".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs"}
    for root in source_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            original = path.read_text(encoding="utf-8", errors="strict")
            text = original
            text = re.sub(
                r'import\s*\{\s*env\s*\}\s*from\s*[\"\']cloudflare:workers[\"\'];?',
                'import { env } from "@/server/runtime/vps3/env";',
                text,
            )
            if text != original:
                import_changes.append(str(path.relative_to(project)))

            if path.parts[-2:] == ("db", "index.ts"):
                text = text.replace(
                    "Cloudflare D1 binding `DB` is unavailable. Set the `d1` field in .openai/hosting.json to `DB`.",
                    "The Personal Workbench VPS3 database is unavailable. Check RUNTIME_DB_PATH and the persistent volume.",
                )

            if path.is_relative_to(project / "app"):
                updated = re.sub(
                    r'export\s+const\s+runtime\s*=\s*[\"\']edge[\"\'];',
                    'export const runtime = "nodejs";',
                    text,
                )
                if updated != text:
                    runtime_changes.append(str(path.relative_to(project)))
                    text = updated

            if "个人日程" in text:
                text = text.replace("个人日程", PRODUCT_NAME_ZH)
                brand_changes.append(str(path.relative_to(project)))

            if path == project / "app" / "page.tsx":
                old = "嗨，{fixture.name}"
                new = '嗨，{reference ? fixture.name : "欢迎回来"}'
                if old in text:
                    text = text.replace(old, new)
                    greeting_changes.append(str(path.relative_to(project)))

            if path == project / "server" / "auth" / "index.ts":
                old_header = 'ipAddressHeaders: ["cf-connecting-ip"],'
                new_header = 'ipAddressHeaders: ["cf-connecting-ip", "x-forwarded-for", "x-real-ip"],'
                text = text.replace(old_header, new_header)

            if text != original:
                path.write_text(text, encoding="utf-8")

    privacy = project / "server" / "security" / "privacy-consent.ts"
    privacy_changed = False
    if privacy.is_file():
        text = privacy.read_text(encoding="utf-8")
        if "WORKBENCH_REQUIRE_SENSITIVE_CONSENT" not in text:
            target = "export async function requireSensitiveCloudConsent(\n  db: PrivacyDb,\n  userId: string,\n  target: string,\n): Promise<void> {\n  if (!requiresSensitiveCloudConsent(target)) return;"
            replacement = "export async function requireSensitiveCloudConsent(\n  db: PrivacyDb,\n  userId: string,\n  target: string,\n): Promise<void> {\n  const runtimeRequiresConsent = typeof process !== \"undefined\"\n    && process.env.WORKBENCH_REQUIRE_SENSITIVE_CONSENT === \"1\";\n  if (!runtimeRequiresConsent || !requiresSensitiveCloudConsent(target)) return;"
            if target not in text:
                raise SystemExit("ADAPT_REQUIRED: 隐私同步函数已发生上游结构变化；开发 Agent 需保留其余逻辑，仅让 VPS3 默认不阻断保存。")
            privacy.write_text(text.replace(target, replacement), encoding="utf-8")
            privacy_changed = True

    return {
        "cloudflare_imports_retargeted": sorted(set(import_changes)),
        "edge_routes_retargeted": sorted(set(runtime_changes)),
        "brand_files_updated": sorted(set(brand_changes)),
        "public_greeting_updated": greeting_changes,
        "sensitive_consent_default_disabled": privacy_changed,
    }


def copy_overlay(repo: Path, project: Path, taskpack_root: Path) -> list[str]:
    copied: list[str] = []
    project_overlay = taskpack_root / "overlay" / PRODUCT_DIR
    for source in project_overlay.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(project_overlay)
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(str(Path(PRODUCT_DIR) / relative))

    repository_overlay = taskpack_root / "overlay" / "repository"
    for source in repository_overlay.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(repository_overlay)
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(str(relative))
    return sorted(copied)


def append_gitignore(project: Path) -> list[str]:
    path = project / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    additions = [
        ".runtime/",
        ".env.vps3",
        "playwright-report/",
        "test-results/",
        "vps3-acceptance-output/",
    ]
    added: list[str] = []
    for item in additions:
        if item not in lines:
            lines.append(item)
            added.append(item)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return added


def assert_result(project: Path) -> dict[str, object]:
    missing: list[str] = []
    required = [
        "server/runtime/vps3/env.ts",
        "server/runtime/vps3/sqlite-d1.ts",
        "server/runtime/vps3/r2-s3.ts",
        "scripts/vps3/migrate-runtime.mjs",
        "scripts/vps3/entrypoint.mjs",
        "Dockerfile.vps3",
        "compose.vps3.yml",
        "app/api/health/route.ts",
        "playwright.vps3.config.ts",
    ]
    for item in required:
        if not (project / item).is_file():
            missing.append(item)

    remaining_imports: list[str] = []
    remaining_edge: list[str] = []
    for root_name in ("app", "db"):
        root = project / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs"}:
                continue
            text = path.read_text(encoding="utf-8")
            if "cloudflare:workers" in text:
                remaining_imports.append(str(path.relative_to(project)))
            if path.is_relative_to(project / "app") and re.search(r'runtime\s*=\s*[\"\']edge[\"\']', text):
                remaining_edge.append(str(path.relative_to(project)))

    package = json.loads((project / "package.json").read_text(encoding="utf-8"))
    result = {
        "required_files_missing": missing,
        "application_cloudflare_imports_remaining": remaining_imports,
        "application_edge_routes_remaining": remaining_edge,
        "package_name": package.get("name"),
        "has_vps3_build": package.get("scripts", {}).get("build:vps3") == "next build",
        "has_runtime_database_dependency": "better-sqlite3" in package.get("dependencies", {}),
        "has_runtime_object_dependency": "@aws-sdk/client-s3" in package.get("dependencies", {}),
    }
    if missing or remaining_imports or remaining_edge or package.get("name") != "personal-workbench":
        raise SystemExit("ADAPT_REQUIRED: 动态应用后仍有未闭合项目：\n" + json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="将 Personal Workbench 的最新仓库状态语义对齐到 VPS3 SaaS 运行层。")
    parser.add_argument("target", help="MetaDatabase worktree 根目录，或 Personal-WorkBench 项目目录")
    parser.add_argument("--report", help="输出不含凭据的应用报告")
    args = parser.parse_args()

    taskpack_root = Path(__file__).resolve().parent
    ensure_embedded_overlay(taskpack_root)
    repo, project = locate_project(Path(args.target))

    report = {
        "mode": "DYNAMIC_SEMANTIC_RECONCILE",
        "commit_pin_required": False,
        "project": str(project),
        "north_star": "普通用户打开网站、注册或登录后，即可直接使用个人工作台；数据保存到云端，并可在其他设备继续使用。",
        "invariants": {
            "display_brand": f"{PRODUCT_NAME_ZH} / {PRODUCT_NAME_EN}",
            "technical_namespace_preserved": TECHNICAL_NAMESPACE,
            "hello_kitty_ui_preserved": True,
            "existing_product_modules_preserved": True,
            "tenant_boundary_preserved": True,
        },
        "package_changes": merge_package(project),
        "next_config_changes": patch_next_config(project),
        "drizzle_config_changes": patch_drizzle_config(project),
        "source_changes": patch_source(project),
        "copied_files": copy_overlay(repo, project, taskpack_root),
        "gitignore_added": append_gitignore(project),
    }
    report["result"] = assert_result(project)
    report["status"] = "APPLIED_TO_CURRENT_TREE"

    output = Path(args.report).resolve() if args.report else project / "vps3-apply-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, report)
    print(f"APPLIED_TO_CURRENT_TREE project={project}")
    print(f"report={output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

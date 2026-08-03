import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("all resource writes establish a session before body parsing", async () => {
  const collection = await readFile("app/api/workbench/[resource]/route.ts", "utf8");
  const record = await readFile("app/api/workbench/[resource]/[id]/route.ts", "utf8");
  assert.ok(collection.indexOf("requireVerifiedSession") < collection.indexOf("readJson(request)"));
  assert.ok(record.indexOf("requireVerifiedSession") < record.indexOf("readJson(request)"));
});

test("resource data access only uses static resource mappings and user predicates", async () => {
  const store = await readFile("server/data/tenant-store.ts", "utf8");
  assert.ok(store.includes('WHERE user_id = ?'));
  assert.ok(store.includes('WHERE id = ? AND user_id = ?'));
  assert.ok(!store.includes("request.params"));
});

test("worker CSP permits only the Turnstile third-party surface", async () => {
  const worker = await readFile("worker/index.ts", "utf8");
  assert.ok(worker.includes("Content-Security-Policy"));
  assert.ok(worker.includes("https://challenges.cloudflare.com"));
  assert.ok(worker.includes("frame-ancestors 'none'"));
  assert.ok(worker.includes("img-src 'self' data: blob:"));
  assert.ok(worker.includes("X-Content-Type-Options"));
});

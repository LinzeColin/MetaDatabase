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

test("sensitive cloud paths gate storage before normal API persistence", async () => {
  const [collection, record, files, fileRecord, privateFiles, legacyPreview, legacyApply] = await Promise.all([
    readFile("app/api/workbench/[resource]/route.ts", "utf8"),
    readFile("app/api/workbench/[resource]/[id]/route.ts", "utf8"),
    readFile("app/api/workbench/files/route.ts", "utf8"),
    readFile("app/api/workbench/files/[id]/route.ts", "utf8"),
    readFile("server/files/private-files.ts", "utf8"),
    readFile("app/api/workbench/legacy-import/preview/route.ts", "utf8"),
    readFile("app/api/workbench/legacy-import/apply/route.ts", "utf8"),
  ]);

  const collectionGate = "await requireSensitiveCloudConsent(env.DB, userId, resourceName);";
  const collectionGet = collection.indexOf("export async function GET");
  const collectionPost = collection.indexOf("export async function POST");
  assert.ok(collection.indexOf(collectionGate, collectionGet) < collection.indexOf("await listTenantRecords", collectionGet));
  assert.ok(collection.indexOf(collectionGate, collectionPost) < collection.indexOf("readJson(request)", collectionPost));

  const recordGet = record.indexOf("export async function GET");
  const recordPatch = record.indexOf("export async function PATCH");
  assert.ok(
    record.indexOf("await requireSensitiveCloudConsent(env.DB, current.identity.userId, current.resourceName);", recordGet)
      < record.indexOf("await getTenantRecord", recordGet),
  );
  assert.ok(
    record.indexOf("await requireSensitiveCloudConsent(env.DB, userId, current.resourceName);", recordPatch)
      < record.indexOf("readJson(request)", recordPatch),
  );

  assert.ok(
    files.indexOf("await requireSensitiveCloudConsent(env.DB, userId, upload.module);")
      < files.lastIndexOf("beginIdempotentWrite"),
  );
  assert.ok(
    fileRecord.indexOf("await requirePrivateFileCloudConsent(env, userId, id);")
      < fileRecord.indexOf("readPrivateFileForm(request)"),
  );
  assert.ok(privateFiles.includes("await requireSensitiveCloudConsent(env.DB, input.userId, input.module);"));
  assert.ok(privateFiles.includes("await requireSensitiveCloudConsent(env.DB, userId, row.module);"));

  assert.ok(
    legacyPreview.lastIndexOf("await requireLegacyImportConsent(env.DB, identity.userId, envelope);")
      < legacyPreview.lastIndexOf("previewLegacyImport"),
  );
  assert.ok(
    legacyApply.lastIndexOf("await requireLegacyImportConsent(env.DB, userId, envelope);")
      < legacyApply.lastIndexOf("beginIdempotentWrite"),
  );
});

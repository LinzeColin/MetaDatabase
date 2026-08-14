import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("all resource writes establish a session before body parsing", async () => {
  const collection = await readFile("app/api/mydairy/[resource]/route.ts", "utf8");
  const record = await readFile("app/api/mydairy/[resource]/[id]/route.ts", "utf8");
  assert.ok(collection.indexOf("requireVerifiedSession") < collection.indexOf("readJson(request)"));
  assert.ok(record.indexOf("requireVerifiedSession") < record.indexOf("readJson(request)"));
});

test("all custom mutation routes use the shared same-origin session boundary", async () => {
  const mutationRoutes = [
    "app/api/account/privacy/route.ts",
    "app/api/mydairy/[resource]/route.ts",
    "app/api/mydairy/[resource]/[id]/route.ts",
    "app/api/mydairy/files/route.ts",
    "app/api/mydairy/files/[id]/route.ts",
    "app/api/mydairy/legacy-import/apply/route.ts",
    "app/api/mydairy/legacy-import/preview/route.ts",
    "app/api/mydairy/profile/route.ts",
  ];
  const sources = await Promise.all(mutationRoutes.map((path) => readFile(path, "utf8")));
  for (const source of sources) {
    assert.ok(source.includes("requireVerifiedMutationSession"));
  }

  const idempotencyRoutes = [
    "app/api/mydairy/[resource]/route.ts",
    "app/api/mydairy/[resource]/[id]/route.ts",
    "app/api/mydairy/files/route.ts",
    "app/api/mydairy/files/[id]/route.ts",
    "app/api/mydairy/legacy-import/apply/route.ts",
    "app/api/mydairy/profile/route.ts",
  ];
  const idempotencySources = await Promise.all(idempotencyRoutes.map((path) => readFile(path, "utf8")));
  for (const source of idempotencySources) {
    assert.ok(source.includes("readIdempotencyKey(request)"));
  }

  const deletion = await readFile("app/api/account/delete/route.ts", "utf8");
  assert.ok(deletion.includes("requireFreshVerifiedSession"));
  assert.ok(deletion.includes("assertConfiguredSameOriginMutation(request, env)"));
});

test("legacy-domain session handoff is a narrowly scoped, server-validated exception", async () => {
  const [issue, complete, helper] = await Promise.all([
    readFile("app/api/auth/legacy-domain-handoff/route.ts", "utf8"),
    readFile("app/api/auth/legacy-domain-handoff/complete/route.ts", "utf8"),
    readFile("server/auth/legacy-domain-handoff.ts", "utf8"),
  ]);

  assert.ok(issue.includes("isRetiredHandoffIssuanceRequest(request)"));
  assert.ok(issue.indexOf("createAuth(env).api.getSession") < issue.indexOf("await readJson(request)"));
  assert.ok(issue.includes("legacySignedSessionCookie(request.headers)"));
  assert.ok(issue.includes("issueLegacyDomainHandoff"));
  assert.equal(issue.includes("sessionCookie },"), false);

  assert.ok(complete.includes("isCanonicalHandoffCompletionRequest(request)"));
  assert.ok(complete.indexOf("consumeLegacyDomainHandoff") < complete.indexOf("createAuth(env).api.getSession"));
  assert.ok(complete.includes("legacyHandoffSessionCookieHeader"));
  assert.ok(helper.includes('DELETE FROM "verification" WHERE "identifier" = ? AND "expiresAt" > ? RETURNING "value"'));
  assert.ok(issue.includes("Referrer-Policy"), "handoff issuance must suppress referrer forwarding");
  assert.ok(complete.includes("Referrer-Policy"), "handoff completion must suppress referrer forwarding");
});

test("account UI presents the full sensitive cross-device privacy disclosure before enable", async () => {
  const [page, route] = await Promise.all([
    readFile("app/account/page.tsx", "utf8"),
    readFile("app/api/account/privacy/route.ts", "utf8"),
  ]);
  for (const requiredText of [
    "敏感跨设备保存隐私说明",
    "权威云端数据",
    "无数据驻留保证",
    "导出全部账户数据",
    "关闭并撤回",
    "不是医疗、诊断、治疗或 PHI 服务",
  ]) {
    assert.ok(page.includes(requiredText), `missing disclosure text: ${requiredText}`);
  }
  assert.ok(page.includes("privacyDisclosureReady"));
  assert.ok(route.includes("legalOperatorName"));
  assert.ok(route.includes("privacyContactEmail"));
  assert.ok(route.includes("隐私联系信息尚未配置"));
});

test("resource data access only uses static resource mappings and user predicates", async () => {
  const store = await readFile("server/data/tenant-store.ts", "utf8");
  assert.ok(store.includes('WHERE user_id = ?'));
  assert.ok(store.includes('WHERE id = ? AND user_id = ?'));
  assert.ok(!store.includes("request.params"));
});

test("worker CSP permits Turnstile, Google Identity and the one retired-host canonical handoff target", async () => {
  const worker = await readFile("worker/index.ts", "utf8");
  assert.ok(worker.includes("Content-Security-Policy"));
  assert.ok(worker.includes("https://challenges.cloudflare.com"));
  assert.ok(worker.includes("https://accounts.google.com"));
  assert.ok(worker.includes("frame-ancestors 'none'"));
  assert.ok(worker.includes("img-src 'self' data: blob:"));
  assert.ok(worker.includes("X-Content-Type-Options"));
  assert.ok(worker.includes("isRetiredCompatibilityHost"));
  assert.ok(worker.includes("form-action 'self' ${CANONICAL_MYDAIRY_ORIGIN}"));
  assert.ok(worker.includes('"form-action \'self\'"'));
});

test("sensitive cloud paths gate storage before normal API persistence", async () => {
  const [collection, record, files, fileRecord, privateFiles, legacyPreview, legacyApply] = await Promise.all([
    readFile("app/api/mydairy/[resource]/route.ts", "utf8"),
    readFile("app/api/mydairy/[resource]/[id]/route.ts", "utf8"),
    readFile("app/api/mydairy/files/route.ts", "utf8"),
    readFile("app/api/mydairy/files/[id]/route.ts", "utf8"),
    readFile("server/files/private-files.ts", "utf8"),
    readFile("app/api/mydairy/legacy-import/preview/route.ts", "utf8"),
    readFile("app/api/mydairy/legacy-import/apply/route.ts", "utf8"),
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

test("storage check is verified-session-only and data-free", async () => {
  const [route, helper] = await Promise.all([
    readFile("app/storage-check/route.ts", "utf8"),
    readFile("server/storage/binding-health.ts", "utf8"),
  ]);
  const handler = route.slice(route.indexOf("export async function GET"));

  assert.ok(handler.indexOf("requireVerifiedSession") < handler.indexOf("probeStorageBindings"));
  assert.ok(route.includes('"Cache-Control": "no-store"'));
  assert.ok(route.includes('"Content-Type": "text/html; charset=utf-8"'));
  assert.ok(route.includes('"X-Robots-Tag": "noindex, nofollow"'));
  assert.equal(route.includes("Response.json"), false);
  assert.ok(helper.includes('env.DB.prepare("SELECT 1 AS storage_binding_probe").first()'));
  assert.ok(helper.includes("env.FILES.head"));
  for (const forbiddenOperation of ["env.FILES.get", "env.FILES.list", "env.FILES.put", "env.FILES.delete"]) {
    assert.equal(helper.includes(forbiddenOperation), false, `forbidden probe operation: ${forbiddenOperation}`);
  }
});

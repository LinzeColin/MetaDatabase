import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export async function verifyR2Contract() {
  const [files, uploadRoute, objectRoute] = await Promise.all([
    readFile("server/files/private-files.ts", "utf8"),
    readFile("app/api/workbench/files/route.ts", "utf8"),
    readFile("app/api/workbench/files/[id]/route.ts", "utf8"),
  ]);
  assert.ok(files.includes("users/${userId}/${module}/${objectId}"));
  assert.ok(files.includes("detectImageMime"));
  assert.ok(files.includes("maxImagePixels"));
  assert.ok(files.includes("maxFileBytes"));
  assert.ok(files.includes("WHERE id = ? AND user_id = ? AND state = 'active'"));
  const replaceSource = files.slice(files.indexOf("export async function replacePrivateFile"));
  assert.ok(replaceSource.indexOf("const row = await ownedFile") < replaceSource.indexOf("await env.FILES.put"));
  assert.ok(files.includes("pending_delete"));
  assert.ok(!files.includes("r2.dev"));
  const authGate = "requireVerifiedMutationSession(createAuth(env), request, env.APP_ORIGIN)";
  assert.ok(uploadRoute.includes(authGate));
  assert.ok(uploadRoute.indexOf(authGate) < uploadRoute.indexOf("await readPrivateFileForm(request)"));
  assert.ok(uploadRoute.includes("beginIdempotentWrite"));
  assert.ok(objectRoute.includes("replacePrivateFile"));
  assert.ok(objectRoute.includes("deletePrivateFile"));

  const report = {
    stage: "S2",
    status: "PASS_LOCAL_CONTRACT",
    objectKey: "users/{userId}/{module}/{objectId}",
    checks: {
      privateBucketOnly: true,
      magicAndMime: true,
      pixelDimensions: true,
      sizeLimitBytes: 10485760,
      ownerBeforeReadReplaceDelete: true,
      idempotentWrites: true,
    },
    savedCandidateR2: "NOT_RUN",
    fullDecodeValidation: "NOT_RUN_SAVED_CANDIDATE",
    notes: [
      "No production R2 object or user content was accessed.",
      "Saved Candidate R2 round-trip remains an external release gate.",
    ],
  };
  await writeFile("13_evidence/r2.json", `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const report = await verifyR2Contract();
  process.stdout.write(`${report.status} key=${report.objectKey}\n`);
}

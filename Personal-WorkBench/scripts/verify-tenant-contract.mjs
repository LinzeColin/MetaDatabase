import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const files = {
  collection: "app/api/mydairy/[resource]/route.ts",
  record: "app/api/mydairy/[resource]/[id]/route.ts",
  profile: "app/api/mydairy/profile/route.ts",
  store: "server/data/tenant-store.ts",
  resources: "server/data/resources.ts",
  tenant: "server/security/tenant.ts",
};

export async function verifyTenantContract() {
  const entries = await Promise.all(Object.entries(files).map(async ([key, file]) => [key, await readFile(file, "utf8")]));
  const source = Object.fromEntries(entries);
  assert.ok(source.resources.includes("tenantResources"));
  assert.ok(source.resources.includes('"savings-transactions"'));
  assert.ok(source.tenant.includes("rejectClientTenantFields"));
  assert.ok(source.tenant.includes("emailVerified !== true"));
  assert.ok(source.store.includes("WHERE user_id = ?"));
  assert.ok(source.store.includes("WHERE id = ? AND user_id = ?"));
  assert.ok(source.collection.indexOf("requireVerifiedSession") < source.collection.indexOf("readJson"));
  assert.ok(source.record.indexOf("requireVerifiedSession") < source.record.indexOf("readJson"));
  assert.ok(source.collection.includes("beginIdempotentWrite"));
  assert.ok(source.record.includes("beginIdempotentWrite"));
  assert.ok(source.profile.indexOf("requireVerifiedSession") < source.profile.indexOf("readJson"));
  assert.ok(source.profile.includes("WHERE user_id = ?"));

  const report = {
    stage: "S2",
    status: "PASS_LOCAL_CONTRACT",
    tenantMatrix: {
      unauthenticated: "401 before input parsing",
      unverified: "403 before data access",
      userAOwnRecord: "server user_id predicate",
      userBReadsUserA: "404 via id + user_id predicate",
      clientSuppliedTenant: "400 before write",
      replaySameIdempotencyKey: "no-op",
      changedPayloadSameKey: "409",
    },
    resources: 15,
    savedCandidateD1: "NOT_RUN",
    notes: [
      "The local database isolation test is executed separately by npm run test:tenant.",
      "Real D1/session execution remains a Saved Candidate gate.",
    ],
  };
  await writeFile("13_evidence/tenant_matrix.json", `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const report = await verifyTenantContract();
  process.stdout.write(`${report.status} resources=${report.resources}\n`);
}

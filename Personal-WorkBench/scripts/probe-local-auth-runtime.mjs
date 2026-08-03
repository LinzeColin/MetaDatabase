import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";

const origin = process.env.S2_LOCAL_AUTH_ORIGIN ?? "http://localhost:3000";
const authResponse = await fetch(`${origin}/api/auth/get-session`, { redirect: "manual" });
const publicConfigResponse = await fetch(`${origin}/api/auth/public-config`, { redirect: "manual" });
const publicConfig = await publicConfigResponse.json();

assert.equal(authResponse.status, 503);
assert.equal(publicConfigResponse.status, 200);
assert.ok(publicConfig && typeof publicConfig === "object");
assert.ok("turnstileSiteKey" in publicConfig);
assert.match(authResponse.headers.get("content-security-policy") ?? "", /challenges\.cloudflare\.com/);

const report = {
  stage: "S2",
  status: "PASS_LOCAL_WORKERS_RUNTIME",
  origin,
  authWithoutRuntimeMaterials: authResponse.status,
  publicConfig: {
    status: publicConfigResponse.status,
    hasSiteKey: typeof publicConfig.turnstileSiteKey === "string",
  },
  cspIncludesTurnstile: true,
  savedCandidate: "NOT_RUN",
};
await writeFile("13_evidence/auth-local-runtime.json", `${JSON.stringify(report, null, 2)}\n`);
process.stdout.write(`${report.status} auth=${report.authWithoutRuntimeMaterials} public-config=${report.publicConfig.status}\n`);

import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";

function explicitOriginFromEnv() {
  const raw = process.env.S2_LOCAL_AUTH_ORIGIN?.trim();
  if (!raw) return null;

  const origin = new URL(raw);
  assert.ok(["http:", "https:"].includes(origin.protocol));
  assert.equal(origin.username, "");
  assert.equal(origin.password, "");
  assert.equal(origin.pathname, "/");
  assert.equal(origin.search, "");
  assert.equal(origin.hash, "");
  return origin.origin;
}

const explicitOrigin = explicitOriginFromEnv();
let authResponse;
let publicConfigResponse;

if (explicitOrigin) {
  authResponse = await fetch(`${explicitOrigin}/api/auth/get-session`, { redirect: "manual" });
  publicConfigResponse = await fetch(`${explicitOrigin}/api/auth/public-config`, { redirect: "manual" });
} else {
  const [{ GET: authGet }, { GET: publicConfigGet }] = await Promise.all([
    import("../app/api/auth/[...all]/route.ts"),
    import("../app/api/auth/public-config/route.ts"),
  ]);
  authResponse = await authGet(new Request("http://local.test/api/auth/get-session"));
  publicConfigResponse = publicConfigGet();
}

const publicConfig = await publicConfigResponse.json();
const workerSource = await readFile(new URL("../worker/index.ts", import.meta.url), "utf8");

assert.equal(authResponse.status, 503);
assert.equal(publicConfigResponse.status, 200);
assert.ok(publicConfig && typeof publicConfig === "object");
assert.ok("turnstileSiteKey" in publicConfig);
assert.match(workerSource, /Content-Security-Policy/);
assert.match(workerSource, /https:\/\/challenges\.cloudflare\.com/);

const report = {
  stage: "S2",
  status: explicitOrigin ? "PASS_LOCAL_AUTH_RUNTIME" : "PASS_LOCAL_NO_SECRET_AUTH_BOUNDARY",
  probeMode: explicitOrigin ? "EXPLICIT_LOCAL_ORIGIN" : "IN_PROCESS_NO_SECRET_ROUTE_HARNESS",
  origin: explicitOrigin ? "EXPLICIT_REDACTED" : null,
  authWithoutRuntimeMaterials: authResponse.status,
  publicConfig: {
    status: publicConfigResponse.status,
    hasSiteKey: typeof publicConfig.turnstileSiteKey === "string",
  },
  cspContractIncludesTurnstile: true,
  savedCandidate: "NOT_RUN",
};
await writeFile("13_evidence/auth-local-runtime.json", `${JSON.stringify(report, null, 2)}\n`);
process.stdout.write(`${report.status} auth=${report.authWithoutRuntimeMaterials} public-config=${report.publicConfig.status}\n`);

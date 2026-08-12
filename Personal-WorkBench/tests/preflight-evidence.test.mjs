import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const forbiddenKeys = new Set(["stdout", "stderr", "raw", "cwd", "taskpack_root"]);

function assertSanitized(report, sentinels) {
  const serialized = JSON.stringify(report);
  for (const sentinel of sentinels) {
    assert.equal(serialized.includes(sentinel), false, `leaked ${sentinel}`);
  }

  const walk = (value) => {
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (value && typeof value === "object") {
      for (const [key, child] of Object.entries(value)) {
        assert.equal(forbiddenKeys.has(key), false, `forbidden key ${key}`);
        walk(child);
      }
      return;
    }
    if (typeof value === "string") {
      assert.equal(value.includes(ROOT), false, "report retained an absolute project path");
    }
  };

  walk(report);
}

async function startProductionSmokeFixture() {
  const server = createServer((request, response) => {
    const status = request.url === "/api/mydairy/profile" ? 401 : 200;
    response.writeHead(status, { "content-type": "application/json" });
    response.end("{}");
  });

  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", resolveListen);
  });

  const address = server.address();
  assert.ok(address && typeof address === "object");

  return {
    origin: `http://127.0.0.1:${address.port}`,
    async close() {
      await new Promise((resolveClose) => server.close(resolveClose));
    },
  };
}

function runProductionSmoke(env) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(process.execPath, ["scripts/verify-production-smoke.mjs"], {
      cwd: ROOT,
      env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.once("error", rejectRun);
    child.once("close", (status) => {
      resolveRun({ status, stdout, stderr });
    });
  });
}

test("production-smoke preflight evidence redacts configured secret-like inputs", async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "pwb-production-evidence-"));
  const evidenceRoot = join(temporaryRoot, "evidence");
  const sentinels = [
    "SENTINEL_PRODUCTION_ORIGIN",
    "sentinel-mail@example.test",
    "SENTINEL_SMOKE_PASSWORD",
    "sentinel-google@example.test",
  ];

  try {
    const run = spawnSync(process.execPath, ["scripts/verify-production-smoke.mjs"], {
      cwd: ROOT,
      encoding: "utf8",
      env: {
        PATH: process.env.PATH ?? "",
        HOME: temporaryRoot,
        PRODUCTION_SMOKE_EVIDENCE_DIR: evidenceRoot,
        PRODUCTION_SMOKE_ORIGIN: "SENTINEL_PRODUCTION_ORIGIN",
        SITES_SMOKE_EMAIL: "sentinel-mail@example.test",
        SITES_SMOKE_PASSWORD: "SENTINEL_SMOKE_PASSWORD",
        SITES_SMOKE_GOOGLE_EMAIL: "sentinel-google@example.test",
      },
    });
    assert.equal(run.status, 1, run.stderr);

    const [status, runReport] = await Promise.all([
      readFile(join(evidenceRoot, "production-smoke-status.json"), "utf8").then(JSON.parse),
      readFile(join(evidenceRoot, "production-smoke-run.json"), "utf8").then(JSON.parse),
    ]);
    assertSanitized(status, sentinels);
    assertSanitized(runReport, sentinels);
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("production-smoke distinguishes a ready precheck from the still-required real auth journey", async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "pwb-production-ready-"));
  const evidenceRoot = join(temporaryRoot, "evidence");
  const fixture = await startProductionSmokeFixture();
  const sentinels = [
    "controlled-mail@example.test",
    "CONTROLLED_SMOKE_PASSWORD",
    "controlled-google@example.test",
  ];

  try {
    const run = await runProductionSmoke({
      PATH: process.env.PATH ?? "",
      HOME: temporaryRoot,
      ALLOW_HTTP_SMOKE_ORIGIN: "1",
      PRODUCTION_SMOKE_EVIDENCE_DIR: evidenceRoot,
      SITES_PRODUCTION_ORIGIN: fixture.origin,
      SITES_SMOKE_EMAIL: "controlled-mail@example.test",
      SITES_SMOKE_PASSWORD: "CONTROLLED_SMOKE_PASSWORD",
      SITES_SMOKE_GOOGLE_EMAIL: "controlled-google@example.test",
    });
    assert.equal(run.status, 0, run.stderr);

    const [status, runReport] = await Promise.all([
      readFile(join(evidenceRoot, "production-smoke-status.json"), "utf8").then(JSON.parse),
      readFile(join(evidenceRoot, "production-smoke-run.json"), "utf8").then(JSON.parse),
    ]);
    assert.equal(status.status, "PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK");
    assert.equal(runReport.status, "PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK");
    assert.equal(runReport.checks.real_auth_flow.status, "NOT_EXECUTED");
    assert.equal(runReport.checks.real_auth_flow.precheck_only, true);
    assertSanitized(status, sentinels);
    assertSanitized(runReport, sentinels);
  } finally {
    await fixture.close();
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("ops-projection preflight evidence redacts adapter configuration", async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "pwb-ops-evidence-"));
  const evidenceRoot = join(temporaryRoot, "evidence");
  const sentinels = [
    "SENTINEL_OPS_ORIGIN",
    "SENTINEL_OPS_TOKEN",
    "SENTINEL_STATUS_ENDPOINT",
    "SENTINEL_OVH_ENDPOINT",
    "SENTINEL_PDB_ENDPOINT",
  ];

  try {
    const run = spawnSync(process.execPath, ["scripts/verify-ops-projection.mjs"], {
      cwd: ROOT,
      encoding: "utf8",
      env: {
        PATH: process.env.PATH ?? "",
        HOME: temporaryRoot,
        OPS_PROJECTION_EVIDENCE_DIR: evidenceRoot,
        PRODUCTION_ORIGIN: "SENTINEL_OPS_ORIGIN",
        OPS_ADAPTER_TOKEN: "SENTINEL_OPS_TOKEN",
        STATUS_ADAPTER_BASE: "SENTINEL_STATUS_ENDPOINT",
        OVH_ADAPTER_BASE: "SENTINEL_OVH_ENDPOINT",
        PRIVATE_DATABASE_ADAPTER_BASE: "SENTINEL_PDB_ENDPOINT",
      },
    });
    assert.equal(run.status, 0, run.stderr);

    const [status, runReport] = await Promise.all([
      readFile(join(evidenceRoot, "ops_projection.json"), "utf8").then(JSON.parse),
      readFile(join(evidenceRoot, "ops_projection-run.json"), "utf8").then(JSON.parse),
    ]);
    assertSanitized(status, sentinels);
    assertSanitized(runReport, sentinels);
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

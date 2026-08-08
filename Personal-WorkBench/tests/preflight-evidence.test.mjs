import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
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
      readFile(join(evidenceRoot, "production.json"), "utf8").then(JSON.parse),
      readFile(join(evidenceRoot, "production-smoke-run.json"), "utf8").then(JSON.parse),
    ]);
    assertSanitized(status, sentinels);
    assertSanitized(runReport, sentinels);
  } finally {
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

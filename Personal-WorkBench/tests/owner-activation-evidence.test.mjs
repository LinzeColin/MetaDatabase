import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  presenceOnly,
  redactCommandCheck,
  redactCommandResult,
} from "../scripts/verify-owner-activation.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("owner activation command evidence never retains raw output", () => {
  const raw = {
    name: "wrangler whoami",
    command: "npx wrangler whoami --json",
    cwd: ROOT,
    status: 0,
    signal: null,
    ok: true,
    stdout: "SENTINEL_CLI_OUTPUT",
    stderr: "SENTINEL_CLI_ERROR",
  };

  const commandEvidence = redactCommandResult(raw);
  const checkEvidence = redactCommandCheck(raw);
  assert.equal(JSON.stringify(commandEvidence).includes("SENTINEL_"), false);
  assert.equal(JSON.stringify(checkEvidence).includes("SENTINEL_"), false);
  assert.deepEqual(presenceOnly("configured"), { present: true });
  assert.deepEqual(presenceOnly(""), { present: false });
});

test("owner activation report records presence only for supplied configuration", async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "pwb-owner-activation-"));
  const evidenceFile = join(temporaryRoot, "owner-activation.json");
  const sentinels = [
    "SENTINEL_AUTH_SECRET",
    "SENTINEL_GOOGLE_CLIENT_ID",
    "SENTINEL_GOOGLE_SECRET",
    "SENTINEL_RESEND_KEY",
    "SENTINEL_TURNSTILE_SITE_KEY",
    "SENTINEL_TURNSTILE_SECRET",
    "SENTINEL_OPERATOR_NAME",
    "sentinel-privacy@example.test",
    "sentinel-mail@example.test",
    "sentinel-auth@example.test",
    "SENTINEL_PRIVACY_VERSION",
    "SENTINEL_PRIVACY_HASH",
  ];

  try {
    const run = spawnSync(process.execPath, ["scripts/verify-owner-activation.mjs"], {
      cwd: ROOT,
      encoding: "utf8",
      env: {
        PATH: process.env.PATH ?? "",
        HOME: temporaryRoot,
        NODE_ENV: "test",
        TASKPACK_ROOT: join(temporaryRoot, "missing-taskpack"),
        OWNER_ACTIVATION_EVIDENCE_FILE: evidenceFile,
        BETTER_AUTH_SECRET: "SENTINEL_AUTH_SECRET",
        APP_ORIGIN: "https://owner-activation.example.test",
        GOOGLE_CLIENT_ID: "SENTINEL_GOOGLE_CLIENT_ID",
        GOOGLE_CLIENT_SECRET: "SENTINEL_GOOGLE_SECRET",
        RESEND_API_KEY: "SENTINEL_RESEND_KEY",
        TURNSTILE_SITE_KEY: "SENTINEL_TURNSTILE_SITE_KEY",
        TURNSTILE_SECRET_KEY: "SENTINEL_TURNSTILE_SECRET",
        LEGAL_OPERATOR_NAME: "SENTINEL_OPERATOR_NAME",
        PRIVACY_CONTACT_EMAIL: "sentinel-privacy@example.test",
        MAIL_FROM: "sentinel-mail@example.test",
        AUTH_FROM_EMAIL: "sentinel-auth@example.test",
        PRIVACY_POLICY_VERSION: "SENTINEL_PRIVACY_VERSION",
        PRIVACY_NOTICE_SHA256: "SENTINEL_PRIVACY_HASH",
      },
    });
    assert.equal(run.status, 1, run.stderr);

    const report = JSON.parse(await readFile(evidenceFile, "utf8"));
    const serialized = JSON.stringify(report);
    for (const sentinel of sentinels) {
      assert.equal(serialized.includes(sentinel), false, `leaked ${sentinel}`);
    }
    assert.deepEqual(report.checks.required_secrets.BETTER_AUTH_SECRET, { present: true });
    assert.deepEqual(report.checks.required_secrets.MAIL_FROM_FROM_RUNTIME, {
      source: "AUTH_FROM_EMAIL",
      present: { MAIL_FROM: true, AUTH_FROM_EMAIL: true },
    });
    assert.equal("raw" in report.evidence.owner_approval, false);
    assert.equal("values" in report.checks.required_secrets.MAIL_FROM_FROM_RUNTIME, false);
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

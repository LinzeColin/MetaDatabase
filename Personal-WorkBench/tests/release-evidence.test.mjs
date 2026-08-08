import assert from "node:assert/strict";
import test from "node:test";
import { evidenceReference, redactCommandResult } from "../scripts/verify-release.mjs";

test("release evidence stores command status without raw command output", () => {
  const result = redactCommandResult({
    name: "quality",
    command: "npm run test:quality",
    status: 0,
    signal: null,
    ok: true,
    stdout: "SENTINEL_RELEASE_OUTPUT",
    stderr: "SENTINEL_RELEASE_ERROR",
  });

  const serialized = JSON.stringify(result);
  assert.equal(serialized.includes("SENTINEL_RELEASE"), false);
  assert.equal("stdout" in result, false);
  assert.equal("stderr" in result, false);
  assert.equal(result.output_redacted, true);
});

test("release evidence references do not retain nested raw evidence", () => {
  const reference = evidenceReference(
    {
      exists: true,
      status: "PASS_LOCAL_QUALITY",
      phase: "S4-T1",
      runAt: "2026-08-09T00:00:00.000Z",
      raw: { secret: "SENTINEL_EVIDENCE_SECRET" },
    },
    "13_evidence/quality.json",
  );

  const serialized = JSON.stringify(reference);
  assert.equal(serialized.includes("SENTINEL_"), false);
  assert.equal("raw" in reference, false);
  assert.equal(reference.source, "13_evidence/quality.json");
});

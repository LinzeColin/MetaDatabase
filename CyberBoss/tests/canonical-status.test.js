const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const test = require("node:test");

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-status-cli-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

test("canonical status CLI writes an atomic redacted snapshot and existing global-status row", (t) => {
  const root = temporaryRoot(t);
  const input = path.join(root, "facts.json");
  const snapshot = path.join(root, "snapshot.json");
  const row = path.join(root, "row.json");
  const components = Object.fromEntries([
    "process", "wechat_poll", "wechat_send", "runtime", "e2e", "queue",
    "canonical", "timeline", "r2", "oci", "resources", "self_heal",
  ].map((id) => [id, { state: "activation_pending", reason_code: `${id}_activation_pending`, age_seconds: null }]));
  components.process = { state: "healthy", reason_code: "process_verified", age_seconds: 0 };
  components.self_heal = { state: "disabled", reason_code: "self_heal_not_enabled", age_seconds: null };
  fs.writeFileSync(input, `${JSON.stringify({
    source_commit: "b".repeat(40),
    components,
    metrics: {
      queue_depth: 0,
      oldest_job_age_seconds: null,
      outbox_pending: 0,
      canonical_pending: 0,
      control_plane_llm_calls_total: 0,
      business_runtime_model_calls_total: 0,
      self_heal_agent_invocations_total: 0,
      memory_available_bytes: null,
      disk_available_bytes: null,
    },
    adapters: {
      private_database: "activation_pending",
      r2: "hazard_blocked",
      cloudflare_access: "activation_pending",
      oci: "activation_pending",
      timeline: "activation_pending",
      global_status: "activation_pending",
    },
    release: { version: "v0.0.0.5", commit: "b".repeat(40), slot: "none", rollback_ready: false },
  })}\n`, "utf8");
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-status-export.js", "export",
    "--input", input,
    "--snapshot", snapshot,
    "--row", row,
    "--generated-at", "2026-07-27T00:00:00.000Z",
    "--observed-at", "2026-07-27T00:00:01.000Z",
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const receipt = JSON.parse(result.stdout);
  const snapshotValue = JSON.parse(fs.readFileSync(snapshot, "utf8"));
  const rowValue = JSON.parse(fs.readFileSync(row, "utf8"));
  assert.equal(receipt.status, "passed");
  assert.equal(receipt.control_plane_llm_calls_total, 0);
  assert.equal(receipt.self_heal_agent_invocations_total, 0);
  assert.equal(snapshotValue.overall, "activation_pending");
  assert.equal(rowValue.status, "down");
  assert.equal(rowValue.generation_id, snapshotValue.generation_id);
  assert.equal(rowValue.agent, "无");
  assert.doesNotMatch(`${result.stdout}\n${JSON.stringify(snapshotValue)}\n${JSON.stringify(rowValue)}`, /prompt|thread|token|private-job|\/var\//i);
});

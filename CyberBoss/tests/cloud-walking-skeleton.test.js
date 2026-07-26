const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const project = path.resolve(__dirname, "..");
const kit = path.join(
  project,
  "docs/product_design/v0.0.0.4/implementation-kit",
);
const releaseId = "0123456789abcdef0123456789abcdef01234567";

function read(relative) {
  return fs.readFileSync(path.join(project, relative), "utf8");
}

test("CB-140 input policy is Runtime-preceding and byte exact", () => {
  const policy = read("app/src/adapters/channel/weixin/message-utils.js");
  const app = read("app/src/core/app.js");
  assert.match(policy, /const DEFAULT_MAX_INPUT_BYTES = 32 \* 1024/);
  assert.match(policy, /Buffer\.byteLength\(String\(text \|\| ""\), "utf8"\)/);
  assert.match(policy, /code: "sender_not_allowed"/);
  assert.match(policy, /code: "input_too_large"/);
  assert.match(app, /normalized\.policyDecision\?\.accepted === false/);
  assert.match(app, /return;\n\s*}\n\n\s*this\.primeDeferredRepliesForSender/);
});

test("trace contract is opt-in, path-bounded and raw-content free", () => {
  const source = read("app/src/core/walking-skeleton-trace.js");
  assert.match(source, /TRACE_STAGE_ORDER = \[/);
  for (const stage of [
    "inbound_received",
    "runtime_dispatched",
    "runtime_completed",
    "outbox_staged",
    "delivery_confirmed",
    "canonical_event",
  ]) {
    assert.match(source, new RegExp(`"${stage}"`));
  }
  assert.match(source, /trace path must stay inside the state directory/);
  assert.match(source, /input_sha256/);
  assert.match(source, /output_sha256/);
  assert.doesNotMatch(source, /input_text|output_text|sender_id|account_id/);
});

test("CB-140 check modes are write-free and do not execute PG-1", () => {
  for (const script of [
    "scripts/install-cloud-walking-skeleton.sh",
    "scripts/accept-cloud-walking-skeleton.sh",
  ]) {
    const file = path.join(kit, script);
    const flag = script.includes("install") ? "--check" : "--check";
    const result = spawnSync(
      "bash",
      [file, flag, "--release-id", releaseId],
      { encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /persistent_writes=false/);
    assert.match(result.stdout, /live_commands=false/);
  }
  const acceptance = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-cloud-walking-skeleton.sh",
  );
  assert.match(acceptance, /pg_1_executed=false/);
  assert.doesNotMatch(acceptance, /^\s*sleep(?:\s|$)/m);
});

test("live acceptance requires ten E2E, policy boundaries, latency and Mac-offline proof", () => {
  const runner = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/run-walking-skeleton-acceptance.mjs",
  );
  const acceptance = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-cloud-walking-skeleton.sh",
  );
  assert.match(runner, /index <= 10/);
  assert.match(runner, /32 \* 1024/);
  assert.match(runner, /\(32 \* 1024\) \+ 1/);
  assert.match(runner, /index <= 20/);
  assert.match(runner, /latencyP50 < 5_000/);
  assert.match(runner, /latencyP95 < 10_000/);
  assert.match(acceptance, /MAC_SOURCE_HITS/);
  assert.match(acceptance, /MAC_PROCESS_HITS/);
  assert.match(acceptance, /NON_LOOPBACK_CONNECTIONS/);
  assert.match(acceptance, /LOOPBACK_LISTENER_COUNT/);
  assert.match(acceptance, /\$4 ~ \/\^127\\\.0\\\.0\\\.1:/);
  assert.doesNotMatch(acceptance, /19080\)\$'/);
  assert.match(acceptance, /real_adapters=activation_pending/);
});

test("CB-140 artifacts retain strict dual-license conflict posture and no publication", () => {
  const builder = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
  );
  const installer = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
  );
  const contract = read("docs/governance/RUN_CONTRACT_P1_5_CB_140.md");
  for (const source of [builder, installer, contract]) {
    assert.match(source, /AGPL-3\.0-only AND GPL-3\.0-only/);
    assert.match(source, /upstream_clarification_received/);
  }
  assert.match(builder, /"remote_publication": "none"/);
  assert.match(contract, /不创建新 repo/);
  assert.match(contract, /不 push，不创建\s*PR\/tag\/release/);
});

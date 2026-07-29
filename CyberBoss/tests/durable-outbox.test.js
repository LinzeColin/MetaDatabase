"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const PROJECT_ROOT = path.resolve(__dirname, "..");

function source(relative) {
  return fs.readFileSync(path.join(PROJECT_ROOT, relative), "utf8");
}

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb230-contract-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test("CB-230 contract retains the frozen TaskPack and phase boundary", () => {
  const dag = source(
    "docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
  );
  const task = dag.slice(
    dag.indexOf("- id: CB-230"),
    dag.indexOf("- id: CB-240"),
  );
  for (const marker of [
    "phase: P2.4",
    "- CB-210",
    "- CB-220",
    "- AC-020",
    "- AC-021",
    "- AC-022",
    "- AC-024",
    "- AC-025",
    "- AC-062",
    "pass_gate: PG-2",
  ]) {
    assert.match(task, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  const contract = source("docs/governance/RUN_CONTRACT_P2_4_CB_230.md");
  for (const marker of [
    "916651854a6402254724c885398060b2e267e496",
    "ambiguous_send_outcome",
    "manual reconcile",
    "CB-240",
    "PG-2",
    "不创建新 repo",
    "AGPL-3.0-only AND GPL-3.0-only",
    "upstream_clarification_received=false",
  ]) {
    assert.match(
      contract,
      new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
    );
  }
});

test("schema v4 is additive, encrypted and confirmation guarded", () => {
  const migration = source("app/migrations/004_cb230_durable_outbox.sql");
  assert.doesNotMatch(migration, /\b(?:DROP|RENAME|VACUUM)\b/i);
  for (const marker of [
    "logical_message_sha256",
    "provider_client_id",
    "claim_owner",
    "dispatch_started_at",
    "confirmation_state",
    "outbox_attempt_events",
    "immutable_outbox_attempt_event",
    "confirmed_outbox_immutable",
    "outbox_confirmation_truth_guard",
  ]) {
    assert.match(migration, new RegExp(marker));
  }
  const database = source("app/src/services/db/database-adapter.js");
  for (const marker of [
    "claimNextOutbox",
    "markOutboxDispatchStarted",
    "markOutboxConfirmed",
    "recoverOutboxOnExclusiveStartup",
    "reconcileAllFinalOutboxJobs",
    "reconcileJobReplyState",
  ]) {
    assert.match(database, new RegExp(marker));
  }
  assert.doesNotMatch(
    database.slice(
      database.indexOf("getOutbox(outboxId)"),
      database.indexOf("getOutboxByDedupeKey"),
    ),
    /payload_ciphertext|target_ref_ciphertext/,
  );
});

test("worker and provider enforce stable chunks, bounded retry and receipt truth", () => {
  const worker = source("app/src/services/outbox/durable-outbox.js");
  for (const marker of [
    "buildStableOutboxIdentity",
    "computeBackoffDelayMs",
    "normalizeProviderConfirmation",
    "OUTBOX_CONFIRMATION_REQUIRED",
    "ambiguous_send_outcome",
    "manual_reconcile_required",
    "after_confirmation_commit",
    "TERMINAL_AUTH_ADVICE",
  ]) {
    assert.match(worker, new RegExp(marker));
  }
  const provider = source("app/src/adapters/channel/weixin/index.js");
  assert.match(provider, /async sendTextChunk/);
  assert.match(provider, /\^cb-outbox-/);
  assert.match(provider, /WEIXIN_OUTBOX_CHUNK_INVALID/);
  const api = source("app/src/adapters/channel/weixin/api.js");
  assert.match(api, /outcomeKnown/);
  assert.match(api, /retryAfterMs/);
});

test("accepted and terminal job replies are wired through durable outbox", () => {
  const inbox = source("app/src/services/inbox/durable-inbox.js");
  const acceptedCallback = inbox.indexOf("this.onAccepted");
  const acceptedCut = inbox.indexOf(
    'this.#fault("after_accepted_outbox_before_cursor")',
  );
  const cursorCommit = inbox.indexOf(
    "this.channelAdapter.commitCandidateCursor",
  );
  assert.ok(acceptedCallback >= 0);
  assert.ok(acceptedCallback < acceptedCut && acceptedCut < cursorCommit);

  const app = source("app/src/core/app.js");
  assert.match(app, /new DurableOutboxWorker/);
  // 原来这里要求 app.js 里存在 messageKind: "accepted"。PANEL-1 按主人的要求把
  // 「收到，正在处理……」那条自动回执整个删了，于是这条断言开始要求一个**被
  // 故意移除的功能**必须还在。契约变了，证据就得跟着变，否则它会一直对正确的
  // 代码亮红灯。
  //
  // 现在钉的是删掉之后仍然必须成立的那件事：终态回复照走 durable outbox，
  // 不因为没有了回执就变成直接发。
  assert.doesNotMatch(
    app,
    /messageKind: "accepted"/,
    "自动回执是 PANEL-1 故意删掉的，不能悄悄回来",
  );
  assert.match(app, /handleDurableJobTerminal/);
  assert.match(app, /resolveDurableReplyTargetForJob/);
  const stream = source("app/src/core/stream-delivery.js");
  assert.match(stream, /this\.outboxWorker\.stageMessage/);
  assert.match(stream, /messageKind: "result"/);
});

test("implementation kit supports candidate-only CB-230 acceptance", () => {
  const builder = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
  );
  const installer = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
  );
  const acceptance = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-durable-outbox.sh",
  );
  for (const value of [builder, installer, acceptance]) {
    assert.match(value, /CB-230/);
    assert.match(value, /P2\.4/);
    assert.match(value, /outbox-recovery-matrix/);
    assert.match(value, /outbox_worker_integrated/);
    assert.match(value, /cb_240_executed/);
    assert.match(value, /pg_2_executed/);
  }
  assert.match(installer, /candidate_only/);
  assert.match(acceptance, /service_must_be_inactive/);
  assert.match(acceptance, /canonical_runtime_db_present/);
  assert.match(acceptance, /provider_writes=false/);
});

test("CB-230 executable acceptance emits bounded synthetic claims", (t) => {
  const directory = temporaryDirectory(t);
  const runtimeRoot = path.join(directory, "runtime");
  const output = path.join(directory, "output");
  const keyFile = path.join(directory, "synthetic.key");
  fs.mkdirSync(runtimeRoot, { mode: 0o700 });
  fs.mkdirSync(output, { mode: 0o700 });
  fs.writeFileSync(
    keyFile,
    Buffer.from(
      "14a4c47d599b838b971428e008a08e4088921800fd9ddc62d80d221c73bc844c",
      "hex",
    ),
    { mode: 0o400 },
  );
  const result = spawnSync(
    process.execPath,
    [
      path.join(PROJECT_ROOT, "app/scripts/durable-outbox-acceptance.js"),
      "--runtime-root", runtimeRoot,
      "--key-file", keyFile,
      "--output-directory", output,
      "--release-commit", "916651854a6402254724c885398060b2e267e496",
      "--target-id-sha256", "7865f743d174",
    ],
    {
      cwd: PROJECT_ROOT,
      encoding: "utf8",
      timeout: 240_000,
      maxBuffer: 8 * 1024 * 1024,
    },
  );
  assert.equal(
    result.status,
    0,
    `status=${result.status} stdout=${result.stdout} stderr=${result.stderr}`,
  );
  assert.match(result.stdout, /CB230_DURABLE_OUTBOX_ACCEPTANCE=PASS/);
  const report = JSON.parse(
    fs.readFileSync(path.join(output, "outbox-recovery-matrix.json"), "utf8"),
  );
  assert.equal(report.result, "passed");
  assert.equal(report.executable_suite.failures, 0);
  assert.equal(report.ac_020_send_before_crash.restart_delivery_count, 1);
  assert.equal(report.ac_021_retry.attempts, 3);
  assert.deepEqual(report.ac_021_retry.retry_delays_ms, [1000, 2000]);
  assert.equal(report.ac_021_retry.real_wait_calls, 0);
  assert.equal(report.ac_022_dedupe.stage_count, 1000);
  assert.equal(report.ac_022_dedupe.confirmed_delivery_count, 1);
  assert.equal(report.ac_024_terminal.raw_provider_detail_forwarded, false);
  assert.equal(
    report.ac_025_chunks.source_sha256,
    report.ac_025_chunks.reconstructed_sha256,
  );
  assert.equal(
    report.ac_025_chunks.replied_before_all_final_chunks_confirmed,
    false,
  );
  assert.equal(
    report.ac_062_recovery.unknown_dispatch_auto_replay_count,
    0,
  );
  assert.equal(
    report.confirmation_truth.void_receipt.void_response_confirmed,
    false,
  );
  assert.equal(report.security.plaintext_db_wal_shm_hits, 0);
  assert.equal(report.security.encryption_key_hits, 0);
  assert.equal(report.boundaries.cb_240_executed, false);
  assert.equal(report.boundaries.pg_2_executed, false);
  assert.doesNotMatch(
    JSON.stringify(report),
    /CB230-FIXTURE|wxid_|Authorization|\/Users\/|\/var\/lib\//,
  );
});

test("strict license, source and unresolved conflict records remain frozen", () => {
  const sourceLock = JSON.parse(source("machine/source-lock.json"));
  assert.deepEqual(sourceLock.upstream_relationship, {
    automatic_sync_allowed: false,
    git_url_dependency_allowed: false,
    periodic_rebase_allowed: false,
    remote_allowed: false,
    runtime_source_fetch_allowed: false,
    submodule_allowed: false,
  });
  assert.equal(
    sourceLock.whereabouts_license_conflict.upstream_clarification_received,
    false,
  );
  assert.equal(
    sourceLock.whereabouts_license_conflict.preserve_original_license_and_source,
    true,
  );
  assert.deepEqual(
    new Set(
      sourceLock.whereabouts_license_conflict.compliance_expression
        .split("AND")
        .map((value) => value.trim()),
    ),
    new Set(["AGPL-3.0-only", "GPL-3.0-only"]),
  );
});

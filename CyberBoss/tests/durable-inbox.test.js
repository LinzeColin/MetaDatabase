"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const PROJECT = path.resolve(__dirname, "..");

function source(relative) {
  return fs.readFileSync(path.join(PROJECT, relative), "utf8");
}

test("CB-210 contract is candidate-cursor, durable-before-cursor and phase bounded", () => {
  const contract = source("docs/governance/RUN_CONTRACT_P2_2_CB_210.md");
  for (const marker of [
    "P2.2 / CB-210",
    "4f914e3b6ed3145a16c1572f4176068b9829b920",
    "AC-004",
    "AC-023",
    "AC-063",
    "INV-001",
    "INV-002",
    "after_fetch_before_durable",
    "after_durable_before_cursor",
    "after_cursor",
    "CB-220",
    "CB-230",
    "不创建新 repo",
    "AGPL-3.0-only AND GPL-3.0-only",
    "upstream_clarification_received=false",
  ]) {
    assert.match(contract, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("WeChat fetch cannot commit cursor or plaintext context state", () => {
  const adapter = source("app/src/adapters/channel/weixin/index.js");
  const fetchStart = adapter.indexOf("async fetchUpdates(");
  const fetchEnd = adapter.indexOf("async getUpdates(", fetchStart);
  assert.ok(fetchStart >= 0 && fetchEnd > fetchStart);
  const fetchBody = adapter.slice(fetchStart, fetchEnd);
  // 这一条才是真正的安全属性：拉取本身绝不能提交游标或落明文上下文。
  assert.doesNotMatch(fetchBody, /saveSyncBuffer|commitSyncBuffer|rememberContextToken/);

  // fetchUpdates 后来被重构成委托给 fetchUpdatesFor（多账号），candidateCursor
  // 跟着搬了进去。原来这里按函数名偏移量切一段源码再找字符串，于是一次**正确**
  // 的重构把它弄红了——测试对着正确的改动亮红灯，比没有测试更糟。
  //
  // 所以跟着委托链走：真正要证明的是"拉取产出的是候选游标，提交是另一步"，
  // 而不是"这个字符串出现在这个函数的字节区间里"。
  const delegateStart = adapter.indexOf("function fetchUpdatesFor(");
  assert.ok(delegateStart >= 0, "fetchUpdates 的委托目标不见了，这条契约要重新看");
  const delegateEnd = adapter.indexOf("function accountView(", delegateStart);
  assert.ok(delegateEnd > delegateStart, "切不出 fetchUpdatesFor 的函数体");
  const delegateBody = adapter.slice(delegateStart, delegateEnd);
  assert.match(delegateBody, /candidateCursor/);
  assert.doesNotMatch(
    delegateBody,
    /commitSyncBuffer/,
    "委托进去之后也不能顺手把游标提交了",
  );
  assert.match(adapter, /commitCandidateCursor/);

  const cursor = source("app/src/adapters/channel/weixin/sync-buffer-store.js");
  for (const marker of [
    "CURSOR_COMPARE_AND_SET_FAILED",
    "CURSOR_REGRESSION",
    "O_NOFOLLOW",
    "fs.fsyncSync",
    "fs.renameSync",
    "0o600",
    "0o700",
  ]) {
    assert.match(cursor, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("durable coordinator orders all durability before explicit cursor commit", () => {
  const coordinator = source("app/src/services/inbox/durable-inbox.js");
  const accept = coordinator.indexOf("this.database.acceptInbound");
  const reject = coordinator.indexOf("this.database.rejectInbound");
  const durableCut = coordinator.indexOf('this.#fault("after_durable_before_cursor")');
  const commit = coordinator.indexOf("this.channelAdapter.commitCandidateCursor");
  const cursorCut = coordinator.indexOf('this.#fault("after_cursor")');
  assert.ok(accept >= 0 && accept < durableCut);
  assert.ok(reject >= 0 && reject < durableCut);
  assert.ok(durableCut < commit && commit < cursorCut);
  for (const marker of [
    "STABLE_SOURCE_MESSAGE_ID_REQUIRED",
    "NUMERIC_CURSOR_BATCH_GAP",
    "NUMERIC_CURSOR_BATCH_NOT_CONTINUOUS",
    "CURSOR_REGRESSION",
  ]) {
    assert.match(coordinator, new RegExp(marker));
  }
});

test("runtime spool persists cursor batch and policy rejection without a job", () => {
  const database = source("app/src/services/db/database-adapter.js");
  assert.match(database, /cursorBatchId/);
  assert.match(database, /cursor_batch_id/);
  assert.match(database, /rejectInbound/);
  assert.match(database, /status: "rejected"/);
  assert.match(database, /SELECT id FROM jobs WHERE inbox_id/);
  assert.match(database, /readInboundContextToken/);
});

test("App defaults durable inbox on and keeps scheduler/outbox boundary explicit", () => {
  const config = source("app/src/core/config.js");
  assert.match(config, /durableInboxOverride === undefined\s*\?\s*true/);
  assert.match(config, /CB_ALLOW_BASELINE_STAGING/);
  assert.match(config, /CB_RUNTIME_ENCRYPTION_KEY_FILE/);
  assert.match(config, /CB_RUNTIME_IDENTITY_KEY_FILE/);
  const app = source("app/src/core/app.js");
  assert.match(app, /new DurableInboxCoordinator/);
  assert.match(app, /readOwnerOnlyRuntimeKey/);
  assert.match(app, /durable batch queued/);
  assert.doesNotMatch(
    app.slice(
      app.indexOf("if (this.durableInboxCoordinator)"),
      app.indexOf("} else {", app.indexOf("if (this.durableInboxCoordinator)")),
    ),
    /handleIncomingMessage/,
  );
});

test("artifact and target scripts support candidate-only CB-210 acceptance", () => {
  const builder = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
  );
  const installer = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
  );
  const acceptance = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-durable-inbox.sh",
  );
  for (const value of [builder, installer, acceptance]) {
    assert.match(value, /CB-210/);
    assert.match(value, /P2\.2/);
    assert.match(value, /durable-inbox-matrix/);
    assert.match(value, /scheduler_integrated/);
    assert.match(value, /outbox_worker_integrated/);
    assert.match(value, /pg_2_executed/);
  }
  assert.match(installer, /candidate_only/);
  assert.match(acceptance, /service_must_be_inactive/);
  assert.match(acceptance, /canonical_runtime_db_present/);
});

test("strict license, source and unresolved conflict records remain frozen", () => {
  const sourceLock = JSON.parse(source("machine/source-lock.json"));
  assert.equal(sourceLock.repository, "LinzeColin/MetaDatabase");
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
        .map((item) => item.trim()),
    ),
    new Set(["AGPL-3.0-only", "GPL-3.0-only"]),
  );
});

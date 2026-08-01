"use strict";

// CB9-440 审批持久化与对象引用（AC-021 / AC-022 / FR-021 / FR-022）
//
//   AC-021 批准前后切断进程并重放；同一 request_id 最多一次副作用，
//          错误用户批准被拒。
//   AC-022 上传文件后 R2 对象校验 hash；Private-Database 仅存对象引用。
//
// 审批跨三条边界，各自一种真实的坏法：
//   跨进程 —— 批准和执行不在同一次调用里。中间挂了，重启后必须知道批过没有。
//   跨重启 —— 所以必须落盘，且**先落盘再执行**。
//   跨用户 —— 一个 request_id 只属于一个人。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  ApprovalError,
  ApprovalLedger,
  TERMINAL,
  canTransition,
  requestIdFor,
} = require("../src/services/approval/approval-ledger");
const {
  FileApprovalStore,
  MemoryApprovalStore,
} = require("../src/services/approval/file-approval-store");
const {
  ObjectKeyError,
  assertKeyBelongsToUser,
  userObjectKey,
} = require("../src/services/canonical/object-key");

const ALICE = `usr_${"a".repeat(24)}`;
const BOB = `usr_${"b".repeat(24)}`;
const SESSION = `comp_${"1".repeat(32)}`;

let clock = Date.parse("2026-07-29T14:48:00.000Z");
const now = () => new Date(clock);
const ledgerOn = (store) => new ApprovalLedger({ store, now });

const ask = (ledger, over = {}) => ledger.request({
  userScope: ALICE, sessionKey: SESSION, turnId: "turn-1",
  action: "shell.execute", target: "rm -rf ./build", ...over,
});

// ── AC-021 幂等 ───────────────────────────────────────────

test("AC-021 同一件事提两次拿到同一条记录，不是两条", () => {
  // request_id 由内容推出来。随机的话，重放会得到两个 id，台账认不出它们是
  // 同一件事——而「重放不产生第二个副作用」正是靠认出来实现的。
  const ledger = ledgerOn(new MemoryApprovalStore());
  const first = ask(ledger);
  const again = ask(ledger);
  assert.equal(first.request_id, again.request_id);
  assert.equal(first.created_at, again.created_at, "重放把创建时间改了");
});

test("AC-021 重放不会把已经批过的请求打回 pending", () => {
  // 打回的话，一条批过的请求会被批第二次——两次副作用。
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  ledger.approve({ requestId: request.request_id, byUserScope: ALICE });
  const replayed = ask(ledger);
  assert.equal(replayed.state, "approved", "重放把状态重置了");
});

test("AC-021 重复批准返回同一条记录，不产生第二次副作用", () => {
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  const once = ledger.approve({ requestId: request.request_id, byUserScope: ALICE });
  const twice = ledger.approve({ requestId: request.request_id, byUserScope: ALICE });
  assert.equal(once.decided_at, twice.decided_at, "第二次批准改写了决定时间");
  assert.equal(twice.state, "approved");
});

test("AC-021 执行权只能被认领一次", () => {
  // 这是「最多一次副作用」的实现。调用方必须拿到 claimed:true 才动手。
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  ledger.approve({ requestId: request.request_id, byUserScope: ALICE });

  const first = ledger.claimExecution({ requestId: request.request_id, byUserScope: ALICE });
  assert.equal(first.claimed, true);
  const second = ledger.claimExecution({ requestId: request.request_id, byUserScope: ALICE });
  assert.equal(second.claimed, false, "同一条审批被认领了两次");
  assert.equal(second.reason, "already_executed");
});

test("AC-021 没批准就不能执行", () => {
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  const claim = ledger.claimExecution({ requestId: request.request_id, byUserScope: ALICE });
  assert.equal(claim.claimed, false);
  assert.equal(claim.reason, "state_pending");
});

test("AC-021 拒绝之后不能再批准", () => {
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  ledger.reject({ requestId: request.request_id, byUserScope: ALICE });
  assert.throws(() => ledger.approve({ requestId: request.request_id, byUserScope: ALICE }),
    /ILLEGAL_TRANSITION/);
});

test("AC-021 终态出不去——这就是幂等的实现", () => {
  for (const state of TERMINAL) {
    for (const to of ["approved", "rejected", "executed", "pending"]) {
      assert.equal(canTransition(state, to), false, `${state} 还能转到 ${to}`);
    }
  }
});

test("AC-021 执行失败标成 failed，不回到 approved", () => {
  // 回去的话下一轮会再执行一次，而失败的原因多半还在。要重来就重新拍一次板。
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  ledger.approve({ requestId: request.request_id, byUserScope: ALICE });
  const failed = ledger.markFailed({ requestId: request.request_id, reason: "命令返回 127" });
  assert.equal(failed.state, "failed");
  assert.match(failed.failure_reason, /127/);
  // failed 之后认领返回 claimed:false 而不是抛——抛的话调用方得为一件「本来
  // 就不该做」的事写一个 catch，而它和「已经执行过了」是同一类结果。
  const claim = ledger.claimExecution({ requestId: request.request_id, byUserScope: ALICE });
  assert.equal(claim.claimed, false, "failed 之后还能认领执行");
  assert.equal(claim.reason, "state_failed");
});

// ── AC-021 跨用户 ─────────────────────────────────────────

test("AC-021 别人拿这个 id 去批，被拒", () => {
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  assert.throws(() => ledger.approve({ requestId: request.request_id, byUserScope: BOB }),
    /WRONG_USER/);
  assert.equal(ledger.read(request.request_id).state, "pending", "被拒的批准改了状态");
});

test("AC-021 身份检查排在所有别的检查之前", () => {
  // 「这个 id 已经批过了」也是信息。连是不是本人都不知道的时候，别的检查结果
  // 都不该泄漏给他。
  const ledger = ledgerOn(new MemoryApprovalStore());
  const request = ask(ledger);
  ledger.approve({ requestId: request.request_id, byUserScope: ALICE });
  // 已经批过 + 错误用户：报的必须是 WRONG_USER，不是「已经批过了」。
  assert.throws(() => ledger.approve({ requestId: request.request_id, byUserScope: BOB }),
    (error) => error.code === "WRONG_USER");
  // 执行认领同理。
  assert.throws(() => ledger.claimExecution({ requestId: request.request_id, byUserScope: BOB }),
    (error) => error.code === "WRONG_USER");
});

test("AC-021 两个人各自的审批互不影响", () => {
  const ledger = ledgerOn(new MemoryApprovalStore());
  const mine = ask(ledger);
  const theirs = ledger.request({
    userScope: BOB, sessionKey: `comp_${"2".repeat(32)}`, turnId: "turn-1",
    action: "shell.execute", target: "rm -rf ./build",
  });
  assert.notEqual(mine.request_id, theirs.request_id, "两个人的同一个动作撞成了一条");
  ledger.approve({ requestId: mine.request_id, byUserScope: ALICE });
  assert.equal(ledger.read(theirs.request_id).state, "pending");
});

test("AC-021 缺任何一段绑定都建不出来", () => {
  const ledger = ledgerOn(new MemoryApprovalStore());
  for (const missing of ["userScope", "sessionKey", "turnId", "action"]) {
    assert.throws(() => ask(ledger, { [missing]: "" }), /BINDING_REQUIRED/,
      `${missing} 空值被放行了`);
  }
});

// ── AC-021 跨重启 ─────────────────────────────────────────

test("AC-021 批准之后切断进程，重启读得回来", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-440-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "approvals.json");

  // 「进程一」提请求并批准。
  const before = ledgerOn(new FileApprovalStore({ filePath: file }));
  const request = ask(before);
  before.approve({ requestId: request.request_id, byUserScope: ALICE });

  // 「进程二」——全新的 store 和台账，只有盘上那份数据。
  const after = ledgerOn(new FileApprovalStore({ filePath: file }));
  const restored = after.read(request.request_id);
  assert.ok(restored, "重启后台账空了——用户会被要求再批一次");
  assert.equal(restored.state, "approved");
  assert.equal(restored.user_scope, ALICE);
  assert.equal(restored.session_key, SESSION);
  assert.equal(restored.turn_id, "turn-1");
});

test("AC-021 批准前切断进程，重启后仍是 pending 而不是丢失", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-440-b-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "approvals.json");
  const request = ask(ledgerOn(new FileApprovalStore({ filePath: file })));
  const after = ledgerOn(new FileApprovalStore({ filePath: file }));
  assert.equal(after.read(request.request_id).state, "pending");
});

test("AC-021 执行认领之后切断，重启不会再执行一次", (t) => {
  // 先写台账再执行。反过来的话，执行完还没记上就崩了，重启后台账说没执行过，
  // 于是再执行一次——而「执行了两次」用户多半发现不了。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-440-c-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "approvals.json");
  const before = ledgerOn(new FileApprovalStore({ filePath: file }));
  const request = ask(before);
  before.approve({ requestId: request.request_id, byUserScope: ALICE });
  assert.equal(before.claimExecution({ requestId: request.request_id, byUserScope: ALICE }).claimed, true);

  const after = ledgerOn(new FileApprovalStore({ filePath: file }));
  assert.equal(after.claimExecution({ requestId: request.request_id, byUserScope: ALICE }).claimed, false,
    "重启后又执行了一次");
});

test("AC-021 台账坏了当作没批过，不当作批过了", (t) => {
  // 读不出来的台账和没有台账，对「批过没有」给出同一个答案：不知道。
  // 不知道时正确的做法是让用户再批一次，而不是直接执行。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-440-d-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "approvals.json");
  fs.writeFileSync(file, "{ 这不是 JSON", "utf8");
  const ledger = ledgerOn(new FileApprovalStore({ filePath: file }));
  assert.equal(ledger.read("req_whatever"), null);
  // 而且照样能建新的。
  const fresh = ask(ledger);
  assert.equal(fresh.state, "pending");

  // 关键的一半：坏台账不能凭空产生一条「已经执行过」的记录。
  //
  // 变异测试补出来的——上面那两条断言对「读坏了就伪造一条 executed 出来」的
  // 实现是全绿的：read 一个不存在的 id 照样是 null，建新的照样能建。而伪造出
  // 来的那条会让一件从没批过的事被当成办完了，永远不再执行。
  assert.equal(ledger.read(fresh.request_id).state, "pending", "新建的请求被伪造成了别的状态");
  const claim = ledger.claimExecution({ requestId: fresh.request_id, byUserScope: ALICE });
  assert.equal(claim.claimed, false, "没批准就能执行");
  assert.equal(claim.reason, "state_pending", `状态被伪造成了 ${claim.reason}`);
  // 台账里除了我们刚建的这条，不该凭空多出别的。
  //
  // pendingExecution 只回 approved，看不见被伪造成 executed 的那种——所以这里
  // 直接看盘上的行数。坏台账必须**当成空的**载入，于是加一条之后正好一行。
  const saved = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.equal(saved.approvals.length, 1,
    `坏台账载入后凭空多出了 ${saved.approvals.length - 1} 条：${JSON.stringify(saved.approvals.map((r) => r.request_id))}`);
  assert.equal(saved.approvals[0].request_id, fresh.request_id);
});

test("AC-021 写盘是原子的——不会留下半截台账", () => {
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "approval", "file-approval-store.js"), "utf8");
  assert.match(src, /renameSync\(temp, this\.filePath\)/,
    "直接覆写：进程在写到一半时崩掉，整个台账就成了半截 JSON");
  const code = src.split("\n").map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");
  assert.ok(!/writeFileSync\(this\.filePath/.test(code), "有一条直接覆写目标文件的路");
});

test("AC-021 没改动就不写盘", (t) => {
  // 每次读都写的话，备份和同步会跟着涨，而且每次都是一次无意义的变更。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-440-e-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "approvals.json");
  const ledger = ledgerOn(new FileApprovalStore({ filePath: file }));
  const request = ask(ledger);
  const firstMtime = fs.statSync(file).mtimeMs;
  ledger.read(request.request_id);
  ledger.read(request.request_id);
  assert.equal(fs.statSync(file).mtimeMs, firstMtime, "只读也写了盘");
});

test("AC-021 重启后能列出「还要接着办的」", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-440-f-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "approvals.json");
  const before = ledgerOn(new FileApprovalStore({ filePath: file }));
  const pending = ask(before, { turnId: "t-pending" });
  const approved = ask(before, { turnId: "t-approved" });
  const done = ask(before, { turnId: "t-done" });
  before.approve({ requestId: approved.request_id, byUserScope: ALICE });
  before.approve({ requestId: done.request_id, byUserScope: ALICE });
  before.claimExecution({ requestId: done.request_id, byUserScope: ALICE });

  const after = ledgerOn(new FileApprovalStore({ filePath: file }));
  const todo = after.pendingExecution(ALICE).map((r) => r.turn_id);
  assert.deepEqual(todo, ["t-approved"],
    `只有批过还没执行的该回来，实际：${todo.join(",")}`);
  assert.ok(!todo.includes(pending.turn_id));
});

test("AC-021 过期的请求不能再批", () => {
  const store = new MemoryApprovalStore();
  const ledger = ledgerOn(store);
  const request = ask(ledger, { ttlMs: 1000 });
  clock += 5000;
  assert.throws(() => ledger.approve({ requestId: request.request_id, byUserScope: ALICE }),
    /REQUEST_EXPIRED/);
  assert.equal(ledger.read(request.request_id).state, "expired");
  clock = Date.parse("2026-07-29T14:48:00.000Z");
});

// ── AC-022 对象引用 ───────────────────────────────────────

test("AC-022 对象键把每个人关在自己那一段前缀里", () => {
  const mine = userObjectKey({ userId: ALICE, category: "attachment", objectId: "photo", version: 1 });
  assert.ok(mine.startsWith(`cyberboss/users/`), mine);
  assert.doesNotThrow(() => assertKeyBelongsToUser(mine, ALICE));
  assert.throws(() => assertKeyBelongsToUser(mine, BOB), ObjectKeyError,
    "别人的键通过了归属检查");
});

test("AC-022 键里逃不出自己的前缀", () => {
  // 逃得出去的话，一个人的键就能命名另一个人的对象。
  for (const evil of ["../bob", "a/b", "..", "a b", ""]) {
    assert.throws(
      () => userObjectKey({ userId: ALICE, category: "attachment", name: evil, version: 1 }),
      ObjectKeyError, `${JSON.stringify(evil)} 被放行了`);
  }
});

test("AC-022 新版本写新键，不覆盖旧的", () => {
  // 覆盖的话，「回退到上一个版本」这件事就没有对象可指了。
  const v1 = userObjectKey({ userId: ALICE, category: "attachment", objectId: "photo", version: 1 });
  const v2 = userObjectKey({ userId: ALICE, category: "attachment", objectId: "photo", version: 2 });
  assert.notEqual(v1, v2);
});

test("AC-022 事件的公开载荷里只放对象引用，不放路径", () => {
  // FR-022：「Timeline 仅保存对象引用」。绝对路径既是泄漏（暴露服务器布局），
  // 也是错的（对象在 R2，本机那份只是缓存）。
  const { makeSessionEvent } = require("../src/services/timeline/session-event");
  const key = userObjectKey({ userId: ALICE, category: "attachment", objectId: "photo", version: 1 });
  const event = makeSessionEvent({
    type: "media", mode: "COMPANION", userScope: ALICE, sessionKey: SESSION,
    idempotencyKey: "media-1", publicPayload: { object_ref: key, bytes: 1024 },
    at: new Date("2026-07-29T14:48:00.000Z"),
  });
  assert.equal(event.public_payload.object_ref, key);
  // 反面：真的塞一条绝对路径进去必须被拒。
  assert.throws(() => makeSessionEvent({
    type: "media", mode: "COMPANION", userScope: ALICE, sessionKey: SESSION,
    idempotencyKey: "media-2", publicPayload: { where: "/srv/linze/apps/cache/photo.jpg" },
    at: new Date("2026-07-29T14:48:00.000Z"),
  }), /private value in public payload/);
});

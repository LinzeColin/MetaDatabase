"use strict";

// 前 5 个人和主人共用同一个 Codex app-server，而调度器是串行的：一次只跑一个
// runtime job。纯先到先得的话，一个访客的长 turn 会把主人的消息堵在后面——主人
// 的助理不会崩，但会变得不可用，而那正是「不能把我的 codex 搞崩溃」的实际含义。
//
// 所以队列改成主人优先，同一档内仍然先到先得。
//
// peek 和 claim 必须用完全相同的排序：调度器先 peek 拿到 head，再带着
// expectedJobId 去 claim。两边选中不同的 job 就会一直 claim 不上，队列直接卡死。
// 这个套件对两条路各断言一次。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");

const FIXTURE_KEY = Buffer.from(
  "8f4cb5db5aa765f11f782f87371dba5f9fde8cbe0f20d08c96f2ea2a9d58e8f2",
  "hex",
);

const OWNER_ID = "usr_owner_000000000000000000";
const GUEST_ID = "usr_guest_000000000000000000";

function openSpool(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-queue-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: Buffer.from(FIXTURE_KEY),
    identityKey: Buffer.from(FIXTURE_KEY),
  });
}

// 主人优先是按 users.role 判的，所以两个人都得真的在表里。直接写 users 而不是
// 走注册流程：这个套件测的是排序，不是注册。
function seedUsers(database) {
  const now = new Date().toISOString();
  const insert = database.database.prepare(
    `INSERT INTO users(user_id, role, status, created_at, updated_at)
     VALUES(?, ?, 'active', ?, ?)`,
  );
  insert.run(OWNER_ID, "owner", now, now);
  insert.run(GUEST_ID, "user", now, now);
}

function enqueue(database, index, userId) {
  return database.acceptInbound({
    source: "weixin",
    sourceAccountRef: "fixture-account",
    sourceMessageId: `msg-${index}`,
    userRef: `ref-${index}`,
    messageType: "text",
    payload: `payload-${index}`,
    userId,
  });
}

test("访客先进队，主人后进队，主人仍然先被取出", (t) => {
  const database = openSpool(t);
  seedUsers(database);

  const guestJob = enqueue(database, 1, GUEST_ID);
  const ownerJob = enqueue(database, 2, OWNER_ID);
  assert.equal(guestJob.status, "queued");
  assert.equal(ownerJob.status, "queued");

  const head = database.peekNextRuntimeJob({});
  assert.equal(
    head.userId ?? head.user_id,
    OWNER_ID,
    "访客的 turn 会把主人的消息堵在后面",
  );
});

test("claim 和 peek 选中同一个 job——否则队列会卡死", (t) => {
  const database = openSpool(t);
  seedUsers(database);

  enqueue(database, 1, GUEST_ID);
  enqueue(database, 2, OWNER_ID);

  const head = database.peekNextRuntimeJob({});
  const claim = database.claimNextRuntimeJob({
    ownerId: "test-scheduler",
    leaseMs: 60_000,
    expectedJobId: head.id,
    bootId: "boot-1",
    pid: 1234,
  });
  assert.equal(claim.claimed, true, "peek 和 claim 排序不一致，claim 不上");
  assert.equal(claim.job.id, head.id);
});

test("同为访客时仍然先到先得", (t) => {
  const database = openSpool(t);
  seedUsers(database);

  const first = enqueue(database, 1, GUEST_ID);
  enqueue(database, 2, GUEST_ID);

  const head = database.peekNextRuntimeJob({});
  assert.equal(head.id, first.jobId, "同一档内不能打乱先来后到");
});

test("没有 user_id 的 job 算主人那一档", (t) => {
  // 主动问候、到点提醒这些是主人自己那条线上的东西，它们不带 user_id。
  // 如果被排到访客后面，主人的提醒会被陌生人的对话推迟。
  const database = openSpool(t);
  seedUsers(database);

  enqueue(database, 1, GUEST_ID);
  const systemJob = enqueue(database, 2, null);

  const head = database.peekNextRuntimeJob({});
  assert.equal(head.id, systemJob.jobId);
});

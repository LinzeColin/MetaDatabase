"use strict";

// 席位名次在时间戳并列时依然是「先到先得」。
//
// 这一份是从 public-entry.test.js 那两条 flaky 测试里长出来的。原来那两条
// （「排队按开通先后」和「前 N 个用主人的密钥」）**靠机器速度碰运气**：
//
//   机器慢 → 三次 admit 跨过毫秒边界 → created_at 各不相同 → 排序正确 → 绿
//   机器快 → 三次 admit 落在同一毫秒 → created_at 并列 → 排序落到 user_id
//            那个 HMAC 哈希上 → 次序被打乱 → 红
//
// 实测单文件跑 6 次红 3 次，全量套件里 0 次红（并行进程多、机器忙，反而慢到
// 跨过了毫秒边界）。**全量绿是绿得不对**：它证明的是「今天机器够忙」。
//
// 更要紧的是这不是测试的毛病。ordinaryUserRank 决定谁能用主人的额度：第 N 和
// 第 N+1 号在同一毫秒注册时，谁拿到那个位子由哈希决定，而产品对用户的承诺是
// 「先到先得」。默认开放注册（CB9-300 / AC-045）之后，同毫秒注册的概率只会
// 更高。
//
// 所以这一份**冻结时钟**，把并列变成必然而不是偶然。它在快机器和慢机器上给出
// 同一个结论——那正是原来那两条做不到的事。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { CyberbossApp } = require("../src/core/app");
const { UserAdmissionService } = require("../src/core/user-admission");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");

const ENCRYPTION_KEY = Buffer.alloc(32, 71);
const IDENTITY_KEY = Buffer.alloc(32, 73);
const BOT = "bot-seat-rank";

// 所有人都在这一毫秒注册。真实生产里两个人同时扫码就是这个样子。
const FROZEN = new Date("2026-08-01T00:00:00.000Z");

function frozenService(t, { seats = 2 } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb-seat-rank-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(dir, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
    now: () => FROZEN,
  });
  t.after(() => { try { spool.close(); } catch { /* 已经关了 */ } });
  const service = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["owner-sender"],
    registrationMode: "open",
    seatLimitProvider: () => seats,
    now: () => FROZEN,
  });
  return { spool, service };
}

const activate = (service, senderRef) =>
  service.admit({ botAccountRef: BOT, senderRef, text: "你好" }).userContext.userId;

test("同一毫秒注册的人，名次仍然按到达先后", (t) => {
  const { spool, service } = frozenService(t);
  const arrivals = ["first", "second", "third", "fourth", "fifth"];
  const ids = arrivals.map((who) => activate(service, who));

  // 前提：这一批确实全部并列，否则这条测试又变成了「碰巧跨过毫秒」。
  const stamps = new Set(spool.database
    .prepare("SELECT created_at FROM users WHERE role='user' AND status='active'")
    .all().map((row) => row.created_at));
  assert.equal(stamps.size, 1, `时间戳没有并列（${stamps.size} 个不同值），这条测试没测到该测的东西`);

  const ranks = ids.map((id) => service.users.ordinaryUserRank(id));
  assert.deepEqual(ranks, [1, 2, 3, 4, 5],
    `并列时名次乱了：${arrivals.map((w, i) => `${w}=${ranks[i]}`).join(" ")}`);
});

test("并列时名次也是稳定的——同一份数据问两次答案一样", (t) => {
  // 不稳定的名次比错的名次更难查：同一个人这次拿到额度、下次拿不到。
  const { service } = frozenService(t);
  const ids = ["a", "b", "c"].map((who) => activate(service, who));
  const first = ids.map((id) => service.users.ordinaryUserRank(id));
  const second = ids.map((id) => service.users.ordinaryUserRank(id));
  assert.deepEqual(first, second);
});

test("主人不占名次，哪怕他和别人同一毫秒建立", (t) => {
  const { spool, service } = frozenService(t);
  const ids = ["a", "b"].map((who) => activate(service, who));
  assert.deepEqual(ids.map((id) => service.users.ordinaryUserRank(id)), [1, 2]);
  assert.equal(service.users.ordinaryUserRank(spool.ownerUserId), 0, "主人占了一个名次");
});

test("并列时额度分配仍然是「前 N 个」——这是名次唯一的用途", (t) => {
  // 名次本身不重要，重要的是它决定谁能用主人的额度。第 N 和第 N+1 号同毫秒
  // 注册时，谁拿到那个位子不能由哈希决定。
  const { spool, service } = frozenService(t, { seats: 2 });
  const ids = ["first", "second", "third"].map((who) => activate(service, who));

  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    userAdmission: service,
    personaStore: { read: () => ({ access: { seats: 2 } }) },
    config: {},
    ownerCredentialCache: Object.freeze({
      providerId: "deepseek", model: "deepseek-chat", apiKey: "sk-owner",
    }),
  });

  assert.ok(app.resolveOwnerQuotaFor(ids[0]), "第 1 个到的人没拿到额度");
  assert.ok(app.resolveOwnerQuotaFor(ids[1]), "第 2 个到的人没拿到额度");
  assert.equal(app.resolveOwnerQuotaFor(ids[2]), null, "第 3 个到的人拿到了额度");
  assert.equal(app.resolveOwnerQuotaFor(spool.ownerUserId), null, "主人走了访客那条路");
});

test("查不到的人名次是 0，不是 1——0 表示「不在这个名单里」", (t) => {
  const { service } = frozenService(t);
  activate(service, "somebody");
  assert.equal(service.users.ordinaryUserRank("usr_" + "z".repeat(24)), 0);
  assert.equal(service.users.ordinaryUserRank(""), 0);
});

test("结构性：排序的并列键是 rowid，不是 user_id", (t) => {
  // user_id 是一个 HMAC 哈希，和到达顺序毫无关系。rowid 是 SQLite 的插入序，
  // 单调递增且永不并列——它**就是**到达顺序本身。
  //
  // 这条盯的是「有人把它改回去」。上面那几条能抓到行为变化，但只有这条能在
  // code review 之外挡住一次「顺手统一一下排序键」的改动。
  // 剔注释再扫：那个模块的注释里**必须**写着「不是 user_id」以及为什么——
  // 连注释一起扫的话，唯一能让测试变绿的办法是删掉那段解释，而那段解释正是
  // 下一个人不会把它改回去的原因。
  const code = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "users", "user-repository.js"), "utf8")
    .split("\n")
    .map((line) => line.replace(/(^|[^:])\/\/.*$/, "$1"))
    .join("\n");
  assert.match(code, /ORDER BY created_at, rowid/);
  assert.ok(!/ORDER BY created_at, user_id/.test(code),
    "名次排序又回到了按 user_id 哈希并列");
  // 反面：剥完之后代码还在，不是把整个文件剥空了。
  assert.match(code, /ordinaryUserRank\(userId\) \{/);
});

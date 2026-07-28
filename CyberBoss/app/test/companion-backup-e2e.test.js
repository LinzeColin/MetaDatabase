"use strict";

// 记日记、设提醒、看时间线、看统计、主动问候，以及真的把数据库备份到两个云。
//
// 这两块之前都只有模块级证明：日记服务从没被一条微信消息碰过，备份协调器的六个
// 依赖全是测试里的假函数——也就是说"备份"从来没把一个真数据库写到任何地方。
// 这套测试打的是真路径：真的 SQLite、真的快照、真的加解密、真的恢复演练。

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { UserAdmissionService } = require("../src/core/user-admission");
const { UserCompanionTurn, parseChineseDueAt } = require("../src/core/user-companion-turn");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { BackupRunner, decryptWithKey, encryptWithKey } = require("../src/services/backup/backup-runner");
const { createObjectClients } = require("../src/services/backup/object-clients");

const ENCRYPTION_KEY = Buffer.alloc(32, 71);
const IDENTITY_KEY = Buffer.alloc(32, 73);
const BOT = "bot-companion";

function harness(t, { nowMs = Date.parse("2026-07-28T02:00:00.000Z") } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-comp-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const databasePath = path.join(directory, "runtime.db");
  const spool = new RuntimeSpoolDatabase({
    databasePath,
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());

  const clock = { ms: nowMs };
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["owner-companion"],
    registrationMode: "invite",
  });
  const companion = new UserCompanionTurn({
    database: spool.database,
    now: () => clock.ms,
  });

  const register = (senderRef) => {
    const invite = admission.issueInvite({ maxUses: 1, ttlMs: 600_000 });
    admission.admit({ botAccountRef: BOT, senderRef, text: invite.code });
    admission.admit({ botAccountRef: BOT, senderRef, text: "同意并开始" });
    return admission.admit({ botAccountRef: BOT, senderRef, text: "hi" }).userContext;
  };

  return { directory, databasePath, spool, admission, companion, clock, register };
}

test("「记一下 ……」确定性落库，一次模型调用都不花", (t) => {
  const h = harness(t);
  const alice = h.register("alice");

  const saved = h.companion.handle(alice, "记一下 今天跑了五公里");
  assert.equal(saved.modelCalls, 0);
  assert.match(saved.text, /记下了/);

  const timeline = h.companion.handle(alice, "我的记忆");
  assert.equal(timeline.modelCalls, 0);
  assert.match(timeline.text, /今天跑了五公里/);

  // 没带内容时给的是"怎么写"，不是把空日记存进去。
  const empty = h.companion.handle(alice, "记一下");
  assert.match(empty.text, /像这样发给我/);
  assert.equal(h.companion.handle(alice, "我的记忆").text.split("\n").length, 2);
});

test("「提醒我 明天9点 交房租」被确定性解析成一个真实时刻", (t) => {
  const h = harness(t);
  const alice = h.register("alice");

  const created = h.companion.handle(alice, "提醒我 明天9点 交房租");
  assert.equal(created.modelCalls, 0);
  assert.match(created.text, /交房租/);

  const rows = h.companion.companion.listReminders(alice, { limit: 10 });
  assert.equal(rows.length, 1);
  const value = JSON.parse(rows[0].value_json);
  assert.equal(value.title, "交房租");
  // 2026-07-28 02:00Z 是东八区的 10:00，所以"明天9点"= 7/29 09:00 +08 = 7/29 01:00Z
  assert.equal(value.dueAt, "2026-07-29T01:00:00.000Z");
});

test("看不懂的时间照实说看不懂，绝不猜一个时刻", (t) => {
  const h = harness(t);
  const alice = h.register("alice");

  const vague = h.companion.handle(alice, "提醒我 有空的时候 买菜");
  assert.match(vague.text, /像这样发给我/);
  assert.equal(h.companion.companion.listReminders(alice, { limit: 10 }).length, 0);

  // 纯函数层面也确认一次：没有时刻就是 null，不是"现在"。
  assert.equal(parseChineseDueAt("有空的时候", Date.now()), null);
  assert.equal(parseChineseDueAt("25点", Date.now()), null);
});

test("统计是累加的，不会被下一条消息清掉", (t) => {
  const h = harness(t);
  const alice = h.register("alice");

  h.companion.recordMessage(alice);
  h.companion.recordMessage(alice);
  h.companion.handle(alice, "记一下 第一条");
  // 换一天再记一条，昨天那天必须还在。
  h.clock.ms += 24 * 60 * 60 * 1000;
  h.companion.recordMessage(alice);

  const week = h.companion.handle(alice, "最近7天");
  assert.equal(week.modelCalls, 0);
  assert.match(week.text, /最近 2 天/);
  assert.match(week.text, /聊天 3 次/);
  assert.match(week.text, /记录 1 次/);
});

test("两个用户的日记和统计互相看不到", (t) => {
  const h = harness(t);
  const alice = h.register("alice");
  const bob = h.register("bob");

  h.companion.handle(alice, "记一下 爱丽丝的秘密");
  h.companion.handle(bob, "记一下 鲍勃的秘密");

  assert.match(h.companion.handle(alice, "我的记忆").text, /爱丽丝的秘密/);
  assert.doesNotMatch(h.companion.handle(alice, "我的记忆").text, /鲍勃/);
  assert.doesNotMatch(h.companion.handle(bob, "我的记忆").text, /爱丽丝/);
});

test("主动问候默认关闭，开了才发，静音时段不发，全程零模型调用", (t) => {
  const h = harness(t);
  const alice = h.register("alice");

  // 默认关闭：没人被打扰过。
  assert.equal(h.companion.planProactive(alice).send, false);
  assert.equal(h.companion.planProactive(alice).modelCalls, 0);

  const on = h.companion.handle(alice, "可以问我");
  assert.equal(on.modelCalls, 0);
  const planned = h.companion.planProactive(alice);
  assert.equal(planned.send, true);
  assert.equal(planned.modelCalls, 0);
  assert.ok(planned.text, "该发的时候必须有一句现成的话，而不是现去问模型");

  // 刚发过就不再发。
  assert.equal(h.companion.planProactive(alice, { lastCheckinMs: h.clock.ms }).send, false);

  // 深夜静音。
  h.clock.ms = Date.parse("2026-07-28T15:00:00.000Z"); // 东八区 23:00
  assert.equal(h.companion.planProactive(alice).reason, "quiet_hours");

  // 说了别打扰就真的不打扰。
  h.clock.ms = Date.parse("2026-07-29T02:00:00.000Z");
  h.companion.handle(alice, "别再问我");
  assert.equal(h.companion.planProactive(alice).reason, "disabled_by_user");
});

test("缺任何一个云目标就如实报缺，不会只写一份副本", (t) => {
  const h = harness(t);

  const noneConfigured = new BackupRunner({
    databasePath: h.databasePath,
    encryptionKey: ENCRYPTION_KEY,
    stateDir: h.directory,
    config: {},
  });
  assert.equal(noneConfigured.status().ready, false);
  assert.deepEqual(noneConfigured.status().missing, ["r2", "oci"]);

  const onlyR2 = new BackupRunner({
    databasePath: h.databasePath,
    encryptionKey: ENCRYPTION_KEY,
    stateDir: h.directory,
    config: {
      r2AccountId: "acct",
      r2Bucket: "bucket",
      r2AccessKeyId: "key",
      r2SecretAccessKey: "secret",
    },
  });
  assert.equal(onlyR2.status().ready, false);
  assert.deepEqual(onlyR2.status().missing, ["oci"]);
  // 只配了一边就直接拒绝，而不是写一份然后发收据。
  assert.rejects(() => onlyR2.run(), (error) => error.code === "BACKUP_TARGET_ABSENT");
});

test("配齐两边时，真的把真数据库快照、加密、写到两处，并做一次恢复演练", async (t) => {
  const h = harness(t);
  h.register("alice");
  const stored = new Map();

  const fetchImpl = async (url, init) => {
    const key = String(url);
    if (init.method === "PUT") {
      stored.set(key, Buffer.from(init.body));
      return {
        ok: true,
        status: 200,
        headers: new Map([
          ["x-amz-version-id", `v-${stored.size}`],
          ["etag", `"e-${stored.size}"`],
        ]),
      };
    }
    const body = stored.get(key);
    return {
      ok: Boolean(body),
      status: body ? 200 : 404,
      headers: new Map(),
      async arrayBuffer() {
        return body;
      },
    };
  };

  const runner = new BackupRunner({
    databasePath: h.databasePath,
    encryptionKey: ENCRYPTION_KEY,
    stateDir: h.directory,
    config: {
      r2AccountId: "acct",
      r2Bucket: "bucket",
      r2AccessKeyId: "key",
      r2SecretAccessKey: "secret",
      ociParUrl: "https://objectstorage.example.com/p/tok/n/ns/b/bucket/o/",
    },
    fetchImpl,
  });
  assert.equal(runner.status().ready, true);

  const receipt = await runner.run({ releaseId: "rel-00000001" });

  assert.equal(receipt.dualCopy, true);
  assert.ok(receipt.copies.r2, "R2 必须给出一个版本号");
  assert.ok(receipt.copies.oci, "OCI 必须给出一个版本标识");
  assert.equal(stored.size, 2, "两处都必须真的收到了字节");

  // 云上那份必须是密文：明文里能读到表名，密文里不该有。
  const [uploaded] = [...stored.values()];
  assert.equal(uploaded.includes(Buffer.from("SQLite format 3")), false, "上传的必须是密文");
  assert.equal(uploaded.subarray(0, 5).toString(), "CBBK1");

  // 用同一把派生密钥能解回来，而且解出来的确实是个能打开的数据库。
  const key = crypto.createHmac("sha256", ENCRYPTION_KEY).update("cyberboss-backup-key").digest();
  const plain = decryptWithKey(key, uploaded);
  assert.equal(plain.subarray(0, 15).toString(), "SQLite format 3");
  assert.equal(require("node:crypto").createHash("sha256").update(plain).digest("hex"), receipt.plainSha256);

  // 收据落盘了，而且能读回来。
  const receipts = runner.listReceipts();
  assert.equal(receipts.length, 1);
  assert.equal(receipts[0].backupId, receipt.backupId);
});

test("一边失败就整次失败，不发半张收据", async (t) => {
  const h = harness(t);

  const fetchImpl = async (url, init) => {
    if (String(url).includes("objectstorage")) {
      return { ok: false, status: 503, headers: new Map() };
    }
    return {
      ok: true,
      status: 200,
      headers: new Map([["x-amz-version-id", "v-1"]]),
    };
  };

  const runner = new BackupRunner({
    databasePath: h.databasePath,
    encryptionKey: ENCRYPTION_KEY,
    stateDir: h.directory,
    config: {
      r2AccountId: "acct",
      r2Bucket: "bucket",
      r2AccessKeyId: "key",
      r2SecretAccessKey: "secret",
      ociParUrl: "https://objectstorage.example.com/p/tok/n/ns/b/bucket/o/",
    },
    fetchImpl,
  });

  await assert.rejects(
    () => runner.run({ releaseId: "rel-00000001" }),
    (error) => error.code === "BACKUP_DUAL_COPY_INCOMPLETE",
  );
  assert.deepEqual(runner.listReceipts(), [], "失败了就不该有任何收据");
});

test("加解密是真的，而且换一把密钥就打不开", () => {
  const key = Buffer.alloc(32, 5);
  const other = Buffer.alloc(32, 6);
  const plain = Buffer.from("SQLite format 3  一些内容");

  const sealed = encryptWithKey(key, plain);
  assert.notDeepEqual(sealed, plain);
  assert.deepEqual(decryptWithKey(key, sealed), plain);
  assert.throws(() => decryptWithKey(other, sealed));

  // 密文被改一个字节就必须解不开，而不是解出一段坏数据。
  const tampered = Buffer.from(sealed);
  tampered[tampered.length - 1] ^= 0xff;
  assert.throws(() => decryptWithKey(key, tampered));
});

test("对象客户端拒绝非 https 的 OCI 预授权地址", () => {
  assert.throws(
    () => createObjectClients({ ociParUrl: "http://objectstorage.example.com/p/x/" }),
    (error) => error.code === "OCI_PAR_MUST_BE_HTTPS",
  );
});

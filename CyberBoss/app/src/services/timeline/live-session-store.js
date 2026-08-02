"use strict";

// 把统一 Session 接到**真实链路**上（CB9-400 收尾 / AC-002、AC-004、AC-044）。
//
// 这个文件是补一个洞，而那个洞是我自己挖的：
//
//   CB9-400 那一轮做了事件模型、日记投影、未来自我、审批台账，加起来七十多条测试
//   全绿，迁移 016 也在生产上跑过了——`agent_sessions_v009` 表实实在在地存在。
//   然后我把 S4 标成了完成。
//
//   今天去生产上一查：**0 行**。真实入站消息一条条进来、一条条回出去，从来没有
//   任何代码往这张表里写过。整层是个孤岛。
//
// 这正是这个仓反复栽的那个形状，只是这次是我造的。教训不是「测试没写够」——
// 那七十多条测的东西都对。教训是**「模块能用」和「真实链路上有人用它」是两件事**，
// 而只有后者能支撑 AC-002/004/044 那种「同一个人连续两轮」的验收。
//
// 所以这个模块只做一件事：在每一个真实 turn 上，把这个人这个模式的那条会话
// **取出来或者建出来**，并且把上下文版本推进一格。

const { createHmac, randomBytes } = require("node:crypto");

const MODES = Object.freeze(["OWNER", "COMPANION"]);
const STATES = Object.freeze(["active", "paused", "reconcile", "closed"]);

const HEX_ONLY = /^[0-9a-fA-F]+$/;

// 密钥两种形状都收：Buffer，和 hex 字符串。
//
// 这个分支不是「顺手兼容一下」，它是又一张 0 行的表换来的。
//
//   第一版这里写的是 `if (!Buffer.isBuffer(secret)) throw`。而真实链路上的生产方
//   （user-admission）把子钥存成 **hex 字符串**——那不是笔误，是因为同一把子钥
//   还要喂给 stableSessionKey，而那个函数收字符串。于是每一个真实 turn 走到这里
//   都抛 SESSION_SECRET_REQUIRED，被 touchTurnSession 的 catch 吞成一行 warn，
//   表继续空着。上线之后真实消息进来又出去，看起来一切正常。
//
//   而这个仓的模块级测试全绿——因为测试自己写了 `Buffer.alloc(32, 9)`，
//   **从来没问过真正的生产方给出来的是什么**。造出来的输入形状让套件全绿而
//   生产 100% 失效，这是同一个坑的第十一次。
//
// 所以收两种形状，但**不收随便一个字符串**：
//
//   hex 必须偶数长度、只含 hex 字符、折算出来至少 16 字节。
//   Buffer.from(x, "hex") 遇到非法字符会**悄悄截断**——Buffer.from("zz","hex")
//   得到一个空 Buffer，那等于压根没有密钥，而且不会有任何人报错。
function normalizeSecret(secret) {
  if (Buffer.isBuffer(secret)) {
    return secret.length >= 16 ? secret : null;
  }
  if (typeof secret !== "string") {
    return null;
  }
  const text = secret.trim();
  if (text.length < 32 || text.length % 2 !== 0 || !HEX_ONLY.test(text)) {
    return null;
  }
  return Buffer.from(text, "hex");
}

class LiveSessionError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "LiveSessionError";
    this.code = code;
    this.detail = detail;
  }
}

// 会话钥匙由 (user_id, mode) 推出来，用一把服务端密钥做 HMAC。
//
// 三条约束一起决定了这个形状：
//
//   **跨重启稳定**（AC-044）——所以不能含时间、不能含随机数。含了的话，进程一重启
//   同一个人就换了一条会话，「记得上一轮」当场失效，而表面上什么都没坏。
//
//   **两个人不会撞进同一条**（表上的 UNIQUE 也在兜这一层）——所以要含 user_id。
//
//   **不能从 session_key 反推出 user_id**——它会进回执、进 Status。所以是 HMAC
//   而不是把 user_id 拼进去。
function sessionKeyFor({ userId, mode, secret }) {
  const id = String(userId ?? "").trim();
  if (!id) {
    throw new LiveSessionError("SESSION_USER_REQUIRED", "userId");
  }
  if (!MODES.includes(mode)) {
    throw new LiveSessionError("SESSION_MODE_UNKNOWN", String(mode ?? ""));
  }
  const key = normalizeSecret(secret);
  if (!key) {
    // 没有密钥就不发钥匙。用一个固定字符串顶上的话，任何人拿到源码就能算出
    // 别人的 session_key。
    throw new LiveSessionError("SESSION_SECRET_REQUIRED", "secret");
  }
  return `sess_${createHmac("sha256", key).update(`${mode}\u0000${id}`).digest("hex").slice(0, 32)}`;
}

// 取出这条会话，没有就建一条，并把上下文版本推进一格。
//
// 一次事务里做完：分成「先查再插」两步的话，同一个人两条消息挨得极近时会双双
// 查到空、双双去插，第二条撞主键报错——而那条消息就这么丢了。
function touchLiveSession(database, {
  userId,
  mode,
  runtimeKind,
  secret,
  now = new Date(),
  beijing = null,
}) {
  if (!database) {
    throw new LiveSessionError("SESSION_DB_REQUIRED", "database");
  }
  const sessionKey = sessionKeyFor({ userId, mode, secret });
  const kind = String(runtimeKind ?? "").trim() || "unknown";
  const utc = new Date(now).toISOString();
  const local = beijing || utc;

  database.exec("BEGIN IMMEDIATE");
  try {
    // ON CONFLICT 而不是「查了再插」：同一个人两条消息挨得极近时，
    // 先查后插会双双查到空、双双去插，第二条撞主键报错，那条消息就丢了。
    database.prepare(
      `INSERT INTO agent_sessions_v009(
         user_id, mode, session_key, runtime_kind, state,
         context_version, last_event_at_utc, last_event_at_beijing,
         created_at_utc, updated_at_utc)
       VALUES(?,?,?,?,'active',1,?,?,?,?)
       ON CONFLICT(user_id, mode) DO UPDATE SET
         context_version = context_version + 1,
         last_event_at_utc = excluded.last_event_at_utc,
         last_event_at_beijing = excluded.last_event_at_beijing,
         updated_at_utc = excluded.updated_at_utc,
         runtime_kind = excluded.runtime_kind,
         -- 会话钥匙**不跟着更新**。跟着更新的话，重启后 runtime 换个名字就换
         -- 一条会话，AC-044 要的「重启后恢复同一条」当场失效。
         state = CASE WHEN agent_sessions_v009.state = 'closed' THEN 'active'
                      ELSE agent_sessions_v009.state END`,
    ).run(String(userId), mode, sessionKey, kind, utc, local, utc, utc);
    const row = database.prepare(
      "SELECT user_id, mode, session_key, runtime_kind, state, context_version,"
      + " last_event_at_utc, created_at_utc FROM agent_sessions_v009"
      + " WHERE user_id=? AND mode=?",
    ).get(String(userId), mode);
    database.exec("COMMIT");
    return Object.freeze({ ...row, created: row.context_version === 1 });
  } catch (error) {
    database.exec("ROLLBACK");
    throw error;
  }
}

// 读一条会话，不建。给「重启后还认不认得他」这类检查用。
function readLiveSession(database, { userId, mode }) {
  if (!database) {
    throw new LiveSessionError("SESSION_DB_REQUIRED", "database");
  }
  const row = database.prepare(
    "SELECT user_id, mode, session_key, runtime_kind, state, context_version,"
    + " last_event_at_utc, created_at_utc FROM agent_sessions_v009"
    + " WHERE user_id=? AND mode=?",
  ).get(String(userId ?? ""), String(mode ?? ""));
  return row ? Object.freeze(row) : null;
}

// 真实链路回执。
//
// 和会话分开写：会话回答「这个人现在在哪一条对话里」，回执回答「这条能力
// 真的被真实链路跑通过一次吗」——后者是 Status 不许伪绿的那把锁（AC-025）。
//
// user_scope 和 session_key 存哈希不存原值：回执要进 Status 和公开页，
// 原值进去就是 AC-043 说的泄漏。
function recordParityReceipt(database, {
  capabilityId,
  mode,
  userScope = null,
  sessionKey = null,
  outcome = "success",
  realPathVerified = true,
  now = new Date(),
  beijing = null,
  secret,
}) {
  if (!database) {
    throw new LiveSessionError("SESSION_DB_REQUIRED", "database");
  }
  if (!["success", "failure", "unknown"].includes(outcome)) {
    throw new LiveSessionError("RECEIPT_OUTCOME_UNKNOWN", String(outcome));
  }
  // 和 sessionKeyFor 同一把归一化：这里原本也只认 Buffer，而真实链路给的是
  // hex 字符串——于是 user_scope_hash 和 session_key_hash 会**双双静默存成 NULL**，
  // 回执照样落库、看起来一切正常，只是回执再也对不上是谁的。
  const key = normalizeSecret(secret);
  if (!key) {
    throw new LiveSessionError("SESSION_SECRET_REQUIRED", "secret");
  }
  const hash = (value) => (value
    ? createHmac("sha256", key).update(String(value)).digest("hex").slice(0, 32)
    : null);
  const utc = new Date(now).toISOString();
  database.prepare(
    `INSERT INTO parity_receipts_v009(
       receipt_id, capability_id, mode, user_scope_hash, session_key_hash,
       real_path_verified, outcome, occurred_at_utc, occurred_at_beijing)
     VALUES(?,?,?,?,?,?,?,?,?)`,
  ).run(
    // 回执 id 是随机的，不是从内容推出来的。
    //
    // 原来推的料是 capability + mode + 时间 + userScope。会话钥匙必须那样推
    // （它是**稳定身份**，跨重启要算得出同一个），但回执是**事件**——同一个人
    // 同一项能力在同一毫秒里发生两次是完全正常的（比如两条提醒同时到点），
    // 而那两条推出来的 id 一模一样，第二条撞主键。撞了之后 recordDeliveryReceipt
    // 的 catch 把它吞成一行 warn，于是一条真实发生过的投递从账上消失了。
    //
    // AC-025 判的是「最近一次成功/失败是什么时候」，丢掉的那条正好可能是最近
    // 的那条——面板会因此显示一个偏旧的时间，看起来像「有点久没人用了」。
    `rcpt_${randomBytes(16).toString("hex")}`,
    String(capabilityId), String(mode), hash(userScope), hash(sessionKey),
    realPathVerified ? 1 : 0, outcome, utc, beijing || utc,
  );
}

module.exports = {
  LiveSessionError,
  MODES,
  STATES,
  readLiveSession,
  recordParityReceipt,
  sessionKeyFor,
  touchLiveSession,
};

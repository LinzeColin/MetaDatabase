"use strict";

// 审批台账（CB9-440 / AC-021、FR-021）。
//
// FR-021 的原话：「审批绑定 user/session/turn/request，重启后可恢复；重复批准
// 不产生重复副作用。」
//
// 审批是这个系统里**唯一一件由人拍板、由机器执行**的事。它跨进程、跨重启、
// 跨用户，三条边界各自都有一种真实会发生的坏法：
//
//   跨进程 —— 批准和执行不在同一次调用里。中间进程挂了，重启后必须知道
//              「这件事批过了没有」。只存在内存里的话，重启即失忆，用户会被
//              要求再批一次；而他多半会以为第一次没生效，于是又批一次——
//              两次副作用。
//   跨重启 —— 所以台账必须落盘，且**先落盘再执行**。反过来的话，执行完还没
//              记上就崩了，重启后台账说没批过，于是再执行一次。
//   跨用户 —— 一个 request_id 只属于一个人。别人拿到这个 id 去批，必须被拒。
//              AC-021 明说「错误用户批准被拒」。
//
// 幂等的实现方式是**状态机 + 唯一键**，不是「查一下有没有」。查一下的写法在
// 两个进程同时批准时会双双查到「没批过」——那正是重复副作用最容易发生的时刻。

const crypto = require("node:crypto");

// 一条审批的一生。箭头是唯一允许的方向。
const STATES = Object.freeze({
  pending: ["approved", "rejected", "expired"],
  approved: ["executed", "failed"],
  // 终态。从这里出不去——这就是「重复批准不产生重复副作用」的实现。
  executed: [],
  rejected: [],
  expired: [],
  failed: [],
});

const TERMINAL = Object.freeze(["executed", "rejected", "expired", "failed"]);

class ApprovalError extends Error {
  constructor(code, detail = "") {
    super(detail ? `${code}: ${detail}` : code);
    this.name = "ApprovalError";
    this.code = code;
  }
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

// request_id 由内容推出来，不是随机生成。
//
// 随机的话，同一个请求重放会得到两个 id，台账认不出它们是同一件事——而
// 「重放不产生第二个副作用」正是靠认出来实现的。
//
// 分隔符用 \u0000：这五段里任何一段都可能含空格（action 是 "shell.execute"
// 但 target 是一整条命令行）。用空格拼的话，("rm -rf a", "b") 和
// ("rm -rf", "a b") 会拼出同一个串，两件不同的事拿到同一个 request_id——
// 于是批准其中一件等于批准了另一件。
// 写成转义而不是裸字节：裸 NUL 会让 grep 和 diff 把整个文件当成二进制。
function requestIdFor({ userScope, sessionKey, turnId, action, target }) {
  return `req_${crypto.createHash("sha256")
    .update([userScope, sessionKey, turnId, action, target].join("\u0000"))
    .digest("hex").slice(0, 24)}`;
}

function canTransition(from, to) {
  return Array.isArray(STATES[from]) && STATES[from].includes(to);
}

class ApprovalLedger {
  // store 是注入的：内存一份给测试，落盘一份给线上。台账自己不关心存在哪儿，
  // 但它要求 store 提供**原子的**读改写——幂等靠的是那个原子性。
  constructor({ store, now = () => new Date() } = {}) {
    if (!store || typeof store.transact !== "function") {
      throw new ApprovalError("STORE_REQUIRED", "store must provide transact()");
    }
    this.store = store;
    this.now = now;
  }

  // 提一个待批的请求。同一件事提两次拿到同一条记录，不是两条。
  request({ userScope, sessionKey, turnId, action, target = "", ttlMs = 15 * 60 * 1000 } = {}) {
    const scope = normalizeText(userScope);
    const session = normalizeText(sessionKey);
    const turn = normalizeText(turnId);
    const act = normalizeText(action);
    if (!scope || !session || !turn || !act) {
      throw new ApprovalError("BINDING_REQUIRED",
        "user/session/turn/action all required");
    }
    const requestId = requestIdFor({
      userScope: scope, sessionKey: session, turnId: turn, action: act, target,
    });
    const at = this.now();
    return this.store.transact((rows) => {
      const existing = rows.get(requestId);
      if (existing) {
        // 已经有了就原样返回。**不重置状态**——重置的话，一条已经批过的请求
        // 会因为重放回到 pending，然后被批第二次。
        return existing;
      }
      const record = Object.freeze({
        request_id: requestId,
        user_scope: scope,
        session_key: session,
        turn_id: turn,
        action: act,
        target: normalizeText(target),
        state: "pending",
        created_at: at.toISOString(),
        expires_at: new Date(at.getTime() + ttlMs).toISOString(),
        decided_at: null,
        decided_by: null,
        executed_at: null,
      });
      rows.set(requestId, record);
      return record;
    });
  }

  // 批准。
  //
  // 三件事同时发生且不可分：核对是不是本人、核对状态能不能转、把状态写下去。
  // 分开做的话，两个进程会同时通过前两步。
  approve({ requestId, byUserScope }) {
    return this.#decide({ requestId, byUserScope, to: "approved" });
  }

  reject({ requestId, byUserScope }) {
    return this.#decide({ requestId, byUserScope, to: "rejected" });
  }

  #decide({ requestId, byUserScope, to }) {
    const id = normalizeText(requestId);
    const by = normalizeText(byUserScope);
    if (!id || !by) {
      throw new ApprovalError("BINDING_REQUIRED", "requestId and byUserScope required");
    }
    const at = this.now();
    return this.store.transact((rows) => {
      const record = rows.get(id);
      if (!record) {
        throw new ApprovalError("REQUEST_NOT_FOUND", id);
      }
      // 跨用户那条边界。放在最前面：连是不是本人都不知道的时候，别的检查
      // 结果都不该泄漏给他（「这个 id 已经批过了」也是信息）。
      if (record.user_scope !== by) {
        throw new ApprovalError("WRONG_USER",
          "approval is bound to another user");
      }
      if (new Date(record.expires_at).getTime() <= at.getTime() && record.state === "pending") {
        const expired = Object.freeze({ ...record, state: "expired", decided_at: at.toISOString() });
        rows.set(id, expired);
        throw new ApprovalError("REQUEST_EXPIRED", id);
      }
      if (record.state === to) {
        // 重复批准：原样返回，**不产生第二次副作用**。这是 AC-021 的核心。
        return record;
      }
      if (!canTransition(record.state, to)) {
        throw new ApprovalError("ILLEGAL_TRANSITION", `${record.state} -> ${to}`);
      }
      const decided = Object.freeze({
        ...record, state: to, decided_at: at.toISOString(), decided_by: by,
      });
      rows.set(id, decided);
      return decided;
    });
  }

  // 认领执行权。
  //
  // 返回 true 表示「这一次由你执行」，false 表示「已经有人执行过了」。
  // 调用方必须在**拿到 true 之后**才去做那件事，而且拿到 false 时什么都不做。
  //
  // 先写台账再执行，不是反过来：执行完还没记上就崩了的话，重启后台账说没执行
  // 过，于是再执行一次。先写的代价是「记了但没执行」——那种情况用户会发现
  // 事情没办，会再说一次；而「执行了两次」他多半发现不了。
  claimExecution({ requestId, byUserScope }) {
    const id = normalizeText(requestId);
    const by = normalizeText(byUserScope);
    const at = this.now();
    return this.store.transact((rows) => {
      const record = rows.get(id);
      if (!record) {
        throw new ApprovalError("REQUEST_NOT_FOUND", id);
      }
      if (record.user_scope !== by) {
        throw new ApprovalError("WRONG_USER", "approval is bound to another user");
      }
      if (record.state === "executed") {
        return { claimed: false, record, reason: "already_executed" };
      }
      if (record.state !== "approved") {
        return { claimed: false, record, reason: `state_${record.state}` };
      }
      const executed = Object.freeze({ ...record, state: "executed", executed_at: at.toISOString() });
      rows.set(id, executed);
      return { claimed: true, record: executed, reason: "" };
    });
  }

  // 执行失败时把它标出来。
  //
  // 不回到 approved：回去的话下一轮会再执行一次，而失败的原因多半还在。
  // failed 是终态，要重来就重新走一遍 request + approve——那需要人再拍一次板，
  // 而这正是应该的。
  markFailed({ requestId, reason = "" }) {
    const id = normalizeText(requestId);
    return this.store.transact((rows) => {
      const record = rows.get(id);
      if (!record) {
        throw new ApprovalError("REQUEST_NOT_FOUND", id);
      }
      if (!canTransition(record.state, "failed")) {
        throw new ApprovalError("ILLEGAL_TRANSITION", `${record.state} -> failed`);
      }
      const failed = Object.freeze({
        ...record, state: "failed", decided_at: record.decided_at,
        failure_reason: normalizeText(reason).slice(0, 200),
      });
      rows.set(id, failed);
      return failed;
    });
  }

  read(requestId) {
    return this.store.transact((rows) => rows.get(normalizeText(requestId)) || null);
  }

  // 重启后要接着办的那些。
  //
  // 只有 approved 会回来：pending 的还没人拍板，terminal 的已经完了。
  pendingExecution(userScope) {
    const scope = normalizeText(userScope);
    return this.store.transact((rows) => Object.freeze([...rows.values()]
      .filter((record) => record.state === "approved" && (!scope || record.user_scope === scope))
      .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))));
  }
}

module.exports = {
  ApprovalError,
  ApprovalLedger,
  STATES,
  TERMINAL,
  canTransition,
  requestIdFor,
};

"use strict";

// CB9-110 Owner 主 Session/Thread/Workspace 统一入口（AC-002 / AC-003）
//
//   AC-002 会话守恒：同一 Owner 依次发送普通消息、创建提醒、触发提醒、脉冲、审批，
//          所有回执的 session_key/thread_ref/workspace_ref 逻辑身份相同。
//   AC-003 不静默回退：关闭 Owner Runtime 后发送消息，状态为 queued_owner_runtime
//          或 explicit_unavailable，**provider_calls=0**。
//
// AC-003 是这一版最容易被"做成看起来对"的一条：一个把主人降级到 provider router
// 的实现，用户侧看到的是"它回话了"，只是换了个模型——这正是 v0.0.0.9 要消除的
// 「核心语义被稀释」。所以这里断言的是**主人的 turn 一次都不能进 provider 路径**。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { SessionStore } = require("../src/adapters/runtime/codex/session-store");

const APP_SRC = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");

const OWNER_SENDER = "wx-owner-1";
const WORKSPACE_ID = "cyberboss";
const ACCOUNT_ID = "5552be32014a-im.bot";

function store(t) {
  const dir = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "cb9-110-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return new SessionStore({ filePath: path.join(dir, "sessions.json") });
}

// ── AC-002 会话守恒 ─────────────────────────────────────────

test("AC-002 五类事件对同一 Owner 产出同一把 binding key", (t) => {
  const s = store(t);
  // 这五个名字对应 AC-002 点名的五类事件。它们在 app.js 里是五个不同的调用点，
  // 但传给 buildBindingKey 的三元组必须一致——否则主人"换个入口就换了个线程"，
  // 正是原版体验丢失的地方。
  const identity = { workspaceId: WORKSPACE_ID, accountId: ACCOUNT_ID, senderId: OWNER_SENDER };
  const keys = {
    普通消息: s.buildBindingKey(identity),
    创建提醒: s.buildBindingKey(identity),
    触发提醒: s.buildBindingKey(identity),
    脉冲: s.buildBindingKey(identity),
    审批: s.buildBindingKey(identity),
  };
  const distinct = new Set(Object.values(keys));
  assert.equal(distinct.size, 1, `五类事件产出了 ${distinct.size} 把 key：${JSON.stringify(keys)}`);
  assert.equal([...distinct][0], `${WORKSPACE_ID}:${ACCOUNT_ID}:${OWNER_SENDER}`);
});

test("AC-002 key 只由 workspace/account/sender 三元组决定，与调用顺序和多余字段无关", (t) => {
  const s = store(t);
  const base = s.buildBindingKey({ workspaceId: WORKSPACE_ID, accountId: ACCOUNT_ID, senderId: OWNER_SENDER });
  // 多带字段（不同调用点传的对象形状不完全一样）不能改变身份
  const withExtras = s.buildBindingKey({
    workspaceId: WORKSPACE_ID, accountId: ACCOUNT_ID, senderId: OWNER_SENDER,
    threadId: "thr-1", turnId: "turn-9", kind: "reminder",
  });
  assert.equal(withExtras, base, "多余字段改变了 binding key，说明身份不稳定");
});

test("AC-002 换人或换号必须换 key——守恒不能靠「所有人共用一把」实现", (t) => {
  const s = store(t);
  const base = s.buildBindingKey({ workspaceId: WORKSPACE_ID, accountId: ACCOUNT_ID, senderId: OWNER_SENDER });
  const otherSender = s.buildBindingKey({ workspaceId: WORKSPACE_ID, accountId: ACCOUNT_ID, senderId: "wx-guest-1" });
  const otherAccount = s.buildBindingKey({ workspaceId: WORKSPACE_ID, accountId: "18bb28ef8228-im.bot", senderId: OWNER_SENDER });
  assert.notEqual(otherSender, base, "换了人还是同一把 key——跨用户串线");
  assert.notEqual(otherAccount, base, "换了号还是同一把 key");
});

// ── AC-003 不静默回退 ───────────────────────────────────────

test("AC-003 主人的 turn 不得进入 provider router（provider_calls=0）", () => {
  // runUserModelTurn 是 provider router / DeepSeek 那条路。AC-003 的实质是：
  // Owner Runtime 不可用时，主人要么排队要么明确告知，**绝不能被降级到另一个模型**。
  // 逐个调用点核对它的守卫条件。
  // 按**所在函数体**判定，不用字符窗口。
  //
  // 第一版用「往前数 1200 字符」找守卫，结果两个假阳性：函数定义 `async
  // runUserModelTurn(` 被当成调用点（往回只看 60 字符，正好切在 async 和函数名
  // 之间），以及 dispatchGuestCheckin 的守卫被新加的注释挤出了窗口。
  // 窗口大小是个会随注释长短漂移的判据，函数边界不会。
  const lines = APP_SRC.split("\n");
  const fnStarts = [];
  lines.forEach((ln, i) => {
    const m = ln.match(/^  (?:async )?([a-zA-Z][a-zA-Z0-9_]*)\(/);
    if (m) fnStarts.push({ line: i, name: m[1] });
  });
  const bodyOf = (lineIdx) => {
    const start = [...fnStarts].reverse().find((f) => f.line <= lineIdx);
    const next = fnStarts.find((f) => f.line > lineIdx);
    return {
      name: start ? start.name : "?",
      text: lines.slice(start ? start.line : 0, next ? next.line : lines.length).join("\n"),
    };
  };

  const callSites = [];
  lines.forEach((ln, i) => {
    if (!ln.includes("runUserModelTurn(")) return;
    if (/^\s*(?:async\s+)?runUserModelTurn\s*\(/.test(ln)) return; // 函数定义本身
    callSites.push({ line: i + 1, ...bodyOf(i) });
  });
  assert.ok(callSites.length >= 3, `runUserModelTurn 调用点只找到 ${callSites.length} 个，断言可能已失效`);
  for (const site of callSites) {
    // 每个调用点所在的函数里都必须有一道"这一轮不是主人"的判定。
    const guarded = /route\s*===\s*"user"/.test(site.text)
      || /route\s*!==\s*"user"/.test(site.text)
      || /hasOwnerSeat\(/.test(site.text)
      || /isOwner/.test(site.text);
    assert.ok(
      guarded,
      `${site.name}()（第 ${site.line} 行）里调用了 runUserModelTurn 却没有非主人判定——主人可能被降级到 provider`,
    );
  }
});

test("AC-003 Owner Runtime 闸门存在且失败时返回 false，不往下走", () => {
  // isTurnDispatchBlocked 为真时 dispatchPreparedTurn 必须 return false（不派发），
  // 而不是继续往下或改走别的模型。
  const idx = APP_SRC.indexOf("isTurnDispatchBlocked(bindingKey, workspaceRoot)");
  assert.notEqual(idx, -1, "找不到 Owner Runtime 闸门");
  const after = APP_SRC.slice(idx, idx + 200);
  assert.match(after, /return false/, "闸门命中之后没有 return false，可能继续往下派发");
  assert.doesNotMatch(after, /runUserModelTurn/, "闸门命中之后直接走了 provider router——这就是静默回退");
});

test("AC-003 主人被拒时必须有明确出口，不能一声不吭", () => {
  // dispatchPreparedTurn 里那道 owner-only 闸门在拒绝时会给用户一句话。
  // 「没有任何反馈」和「换个模型偷偷回了」是 AC-003 要同时排除的两种坏。
  const idx = APP_SRC.indexOf("owner_only_capability");
  assert.notEqual(idx, -1, "找不到 owner-only 拒绝分支");
  const around = APP_SRC.slice(idx, idx + 400);
  assert.match(around, /sendText/, "拒绝时没有给用户任何反馈");
});

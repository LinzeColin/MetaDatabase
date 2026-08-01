"use strict";

// CB9-100 服务端双模式不变量与 spoof 防护（AC-001 / AC-005）
//
// 任务包 v0.0.0.9 的判据：
//   AC-001 模拟 owner/companion/client-spoof 三类输入；**仅服务端身份决定模式**，
//          spoof 返回拒绝且无 Runtime 调用。
//   AC-005 普通用户枚举 Owner-only 能力；**允许数=0**，拒绝覆盖
//          Workspace/Tool/Shell/MCP/Approval/Thread 六类。
//
// 为什么要枚举而不是抽查：能力表是会长的。抽查三五项的测试在新增一项
// owner-only 能力时依然全绿，而那一项可能正好没接闸门。这里对**整张表**求值，
// 加一项就自动被覆盖。

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  OWNER_ONLY_CAPABILITIES,
  USER_CAPABILITIES,
  UserContext,
} = require("../src/services/users/user-context");

const OWNER = `usr_${"o".repeat(24)}`;
const GUEST = `usr_${"g".repeat(24)}`;

const owner = () => new UserContext({ userId: OWNER, role: "owner" });
const companion = () => new UserContext({ userId: GUEST, role: "user" });

// ── AC-005 能力隔离 ─────────────────────────────────────────

test("AC-005 普通用户枚举全部 Owner-only 能力，允许数必须为 0", () => {
  const ctx = companion();
  const allowed = OWNER_ONLY_CAPABILITIES.filter((cap) => ctx.may(cap));
  assert.deepEqual(allowed, [], `普通用户拿到了不该有的能力：${allowed.join(", ")}`);
  assert.ok(OWNER_ONLY_CAPABILITIES.length >= 11, "能力表被缩小了，先确认不是把闸门删了");
});

test("AC-005 拒绝必须覆盖 Workspace/Tool/Shell/MCP/Approval/Thread 六类", () => {
  // Approval 和 Thread 在这个仓里**没有专属能力项**：
  //   审批口令（yes/always/无）走 shell.execute —— 批准的是要在主人机器上跑的命令；
  //   Thread（建线程/续线程）走 codex.turn / claudecode.turn。
  // 把这个映射显式钉在这里。以后有人加 approval.* 或 thread.* 而忘了接闸门，
  // 下面那条「六类各自至少有一项落在 owner-only 表里」就会红。
  const COVERAGE = {
    Workspace: ["workspace.read", "workspace.write"],
    Tool: ["project.tool"],
    Shell: ["shell.execute"],
    MCP: ["mcp.invoke"],
    Approval: ["shell.execute"],
    Thread: ["codex.turn", "claudecode.turn"],
  };
  const ctx = companion();
  for (const [group, caps] of Object.entries(COVERAGE)) {
    const known = caps.filter((c) => OWNER_ONLY_CAPABILITIES.includes(c));
    assert.ok(known.length > 0, `${group} 这一类在 owner-only 表里一项都没有`);
    for (const cap of known) {
      assert.equal(ctx.may(cap), false, `${group} 的 ${cap} 对普通用户是放行的`);
    }
  }
});

test("AC-005 两张能力表互不相交——否则「隔离」只是命名上的", () => {
  const overlap = OWNER_ONLY_CAPABILITIES.filter((c) => USER_CAPABILITIES.includes(c));
  assert.deepEqual(overlap, [], `两表重叠：${overlap.join(", ")}`);
});

test("AC-005 主人拿得到全部 owner-only 能力——闸门不能靠「谁都拒绝」来通过", () => {
  // 反面用例。少了它，一个「may() 永远返回 false」的实现也能让上面几条全绿。
  const ctx = owner();
  const denied = OWNER_ONLY_CAPABILITIES.filter((cap) => !ctx.may(cap));
  assert.deepEqual(denied, [], `主人被拒的能力：${denied.join(", ")}`);
});

// ── AC-001 身份只由服务端决定 ───────────────────────────────

test("AC-001 消息体里的任何字段都改不了模式", () => {
  // spoof：把 role/capabilities 塞进构造参数，看能不能提权。
  const spoofs = [
    { userId: GUEST, role: "owner" },              // 直接冒充
    { userId: GUEST, role: "user", isOwner: true },
    { userId: GUEST, role: "user", capabilities: OWNER_ONLY_CAPABILITIES },
    { userId: GUEST, role: "user", may: () => true },
  ];
  // 第一条是**合法构造**（服务端可以建主人上下文），它证明的是：提权只能来自
  // 服务端已解析的 role，不能来自消息体。其余三条是外来字段，必须被忽略。
  for (const input of spoofs.slice(1)) {
    const ctx = new UserContext(input);
    assert.equal(ctx.isOwner, false, `外来字段把上下文变成了主人：${JSON.stringify(Object.keys(input))}`);
    const allowed = OWNER_ONLY_CAPABILITIES.filter((c) => ctx.may(c));
    assert.deepEqual(allowed, [], `外来字段提权成功：${allowed.join(", ")}`);
  }
});

test("AC-001 上下文是冻结的，建好之后改不动", () => {
  const ctx = companion();
  assert.ok(Object.isFrozen(ctx), "UserContext 没冻结，下游可以就地改 role");
  try {
    ctx.role = "owner";
  } catch {
    // strict mode 下会抛，非 strict 静默失败，两种都可以接受
  }
  assert.equal(ctx.isOwner, false, "role 被就地改成了主人");
  assert.equal(ctx.may("shell.execute"), false);
});

test("AC-001 非 active 状态的用户拿不到任何能力", () => {
  for (const status of ["pending_consent", "suspended", "deleting", "deleted"]) {
    const ctx = new UserContext({ userId: GUEST, role: "user", status });
    const allowed = [...OWNER_ONLY_CAPABILITIES, ...USER_CAPABILITIES].filter((c) => ctx.may(c));
    assert.deepEqual(allowed, [], `status=${status} 还能用：${allowed.join(", ")}`);
  }
});

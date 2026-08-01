"use strict";

// CB9-130 跨用户/跨模式能力矩阵与回归防线（AC-005，method=security）
//
// CB9-100 验的是能力模型本身（一个 Companion 拿不到 owner-only 能力）。
// 这一条要的是**矩阵**：把 actor × capability 全网格枚举一遍，再加上跨用户
// 数据域。差别在于——单点断言在新增一个 actor（比如"受邀管理员""只读观察者"）
// 时依然全绿，而那个新 actor 可能默认继承了不该有的能力。
//
// 网格是从能力表**动态生成**的，不是手写清单。加一项能力、加一个 status，
// 网格自动变大，不用改测试。这是「回归防线」和「一批断言」的区别。

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  OWNER_ONLY_CAPABILITIES,
  USER_CAPABILITIES,
  UserContext,
} = require("../src/services/users/user-context");
const {
  buildBoundedContext,
  stableSessionKey,
} = require("../src/services/companion/companion-session-context");

const SECRET = "z".repeat(32);
const ALICE = `usr_${"a".repeat(24)}`;
const BOB = `usr_${"b".repeat(24)}`;
const OWNER = `usr_${"o".repeat(24)}`;

// 所有 actor 形态。新增角色/状态时在这里加一行，网格自动覆盖。
const ACTORS = [
  { name: "owner:active", ctx: () => new UserContext({ userId: OWNER, role: "owner", status: "active" }), owner: true },
  { name: "user:active", ctx: () => new UserContext({ userId: ALICE, role: "user", status: "active" }), owner: false },
  { name: "user:pending_consent", ctx: () => new UserContext({ userId: ALICE, role: "user", status: "pending_consent" }), owner: false, inert: true },
  { name: "user:suspended", ctx: () => new UserContext({ userId: ALICE, role: "user", status: "suspended" }), owner: false, inert: true },
  { name: "user:deleting", ctx: () => new UserContext({ userId: ALICE, role: "user", status: "deleting" }), owner: false, inert: true },
  { name: "user:deleted", ctx: () => new UserContext({ userId: ALICE, role: "user", status: "deleted" }), owner: false, inert: true },
];

const ALL_CAPABILITIES = [...OWNER_ONLY_CAPABILITIES, ...USER_CAPABILITIES];

test("AC-005 能力矩阵：actor × capability 全网格，逐格核对", () => {
  const violations = [];
  for (const actor of ACTORS) {
    const ctx = actor.ctx();
    for (const cap of ALL_CAPABILITIES) {
      const got = ctx.may(cap);
      // 期望值由规则推出，不是查表：
      //   非 active 的任何人 → 全 false
      //   owner            → 全 true
      //   active 普通用户   → 仅 USER_CAPABILITIES
      const want = actor.inert
        ? false
        : actor.owner
          ? true
          : USER_CAPABILITIES.includes(cap);
      if (got !== want) {
        violations.push(`${actor.name} × ${cap}: got=${got} want=${want}`);
      }
    }
  }
  assert.deepEqual(violations, [], `能力矩阵有 ${violations.length} 格不符：\n${violations.join("\n")}`);
});

test("AC-005 网格规模随能力表增长——不是一张手写的固定清单", () => {
  const cells = ACTORS.length * ALL_CAPABILITIES.length;
  assert.equal(cells, 6 * 21, `网格 ${cells} 格；能力表变了就该变，这条只是把规模钉出来`);
  assert.ok(ALL_CAPABILITIES.length >= 21, "能力表被缩小了，先确认不是把闸门删了");
});

test("AC-005 六类高危面在矩阵里对每个非主人 actor 都是拒绝", () => {
  const HIGH_RISK = {
    Workspace: ["workspace.read", "workspace.write"],
    Tool: ["project.tool"],
    Shell: ["shell.execute"],
    MCP: ["mcp.invoke"],
    Approval: ["shell.execute"],
    Thread: ["codex.turn", "claudecode.turn"],
  };
  for (const actor of ACTORS.filter((a) => !a.owner)) {
    const ctx = actor.ctx();
    for (const [group, caps] of Object.entries(HIGH_RISK)) {
      for (const cap of caps) {
        assert.equal(ctx.may(cap), false, `${actor.name} 拿到了 ${group} 的 ${cap}`);
      }
    }
  }
});

// ── 跨用户数据域（矩阵的另一个轴）────────────────────────────

test("AC-005 跨用户数据域：A 的上下文里不出现 B 的任何一行", () => {
  const mixed = {
    turns: [{ user_scope: BOB, text: "BOB 的对话" }, { user_scope: ALICE, text: "ALICE 的对话" }],
    acceptedFacts: [{ user_scope: BOB, fact: "BOB 的事实" }],
    unresolvedItems: [{ user_scope: BOB, item: "BOB 的待办" }],
    timeline: [{ user_scope: BOB, event: "BOB 的事件" }],
  };
  for (const [me, other] of [[ALICE, "BOB"], [BOB, "ALICE"]]) {
    const ctx = buildBoundedContext({
      userScope: me, sessionKey: stableSessionKey(me, SECRET), ...mixed,
    });
    assert.ok(!JSON.stringify(ctx).includes(`${other} 的`), `${me} 的上下文里出现了 ${other} 的数据`);
  }
});

test("AC-005 Companion 上下文里不得出现 owner-only 能力名", () => {
  // 上下文会被送进模型。即使模型碰不到工具，把 owner-only 能力名写进去也是
  // 在教它去试——而且 Timeline/证据里会留下这些词。
  const ctx = buildBoundedContext({
    userScope: ALICE, sessionKey: stableSessionKey(ALICE, SECRET),
    turns: [{ user_scope: ALICE, text: "普通对话" }],
  });
  const dumped = JSON.stringify(ctx);
  for (const cap of OWNER_ONLY_CAPABILITIES) {
    assert.ok(!dumped.includes(cap), `Companion 上下文里出现了 owner-only 能力名 ${cap}`);
  }
  assert.equal(ctx.mode, "COMPANION");
});

test("AC-005 主人和 Companion 的 session 命名空间不重叠", () => {
  // Companion 的 key 前缀是 comp_；主人走的是 workspaceId:accountId:senderId
  // 这套 binding key。两者形状不同，不可能互相冒充。
  const compKey = stableSessionKey(ALICE, SECRET);
  assert.ok(compKey.startsWith("comp_"));
  assert.ok(!compKey.includes(":"), "Companion key 撞进了主人 binding key 的形状");
});

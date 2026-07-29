"use strict";

// 「yes / always / 无」这三条口令直接决定一条命令要不要在主人的机器上真的跑，
// 而「always」还会把命令前缀写进工作区永久白名单。dispatchChannelCommand 里
// 它们原本没有任何主人判断。
//
// 今天这还伤不到人：访客走的是 provider router，根本拿不到 Codex 线程，也就
// 永远没有 pendingApproval。但「让前 5 个人也走我的 Codex」一旦做成，访客就会
// 收到属于他自己那条线程的审批提示——他回一个「yes」，命令就在主人机器上执行了。
// 闸门必须先于那件事存在。
//
// 这个套件同时钉死一个反向的坑：admitInboundMessage 在多用户准入整个关掉时返回
// 的是 userContext: null（route:"owner"）。如果闸门写成「没有 context 就拒绝」，
// 单用户形态下主人自己的审批会被全部挡掉——那是把一个安全补丁变成一次故障。

const assert = require("node:assert/strict");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { UserContext } = require("../src/services/users/user-context");

const OWNER_ID = "usr_owner_000000000000000000";
const GUEST_ID = "usr_guest_000000000000000000";

function contextFor(role, userId) {
  return new UserContext({ userId, role, status: "active" });
}

// 真的调 app.js 里那个 dispatchChannelCommand，不是抄一份。命令名固定是审批那
// 三条，所以 switch 只会走到被测的那个分支，其余依赖不需要存在。
function runApprovalCommand({ activeUserContext, name }) {
  const sent = [];
  let approvalHandled = false;
  const self = {
    activeUserContext,
    channelAdapter: {
      async sendText(payload) {
        sent.push(payload);
      },
    },
    async handleApprovalCommand() {
      approvalHandled = true;
    },
  };
  const normalized = { senderId: "wx_sender", contextToken: "ctx_1" };
  return CyberbossApp.prototype.dispatchChannelCommand
    .call(self, normalized, { name })
    .then(() => ({ approvalHandled, sent }));
}

for (const name of ["yes", "always", "no"]) {
  test(`访客发「${name}」批不动主人机器上的命令`, async () => {
    const { approvalHandled, sent } = await runApprovalCommand({
      activeUserContext: contextFor("user", GUEST_ID),
      name,
    });
    assert.equal(approvalHandled, false, "访客不能到达审批处理");
    assert.equal(sent.length, 1);
    assert.match(sent[0].text, /只有主人能批准/);
  });

  test(`主人发「${name}」照常放行`, async () => {
    const { approvalHandled, sent } = await runApprovalCommand({
      activeUserContext: contextFor("owner", OWNER_ID),
      name,
    });
    assert.equal(approvalHandled, true, "主人必须批得动");
    assert.equal(sent.length, 0);
  });

  test(`单用户形态（context 为 null）发「${name}」不能被误伤`, async () => {
    const { approvalHandled, sent } = await runApprovalCommand({
      activeUserContext: null,
      name,
    });
    assert.equal(approvalHandled, true, "准入关掉时全机只有主人，不能挡他");
    assert.equal(sent.length, 0);
  });
}

test("闸门用的是 shell.execute，而不是随便一个主人能力", () => {
  // 批准执行一条命令，语义上就是 shell.execute。挑错能力名的话，闸门看起来在
  // 工作，实际拦的是另一件事。
  const guest = contextFor("user", GUEST_ID);
  const owner = contextFor("owner", OWNER_ID);
  assert.equal(guest.may("shell.execute"), false);
  assert.equal(owner.may("shell.execute"), true);
  // 访客确实有别的能力——所以这个断言不是「访客什么都不能做」的同义反复。
  assert.equal(guest.may("chat.turn"), true);
});

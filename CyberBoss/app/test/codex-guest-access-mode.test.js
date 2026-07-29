"use strict";

// 访客档（guest-chat）：让前 5 个人也走主人的 Codex，但拿不到主人的执行权限。
//
// 2026-07-29 在生产机上实测过的两条硬事实，这个套件把它们钉住：
//  * bwrap 因为 Ubuntu 24.04 的 AppArmor userns 限制根本起不来，带沙箱的命令
//    一律 exitCode 1、0 字节——失败关闭，不会退回裸跑。
//  * dangerFullAccess 绕过 bwrap 直接裸跑（实测退出码 0、真的读到了文件）。
//
// 所以「沙箱坏着」不等于「什么都跑不了」，full-access 依然是真刀。访客档必须
// 显式写死 readOnly，而不是依赖环境恰好坏着——bwrap 坏着要安全，哪天装上
// bubblewrap 修好了也要安全。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createCodexRuntimeAdapter } = require("../src/adapters/runtime/codex");
const { CodexRpcClient } = require("../src/adapters/runtime/codex/rpc-client");

function clientWithCapture() {
  const client = new CodexRpcClient({
    endpoint: "ws://127.0.0.1:8765",
    extraWritableRoots: ["/workspace/shared"],
  });
  const calls = [];
  client.sendRequest = async (method, params) => {
    calls.push({ method, params });
    return { result: { turn: { id: "turn-1" } } };
  };
  return { client, calls };
}

async function turnWith(accessMode) {
  const { client, calls } = clientWithCapture();
  await client.sendUserMessage({
    threadId: "thread-1",
    text: "在吗",
    accessMode,
    workspaceRoot: "/workspace/project",
  });
  return calls[0].params;
}

test("访客档给的是只读沙箱，而且不给网络", async () => {
  const params = await turnWith("guest-chat");
  assert.deepEqual(params.sandboxPolicy, {
    type: "readOnly",
    networkAccess: false,
  });
});

test("访客档不把任何目录标成可写", async () => {
  const params = await turnWith("guest-chat");
  // workspaceRoot 和 extraWritableRoots 都传了，但访客档一个都不该采纳。
  assert.equal(Object.hasOwn(params.sandboxPolicy, "writableRoots"), false);
});

test("访客档的审批策略是 never，不是 on-request", async () => {
  // on-request 会把审批提示发回给发起那条线程的人——也就是访客自己，等于让他
  // 批准自己的命令。never 让 Codex 直接放弃执行，不问任何人。
  const params = await turnWith("guest-chat");
  assert.equal(params.approvalPolicy, "never");
});

test("主人那条路一点没变", async () => {
  const params = await turnWith("default");
  assert.equal(params.approvalPolicy, "on-request");
  assert.deepEqual(params.sandboxPolicy, {
    type: "workspaceWrite",
    writableRoots: ["/workspace/project", "/workspace/shared"],
    networkAccess: true,
  });
});

test("full-access 仍然是真刀——所以它绝不能落到访客手里", async () => {
  // 这条断言的意义不是「full-access 能用」，而是记住它有多重：实测中它绕过
  // bwrap 直接裸跑。任何把访客路由到这一档的改动都必须被视为事故。
  const params = await turnWith("full-access");
  assert.deepEqual(params.sandboxPolicy, { type: "dangerFullAccess" });
});

test("认不出来的档位一律退回主人那档，不会静默变成访客档", async () => {
  // 反向的坑：如果拼错的档位悄悄落进访客档，主人会突然失去写权限而且没人报错。
  const params = await turnWith("guest_chat");
  assert.equal(params.sandboxPolicy.type, "workspaceWrite");
});

test("accessMode 本身不会被当成协议参数发出去", async () => {
  const params = await turnWith("guest-chat");
  assert.equal(Object.hasOwn(params, "accessMode"), false);
});

// ——————————————————————————————————————————————————————————
// 上面那些只证明 rpc-client 收到 accessMode 之后会做对的事。真正会出事的地方
// 在更上一层：适配器的 sendTurn 是按名字解构的，漏掉 accessMode 的话上层传了也
// 到不了 rpc-client，而且一声不响——访客照样拿到主人那档权限，上面 7 条测试全绿。
// 这一条测的是**可达性**：accessMode 真的从 sendTurn 走到了 sendUserMessage。
// ——————————————————————————————————————————————————————————
test("accessMode 真的能从适配器走到 rpc-client（不是写了就等于到得了）", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb-guest-"));
  const adapter = createCodexRuntimeAdapter({
    sessionsFile: path.join(dir, "sessions.json"),
    codexEndpoint: "ws://127.0.0.1:8765",
    stateDir: dir,
  });

  // createClient() 返回的就是适配器内部那一个 client 实例，所以在它身上打桩等于
  // 截住了真实调用链，而不是换掉一条假的。
  const client = adapter.createClient();
  let captured = null;
  client.connect = async () => {};
  client.initialize = async () => {};
  client.listModels = async () => ({ result: { data: [] } });
  client.isReady = true;
  client.isTransportReady = () => true;
  client.startThread = async () => ({ result: { thread: { id: "thread-guest" } } });
  client.sendUserMessage = async (args) => {
    captured = args;
    return { result: { turn: { id: "turn-guest" } } };
  };

  await adapter.sendTurn({
    bindingKey: "ws|acct|guest",
    workspaceRoot: "/workspace/project",
    text: "在吗",
    accessMode: "guest-chat",
  });

  assert.ok(captured, "sendUserMessage 应该被调到");
  assert.equal(
    captured.accessMode,
    "guest-chat",
    "accessMode 在适配器那一层被丢掉了——访客会拿到主人那档执行权限",
  );

  fs.rmSync(dir, { recursive: true, force: true });
});

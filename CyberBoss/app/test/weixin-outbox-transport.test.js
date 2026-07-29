"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createWeixinChannelAdapter } = require("../src/adapters/channel/weixin");
const {
  saveWeixinAccount,
} = require("../src/adapters/channel/weixin/account-store");

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb230-weixin-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function fixtureConfig(directory, baseUrl) {
  const stateDir = path.join(directory, "state");
  return {
    stateDir,
    accountsDir: path.join(stateDir, "accounts"),
    syncBufferDir: path.join(stateDir, "sync-buffers"),
    weixinConfigFile: path.join(stateDir, "weixin-config.json"),
    weixinBaseUrl: baseUrl,
    weixinCdnBaseUrl: baseUrl,
    accountId: "fixture-account",
    workspaceId: "fixture-workspace",
    allowedUserIds: ["fixture-user"],
    maxInputBytes: 32_768,
  };
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  return `http://127.0.0.1:${address.port}/`;
}

test("durable single-chunk transport preserves text and stable provider client id", async (t) => {
  const directory = temporaryDirectory(t);
  const requests = [];
  const server = http.createServer((request, response) => {
    let raw = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      raw += chunk;
    });
    request.on("end", () => {
      requests.push(JSON.parse(raw));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        ret: 0,
        errcode: 0,
        message_id: "fixture-receipt",
      }));
    });
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);
  const config = fixtureConfig(directory, baseUrl);
  saveWeixinAccount(config, config.accountId, {
    token: "fixture-token",
    baseUrl,
    userId: "fixture-bot",
  });
  const adapter = createWeixinChannelAdapter(config);
  const clientId = "cb-outbox-0123456789abcdef0123456789abcdef";
  const exactText = "[1/2] exact durable chunk。\n";
  const receipt = await adapter.sendTextChunk({
    userId: "fixture-user",
    text: exactText,
    contextToken: "fixture-context",
    clientId,
  });

  assert.equal(receipt.ret, 0);
  assert.equal(receipt.errcode, 0);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].msg.client_id, clientId);
  assert.equal(requests[0].msg.context_token, "fixture-context");
  assert.equal(requests[0].msg.item_list[0].text_item.text, exactText);
});

test("durable transport rejects random ids and oversized chunks before provider call", async (t) => {
  const directory = temporaryDirectory(t);
  let requests = 0;
  const server = http.createServer((_request, response) => {
    requests += 1;
    response.writeHead(200, { "content-type": "application/json" });
    response.end('{"ret":0}');
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);
  const config = fixtureConfig(directory, baseUrl);
  saveWeixinAccount(config, config.accountId, {
    token: "fixture-token",
    baseUrl,
  });
  const adapter = createWeixinChannelAdapter(config);

  await assert.rejects(
    () =>
      adapter.sendTextChunk({
        userId: "fixture-user",
        text: "valid",
        contextToken: "fixture-context",
        clientId: "cb-random",
      }),
    (error) =>
      error.code === "WEIXIN_STABLE_CLIENT_ID_REQUIRED"
      && error.outcomeKnown === true,
  );
  await assert.rejects(
    () =>
      adapter.sendTextChunk({
        userId: "fixture-user",
        text: "x".repeat(3_801),
        contextToken: "fixture-context",
        clientId: "cb-outbox-0123456789abcdef0123456789abcdef",
      }),
    (error) =>
      error.code === "WEIXIN_OUTBOX_CHUNK_INVALID"
      && error.outcomeKnown === true,
  );
  assert.equal(requests, 0);
});

test("HTTP 503 is an explicit known failure with bounded retry metadata", async (t) => {
  const directory = temporaryDirectory(t);
  const server = http.createServer((_request, response) => {
    response.writeHead(503, {
      "content-type": "application/json",
      "retry-after": "2",
    });
    response.end('{"error":"fixture unavailable"}');
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);
  const config = fixtureConfig(directory, baseUrl);
  saveWeixinAccount(config, config.accountId, {
    token: "fixture-token",
    baseUrl,
  });
  const adapter = createWeixinChannelAdapter(config);

  await assert.rejects(
    () =>
      adapter.sendTextChunk({
        userId: "fixture-user",
        text: "fixture",
        contextToken: "fixture-context",
        clientId: "cb-outbox-0123456789abcdef0123456789abcdef",
      }),
    (error) =>
      error.code === "WEIXIN_HTTP_ERROR"
      && error.status === 503
      && error.outcomeKnown === true
      && error.retryAfterMs === 2_000,
  );
});

// ── 真实响应形状 ────────────────────────────────────────────
//
// 上面每一条 fixture 回的都是 `{ret:0, errcode:0, message_id:"…"}`。
// iLink **从来不这么回**。2026-07-29 在生产上真发一条，拿到的是：
//
//     {"message_id": 7488003379736578000}
//
// 没有 ret，没有 errcode，message_id 还是个数字不是字符串。
//
// 这个差别不是细节，它让这套系统在生产上 100% 失效了整整一天：
// normalizeProviderConfirmation 只认 ret===0，于是每一条**真的送达**的消息
// 都被判成 ambiguous、第一次尝试就 failed_terminal。用户收得到回复，账本却
// 全是"发送失败"，后台显示"没答上"。而套件 683/683 全绿——因为它测的是我
// 自己编的形状，不是渠道真给的形状。
//
// 所以下面这几条钉的是**观测到的**契约，不是想象中的契约。

const {
  normalizeProviderConfirmation,
} = require("../src/services/outbox/durable-outbox");

test("iLink 真实成功响应（只有 message_id，没有 ret/errcode）必须判为已送达", async (t) => {
  const directory = temporaryDirectory(t);
  const server = http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    // 一个字节都不改，就是生产上抓到的那一行。
    response.end('{"message_id":7488003379736578000}');
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);
  const config = fixtureConfig(directory, baseUrl);
  saveWeixinAccount(config, config.accountId, {
    token: "fixture-token",
    baseUrl,
    userId: "fixture-bot",
  });

  const adapter = createWeixinChannelAdapter(config);
  const clientId = "cb-outbox-0123456789abcdef0123456789abcdef";
  const response = await adapter.sendTextChunk({
    userId: "fixture-user",
    text: "真实形状",
    contextToken: "fixture-context",
    clientId,
  });

  // 第一层：传输层不能因为缺 ret 就抛错（它本来就没抛，和参考实现一致）。
  assert.equal(response.ret, undefined);
  assert.equal(response.errcode, undefined);
  assert.ok(response.message_id, "provider 的回执就是 message_id");

  // 第二层——真正出过事的那一层：确认器必须认这个形状。
  const confirmation = normalizeProviderConfirmation(response, clientId);
  assert.equal(confirmation.confirmed, true, "有 message_id 就是送达了，不能判成「不知道」");
  assert.equal(confirmation.clientId, clientId);
  assert.ok(confirmation.receiptHash, "必须留下可核对的回执");
});

test("既没有状态码也没有 message_id 时，仍然判为不知道——这条守卫不许被放宽", () => {
  const clientId = "cb-outbox-0123456789abcdef0123456789abcdef";
  // 放宽 ret 的判定不等于什么都收下。真的没有任何回执时，必须继续判 ambiguous，
  // 因为 ambiguous 不重试正是为了不把同一句话发两遍。
  assert.throws(
    () => normalizeProviderConfirmation({}, clientId),
    /OUTBOX_CONFIRMATION_REQUIRED/,
  );
  assert.throws(
    () => normalizeProviderConfirmation({ message_id: "" }, clientId),
    /OUTBOX_CONFIRMATION_REQUIRED/,
  );
  assert.throws(
    () => normalizeProviderConfirmation(null, clientId),
    /OUTBOX_CONFIRMATION_REQUIRED/,
  );
});

test("明确的失败状态码仍然是失败，不能被 message_id 盖过去", () => {
  const clientId = "cb-outbox-0123456789abcdef0123456789abcdef";
  for (const bad of [
    { ret: -1, message_id: "x" },
    { errcode: 40001, message_id: "x" },
    { ret: 0, errcode: 40001, message_id: "x" },
  ]) {
    assert.throws(
      () => normalizeProviderConfirmation(bad, clientId),
      /OUTBOX_CONFIRMATION_REQUIRED/,
      `${JSON.stringify(bad)} 必须仍然判失败`,
    );
  }
});

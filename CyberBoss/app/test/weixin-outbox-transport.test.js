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

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createWeixinChannelAdapter } = require("../src/adapters/channel/weixin");
const { saveWeixinAccount } = require("../src/adapters/channel/weixin/account-store");
const {
  SyncBufferStoreError,
  commitSyncBuffer,
  loadSyncBuffer,
  resolveSyncBufferPath,
} = require("../src/adapters/channel/weixin/sync-buffer-store");

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb210-cursor-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function fixtureConfig(directory, baseUrl = "http://127.0.0.1:1") {
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
    allowedUserIds: ["fixture-sender"],
    maxInputBytes: 32768,
  };
}

test("cursor commit is atomic, compare-and-set and monotonic for numeric cursors", (t) => {
  const directory = temporaryDirectory(t);
  const config = fixtureConfig(directory);
  assert.equal(loadSyncBuffer(config, config.accountId), "");
  assert.deepEqual(
    commitSyncBuffer(config, config.accountId, {
      expected: "",
      candidate: "10",
    }),
    { previous: "", committed: "10", changed: true },
  );
  assert.equal(loadSyncBuffer(config, config.accountId), "10");
  const cursorPath = resolveSyncBufferPath(config, config.accountId);
  assert.equal(fs.statSync(cursorPath).mode & 0o777, 0o600);
  assert.equal(fs.statSync(path.dirname(cursorPath)).mode & 0o777, 0o700);
  assert.equal(
    fs.readdirSync(path.dirname(cursorPath)).filter((name) => name.endsWith(".tmp")).length,
    0,
  );
  assert.equal(fs.existsSync(`${cursorPath}.lock`), false);

  assert.throws(
    () => commitSyncBuffer(config, config.accountId, {
      expected: "9",
      candidate: "11",
    }),
    (error) =>
      error instanceof SyncBufferStoreError
      && error.code === "CURSOR_COMPARE_AND_SET_FAILED",
  );
  assert.throws(
    () => commitSyncBuffer(config, config.accountId, {
      expected: "10",
      candidate: "9",
    }),
    (error) =>
      error instanceof SyncBufferStoreError
      && error.code === "CURSOR_REGRESSION",
  );
  assert.deepEqual(
    commitSyncBuffer(config, config.accountId, {
      expected: "10",
      candidate: "10",
    }),
    { previous: "10", committed: "10", changed: false },
  );
});

test("cursor commit lock rejects a live writer and recovers a killed writer", (t) => {
  const directory = temporaryDirectory(t);
  const config = fixtureConfig(directory);
  const cursorPath = resolveSyncBufferPath(config, config.accountId);
  const lockPath = `${cursorPath}.lock`;
  fs.mkdirSync(lockPath, { mode: 0o700 });
  fs.writeFileSync(
    path.join(lockPath, "owner.json"),
    JSON.stringify({ pid: process.pid, token: "active" }),
    { encoding: "utf8", mode: 0o600 },
  );
  assert.throws(
    () => commitSyncBuffer(config, config.accountId, {
      expected: "",
      candidate: "1",
    }),
    (error) =>
      error instanceof SyncBufferStoreError
      && error.code === "CURSOR_COMMIT_LOCKED",
  );
  fs.unlinkSync(path.join(lockPath, "owner.json"));
  fs.rmdirSync(lockPath);

  fs.mkdirSync(lockPath, { mode: 0o700 });
  fs.writeFileSync(
    path.join(lockPath, "owner.json"),
    JSON.stringify({ pid: 99999999, token: "stale" }),
    { encoding: "utf8", mode: 0o600 },
  );
  assert.deepEqual(
    commitSyncBuffer(config, config.accountId, {
      expected: "",
      candidate: "1",
    }),
    { previous: "", committed: "1", changed: true },
  );
  assert.equal(loadSyncBuffer(config, config.accountId), "1");
  assert.equal(fs.existsSync(lockPath), false);
  assert.equal(
    fs.readdirSync(path.dirname(cursorPath))
      .filter((name) => name.includes(".lock.stale.")).length,
    0,
  );
});

test("cursor store rejects symlinks and oversized values", (t) => {
  const directory = temporaryDirectory(t);
  const config = fixtureConfig(directory);
  fs.mkdirSync(config.syncBufferDir, { recursive: true });
  const outside = path.join(directory, "outside.txt");
  fs.writeFileSync(outside, "outside", "utf8");
  fs.symlinkSync(outside, resolveSyncBufferPath(config, config.accountId));
  assert.throws(
    () => loadSyncBuffer(config, config.accountId),
    (error) =>
      error instanceof SyncBufferStoreError
      && error.code === "CURSOR_FILE_INVALID",
  );
  fs.unlinkSync(resolveSyncBufferPath(config, config.accountId));
  assert.throws(
    () => commitSyncBuffer(config, config.accountId, {
      expected: "",
      candidate: "x".repeat(4097),
    }),
    (error) =>
      error instanceof SyncBufferStoreError
      && error.code === "CURSOR_INVALID",
  );
});

test("WeChat fetch returns a candidate without committing cursor or context state", async (t) => {
  const directory = temporaryDirectory(t);
  const requests = [];
  const server = http.createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      requests.push(JSON.parse(body));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        ret: 0,
        errcode: 0,
        get_updates_buf: "cursor-1",
        msgs: [{
          message_type: 1,
          message_id: "provider-message-1",
          from_user_id: "fixture-sender",
          context_token: "fixture-context-token",
          create_time_ms: 1700000000000,
          item_list: [{ type: 1, text_item: { text: "fixture message" } }],
        }],
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const address = server.address();
  const config = fixtureConfig(directory, `http://127.0.0.1:${address.port}`);
  saveWeixinAccount(config, config.accountId, {
    token: "fixture-token",
    baseUrl: config.weixinBaseUrl,
    userId: "fixture-bot",
  });
  const adapter = createWeixinChannelAdapter(config);
  const fetched = await adapter.fetchUpdates({
    syncBuffer: "",
    timeoutMs: 2000,
  });

  assert.equal(fetched.committedCursor, "");
  assert.equal(fetched.candidateCursor, "cursor-1");
  assert.equal(fetched.messages.length, 1);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].get_updates_buf, "");
  assert.equal(adapter.loadSyncBuffer(), "");
  assert.deepEqual(adapter.getKnownContextTokens(), {});

  const committed = adapter.commitCandidateCursor({
    expectedCursor: "",
    candidateCursor: fetched.candidateCursor,
  });
  assert.equal(committed.changed, true);
  assert.equal(adapter.loadSyncBuffer(), "cursor-1");
  assert.deepEqual(adapter.getKnownContextTokens(), {});
});

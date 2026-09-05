const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");
const net = require("node:net");
const path = require("node:path");
const {
  findAvailablePort,
  httpReachable,
  inspectExistingServer,
  launchdPid,
  launchdEnvironment,
  launchdSubmitArgs,
  runtimeAlive,
} = require("../src/runtime/server.cjs");

test("finds a loopback port and detects an HTTP listener", async () => {
  const port = await findAvailablePort(0);
  const server = http.createServer((_request, response) => response.end("ok"));
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  assert.equal(await httpReachable(port), true);
  await new Promise((resolve) => server.close(resolve));
});

test("reports child and adopted runtime liveness", () => {
  assert.equal(runtimeAlive({ child: { exitCode: null } }), true);
  assert.equal(runtimeAlive({ child: { exitCode: 0 } }), false);
  assert.equal(runtimeAlive({ adopted: true, pid: process.pid }), true);
});

test("submits the stable CLI as a transient launchd service", () => {
  assert.deepEqual(launchdSubmitArgs({
    label: "com.electron.kimi-code.backend",
    cliPath: "/Users/example/.kimi-code/bin/kimi",
    port: 58627,
    environment: {
      HOME: "/Users/example",
      KIMI_CODE_HOME: "/Users/example/.kimi-code",
    },
  }), [
    "submit",
    "-l", "com.electron.kimi-code.backend",
    "-o", "/dev/null",
    "-e", "/dev/null",
    "--",
    "/usr/bin/env", "-i",
    "HOME=/Users/example",
    "KIMI_CODE_HOME=/Users/example/.kimi-code",
    "/Users/example/.kimi-code/bin/kimi",
    "web", "--no-open", "--host", "127.0.0.1", "--port", "58627",
  ]);
});

test("does not pass unrelated app secrets into the launchd backend", () => {
  assert.deepEqual(launchdEnvironment({
    HOME: "/Users/example",
    PATH: "/usr/bin:/bin",
    SECRET_TOKEN: "must-not-leak",
  }, "/Users/example/.kimi-code"), {
    HOME: "/Users/example",
    PATH: "/usr/bin:/bin",
    KIMI_CODE_HOME: "/Users/example/.kimi-code",
    NO_COLOR: "1",
  });
});

// ── 回归：2026-09-06 「无法启动 Kimi Code Desktop」 ─────────────────────
// 三个 bug 同源：lsof 的失败被当成了「端口有问题」。
// 实测本机（挂着 smbfs）同一条 lsof 查询连跑 5 次 = 0.27/3.53/0.94/0.27/0.38 秒，
// 而当时超时写死 3 秒 —— 每开一次 App 掷一次骰子。

test("free port reports cleanly instead of surfacing a raw lsof failure", async () => {
  // lsof 查无匹配时退出码是 1、stderr 为空。那是「没有人占用」，不是「查询失败」。
  // 旧代码把它当异常，用户看到的就是 `Command failed: /usr/sbin/lsof ...`。
  const port = await findAvailablePort(0);
  const result = await inspectExistingServer({
    port,
    cliPath: "/nonexistent/kimi",
    homeDir: "/nonexistent",
  });
  assert.notEqual(result.status, "adoptable");
  assert.doesNotMatch(result.reason, /Command failed/);
  assert.doesNotMatch(result.reason, /lsof/);
});

test("a foreign program on the fixed port is occupied, never a hard conflict", async () => {
  // occupied → 调用方换端口继续开；conflict → 拒绝启动。
  // 只有「另一个 Kimi GUI 在管这个后台」配得上 conflict，别的都不配。
  const port = await findAvailablePort(0);
  const server = net.createServer();
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  try {
    const result = await inspectExistingServer({
      port,
      cliPath: path.join("/nonexistent", "kimi"),
      homeDir: "/nonexistent",
    });
    assert.equal(result.status, "occupied");
    assert.notEqual(result.status, "conflict");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("launchdPid returns 0 for an unknown label instead of throwing", async () => {
  assert.equal(await launchdPid("com.example.definitely-not-loaded.7f3a91"), 0);
  assert.equal(await launchdPid(null), 0);
});

test("a non-darwin platform degrades instead of blocking startup", async () => {
  const result = await inspectExistingServer({
    port: 1,
    cliPath: "/nonexistent/kimi",
    homeDir: "/nonexistent",
    platform: "linux",
  });
  assert.equal(result.status, "occupied");
});

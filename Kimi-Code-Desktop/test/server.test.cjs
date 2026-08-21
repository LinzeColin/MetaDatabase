const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");
const {
  findAvailablePort,
  httpReachable,
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

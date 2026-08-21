const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");
const { findAvailablePort, httpReachable } = require("../src/runtime/server.cjs");

test("finds a loopback port and detects an HTTP listener", async () => {
  const port = await findAvailablePort(0);
  const server = http.createServer((_request, response) => response.end("ok"));
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  assert.equal(await httpReachable(port), true);
  await new Promise((resolve) => server.close(resolve));
});

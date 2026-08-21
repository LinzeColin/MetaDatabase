const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function listenOnce(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen({ host: "127.0.0.1", port, exclusive: true }, () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

async function findAvailablePort(preferred = 58627) {
  try {
    return await listenOnce(preferred);
  } catch (error) {
    if (error.code !== "EADDRINUSE") throw error;
    return listenOnce(0);
  }
}

function httpReachable(port) {
  return new Promise((resolve) => {
    const request = http.get({ host: "127.0.0.1", port, path: "/", timeout: 750 }, (response) => {
      response.resume();
      resolve(true);
    });
    request.once("timeout", () => { request.destroy(); resolve(false); });
    request.once("error", () => resolve(false));
  });
}

async function waitForServer({ child, port, timeoutMs = 30000 }) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.launchError) throw child.launchError;
    if (child.exitCode !== null) throw new Error(`Kimi Code server exited with code ${child.exitCode}`);
    if (await httpReachable(port)) return;
    await delay(250);
  }
  throw new Error(`Kimi Code server did not become ready on port ${port}`);
}

async function readServerToken(homeDir, timeoutMs = 5000) {
  const tokenFile = path.join(homeDir, "server.token");
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const token = fs.readFileSync(tokenFile, "utf8").trim();
      if (token) return token;
    } catch {
      // Kimi creates the token after the local service starts.
    }
    await delay(100);
  }
  throw new Error(`Kimi Code did not create ${tokenFile}`);
}

function captureOutput(stream, target) {
  if (!stream) return;
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    target.text = (target.text + chunk).slice(-12000);
  });
}

async function startKimiServer({ cliPath, homeDir, preferredPort = 58627, env = process.env }) {
  const port = await findAvailablePort(preferredPort);
  fs.mkdirSync(homeDir, { recursive: true });
  const output = { text: "" };
  const child = spawn(cliPath, ["web", "--no-open", "--host", "127.0.0.1", "--port", String(port)], {
    env: { ...env, KIMI_CODE_HOME: homeDir, NO_COLOR: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    detached: false,
  });
  child.launchError = null;
  child.once("error", (error) => { child.launchError = error; });
  captureOutput(child.stdout, output);
  captureOutput(child.stderr, output);
  try {
    await waitForServer({ child, port });
    const token = await readServerToken(homeDir);
    return { child, homeDir, output, port, token };
  } catch (error) {
    if (child.exitCode === null) child.kill();
    const diagnostic = output.text.trim();
    if (diagnostic) error.message += `\n${diagnostic.slice(-2000)}`;
    throw error;
  }
}

async function stopKimiServer(runtime, timeoutMs = 5000) {
  const child = runtime?.child;
  if (!child || child.exitCode !== null) return;
  const exited = new Promise((resolve) => child.once("exit", resolve));
  child.kill("SIGTERM");
  await Promise.race([exited, delay(timeoutMs)]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

module.exports = {
  findAvailablePort,
  httpReachable,
  readServerToken,
  startKimiServer,
  stopKimiServer,
  waitForServer,
};

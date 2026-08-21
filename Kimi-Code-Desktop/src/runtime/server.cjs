const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { execFile, spawn } = require("node:child_process");

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function execFileText(file, args, options = {}) {
  return new Promise((resolve, reject) => {
    execFile(file, args, { encoding: "utf8", timeout: 3000, ...options }, (error, stdout) => {
      if (error) reject(error);
      else resolve(stdout);
    });
  });
}

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

async function macListener(port) {
  const rawPid = await execFileText("/usr/sbin/lsof", ["-nP", "-t", `-iTCP:${port}`, "-sTCP:LISTEN"]);
  const pids = [...new Set(rawPid.split(/\s+/).filter(Boolean).map(Number).filter(Number.isInteger))];
  if (pids.length !== 1) return null;
  const pid = pids[0];
  const files = await execFileText("/usr/sbin/lsof", ["-nP", "-a", "-p", String(pid), "-d", "txt", "-Fn"]);
  const executable = files.split("\n").find((line) => line.startsWith("n"))?.slice(1) || "";
  const parent = await execFileText("/bin/ps", ["-p", String(pid), "-o", "ppid="]);
  return { pid, executable, parentPid: Number(parent.trim()) || 0 };
}

async function inspectExistingServer({ port, cliPath, homeDir, platform = process.platform }) {
  if (platform !== "darwin") return { status: "occupied", reason: "当前平台无法安全识别占用端口的进程" };
  try {
    const listener = await macListener(port);
    if (!listener) return { status: "occupied", reason: "端口由多个或未知进程占用" };
    const allowed = new Set([
      path.resolve(cliPath),
      path.resolve(homeDir, "bin", "kimi"),
    ]);
    if (!allowed.has(path.resolve(listener.executable))) {
      return { status: "occupied", reason: `端口由其他程序占用：${listener.executable || `PID ${listener.pid}`}` };
    }
    if (listener.parentPid > 1 && listener.parentPid !== process.pid) {
      return { status: "occupied", reason: "已有另一个 Kimi Code GUI 正在管理这个后台服务" };
    }
    if (!await httpReachable(port)) return { status: "occupied", reason: "Kimi 后台端口存在但尚未就绪" };
    return { status: "adoptable", ...listener };
  } catch (error) {
    return { status: "occupied", reason: `无法确认端口进程身份：${error.message}` };
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

function launchdSubmitArgs({ label, cliPath, port, environment = {} }) {
  const cleanEnvironment = Object.entries(environment)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`);
  return [
    "submit",
    "-l", label,
    "-o", "/dev/null",
    "-e", "/dev/null",
    "--",
    "/usr/bin/env", "-i", ...cleanEnvironment,
    cliPath,
    "web", "--no-open", "--host", "127.0.0.1", "--port", String(port),
  ];
}

function launchdEnvironment(env, homeDir) {
  const allowed = ["HOME", "LANG", "LC_ALL", "LC_CTYPE", "LOGNAME", "PATH", "SHELL", "TMPDIR", "USER"];
  const result = {};
  for (const key of allowed) {
    if (env[key]) result[key] = env[key];
  }
  return { ...result, KIMI_CODE_HOME: homeDir, NO_COLOR: "1" };
}

async function removeLaunchdJob(label) {
  try {
    await execFileText("/bin/launchctl", ["remove", label]);
    return true;
  } catch {
    return false;
  }
}

async function startLaunchdServer({ cliPath, homeDir, label, port, env, timeoutMs = 30000 }) {
  await removeLaunchdJob(label);
  const cleanEnvironment = launchdEnvironment(env, homeDir);
  await execFileText("/bin/launchctl", launchdSubmitArgs({
    label,
    cliPath,
    port,
    environment: cleanEnvironment,
  }), {
    env: { PATH: "/usr/bin:/bin" },
    timeout: 5000,
  });
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await httpReachable(port)) {
      const listener = await macListener(port);
      if (listener && path.resolve(listener.executable) === path.resolve(cliPath)) return listener.pid;
      await removeLaunchdJob(label);
      throw new Error(`launchd 启动了未知的 Kimi 后台进程（端口 ${port}）`);
    }
    await delay(250);
  }
  await removeLaunchdJob(label);
  throw new Error(`launchd 中的 Kimi Code server 未能在端口 ${port} 就绪`);
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

async function startKimiServer({
  cliPath,
  homeDir,
  preferredPort = 58627,
  env = process.env,
  launchdLabel = null,
}) {
  let port = preferredPort;
  try {
    port = await listenOnce(preferredPort);
  } catch (error) {
    if (error.code !== "EADDRINUSE") throw error;
    const existing = await inspectExistingServer({ port: preferredPort, cliPath, homeDir });
    if (existing.status !== "adoptable") {
      throw new Error(`无法使用固定后台端口 ${preferredPort}：${existing.reason}。请先正常退出已有 Kimi Code。`);
    }
    const token = await readServerToken(homeDir);
    return {
      adopted: true,
      child: null,
      executable: existing.executable,
      homeDir,
      launchdLabel,
      output: { text: "" },
      pid: existing.pid,
      port: preferredPort,
      token,
    };
  }
  fs.mkdirSync(homeDir, { recursive: true });
  if (process.platform === "darwin" && launchdLabel) {
    const pid = await startLaunchdServer({ cliPath, homeDir, label: launchdLabel, port, env });
    const token = await readServerToken(homeDir);
    return {
      adopted: false,
      child: null,
      executable: cliPath,
      homeDir,
      launchdLabel,
      output: { text: "" },
      pid,
      port,
      token,
    };
  }
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
    return { adopted: false, child, executable: cliPath, homeDir, output, pid: child.pid, port, token };
  } catch (error) {
    if (child.exitCode === null) child.kill();
    const diagnostic = output.text.trim();
    if (diagnostic) error.message += `\n${diagnostic.slice(-2000)}`;
    throw error;
  }
}

async function stopKimiServer(runtime, timeoutMs = 5000) {
  const child = runtime?.child;
  if (child) {
    if (child.exitCode !== null) return;
    const exited = new Promise((resolve) => child.once("exit", resolve));
    child.kill("SIGTERM");
    await Promise.race([exited, delay(timeoutMs)]);
    if (child.exitCode === null) child.kill("SIGKILL");
    return;
  }
  if (!runtime?.pid) return;
  if (runtime.launchdLabel) await removeLaunchdJob(runtime.launchdLabel);
  if (!runtime.adopted && !runtime.launchdLabel) return;
  try { process.kill(runtime.pid, "SIGTERM"); }
  catch (error) { if (error.code !== "ESRCH") throw error; else return; }
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { process.kill(runtime.pid, 0); }
    catch (error) { if (error.code === "ESRCH") return; throw error; }
    await delay(100);
  }
  process.kill(runtime.pid, "SIGKILL");
}

function runtimeAlive(runtime) {
  if (!runtime) return false;
  if (runtime.child) return runtime.child.exitCode === null;
  if (!runtime.pid) return false;
  try { process.kill(runtime.pid, 0); return true; }
  catch { return false; }
}

module.exports = {
  findAvailablePort,
  httpReachable,
  inspectExistingServer,
  launchdEnvironment,
  launchdSubmitArgs,
  readServerToken,
  runtimeAlive,
  startKimiServer,
  stopKimiServer,
  waitForServer,
};

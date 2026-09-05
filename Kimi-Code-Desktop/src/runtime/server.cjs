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

// lsof 在挂了网络卷的机器上会变慢：本机挂着 //192.168.0.1/share (smbfs)，
// 同一条 -iTCP 查询连跑 5 次实测 0.27 / 3.53 / 0.94 / 0.27 / 0.38 秒 ——
// 五次里有一次超过原来写死的 3 秒超时。而超时被当成「查不出占用者身份」并
// 直接拒绝启动，等于每开一次 App 掷一次骰子。
// -b -w 让 lsof 跳过会阻塞的内核调用（实测 -i 查询和 txt 路径解析都不受影响）。
const LSOF = "/usr/sbin/lsof";
const LSOF_BASE_ARGS = ["-b", "-w", "-nP"];
const LSOF_TIMEOUT_MS = 10000;

// 查不到匹配时 lsof 的退出码就是 1、且不往 stderr 写一个字。
// 那是「没有人占用」，不是「查询失败」——两者必须分开，否则空端口也会被判成故障。
async function lsofText(args) {
  try {
    const text = await execFileText(LSOF, [...LSOF_BASE_ARGS, ...args], { timeout: LSOF_TIMEOUT_MS });
    return { ok: true, text };
  } catch (error) {
    if (error.code === 1 && !String(error.stderr || "").trim()) return { ok: true, text: "" };
    const reason = error.killed || error.signal
      ? `lsof 超过 ${LSOF_TIMEOUT_MS}ms 未返回（本机挂着网络卷时 lsof 会变慢）`
      : String(error.message || error).trim();
    return { ok: false, reason };
  }
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
  const listening = await lsofText(["-t", `-iTCP:${port}`, "-sTCP:LISTEN"]);
  if (!listening.ok) return { error: listening.reason };
  const pids = [...new Set(listening.text.split(/\s+/).filter(Boolean).map(Number).filter(Number.isInteger))];
  if (pids.length !== 1) return { error: "端口由多个或未知进程占用" };
  const pid = pids[0];
  const files = await lsofText(["-a", "-p", String(pid), "-d", "txt", "-Fn"]);
  if (!files.ok) return { error: files.reason };
  const executable = files.text.split("\n").find((line) => line.startsWith("n"))?.slice(1) || "";
  // ppid 只用来判断「是不是另一个 GUI 在管它」，取不到就当孤儿（0），不该让整条链失败。
  let parentPid = 0;
  try {
    const parent = await execFileText("/bin/ps", ["-p", String(pid), "-o", "ppid="]);
    parentPid = Number(parent.trim()) || 0;
  } catch { parentPid = 0; }
  return { pid, executable, parentPid };
}

async function inspectExistingServer({ port, cliPath, homeDir, platform = process.platform }) {
  if (platform !== "darwin") return { status: "occupied", reason: "当前平台无法安全识别占用端口的进程" };
  const listener = await macListener(port);
  // 认不出占用者 ≠ 不能开 App。只有「另一个 GUI 正在管这个后台」才是真冲突，
  // 其余一律 occupied，由调用方换端口继续开。
  if (listener.error) return { status: "occupied", reason: listener.error };
  const allowed = new Set([
    path.resolve(cliPath),
    path.resolve(homeDir, "bin", "kimi"),
  ]);
  if (!allowed.has(path.resolve(listener.executable))) {
    return { status: "occupied", reason: `端口由其他程序占用：${listener.executable || `PID ${listener.pid}`}` };
  }
  if (listener.parentPid > 1 && listener.parentPid !== process.pid) {
    return { status: "conflict", reason: "已有另一个 Kimi Code GUI 正在管理这个后台服务" };
  }
  if (!await httpReachable(port)) return { status: "occupied", reason: "Kimi 后台端口存在但尚未就绪" };
  return { status: "adoptable", ...listener };
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

// 我们自己提交的 launchd 任务，PID 由 launchd 记账。这是比 lsof 更权威、
// 也更快的身份来源：不扫全机文件表，因此不受网络卷拖慢影响。
async function launchdPid(label) {
  if (!label) return 0;
  try {
    const out = await execFileText("/bin/launchctl", ["list", label], { timeout: 5000 });
    const match = out.match(/"PID"\s*=\s*(\d+);/);
    return match ? Number(match[1]) : 0;
  } catch { return 0; }
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
  // 整段包住：任何一条失败路径都必须把 launchd 任务收走。
  // 原来只有两处显式 throw 前收，macListener 抛异常时直接穿出去，
  // 后台服务被漏在那里继续监听 —— 下次启动就撞上自己漏下的东西。
  try {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await httpReachable(port)) {
        const pid = await launchdPid(label);
        if (!pid) { await delay(250); continue; }
        // lsof 只做交叉校验：查得出就必须对得上；查不出（超时/被网络卷拖住）
        // 不构成失败 —— 端口是我们刚独占绑过的，任务是我们刚提交的，HTTP 已经应答。
        const listener = await macListener(port);
        if (listener.error) {
          console.warn(`[kimi] 端口 ${port} 身份交叉校验跳过：${listener.error}`);
        } else if (listener.pid !== pid) {
          throw new Error(`端口 ${port} 上监听的是 PID ${listener.pid}，不是 launchd 启动的 Kimi 后台（PID ${pid}）`);
        }
        return pid;
      }
      await delay(250);
    }
    throw new Error(`launchd 中的 Kimi Code server 未能在端口 ${port} 就绪`);
  } catch (error) {
    await removeLaunchdJob(label);
    throw error;
  }
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
  let portFallbackReason = null;
  try {
    port = await listenOnce(preferredPort);
  } catch (error) {
    if (error.code !== "EADDRINUSE") throw error;
    // 先问 launchd：这个 label 的后台服务是我们自己上一轮留下的，
    // launchd 直接给 PID，不用 lsof，也就不会被网络卷拖到超时。
    const ownPid = await launchdPid(launchdLabel);
    const adoptable = ownPid && await httpReachable(preferredPort)
      ? { status: "adoptable", pid: ownPid, executable: cliPath }
      : await inspectExistingServer({ port: preferredPort, cliPath, homeDir });
    if (adoptable.status === "adoptable") {
      const token = await readServerToken(homeDir);
      return {
        adopted: true,
        child: null,
        executable: adoptable.executable,
        homeDir,
        launchdLabel,
        output: { text: "" },
        pid: adoptable.pid,
        port: preferredPort,
        token,
      };
    }
    if (adoptable.status === "conflict") {
      throw new Error(`无法使用固定后台端口 ${preferredPort}：${adoptable.reason}。请先正常退出已有 Kimi Code。`);
    }
    // 端口被别人占着、或者根本查不出是谁 —— 换一个端口照常开。
    // 固定端口只是偏好：App 全程读返回的 port，没有任何地方读常量。
    portFallbackReason = adoptable.reason;
    console.warn(`[kimi] 固定端口 ${preferredPort} 不可用（${adoptable.reason}），改用临时端口`);
    port = await listenOnce(0);
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
      portFallbackReason,
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
  launchdPid,
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

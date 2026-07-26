#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { once } = require("node:events");

const REQUIRED_RELEASE_PREFIX = "/opt/cyberboss-cloud/releases/";
const REQUIRED_STATE_PREFIX = "/var/lib/cyberboss/";
const REQUIRED_TOKEN_PREFIXES = Object.freeze([
  "/run/cyberboss-cb130/",
  "/run/cyberboss-cb140/",
]);
const RUNTIME_ENDPOINT = "ws://127.0.0.1:8765";
const STATUS_HOST = "127.0.0.1";
const STATUS_PORT = 8780;
const SIM_WEIXIN_ACCOUNT_ID = "sim-ilink-bot";
const SIM_WEIXIN_TOKEN = "sim-token-not-secret";
const CRITICAL_ROLES = Object.freeze(["runtime", "channel", "bridge"]);

class SupervisorViolation extends Error {
  constructor(code) {
    super(code);
    this.name = "SupervisorViolation";
    this.code = code;
  }
}

function expect(condition, code) {
  if (!condition) {
    throw new SupervisorViolation(code);
  }
}

function readText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function readBoolean(value) {
  return ["1", "true", "yes", "on"].includes(readText(value).toLowerCase());
}

function isLoopbackHost(hostname) {
  return hostname === "127.0.0.1" || hostname === "::1" || hostname === "localhost";
}

function parseLoopbackUrl(value, protocol, requiredPort, code) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new SupervisorViolation(`${code}_url`);
  }
  expect(parsed.protocol === protocol, `${code}_protocol`);
  expect(isLoopbackHost(parsed.hostname), `${code}_host`);
  expect(Number(parsed.port) === requiredPort, `${code}_port`);
  expect(!parsed.username && !parsed.password, `${code}_credentials`);
  return parsed;
}

function assertAbsoluteWithin(candidate, prefix, code) {
  const raw = readText(candidate);
  expect(path.isAbsolute(raw), `${code}_absolute`);
  const resolved = path.resolve(raw);
  const normalizedPrefix = path.resolve(prefix);
  expect(
    resolved === normalizedPrefix || resolved.startsWith(`${normalizedPrefix}${path.sep}`),
    `${code}_scope`,
  );
  return resolved;
}

function assertAbsoluteWithinOneOf(candidate, prefixes, code) {
  const raw = readText(candidate);
  expect(path.isAbsolute(raw), `${code}_absolute`);
  const resolved = path.resolve(raw);
  for (const prefix of prefixes) {
    const normalizedPrefix = path.resolve(prefix);
    if (
      resolved === normalizedPrefix
      || resolved.startsWith(`${normalizedPrefix}${path.sep}`)
    ) {
      return resolved;
    }
  }
  throw new SupervisorViolation(`${code}_scope`);
}

function loadConfiguration(environment = process.env) {
  const releaseCommit = readText(environment.CB_EXPECTED_RELEASE_ID);
  expect(/^[0-9a-f]{40}$/.test(releaseCommit), "release_commit");
  const releaseRoot = assertAbsoluteWithin(
    environment.CB_RELEASE_ROOT,
    REQUIRED_RELEASE_PREFIX,
    "release_root",
  );
  expect(releaseRoot === `${REQUIRED_RELEASE_PREFIX}${releaseCommit}`, "release_root_commit");
  const stateDir = assertAbsoluteWithin(
    environment.CYBERBOSS_STATE_DIR,
    REQUIRED_STATE_PREFIX,
    "state_dir",
  );
  const statusTokenFile = assertAbsoluteWithinOneOf(
    environment.CB_STATUS_TOKEN_FILE,
    REQUIRED_TOKEN_PREFIXES,
    "status_token_file",
  );
  const runtimeProvider = readText(environment.CB_RUNTIME_PROVIDER);
  const channelProvider = readText(environment.CB_CHANNEL_PROVIDER);
  expect(["simulator", "real"].includes(runtimeProvider), "runtime_provider");
  expect(["simulator", "real"].includes(channelProvider), "channel_provider");
  expect(readText(environment.CYBERBOSS_RUNTIME) === "codex", "runtime_kind");
  const runtimeUrl = parseLoopbackUrl(
    readText(environment.CYBERBOSS_CODEX_ENDPOINT),
    "ws:",
    8765,
    "runtime_endpoint",
  );
  let channelUrl;
  if (channelProvider === "simulator") {
    channelUrl = parseLoopbackUrl(
      readText(environment.CYBERBOSS_WEIXIN_BASE_URL),
      "http:",
      19080,
      "channel_endpoint",
    );
  } else {
    try {
      channelUrl = new URL(readText(environment.CYBERBOSS_WEIXIN_BASE_URL));
    } catch {
      throw new SupervisorViolation("channel_endpoint_url");
    }
    expect(channelUrl.protocol === "https:", "channel_endpoint_protocol");
    expect(!channelUrl.username && !channelUrl.password, "channel_endpoint_credentials");
  }
  expect(readText(environment.CB_HTTP_HOST) === STATUS_HOST, "status_host");
  expect(Number(environment.CB_HTTP_PORT) === STATUS_PORT, "status_port");

  const acceptanceMode = readBoolean(environment.CB_ACCEPTANCE_MODE);
  const forcedUnreadyRole = readText(environment.CB_ACCEPTANCE_UNREADY_ROLE);
  expect(!forcedUnreadyRole || acceptanceMode, "unready_fixture_gate");
  expect(!forcedUnreadyRole || CRITICAL_ROLES.includes(forcedUnreadyRole), "unready_fixture_role");

  return {
    releaseCommit,
    releaseRoot,
    appRoot: path.join(releaseRoot, "app"),
    stateDir,
    statusTokenFile,
    runtimeProvider,
    channelProvider,
    runtimeUrl,
    channelUrl,
    statusHost: STATUS_HOST,
    statusPort: STATUS_PORT,
    forcedUnreadyRole,
    codexCommand: readText(environment.CYBERBOSS_CODEX_COMMAND)
      || "/opt/cyberboss-cloud/shared/toolchains/bin/codex",
    simulatorDirectory: path.join(releaseRoot, "implementation-kit", "simulators"),
  };
}

function createLifecycleState() {
  return {
    supervisor: true,
    runtime: false,
    channel: false,
    bridge: false,
    fatalReason: "",
    shuttingDown: false,
  };
}

function componentSnapshot(state, forcedUnreadyRole = "") {
  return {
    supervisor: state.supervisor === true && !state.shuttingDown,
    runtime: state.runtime === true && forcedUnreadyRole !== "runtime",
    channel: state.channel === true && forcedUnreadyRole !== "channel",
    bridge: state.bridge === true && forcedUnreadyRole !== "bridge",
  };
}

function evaluateHealth(state, forcedUnreadyRole = "") {
  const components = componentSnapshot(state, forcedUnreadyRole);
  const healthy = components.supervisor && !state.fatalReason;
  const unready = CRITICAL_ROLES.filter((role) => components[role] !== true);
  return {
    healthy,
    ready: healthy && unready.length === 0,
    components,
    unready,
  };
}

function providerClaim(provider, ready) {
  if (provider === "simulator") {
    return ready ? "simulator_verified" : "simulator_unready";
  }
  return "activation_pending";
}

function buildStatusSnapshot(config, state) {
  const health = evaluateHealth(state, config.forcedUnreadyRole);
  return {
    schema_version: 1,
    project: "CyberBoss",
    phase: "P1.4",
    task_id: "CB-130",
    release_commit: config.releaseCommit,
    claim_level:
      config.runtimeProvider === "simulator" && config.channelProvider === "simulator"
        ? "simulator_fixture"
        : "staging_unverified",
    status: health.ready ? "ready" : health.healthy ? "unready" : "unhealthy",
    healthy: health.healthy,
    ready: health.ready,
    components: health.components,
    unready_components: health.unready,
    providers: {
      runtime: providerClaim(config.runtimeProvider, health.components.runtime),
      channel: providerClaim(config.channelProvider, health.components.channel),
    },
    process_family: {
      supervised: true,
      detached_children: false,
      kill_mode: "control-group",
      singleton_lock: true,
    },
    network: {
      runtime_loopback_only: true,
      status_loopback_only: true,
      public_listener: false,
    },
    recovery: {
      mode: "probe_driven",
      fixed_wait: false,
      llm_call: false,
    },
  };
}

function safeTokenEqual(headerValue, token) {
  const expected = `Bearer ${token}`;
  const received = readText(headerValue);
  const expectedBuffer = Buffer.from(expected, "utf8");
  const receivedBuffer = Buffer.from(received, "utf8");
  if (expectedBuffer.length !== receivedBuffer.length) {
    return false;
  }
  return crypto.timingSafeEqual(expectedBuffer, receivedBuffer);
}

function writeJson(response, statusCode, value, extraHeaders = {}) {
  const body = `${JSON.stringify(value)}\n`;
  response.writeHead(statusCode, {
    "cache-control": "no-store",
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body),
    ...extraHeaders,
  });
  response.end(body);
}

function createStatusHandler(config, state, statusToken) {
  return (request, response) => {
    if (request.method !== "GET") {
      return writeJson(response, 405, { error: "method_not_allowed" });
    }
    const pathname = new URL(request.url, "http://127.0.0.1").pathname;
    const health = evaluateHealth(state, config.forcedUnreadyRole);
    if (pathname === "/healthz") {
      return writeJson(response, health.healthy ? 200 : 503, {
        status: health.healthy ? "healthy" : "unhealthy",
      });
    }
    if (pathname === "/readyz") {
      return writeJson(response, health.ready ? 200 : 503, {
        status: health.ready ? "ready" : "unready",
        unready_components: health.unready,
      });
    }
    if (pathname === "/status/snapshot.json") {
      if (!safeTokenEqual(request.headers.authorization, statusToken)) {
        return writeJson(
          response,
          401,
          { error: "unauthorized" },
          { "www-authenticate": "Bearer" },
        );
      }
      return writeJson(response, 200, buildStatusSnapshot(config, state));
    }
    return writeJson(response, 404, { error: "not_found" });
  };
}

function loadStatusToken(filePath) {
  const metadata = fs.lstatSync(filePath);
  expect(metadata.isFile() && !metadata.isSymbolicLink(), "status_token_type");
  expect((metadata.mode & 0o007) === 0, "status_token_world_access");
  const token = fs.readFileSync(filePath, "utf8").trim();
  expect(/^[0-9a-f]{64}$/.test(token), "status_token_format");
  return token;
}

function ensureSimulatorAccount(config) {
  if (config.channelProvider !== "simulator") {
    return;
  }
  const accountsDir = path.join(config.stateDir, "accounts");
  fs.mkdirSync(accountsDir, { recursive: true, mode: 0o700 });
  const accountPath = path.join(accountsDir, `${SIM_WEIXIN_ACCOUNT_ID}.json`);
  const expected = {
    accountId: SIM_WEIXIN_ACCOUNT_ID,
    rawAccountId: SIM_WEIXIN_ACCOUNT_ID,
    token: SIM_WEIXIN_TOKEN,
    baseUrl: config.channelUrl.toString(),
    userId: "sim-authorized-user",
    savedAt: "2023-11-14T22:13:20.000Z",
  };
  const serialized = `${JSON.stringify(expected, null, 2)}\n`;
  if (fs.existsSync(accountPath)) {
    expect(fs.readFileSync(accountPath, "utf8") === serialized, "simulator_account_drift");
    return;
  }
  const temporary = `${accountPath}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, serialized, { encoding: "utf8", mode: 0o600, flag: "wx" });
  fs.renameSync(temporary, accountPath);
}

function childSpawnOptions(config, extraEnvironment = {}) {
  return {
    cwd: config.appRoot,
    env: {
      ...process.env,
      ...extraEnvironment,
    },
    detached: false,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
  };
}

function logEvent(event, fields = {}) {
  const suffix = Object.entries(fields)
    .map(([key, value]) => `${key}=${String(value).replace(/[^a-zA-Z0-9_.:-]/g, "_")}`)
    .join(" ");
  process.stdout.write(`CB_SUPERVISOR_EVENT event=${event}${suffix ? ` ${suffix}` : ""}\n`);
}

function watchLines(stream, onLine) {
  let buffer = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buffer += chunk;
    if (buffer.length > 65_536 && !buffer.includes("\n")) {
      buffer = buffer.slice(-65_536);
    }
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      onLine(line);
    }
  });
  stream.on("end", () => {
    if (buffer) {
      onLine(buffer);
    }
  });
}

function spawnManagedChild({
  role,
  command,
  args,
  config,
  state,
  environment = {},
  readyPattern,
  onFatal,
}) {
  const child = spawn(command, args, childSpawnOptions(config, environment));
  let ready = false;
  let resolveReady;
  let rejectReady;
  const readyPromise = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });
  const markReady = () => {
    if (!ready) {
      ready = true;
      state[role] = true;
      logEvent("component_ready", { role });
      resolveReady();
    }
  };
  const inspectLine = (line) => {
    if (!ready && readyPattern && readyPattern.test(line)) {
      markReady();
    }
  };
  watchLines(child.stdout, inspectLine);
  watchLines(child.stderr, () => {});
  child.once("error", (error) => {
    if (!ready) {
      rejectReady(new SupervisorViolation(`${role}_spawn_${error.code || "error"}`));
    }
  });
  child.once("exit", (code, signal) => {
    state[role] = false;
    if (!ready) {
      rejectReady(new SupervisorViolation(`${role}_exit_before_ready`));
    }
    if (!state.shuttingDown) {
      state.fatalReason = `${role}_exited`;
      logEvent("component_exit", {
        role,
        outcome: "fatal",
        termination: signal ? "signal" : `code_${code ?? "unknown"}`,
      });
      onFatal(role);
    }
  });
  return { child, readyPromise, role, markReady };
}

function withSafetyDeadline(promise, milliseconds, code) {
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new SupervisorViolation(code)), milliseconds);
  });
  return Promise.race([promise, deadline]).finally(() => clearTimeout(timer));
}

function probeHttpReady(runtimeUrl) {
  return new Promise((resolve) => {
    const request = http.get(
      {
        host: runtimeUrl.hostname,
        port: Number(runtimeUrl.port),
        path: "/readyz",
        timeout: 500,
      },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      },
    );
    request.once("timeout", () => {
      request.destroy();
      resolve(false);
    });
    request.once("error", () => resolve(false));
  });
}

async function waitForRuntimeProbe(runtimeUrl, child) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline && child.exitCode === null && child.signalCode === null) {
    if (await probeHttpReady(runtimeUrl)) {
      return;
    }
    await new Promise((resolve) => setImmediate(resolve));
  }
  throw new SupervisorViolation("runtime_probe_deadline");
}

async function closeServer(server) {
  if (!server.listening) {
    return;
  }
  server.close();
  await once(server, "close").catch(() => {});
}

async function main() {
  const config = loadConfiguration();
  const state = createLifecycleState();
  const children = [];
  let statusServer = null;
  let shutdownPromise = null;

  const shutdown = (exitCode) => {
    if (shutdownPromise) {
      return shutdownPromise;
    }
    shutdownPromise = (async () => {
      state.shuttingDown = true;
      state.supervisor = false;
      logEvent("shutdown", { outcome: exitCode === 0 ? "clean" : "restart_required" });
      await closeServer(statusServer).catch(() => {});
      for (const managed of children) {
        if (managed.child.exitCode === null && managed.child.signalCode === null) {
          managed.child.kill("SIGTERM");
        }
      }
      const exits = children.map(({ child }) => (
        child.exitCode !== null || child.signalCode !== null
          ? Promise.resolve()
          : once(child, "exit").then(() => undefined)
      ));
      await withSafetyDeadline(Promise.all(exits), 5_000, "child_shutdown_deadline")
        .catch(() => {
          for (const managed of children) {
            if (managed.child.exitCode === null && managed.child.signalCode === null) {
              managed.child.kill("SIGKILL");
            }
          }
        });
      process.exit(exitCode);
    })();
    return shutdownPromise;
  };

  const fatal = () => {
    setImmediate(() => {
      void shutdown(75);
    });
  };

  process.once("SIGINT", () => {
    void shutdown(0);
  });
  process.once("SIGTERM", () => {
    void shutdown(0);
  });

  fs.mkdirSync(config.stateDir, { recursive: true, mode: 0o700 });
  for (const relative of ["logs", "status", "tmp"]) {
    fs.mkdirSync(path.join(config.stateDir, relative), { recursive: true, mode: 0o700 });
  }
  ensureSimulatorAccount(config);
  const statusToken = loadStatusToken(config.statusTokenFile);
  statusServer = http.createServer(createStatusHandler(config, state, statusToken));
  statusServer.on("error", () => {
    if (!state.shuttingDown) {
      state.fatalReason = "status_server_error";
      fatal();
    }
  });
  statusServer.listen(config.statusPort, config.statusHost);
  await once(statusServer, "listening");
  logEvent("status_listening", { bind: "loopback", port: config.statusPort });

  let runtime;
  if (config.runtimeProvider === "simulator") {
    runtime = spawnManagedChild({
      role: "runtime",
      command: process.execPath,
      args: [path.join(config.simulatorDirectory, "codex-app-server-simulator.mjs")],
      config,
      state,
      environment: {
        SIM_CODEX_HOST: "127.0.0.1",
        SIM_CODEX_PORT: "8765",
      },
      readyPattern: /CODEX_SIMULATOR=READY\b/,
      onFatal: fatal,
    });
    children.push(runtime);
    await withSafetyDeadline(runtime.readyPromise, 30_000, "runtime_ready_deadline");
  } else {
    runtime = spawnManagedChild({
      role: "runtime",
      command: config.codexCommand,
      args: ["app-server", "--listen", RUNTIME_ENDPOINT],
      config,
      state,
      readyPattern: null,
      onFatal: fatal,
    });
    children.push(runtime);
    runtime.readyPromise.catch(() => {});
    await waitForRuntimeProbe(config.runtimeUrl, runtime.child);
    runtime.markReady();
  }

  if (config.channelProvider === "simulator") {
    const channel = spawnManagedChild({
      role: "channel",
      command: process.execPath,
      args: [path.join(config.simulatorDirectory, "weixin-ilink-simulator.mjs")],
      config,
      state,
      environment: {
        SIM_WEIXIN_HOST: "127.0.0.1",
        SIM_WEIXIN_PORT: "19080",
        SIM_WEIXIN_HOLD_EMPTY_POLLS: "true",
      },
      readyPattern: /WEIXIN_SIMULATOR=READY\b/,
      onFatal: fatal,
    });
    children.push(channel);
    await withSafetyDeadline(channel.readyPromise, 30_000, "channel_ready_deadline");
  } else {
    state.channel = true;
    logEvent("component_configured", { role: "channel", activation: "pending" });
  }

  const bridge = spawnManagedChild({
    role: "bridge",
    command: process.execPath,
    args: ["./bin/cyberboss.js", "start"],
    config,
    state,
    environment: {
      CYBERBOSS_ACCOUNT_ID:
        config.channelProvider === "simulator"
          ? SIM_WEIXIN_ACCOUNT_ID
          : process.env.CYBERBOSS_ACCOUNT_ID,
      CYBERBOSS_CODEX_ENDPOINT: RUNTIME_ENDPOINT,
      CYBERBOSS_ENABLE_LOCATION_SERVER: "false",
      CYBERBOSS_WEIXIN_BASE_URL: config.channelUrl.toString(),
    },
    readyPattern: /\[cyberboss\] bootstrap ok\b/,
    onFatal: fatal,
  });
  children.push(bridge);
  await withSafetyDeadline(bridge.readyPromise, 30_000, "bridge_ready_deadline");
  logEvent("service_ready", {
    claim:
      config.runtimeProvider === "simulator" && config.channelProvider === "simulator"
        ? "fixture"
        : "activation_pending",
  });

  await new Promise(() => {});
}

if (require.main === module) {
  main().catch((error) => {
    const code = error instanceof SupervisorViolation ? error.code : "unexpected";
    logEvent("startup_failure", { reason: code });
    process.exit(78);
  });
}

module.exports = {
  SupervisorViolation,
  buildStatusSnapshot,
  childSpawnOptions,
  createLifecycleState,
  createStatusHandler,
  evaluateHealth,
  isLoopbackHost,
  loadConfiguration,
  safeTokenEqual,
};

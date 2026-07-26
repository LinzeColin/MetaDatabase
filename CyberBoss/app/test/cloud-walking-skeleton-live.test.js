const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const appRoot = path.resolve(__dirname, "..");
const kitRoot = path.resolve(
  appRoot,
  "../docs/product_design/v0.0.0.4/implementation-kit",
);

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function spawnNode(args, { cwd = appRoot, env = {} } = {}) {
  const child = spawn(process.execPath, args, {
    cwd,
    env: { ...process.env, ...env },
    detached: false,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.output = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    child.output += chunk;
  });
  child.stderr.on("data", (chunk) => {
    child.output += chunk;
  });
  return child;
}

async function waitForOutput(child, pattern, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (pattern.test(child.output)) {
      return child.output;
    }
    if (child.exitCode !== null) {
      throw new Error(`child exited before ${pattern}: ${child.output.slice(-1000)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(`output timeout ${pattern}: ${child.output.slice(-1000)}`);
}

async function stopChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) {
    return;
  }
  child.kill("SIGTERM");
  const exited = await Promise.race([
    new Promise((resolve) => child.once("exit", () => resolve(true))),
    new Promise((resolve) => setTimeout(() => resolve(false), 2_000)),
  ]);
  if (!exited && child.exitCode === null) {
    child.kill("SIGKILL");
    await new Promise((resolve) => child.once("exit", resolve));
  }
}

test("live simulator process chain passes the complete CB-140 acceptance runner", {
  timeout: 60_000,
}, async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-cb140-live-"));
  const stateDir = path.join(root, "state");
  const workspaceBase = path.join(root, "workspaces");
  const workspace = path.join(workspaceBase, "cyberboss");
  const traceFile = path.join(stateDir, "evidence", "walking-skeleton.ndjson");
  const outputDir = path.join(root, "output");
  fs.mkdirSync(workspace, { recursive: true });
  fs.mkdirSync(path.join(stateDir, "accounts"), { recursive: true });
  fs.mkdirSync(outputDir, { recursive: true });

  const workspaceConfig = path.join(root, "workspaces.json");
  writeJson(workspaceConfig, {
    schema_version: 1,
    default_alias: "cyberboss",
    workspace_base: workspaceBase,
    workspaces: {
      cyberboss: {
        repo: "LinzeColin/MetaDatabase",
        root: workspace,
        project_subpath: "CyberBoss",
        read_only: false,
        max_bytes: 4_294_967_296,
        allowed_branches: ["main", "codex/cyberboss-*"],
        sparse_paths: ["CyberBoss", ".github"],
        root_integration_paths: [".github"],
        root_integration_write: false,
        write_globs: ["CyberBoss/**"],
      },
    },
  });
  writeJson(path.join(stateDir, "accounts", "sim-ilink-bot.json"), {
    accountId: "sim-ilink-bot",
    rawAccountId: "sim-ilink-bot",
    token: "sim-token-not-secret",
    baseUrl: "http://127.0.0.1:19080/",
    userId: "sim-authorized-user",
    savedAt: "2026-07-27T00:00:00.000Z",
  });

  const runtime = spawnNode([
    path.join(kitRoot, "simulators", "codex-app-server-simulator.mjs"),
  ], {
    env: {
      SIM_CODEX_HOST: "127.0.0.1",
      SIM_CODEX_PORT: "8765",
    },
  });
  const channel = spawnNode([
    path.join(kitRoot, "simulators", "weixin-ilink-simulator.mjs"),
  ], {
    env: {
      SIM_WEIXIN_HOST: "127.0.0.1",
      SIM_WEIXIN_PORT: "19080",
      SIM_WEIXIN_HOLD_EMPTY_POLLS: "true",
    },
  });
  let bridge = null;
  t.after(async () => {
    await stopChild(bridge);
    await stopChild(channel);
    await stopChild(runtime);
  });

  await waitForOutput(runtime, /CODEX_SIMULATOR=READY/);
  await waitForOutput(channel, /WEIXIN_SIMULATOR=READY/);
  bridge = spawnNode(["./bin/cyberboss.js", "start"], {
    env: {
      CYBERBOSS_STATE_DIR: stateDir,
      CYBERBOSS_WORKSPACE_CONFIG: workspaceConfig,
      CYBERBOSS_WORKSPACE_BASE: workspaceBase,
      CYBERBOSS_WORKSPACE_ALIAS: "cyberboss",
      CYBERBOSS_WORKSPACE_ROOT: workspace,
      CYBERBOSS_ACCOUNT_ID: "sim-ilink-bot",
      CYBERBOSS_ALLOWED_USER_IDS: "sim-authorized-user",
      CYBERBOSS_RUNTIME: "codex",
      CYBERBOSS_CODEX_ENDPOINT: "ws://127.0.0.1:8765",
      CYBERBOSS_WEIXIN_BASE_URL: "http://127.0.0.1:19080/",
      CYBERBOSS_WALKING_SKELETON_TRACE_FILE: traceFile,
      CB_MAX_INPUT_BYTES: "32768",
    },
  });
  await waitForOutput(bridge, /\[cyberboss\] bootstrap ok/);

  const runner = spawnNode([
    path.join(kitRoot, "scripts", "run-walking-skeleton-acceptance.mjs"),
    "--trace-file",
    traceFile,
    "--output",
    path.join(outputDir, "walking-skeleton.json"),
    "--correlated-output",
    path.join(outputDir, "correlated-trace.redacted.ndjson"),
    "--fixture-html",
    path.join(outputDir, "wechat-roundtrip.fixture.html"),
  ]);
  const [exitCode] = await new Promise((resolve) => {
    runner.once("exit", (...args) => resolve(args));
  });
  assert.equal(exitCode, 0, runner.output);
  assert.match(runner.output, /CB140_WALKING_SKELETON=PASS e2e=10\/10/);

  const report = JSON.parse(
    fs.readFileSync(path.join(outputDir, "walking-skeleton.json"), "utf8"),
  );
  assert.equal(report.simulator_e2e.successful_traces, 10);
  assert.equal(report.inbound_policy.allowlist_unauthorized_runtime_calls, 0);
  assert.equal(report.inbound_policy.boundary_32768_runtime_calls, 1);
  assert.equal(report.inbound_policy.boundary_32769_runtime_calls, 0);
  assert.equal(report.latency.sample_count, 20);
  assert.ok(report.latency.p50_ms < 5_000);
  assert.ok(report.latency.p95_ms < 10_000);
  assert.equal(report.real_adapters.wechat, "activation_pending");
  assert.equal(report.real_adapters.codex, "activation_pending");
  assert.equal(report.pg_1_executed, false);
});

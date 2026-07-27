const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { once } = require("node:events");

const {
  buildStatusSnapshot,
  childSpawnOptions,
  createLifecycleState,
  createStatusHandler,
  evaluateHealth,
  holdPendingChannel,
  loadConfiguration,
  notifySystemdReady,
} = require("../scripts/cloud-supervisor");

const releaseCommit = "1".repeat(40);

function validEnvironment(overrides = {}) {
  return {
    CB_EXPECTED_RELEASE_ID: releaseCommit,
    CB_RELEASE_ROOT: `/opt/cyberboss-cloud/releases/${releaseCommit}`,
    CYBERBOSS_STATE_DIR: "/var/lib/cyberboss/cb130-staging",
    CB_STATUS_TOKEN_FILE: "/run/cyberboss-cb130/status.token",
    CB_RUNTIME_PROVIDER: "simulator",
    CB_CHANNEL_PROVIDER: "simulator",
    CYBERBOSS_RUNTIME: "codex",
    CYBERBOSS_CODEX_ENDPOINT: "ws://127.0.0.1:8765",
    CYBERBOSS_WEIXIN_BASE_URL: "http://127.0.0.1:19080/",
    CB_HTTP_HOST: "127.0.0.1",
    CB_HTTP_PORT: "8780",
    ...overrides,
  };
}

function request(server, pathname, authorization = "") {
  const address = server.address();
  return new Promise((resolve, reject) => {
    const req = http.get(
      {
        host: "127.0.0.1",
        port: address.port,
        path: pathname,
        headers: authorization ? { authorization } : {},
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          const contentType = String(response.headers["content-type"] || "");
          resolve({
            status: response.statusCode,
            body,
            value: contentType.includes("application/json") ? JSON.parse(body) : undefined,
          });
        });
      },
    );
    req.on("error", reject);
  });
}

test("cloud configuration is exact-commit and loopback fail-closed", () => {
  const config = loadConfiguration(validEnvironment());
  assert.equal(config.runtimeUrl.toString(), "ws://127.0.0.1:8765/");
  assert.equal(config.channelUrl.toString(), "http://127.0.0.1:19080/");
  assert.equal(config.deploymentPhase, "P1.4");
  assert.equal(config.deploymentTaskId, "CB-130");
  const cb510 = loadConfiguration(validEnvironment({
    CB_DEPLOYMENT_PHASE: "P5.2",
    CB_DEPLOYMENT_TASK_ID: "CB-510",
  }));
  assert.equal(cb510.deploymentPhase, "P5.2");
  assert.equal(cb510.deploymentTaskId, "CB-510");
  const pendingChannel = loadConfiguration(validEnvironment({
    CB_CHANNEL_PROVIDER: "real",
    CYBERBOSS_WEIXIN_BASE_URL: "https://ilinkai.weixin.qq.com/",
    CB_CHANNEL_ACTIVATION_MODE: "pending",
  }));
  assert.equal(pendingChannel.channelActivationMode, "pending");
  assert.equal(holdPendingChannel(pendingChannel), true);
  assert.throws(
    () => loadConfiguration(validEnvironment({
      CYBERBOSS_CODEX_ENDPOINT: "ws://0.0.0.0:8765",
    })),
    /runtime_endpoint_host/,
  );
  assert.throws(
    () => loadConfiguration(validEnvironment({
      CB_RELEASE_ROOT: `/opt/cyberboss-cloud/releases/${"2".repeat(40)}`,
    })),
    /release_root_commit/,
  );
  assert.throws(
    () => loadConfiguration(validEnvironment({
      CB_ACCEPTANCE_UNREADY_ROLE: "runtime",
    })),
    /unready_fixture_gate/,
  );
  assert.throws(
    () => loadConfiguration(validEnvironment({
      CB_DEPLOYMENT_PHASE: "P5",
    })),
    /deployment_phase/,
  );
  assert.throws(
    () => loadConfiguration(validEnvironment({
      CB_DEPLOYMENT_TASK_ID: "CB-51",
    })),
    /deployment_task_id/,
  );
  assert.throws(
    () => loadConfiguration(validEnvironment({
      CB_CHANNEL_ACTIVATION_MODE: "pending",
    })),
    /channel_activation_mode_provider/,
  );
});

test("managed children are never detached and never use a shell", () => {
  const config = loadConfiguration(validEnvironment());
  const options = childSpawnOptions(config);
  assert.equal(options.detached, false);
  assert.equal(options.shell, false);
  assert.deepEqual(options.stdio, ["ignore", "pipe", "pipe"]);
});

test("systemd readiness is emitted only after a listener exists and fails closed", () => {
  assert.equal(notifySystemdReady({}, () => {
    throw new Error("must not execute without NOTIFY_SOCKET");
  }), false);

  const calls = [];
  assert.equal(
    notifySystemdReady(
      { NOTIFY_SOCKET: "/run/systemd/notify" },
      (command, args, options) => {
        calls.push({ command, args, options });
        return { status: 0 };
      },
    ),
    true,
  );
  assert.deepEqual(calls, [{
    command: "/usr/bin/systemd-notify",
    args: [
      "--ready",
      "--status=CyberBoss loopback status listener ready",
      "--no-block",
    ],
    options: {
      env: { NOTIFY_SOCKET: "/run/systemd/notify" },
      shell: false,
      stdio: "ignore",
    },
  }]);
  assert.throws(
    () => notifySystemdReady(
      { NOTIFY_SOCKET: "/run/systemd/notify" },
      () => ({ status: 1 }),
    ),
    /systemd_notify_ready/,
  );
});

test("health and readiness are independent and a forced fixture cannot fake green", () => {
  const state = createLifecycleState();
  assert.deepEqual(evaluateHealth(state), {
    healthy: true,
    ready: false,
    components: {
      supervisor: true,
      runtime: false,
      channel: false,
      bridge: false,
    },
    unready: ["runtime", "channel", "bridge"],
  });
  state.runtime = true;
  state.channel = true;
  state.bridge = true;
  assert.equal(evaluateHealth(state).ready, true);
  const forced = evaluateHealth(state, "runtime");
  assert.equal(forced.healthy, true);
  assert.equal(forced.ready, false);
  assert.deepEqual(forced.unready, ["runtime"]);
  state.fatalReason = "bridge_exited";
  assert.equal(evaluateHealth(state).healthy, false);
});

test("a missing real channel credential holds only the channel and bridge pending", () => {
  const config = loadConfiguration(validEnvironment({
    CB_RUNTIME_PROVIDER: "real",
    CB_CHANNEL_PROVIDER: "real",
    CYBERBOSS_WEIXIN_BASE_URL: "https://ilinkai.weixin.qq.com/",
    CB_CHANNEL_ACTIVATION_MODE: "pending",
  }));
  const state = createLifecycleState();
  state.runtime = true;
  assert.equal(holdPendingChannel(config), true);
  const snapshot = buildStatusSnapshot(config, state);
  assert.equal(snapshot.healthy, true);
  assert.equal(snapshot.ready, false);
  assert.deepEqual(snapshot.unready_components, ["channel", "bridge"]);
  assert.equal(snapshot.providers.runtime, "activation_pending");
  assert.equal(snapshot.providers.channel, "activation_pending");
});

test("status snapshot is bounded, protected and contains no operational identity", async (t) => {
  const config = loadConfiguration(validEnvironment({
    CB_DEPLOYMENT_PHASE: "P5.2",
    CB_DEPLOYMENT_TASK_ID: "CB-510",
  }));
  const state = createLifecycleState();
  state.runtime = true;
  state.channel = true;
  state.bridge = true;
  const token = "a".repeat(64);
  const server = http.createServer(createStatusHandler(config, state, token));
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(async () => {
    server.close();
    await once(server, "close").catch(() => {});
  });

  assert.equal((await request(server, "/healthz")).status, 200);
  assert.equal((await request(server, "/readyz")).status, 200);
  assert.equal((await request(server, "/status/snapshot.json")).status, 401);
  assert.equal(
    (await request(server, "/status/snapshot.json", "Bearer invalid")).status,
    401,
  );
  const authorized = await request(
    server,
    "/status/snapshot.json",
    `Bearer ${token}`,
  );
  assert.equal(authorized.status, 200);
  assert.equal(authorized.value.ready, true);
  assert.equal(authorized.value.phase, "P5.2");
  assert.equal(authorized.value.task_id, "CB-510");
  assert.equal(authorized.value.providers.runtime, "simulator_verified");
  const serialized = JSON.stringify(authorized.value);
  for (const forbidden of [
    "token",
    "thread",
    "account",
    "message",
    "prompt",
    "result",
    "/var/",
    "/srv/",
    "pid",
  ]) {
    assert.equal(serialized.toLowerCase().includes(forbidden), false);
  }
  assert.deepEqual(authorized.value, buildStatusSnapshot(config, state));
});

test("timeline and compact status are served only from the derived static surface", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb-supervisor-timeline-"));
  const timelineRoot = path.join(root, "site");
  fs.mkdirSync(path.join(timelineRoot, "assets"), { recursive: true, mode: 0o700 });
  fs.writeFileSync(path.join(timelineRoot, "index.html"), "<h1>时间线</h1>", "utf8");
  fs.writeFileSync(path.join(timelineRoot, "assets", "dashboard.js"), "window.ok=true;", "utf8");
  const config = {
    ...loadConfiguration(validEnvironment({
      CB_DEPLOYMENT_PHASE: "P5.2",
      CB_DEPLOYMENT_TASK_ID: "CB-510",
    })),
    timelinePublicRoot: timelineRoot,
  };
  const state = createLifecycleState();
  state.runtime = true;
  state.channel = true;
  state.bridge = true;
  const server = http.createServer(createStatusHandler(config, state, "b".repeat(64)));
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(async () => {
    server.close();
    await once(server, "close").catch(() => {});
    fs.rmSync(root, { recursive: true, force: true });
  });

  const rootResponse = await request(server, "/");
  assert.equal(rootResponse.status, 302);
  const timeline = await request(server, "/timeline/");
  assert.equal(timeline.status, 200);
  assert.equal(timeline.value, undefined);
  assert.equal(timeline.body, "<h1>时间线</h1>");
  const status = await request(server, "/status/");
  assert.deepEqual(status.value, {
    project: "CyberBoss",
    phase: "P5.2",
    task_id: "CB-510",
    status: "ready",
    healthy: true,
    ready: true,
  });
  assert.equal((await request(server, "/timeline/../index.html")).status, 404);
  assert.equal((await request(server, "/timeline/missing.svg")).status, 404);
});

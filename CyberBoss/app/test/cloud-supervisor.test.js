const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");
const { once } = require("node:events");

const {
  buildStatusSnapshot,
  childSpawnOptions,
  createLifecycleState,
  createStatusHandler,
  evaluateHealth,
  loadConfiguration,
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
          resolve({
            status: response.statusCode,
            value: JSON.parse(Buffer.concat(chunks).toString("utf8")),
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
});

test("managed children are never detached and never use a shell", () => {
  const config = loadConfiguration(validEnvironment());
  const options = childSpawnOptions(config);
  assert.equal(options.detached, false);
  assert.equal(options.shell, false);
  assert.deepEqual(options.stdio, ["ignore", "pipe", "pipe"]);
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

test("status snapshot is bounded, protected and contains no operational identity", async (t) => {
  const config = loadConfiguration(validEnvironment());
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

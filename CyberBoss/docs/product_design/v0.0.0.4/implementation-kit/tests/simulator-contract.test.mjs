import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectDirectory = path.resolve(testDirectory, "../../../../..");
const simulatorDirectory = path.resolve(testDirectory, "../simulators");
const weixinSimulator = path.join(simulatorDirectory, "weixin-ilink-simulator.mjs");
const codexSimulator = path.join(simulatorDirectory, "codex-app-server-simulator.mjs");
const requireFromApp = createRequire(path.join(projectDirectory, "app/package.json"));
const { WebSocket } = requireFromApp("ws");

const safetyTimeoutMs = 5_000;

async function startSimulator(script, environment, readyPattern) {
  const child = spawn(process.execPath, [script], {
    cwd: projectDirectory,
    env: {
      ...process.env,
      ...environment,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";

  const ready = new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`simulator readiness timeout: ${path.basename(script)}`));
    }, safetyTimeoutMs);

    const inspect = () => {
      const match = readyPattern.exec(stdout);
      if (match) {
        clearTimeout(timer);
        resolve(match);
      }
    };

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
      inspect();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      reject(
        new Error(
          `simulator exited before ready: ${path.basename(script)} code=${code} stderr=${stderr.trim()}`,
        ),
      );
    });
  });

  const match = await ready;
  return {
    child,
    match,
    output() {
      return { stdout, stderr };
    },
  };
}

async function stopSimulator(simulator) {
  const child = simulator?.child;
  if (!child || child.exitCode !== null || child.signalCode !== null) {
    return;
  }
  const exited = once(child, "exit");
  child.kill("SIGTERM");
  let timerId;
  const timeout = new Promise((_, reject) => {
    timerId = setTimeout(
      () => reject(new Error("simulator shutdown timeout")),
      safetyTimeoutMs,
    );
  });
  try {
    await Promise.race([exited, timeout]);
  } catch (error) {
    child.kill("SIGKILL");
    await once(child, "exit").catch(() => {});
    throw error;
  } finally {
    clearTimeout(timerId);
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const value = await response.json();
  return { response, value };
}

async function postJson(baseUrl, pathname, value) {
  return fetchJson(new URL(pathname, baseUrl), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(value),
  });
}

async function waitForPredicate(predicate, label) {
  const deadline = Date.now() + safetyTimeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) {
      return;
    }
    await new Promise((resolve) => setImmediate(resolve));
  }
  throw new Error(`${label} timeout`);
}

function sendMessageBody(clientId, text = "pong") {
  return {
    msg: {
      client_id: clientId,
      to_user_id: "sim-authorized-user",
      context_token: "sim-context-1",
      item_list: [{ type: 1, text_item: { text } }],
    },
  };
}

class RpcPeer {
  constructor(socket) {
    this.socket = socket;
    this.sequence = 0;
    this.queue = [];
    this.waiters = [];
    socket.on("message", (raw) => {
      const message = JSON.parse(raw.toString("utf8"));
      const waiterIndex = this.waiters.findIndex((entry) => entry.predicate(message));
      if (waiterIndex >= 0) {
        const [waiter] = this.waiters.splice(waiterIndex, 1);
        clearTimeout(waiter.timer);
        waiter.resolve(message);
        return;
      }
      this.queue.push(message);
    });
    socket.on("close", () => {
      const waiters = this.waiters.splice(0);
      for (const waiter of waiters) {
        clearTimeout(waiter.timer);
        waiter.reject(new Error("websocket closed"));
      }
    });
  }

  static async connect(endpoint) {
    const socket = new WebSocket(endpoint);
    await once(socket, "open");
    return new RpcPeer(socket);
  }

  waitFor(predicate, label = "rpc message") {
    const queueIndex = this.queue.findIndex(predicate);
    if (queueIndex >= 0) {
      return Promise.resolve(this.queue.splice(queueIndex, 1)[0]);
    }
    return new Promise((resolve, reject) => {
      const entry = {
        predicate,
        resolve,
        reject,
        timer: setTimeout(() => {
          const index = this.waiters.indexOf(entry);
          if (index >= 0) {
            this.waiters.splice(index, 1);
          }
          reject(new Error(`${label} timeout`));
        }, safetyTimeoutMs),
      };
      this.waiters.push(entry);
    });
  }

  request(method, params = {}) {
    const id = ++this.sequence;
    const response = this.waitFor(
      (message) => message.id === id && !message.method,
      `${method} response`,
    );
    this.socket.send(JSON.stringify({ id, method, params }));
    return response;
  }

  notify(method, params = {}) {
    this.socket.send(JSON.stringify({ method, params }));
  }

  respond(id, result) {
    this.socket.send(JSON.stringify({ id, result }));
  }

  rawRequest(method, params = {}) {
    const id = ++this.sequence;
    this.socket.send(JSON.stringify({ id, method, params }));
    return id;
  }

  async close() {
    if (this.socket.readyState === WebSocket.CLOSED) {
      return;
    }
    const closed = once(this.socket, "close");
    this.socket.close();
    await closed;
  }
}

async function initializePeer(peer) {
  const response = await peer.request("initialize", {
    clientInfo: {
      name: "cyberboss_simulator_contract",
      title: "CyberBoss simulator contract",
      version: "0.0.0.4",
    },
    capabilities: {
      experimentalApi: true,
    },
  });
  assert.equal(response.error, undefined);
  assert.equal(response.result.serverInfo.name, "cyberboss-sim");
  peer.notify("initialized", {});
}

async function startThread(peer) {
  const response = await peer.request("thread/start", { model: "sim-model" });
  assert.equal(response.error, undefined);
  return response.result.thread.id;
}

async function setScenario(peer, scenario) {
  const response = await peer.request("simulator/setScenario", { scenario });
  assert.equal(response.error, undefined);
  assert.equal(response.result.next_scenario, scenario);
}

async function startTurn(peer, threadId, text = "ping") {
  const response = await peer.request("turn/start", {
    threadId,
    input: [{ type: "text", text }],
  });
  assert.equal(response.error, undefined);
  return response.result.turn.id;
}

async function collectUntilTerminal(peer, turnId) {
  const events = [];
  while (true) {
    const message = await peer.waitFor(
      (candidate) => (
        candidate.params?.turnId === turnId
        || candidate.params?.turn?.id === turnId
      ),
      `terminal event for ${turnId}`,
    );
    events.push(message);
    if (message.method === "turn/completed" || message.method === "turn/failed") {
      return events;
    }
  }
}

test("WeChat iLink simulator covers login, cursor, duplicate and failure contracts", async (t) => {
  const simulator = await startSimulator(
    weixinSimulator,
    {
      SIM_WEIXIN_HOST: "127.0.0.1",
      SIM_WEIXIN_PORT: "0",
    },
    /WEIXIN_SIMULATOR=READY base_url=(http:\/\/127\.0\.0\.1:\d+\/)/,
  );
  t.after(() => stopSimulator(simulator));
  const baseUrl = simulator.match[1];

  const qr = await fetchJson(new URL("/ilink/bot/get_bot_qrcode", baseUrl));
  assert.equal(qr.response.status, 200);
  assert.equal(qr.value.qrcode, "sim-qrcode-not-real");
  assert.match(qr.value.qrcode_img_content, /\/admin\/fixture$/);

  const qrStatus = await fetchJson(
    new URL("/ilink/bot/get_qrcode_status?qrcode=sim-qrcode-not-real", baseUrl),
  );
  assert.equal(qrStatus.value.status, "confirmed");
  assert.equal(qrStatus.value.ilink_bot_id, "sim-ilink-bot");

  const empty = await postJson(baseUrl, "/ilink/bot/getupdates", {
    get_updates_buf: "0",
  });
  assert.deepEqual(empty.value.msgs, []);
  assert.equal(empty.value.get_updates_buf, "0");

  const injected = await postJson(baseUrl, "/admin/inject", {
    text: "ping",
    count: 3,
  });
  assert.equal(injected.value.injected, 3);

  const firstBatch = await postJson(baseUrl, "/ilink/bot/getupdates", {
    get_updates_buf: "0",
  });
  assert.equal(firstBatch.value.msgs.length, 3);
  assert.equal(firstBatch.value.get_updates_buf, "3");
  assert.equal(
    new Set(firstBatch.value.msgs.map((item) => item.context_token)).size,
    3,
  );

  const replay = await postJson(baseUrl, "/admin/replay", {
    message_id: firstBatch.value.msgs[0].message_id,
  });
  assert.equal(replay.value.cursor, "4");
  const replayBatch = await postJson(baseUrl, "/ilink/bot/getupdates", {
    get_updates_buf: "3",
  });
  assert.equal(replayBatch.value.msgs.length, 1);
  assert.equal(
    replayBatch.value.msgs[0].message_id,
    firstBatch.value.msgs[0].message_id,
  );
  assert.equal(replayBatch.value.get_updates_buf, "4");

  await postJson(baseUrl, "/admin/inject", {
    text: "out-of-order",
    count: 3,
  });
  await postJson(baseUrl, "/admin/order", { next: "reverse" });
  const reverseBatch = await postJson(baseUrl, "/ilink/bot/getupdates", {
    get_updates_buf: "4",
  });
  assert.deepEqual(
    reverseBatch.value.msgs.map((item) => item.seq),
    [7, 6, 5],
  );
  assert.equal(reverseBatch.value.get_updates_buf, "7");

  const firstSend = await postJson(
    baseUrl,
    "/ilink/bot/sendmessage",
    sendMessageBody("client-idempotent"),
  );
  const duplicateSend = await postJson(
    baseUrl,
    "/ilink/bot/sendmessage",
    sendMessageBody("client-idempotent"),
  );
  assert.equal(firstSend.value.duplicate_ack, false);
  assert.equal(duplicateSend.value.duplicate_ack, true);
  assert.equal(
    duplicateSend.value.provider_receipt_id,
    firstSend.value.provider_receipt_id,
  );

  for (const status of ["401", "403", "429", "500", "503"]) {
    await postJson(baseUrl, "/admin/fault", { getupdates: [status] });
    const fault = await postJson(baseUrl, "/ilink/bot/getupdates", {
      get_updates_buf: "7",
    });
    assert.equal(fault.response.status, Number(status));
    if (status === "429" || status === "503") {
      assert.equal(fault.response.headers.get("retry-after"), "0");
    }
  }

  await postJson(baseUrl, "/admin/fault", { getupdates: ["timeout"] });
  const timeout = await postJson(baseUrl, "/ilink/bot/getupdates", {
    get_updates_buf: "7",
  });
  assert.equal(timeout.response.status, 504);
  assert.equal(
    timeout.response.headers.get("x-cyberboss-simulated-transport-fault"),
    "timeout",
  );

  await postJson(baseUrl, "/admin/fault", {
    getupdates: ["connection_reset"],
  });
  await assert.rejects(
    postJson(baseUrl, "/ilink/bot/getupdates", { get_updates_buf: "7" }),
    /fetch failed|socket|other side closed/i,
  );

  for (const status of ["401", "403", "429", "500", "503"]) {
    await postJson(baseUrl, "/admin/fault", { sendmessage: [status] });
    const fault = await postJson(
      baseUrl,
      "/ilink/bot/sendmessage",
      sendMessageBody(`client-http-${status}`),
    );
    assert.equal(fault.response.status, Number(status));
  }

  await postJson(baseUrl, "/admin/fault", { sendmessage: ["timeout"] });
  const sendTimeout = await postJson(
    baseUrl,
    "/ilink/bot/sendmessage",
    sendMessageBody("client-timeout"),
  );
  assert.equal(sendTimeout.response.status, 504);

  await postJson(baseUrl, "/admin/fault", {
    sendmessage: ["connection_reset"],
  });
  await assert.rejects(
    postJson(
      baseUrl,
      "/ilink/bot/sendmessage",
      sendMessageBody("client-reset"),
    ),
    /fetch failed|socket|other side closed/i,
  );

  await postJson(baseUrl, "/admin/fault", {
    sendmessage: ["unknown_outcome"],
  });
  await assert.rejects(
    postJson(
      baseUrl,
      "/ilink/bot/sendmessage",
      sendMessageBody("client-unknown"),
    ),
    /fetch failed|socket|other side closed/i,
  );
  const unknownRetry = await postJson(
    baseUrl,
    "/ilink/bot/sendmessage",
    sendMessageBody("client-unknown"),
  );
  assert.equal(unknownRetry.value.duplicate_ack, true);

  const sent = await fetchJson(new URL("/admin/sent", baseUrl));
  const unknownReceipts = sent.value.sent.filter(
    (entry) => entry.client_id === "client-unknown",
  );
  assert.equal(unknownReceipts.length, 1);
  assert.equal(unknownReceipts[0].outcome, "unknown");

  const fixturePage = await fetch(new URL("/admin/fixture", baseUrl));
  const fixtureHtml = await fixturePage.text();
  assert.equal(fixturePage.status, 200);
  assert.match(fixtureHtml, /SIMULATOR FIXTURE — NOT REAL WECHAT/);
  assert.match(fixtureHtml, /claim_level=fixture/);
  assert.doesNotMatch(fixtureHtml, /Bearer\s+[A-Za-z0-9._-]+/);
});

test("WeChat simulator can hold an empty cloud poll until synthetic input arrives", async (t) => {
  const simulator = await startSimulator(
    weixinSimulator,
    {
      SIM_WEIXIN_HOST: "127.0.0.1",
      SIM_WEIXIN_PORT: "0",
      SIM_WEIXIN_HOLD_EMPTY_POLLS: "true",
    },
    /WEIXIN_SIMULATOR=READY base_url=(http:\/\/127\.0\.0\.1:\d+\/)/,
  );
  t.after(() => stopSimulator(simulator));
  const baseUrl = simulator.match[1];
  const pending = postJson(baseUrl, "/ilink/bot/getupdates", {
    get_updates_buf: "0",
  });
  await waitForPredicate(async () => {
    const state = await fetchJson(new URL("/admin/state", baseUrl));
    return state.value.pending_updates === 1;
  }, "pending update registration");
  const injected = await postJson(baseUrl, "/admin/inject", {
    text: "cloud-ready",
    count: 1,
  });
  assert.equal(injected.value.injected, 1);
  const result = await pending;
  assert.equal(result.response.status, 200);
  assert.equal(result.value.msgs.length, 1);
  assert.equal(result.value.msgs[0].item_list[0].text_item.text, "cloud-ready");
  assert.equal(result.value.get_updates_buf, "1");
});

test("Codex simulator covers handshake, progress, approval, failures and false-success", async (t) => {
  const simulator = await startSimulator(
    codexSimulator,
    {
      SIM_CODEX_HOST: "127.0.0.1",
      SIM_CODEX_PORT: "0",
      SIM_CODEX_MAX_ACTIVE_TURNS: "1",
    },
    /CODEX_SIMULATOR=READY endpoint=(ws:\/\/127\.0\.0\.1:\d+)/,
  );
  t.after(() => stopSimulator(simulator));
  const peer = await RpcPeer.connect(simulator.match[1]);
  t.after(() => peer.close());

  const beforeInitialize = await peer.request("thread/start", {});
  assert.equal(beforeInitialize.error.message, "Not initialized");

  await initializePeer(peer);
  const repeatedInitialize = await peer.request("initialize", {
    clientInfo: { name: "duplicate", title: "duplicate", version: "0" },
  });
  assert.equal(repeatedInitialize.error.message, "Already initialized");

  const threadId = await startThread(peer);

  await setScenario(peer, "success");
  const successTurnId = await startTurn(peer, threadId, "ping");
  const successEvents = await collectUntilTerminal(peer, successTurnId);
  assert.deepEqual(
    new Set(successEvents.map((event) => event.method)),
    new Set([
      "turn/started",
      "item/started",
      "item/agentMessage/delta",
      "item/completed",
      "turn/completed",
    ]),
  );
  assert.ok(successEvents.every((event) => !Object.hasOwn(event, "jsonrpc")));
  const deltas = successEvents
    .filter((event) => event.method === "item/agentMessage/delta")
    .map((event) => event.params.delta)
    .join("");
  assert.equal(deltas, "SIMULATED_CODEX_RESULT: ping");

  await setScenario(peer, "approval");
  const approvalTurnId = await startTurn(peer, threadId, "approval");
  const approvalRequest = await peer.waitFor(
    (message) => (
      message.method === "item/commandExecution/requestApproval"
      && message.params?.turnId === approvalTurnId
    ),
    "approval request",
  );
  assert.deepEqual(approvalRequest.params.command, ["printf", "fixture"]);
  peer.respond(approvalRequest.id, { decision: "accept" });
  const approvalEvents = await collectUntilTerminal(peer, approvalTurnId);
  assert.equal(approvalEvents.at(-1).method, "turn/completed");

  await setScenario(peer, "retryable_error");
  const retryableTurnId = await startTurn(peer, threadId, "retryable");
  const retryableEvents = await collectUntilTerminal(peer, retryableTurnId);
  assert.equal(retryableEvents.at(-1).method, "turn/failed");
  assert.equal(retryableEvents.at(-1).params.turn.error.retryable, true);

  await setScenario(peer, "terminal_error");
  const terminalTurnId = await startTurn(peer, threadId, "terminal");
  const terminalEvents = await collectUntilTerminal(peer, terminalTurnId);
  assert.equal(terminalEvents.at(-1).method, "turn/failed");
  assert.equal(terminalEvents.at(-1).params.turn.error.retryable, false);

  await setScenario(peer, "cancel_hold");
  const heldTurnId = await startTurn(peer, threadId, "hold");
  await peer.waitFor(
    (message) => (
      message.method === "turn/started"
      && message.params?.turnId === heldTurnId
    ),
    "held turn start",
  );
  const overloaded = await peer.request("turn/start", {
    threadId,
    input: [{ type: "text", text: "must overload" }],
  });
  assert.equal(overloaded.error.code, -32001);
  assert.equal(overloaded.error.message, "Server overloaded; retry later.");
  const interrupted = await peer.request("turn/interrupt", {
    threadId,
    turnId: heldTurnId,
  });
  assert.equal(interrupted.error, undefined);
  const interruptedEvents = await collectUntilTerminal(peer, heldTurnId);
  assert.equal(interruptedEvents.at(-1).params.turn.status, "interrupted");

  await setScenario(peer, "false_success");
  const falseSuccessTurnId = await startTurn(peer, threadId, "false success");
  const falseSuccessEvents = await collectUntilTerminal(peer, falseSuccessTurnId);
  assert.deepEqual(
    falseSuccessEvents.map((event) => event.method),
    ["turn/started", "turn/completed"],
  );
  const falseSuccessState = await peer.request("simulator/state", {});
  const falseTurn = falseSuccessState.result.turns.find(
    (turn) => turn.id === falseSuccessTurnId,
  );
  assert.equal(falseTurn.artifact_count, 0);
  assert.equal(falseTurn.oracle, "false_success");

  await setScenario(peer, "late_duplicate");
  const duplicateTurnId = await startTurn(peer, threadId, "deduplicate");
  const duplicateEvents = [];
  while (true) {
    const event = await peer.waitFor(
      (message) => (
        message.params?.turnId === duplicateTurnId
        || message.params?.turn?.id === duplicateTurnId
      ),
      "late/duplicate fixture",
    );
    duplicateEvents.push(event);
    if (event.method === "simulator/lateEventDone") {
      break;
    }
  }
  assert.equal(
    duplicateEvents.filter((event) => event.method === "item/completed").length,
    2,
  );
  assert.ok(
    duplicateEvents.findIndex((event) => event.method === "turn/completed")
      < duplicateEvents.findIndex(
        (event) => (
          event.method === "item/agentMessage/delta"
          && event.params.delta === "LATE_EVENT_MUST_BE_IGNORED"
        ),
      ),
  );
  const state = await peer.request("simulator/state", {});
  const completed = state.result.turns.find((turn) => turn.id === successTurnId);
  assert.equal(completed.oracle, "valid_completion");
  assert.equal(completed.artifact_count, 1);
  assert.match(completed.artifact_sha256[0], /^[a-f0-9]{64}$/);
});

test("Codex simulator process crash is reconnectable without claiming success", async () => {
  const first = await startSimulator(
    codexSimulator,
    {
      SIM_CODEX_HOST: "127.0.0.1",
      SIM_CODEX_PORT: "0",
    },
    /CODEX_SIMULATOR=READY endpoint=ws:\/\/127\.0\.0\.1:(\d+)/,
  );
  const port = first.match[1];
  const firstPeer = await RpcPeer.connect(`ws://127.0.0.1:${port}`);
  await initializePeer(firstPeer);
  const firstThread = await startThread(firstPeer);
  await setScenario(firstPeer, "process_crash");
  const exit = once(first.child, "exit");
  firstPeer.rawRequest("turn/start", {
    threadId: firstThread,
    input: [{ type: "text", text: "crash" }],
  });
  const [exitCode] = await exit;
  assert.equal(exitCode, 75);
  assert.equal(
    first.output().stdout.includes("SIMULATED_CODEX_RESULT"),
    false,
  );

  const second = await startSimulator(
    codexSimulator,
    {
      SIM_CODEX_HOST: "127.0.0.1",
      SIM_CODEX_PORT: port,
    },
    /CODEX_SIMULATOR=READY endpoint=(ws:\/\/127\.0\.0\.1:\d+)/,
  );
  try {
    const secondPeer = await RpcPeer.connect(second.match[1]);
    try {
      await initializePeer(secondPeer);
      const secondThread = await startThread(secondPeer);
      const turnId = await startTurn(secondPeer, secondThread, "after reconnect");
      const events = await collectUntilTerminal(secondPeer, turnId);
      assert.equal(events.at(-1).method, "turn/completed");
      assert.ok(events.some((event) => event.method === "item/completed"));
    } finally {
      await secondPeer.close();
    }
  } finally {
    await stopSimulator(second);
  }
});

test("both simulators fail closed on non-loopback bind requests", () => {
  for (const [script, environmentKey] of [
    [weixinSimulator, "SIM_WEIXIN_HOST"],
    [codexSimulator, "SIM_CODEX_HOST"],
  ]) {
    const result = spawnSync(process.execPath, [script], {
      cwd: projectDirectory,
      env: {
        ...process.env,
        [environmentKey]: "0.0.0.0",
      },
      encoding: "utf8",
      timeout: safetyTimeoutMs,
    });
    assert.equal(result.status, 64);
    assert.match(`${result.stdout}${result.stderr}`, /loopback_required/);
  }
});

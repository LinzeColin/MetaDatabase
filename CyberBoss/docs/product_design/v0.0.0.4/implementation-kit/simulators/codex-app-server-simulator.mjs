#!/usr/bin/env node
// Contract fixture only. It deliberately implements the bounded CyberBoss MVP
// subset and simulator-only control methods; it is not an OpenAI service.
import crypto from "node:crypto";
import { createRequire } from "node:module";

const requireFromApp = createRequire(
  new URL("../../../../../app/package.json", import.meta.url),
);
const { WebSocket, WebSocketServer } = requireFromApp("ws");

const host = process.env.SIM_CODEX_HOST || "127.0.0.1";
const requestedPort = Number(process.env.SIM_CODEX_PORT || 18765);
const maxActiveTurns = Math.max(
  1,
  Number(process.env.SIM_CODEX_MAX_ACTIVE_TURNS || 1),
);
const scenarios = new Set([
  "success",
  "approval",
  "retryable_error",
  "terminal_error",
  "overload",
  "cancel_hold",
  "false_success",
  "late_duplicate",
  "process_crash",
]);

if (!isLoopbackHost(host)) {
  console.error("CODEX_SIMULATOR=REFUSED reason=loopback_required");
  process.exit(64);
}
if (!Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) {
  console.error("CODEX_SIMULATOR=REFUSED reason=invalid_port");
  process.exit(64);
}

const wss = new WebSocketServer({ host, port: requestedPort });
const threads = new Map();
const turns = new Map();
const pendingApprovals = new Map();
let threadSequence = 0;
let turnSequence = 0;
let itemSequence = 0;
let approvalSequence = 0;
let activeTurnCount = 0;

function isLoopbackHost(value) {
  return value === "127.0.0.1" || value === "::1" || value === "localhost";
}

function send(ws, payload) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

function response(ws, id, result = {}) {
  send(ws, { id, result });
}

function rpcError(ws, id, code, message, data = undefined) {
  send(ws, {
    id,
    error: {
      code,
      message,
      ...(data === undefined ? {} : { data }),
    },
  });
}

function notification(ws, method, params) {
  send(ws, { method, params });
}

function serverRequest(ws, id, method, params) {
  send(ws, { id, method, params });
}

function nextId(prefix, value) {
  return `${prefix}-${String(value).padStart(4, "0")}`;
}

function safeInputText(params) {
  const input = Array.isArray(params?.input) ? params.input : [];
  return input
    .map((entry) => (entry?.type === "text" ? String(entry.text || "") : ""))
    .filter(Boolean)
    .join("\n")
    .slice(0, 400);
}

function artifactFor(text) {
  const normalized = `SIMULATED_CODEX_RESULT: ${text || "Completed."}`;
  return {
    text: normalized,
    sha256: crypto.createHash("sha256").update(normalized).digest("hex"),
  };
}

function startItem(ws, turn, type = "agentMessage") {
  const itemId = nextId("item", ++itemSequence);
  notification(ws, "item/started", {
    threadId: turn.threadId,
    turnId: turn.id,
    item: { id: itemId, type },
  });
  return itemId;
}

function completeArtifact(ws, turn, text, { duplicate = false } = {}) {
  const artifact = artifactFor(text);
  const itemId = startItem(ws, turn);
  const midpoint = Math.max(1, Math.floor(artifact.text.length / 2));
  notification(ws, "item/agentMessage/delta", {
    threadId: turn.threadId,
    turnId: turn.id,
    itemId,
    delta: artifact.text.slice(0, midpoint),
  });
  notification(ws, "item/agentMessage/delta", {
    threadId: turn.threadId,
    turnId: turn.id,
    itemId,
    delta: artifact.text.slice(midpoint),
  });
  const completed = {
    threadId: turn.threadId,
    turnId: turn.id,
    item: {
      id: itemId,
      type: "agentMessage",
      text: artifact.text,
    },
  };
  notification(ws, "item/completed", completed);
  if (duplicate) {
    notification(ws, "item/completed", completed);
  }
  turn.artifacts.push({
    itemId,
    sha256: artifact.sha256,
    text: artifact.text,
  });
  return { artifact, itemId, completed };
}

function completeTurn(ws, turn, status = "completed") {
  if (!turn.active) {
    return;
  }
  turn.active = false;
  activeTurnCount = Math.max(0, activeTurnCount - 1);
  turn.status = status;
  notification(ws, "turn/completed", {
    threadId: turn.threadId,
    turnId: turn.id,
    turn: { id: turn.id, status },
  });
}

function failTurn(ws, turn, { retryable }) {
  if (!turn.active) {
    return;
  }
  turn.active = false;
  activeTurnCount = Math.max(0, activeTurnCount - 1);
  turn.status = retryable ? "failed_retryable" : "failed_terminal";
  notification(ws, "turn/failed", {
    threadId: turn.threadId,
    turnId: turn.id,
    turn: {
      id: turn.id,
      status: "failed",
      error: {
        message: retryable
          ? "injected retryable runtime failure"
          : "injected terminal runtime failure",
        retryable,
      },
    },
  });
}

function stateSnapshot() {
  return {
    claim_level: "fixture",
    active_turns: activeTurnCount,
    max_active_turns: maxActiveTurns,
    threads: threads.size,
    turns: Array.from(turns.values()).map((turn) => ({
      id: turn.id,
      thread_id: turn.threadId,
      scenario: turn.scenario,
      status: turn.status,
      artifact_count: turn.artifacts.length,
      artifact_sha256: turn.artifacts.map((artifact) => artifact.sha256),
      oracle:
        turn.status === "completed" && turn.artifacts.length > 0
          ? "valid_completion"
          : turn.status === "completed"
            ? "false_success"
            : "not_completed",
    })),
  };
}

function handleApprovalResponse(ws, msg) {
  const key = String(msg.id ?? "");
  const pending = pendingApprovals.get(key);
  if (!pending) {
    return false;
  }
  pendingApprovals.delete(key);
  const { turn, itemId } = pending;
  const accepted =
    msg?.result?.decision === "accept"
    || msg?.result?.action === "accept"
    || msg?.result?.approved === true;
  notification(ws, "item/completed", {
    threadId: turn.threadId,
    turnId: turn.id,
    item: {
      id: itemId,
      type: "commandExecution",
      status: accepted ? "completed" : "declined",
    },
  });
  if (!accepted) {
    failTurn(ws, turn, { retryable: false });
    return true;
  }
  completeArtifact(ws, turn, "approval accepted");
  completeTurn(ws, turn);
  return true;
}

function handleTurnStart(ws, msg, connection) {
  const scenario = connection.nextScenario;
  connection.nextScenario = "success";
  if (scenario === "overload" || activeTurnCount >= maxActiveTurns) {
    rpcError(ws, msg.id, -32001, "Server overloaded; retry later.");
    return;
  }

  const threadId = String(msg.params?.threadId || "");
  if (!threadId || !threads.has(threadId)) {
    rpcError(ws, msg.id, -32602, "thread/start requires an existing threadId");
    return;
  }

  const turnId = nextId("turn", ++turnSequence);
  const turn = {
    id: turnId,
    threadId,
    scenario,
    status: "running",
    active: true,
    artifacts: [],
  };
  turns.set(turnId, turn);
  activeTurnCount += 1;
  response(ws, msg.id, { turn: { id: turnId, status: "running" } });
  notification(ws, "turn/started", {
    threadId,
    turnId,
    turn: { id: turnId, status: "running" },
  });

  if (scenario === "process_crash") {
    process.exitCode = 75;
    setImmediate(() => process.exit(75));
    return;
  }
  if (scenario === "cancel_hold") {
    return;
  }
  if (scenario === "retryable_error") {
    failTurn(ws, turn, { retryable: true });
    return;
  }
  if (scenario === "terminal_error") {
    failTurn(ws, turn, { retryable: false });
    return;
  }
  if (scenario === "false_success") {
    completeTurn(ws, turn);
    return;
  }
  if (scenario === "approval") {
    const itemId = startItem(ws, turn, "commandExecution");
    const approvalId = nextId("approval", ++approvalSequence);
    pendingApprovals.set(approvalId, { turn, itemId });
    serverRequest(ws, approvalId, "item/commandExecution/requestApproval", {
      threadId,
      turnId,
      itemId,
      reason: "synthetic command approval fixture",
      command: ["printf", "fixture"],
    });
    return;
  }

  const inputText = safeInputText(msg.params);
  const duplicate = scenario === "late_duplicate";
  const completed = completeArtifact(ws, turn, inputText, { duplicate });
  completeTurn(ws, turn);
  if (scenario === "late_duplicate") {
    notification(ws, "item/agentMessage/delta", {
      threadId,
      turnId,
      itemId: completed.itemId,
      delta: "LATE_EVENT_MUST_BE_IGNORED",
    });
    notification(ws, "simulator/lateEventDone", {
      threadId,
      turnId,
      itemId: completed.itemId,
    });
  }
}

wss.on("connection", (ws) => {
  const connection = {
    initializeSeen: false,
    initialized: false,
    nextScenario: "success",
  };

  ws.on("message", (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw.toString("utf8"));
    } catch {
      return;
    }

    if (!msg.method && msg.id != null && handleApprovalResponse(ws, msg)) {
      return;
    }

    const method = String(msg.method || "");
    if (msg.id == null) {
      if (method === "initialized" && connection.initializeSeen) {
        connection.initialized = true;
      }
      return;
    }

    if (method === "initialize") {
      if (connection.initializeSeen) {
        rpcError(ws, msg.id, -32600, "Already initialized");
        return;
      }
      connection.initializeSeen = true;
      response(ws, msg.id, {
        serverInfo: { name: "cyberboss-sim", version: "0.0.0.4" },
        userAgent: "cyberboss-sim/0.0.0.4",
        platformFamily: "unix",
        platformOs: "linux",
      });
      return;
    }

    if (!connection.initialized) {
      rpcError(ws, msg.id, -32002, "Not initialized");
      return;
    }

    if (method === "simulator/setScenario") {
      const scenario = String(msg.params?.scenario || "");
      if (!scenarios.has(scenario)) {
        rpcError(ws, msg.id, -32602, "Unknown simulator scenario");
        return;
      }
      connection.nextScenario = scenario;
      response(ws, msg.id, { next_scenario: scenario, claim_level: "fixture" });
      return;
    }
    if (method === "simulator/state") {
      response(ws, msg.id, stateSnapshot());
      return;
    }
    if (method === "model/list") {
      response(ws, msg.id, {
        data: [
          {
            id: "sim-model",
            model: "sim-model",
            inputModalities: ["text"],
          },
        ],
      });
      return;
    }
    if (method === "thread/start") {
      const threadId = nextId("thread", ++threadSequence);
      threads.set(threadId, { id: threadId, status: "active" });
      response(ws, msg.id, { thread: { id: threadId } });
      notification(ws, "thread/started", { thread: { id: threadId } });
      return;
    }
    if (method === "thread/resume" || method === "thread/compact/start") {
      const threadId = String(msg.params?.threadId || "");
      if (!threadId || !threads.has(threadId)) {
        rpcError(ws, msg.id, -32602, `${method} requires an existing threadId`);
        return;
      }
      response(ws, msg.id, { thread: { id: threadId } });
      return;
    }
    if (method === "thread/list") {
      response(ws, msg.id, {
        data: Array.from(threads.values()).map((thread) => ({ id: thread.id })),
        nextCursor: null,
      });
      return;
    }
    if (method === "turn/interrupt") {
      const turnId = String(msg.params?.turnId || "");
      const turn = turns.get(turnId);
      if (!turn || !turn.active) {
        rpcError(ws, msg.id, -32602, "turn/interrupt requires an active turn");
        return;
      }
      response(ws, msg.id, {});
      completeTurn(ws, turn, "interrupted");
      return;
    }
    if (method === "turn/start") {
      handleTurnStart(ws, msg, connection);
      return;
    }
    rpcError(ws, msg.id, -32601, `method not implemented by simulator: ${method}`);
  });
});

wss.on("listening", () => {
  const address = wss.address();
  const activePort = typeof address === "object" && address ? address.port : requestedPort;
  console.log(
    `CODEX_SIMULATOR=READY endpoint=ws://${host}:${activePort} claim_level=fixture max_active_turns=${maxActiveTurns}`,
  );
});

function shutdown() {
  for (const client of wss.clients) {
    client.close();
  }
  wss.close(() => process.exit(0));
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);

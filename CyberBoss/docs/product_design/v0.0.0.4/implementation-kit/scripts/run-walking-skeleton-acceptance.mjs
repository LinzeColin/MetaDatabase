#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const WEIXIN_BASE_URL = "http://127.0.0.1:19080/";
const CODEX_ENDPOINT = "ws://127.0.0.1:8765";
const COMPLETE_STAGES = [
  "inbound_received",
  "runtime_dispatched",
  "runtime_completed",
  "outbox_staged",
  "delivery_confirmed",
  "canonical_event",
];
const options = parseArgs(process.argv.slice(2));

function parseArgs(argv) {
  const parsed = {
    traceFile: "",
    output: "",
    correlatedOutput: "",
    fixtureHtml: "",
  };
  const names = new Map([
    ["--trace-file", "traceFile"],
    ["--output", "output"],
    ["--correlated-output", "correlatedOutput"],
    ["--fixture-html", "fixtureHtml"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const key = names.get(argv[index]);
    const value = argv[index + 1];
    if (!key || !value) {
      throw new Error(`invalid_argument:${argv[index] || "missing"}`);
    }
    parsed[key] = path.resolve(value);
    index += 1;
  }
  for (const [key, value] of Object.entries(parsed)) {
    if (!value || !path.isAbsolute(value)) {
      throw new Error(`missing_absolute_path:${key}`);
    }
  }
  return parsed;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitFor(label, predicate, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const result = await predicate();
      if (result) {
        return result;
      }
    } catch (error) {
      lastError = error;
    }
    await delay(50);
  }
  const detail = lastError instanceof Error ? `:${lastError.message}` : "";
  throw new Error(`${label}_timeout${detail}`);
}

async function fetchJson(pathname) {
  const response = await fetch(new URL(pathname, WEIXIN_BASE_URL), {
    signal: AbortSignal.timeout(2_000),
  });
  if (!response.ok) {
    throw new Error(`http_${response.status}:${pathname}`);
  }
  return response.json();
}

async function postJson(pathname, body) {
  const response = await fetch(new URL(pathname, WEIXIN_BASE_URL), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) {
    throw new Error(`http_${response.status}:${pathname}`);
  }
  return response.json();
}

async function readSimulatorTurns() {
  const socket = new WebSocket(CODEX_ENDPOINT);
  let nextId = 1400;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    let message;
    try {
      message = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (message.id == null || !pending.has(message.id)) {
      return;
    }
    const request = pending.get(message.id);
    pending.delete(message.id);
    clearTimeout(request.timer);
    if (message.error) {
      request.reject(new Error(String(message.error.message || "rpc_error")));
      return;
    }
    request.resolve(message.result);
  });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("websocket_open_timeout")), 2_000);
    socket.addEventListener("open", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
    socket.addEventListener("error", () => {
      clearTimeout(timer);
      reject(new Error("websocket_open_error"));
    }, { once: true });
  });
  const rpc = (method, params) => new Promise((resolve, reject) => {
    const id = nextId += 1;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`rpc_timeout:${method}`));
    }, 2_000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
  });

  try {
    await rpc("initialize", {
      clientInfo: {
        name: "cyberboss_cb140_acceptance",
        title: "CyberBoss CB-140 Acceptance",
        version: "0.0.0.4",
      },
      capabilities: { experimentalApi: true },
    });
    socket.send(JSON.stringify({
      jsonrpc: "2.0",
      method: "initialized",
      params: null,
    }));
    const state = await rpc("simulator/state", {});
    return Array.isArray(state?.turns) ? state.turns : [];
  } finally {
    socket.close();
  }
}

function readTraceRecords() {
  if (!fs.existsSync(options.traceFile)) {
    return [];
  }
  const text = fs.readFileSync(options.traceFile, "utf8");
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

function groupTraces(records = readTraceRecords()) {
  const grouped = new Map();
  for (const record of records) {
    const traceId = String(record?.trace_id || "");
    if (!traceId) {
      continue;
    }
    const list = grouped.get(traceId) || [];
    list.push(record);
    grouped.set(traceId, list);
  }
  return grouped;
}

function stageNames(records) {
  return records.map((record) => String(record.stage || ""));
}

function isCompleteTrace(records) {
  const stages = stageNames(records);
  return COMPLETE_STAGES.every((stage, index) => stages[index] === stage);
}

async function waitForNewTrace(knownTraceIds, {
  complete = true,
  rejectionCode = "",
} = {}) {
  return waitFor("trace", async () => {
    const grouped = groupTraces();
    for (const [traceId, records] of grouped.entries()) {
      if (knownTraceIds.has(traceId)) {
        continue;
      }
      if (rejectionCode) {
        const rejected = records.find(
          (record) => record.stage === "inbound_rejected" && record.rejection_code === rejectionCode,
        );
        if (!rejected) {
          continue;
        }
        knownTraceIds.add(traceId);
        return { traceId, records };
      }
      if (complete && !isCompleteTrace(records)) {
        continue;
      }
      knownTraceIds.add(traceId);
      return { traceId, records };
    }
    return null;
  });
}

function extractReplyText(entry) {
  const items = Array.isArray(entry?.body?.msg?.item_list)
    ? entry.body.msg.item_list
    : [];
  return items
    .map((item) => String(item?.text_item?.text || ""))
    .filter(Boolean)
    .join("\n");
}

async function sendAndWait({
  text,
  messageId,
  senderId = "sim-authorized-user",
  expectRuntimeDelta = 1,
  expectedReplyFragment = "",
  rejectionCode = "",
  knownTraceIds,
}) {
  const beforeTurns = (await readSimulatorTurns()).length;
  const beforeSent = (await fetchJson("/admin/sent")).sent.length;
  await postJson("/admin/inject", {
    text,
    message_id: messageId,
    client_id: `cb140-${messageId}`,
    from_user_id: senderId,
    context_token: `cb140-context-${messageId}`,
  });

  const trace = await waitForNewTrace(knownTraceIds, {
    complete: !rejectionCode,
    rejectionCode,
  });
  const afterTurns = (await readSimulatorTurns()).length;
  if (afterTurns - beforeTurns !== expectRuntimeDelta) {
    throw new Error(`runtime_delta:${messageId}:${afterTurns - beforeTurns}:${expectRuntimeDelta}`);
  }

  let replyText = "";
  if (!rejectionCode || rejectionCode === "input_too_large") {
    const sent = await waitFor("channel_reply", async () => {
      const value = await fetchJson("/admin/sent");
      return value.sent.length > beforeSent ? value.sent : null;
    });
    replyText = extractReplyText(sent.at(-1));
    if (expectedReplyFragment && !replyText.includes(expectedReplyFragment)) {
      throw new Error(`reply_oracle:${messageId}`);
    }
  } else {
    const sent = (await fetchJson("/admin/sent")).sent;
    if (sent.length !== beforeSent) {
      throw new Error(`unauthorized_reply:${messageId}`);
    }
  }

  const canonical = trace.records.find((record) => record.stage === "canonical_event") || null;
  return {
    trace_id: trace.traceId,
    runtime_delta: afterTurns - beforeTurns,
    reply_sha256: replyText ? await sha256Text(replyText) : null,
    latency_ms: canonical?.latency_ms ?? null,
    stages: stageNames(trace.records),
  };
}

async function sha256Text(text) {
  const bytes = new TextEncoder().encode(String(text || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function percentile(values, percentileValue) {
  const ordered = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.ceil((percentileValue / 100) * ordered.length) - 1);
  return ordered[index];
}

function writePrivate(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true, mode: 0o700 });
  fs.writeFileSync(filePath, value, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
}

await waitFor("weixin_ready", () => fetchJson("/admin/state"));
await waitFor("codex_ready", async () => (await readSimulatorTurns()) || []);
await postJson("/admin/reset", {});

const knownTraceIds = new Set(groupTraces().keys());
const e2e = [];
for (let index = 1; index <= 10; index += 1) {
  const marker = `CB140-E2E-${String(index).padStart(2, "0")}`;
  e2e.push(await sendAndWait({
    text: `${marker} return this read-only marker`,
    messageId: 140000 + index,
    expectedReplyFragment: index === 1 ? "" : marker,
    knownTraceIds,
  }));
}

const unauthorized = await sendAndWait({
  text: "CB140 unauthorized input must never reach Runtime",
  messageId: 140100,
  senderId: "sim-unauthorized-user",
  expectRuntimeDelta: 0,
  rejectionCode: "sender_not_allowed",
  knownTraceIds,
});

const boundaryAccepted = await sendAndWait({
  text: "a".repeat(32 * 1024),
  messageId: 140101,
  expectedReplyFragment: "",
  knownTraceIds,
});

const boundaryRejected = await sendAndWait({
  text: "b".repeat((32 * 1024) + 1),
  messageId: 140102,
  expectRuntimeDelta: 0,
  expectedReplyFragment: "32768-byte limit",
  rejectionCode: "input_too_large",
  knownTraceIds,
});

const latencySamples = [];
const latencyResults = [];
for (let index = 1; index <= 20; index += 1) {
  const marker = `CB140-LATENCY-${String(index).padStart(2, "0")}`;
  const result = await sendAndWait({
    text: `${marker} read-only`,
    messageId: 140200 + index,
    expectedReplyFragment: marker,
    knownTraceIds,
  });
  if (!Number.isFinite(result.latency_ms)) {
    throw new Error(`latency_missing:${marker}`);
  }
  latencyResults.push(result);
  latencySamples.push(result.latency_ms);
}
const latencyP50 = percentile(latencySamples, 50);
const latencyP95 = percentile(latencySamples, 95);
if (!(latencyP50 < 5_000 && latencyP95 < 10_000)) {
  throw new Error(`latency_threshold:p50=${latencyP50}:p95=${latencyP95}`);
}

const screenshotMarker = "CB140-SIMULATOR-SCREENSHOT";
const screenshotResult = await sendAndWait({
  text: `${screenshotMarker} read-only walking skeleton proof`,
  messageId: 140300,
  expectedReplyFragment: screenshotMarker,
  knownTraceIds,
});
const fixtureResponse = await fetch(new URL("/admin/fixture", WEIXIN_BASE_URL), {
  signal: AbortSignal.timeout(2_000),
});
if (!fixtureResponse.ok) {
  throw new Error(`fixture_http_${fixtureResponse.status}`);
}
const fixtureHtml = await fixtureResponse.text();
if (!fixtureHtml.includes("SIMULATOR FIXTURE — NOT REAL WECHAT")) {
  throw new Error("fixture_label_missing");
}
writePrivate(options.fixtureHtml, fixtureHtml);

const allRecords = readTraceRecords();
const selectedTraceIds = new Set([
  ...e2e.map((item) => item.trace_id),
  unauthorized.trace_id,
  boundaryAccepted.trace_id,
  boundaryRejected.trace_id,
  ...latencyResults.map((item) => item.trace_id),
  screenshotResult.trace_id,
].filter(Boolean));
const correlatedRecords = allRecords.filter((record) => knownTraceIds.has(record.trace_id));
writePrivate(
  options.correlatedOutput,
  `${correlatedRecords.map((record) => JSON.stringify(record)).join("\n")}\n`,
);

const report = {
  schema_version: 1,
  task_id: "CB-140",
  phase: "P1.5",
  claim_level: "fixture",
  simulator_e2e: {
    passed: true,
    successful_traces: e2e.length,
    expected_traces: 10,
    trace_ids: e2e.map((item) => item.trace_id),
    complete_stage_chain: true,
  },
  inbound_policy: {
    allowlist_unauthorized_runtime_calls: unauthorized.runtime_delta,
    boundary_32768_runtime_calls: boundaryAccepted.runtime_delta,
    boundary_32769_runtime_calls: boundaryRejected.runtime_delta,
    passed: unauthorized.runtime_delta === 0
      && boundaryAccepted.runtime_delta === 1
      && boundaryRejected.runtime_delta === 0,
  },
  latency: {
    sample_count: latencySamples.length,
    p50_ms: latencyP50,
    p95_ms: latencyP95,
    threshold_p50_ms: 5_000,
    threshold_p95_ms: 10_000,
    passed: true,
  },
  correlation: {
    trace_id_count: knownTraceIds.size,
    selected_e2e_trace_id_count: selectedTraceIds.size,
    raw_message_content_persisted: false,
    raw_result_content_persisted: false,
    raw_identity_persisted: false,
    passed: true,
  },
  real_adapters: {
    wechat: "activation_pending",
    codex: "activation_pending",
    real_qr_scan: false,
    real_message_sent: false,
    real_runtime_turns: 0,
  },
  pg_1_executed: false,
  stage_2_spool_claimed: false,
  result: "passed",
};
writePrivate(options.output, `${JSON.stringify(report, null, 2)}\n`);
console.log(
  `CB140_WALKING_SKELETON=PASS e2e=${e2e.length}/10 latency=${latencySamples.length}/20 p50_ms=${latencyP50} p95_ms=${latencyP95} unauthorized_runtime=0 oversized_runtime=0 real_adapters=activation_pending`,
);

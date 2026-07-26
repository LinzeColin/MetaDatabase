const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const TRACE_STAGE_ORDER = [
  "inbound_received",
  "runtime_dispatched",
  "runtime_completed",
  "outbox_staged",
  "delivery_confirmed",
  "canonical_event",
];

class WalkingSkeletonTraceStore {
  constructor({ filePath = "", stateDir = "" } = {}) {
    this.filePath = normalizeText(filePath);
    this.stateDir = normalizeText(stateDir);
    this.sequence = 0;
    this.traceState = new Map();
    if (!this.filePath) {
      return;
    }
    this.filePath = assertTracePath(this.filePath, this.stateDir);
    initializeTraceFile(this.filePath);
    this.loadExistingState();
  }

  isEnabled() {
    return Boolean(this.filePath);
  }

  beginInbound(message) {
    if (!this.isEnabled()) {
      return "";
    }
    const traceId = buildTraceId(message);
    const decision = message?.policyDecision || {};
    if (decision.accepted === false) {
      this.append(traceId, "inbound_rejected", {
        input_bytes: toNonNegativeInteger(decision.inputBytes),
        max_input_bytes: toPositiveInteger(decision.maxInputBytes),
        rejection_code: normalizeRejectionCode(decision.code),
      });
      return traceId;
    }
    this.record({
      stage: "inbound_received",
      traceId,
      text: message?.text,
      inputBytes: decision.inputBytes,
    });
    return traceId;
  }

  record({
    stage = "",
    traceId = "",
    threadId = "",
    turnId = "",
    text = "",
    inputBytes = undefined,
  } = {}) {
    if (!this.isEnabled()) {
      return null;
    }
    const normalizedTraceId = normalizeTraceId(traceId);
    const normalizedStage = normalizeText(stage);
    if (!normalizedTraceId || !TRACE_STAGE_ORDER.includes(normalizedStage)) {
      return null;
    }

    const desiredIndex = normalizedStage === "delivery_confirmed"
      ? TRACE_STAGE_ORDER.indexOf("canonical_event")
      : TRACE_STAGE_ORDER.indexOf(normalizedStage);
    const state = this.ensureTraceState(normalizedTraceId);
    const runtimeFields = buildRuntimeFields(threadId, turnId);
    const outputFields = buildOutputFields(text);

    for (let index = 0; index <= desiredIndex; index += 1) {
      const requiredStage = TRACE_STAGE_ORDER[index];
      if (state.stages.has(requiredStage)) {
        continue;
      }
      const fields = {};
      if (requiredStage === "inbound_received") {
        fields.input_bytes = toNonNegativeInteger(inputBytes ?? Buffer.byteLength(String(text || ""), "utf8"));
        fields.input_sha256 = hashText(text);
        state.inboundAtMs = Date.now();
      }
      if (requiredStage === "runtime_dispatched" || requiredStage === "runtime_completed") {
        Object.assign(fields, runtimeFields);
      }
      if (requiredStage === "runtime_completed" || requiredStage === "outbox_staged" || requiredStage === "delivery_confirmed") {
        Object.assign(fields, outputFields);
      }
      if (requiredStage === "canonical_event") {
        fields.completed = true;
        fields.latency_ms = Math.max(0, Date.now() - (state.inboundAtMs || Date.now()));
        fields.stage_count = TRACE_STAGE_ORDER.length - 1;
      }
      this.append(normalizedTraceId, requiredStage, fields);
      state.stages.add(requiredStage);
    }
    return normalizedTraceId;
  }

  ensureTraceState(traceId) {
    if (!this.traceState.has(traceId)) {
      this.traceState.set(traceId, {
        stages: new Set(),
        inboundAtMs: 0,
      });
    }
    return this.traceState.get(traceId);
  }

  append(traceId, stage, fields) {
    const timestamp = new Date().toISOString();
    const record = {
      schema_version: 1,
      task_id: "CB-140",
      claim_level: "fixture",
      sequence: this.sequence += 1,
      trace_id: traceId,
      stage,
      timestamp,
      ...dropEmptyFields(fields),
    };
    fs.appendFileSync(this.filePath, `${JSON.stringify(record)}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    return record;
  }

  loadExistingState() {
    const contents = fs.readFileSync(this.filePath, "utf8");
    for (const line of contents.split("\n")) {
      if (!line.trim()) {
        continue;
      }
      let record;
      try {
        record = JSON.parse(line);
      } catch {
        throw new Error("walking skeleton trace file contains invalid JSON");
      }
      const traceId = normalizeTraceId(record?.trace_id);
      const stage = normalizeText(record?.stage);
      if (!traceId || (!TRACE_STAGE_ORDER.includes(stage) && stage !== "inbound_rejected")) {
        throw new Error("walking skeleton trace file contains an invalid record");
      }
      this.sequence = Math.max(this.sequence, toNonNegativeInteger(record.sequence));
      const state = this.ensureTraceState(traceId);
      if (TRACE_STAGE_ORDER.includes(stage)) {
        state.stages.add(stage);
      }
      if (stage === "inbound_received") {
        const parsed = Date.parse(record.timestamp);
        state.inboundAtMs = Number.isFinite(parsed) ? parsed : 0;
      }
    }
  }
}

function buildTraceId(message) {
  const parts = [
    normalizeText(message?.provider),
    normalizeText(message?.accountId),
    normalizeText(message?.senderId),
    normalizeText(message?.messageId),
    normalizeText(message?.receivedAt),
  ];
  return `cb140-${crypto.createHash("sha256").update(parts.join("\u001f")).digest("hex").slice(0, 24)}`;
}

function buildRuntimeFields(threadId, turnId) {
  const fields = {};
  const normalizedThreadId = normalizeText(threadId);
  const normalizedTurnId = normalizeText(turnId);
  if (normalizedThreadId) {
    fields.runtime_thread_sha256 = hashText(normalizedThreadId);
  }
  if (normalizedTurnId) {
    fields.runtime_turn_sha256 = hashText(normalizedTurnId);
  }
  return fields;
}

function buildOutputFields(text) {
  const normalized = String(text || "");
  if (!normalized) {
    return {};
  }
  return {
    output_bytes: Buffer.byteLength(normalized, "utf8"),
    output_sha256: hashText(normalized),
  };
}

function initializeTraceFile(filePath) {
  const parent = path.dirname(filePath);
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  if (fs.existsSync(filePath)) {
    const metadata = fs.lstatSync(filePath);
    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error("walking skeleton trace path must be a regular file");
    }
    fs.chmodSync(filePath, 0o600);
    return;
  }
  fs.writeFileSync(filePath, "", {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
}

function assertTracePath(filePath, stateDir) {
  if (!path.isAbsolute(filePath)) {
    throw new Error("walking skeleton trace path must be absolute");
  }
  if (!path.isAbsolute(stateDir)) {
    throw new Error("walking skeleton trace state directory must be absolute");
  }
  const resolved = path.resolve(filePath);
  const root = path.resolve(stateDir);
  if (resolved === root || !resolved.startsWith(`${root}${path.sep}`)) {
    throw new Error("walking skeleton trace path must stay inside the state directory");
  }
  return resolved;
}

function normalizeTraceId(value) {
  const normalized = normalizeText(value);
  return /^cb140-[0-9a-f]{24}$/.test(normalized) ? normalized : "";
}

function normalizeRejectionCode(value) {
  const normalized = normalizeText(value);
  return ["sender_not_allowed", "input_too_large"].includes(normalized)
    ? normalized
    : "policy_rejected";
}

function hashText(value) {
  return crypto.createHash("sha256").update(String(value || "")).digest("hex");
}

function dropEmptyFields(fields) {
  return Object.fromEntries(
    Object.entries(fields || {}).filter(([, value]) => value !== "" && value !== undefined && value !== null),
  );
}

function toNonNegativeInteger(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
}

function toPositiveInteger(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

module.exports = {
  TRACE_STAGE_ORDER,
  WalkingSkeletonTraceStore,
  buildTraceId,
};

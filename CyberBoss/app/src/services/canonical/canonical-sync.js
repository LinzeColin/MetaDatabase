"use strict";

const { spawn } = require("node:child_process");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { gunzipSync, gzipSync } = require("node:zlib");

const {
  canonicalEventJson,
  stableJson,
} = require("../db/database-adapter");
const { assertPayloadSafe } = require("./user-fact-envelope");

const DEFAULT_BATCH_MAX_RECORDS = 50;
const DEFAULT_BATCH_MAX_BYTES = 262_144;
// Retained only to parse pre-amendment configuration. Age is never a remote
// dispatch trigger after the CB-240 owner amendment.
const DEFAULT_BATCH_MAX_AGE_MS = 60_000;
const DEFAULT_BACKLOG_MAX_EVENTS = 10_000;
const DEFAULT_BACKLOG_MAX_BYTES = 64 * 1024 * 1024;
const DEFAULT_MAX_LAG_SECONDS = 900;
const DEFAULT_MAX_EVENTS_PER_INVOCATION = 2_000;
const DEFAULT_MAX_UNCOMPRESSED_BYTES_PER_INVOCATION = 10 * 1024 * 1024;
const DEFAULT_MAX_ATTEMPTS_PER_INVOCATION = 5;
const DEFAULT_RETRY_BASE_MS = 1_000;
const DEFAULT_RETRY_MAX_MS = 15 * 60 * 1_000;
const CANONICAL_AREA = "Private-MetaDatabase";
const CANONICAL_DOMAIN = "CyberBoss";
const OBJECT_NAME_PREFIX = "cyberboss-canonical-events-v1_";
const RECEIPT_STATUSES = new Set(["verified", "retry", "integrity_error"]);
const DEFAULT_MATERIAL_EVENT_TYPES = Object.freeze([
  "incident_declared",
  "recovery_completed",
  "release_completed",
]);
const TERMINAL_STATUSES = new Set([
  "replied",
  "reply_failed",
  "succeeded",
  "failed_terminal",
  "cancelled",
]);

class CanonicalSyncError extends Error {
  constructor(code, options = {}) {
    super(code);
    this.name = "CanonicalSyncError";
    this.code = code;
    if (options.cause !== undefined) {
      this.cause = options.cause;
    }
  }
}

class CanonicalIntegrityError extends CanonicalSyncError {
  constructor(code = "CANONICAL_INTEGRITY_CONFLICT") {
    super(code);
    this.name = "CanonicalIntegrityError";
  }
}

class PrivateDatabaseCommandError extends CanonicalSyncError {
  constructor(code, {
    httpStatus = null,
    retryAfterMs = null,
    outcomeUnknown = false,
  } = {}) {
    super(code);
    this.name = "PrivateDatabaseCommandError";
    this.httpStatus = httpStatus;
    this.retryAfterMs = retryAfterMs;
    this.outcomeUnknown = outcomeUnknown === true;
  }
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function isoTimestamp(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) {
    throw new CanonicalSyncError("CANONICAL_CLOCK_INVALID");
  }
  return date.toISOString();
}

function normalizedText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function requireSafeToken(value, code, maximum = 256) {
  const normalized = normalizedText(value);
  if (
    !normalized ||
    normalized.length > maximum ||
    !/^[A-Za-z0-9_.:/-]+$/.test(normalized)
  ) {
    throw new CanonicalSyncError(code);
  }
  return normalized;
}

function requireSha256(value, code) {
  const normalized = normalizedText(value);
  if (!/^[0-9a-f]{64}$/.test(normalized)) {
    throw new CanonicalSyncError(code);
  }
  return normalized;
}

function validateMaterialEventTypes(value) {
  if (!Array.isArray(value)) {
    throw new CanonicalSyncError("CANONICAL_MATERIAL_EVENT_TYPES_INVALID");
  }
  const normalized = [...new Set(value.map((item) => requireSafeToken(
    item,
    "CANONICAL_MATERIAL_EVENT_TYPE_INVALID",
    160,
  )))].sort(stableTokenCompare);
  if (
    normalized.length !== DEFAULT_MATERIAL_EVENT_TYPES.length ||
    normalized.some((item, index) => item !== DEFAULT_MATERIAL_EVENT_TYPES[index])
  ) {
    throw new CanonicalSyncError("CANONICAL_MATERIAL_EVENT_TYPES_INVALID");
  }
  return Object.freeze(normalized);
}

function canonicalDeliveryClass(record, {
  materialEventTypes = DEFAULT_MATERIAL_EVENT_TYPES,
} = {}) {
  const allowed = validateMaterialEventTypes(materialEventTypes);
  const eventType = requireSafeToken(
    record?.event_type,
    "CANONICAL_EVENT_TYPE_INVALID",
    160,
  );
  const normalized = eventType.startsWith("job.")
    ? eventType.slice("job.".length)
    : eventType;
  return allowed.includes(normalized) ? "material" : "ordinary";
}

function canonicalBatchDeliveryClass(records, options = {}) {
  if (!Array.isArray(records) || records.length < 1) {
    throw new CanonicalSyncError("CANONICAL_BATCH_DELIVERY_CLASS_INVALID");
  }
  const classes = new Set(records.map((record) => canonicalDeliveryClass(
    record,
    options,
  )));
  if (classes.size !== 1) {
    throw new CanonicalIntegrityError("CANONICAL_BATCH_DELIVERY_CLASS_MIXED");
  }
  return classes.values().next().value;
}

function normalizeWorkerMode(value) {
  const mode = normalizedText(value);
  if (!new Set(["daily", "material", "manual"]).has(mode)) {
    throw new CanonicalSyncError("CANONICAL_WORKER_MODE_INVALID");
  }
  return mode;
}

function workerModeAllows(mode, deliveryClass) {
  return mode === "material"
    ? deliveryClass === "material"
    : mode === "daily" || mode === "manual";
}

function stableTokenCompare(left, right) {
  return Buffer.compare(
    Buffer.from(left, "utf8"),
    Buffer.from(right, "utf8"),
  );
}

function ensureDirectory(directory, mode = 0o700) {
  if (!path.isAbsolute(directory)) {
    throw new CanonicalSyncError("CANONICAL_DIRECTORY_ABSOLUTE_REQUIRED");
  }
  if (!fs.existsSync(directory)) {
    fs.mkdirSync(directory, { recursive: true, mode });
  }
  const stats = fs.lstatSync(directory);
  if (!stats.isDirectory() || stats.isSymbolicLink()) {
    throw new CanonicalSyncError("CANONICAL_DIRECTORY_INVALID");
  }
  return directory;
}

function atomicWrite(filePath, bytes, mode = 0o640) {
  const directory = ensureDirectory(path.dirname(filePath));
  const name = path.basename(filePath);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/.test(name)) {
    throw new CanonicalSyncError("CANONICAL_FILE_NAME_INVALID");
  }
  const temporary = path.join(
    directory,
    `.${name}.tmp-${process.pid}-${sha256(Buffer.from(name)).slice(0, 8)}`,
  );
  if (fs.existsSync(temporary) || fs.lstatSync(directory).isSymbolicLink()) {
    throw new CanonicalSyncError("CANONICAL_ATOMIC_TARGET_INVALID");
  }
  try {
    fs.writeFileSync(temporary, bytes, { mode, flag: "wx" });
    fs.chmodSync(temporary, mode);
    fs.renameSync(temporary, filePath);
  } finally {
    if (fs.existsSync(temporary)) {
      fs.rmSync(temporary, { force: true });
    }
  }
}

function readJsonFile(filePath, code = "CANONICAL_JSON_INVALID") {
  if (!fs.existsSync(filePath) || fs.lstatSync(filePath).isSymbolicLink()) {
    throw new CanonicalSyncError(code);
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    throw new CanonicalSyncError(code);
  }
}

function canonicalRecordHash(record) {
  const hashInput = { ...record };
  delete hashInput.record_sha256;
  return sha256(Buffer.from(stableJson(hashInput), "utf8"));
}

function mapJobEventToCanonical(row, {
  deployedCommit,
} = {}) {
  if (!row || typeof row !== "object") {
    throw new CanonicalSyncError("CANONICAL_JOB_EVENT_REQUIRED");
  }
  const status = requireSafeToken(
    row.to_status || row.job_status || "unknown",
    "CANONICAL_STATUS_INVALID",
    160,
  );
  const eventType = requireSafeToken(
    row.event_type || `state_${status}`,
    "CANONICAL_EVENT_TYPE_INVALID",
    160,
  );
  const record = {
    schema_version: 1,
    event_id: requireSafeToken(
      row.event_id,
      "CANONICAL_EVENT_ID_INVALID",
      160,
    ),
    occurred_at: isoTimestamp(row.occurred_at),
    recorded_at: isoTimestamp(row.recorded_at),
    source: "cyberboss-cloud",
    event_type: `job.${eventType}`,
    status,
    job_id: requireSafeToken(row.job_id, "CANONICAL_JOB_ID_INVALID", 160),
    correlation_id: requireSafeToken(
      row.correlation_id,
      "CANONICAL_CORRELATION_ID_INVALID",
      160,
    ),
    workspace_alias: requireSafeToken(
      row.workspace_alias,
      "CANONICAL_WORKSPACE_ALIAS_INVALID",
      160,
    ),
    runtime: requireSafeToken(
      row.runtime,
      "CANONICAL_RUNTIME_INVALID",
      160,
    ),
    input_sha256: requireSha256(
      row.input_sha256,
      "CANONICAL_INPUT_HASH_INVALID",
    ),
    output_sha256:
      row.output_sha256 === null || row.output_sha256 === undefined
        ? null
        : requireSha256(
            row.output_sha256,
            "CANONICAL_OUTPUT_HASH_INVALID",
          ),
    summary_redacted: `Job event: ${eventType}.`,
    evidence_refs: [],
    deployed_commit: normalizedText(deployedCommit),
    record_sha256: "",
  };
  record.record_sha256 = canonicalRecordHash(record);
  canonicalEventJson(record);
  return Object.freeze(record);
}

function normalizeCanonicalRecord(value) {
  const serialized = canonicalEventJson(value);
  return Object.freeze(JSON.parse(serialized));
}

function eventSetSha256(records) {
  if (!Array.isArray(records)) {
    throw new CanonicalSyncError("CANONICAL_EVENT_SET_REQUIRED");
  }
  const pairs = records
    .map((record) => ({
      event_id: requireSafeToken(
        record?.event_id,
        "CANONICAL_EVENT_ID_INVALID",
        160,
      ),
      record_sha256: requireSha256(
        record?.record_sha256,
        "CANONICAL_RECORD_HASH_INVALID",
      ),
    }))
    .sort((left, right) => (
      stableTokenCompare(left.event_id, right.event_id) ||
      stableTokenCompare(left.record_sha256, right.record_sha256)
    ));
  for (let index = 1; index < pairs.length; index += 1) {
    if (pairs[index - 1].event_id === pairs[index].event_id) {
      throw new CanonicalIntegrityError(
        pairs[index - 1].record_sha256 === pairs[index].record_sha256
          ? "CANONICAL_DUPLICATE_EVENT"
          : "CANONICAL_DUPLICATE_ID_CONFLICT",
      );
    }
  }
  return sha256(
    Buffer.from(
      stableJson(pairs),
      "utf8",
    ),
  );
}

function encodeCanonicalBatch(records, {
  maxBytes = DEFAULT_BATCH_MAX_BYTES,
} = {}) {
  if (
    !Array.isArray(records) ||
    records.length < 1 ||
    records.length > DEFAULT_BATCH_MAX_RECORDS ||
    !Number.isSafeInteger(maxBytes) ||
    maxBytes < 1 ||
    maxBytes > 95 * 1024 * 1024
  ) {
    throw new CanonicalSyncError("CANONICAL_BATCH_INPUT_INVALID");
  }
  const ordered = records
    .map(normalizeCanonicalRecord)
    .sort((left, right) =>
      stableTokenCompare(left.event_id, right.event_id));
  const seen = new Map();
  for (const record of ordered) {
    const existing = seen.get(record.event_id);
    if (existing && existing !== record.record_sha256) {
      throw new CanonicalIntegrityError("CANONICAL_DUPLICATE_ID_CONFLICT");
    }
    if (existing) {
      throw new CanonicalSyncError("CANONICAL_DUPLICATE_EVENT");
    }
    seen.set(record.event_id, record.record_sha256);
  }
  const setSha256 = eventSetSha256(ordered);
  const header = {
    schema_version: 1,
    record_type: "batch_header",
    domain: CANONICAL_DOMAIN,
    logical_type: "canonical_event_batch",
    event_count: ordered.length,
    first_event_id: ordered[0].event_id,
    last_event_id: ordered.at(-1).event_id,
    event_set_sha256: setSha256,
  };
  const ndjson = Buffer.from(
    `${[stableJson(header), ...ordered.map(stableJson)].join("\n")}\n`,
    "utf8",
  );
  if (ndjson.length > maxBytes) {
    throw new CanonicalSyncError("CANONICAL_BATCH_BYTE_LIMIT");
  }
  const compressed = gzipSync(ndjson, {
    level: 9,
    mtime: 0,
  });
  const objectSha256 = sha256(compressed);
  const batchId = `batch_${setSha256}`;
  const objectName = `${OBJECT_NAME_PREFIX}${setSha256.slice(0, 24)}.ndjson.gz`;
  return Object.freeze({
    batchId,
    batchLabel: [
      "CyberBoss",
      "canonical_event_batch",
      "v1",
      header.first_event_id,
      header.last_event_id,
      setSha256,
    ].join("."),
    compressed,
    compressedBytes: compressed.length,
    eventCount: ordered.length,
    eventSetSha256: setSha256,
    firstEventId: header.first_event_id,
    lastEventId: header.last_event_id,
    header: Object.freeze(header),
    ndjson,
    objectName,
    objectSha256,
    records: Object.freeze(ordered),
    uncompressedBytes: ndjson.length,
  });
}

function decodeCanonicalBatch(bytes, {
  expectedObjectSha256 = null,
  maxBytes = DEFAULT_BATCH_MAX_BYTES,
} = {}) {
  if (!Buffer.isBuffer(bytes) || bytes.length === 0) {
    throw new CanonicalIntegrityError("CANONICAL_OBJECT_EMPTY");
  }
  if (
    expectedObjectSha256 !== null &&
    sha256(bytes) !== requireSha256(
      expectedObjectSha256,
      "CANONICAL_EXPECTED_OBJECT_HASH_INVALID",
    )
  ) {
    throw new CanonicalIntegrityError("CANONICAL_OBJECT_HASH_MISMATCH");
  }
  let ndjson;
  try {
    ndjson = gunzipSync(bytes, {
      maxOutputLength: maxBytes + 1,
    });
  } catch {
    throw new CanonicalIntegrityError("CANONICAL_OBJECT_DECOMPRESSION_FAILED");
  }
  if (ndjson.length > maxBytes) {
    throw new CanonicalIntegrityError("CANONICAL_OBJECT_BYTE_LIMIT");
  }
  const lines = ndjson
    .toString("utf8")
    .split("\n")
    .filter((line) => line.length > 0);
  if (lines.length < 2) {
    throw new CanonicalIntegrityError("CANONICAL_OBJECT_RECORDS_MISSING");
  }
  let header;
  let records;
  try {
    header = JSON.parse(lines[0]);
    records = lines.slice(1).map((line) => normalizeCanonicalRecord(
      JSON.parse(line),
    ));
  } catch (error) {
    if (error instanceof CanonicalSyncError) {
      throw error;
    }
    throw new CanonicalIntegrityError("CANONICAL_OBJECT_JSON_INVALID");
  }
  const rebuilt = encodeCanonicalBatch(records, { maxBytes });
  if (
    header.schema_version !== 1 ||
    header.record_type !== "batch_header" ||
    header.domain !== CANONICAL_DOMAIN ||
    header.logical_type !== "canonical_event_batch" ||
    Number(header.event_count) !== records.length ||
    header.first_event_id !== rebuilt.firstEventId ||
    header.last_event_id !== rebuilt.lastEventId ||
    header.event_set_sha256 !== rebuilt.eventSetSha256 ||
    !rebuilt.ndjson.equals(ndjson) ||
    !rebuilt.compressed.equals(bytes)
  ) {
    throw new CanonicalIntegrityError("CANONICAL_OBJECT_NOT_DETERMINISTIC");
  }
  return rebuilt;
}

function listRegularFiles(directory, suffix = "") {
  ensureDirectory(directory);
  return fs.readdirSync(directory, { withFileTypes: true })
    .filter(
      (entry) =>
        entry.isFile() &&
        !entry.isSymbolicLink() &&
        (!suffix || entry.name.endsWith(suffix)),
    )
    .map((entry) => path.join(directory, entry.name))
    .sort();
}

function parseHttpStatus(text) {
  const match = String(text || "").match(
    /(?:HTTP_STATUS[=:]\s*|HTTP\s+|status[=:]\s*)(403|404|409|429|5\d\d)\b/i,
  );
  return match ? Number(match[1]) : null;
}

function parseRetryAfterMs(text) {
  const milliseconds = String(text || "").match(
    /retry[_ -]?after[_ -]?ms[=:]\s*(\d{1,10})/i,
  );
  if (milliseconds) {
    return Number(milliseconds[1]);
  }
  const seconds = String(text || "").match(
    /retry[_ -]?after[=:]\s*(\d{1,7})/i,
  );
  return seconds ? Number(seconds[1]) * 1_000 : null;
}

function runBoundedProcess(command, args, {
  env,
  timeoutMs = 120_000,
} = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const maximum = 256 * 1024;
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      if (!settled) {
        settled = true;
        reject(
          new PrivateDatabaseCommandError(
            "PRIVATE_DB_COMMAND_TIMEOUT",
            { outcomeUnknown: true },
          ),
        );
      }
    }, timeoutMs);
    timer.unref?.();
    const append = (current, chunk) => {
      const next = current + chunk.toString("utf8");
      if (Buffer.byteLength(next, "utf8") > maximum) {
        child.kill("SIGKILL");
        throw new PrivateDatabaseCommandError(
          "PRIVATE_DB_COMMAND_OUTPUT_LIMIT",
          { outcomeUnknown: true },
        );
      }
      return next;
    };
    child.stdout.on("data", (chunk) => {
      try {
        stdout = append(stdout, chunk);
      } catch (error) {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(error);
        }
      }
    });
    child.stderr.on("data", (chunk) => {
      try {
        stderr = append(stderr, chunk);
      } catch (error) {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(error);
        }
      }
    });
    child.once("error", (error) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(
          new PrivateDatabaseCommandError(
            "PRIVATE_DB_COMMAND_START_FAILED",
            { outcomeUnknown: false, cause: error },
          ),
        );
      }
    });
    child.once("exit", (code, signal) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      if (signal || code !== 0) {
        const output = `${stdout}\n${stderr}`;
        reject(
          new PrivateDatabaseCommandError(
            signal
              ? "PRIVATE_DB_COMMAND_INTERRUPTED"
              : "PRIVATE_DB_COMMAND_FAILED",
            {
              httpStatus: parseHttpStatus(output),
              retryAfterMs: parseRetryAfterMs(output),
              outcomeUnknown:
                signal !== null ||
                /timeout|connection reset|eof|tls|unknown/i.test(output),
            },
          ),
        );
        return;
      }
      resolve(Object.freeze({ stdout, stderr }));
    });
  });
}

class NoClonePrivateDatabaseAdapter {
  constructor({
    wrapperPath,
    clientPath,
    domain = CANONICAL_DOMAIN,
    area = CANONICAL_AREA,
    environment = process.env,
    timeoutMs = 120_000,
  } = {}) {
    if (
      !path.isAbsolute(normalizedText(wrapperPath)) ||
      !path.isAbsolute(normalizedText(clientPath)) ||
      path.basename(clientPath) !== "private_db_client.py" ||
      domain !== CANONICAL_DOMAIN ||
      area !== CANONICAL_AREA ||
      !Number.isSafeInteger(timeoutMs) ||
      timeoutMs < 1_000 ||
      timeoutMs > 10 * 60_000
    ) {
      throw new CanonicalSyncError("PRIVATE_DB_ADAPTER_CONFIG_INVALID");
    }
    this.wrapperPath = wrapperPath;
    this.clientPath = clientPath;
    this.domain = domain;
    this.area = area;
    this.environment = { ...environment };
    this.timeoutMs = timeoutMs;
    this.realDataOperation = true;
    this.noClone = true;
    this.operationCounts = {
      get: 0,
      ingest: 0,
      list: 0,
      verify: 0,
    };
  }

  async #run(operation, args = []) {
    if (!Object.hasOwn(this.operationCounts, operation)) {
      throw new CanonicalSyncError("PRIVATE_DB_OPERATION_FORBIDDEN");
    }
    this.operationCounts[operation] += 1;
    return runBoundedProcess(
      this.wrapperPath,
      [
        "--client",
        this.clientPath,
        "--domain",
        this.domain,
        "--execute",
        operation,
        this.area,
        ...args,
      ],
      {
        env: this.environment,
        timeoutMs: this.timeoutMs,
      },
    );
  }

  async ingest({ filePath, batchLabel }) {
    const result = await this.#run("ingest", [
      filePath,
      "--batch",
      batchLabel,
    ]);
    return Object.freeze({
      httpStatus: 201,
      outputSha256: sha256(Buffer.from(result.stdout, "utf8")),
    });
  }

  async get(relativePath, outputPath) {
    return this.#run("get", [relativePath, outputPath]);
  }

  async list(prefix = "") {
    const result = await this.#run("list", prefix ? [prefix] : []);
    return result.stdout
      .split("\n")
      .map((line) => line.trim().split(/\s+/).at(-1) || "")
      .filter(Boolean)
      .map((entry) =>
        entry.startsWith(`${this.area}/`)
          ? entry.slice(this.area.length + 1)
          : entry,
      );
  }

  async verify() {
    return this.#run("verify");
  }
}

class FilesystemPrivateDatabaseAdapter {
  constructor({
    root,
    now = () => new Date("2026-07-27T00:00:00.000Z"),
    faults = [],
  } = {}) {
    this.root = ensureDirectory(root);
    this.areaRoot = ensureDirectory(path.join(this.root, CANONICAL_AREA));
    ensureDirectory(path.join(this.areaRoot, "objects"));
    this.now = now;
    this.faults = Array.isArray(faults) ? [...faults] : [];
    this.realDataOperation = false;
    this.noClone = true;
    this.operationCounts = {
      get: 0,
      ingest: 0,
      list: 0,
      verify: 0,
    };
  }

  queueFault(fault) {
    this.faults.push({ ...fault });
  }

  #resolve(relativePath) {
    const normalized = normalizedText(relativePath);
    if (
      !normalized ||
      path.posix.isAbsolute(normalized) ||
      normalized.split("/").includes("..") ||
      !/^[A-Za-z0-9._/-]+$/.test(normalized)
    ) {
      throw new CanonicalSyncError("PRIVATE_DB_FIXTURE_PATH_INVALID");
    }
    const resolved = path.resolve(this.areaRoot, normalized);
    if (!resolved.startsWith(`${this.areaRoot}${path.sep}`)) {
      throw new CanonicalSyncError("PRIVATE_DB_FIXTURE_PATH_ESCAPE");
    }
    return resolved;
  }

  #manifestPath() {
    return path.join(this.areaRoot, "manifest.jsonl");
  }

  #writeIngest(filePath, batchLabel) {
    const bytes = fs.readFileSync(filePath);
    const objectSha256 = sha256(bytes);
    const name = path.basename(filePath);
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/.test(name)) {
      throw new CanonicalSyncError("PRIVATE_DB_FIXTURE_NAME_INVALID");
    }
    const relativeObject = `objects/${objectSha256.slice(0, 2)}/${objectSha256}_${name}`;
    const target = this.#resolve(relativeObject);
    ensureDirectory(path.dirname(target));
    if (fs.existsSync(target)) {
      if (sha256(fs.readFileSync(target)) !== objectSha256) {
        throw new CanonicalIntegrityError("PRIVATE_DB_IMMUTABLE_OBJECT_MISMATCH");
      }
    } else {
      atomicWrite(target, bytes, 0o640);
    }
    const manifestPath = this.#manifestPath();
    const records = fs.existsSync(manifestPath)
      ? fs.readFileSync(manifestPath, "utf8")
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line))
      : [];
    let record = records.find((candidate) => candidate.sha256 === objectSha256);
    if (!record) {
      record = {
        sha256: objectSha256,
        original_name: name,
        size_bytes: bytes.length,
        domain: CANONICAL_DOMAIN,
        batch: batchLabel,
        object_path: relativeObject,
        ingested_at: isoTimestamp(this.now()).slice(0, 10),
      };
      const next = `${records.concat(record).map(stableJson).join("\n")}\n`;
      atomicWrite(manifestPath, Buffer.from(next, "utf8"), 0o640);
    }
    return Object.freeze({
      httpStatus: 201,
      manifestRecord: Object.freeze(record),
      objectPath: relativeObject,
      objectSha256,
    });
  }

  async ingest({ filePath, batchLabel }) {
    this.operationCounts.ingest += 1;
    const fault = this.faults.shift() || null;
    let written = null;
    if (fault?.afterWrite === true) {
      written = this.#writeIngest(filePath, batchLabel);
    }
    if (fault) {
      throw new PrivateDatabaseCommandError(
        fault.code || `PRIVATE_DB_FIXTURE_HTTP_${fault.httpStatus || 503}`,
        {
          httpStatus: fault.httpStatus || 503,
          retryAfterMs: fault.retryAfterMs ?? null,
          outcomeUnknown: fault.outcomeUnknown === true || fault.afterWrite === true,
        },
      );
    }
    return written || this.#writeIngest(filePath, batchLabel);
  }

  async get(relativePath, outputPath) {
    this.operationCounts.get += 1;
    const source = this.#resolve(relativePath);
    if (!fs.existsSync(source) || !fs.lstatSync(source).isFile()) {
      throw new PrivateDatabaseCommandError(
        "PRIVATE_DB_FIXTURE_NOT_FOUND",
        { httpStatus: 404 },
      );
    }
    fs.copyFileSync(source, outputPath);
    fs.chmodSync(outputPath, 0o600);
    return Object.freeze({ httpStatus: 200 });
  }

  async list(prefix = "") {
    this.operationCounts.list += 1;
    const target = prefix ? this.#resolve(prefix) : this.areaRoot;
    if (!fs.existsSync(target)) {
      return [];
    }
    return fs.readdirSync(target, { withFileTypes: true })
      .map((entry) => `${prefix ? `${prefix}/` : ""}${entry.name}`)
      .sort();
  }

  async verify() {
    this.operationCounts.verify += 1;
    const manifestPath = this.#manifestPath();
    if (!fs.existsSync(manifestPath)) {
      return Object.freeze({ records: 0, missing: 0 });
    }
    let records = 0;
    let missing = 0;
    for (const line of fs.readFileSync(manifestPath, "utf8").split("\n")) {
      if (!line) {
        continue;
      }
      records += 1;
      const record = JSON.parse(line);
      const objectPath = this.#resolve(record.object_path);
      if (
        !fs.existsSync(objectPath) ||
        sha256(fs.readFileSync(objectPath)) !== record.sha256
      ) {
        missing += 1;
      }
    }
    if (missing > 0) {
      throw new CanonicalIntegrityError("PRIVATE_DB_FIXTURE_VERIFY_FAILED");
    }
    return Object.freeze({ records, missing });
  }
}

function normalizeManifestRecord(record) {
  if (
    !record ||
    typeof record !== "object" ||
    Array.isArray(record) ||
    record.domain !== CANONICAL_DOMAIN ||
    !normalizedText(record.original_name).startsWith(OBJECT_NAME_PREFIX) ||
    !Number.isSafeInteger(Number(record.size_bytes)) ||
    Number(record.size_bytes) < 1
  ) {
    return null;
  }
  const objectSha256 = requireSha256(
    record.sha256,
    "CANONICAL_MANIFEST_HASH_INVALID",
  );
  const objectPath = normalizedText(record.object_path);
  if (
    !objectPath.startsWith(`objects/${objectSha256.slice(0, 2)}/`) ||
    path.posix.isAbsolute(objectPath) ||
    objectPath.split("/").includes("..") ||
    !/^[A-Za-z0-9._/-]+$/.test(objectPath)
  ) {
    throw new CanonicalIntegrityError("CANONICAL_MANIFEST_PATH_INVALID");
  }
  return Object.freeze({
    ...record,
    object_path: objectPath,
    sha256: objectSha256,
  });
}

async function readRemoteCanonical(adapter, {
  temporaryDirectory = null,
} = {}) {
  if (
    !adapter ||
    typeof adapter.list !== "function" ||
    typeof adapter.get !== "function" ||
    typeof adapter.verify !== "function"
  ) {
    throw new CanonicalSyncError("CANONICAL_REMOTE_ADAPTER_REQUIRED");
  }
  const ownedTemporary = temporaryDirectory === null;
  const root = temporaryDirectory || fs.mkdtempSync(
    path.join(os.tmpdir(), "cb240-remote-"),
  );
  ensureDirectory(root);
  try {
    const listing = await adapter.list("");
    const manifestPath = path.join(root, "manifest.jsonl");
    try {
      await adapter.get("manifest.jsonl", manifestPath);
    } catch (error) {
      if (error?.httpStatus === 404) {
        await adapter.verify();
        return Object.freeze({
          events: new Map(),
          listing: Object.freeze([...listing]),
          manifestRecords: Object.freeze([]),
          objectCount: 0,
        });
      }
      throw error;
    }
    const manifestRecords = [];
    for (const line of fs.readFileSync(manifestPath, "utf8").split("\n")) {
      if (!line) {
        continue;
      }
      let parsed;
      try {
        parsed = JSON.parse(line);
      } catch {
        throw new CanonicalIntegrityError("CANONICAL_MANIFEST_JSON_INVALID");
      }
      const normalized = normalizeManifestRecord(parsed);
      if (normalized) {
        manifestRecords.push(normalized);
      }
    }
    const events = new Map();
    for (let index = 0; index < manifestRecords.length; index += 1) {
      const record = manifestRecords[index];
      const localObject = path.join(root, `object-${index}.ndjson.gz`);
      await adapter.get(record.object_path, localObject);
      const bytes = fs.readFileSync(localObject);
      if (
        bytes.length !== Number(record.size_bytes) ||
        sha256(bytes) !== record.sha256
      ) {
        throw new CanonicalIntegrityError("CANONICAL_REMOTE_OBJECT_MISMATCH");
      }
      const decoded = decodeCanonicalBatch(bytes, {
        expectedObjectSha256: record.sha256,
      });
      for (const event of decoded.records) {
        const existing = events.get(event.event_id);
        if (existing && existing.record.record_sha256 !== event.record_sha256) {
          throw new CanonicalIntegrityError("CANONICAL_REMOTE_EVENT_CONFLICT");
        }
        if (!existing) {
          events.set(
            event.event_id,
            Object.freeze({
              manifestRecord: record,
              record: event,
            }),
          );
        }
      }
    }
    await adapter.verify();
    return Object.freeze({
      events,
      listing: Object.freeze([...listing]),
      manifestRecords: Object.freeze(manifestRecords),
      objectCount: manifestRecords.length,
    });
  } finally {
    if (ownedTemporary) {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }
}

function findVerifiedBatch(remote, batch) {
  const matches = [];
  for (const record of batch.records) {
    const candidate = remote.events.get(record.event_id);
    if (!candidate) {
      return null;
    }
    if (candidate.record.record_sha256 !== record.record_sha256) {
      throw new CanonicalIntegrityError("CANONICAL_REMOTE_EVENT_CONFLICT");
    }
    matches.push(candidate.manifestRecord);
  }
  const manifest = matches.find(
    (record) => record.sha256 === batch.objectSha256,
  );
  if (!manifest) {
    return null;
  }
  return Object.freeze({
    manifestRecord: manifest,
    manifestRecordSha256: sha256(
      Buffer.from(stableJson(manifest), "utf8"),
    ),
    remoteEventCount: remote.events.size,
  });
}

function receiptHash(receipt) {
  return sha256(Buffer.from(stableJson(receipt), "utf8"));
}

function validateReceipt(receipt) {
  if (
    !receipt ||
    typeof receipt !== "object" ||
    Array.isArray(receipt) ||
    receipt.schema_version !== 1 ||
    receipt.task_id !== "CB-240" ||
    !RECEIPT_STATUSES.has(receipt.status)
  ) {
    throw new CanonicalIntegrityError("CANONICAL_RECEIPT_CONTRACT_INVALID");
  }
  const commonFields = [
    "schema_version",
    "task_id",
    "status",
    "batch_id",
    "object_sha256",
    "event_set_sha256",
    "no_clone",
    "real_data_operation",
  ];
  const statusFields = {
    verified: [
      "manifest_record_sha256",
      "remote_object_path",
      "verified_at",
      "remote_event_count",
    ],
    retry: [
      "error_class",
      "retry_after_ms",
      "next_attempt_at",
    ],
    integrity_error: ["error_class"],
  };
  const expectedFields = new Set([
    ...commonFields,
    ...statusFields[receipt.status],
  ]);
  if (
    Object.keys(receipt).length !== expectedFields.size ||
    Object.keys(receipt).some((field) => !expectedFields.has(field)) ||
    receipt.no_clone !== true ||
    typeof receipt.real_data_operation !== "boolean"
  ) {
    throw new CanonicalIntegrityError("CANONICAL_RECEIPT_FIELDS_INVALID");
  }
  requireSafeToken(receipt.batch_id, "CANONICAL_RECEIPT_BATCH_INVALID", 160);
  requireSha256(
    receipt.object_sha256,
    "CANONICAL_RECEIPT_OBJECT_HASH_INVALID",
  );
  requireSha256(
    receipt.event_set_sha256,
    "CANONICAL_RECEIPT_EVENT_SET_INVALID",
  );
  if (receipt.status === "verified") {
    requireSha256(
      receipt.manifest_record_sha256,
      "CANONICAL_RECEIPT_MANIFEST_HASH_INVALID",
    );
    if (
      !normalizedText(receipt.remote_object_path).startsWith("objects/") ||
      !receipt.verified_at
    ) {
      throw new CanonicalIntegrityError(
        "CANONICAL_RECEIPT_VERIFICATION_INVALID",
      );
    }
    isoTimestamp(receipt.verified_at);
    if (
      !Number.isSafeInteger(receipt.remote_event_count) ||
      receipt.remote_event_count < 1
    ) {
      throw new CanonicalIntegrityError(
        "CANONICAL_RECEIPT_REMOTE_COUNT_INVALID",
      );
    }
  } else {
    requireSafeToken(
      receipt.error_class,
      "CANONICAL_RECEIPT_ERROR_INVALID",
      160,
    );
    if (receipt.status === "retry") {
      if (
        !Number.isSafeInteger(receipt.retry_after_ms) ||
        receipt.retry_after_ms < 0 ||
        receipt.retry_after_ms > 24 * 60 * 60 * 1_000
      ) {
        throw new CanonicalIntegrityError(
          "CANONICAL_RECEIPT_RETRY_HINT_INVALID",
        );
      }
      isoTimestamp(receipt.next_attempt_at);
    }
  }
  return Object.freeze({ ...receipt });
}

class CanonicalSpoolCoordinator {
  constructor({
    database,
    outgoingDirectory,
    receiptDirectory,
    quarantineDirectory,
    deployedCommit,
    now = () => new Date(),
    maxRecords = DEFAULT_BATCH_MAX_RECORDS,
    maxBytes = DEFAULT_BATCH_MAX_BYTES,
    maxAgeMs = DEFAULT_BATCH_MAX_AGE_MS,
    backlogMaxEvents = DEFAULT_BACKLOG_MAX_EVENTS,
    backlogMaxBytes = DEFAULT_BACKLOG_MAX_BYTES,
    maxLagSeconds = DEFAULT_MAX_LAG_SECONDS,
    materialEventTypes = DEFAULT_MATERIAL_EVENT_TYPES,
    ordinarySyncOnCalendar = "*-*-* 03:20:00 UTC",
    flushOnTerminal = true,
    intervalMs = 1_000,
    setIntervalFn = setInterval,
    clearIntervalFn = clearInterval,
  } = {}) {
    if (
      !database ||
      typeof database.listCanonicalCandidateEvents !== "function" ||
      !/^[0-9a-f]{40}$/.test(normalizedText(deployedCommit)) ||
      !Number.isSafeInteger(maxRecords) ||
      maxRecords < 1 ||
      maxRecords > DEFAULT_BATCH_MAX_RECORDS ||
      !Number.isSafeInteger(maxBytes) ||
      maxBytes < 1 ||
      !Number.isSafeInteger(maxAgeMs) ||
      maxAgeMs < 1 ||
      ordinarySyncOnCalendar !== "*-*-* 03:20:00 UTC" ||
      typeof now !== "function" ||
      typeof setIntervalFn !== "function" ||
      typeof clearIntervalFn !== "function"
    ) {
      throw new CanonicalSyncError("CANONICAL_COORDINATOR_CONFIG_INVALID");
    }
    const normalizedMaterialEventTypes = validateMaterialEventTypes(
      materialEventTypes,
    );
    if (typeof flushOnTerminal !== "boolean") {
      throw new CanonicalSyncError("CANONICAL_COORDINATOR_CONFIG_INVALID");
    }
    this.database = database;
    this.outgoingDirectory = ensureDirectory(outgoingDirectory);
    this.receiptDirectory = ensureDirectory(receiptDirectory);
    this.quarantineDirectory = ensureDirectory(quarantineDirectory);
    this.deployedCommit = deployedCommit;
    this.now = now;
    this.maxRecords = maxRecords;
    this.maxBytes = maxBytes;
    this.legacyMaxAgeMs = maxAgeMs;
    this.backlogMaxEvents = backlogMaxEvents;
    this.backlogMaxBytes = backlogMaxBytes;
    this.maxLagSeconds = maxLagSeconds;
    this.materialEventTypes = normalizedMaterialEventTypes;
    this.ordinarySyncOnCalendar = ordinarySyncOnCalendar;
    this.materialFlushEnabled = flushOnTerminal;
    this.lastDailyOrdinarySlot = null;
    this.intervalMs = intervalMs;
    this.setIntervalFn = setIntervalFn;
    this.clearIntervalFn = clearIntervalFn;
    this.timer = null;
    this.cyclePromise = null;
    this.started = false;
  }

  stageCandidates(limit = 10_000) {
    const candidates = this.database.listCanonicalCandidateEvents(limit);
    let staged = 0;
    for (const candidate of candidates) {
      const event = mapJobEventToCanonical(candidate, {
        deployedCommit: this.deployedCommit,
      });
      // CB-800 / AC-030 on the live write path: the frozen forbidden-field and
      // secret-value scan runs before an event can be staged, so raw message
      // text, a prompt, a response or a key cannot reach the canonical area
      // even if some upstream producer starts emitting one.
      assertPayloadSafe(event, `canonical_event:${event.event_id}`);
      this.database.enqueueSyncEvent({
        eventId: event.event_id,
        objectType: "job_event",
        objectId: candidate.event_id,
        canonicalPath:
          `Private-MetaDatabase/CyberBoss/events/${event.event_id}.json`,
        payloadRedacted: event,
      });
      staged += 1;
    }
    return staged;
  }

  #parseRow(row) {
    try {
      return JSON.parse(row.payload_redacted_json);
    } catch {
      throw new CanonicalIntegrityError("CANONICAL_LOCAL_EVENT_JSON_INVALID");
    }
  }

  #rowDeliveryClass(row) {
    return canonicalDeliveryClass(this.#parseRow(row), {
      materialEventTypes: this.materialEventTypes,
    });
  }

  #selectBatch(rows, deliveryClass) {
    const records = [];
    let reachedByteBoundary = false;
    for (const row of rows) {
      const candidate = this.#parseRow(row);
      if (
        canonicalDeliveryClass(candidate, {
          materialEventTypes: this.materialEventTypes,
        }) !== deliveryClass
      ) {
        continue;
      }
      if (records.length >= this.maxRecords) {
        break;
      }
      try {
        encodeCanonicalBatch([...records, candidate], {
          maxBytes: this.maxBytes,
        });
        records.push(candidate);
      } catch (error) {
        if (error?.code !== "CANONICAL_BATCH_BYTE_LIMIT") {
          throw error;
        }
        if (records.length === 0) {
          throw new CanonicalIntegrityError(
            "CANONICAL_SINGLE_EVENT_BYTE_LIMIT",
          );
        }
        reachedByteBoundary = true;
        break;
      }
    }
    return Object.freeze({ records, reachedByteBoundary, deliveryClass });
  }

  #dailyOrdinarySlot(at) {
    const date = new Date(at);
    if (
      date.getUTCHours() !== 3 ||
      date.getUTCMinutes() !== 20
    ) {
      return null;
    }
    return date.toISOString().slice(0, 16);
  }

  materializeAssignedBatch() {
    const assigned = this.database.nextCanonicalBatch(isoTimestamp(this.now()));
    if (!assigned) {
      return null;
    }
    const rows = this.database.listCanonicalBatch(assigned.batch_id);
    if (rows.length === 0) {
      throw new CanonicalIntegrityError("CANONICAL_ASSIGNED_BATCH_EMPTY");
    }
    const records = rows.map((row) => JSON.parse(row.payload_redacted_json));
    const batch = encodeCanonicalBatch(records, { maxBytes: this.maxBytes });
    const deliveryClass = canonicalBatchDeliveryClass(batch.records, {
      materialEventTypes: this.materialEventTypes,
    });
    if (
      batch.batchId !== assigned.batch_id ||
      rows.some(
        (row) =>
          row.batch_event_set_sha256 !== batch.eventSetSha256 ||
          row.canonical_object_sha256 !== batch.objectSha256,
      )
    ) {
      this.database.markCanonicalBatchIntegrity(
        assigned.batch_id,
        "local_batch_rebuild_mismatch",
      );
      throw new CanonicalIntegrityError("CANONICAL_LOCAL_BATCH_MISMATCH");
    }
    const target = path.join(this.outgoingDirectory, batch.objectName);
    if (fs.existsSync(target)) {
      const existing = fs.readFileSync(target);
      if (!existing.equals(batch.compressed)) {
        this.database.markCanonicalBatchIntegrity(
          assigned.batch_id,
          "local_object_hash_conflict",
        );
        throw new CanonicalIntegrityError("CANONICAL_LOCAL_OBJECT_CONFLICT");
      }
    } else {
      atomicWrite(target, batch.compressed, 0o640);
    }
    return Object.freeze({ ...batch, deliveryClass, filePath: target });
  }

  buildDueBatch({ force = false, dailyOrdinarySlot = null } = {}) {
    const existing = this.materializeAssignedBatch();
    if (existing) {
      return existing;
    }
    const now = isoTimestamp(this.now());
    const rows = this.database.listUnbatchedCanonicalEvents({
      limit: 10_000,
      at: now,
    });
    if (rows.length === 0) {
      return null;
    }
    const deliveryClass = rows.some((row) => (
      this.#rowDeliveryClass(row) === "material"
    ))
      ? "material"
      : "ordinary";
    const selected = this.#selectBatch(rows, deliveryClass);
    if (selected.records.length === 0) {
      throw new CanonicalIntegrityError("CANONICAL_BATCH_SELECTION_EMPTY");
    }
    const batch = encodeCanonicalBatch(selected.records, {
      maxBytes: this.maxBytes,
    });
    const due =
      force === true ||
      (deliveryClass === "material" && this.materialFlushEnabled) ||
      selected.records.length >= this.maxRecords ||
      selected.reachedByteBoundary ||
      (
        deliveryClass === "ordinary" &&
        dailyOrdinarySlot !== null &&
        dailyOrdinarySlot !== this.lastDailyOrdinarySlot
      );
    if (!due) {
      return null;
    }
    this.database.assignCanonicalBatch({
      eventIds: batch.records.map((record) => record.event_id),
      batchId: batch.batchId,
      eventSetSha256: batch.eventSetSha256,
      objectSha256: batch.objectSha256,
    });
    if (deliveryClass === "ordinary" && dailyOrdinarySlot !== null) {
      this.lastDailyOrdinarySlot = dailyOrdinarySlot;
    }
    const target = path.join(this.outgoingDirectory, batch.objectName);
    atomicWrite(target, batch.compressed, 0o640);
    return Object.freeze({ ...batch, deliveryClass, filePath: target });
  }

  reconcileReceipts() {
    let verified = 0;
    let retry = 0;
    let integrity = 0;
    let skipped = 0;
    for (const receiptPath of listRegularFiles(
      this.receiptDirectory,
      ".receipt.json",
    )) {
      const receipt = validateReceipt(readJsonFile(receiptPath));
      const digest = receiptHash(receipt);
      const rows = this.database.listCanonicalBatch(receipt.batch_id);
      if (rows.length === 0) {
        throw new CanonicalIntegrityError("CANONICAL_RECEIPT_BATCH_UNKNOWN");
      }
      if (
        rows.some(
          (row) =>
            row.canonical_object_sha256 !== receipt.object_sha256 ||
            row.batch_event_set_sha256 !== receipt.event_set_sha256,
        )
      ) {
        this.database.markCanonicalBatchIntegrity(
          receipt.batch_id,
          "receipt_batch_mismatch",
          digest,
        );
        integrity += 1;
        continue;
      }
      if (rows.every((row) => row.last_receipt_sha256 === digest)) {
        skipped += 1;
        continue;
      }
      if (receipt.status === "verified") {
        this.database.markCanonicalBatchVerified(receipt.batch_id, {
          objectSha256: receipt.object_sha256,
          manifestRecordSha256: receipt.manifest_record_sha256,
          remoteObjectPath: receipt.remote_object_path,
          receiptSha256: digest,
        });
        verified += rows.length;
      } else if (receipt.status === "retry") {
        this.database.markCanonicalBatchRetry(receipt.batch_id, {
          errorClass: receipt.error_class,
          nextAttemptAt: receipt.next_attempt_at,
          retryAfterMs: receipt.retry_after_ms,
          receiptSha256: digest,
        });
        retry += rows.length;
      } else {
        this.database.markCanonicalBatchIntegrity(
          receipt.batch_id,
          receipt.error_class,
          digest,
        );
        const outgoing = listRegularFiles(
          this.outgoingDirectory,
          ".ndjson.gz",
        ).find((candidate) => {
          try {
            return decodeCanonicalBatch(fs.readFileSync(candidate)).batchId ===
              receipt.batch_id;
          } catch {
            return false;
          }
        });
        if (outgoing) {
          const quarantine = path.join(
            this.quarantineDirectory,
            `${path.basename(outgoing)}.${digest.slice(0, 12)}.quarantine`,
          );
          fs.renameSync(outgoing, quarantine);
        }
        integrity += rows.length;
      }
    }
    return Object.freeze({ verified, retry, integrity, skipped });
  }

  status() {
    return this.database.canonicalSyncStatus({
      at: isoTimestamp(this.now()),
      maxPendingEvents: this.backlogMaxEvents,
      maxPendingBytes: this.backlogMaxBytes,
      maxLagSeconds: this.maxLagSeconds,
      materialEventTypes: this.materialEventTypes,
    });
  }

  mutationGuard() {
    const status = this.status();
    return Object.freeze({
      mutationAllowed: status.mutationAllowed,
      reason: status.mutationAllowed
        ? "canonical_ready"
        : status.integrityCount > 0
          ? "canonical_integrity_error"
          : status.materialRetryCount > 0
            ? "canonical_material_backlog_protect"
          : "canonical_backlog_protect",
      status,
    });
  }

  runCycle(options = {}) {
    if (this.cyclePromise) {
      return this.cyclePromise;
    }
    this.cyclePromise = Promise.resolve().then(() => {
      const receipts = this.reconcileReceipts();
      const staged = this.stageCandidates();
      const batch = this.buildDueBatch({
        ...options,
        dailyOrdinarySlot: this.#dailyOrdinarySlot(this.now()),
      });
      const status = this.status();
      this.database.setServiceState("canonical_sync", {
        integrity_count: status.integrityCount,
        mutation_allowed: status.mutationAllowed,
        pending_count: status.pendingEvents,
        state_code: status.state,
      });
      return Object.freeze({
        receipts,
        staged,
        batch: batch
          ? Object.freeze({
              batchId: batch.batchId,
              eventCount: batch.eventCount,
              eventSetSha256: batch.eventSetSha256,
              objectSha256: batch.objectSha256,
              deliveryClass: batch.deliveryClass,
            })
          : null,
        status,
      });
    }).finally(() => {
      this.cyclePromise = null;
    });
    return this.cyclePromise;
  }

  async start() {
    if (this.started) {
      return Object.freeze({ alreadyStarted: true, status: this.status() });
    }
    const recovery = this.database.recoverCanonicalSync();
    const cycle = await this.runCycle();
    this.timer = this.setIntervalFn(() => {
      void this.runCycle().catch(() => {});
    }, this.intervalMs);
    this.timer?.unref?.();
    this.started = true;
    return Object.freeze({ alreadyStarted: false, recovery, cycle });
  }

  stop() {
    if (this.timer) {
      this.clearIntervalFn(this.timer);
      this.timer = null;
    }
    this.started = false;
  }
}

function retryDelayMs(attempt, {
  baseMs = DEFAULT_RETRY_BASE_MS,
  maxMs = DEFAULT_RETRY_MAX_MS,
  hintMs = null,
} = {}) {
  const exponential = Math.min(
    maxMs,
    baseMs * (2 ** Math.max(0, attempt - 1)),
  );
  const hint =
    Number.isSafeInteger(hintMs) && hintMs >= 0
      ? Math.min(maxMs, hintMs)
      : 0;
  return Math.max(exponential, hint);
}

function dataStateDefault() {
  return {
    schema_version: 1,
    task_id: "CB-240",
    batches: {},
  };
}

class CanonicalDataWorker {
  constructor({
    outgoingDirectory,
    receiptDirectory,
    stateFile,
    adapter,
    now = () => new Date(),
    materialEventTypes = DEFAULT_MATERIAL_EVENT_TYPES,
    maxEventsPerInvocation = DEFAULT_MAX_EVENTS_PER_INVOCATION,
    maxUncompressedBytesPerInvocation =
      DEFAULT_MAX_UNCOMPRESSED_BYTES_PER_INVOCATION,
    maxAttemptsPerInvocation = DEFAULT_MAX_ATTEMPTS_PER_INVOCATION,
  } = {}) {
    if (
      !adapter ||
      typeof adapter.ingest !== "function" ||
      !path.isAbsolute(normalizedText(stateFile)) ||
      typeof now !== "function" ||
      !Number.isSafeInteger(maxEventsPerInvocation) ||
      maxEventsPerInvocation < 1 ||
      maxEventsPerInvocation > 10_000 ||
      !Number.isSafeInteger(maxUncompressedBytesPerInvocation) ||
      maxUncompressedBytesPerInvocation < DEFAULT_BATCH_MAX_BYTES ||
      maxUncompressedBytesPerInvocation > 95 * 1024 * 1024 ||
      !Number.isSafeInteger(maxAttemptsPerInvocation) ||
      maxAttemptsPerInvocation < 1 ||
      maxAttemptsPerInvocation > 100
    ) {
      throw new CanonicalSyncError("CANONICAL_DATA_WORKER_CONFIG_INVALID");
    }
    this.outgoingDirectory = ensureDirectory(outgoingDirectory);
    this.receiptDirectory = ensureDirectory(receiptDirectory);
    ensureDirectory(path.dirname(stateFile));
    this.stateFile = stateFile;
    this.adapter = adapter;
    this.now = now;
    this.materialEventTypes = validateMaterialEventTypes(materialEventTypes);
    this.maxEventsPerInvocation = maxEventsPerInvocation;
    this.maxUncompressedBytesPerInvocation =
      maxUncompressedBytesPerInvocation;
    this.maxAttemptsPerInvocation = maxAttemptsPerInvocation;
    this.state = fs.existsSync(stateFile)
      ? readJsonFile(stateFile, "CANONICAL_DATA_STATE_INVALID")
      : dataStateDefault();
    if (
      this.state.schema_version !== 1 ||
      this.state.task_id !== "CB-240" ||
      !this.state.batches ||
      typeof this.state.batches !== "object" ||
      Array.isArray(this.state.batches)
    ) {
      throw new CanonicalSyncError("CANONICAL_DATA_STATE_INVALID");
    }
  }

  #saveState() {
    atomicWrite(
      this.stateFile,
      Buffer.from(`${stableJson(this.state)}\n`, "utf8"),
      0o600,
    );
  }

  #writeReceipt(receipt) {
    const validated = validateReceipt(receipt);
    const target = path.join(
      this.receiptDirectory,
      `${validated.batch_id}.receipt.json`,
    );
    atomicWrite(
      target,
      Buffer.from(`${stableJson(validated)}\n`, "utf8"),
      0o640,
    );
    return validated;
  }

  async #remoteVerification(batch) {
    const remote = await readRemoteCanonical(this.adapter);
    const match = findVerifiedBatch(remote, batch);
    return Object.freeze({ match, remote });
  }

  #verifiedReceipt(batch, match, at) {
    return {
      schema_version: 1,
      task_id: "CB-240",
      status: "verified",
      batch_id: batch.batchId,
      object_sha256: batch.objectSha256,
      event_set_sha256: batch.eventSetSha256,
      manifest_record_sha256: match.manifestRecordSha256,
      remote_object_path: match.manifestRecord.object_path,
      verified_at: at,
      remote_event_count: match.remoteEventCount,
      no_clone: true,
      real_data_operation: this.adapter.realDataOperation === true,
    };
  }

  async #process(filePath, batch = null) {
    const decodedBatch = batch || decodeCanonicalBatch(fs.readFileSync(filePath));
    const deliveryClass = canonicalBatchDeliveryClass(decodedBatch.records, {
      materialEventTypes: this.materialEventTypes,
    });
    const batchToProcess = decodedBatch;
    const now = isoTimestamp(this.now());
    const previous = this.state.batches[batchToProcess.batchId] || {
      attempt_count: 0,
      status: "pending",
      next_attempt_at: null,
    };
    if (
      previous.status === "verified" ||
      (
        previous.next_attempt_at &&
        Date.parse(previous.next_attempt_at) > Date.parse(now)
      )
    ) {
      return Object.freeze({
        batchId: batchToProcess.batchId,
        deliveryClass,
        status: "skipped",
      });
    }

    try {
      const before = await this.#remoteVerification(batchToProcess);
      if (before.match) {
        const receipt = this.#writeReceipt(
          this.#verifiedReceipt(batchToProcess, before.match, now),
        );
        this.state.batches[batchToProcess.batchId] = {
          attempt_count: Number(previous.attempt_count || 0),
          status: "verified",
          next_attempt_at: null,
          object_sha256: batchToProcess.objectSha256,
        };
        this.#saveState();
        return Object.freeze({ ...receipt, deliveryClass });
      }

      try {
        await this.adapter.ingest({
          filePath,
          batchLabel: batchToProcess.batchLabel,
        });
      } catch (error) {
        if (
          [409, 429, 500, 502, 503, 504].includes(error?.httpStatus) ||
          error?.outcomeUnknown === true
        ) {
          const afterFailure = await this.#remoteVerification(batchToProcess);
          if (afterFailure.match) {
            const receipt = this.#writeReceipt(
              this.#verifiedReceipt(batchToProcess, afterFailure.match, now),
            );
            this.state.batches[batchToProcess.batchId] = {
              attempt_count: Number(previous.attempt_count || 0) + 1,
              status: "verified",
              next_attempt_at: null,
              object_sha256: batchToProcess.objectSha256,
            };
            this.#saveState();
            return Object.freeze({ ...receipt, deliveryClass });
          }
        }
        throw error;
      }

      const after = await this.#remoteVerification(batchToProcess);
      if (!after.match) {
        throw new PrivateDatabaseCommandError(
          "CANONICAL_REMOTE_SET_INCOMPLETE",
          { outcomeUnknown: true },
        );
      }
      const receipt = this.#writeReceipt(
        this.#verifiedReceipt(batchToProcess, after.match, now),
      );
      this.state.batches[batchToProcess.batchId] = {
        attempt_count: Number(previous.attempt_count || 0) + 1,
        status: "verified",
        next_attempt_at: null,
        object_sha256: batchToProcess.objectSha256,
      };
      this.#saveState();
      return Object.freeze({ ...receipt, deliveryClass });
    } catch (error) {
      if (error instanceof CanonicalIntegrityError) {
        const receipt = this.#writeReceipt({
          schema_version: 1,
          task_id: "CB-240",
          status: "integrity_error",
          batch_id: batchToProcess.batchId,
          object_sha256: batchToProcess.objectSha256,
          event_set_sha256: batchToProcess.eventSetSha256,
          error_class: "event_hash_conflict",
          no_clone: true,
          real_data_operation: this.adapter.realDataOperation === true,
        });
        this.state.batches[batchToProcess.batchId] = {
          attempt_count: Number(previous.attempt_count || 0) + 1,
          status: "integrity_error",
          next_attempt_at: null,
          object_sha256: batchToProcess.objectSha256,
        };
        this.#saveState();
        return Object.freeze({ ...receipt, deliveryClass });
      }
      const attempt = Number(previous.attempt_count || 0) + 1;
      const httpStatus = Number(error?.httpStatus || 0) || null;
      const errorClass =
        httpStatus === 403
          ? "canonical_auth_scope"
          : httpStatus === 409
            ? "manifest_conflict"
            : httpStatus === 429
              ? "provider_rate_limit"
              : error?.outcomeUnknown === true
                ? "unknown_outcome_reconcile"
                : "canonical_unavailable";
      const delay = retryDelayMs(attempt, {
        hintMs: error?.retryAfterMs,
      });
      const nextAttemptAt = new Date(Date.parse(now) + delay).toISOString();
      const receipt = this.#writeReceipt({
        schema_version: 1,
        task_id: "CB-240",
        status: "retry",
        batch_id: batchToProcess.batchId,
        object_sha256: batchToProcess.objectSha256,
        event_set_sha256: batchToProcess.eventSetSha256,
        error_class: errorClass,
        retry_after_ms: delay,
        next_attempt_at: nextAttemptAt,
        no_clone: true,
        real_data_operation: this.adapter.realDataOperation === true,
      });
      this.state.batches[batchToProcess.batchId] = {
        attempt_count: attempt,
        status: "retry",
        next_attempt_at: nextAttemptAt,
        object_sha256: batchToProcess.objectSha256,
      };
      this.#saveState();
      return Object.freeze({ ...receipt, deliveryClass });
    }
  }

  async runOnce({ mode = "manual" } = {}) {
    const normalizedMode = normalizeWorkerMode(mode);
    const files = listRegularFiles(
      this.outgoingDirectory,
      ".ndjson.gz",
    );
    const results = [];
    let eligible = 0;
    let deferred = 0;
    let skipped = 0;
    let eventCount = 0;
    let uncompressedBytes = 0;
    const invocationNow = isoTimestamp(this.now());
    for (const filePath of files) {
      const batch = decodeCanonicalBatch(fs.readFileSync(filePath));
      const deliveryClass = canonicalBatchDeliveryClass(batch.records, {
        materialEventTypes: this.materialEventTypes,
      });
      if (!workerModeAllows(normalizedMode, deliveryClass)) {
        deferred += 1;
        continue;
      }
      const previous = this.state.batches[batch.batchId];
      if (previous?.status === "verified") {
        skipped += 1;
        continue;
      }
      if (
        previous?.next_attempt_at &&
        Date.parse(previous.next_attempt_at) > Date.parse(invocationNow)
      ) {
        deferred += 1;
        continue;
      }
      eligible += 1;
      if (
        results.length >= this.maxAttemptsPerInvocation ||
        eventCount + batch.eventCount > this.maxEventsPerInvocation ||
        uncompressedBytes + batch.uncompressedBytes >
          this.maxUncompressedBytesPerInvocation
      ) {
        deferred += 1;
        continue;
      }
      eventCount += batch.eventCount;
      uncompressedBytes += batch.uncompressedBytes;
      results.push(await this.#process(filePath, batch));
    }
    return Object.freeze({
      status: results.length === 0 ? "noop_no_commit" : "completed",
      mode: normalizedMode,
      inspected: files.length,
      eligible,
      deferred,
      skipped,
      eventCount,
      uncompressedBytes,
      results: Object.freeze(results),
      operations: Object.freeze({ ...this.adapter.operationCounts }),
      realDataOperation: this.adapter.realDataOperation === true,
      noClone: this.adapter.noClone === true,
    });
  }
}

function timelineProjection(event) {
  return {
    schema_version: 1,
    source: "cyberboss-canonical",
    event_id: event.event_id,
    occurred_at: event.occurred_at,
    event_type: event.event_type,
    status: event.status,
    job_id: event.job_id,
    summary_redacted: event.summary_redacted,
    record_sha256: event.record_sha256,
  };
}

async function rebuildCanonicalProjection({
  adapter,
  outputDirectory,
  recoveryPointerPath = null,
  sqlitePath = null,
} = {}) {
  const output = ensureDirectory(outputDirectory);
  if (listRegularFiles(output).length !== 0) {
    throw new CanonicalSyncError("CANONICAL_REBUILD_OUTPUT_NOT_EMPTY");
  }
  if (sqlitePath && fs.existsSync(sqlitePath)) {
    throw new CanonicalSyncError("CANONICAL_REBUILD_SQLITE_MUST_BE_ABSENT");
  }
  const remote = await readRemoteCanonical(adapter);
  const events = [...remote.events.values()]
    .map((entry) => entry.record)
    .sort((left, right) => {
      const time = left.recorded_at.localeCompare(right.recorded_at);
      return time !== 0 ? time : left.event_id.localeCompare(right.event_id);
    });
  const setSha256 = eventSetSha256(
    events.slice().sort((left, right) =>
      left.event_id.localeCompare(right.event_id),
    ),
  );
  let recoveryPointerSha256 = null;
  if (recoveryPointerPath) {
    const pointer = readJsonFile(
      recoveryPointerPath,
      "CANONICAL_RECOVERY_POINTER_INVALID",
    );
    if (
      pointer.schema_version !== 1 ||
      pointer.provider !== "r2_fixture" ||
      pointer.domain !== CANONICAL_DOMAIN ||
      pointer.canonical_event_set_sha256 !== setSha256
    ) {
      throw new CanonicalIntegrityError(
        "CANONICAL_RECOVERY_POINTER_MISMATCH",
      );
    }
    recoveryPointerSha256 = sha256(fs.readFileSync(recoveryPointerPath));
  }
  const latestByJob = new Map();
  for (const event of events) {
    if (!TERMINAL_STATUSES.has(event.status)) {
      continue;
    }
    const current = latestByJob.get(event.job_id);
    if (
      !current ||
      event.recorded_at > current.recorded_at ||
      (
        event.recorded_at === current.recorded_at &&
        event.event_id > current.event_id
      )
    ) {
      latestByJob.set(event.job_id, event);
    }
  }
  const jobs = [...latestByJob.values()]
    .sort((left, right) => left.job_id.localeCompare(right.job_id))
    .map((event) => ({
      job_id: event.job_id,
      status: event.status,
      event_id: event.event_id,
      occurred_at: event.occurred_at,
      recorded_at: event.recorded_at,
      record_sha256: event.record_sha256,
    }));
  const terminalIndex = {
    schema_version: 1,
    source: "Private-MetaDatabase",
    domain: CANONICAL_DOMAIN,
    event_count: events.length,
    terminal_job_count: jobs.length,
    event_set_sha256: setSha256,
    jobs,
  };
  const terminalBytes = Buffer.from(
    `${stableJson(terminalIndex)}\n`,
    "utf8",
  );
  const timelineBytes = Buffer.from(
    events.length
      ? `${events.map((event) => stableJson(timelineProjection(event))).join("\n")}\n`
      : "",
    "utf8",
  );
  const terminalPath = path.join(output, "terminal-index.json");
  const timelinePath = path.join(output, "timeline-source.ndjson");
  atomicWrite(terminalPath, terminalBytes, 0o600);
  atomicWrite(timelinePath, timelineBytes, 0o600);
  const report = {
    schema_version: 1,
    task_id: "CB-240",
    source: "Private-MetaDatabase",
    domain: CANONICAL_DOMAIN,
    no_clone: true,
    sqlite_present: false,
    canonical_event_count: events.length,
    terminal_job_count: jobs.length,
    object_count: remote.objectCount,
    event_set_sha256: setSha256,
    terminal_index_sha256: sha256(terminalBytes),
    timeline_source_sha256: sha256(timelineBytes),
    recovery_pointer_sha256: recoveryPointerSha256,
    operations: { ...adapter.operationCounts },
    real_data_operation: adapter.realDataOperation === true,
    result: "passed",
  };
  atomicWrite(
    path.join(output, "rebuild-report.json"),
    Buffer.from(`${stableJson(report)}\n`, "utf8"),
    0o600,
  );
  return Object.freeze({
    report: Object.freeze(report),
    terminalIndex: Object.freeze(terminalIndex),
  });
}

module.exports = {
  CANONICAL_AREA,
  CANONICAL_DOMAIN,
  DEFAULT_BACKLOG_MAX_BYTES,
  DEFAULT_BACKLOG_MAX_EVENTS,
  DEFAULT_BATCH_MAX_AGE_MS,
  DEFAULT_BATCH_MAX_BYTES,
  DEFAULT_BATCH_MAX_RECORDS,
  DEFAULT_MATERIAL_EVENT_TYPES,
  DEFAULT_MAX_ATTEMPTS_PER_INVOCATION,
  DEFAULT_MAX_EVENTS_PER_INVOCATION,
  DEFAULT_MAX_LAG_SECONDS,
  DEFAULT_MAX_UNCOMPRESSED_BYTES_PER_INVOCATION,
  CanonicalDataWorker,
  CanonicalIntegrityError,
  CanonicalSpoolCoordinator,
  CanonicalSyncError,
  canonicalBatchDeliveryClass,
  canonicalDeliveryClass,
  FilesystemPrivateDatabaseAdapter,
  NoClonePrivateDatabaseAdapter,
  PrivateDatabaseCommandError,
  decodeCanonicalBatch,
  encodeCanonicalBatch,
  eventSetSha256,
  mapJobEventToCanonical,
  readRemoteCanonical,
  rebuildCanonicalProjection,
  retryDelayMs,
  sha256,
  validateReceipt,
};

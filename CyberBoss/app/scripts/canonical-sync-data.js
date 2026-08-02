#!/usr/bin/env node
"use strict";

const os = require("node:os");
const path = require("node:path");

const {
  CanonicalDataWorker,
  NoClonePrivateDatabaseAdapter,
} = require("../src/services/canonical/canonical-sync");

function required(name) {
  const value = String(process.env[name] || "").trim();
  if (!value) {
    throw new Error(`CANONICAL_ENV_REQUIRED:${name}`);
  }
  return value;
}

function parseMode(argv) {
  if (argv.length === 0) {
    return "daily";
  }
  const value = argv.length === 1 && argv[0].startsWith("--mode=")
    ? argv[0].slice("--mode=".length)
    : argv.length === 2 && argv[0] === "--mode"
      ? argv[1]
      : "";
  if (!["daily", "material", "manual"].includes(value)) {
    throw new Error("CANONICAL_MODE_INVALID");
  }
  return value;
}

function readBoundedInt(name, fallback, minimum, maximum) {
  const raw = String(process.env[name] || "").trim();
  if (!raw) {
    return fallback;
  }
  const value = Number.parseInt(raw, 10);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new Error(`CANONICAL_ENV_INVALID:${name}`);
  }
  return value;
}

function materialEventTypes() {
  const configured = String(
    process.env.CB_CANONICAL_MATERIAL_EVENT_TYPES || "",
  )
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .sort();
  const allowed = [
    "incident_declared",
    "recovery_completed",
    "release_completed",
  ];
  if (configured.length === 0) {
    return allowed;
  }
  if (
    configured.length !== allowed.length ||
    configured.some((value, index) => value !== allowed[index])
  ) {
    throw new Error("CANONICAL_MATERIAL_EVENT_TYPES_INVALID");
  }
  return configured;
}

function assertDailyPolicy() {
  const schedule = String(
    process.env.CB_CANONICAL_ORDINARY_SYNC_SCHEDULE || "daily",
  ).trim();
  const calendar = String(
    process.env.CB_CANONICAL_ORDINARY_SYNC_ON_CALENDAR ||
      "*-*-* 03:20:00 UTC",
  ).trim();
  if (schedule !== "daily" || calendar !== "*-*-* 03:20:00 UTC") {
    throw new Error("CANONICAL_SYNC_POLICY_INVALID");
  }
}

async function main() {
  const mode = parseMode(process.argv.slice(2));
  assertDailyPolicy();
  const expectedIdentity = required("CB_DATA_EXECUTION_IDENTITY");
  if (os.userInfo().username !== expectedIdentity) {
    throw new Error("CANONICAL_DATA_IDENTITY_REQUIRED");
  }
  const spoolRoot = path.resolve(required("CB_CANONICAL_SPOOL_ROOT"));
  const dataStateRoot = path.resolve(required("CB_CANONICAL_DATA_STATE_ROOT"));
  const adapter = new NoClonePrivateDatabaseAdapter({
    wrapperPath: path.resolve(required("CB_PRIVATE_DB_SAFE_WRAPPER")),
    clientPath: path.resolve(required("CB_PRIVATE_DB_CLIENT")),
    environment: process.env,
  });
  const worker = new CanonicalDataWorker({
    outgoingDirectory: path.join(spoolRoot, "outgoing"),
    receiptDirectory: path.join(spoolRoot, "receipts"),
    stateFile: path.join(dataStateRoot, "canonical-sync-state.json"),
    adapter,
    materialEventTypes: materialEventTypes(),
    maxEventsPerInvocation: readBoundedInt(
      "CB_CANONICAL_MAX_EVENTS_PER_INVOCATION",
      2_000,
      1,
      10_000,
    ),
    maxUncompressedBytesPerInvocation: readBoundedInt(
      "CB_CANONICAL_MAX_UNCOMPRESSED_BYTES_PER_INVOCATION",
      10 * 1024 * 1024,
      262_144,
      95 * 1024 * 1024,
    ),
    maxAttemptsPerInvocation: readBoundedInt(
      "CB_CANONICAL_MAX_ATTEMPTS_PER_INVOCATION",
      5,
      1,
      100,
    ),
  });
  const result = await worker.runOnce({ mode });
  process.stdout.write(
    `${JSON.stringify({
      status: result.status,
      mode: result.mode,
      inspected: result.inspected,
      eligible: result.eligible,
      deferred: result.deferred,
      event_count: result.eventCount,
      uncompressed_bytes: result.uncompressedBytes,
      no_clone: result.noClone,
      real_data_operation: result.realDataOperation,
      operation_counts: result.operations,
    })}\n`,
  );
}

main().catch((error) => {
  // 带上 syscall 和 path。
  //
  // 只印 code 的话，一个 EACCES 就是一句「EACCES」——不知道是哪个文件、
  // 哪一步。material 那条同步为此卡了很久：daily 修好之后它还在 EACCES，
  // 而错误里没有任何线索指向是哪一跳，只能一个目录一个目录去试。
  //
  // 这和 /var/lib/cyberboss 那次是同一个教训：**EACCES 不告诉你是哪一跳挂的**，
  // 所以报错的人有义务说出来。
  //
  // path 是文件系统路径，不是用户数据——它进的是运维日志，不是公开面。
  const parts = [`code=${error?.code || error?.message || "unknown"}`];
  if (error?.syscall) {
    parts.push(`syscall=${error.syscall}`);
  }
  if (error?.path) {
    parts.push(`path=${error.path}`);
  }
  process.stderr.write(`CANONICAL_DATA_SYNC=FAIL ${parts.join(" ")}\n`);
  process.exitCode = 2;
});

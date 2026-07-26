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

async function main() {
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
  });
  const result = await worker.runOnce();
  process.stdout.write(
    `${JSON.stringify({
      status: "completed",
      inspected: result.inspected,
      no_clone: result.noClone,
      real_data_operation: result.realDataOperation,
      operation_counts: result.operations,
    })}\n`,
  );
}

main().catch((error) => {
  process.stderr.write(
    `CANONICAL_DATA_SYNC=FAIL code=${error?.code || error?.message || "unknown"}\n`,
  );
  process.exitCode = 2;
});

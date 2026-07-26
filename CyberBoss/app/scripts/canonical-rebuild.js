#!/usr/bin/env node
"use strict";

const os = require("node:os");
const path = require("node:path");

const {
  NoClonePrivateDatabaseAdapter,
  rebuildCanonicalProjection,
} = require("../src/services/canonical/canonical-sync");

function parseArguments(values) {
  const result = {};
  const allowed = new Set([
    "--output-directory",
    "--recovery-pointer",
    "--sqlite-path",
  ]);
  for (let index = 0; index < values.length; index += 2) {
    const name = values[index];
    const value = values[index + 1];
    if (!allowed.has(name) || value === undefined) {
      throw new Error("CANONICAL_REBUILD_ARGUMENT_INVALID");
    }
    result[name.slice(2)] = path.resolve(value);
  }
  if (!result["output-directory"]) {
    throw new Error("CANONICAL_REBUILD_OUTPUT_REQUIRED");
  }
  return result;
}

function required(name) {
  const value = String(process.env[name] || "").trim();
  if (!value) {
    throw new Error(`CANONICAL_ENV_REQUIRED:${name}`);
  }
  return value;
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  const expectedIdentity = required("CB_DATA_EXECUTION_IDENTITY");
  if (os.userInfo().username !== expectedIdentity) {
    throw new Error("CANONICAL_DATA_IDENTITY_REQUIRED");
  }
  const adapter = new NoClonePrivateDatabaseAdapter({
    wrapperPath: path.resolve(required("CB_PRIVATE_DB_SAFE_WRAPPER")),
    clientPath: path.resolve(required("CB_PRIVATE_DB_CLIENT")),
    environment: process.env,
  });
  const result = await rebuildCanonicalProjection({
    adapter,
    outputDirectory: args["output-directory"],
    recoveryPointerPath: args["recovery-pointer"] || null,
    sqlitePath: args["sqlite-path"] || null,
  });
  process.stdout.write(
    `${JSON.stringify({
      status: "passed",
      event_count: result.report.canonical_event_count,
      terminal_job_count: result.report.terminal_job_count,
      event_set_sha256: result.report.event_set_sha256,
      no_clone: true,
    })}\n`,
  );
}

main().catch((error) => {
  process.stderr.write(
    `CANONICAL_REBUILD=FAIL code=${error?.code || error?.message || "unknown"}\n`,
  );
  process.exitCode = 2;
});

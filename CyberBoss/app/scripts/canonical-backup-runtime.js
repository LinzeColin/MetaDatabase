#!/usr/bin/env node

const fs = require("fs");
const {
  CanonicalBackupError,
  createOnlineBackup,
  restoreBackupIsolated,
  simulateRemoteUpload,
} = require("../src/services/backup/canonical-backup-runtime");

async function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArgs(argv);
    if (options.help) {
      process.stdout.write(helpText());
      return 0;
    }
    if (options.command === "backup") {
      const policy = readPolicy(options.policy);
      const backup = createOnlineBackup({
        sourceDbPath: options.sourceDb,
        outputDir: options.outputDir,
        sourceCommit: options.sourceCommit,
        createdAt: options.createdAt,
        scopePolicy: policy,
        configReferences: options.configReferences,
      });
      const receipts = {};
      if (options.r2SimulatorRoot) {
        receipts.r2 = simulateRemoteUpload({
          bundlePath: backup.bundlePath,
          provider: "r2",
          simulatorRoot: options.r2SimulatorRoot,
          scopePolicy: policy,
        });
      }
      if (options.ociSimulatorRoot) {
        receipts.oci = simulateRemoteUpload({
          bundlePath: backup.bundlePath,
          provider: "oci",
          simulatorRoot: options.ociSimulatorRoot,
          scopePolicy: policy,
        });
      }
      process.stdout.write(`${JSON.stringify({
        status: "local_verified",
        backup_id: backup.manifest.backup_id,
        archive_sha256: backup.manifest.archive.sha256,
        sqlite_integrity: backup.manifest.sqlite.sqlite_integrity,
        logical_digest: backup.manifest.sqlite.logical_digest,
        r2_state: receipts.r2?.state || backup.manifest.remote.r2.state,
        oci_state: receipts.oci?.state || backup.manifest.remote.oci.state,
        real_r2_operations: backup.manifest.counters.real_r2_operations,
        real_oci_operations: backup.manifest.counters.real_oci_operations,
        control_plane_llm_calls: backup.manifest.counters.control_plane_llm_calls,
        operations_llm_calls: backup.manifest.counters.operations_llm_calls,
      })}\n`);
      return 0;
    }
    const restored = restoreBackupIsolated({
      bundlePath: options.bundle,
      restoreRoot: options.restoreRoot,
      networkDisabled: true,
    });
    process.stdout.write(`${JSON.stringify(restored)}\n`);
    return 0;
  } catch (error) {
    const code = error instanceof CanonicalBackupError ? error.code : "BACKUP_RUNTIME_FAILED";
    process.stderr.write(`${JSON.stringify({ status: "failed", code })}\n`);
    return 2;
  }
}

function parseArgs(argv) {
  const values = Array.isArray(argv) ? argv.map((value) => String(value ?? "")) : [];
  const command = values[0] === "restore" ? "restore" : "backup";
  const offset = values[0] === "backup" || values[0] === "restore" ? 1 : 0;
  const options = {
    command,
    help: values.includes("--help") || values.includes("-h"),
    policy: "",
    sourceDb: "",
    outputDir: "",
    sourceCommit: "",
    createdAt: "",
    configReferences: [],
    r2SimulatorRoot: "",
    ociSimulatorRoot: "",
    bundle: "",
    restoreRoot: "",
  };
  for (let index = offset; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--help" || flag === "-h") {
      continue;
    }
    const next = values[index + 1];
    if (!next || next.startsWith("--")) {
      throw new CanonicalBackupError("BACKUP_ARGUMENT_INVALID");
    }
    if (flag === "--policy") {
      options.policy = next;
    } else if (flag === "--source-db") {
      options.sourceDb = next;
    } else if (flag === "--output-dir") {
      options.outputDir = next;
    } else if (flag === "--source-commit") {
      options.sourceCommit = next;
    } else if (flag === "--created-at") {
      options.createdAt = next;
    } else if (flag === "--config-reference") {
      options.configReferences.push(next);
    } else if (flag === "--r2-simulator-root") {
      options.r2SimulatorRoot = next;
    } else if (flag === "--oci-simulator-root") {
      options.ociSimulatorRoot = next;
    } else if (flag === "--bundle") {
      options.bundle = next;
    } else if (flag === "--restore-root") {
      options.restoreRoot = next;
    } else {
      throw new CanonicalBackupError("BACKUP_ARGUMENT_INVALID");
    }
    index += 1;
  }
  if (!options.help && options.command === "backup" && (
    !options.policy || !options.sourceDb || !options.outputDir || !options.sourceCommit || !options.createdAt
  )) {
    throw new CanonicalBackupError("BACKUP_ARGUMENT_REQUIRED");
  }
  if (!options.help && options.command === "restore" && (!options.bundle || !options.restoreRoot)) {
    throw new CanonicalBackupError("RESTORE_ARGUMENT_REQUIRED");
  }
  return options;
}

function readPolicy(filePath) {
  try {
    const policy = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!policy || typeof policy !== "object" || Array.isArray(policy)) {
      throw new Error("invalid");
    }
    return policy;
  } catch {
    throw new CanonicalBackupError("BACKUP_SCOPE_POLICY_UNAVAILABLE");
  }
}

function helpText() {
  return [
    "Usage:",
    "  canonical-backup-runtime.js backup --policy <identity-scope.policy.json> --source-db <runtime.sqlite3> --output-dir <local-backups> --source-commit <40-hex> --created-at <ISO-8601> [--config-reference <safe-reference>] [--r2-simulator-root <local-fixture>] [--oci-simulator-root <local-fixture>]",
    "  canonical-backup-runtime.js restore --bundle <backup-bundle> --restore-root <isolated-root>",
    "",
    "Creates an online local SQLite snapshot and optionally verifies only local R2/OCI simulator objects. It never performs a real provider request or starts a timer.",
  ].join("\n").concat("\n");
}

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  });
}

module.exports = { main, parseArgs };

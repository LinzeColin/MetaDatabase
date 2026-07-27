#!/usr/bin/env node

const fs = require("fs");
const {
  CanonicalStatusError,
  buildGlobalStatusRow,
  buildRedactedStatusSnapshot,
  writeGlobalStatusRowAtomic,
  writeStatusSnapshotAtomic,
} = require("../src/services/status/canonical-status-export");

async function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArgs(argv);
    if (options.help) {
      process.stdout.write(helpText());
      return 0;
    }
    const facts = readFacts(options.input);
    const snapshot = buildRedactedStatusSnapshot({
      generatedAt: options.generatedAt,
      sourceCommit: facts.source_commit,
      runtimeSnapshot: facts.runtime_snapshot || {},
      components: facts.components || {},
      metrics: facts.metrics || {},
      adapters: facts.adapters || {},
      release: facts.release || {},
    });
    const snapshotReceipt = writeStatusSnapshotAtomic({
      snapshot,
      outputPath: options.snapshot,
    });
    const row = buildGlobalStatusRow({
      snapshot,
      observedAt: options.observedAt,
      maxAgeSeconds: options.maxAgeSeconds,
    });
    const rowReceipt = writeGlobalStatusRowAtomic({ row, outputPath: options.row });
    process.stdout.write(`${JSON.stringify({
      status: "passed",
      generation_id: snapshot.generation_id,
      overall: snapshot.overall,
      global_status: row.status,
      snapshot_sha256: snapshotReceipt.sha256,
      row_sha256: rowReceipt.sha256,
      control_plane_llm_calls_total: snapshot.metrics.control_plane_llm_calls_total,
      self_heal_agent_invocations_total: snapshot.metrics.self_heal_agent_invocations_total,
    })}\n`);
    return 0;
  } catch (error) {
    const code = error instanceof CanonicalStatusError ? error.code : "STATUS_EXPORT_FAILED";
    process.stderr.write(`${JSON.stringify({ status: "failed", code })}\n`);
    return 2;
  }
}

function parseArgs(argv) {
  const values = Array.isArray(argv) ? argv.map((value) => String(value ?? "")) : [];
  const options = {
    help: values.includes("--help") || values.includes("-h"),
    input: "",
    snapshot: "",
    row: "",
    generatedAt: "",
    observedAt: "",
    maxAgeSeconds: 120,
  };
  const offset = values[0] === "export" ? 1 : 0;
  for (let index = offset; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--help" || flag === "-h") {
      continue;
    }
    const next = values[index + 1];
    if (!next || next.startsWith("--")) {
      throw new CanonicalStatusError("STATUS_ARGUMENT_INVALID");
    }
    if (flag === "--input") {
      options.input = next;
    } else if (flag === "--snapshot") {
      options.snapshot = next;
    } else if (flag === "--row") {
      options.row = next;
    } else if (flag === "--generated-at") {
      options.generatedAt = next;
    } else if (flag === "--observed-at") {
      options.observedAt = next;
    } else if (flag === "--max-age-seconds") {
      options.maxAgeSeconds = next;
    } else {
      throw new CanonicalStatusError("STATUS_ARGUMENT_INVALID");
    }
    index += 1;
  }
  if (!options.help && (!options.input || !options.snapshot || !options.row || !options.generatedAt || !options.observedAt)) {
    throw new CanonicalStatusError("STATUS_ARGUMENT_REQUIRED");
  }
  return options;
}

function readFacts(filePath) {
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("invalid");
    }
    const allowed = new Set(["source_commit", "runtime_snapshot", "components", "metrics", "adapters", "release"]);
    if (Object.keys(parsed).some((key) => !allowed.has(key))) {
      throw new CanonicalStatusError("STATUS_FACTS_FIELD_UNKNOWN");
    }
    return parsed;
  } catch (error) {
    if (error instanceof CanonicalStatusError) {
      throw error;
    }
    throw new CanonicalStatusError("STATUS_FACTS_INVALID");
  }
}

function helpText() {
  return [
    "Usage:",
    "  canonical-status-export.js export --input <safe-facts.json> --snapshot <snapshot.json> --row <global-row.json> --generated-at <ISO-8601> --observed-at <ISO-8601> [--max-age-seconds 120]",
    "",
    "Builds an atomic, redacted status snapshot and a compatible row for the existing global Status collector.",
  ].join("\n").concat("\n");
}

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  });
}

module.exports = { main, parseArgs };

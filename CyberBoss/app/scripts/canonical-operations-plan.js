#!/usr/bin/env node
"use strict";

const fs = require("node:fs");

const {
  CanonicalOperationsError,
  buildOperationsPlan,
} = require("../src/services/operations/canonical-operations-policy");

async function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArgs(argv);
    if (options.help) {
      process.stdout.write(helpText());
      return 0;
    }
    const plan = buildOperationsPlan({
      now: options.now,
      resourceSnapshot: readJson(options.snapshot),
      retentionPolicy: readJson(options.retentionPolicy),
      retentionInventory: readJson(options.inventory),
      priorReceipt: options.priorReceipt ? readJson(options.priorReceipt) : null,
      backupEligible: options.backupEligible,
    });
    process.stdout.write(`${JSON.stringify({
      status: "planned",
      generated_at: plan.generated_at,
      guard_state: plan.resource.guard_state,
      resource_reason: plan.resource.reason,
      action: plan.action.kind,
      action_target: plan.action.target,
      action_max_invocations: plan.action.max_invocations,
      retention_state: plan.retention.state,
      cache_reclaim_bytes: plan.retention.cache_reclaim_bytes,
      timer_activation: plan.timer_contract.activation,
      timer_installed: plan.timer_contract.installed,
      real_service_operations: plan.counters.real_service_operations,
      real_backup_operations: plan.counters.real_backup_operations,
      control_plane_llm_calls: plan.counters.control_plane_llm_calls,
      operations_llm_calls: plan.counters.operations_llm_calls,
    })}\n`);
    return 0;
  } catch (error) {
    const code = error instanceof CanonicalOperationsError
      ? error.code
      : "OPERATIONS_PLAN_FAILED";
    process.stderr.write(`${JSON.stringify({ status: "failed", code })}\n`);
    return 2;
  }
}

function parseArgs(argv) {
  const values = Array.isArray(argv) ? argv.map((value) => String(value ?? "")) : [];
  const offset = values[0] === "plan" ? 1 : 0;
  const options = {
    help: values.includes("--help") || values.includes("-h"),
    snapshot: "",
    retentionPolicy: "",
    inventory: "",
    priorReceipt: "",
    now: "",
    backupEligible: false,
  };
  for (let index = offset; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--help" || flag === "-h") {
      continue;
    }
    if (flag === "--backup-eligible") {
      options.backupEligible = true;
      continue;
    }
    const next = values[index + 1];
    if (!next || next.startsWith("--")) {
      throw new CanonicalOperationsError("OPERATIONS_ARGUMENT_INVALID");
    }
    if (flag === "--snapshot") {
      options.snapshot = next;
    } else if (flag === "--retention-policy") {
      options.retentionPolicy = next;
    } else if (flag === "--inventory") {
      options.inventory = next;
    } else if (flag === "--prior-receipt") {
      options.priorReceipt = next;
    } else if (flag === "--now") {
      options.now = next;
    } else {
      throw new CanonicalOperationsError("OPERATIONS_ARGUMENT_INVALID");
    }
    index += 1;
  }
  if (!options.help && (!options.snapshot || !options.retentionPolicy || !options.inventory || !options.now)) {
    throw new CanonicalOperationsError("OPERATIONS_ARGUMENT_REQUIRED");
  }
  return options;
}

function readJson(filePath) {
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("invalid");
    }
    return parsed;
  } catch {
    throw new CanonicalOperationsError("OPERATIONS_INPUT_UNAVAILABLE");
  }
}

function helpText() {
  return [
    "Usage:",
    "  canonical-operations-plan.js plan --snapshot <resource.json> --retention-policy <retention-policy.json> --inventory <retention-inventory.json> --now <ISO-8601> [--prior-receipt <receipt.json>] [--backup-eligible]",
    "",
    "Builds a deterministic, local-only resource/self-heal/retention plan. It never installs a timer, invokes systemd, deletes data, performs a provider request, or invokes an LLM.",
  ].join("\n").concat("\n");
}

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  });
}

module.exports = { main, parseArgs };

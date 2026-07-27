"use strict";

const {
  buildActivationPlan,
  buildCleanStagingRehearsal,
} = require("../src/services/release/canonical-dress-rehearsal");

function parseMode(argv) {
  if (argv.length !== 2 || argv[0] !== "rehearse" || !argv[1].startsWith("--mode=")) {
    throw codedError("DRESS_REHEARSAL_ARGUMENT_INVALID");
  }
  const mode = argv[1].slice("--mode=".length);
  if (new Set(["activate", "canary-live", "rollback-live", "promote"]).has(mode)) {
    throw codedError("DRESS_REHEARSAL_EXTERNAL_EXECUTION_DISABLED");
  }
  if (!new Set(["local", "activation-plan"]).has(mode)) {
    throw codedError("DRESS_REHEARSAL_ARGUMENT_INVALID");
  }
  return mode;
}

function main(argv = process.argv.slice(2)) {
  try {
    const mode = parseMode(argv);
    const receipt = mode === "local"
      ? buildCleanStagingRehearsal()
      : buildActivationPlan();
    if (mode === "local" && receipt.status !== "passed") {
      throw codedError("DRESS_REHEARSAL_FAILED");
    }
    process.stdout.write(JSON.stringify(receipt) + "\n");
    process.stdout.write("DRESS_REHEARSAL=PASS\n");
    return 0;
  } catch (caught) {
    process.stderr.write((caught?.code || "DRESS_REHEARSAL_ERROR") + "\n");
    return 2;
  }
}

function codedError(code) {
  const failure = new Error(code);
  failure.code = code;
  return failure;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { main, parseMode };

"use strict";

const {
  buildFaultRecoveryMatrix,
  buildPostdeployFaultMatrixPlan,
} = require("../src/services/assurance/canonical-fault-recovery-matrix");

function parseMode(argv) {
  if (argv.length !== 2 || argv[0] !== "evaluate" || !argv[1].startsWith("--mode=")) {
    throw codedError("FAULT_RECOVERY_ARGUMENT_INVALID");
  }
  const mode = argv[1].slice("--mode=".length);
  if (mode === "real") {
    throw codedError("FAULT_RECOVERY_REAL_EXECUTION_DISABLED");
  }
  if (!new Set(["matrix", "postdeploy-plan"]).has(mode)) {
    throw codedError("FAULT_RECOVERY_ARGUMENT_INVALID");
  }
  return mode;
}

function main(argv = process.argv.slice(2)) {
  try {
    const mode = parseMode(argv);
    const receipt = mode === "matrix" ? buildFaultRecoveryMatrix() : buildPostdeployFaultMatrixPlan();
    process.stdout.write(`${JSON.stringify(receipt)}\n`);
    process.stdout.write("FAULT_RECOVERY_MATRIX=PASS\n");
    return 0;
  } catch (caught) {
    process.stderr.write(`${caught?.code || "FAULT_RECOVERY_ERROR"}\n`);
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

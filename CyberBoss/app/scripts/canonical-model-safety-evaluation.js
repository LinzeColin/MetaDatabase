"use strict";

const {
  FIXTURE_MODE,
  ModelSafetyEvaluationError,
  evaluateDeterministicModelSafety,
} = require("../src/services/evaluation/canonical-model-safety-evaluation");

function main(argv = process.argv.slice(2)) {
  try {
    if (argv.length !== 2 || argv[0] !== "evaluate" || !argv[1].startsWith("--mode=")) {
      throw new ModelSafetyEvaluationError("MODEL_SAFETY_ARGUMENT_INVALID");
    }
    const mode = argv[1].slice("--mode=".length);
    if (mode === "real") {
      throw new ModelSafetyEvaluationError("MODEL_SAFETY_REAL_TRIAL_DISABLED");
    }
    if (mode !== "fixture") {
      throw new ModelSafetyEvaluationError("MODEL_SAFETY_ARGUMENT_INVALID");
    }
    const scorecard = evaluateDeterministicModelSafety();
    if (scorecard.evaluation_mode !== FIXTURE_MODE || scorecard.status !== "passed") {
      throw new ModelSafetyEvaluationError("MODEL_SAFETY_EVALUATION_FAILED");
    }
    process.stdout.write(`${JSON.stringify(scorecard)}\nMODEL_SAFETY_EVALUATION=PASS\n`);
    return 0;
  } catch (error) {
    process.stderr.write(`${error?.code || "MODEL_SAFETY_EVALUATION_ERROR"}\n`);
    return 2;
  }
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { main };

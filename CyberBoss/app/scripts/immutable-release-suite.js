"use strict";

const {
  buildImmutableReleaseCandidate,
  buildOperatorRunbook,
} = require("../src/services/release/canonical-immutable-release");

function parseMode(argv) {
  if (argv.length !== 2 || argv[0] !== "evaluate" || !argv[1].startsWith("--mode=")) {
    throw codedError("IMMUTABLE_RELEASE_ARGUMENT_INVALID");
  }
  const mode = argv[1].slice("--mode=".length);
  if (new Set(["activate", "canary-live", "rollback-live"]).has(mode)) {
    throw codedError("IMMUTABLE_RELEASE_EXTERNAL_EXECUTION_DISABLED");
  }
  if (!new Set(["local", "operator-plan"]).has(mode)) {
    throw codedError("IMMUTABLE_RELEASE_ARGUMENT_INVALID");
  }
  return mode;
}

function main(argv = process.argv.slice(2)) {
  try {
    const mode = parseMode(argv);
    const receipt = mode === "local" ? buildImmutableReleaseCandidate() : buildOperatorRunbook();
    process.stdout.write(`${JSON.stringify(receipt)}\n`);
    process.stdout.write("IMMUTABLE_RELEASE_CANDIDATE=PASS\n");
    return 0;
  } catch (caught) {
    process.stderr.write(`${caught?.code || "IMMUTABLE_RELEASE_ERROR"}\n`);
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

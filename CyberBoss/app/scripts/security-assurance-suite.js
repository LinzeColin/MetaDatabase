"use strict";

const path = require("node:path");

const {
  SecurityAssuranceError,
  buildCorrespondingSourcePackage,
  buildSecurityAssurance,
} = require("../src/services/assurance/canonical-security-assurance");

function main(argv = process.argv.slice(2)) {
  try {
    if (argv.length !== 2 || argv[0] !== "evaluate" || !argv[1].startsWith("--mode=")) {
      throw new SecurityAssuranceError("SECURITY_ASSURANCE_ARGUMENT_INVALID");
    }
    const mode = argv[1].slice("--mode=".length);
    if (mode === "release" || mode === "external") {
      throw new SecurityAssuranceError("SECURITY_ASSURANCE_EXTERNAL_RELEASE_DISABLED");
    }
    if (mode !== "local" && mode !== "source-package") {
      throw new SecurityAssuranceError("SECURITY_ASSURANCE_ARGUMENT_INVALID");
    }
    const projectRoot = path.resolve(__dirname, "../..");
    const output = mode === "local"
      ? buildSecurityAssurance({ projectRoot })
      : buildCorrespondingSourcePackage({ projectRoot });
    process.stdout.write(JSON.stringify(output) + "\nSECURITY_ASSURANCE=PASS\n");
    return 0;
  } catch (error) {
    process.stderr.write((error?.code || "SECURITY_ASSURANCE_ERROR") + "\n");
    return 2;
  }
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { main };

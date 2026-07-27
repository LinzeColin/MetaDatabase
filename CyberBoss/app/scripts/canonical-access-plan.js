#!/usr/bin/env node

const fs = require("fs");
const {
  CanonicalAccessError,
  buildAccessDomainPlan,
  writeAccessPlanAtomic,
} = require("../src/services/access/canonical-access-domain");

async function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArgs(argv);
    if (options.help) {
      process.stdout.write(helpText());
      return 0;
    }
    const policy = readPolicy(options.policy);
    const plan = buildAccessDomainPlan({
      policy,
      audienceReference: options.audienceReference,
      issuerReference: options.issuerReference,
      keysetReference: options.keysetReference,
    });
    const receipt = writeAccessPlanAtomic({ plan, outputPath: options.output });
    process.stdout.write(`${JSON.stringify({
      status: "planned",
      plan_id: receipt.plan_id,
      plan_sha256: receipt.sha256,
      access_activation: plan.activation.access_policy,
      dns_activation: plan.activation.dns_route,
      analytics_activation: plan.analytics.state,
      real_cloudflare_operations: plan.activation.real_cloudflare_operations,
      control_plane_llm_calls: plan.counters.control_plane_llm_calls,
      operations_llm_calls: plan.counters.operations_llm_calls,
    })}\n`);
    return 0;
  } catch (error) {
    const code = error instanceof CanonicalAccessError ? error.code : "ACCESS_PLAN_FAILED";
    process.stderr.write(`${JSON.stringify({ status: "failed", code })}\n`);
    return 2;
  }
}

function parseArgs(argv) {
  const values = Array.isArray(argv) ? argv.map((value) => String(value ?? "")) : [];
  const options = {
    help: values.includes("--help") || values.includes("-h"),
    policy: "",
    audienceReference: "",
    issuerReference: "",
    keysetReference: "",
    output: "",
  };
  const offset = values[0] === "plan" ? 1 : 0;
  for (let index = offset; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--help" || flag === "-h") {
      continue;
    }
    const next = values[index + 1];
    if (!next || next.startsWith("--")) {
      throw new CanonicalAccessError("ACCESS_ARGUMENT_INVALID");
    }
    if (flag === "--policy") {
      options.policy = next;
    } else if (flag === "--audience-reference") {
      options.audienceReference = next;
    } else if (flag === "--issuer-reference") {
      options.issuerReference = next;
    } else if (flag === "--keyset-reference") {
      options.keysetReference = next;
    } else if (flag === "--output") {
      options.output = next;
    } else {
      throw new CanonicalAccessError("ACCESS_ARGUMENT_INVALID");
    }
    index += 1;
  }
  if (!options.help && (
    !options.policy ||
    !options.audienceReference ||
    !options.issuerReference ||
    !options.keysetReference ||
    !options.output
  )) {
    throw new CanonicalAccessError("ACCESS_ARGUMENT_REQUIRED");
  }
  return options;
}

function readPolicy(filePath) {
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("invalid");
    }
    return parsed;
  } catch {
    throw new CanonicalAccessError("ACCESS_POLICY_UNAVAILABLE");
  }
}

function helpText() {
  return [
    "Usage:",
    "  canonical-access-plan.js plan --policy <identity-scope.policy.json> --audience-reference <root-owned-reference> --issuer-reference <root-owned-reference> --keyset-reference <root-owned-reference> --output <plan.json>",
    "",
    "Creates only a local, atomic Cloudflare Access domain plan. It never performs a provider request or apply operation.",
  ].join("\n").concat("\n");
}

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  });
}

module.exports = { main, parseArgs };

#!/usr/bin/env node

const {
  CanonicalTimelineError,
  rebuildCanonicalTimeline,
  searchCanonicalTimeline,
} = require("../src/services/timeline/canonical-timeline-projection");

async function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArgs(argv);
    if (options.help) {
      process.stdout.write(helpText());
      return 0;
    }
    if (options.command === "search") {
      const result = searchCanonicalTimeline({
        outputDir: options.output,
        query: options.query,
        limit: options.limit,
      });
      process.stdout.write(`${JSON.stringify(result)}\n`);
      return 0;
    }
    const result = await rebuildCanonicalTimeline({
      sourcePath: options.source,
      outputDir: options.output,
      locale: options.locale,
    });
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return 0;
  } catch (error) {
    const code = error instanceof CanonicalTimelineError
      ? error.code
      : "CANONICAL_TIMELINE_BUILD_FAILED";
    process.stderr.write(`${JSON.stringify({ status: "failed", code })}\n`);
    return 2;
  }
}

function parseArgs(argv) {
  const values = Array.isArray(argv) ? argv.map((value) => String(value ?? "")) : [];
  const command = values[0] === "search" ? "search" : "build";
  const options = {
    command,
    help: values.includes("--help") || values.includes("-h"),
    source: "",
    output: "",
    locale: "zh-CN",
    query: "",
    limit: 20,
  };
  const offset = values[0] === "build" || values[0] === "search" ? 1 : 0;
  for (let index = offset; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--help" || flag === "-h") {
      continue;
    }
    const next = values[index + 1];
    if (!next || next.startsWith("--")) {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_ARGUMENT_INVALID");
    }
    if (flag === "--source") {
      options.source = next;
    } else if (flag === "--output") {
      options.output = next;
    } else if (flag === "--locale") {
      options.locale = next;
    } else if (flag === "--query") {
      options.query = next;
    } else if (flag === "--limit") {
      options.limit = next;
    } else {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_ARGUMENT_INVALID");
    }
    index += 1;
  }
  if (!options.help && !options.output) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_OUTPUT_REQUIRED");
  }
  if (!options.help && options.command === "build" && !options.source) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_SOURCE_REQUIRED");
  }
  return options;
}

function helpText() {
  return [
    "Usage:",
    "  canonical-timeline-build.js build --source <timeline-source.ndjson> --output <derived-output> [--locale zh-CN]",
    "  canonical-timeline-build.js search --output <derived-output> --query <关键词> [--limit 20]",
    "",
    "The builder reads canonical facts only, emits a derived static timeline, and preserves last-good on a failed rebuild.",
  ].join("\n").concat("\n");
}

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  });
}

module.exports = { main, parseArgs };

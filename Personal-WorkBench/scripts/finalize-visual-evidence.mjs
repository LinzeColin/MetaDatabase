import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const visualRoot = join(root, "13_evidence", "visual");
const rounds = await Promise.all(
  [1, 2, 3].map(async (round) => JSON.parse(await readFile(join(visualRoot, `round-${round}`, "metrics.json"), "utf8"))),
);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

for (const report of rounds) assert(report.status === "PASS", `round ${report.round} must pass before finalizing`);
const latest = rounds.at(-1);
const routes = Object.fromEntries(
  Object.entries(latest.routes).map(([route, detail]) => [
    route,
    {
      status: detail.status,
      artifacts: detail.artifacts,
      final_round_metric: detail.visual_metric,
      final_round_anchors: detail.anchor,
    },
  ]),
);
const report = {
  schema_version: "1.0.0",
  status: "PASS",
  reference_viewport_css: [472, 1024],
  method: "Chrome local preview captured the fixed 472×1024 app-stage canvas; browser-window dimensions are retained in each round. Task-pack masks were applied; metrics are diagnostics and not similarity percentages.",
  rounds: rounds.map(({ round, focus, status }) => ({ round, focus, status, metrics: `13_evidence/visual/round-${round}/metrics.json` })),
  routes,
  public_release_gate: "BLOCKED_ASSET_RIGHTS",
};
await writeFile(join(visualRoot, "manifest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ status: report.status, rounds: report.rounds.length, routes: Object.keys(report.routes).length, evidence: "13_evidence/visual/manifest.json" }));

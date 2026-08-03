import { access, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const evidencePath = join(root, "13_evidence", "visual", "manifest.json");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

await access(evidencePath);
const report = JSON.parse(await readFile(evidencePath, "utf8"));
assert(report.status === "PASS", "visual evidence status must be PASS");
assert(report.reference_viewport_css?.join("x") === "472x1024", "visual evidence must use the frozen 472×1024 viewport");
assert(report.rounds?.length >= 1 && report.rounds.length <= 3, "visual evidence must contain one to three real rounds");
assert(Object.keys(report.routes ?? {}).length === 5, "visual evidence must cover five reference routes");
for (const [route, detail] of Object.entries(report.routes ?? {})) {
  assert(detail.status === "PASS", `${route} visual result must pass`);
  for (const path of detail.artifacts ?? []) await access(join(root, path));
}
console.log(JSON.stringify({ status: "PASS", routes: Object.keys(report.routes).length, rounds: report.rounds.length, evidence: "13_evidence/visual/manifest.json" }));

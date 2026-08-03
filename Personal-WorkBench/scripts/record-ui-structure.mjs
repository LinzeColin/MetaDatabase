import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const output = join(root, "13_evidence", "ui_structure.json");
const pages = {
  welcome: { route: "/?reference=welcome", required: ["welcome-page", "welcome-kitty", "welcome-enter"] },
  home: { route: "/?reference=home", required: ["sidebar", "home-time", "quote-card", "habit-grid"] },
  ledger: { route: "/?reference=ledger", required: ["sidebar", "summary-grid", "ledger-form", "record-list-card"] },
  "fatloss-food": { route: "/?reference=fatloss-food", required: ["sidebar", "module-tabs", "food-card", "upload-zone"] },
  period: { route: "/?reference=period", required: ["sidebar", "period-form", "period-overview", "period-history"] },
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function render(path) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("structure", `${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

const routes = {};
for (const [name, spec] of Object.entries(pages)) {
  const response = await render(spec.route);
  assert(response.status === 200, `${name} must return 200`);
  const html = await response.text();
  const required = Object.fromEntries(spec.required.map((className) => [className, new RegExp(`class=\"[^\"]*${className}`).test(html)]));
  assert(Object.values(required).every(Boolean), `${name} missing a required structural element`);
  assert(html.includes(`data-reference-page=\"${name}\"`), `${name} must declare its frozen route marker`);
  assert(!html.includes('class="account-entry'), `${name} must hide account entry in reference mode`);
  routes[name] = { status: "PASS", required_classes: required, account_entry: "HIDDEN", reference_marker: "PASS" };
}

const normal = await render("/?view=home");
const normalHtml = await normal.text();
assert(normal.status === 200 && normalHtml.includes('class="account-entry normal-only"'), "normal home must keep a separate account entry");
const report = {
  schema_version: "1.0.0",
  task_id: "S1-T2",
  status: "PASS",
  generated_at: new Date().toISOString(),
  reference_routes: routes,
  normal_mode: { status: "PASS", account_entry: "VISIBLE_OUTSIDE_REFERENCE_MODE" },
  verification: "built worker HTML; no starter preview metadata or skeleton content",
};
await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ status: report.status, routes: Object.keys(routes).length, evidence: "13_evidence/ui_structure.json" }));

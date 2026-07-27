const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const test = require("node:test");
const assert = require("node:assert/strict");

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-timeline-cli-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function run(args) {
  return spawnSync(process.execPath, ["app/scripts/canonical-timeline-build.js", ...args], {
    cwd: path.resolve(__dirname, ".."),
    encoding: "utf8",
  });
}

test("canonical timeline CLI builds and searches a read-only projection", (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "timeline-source.ndjson");
  const output = path.join(root, "derived-timeline");
  fs.writeFileSync(source, `${JSON.stringify({
    schema_version: 1,
    source: "cyberboss-canonical",
    event_id: "event_cli_0001",
    occurred_at: "2026-07-27T10:15:00.000Z",
    event_type: "recovery_completed",
    status: "succeeded",
    job_id: "private-job-cli-0001",
    summary_redacted: "CB300-PRIVATE-CLI-SUMMARY",
    record_sha256: "b".repeat(64),
  })}\n`, "utf8");
  const before = fs.readFileSync(source, "utf8");

  const build = run(["build", "--source", source, "--output", output]);
  assert.equal(build.status, 0, build.stderr);
  const buildResult = JSON.parse(build.stdout);
  assert.equal(buildResult.status, "built");
  assert.equal(buildResult.directCanonicalWrites, 0);
  assert.equal(fs.readFileSync(source, "utf8"), before);

  const search = run(["search", "--output", output, "--query", "恢复"]);
  assert.equal(search.status, 0, search.stderr);
  const searchResult = JSON.parse(search.stdout);
  assert.equal(searchResult.total, 1);
  assert.equal(searchResult.entries[0].title, "恢复完成");
  assert.doesNotMatch(search.stdout, /private-job|PRIVATE-CLI|event_cli/);
});

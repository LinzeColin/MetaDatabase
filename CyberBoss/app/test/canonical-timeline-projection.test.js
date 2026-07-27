const fs = require("fs");
const os = require("os");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  CanonicalTimelineError,
  rebuildCanonicalTimeline,
  searchCanonicalTimeline,
} = require("../src/services/timeline/canonical-timeline-projection");

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-timeline-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function record(index, overrides = {}) {
  const suffix = String(index).padStart(4, "0");
  return {
    schema_version: 1,
    source: "cyberboss-canonical",
    event_id: `event_fixture_${suffix}`,
    occurred_at: `2026-07-27T0${index}:00:00.000Z`,
    event_type: "job.job_transition",
    status: "replied",
    job_id: `private-job-${suffix}`,
    summary_redacted: `CB300-PRIVATE-SUMMARY-${suffix}`,
    record_sha256: `${String(index).repeat(64)}`.slice(0, 64),
    ...overrides,
  };
}

function writeNdjson(filePath, rows) {
  fs.writeFileSync(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
}

test("canonical timeline rebuild is deterministic, read-only, searchable, and Chinese", async (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "timeline-source.ndjson");
  const output = path.join(root, "derived-timeline");
  const rows = [
    record(1),
    record(2, { event_type: "release_completed", status: "succeeded" }),
  ];
  writeNdjson(source, rows);
  const before = fs.readFileSync(source, "utf8");

  const first = await rebuildCanonicalTimeline({ sourcePath: source, outputDir: output });
  assert.equal(first.status, "built");
  assert.equal(first.eventCount, 2);
  assert.equal(first.directCanonicalWrites, 0);
  assert.equal(first.fallbackUsed, false);
  assert.equal(fs.readFileSync(source, "utf8"), before);

  const release = path.join(output, first.release);
  const projection = JSON.parse(fs.readFileSync(path.join(release, "projection.json"), "utf8"));
  const search = searchCanonicalTimeline({ outputDir: output, query: "完成" });
  const rendered = fs.readFileSync(path.join(release, "site", "index.html"), "utf8");
  const dashboard = fs.readFileSync(path.join(release, "site", "assets", "dashboard.js"), "utf8");
  const completeOutput = fs.readdirSync(release, { recursive: true })
    .filter((entry) => typeof entry === "string")
    .filter((entry) => fs.statSync(path.join(release, entry)).isFile())
    .map((entry) => fs.readFileSync(path.join(release, entry), "utf8"))
    .join("\n");

  assert.equal(projection.source, "canonical");
  assert.deepEqual(projection.events.map((entry) => entry.title), ["任务完成", "发布完成"]);
  assert.equal(search.total, 2);
  assert.equal(search.entries.every((entry) => /^evt-[a-f0-9]{24}$/.test(entry.id)), true);
  assert.match(rendered, /<title>CyberBoss 时间线<\/title>/);
  assert.match(dashboard, /children: "时间线"/);
  assert.doesNotMatch(dashboard, /children: "Timeline"/);
  for (const forbidden of [
    rows[0].event_id,
    rows[0].job_id,
    rows[0].summary_redacted,
    rows[0].record_sha256,
  ]) {
    assert.equal(completeOutput.includes(forbidden), false);
  }

  const second = await rebuildCanonicalTimeline({ sourcePath: source, outputDir: output });
  assert.equal(second.status, "reused");
  assert.equal(second.buildDigest, first.buildDigest);
  assert.equal(second.projectionSha256, first.projectionSha256);
});

test("failed canonical rebuild preserves the exact last-good pointer", async (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "timeline-source.ndjson");
  const output = path.join(root, "derived-timeline");
  writeNdjson(source, [record(3)]);
  const built = await rebuildCanonicalTimeline({ sourcePath: source, outputDir: output });
  const pointerPath = path.join(output, "last-good.json");
  const pointerBefore = fs.readFileSync(pointerPath, "utf8");

  writeNdjson(source, [record(4, { prompt: "this field must never enter a projection" })]);
  const fallback = await rebuildCanonicalTimeline({ sourcePath: source, outputDir: output });

  assert.equal(fallback.status, "last_good");
  assert.equal(fallback.fallbackUsed, true);
  assert.equal(fallback.failureCode, "CANONICAL_TIMELINE_FORBIDDEN_FIELD");
  assert.equal(fallback.buildDigest, built.buildDigest);
  assert.equal(fs.readFileSync(pointerPath, "utf8"), pointerBefore);
});

test("canonical timeline fails closed before a first build on divergent or private input", async (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "timeline-source.ndjson");
  const output = path.join(root, "derived-timeline");
  const first = record(5);
  const divergent = record(5, { record_sha256: "a".repeat(64) });
  writeNdjson(source, [first, divergent]);

  await assert.rejects(
    rebuildCanonicalTimeline({ sourcePath: source, outputDir: output }),
    (error) => error instanceof CanonicalTimelineError && error.code === "CANONICAL_TIMELINE_DIVERGENT_EVENT",
  );
  assert.equal(fs.existsSync(path.join(output, "last-good.json")), false);

  writeNdjson(source, [record(6, { source: "noncanonical-fixture" })]);
  await assert.rejects(
    rebuildCanonicalTimeline({ sourcePath: source, outputDir: output }),
    (error) => error instanceof CanonicalTimelineError && error.code === "CANONICAL_TIMELINE_SOURCE_INVALID",
  );
});

test("empty canonical input renders an explicit empty state instead of vendor demo facts", async (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "timeline-source.ndjson");
  const output = path.join(root, "derived-timeline");
  fs.writeFileSync(source, "", "utf8");

  const result = await rebuildCanonicalTimeline({ sourcePath: source, outputDir: output });
  const release = path.join(output, result.release);
  const data = fs.readFileSync(path.join(release, "site", "dashboard-data.json"), "utf8");
  const html = fs.readFileSync(path.join(release, "site", "index.html"), "utf8");

  assert.equal(result.eventCount, 0);
  assert.match(data, /"events":\[\]/);
  assert.match(html, /暂无可公开的时间线事件/);
  assert.doesNotMatch(data, /demo/i);
});

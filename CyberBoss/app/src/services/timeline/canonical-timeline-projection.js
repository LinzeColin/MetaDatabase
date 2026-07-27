const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const TIMELINE_PACKAGE_ROOT = path.dirname(require.resolve("timeline-for-agent/package.json"));
const {
  buildTimelineDashboard,
} = require(path.join(TIMELINE_PACKAGE_ROOT, "src", "infra", "timeline", "timeline-dashboard-builder"));
const {
  createDefaultTaxonomy,
} = require(path.join(TIMELINE_PACKAGE_ROOT, "src", "infra", "timeline", "default-taxonomy"));

const PROJECTION_SCHEMA = "cyberboss.timeline_projection.v1";
const LAST_GOOD_SCHEMA = "cyberboss.timeline_last_good.v1";
const SEARCH_SCHEMA = "cyberboss.timeline_search_index.v1";
const BUILD_SCHEMA = "cyberboss.timeline_build.v1";
const ALLOWED_CANONICAL_FIELDS = new Set([
  "schema_version",
  "source",
  "event_id",
  "occurred_at",
  "recorded_at",
  "event_type",
  "status",
  "job_id",
  "correlation_id",
  "workspace_alias",
  "summary_redacted",
  "record_sha256",
]);
const TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "failed_terminal",
  "cancelled",
  "expired",
  "replied",
  "reply_failed",
]);

class CanonicalTimelineError extends Error {
  constructor(code) {
    super(code);
    this.name = "CanonicalTimelineError";
    this.code = code;
  }
}

async function rebuildCanonicalTimeline({
  sourcePath,
  outputDir,
  locale = "zh-CN",
} = {}) {
  const source = resolveRequiredFile(sourcePath, "CANONICAL_TIMELINE_SOURCE_REQUIRED");
  const output = resolveRequiredDirectory(outputDir, "CANONICAL_TIMELINE_OUTPUT_REQUIRED");
  const pointerPath = path.join(output, "last-good.json");
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });

  try {
    const sourceBytes = fs.readFileSync(source);
    const sourceSha256 = sha256(sourceBytes);
    const canonicalEvents = parseCanonicalEvents(sourceBytes);
    const projection = createProjection(canonicalEvents, sourceSha256);
    const projectionBytes = Buffer.from(`${stableJson(projection)}\n`, "utf8");
    const buildDigest = sha256(Buffer.from(stableJson({
      schema_version: BUILD_SCHEMA,
      renderer: readRendererVersion(),
      source_sha256: sourceSha256,
      projection_sha256: sha256(projectionBytes),
      locale: normalizeLocale(locale),
    }), "utf8"));
    const searchIndex = createSearchIndex(projection, buildDigest);
    const searchBytes = Buffer.from(`${stableJson(searchIndex)}\n`, "utf8");
    const releases = path.join(output, "releases");
    const releasePath = path.join(releases, buildDigest);
    let status = "reused";

    if (!fs.existsSync(releasePath)) {
      status = "built";
      await buildReleaseAsync({
        output,
        releasePath,
        buildDigest,
        projection,
        projectionBytes,
        searchIndex,
        searchBytes,
        canonicalEvents,
        locale,
      });
    }
    const build = readJson(path.join(releasePath, "build-manifest.json"), "CANONICAL_TIMELINE_BUILD_INVALID");
    assertBuildManifest(build, { buildDigest, sourceSha256, projectionBytes, searchBytes });
    const pointer = {
      schema_version: LAST_GOOD_SCHEMA,
      build_digest: buildDigest,
      release: path.posix.join("releases", buildDigest),
      source_sha256: sourceSha256,
      projection_sha256: sha256(projectionBytes),
      search_index_sha256: sha256(searchBytes),
      event_count: projection.events.length,
      locale: normalizeLocale(locale),
    };
    atomicWrite(pointerPath, Buffer.from(`${stableJson(pointer)}\n`, "utf8"));
    return Object.freeze({
      status,
      buildDigest,
      sourceSha256,
      projectionSha256: pointer.projection_sha256,
      searchIndexSha256: pointer.search_index_sha256,
      eventCount: pointer.event_count,
      release: pointer.release,
      directCanonicalWrites: 0,
      fallbackUsed: false,
    });
  } catch (error) {
    const fallback = readLastGood(output);
    if (fallback) {
      return Object.freeze({
        status: "last_good",
        buildDigest: fallback.build_digest,
        sourceSha256: fallback.source_sha256,
        projectionSha256: fallback.projection_sha256,
        searchIndexSha256: fallback.search_index_sha256,
        eventCount: fallback.event_count,
        release: fallback.release,
        directCanonicalWrites: 0,
        fallbackUsed: true,
        failureCode: safeFailureCode(error),
      });
    }
    throw error;
  }
}

function searchCanonicalTimeline({ outputDir, query = "", limit = 20 } = {}) {
  const output = resolveRequiredDirectory(outputDir, "CANONICAL_TIMELINE_OUTPUT_REQUIRED");
  const pointer = readLastGood(output);
  if (!pointer) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_LAST_GOOD_MISSING");
  }
  const release = resolveRelease(output, pointer.release);
  const index = readJson(path.join(release, "search-index.json"), "CANONICAL_TIMELINE_SEARCH_INVALID");
  if (
    index.schema_version !== SEARCH_SCHEMA
    || index.build_digest !== pointer.build_digest
    || !Array.isArray(index.entries)
  ) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_SEARCH_INVALID");
  }
  const needle = normalizeSearch(query);
  const boundedLimit = normalizeLimit(limit);
  const entries = index.entries.filter((entry) => isPublicSearchEntry(entry));
  const matches = needle
    ? entries.filter((entry) => searchHaystack(entry).includes(needle))
    : entries;
  return Object.freeze({
    buildDigest: pointer.build_digest,
    sourceSha256: pointer.source_sha256,
    query: needle,
    total: matches.length,
    entries: Object.freeze(matches.slice(0, boundedLimit).map((entry) => Object.freeze({ ...entry }))),
  });
}

function readLastGood(outputDir) {
  const pointerPath = path.join(path.resolve(outputDir), "last-good.json");
  if (!fs.existsSync(pointerPath)) {
    return null;
  }
  try {
    const pointer = readJson(pointerPath, "CANONICAL_TIMELINE_LAST_GOOD_INVALID");
    if (
      pointer.schema_version !== LAST_GOOD_SCHEMA
      || !isDigest(pointer.build_digest)
      || !isDigest(pointer.source_sha256)
      || !isDigest(pointer.projection_sha256)
      || !isDigest(pointer.search_index_sha256)
      || !Number.isInteger(pointer.event_count)
      || pointer.event_count < 0
      || !isSafeRelease(pointer.release)
    ) {
      return null;
    }
    const release = resolveRelease(outputDir, pointer.release);
    if (!fs.existsSync(path.join(release, "build-manifest.json"))) {
      return null;
    }
    return pointer;
  } catch {
    return null;
  }
}

async function buildReleaseAsync({
  output,
  releasePath,
  buildDigest,
  projection,
  projectionBytes,
  searchIndex,
  searchBytes,
  canonicalEvents,
  locale,
}) {
  const parent = path.dirname(output);
  const staging = fs.mkdtempSync(path.join(parent, `.${path.basename(output)}-timeline-stage-`));
  const stagedRelease = path.join(staging, "release");
  try {
    fs.mkdirSync(stagedRelease, { recursive: true, mode: 0o700 });
    const packageRoot = TIMELINE_PACKAGE_ROOT;
    const siteDir = path.join(stagedRelease, "site");
    if (projection.events.length > 0) {
      const facts = buildVendorFacts(projection.events);
      const store = {
        factsFilePath: "",
        taxonomyFilePath: "",
        locale: normalizeLocale(locale),
        getState() {
          return {
            version: 1,
            timezone: "UTC",
            taxonomy: createDefaultTaxonomy(),
            facts,
            proposals: [],
          };
        },
      };
      await buildTimelineDashboard({
        store,
        siteDir,
        locale: normalizeLocale(locale),
        entryFile: path.join(packageRoot, "src", "timeline", "dashboard-app.jsx"),
        cssFile: path.join(packageRoot, "src", "timeline", "css", "dashboard.css"),
      });
      localizeRenderedChrome(siteDir);
    } else {
      buildEmptyTimelineSite(siteDir, packageRoot);
    }
    atomicWrite(path.join(stagedRelease, "projection.json"), projectionBytes);
    atomicWrite(path.join(stagedRelease, "search-index.json"), searchBytes);
    const manifest = {
      schema_version: BUILD_SCHEMA,
      build_digest: buildDigest,
      renderer: readRendererVersion(),
      source_sha256: projection.source_sha256,
      projection_sha256: sha256(projectionBytes),
      search_index_sha256: sha256(searchBytes),
      event_count: projection.events.length,
      locale: normalizeLocale(locale),
      direct_canonical_writes: 0,
    };
    atomicWrite(
      path.join(stagedRelease, "build-manifest.json"),
      Buffer.from(`${stableJson(manifest)}\n`, "utf8"),
    );
    assertReleaseShape(stagedRelease);
    assertReleasePrivacy(stagedRelease, canonicalEvents);
    fs.mkdirSync(path.dirname(releasePath), { recursive: true, mode: 0o700 });
    if (fs.existsSync(releasePath)) {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_RELEASE_COLLISION");
    }
    fs.renameSync(stagedRelease, releasePath);
  } finally {
    fs.rmSync(staging, { recursive: true, force: true });
  }
}

function parseCanonicalEvents(sourceBytes) {
  const records = [];
  const seen = new Map();
  for (const raw of sourceBytes.toString("utf8").split(/\r?\n/)) {
    if (!raw.trim()) {
      continue;
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_NDJSON_INVALID");
    }
    const record = normalizeCanonicalEvent(parsed);
    const previous = seen.get(record.event_id);
    if (previous && previous !== record.record_sha256) {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_DIVERGENT_EVENT");
    }
    if (!previous) {
      seen.set(record.event_id, record.record_sha256);
      records.push(record);
    }
  }
  return records.sort((left, right) => (
    left.occurred_at.localeCompare(right.occurred_at)
    || left.event_id.localeCompare(right.event_id)
  ));
}

function normalizeCanonicalEvent(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_EVENT_INVALID");
  }
  if (value.schema_version !== 1 || normalizeText(value.source) !== "cyberboss-canonical") {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_SOURCE_INVALID");
  }
  for (const key of Object.keys(value)) {
    if (!ALLOWED_CANONICAL_FIELDS.has(key)) {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_FORBIDDEN_FIELD");
    }
  }
  const eventId = normalizeOpaqueId(value.event_id);
  const occurredAt = normalizeTimestamp(value.occurred_at);
  const eventType = normalizeEventType(value.event_type);
  const status = normalizeStatus(value.status);
  const recordSha256 = normalizeDigest(value.record_sha256);
  if (!eventId || !occurredAt || !eventType || !status || !recordSha256) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_EVENT_INVALID");
  }
  return {
    event_id: eventId,
    occurred_at: occurredAt,
    event_type: eventType,
    status,
    job_id: normalizeOpaqueId(value.job_id),
    summary_redacted: normalizeText(value.summary_redacted),
    record_sha256: recordSha256,
  };
}

function createProjection(canonicalEvents, sourceSha256) {
  const events = canonicalEvents.map((record) => {
    const publicId = `evt-${sha256(Buffer.from(record.event_id, "utf8")).slice(0, 24)}`;
    const interval = normalizeInterval(record.occurred_at);
    return {
      id: publicId,
      date: interval.date,
      start_at: interval.startAt,
      end_at: interval.endAt,
      title: publicTitle(record),
      status: record.status,
    };
  });
  return {
    schema_version: PROJECTION_SCHEMA,
    source: "canonical",
    source_sha256: sourceSha256,
    direct_canonical_writes: 0,
    events,
  };
}

function createSearchIndex(projection, buildDigest) {
  return {
    schema_version: SEARCH_SCHEMA,
    build_digest: buildDigest,
    source_sha256: projection.source_sha256,
    entries: projection.events.map((event) => ({
      id: event.id,
      date: event.date,
      title: event.title,
      status: event.status,
    })),
  };
}

function buildVendorFacts(events) {
  const facts = {};
  for (const event of events) {
    const current = facts[event.date] || {
      status: "final",
      updatedAt: event.end_at,
      source: "canonical_projection",
      events: [],
    };
    current.updatedAt = current.updatedAt > event.end_at ? current.updatedAt : event.end_at;
    current.events.push({
      id: event.id,
      startAt: event.start_at,
      endAt: event.end_at,
      title: event.title,
      note: "",
      categoryId: "work",
      subcategoryId: "work.other",
      tags: [event.status],
      confidence: "high",
      sourceMessageIds: [],
    });
    facts[event.date] = current;
  }
  for (const value of Object.values(facts)) {
    value.events.sort((left, right) => left.startAt.localeCompare(right.startAt) || left.id.localeCompare(right.id));
  }
  return facts;
}

function localizeRenderedChrome(siteDir) {
  const indexPath = path.join(siteDir, "index.html");
  const index = fs.readFileSync(indexPath, "utf8");
  if (!index.includes("<title>")) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_INDEX_INVALID");
  }
  atomicWrite(
    indexPath,
    Buffer.from(index.replace(/<title>[^<]*<\/title>/, "<title>CyberBoss 时间线</title>"), "utf8"),
  );
  const dashboardPath = path.join(siteDir, "assets", "dashboard.js");
  const dashboard = fs.readFileSync(dashboardPath, "utf8");
  const upstreamHeading = 'children: "Timeline"';
  if (!dashboard.includes(upstreamHeading)) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_LOCALE_INVALID");
  }
  atomicWrite(
    dashboardPath,
    Buffer.from(dashboard.replaceAll(upstreamHeading, 'children: "时间线"'), "utf8"),
  );
}

function buildEmptyTimelineSite(siteDir, packageRoot) {
  const assets = path.join(siteDir, "assets");
  fs.mkdirSync(assets, { recursive: true, mode: 0o700 });
  fs.copyFileSync(
    path.join(packageRoot, "src", "timeline", "css", "dashboard.css"),
    path.join(assets, "dashboard.css"),
  );
  atomicWrite(
    path.join(assets, "dashboard.js"),
    Buffer.from("document.getElementById('root').textContent='暂无可公开的时间线事件。';\n", "utf8"),
  );
  atomicWrite(
    path.join(siteDir, "dashboard-data.json"),
    Buffer.from(`${stableJson({ locale: "zh-CN", events: [] })}\n`, "utf8"),
  );
  atomicWrite(
    path.join(siteDir, "index.html"),
    Buffer.from([
      "<!doctype html>",
      "<html lang=\"zh-CN\">",
      "<head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>CyberBoss 时间线</title><link rel=\"stylesheet\" href=\"./assets/dashboard.css\" /></head>",
      "<body><main><h1>CyberBoss 时间线</h1><div id=\"root\">暂无可公开的时间线事件。</div></main><script src=\"./assets/dashboard.js\"></script></body>",
      "</html>",
    ].join("\n"), "utf8"),
  );
}

function assertReleaseShape(releasePath) {
  for (const relative of [
    "site/index.html",
    "site/dashboard-data.json",
    "site/assets/dashboard.js",
    "site/assets/dashboard.css",
    "projection.json",
    "search-index.json",
    "build-manifest.json",
  ]) {
    if (!fs.existsSync(path.join(releasePath, relative))) {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_RENDER_INCOMPLETE");
    }
  }
}

function assertReleasePrivacy(releasePath, canonicalEvents) {
  const forbidden = canonicalEvents.flatMap((event) => [
    event.event_id,
    event.job_id,
    event.summary_redacted,
    event.record_sha256,
  ]).filter((value) => typeof value === "string" && value.length >= 8);
  for (const filePath of listFiles(releasePath)) {
    const content = fs.readFileSync(filePath, "utf8");
    if (forbidden.some((value) => content.includes(value))) {
      throw new CanonicalTimelineError("CANONICAL_TIMELINE_PRIVACY_LEAK");
    }
  }
}

function assertBuildManifest(manifest, { buildDigest, sourceSha256, projectionBytes, searchBytes }) {
  if (
    manifest.schema_version !== BUILD_SCHEMA
    || manifest.build_digest !== buildDigest
    || manifest.source_sha256 !== sourceSha256
    || manifest.projection_sha256 !== sha256(projectionBytes)
    || manifest.search_index_sha256 !== sha256(searchBytes)
    || manifest.direct_canonical_writes !== 0
  ) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_BUILD_INVALID");
  }
}

function resolveRequiredFile(value, code) {
  const resolved = normalizeText(value);
  if (!resolved) {
    throw new CanonicalTimelineError(code);
  }
  const filePath = path.resolve(resolved);
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_SOURCE_UNAVAILABLE");
  }
  return filePath;
}

function resolveRequiredDirectory(value, code) {
  const resolved = normalizeText(value);
  if (!resolved) {
    throw new CanonicalTimelineError(code);
  }
  const output = path.resolve(resolved);
  if (fs.existsSync(output) && !fs.statSync(output).isDirectory()) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_OUTPUT_INVALID");
  }
  return output;
}

function resolveRelease(outputDir, relative) {
  if (!isSafeRelease(relative)) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_LAST_GOOD_INVALID");
  }
  const root = path.resolve(outputDir);
  const release = path.resolve(root, relative);
  if (!release.startsWith(`${root}${path.sep}`)) {
    throw new CanonicalTimelineError("CANONICAL_TIMELINE_LAST_GOOD_INVALID");
  }
  return release;
}

function normalizeInterval(occurredAt) {
  const value = new Date(occurredAt);
  value.setUTCSeconds(0, 0);
  const date = value.toISOString().slice(0, 10);
  const end = new Date(value.getTime() + 60_000);
  const dayEnd = new Date(`${date}T23:59:59.999Z`);
  return {
    date,
    startAt: value.toISOString(),
    endAt: (end <= dayEnd ? end : dayEnd).toISOString(),
  };
}

function publicTitle(record) {
  if (record.event_type === "release_completed") {
    return "发布完成";
  }
  if (record.event_type === "incident_declared") {
    return "故障事件";
  }
  if (record.event_type === "recovery_completed") {
    return "恢复完成";
  }
  if (record.status === "succeeded" || record.status === "replied") {
    return "任务完成";
  }
  if (record.status === "cancelled" || record.status === "expired") {
    return "任务取消";
  }
  return "任务失败";
}

function normalizeEventType(value) {
  const text = normalizeText(value);
  return /^[a-z][a-z0-9_.-]{0,63}$/.test(text) ? text : "";
}

function normalizeStatus(value) {
  const text = normalizeText(value);
  return TERMINAL_STATUSES.has(text) ? text : "";
}

function normalizeOpaqueId(value) {
  const text = normalizeText(value);
  return /^[A-Za-z0-9_.:-]{1,160}$/.test(text) ? text : "";
}

function normalizeDigest(value) {
  const text = normalizeText(value);
  return isDigest(text) ? text : "";
}

function normalizeTimestamp(value) {
  const text = normalizeText(value);
  const date = new Date(text);
  return text && Number.isFinite(date.getTime()) ? date.toISOString() : "";
}

function normalizeLocale(value) {
  return normalizeText(value) === "en" ? "en" : "zh-CN";
}

function normalizeSearch(value) {
  return normalizeText(value).toLocaleLowerCase("zh-CN");
}

function normalizeLimit(value) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isInteger(parsed) && parsed > 0 ? Math.min(parsed, 100) : 20;
}

function isPublicSearchEntry(value) {
  return !!value
    && typeof value === "object"
    && /^evt-[a-f0-9]{24}$/.test(String(value.id || ""))
    && /^\d{4}-\d{2}-\d{2}$/.test(String(value.date || ""))
    && ["发布完成", "故障事件", "恢复完成", "任务完成", "任务取消", "任务失败"].includes(value.title)
    && TERMINAL_STATUSES.has(value.status);
}

function searchHaystack(entry) {
  return [entry.date, entry.title, entry.status].join(" ").toLocaleLowerCase("zh-CN");
}

function listFiles(root) {
  const files = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const candidate = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...listFiles(candidate));
    } else if (entry.isFile()) {
      files.push(candidate);
    }
  }
  return files;
}

function readJson(filePath, code) {
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("invalid");
    }
    return parsed;
  } catch {
    throw new CanonicalTimelineError(code);
  }
}

function atomicWrite(filePath, bytes) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true, mode: 0o700 });
  const temporary = path.join(path.dirname(filePath), `.${path.basename(filePath)}.${crypto.randomUUID()}.tmp`);
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, bytes);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporary, filePath);
  } finally {
    if (descriptor !== undefined) {
      fs.closeSync(descriptor);
    }
    if (fs.existsSync(temporary)) {
      fs.rmSync(temporary, { force: true });
    }
  }
}

function stableJson(value) {
  return JSON.stringify(sortJson(value));
}

function sortJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortJson);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortJson(value[key])]));
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function isDigest(value) {
  return /^[a-f0-9]{64}$/.test(String(value || ""));
}

function isSafeRelease(value) {
  return /^releases\/[a-f0-9]{64}$/.test(String(value || ""));
}

function safeFailureCode(error) {
  return error instanceof CanonicalTimelineError ? error.code : "CANONICAL_TIMELINE_BUILD_FAILED";
}

function readRendererVersion() {
  const packageJson = JSON.parse(fs.readFileSync(path.join(TIMELINE_PACKAGE_ROOT, "package.json"), "utf8"));
  return `timeline-for-agent@${normalizeText(packageJson.version) || "unknown"}`;
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

module.exports = {
  BUILD_SCHEMA,
  CanonicalTimelineError,
  LAST_GOOD_SCHEMA,
  PROJECTION_SCHEMA,
  SEARCH_SCHEMA,
  readLastGood,
  rebuildCanonicalTimeline,
  searchCanonicalTimeline,
};

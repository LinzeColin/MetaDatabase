"use strict";

// CB-810 / AC-032: the business-line Status matrix.
//
// The matrix is the surface an operator looks at when something is wrong, so
// it is exactly the surface most likely to grow a convenient identifier. Every
// row is therefore checked twice before it can be published: the frozen field
// list must be present and complete, and both field names and field values are
// scanned recursively for anything that could identify a person.
//
// The scan fails closed. An unrecognised business line, a missing required
// field, an extra field, a forbidden name at any depth or a value matching a
// sensitive pattern all refuse the whole snapshot rather than dropping one row
// and publishing the rest — a partially redacted snapshot reads as complete.

const { createHash } = require("node:crypto");

// 双模式（AC-026）和另外五段纵向内容。
//
// MODES 只在 vertical-sections.js 里定义一份，这里转出去。两处各写一份的话，
// 迟早会不一致——而不一致的那一天，矩阵按一份清单查完整性、modes 段按另一份
// 渲染，缺的那个模式两边都以为对方管了。
const {
  MODES,
  SECTION_NAMES,
  buildBackups,
  buildCanonicalSync,
  buildModes,
  buildQueue,
  buildResources,
} = require("./vertical-sections");

// Frozen by machine/status_business_matrix.json.
const BUSINESS_LINES = Object.freeze([
  "wechat_channel",
  "user_registration_consent",
  "user_isolation",
  "secure_setup_portal",
  "ai_provider_connection",
  "four_source_import",
  "profile_memory",
  "timeline_diary_reminder",
  "canonical_sync",
  "r2_oci_objects",
  "backup_restore",
  "owner_codex_runtime",
  "release_rollback",
  "model_usage_budget_circuit",
  // v0.0.0.9 的第 15 项（CB9-510 / AC-026）。
  //
  // 时区和位置是这一版新加的一整条业务线：加入页静默采集 → 信号合并与确认 →
  // 提醒和安静时段按本人时区。它有自己的失败方式（采不到、猜错了、用户改了
  // 之后没生效），不挂在别的线下面就没人看得见。
  "location_timezone",
]);

const REQUIRED_FIELDS = Object.freeze([
  "business_line",
  // 双模式：矩阵是 15 项能力 × 2 个模式，不是 15 行。
  "mode",
  "stage",
  "state",
  "upstream",
  "downstream",
  "slo",
  "queue_depth",
  "oldest_job_seconds",
  "error_rate",
  "last_success_at",
  // AC-035 要「上次成功/失败」两个都有。
  //
  // 只有成功时间的话，一条长期不健康的线和一条从没跑过的线长得一模一样——
  // 两者的 last_success_at 都是 null，而它们该做的事完全不同（前者去查故障，
  // 后者去问为什么没人用）。这和 CB9-500 分开 UNKNOWN 与 UNAVAILABLE 是同一
  // 件事，只是换到了矩阵这一层。
  "last_failure_at",
  "last_recovery_at",
  // AC-035 要「建议动作」。
  //
  // 一个只说「blocked」的面板等于把排查全推给看的人。而这一层**知道**下一步
  // 该干什么——它有 reason_code。把动作写出来，值班的人不用先去读代码。
  "suggested_action",
  "release",
  "rollback_release",
  "reason_code",
]);

const FORBIDDEN_FIELDS = Object.freeze([
  "wechat_id",
  "user_id",
  "name",
  "message",
  "prompt",
  "response",
  "api_key",
  "file_name",
  "profile",
  "object_key",
]);

// Additive protection over the frozen ten. These are the names the same data
// arrives under when someone adds a field without reading the contract.
//
// Note what is deliberately absent: the bare fragment "token". The frozen
// model-usage contract requires `reserved_tokens` and `charged_tokens`, so a
// blanket ban on the substring would forbid the very fields AC-048 mandates.
// The credential-bearing token names are listed individually instead.
const FORBIDDEN_FIELD_FRAGMENTS = Object.freeze([
  "wechat", "weixin", "wxid", "userid", "user_id", "sender", "person",
  "message", "prompt", "response", "api_key", "apikey", "filename",
  "file_name", "profile", "object_key", "objectkey", "secret",
  "password", "authorization", "credential", "email", "phone", "nickname",
  "avatar", "private_key",
  "access_token", "refresh_token", "session_token", "setup_token",
  "csrf_token", "auth_token", "bearer_token", "id_token", "api_token",
  "token_value", "token_hash", "token_secret", "token_raw",
]);

const FORBIDDEN_VALUE =
  /-----BEGIN |\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b|\bAIza[A-Za-z0-9_-]{30,}\b|\bwxid_[A-Za-z0-9_-]+\b|\busr_[A-Za-z0-9_-]{20,}\b|\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\/(?:root|home|Users)\//i;

const STATES = Object.freeze([
  "healthy",
  "degraded",
  "blocked",
  "activation_pending",
  "not_started",
]);
const MAX_SCAN_DEPTH = 8;
const SAFE_TEXT = /^[A-Za-z0-9 _.:+/-]{0,160}$/;

class StatusMatrixError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "StatusMatrixError";
    this.code = code;
    // A path or a field name, never a field value.
    this.detail = detail;
  }
}

function normalizedKey(key) {
  return String(key).toLowerCase().replace(/[^a-z0-9]/g, "_");
}

function assertKeyAllowed(key, path) {
  const normalized = normalizedKey(key);
  if (FORBIDDEN_FIELDS.includes(normalized)) {
    throw new StatusMatrixError("STATUS_FIELD_FORBIDDEN", path);
  }
  for (const fragment of FORBIDDEN_FIELD_FRAGMENTS) {
    if (normalized.includes(fragment)) {
      throw new StatusMatrixError("STATUS_FIELD_FORBIDDEN", path);
    }
  }
}

function assertNoSensitiveValues(value, path = "$", depth = 0) {
  if (depth > MAX_SCAN_DEPTH) {
    throw new StatusMatrixError("STATUS_SNAPSHOT_TOO_DEEP", path);
  }
  if (value === null || value === undefined) {
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new StatusMatrixError("STATUS_VALUE_INVALID", path);
    }
    return;
  }
  if (typeof value === "boolean") {
    return;
  }
  if (typeof value === "string") {
    if (FORBIDDEN_VALUE.test(value)) {
      throw new StatusMatrixError("STATUS_VALUE_FORBIDDEN", path);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoSensitiveValues(item, `${path}[${index}]`, depth + 1));
    return;
  }
  if (typeof value !== "object") {
    throw new StatusMatrixError("STATUS_VALUE_INVALID", path);
  }
  for (const [key, nested] of Object.entries(value)) {
    const childPath = `${path}.${key}`;
    assertKeyAllowed(key, childPath);
    assertNoSensitiveValues(nested, childPath, depth + 1);
  }
}

function requireSafeText(value, field, allowNull = true) {
  if (value === null || value === undefined) {
    if (allowNull) {
      return null;
    }
    throw new StatusMatrixError("STATUS_FIELD_MISSING", field);
  }
  const text = String(value);
  if (!SAFE_TEXT.test(text)) {
    throw new StatusMatrixError("STATUS_FIELD_UNSAFE", field);
  }
  return text;
}

function requireCount(value, field) {
  const count = Number(value);
  if (!Number.isFinite(count) || count < 0) {
    throw new StatusMatrixError("STATUS_FIELD_NOT_A_COUNT", field);
  }
  return count;
}

function requireLineList(value, field) {
  if (value === null || value === undefined) {
    return Object.freeze([]);
  }
  if (!Array.isArray(value)) {
    throw new StatusMatrixError("STATUS_FIELD_NOT_A_LIST", field);
  }
  const items = value.map((item) => String(item));
  for (const item of items) {
    if (!BUSINESS_LINES.includes(item)) {
      throw new StatusMatrixError("STATUS_DEPENDENCY_UNKNOWN", field);
    }
  }
  return Object.freeze([...items].sort());
}

function buildBusinessLine(line) {
  if (!line || typeof line !== "object" || Array.isArray(line)) {
    throw new StatusMatrixError("STATUS_LINE_INVALID", "line");
  }
  // Scan first: a forbidden field is refused before any of it is copied into
  // the output object.
  assertNoSensitiveValues(line, "$");

  const businessLine = String(line.business_line ?? "");
  if (!BUSINESS_LINES.includes(businessLine)) {
    throw new StatusMatrixError("STATUS_BUSINESS_LINE_UNKNOWN", "business_line");
  }
  const missing = REQUIRED_FIELDS.filter((field) => !Object.hasOwn(line, field));
  if (missing.length > 0) {
    throw new StatusMatrixError("STATUS_REQUIRED_FIELD_MISSING", missing.join(","));
  }
  const extra = Object.keys(line).filter((key) => !REQUIRED_FIELDS.includes(key));
  if (extra.length > 0) {
    throw new StatusMatrixError("STATUS_UNEXPECTED_FIELD", extra.join(","));
  }
  const state = String(line.state ?? "");
  if (!STATES.includes(state)) {
    throw new StatusMatrixError("STATUS_STATE_UNKNOWN", "state");
  }
  // 双模式（AC-026）。同一项能力对主人和对访客可以是不同状态：主人的 Codex
  // 好好的，而访客那条 provider 路可能是断的——合成一个状态就把这件事抹平了。
  const mode = String(line.mode ?? "");
  if (!MODES.includes(mode)) {
    throw new StatusMatrixError("STATUS_MODE_UNKNOWN", "mode");
  }
  return Object.freeze({
    business_line: businessLine,
    mode,
    stage: requireSafeText(line.stage, "stage", false),
    state,
    upstream: requireLineList(line.upstream, "upstream"),
    downstream: requireLineList(line.downstream, "downstream"),
    slo: requireSafeText(line.slo, "slo"),
    queue_depth: requireCount(line.queue_depth ?? 0, "queue_depth"),
    oldest_job_seconds: requireCount(line.oldest_job_seconds ?? 0, "oldest_job_seconds"),
    error_rate: requireCount(line.error_rate ?? 0, "error_rate"),
    last_success_at: requireSafeText(line.last_success_at, "last_success_at"),
    last_failure_at: requireSafeText(line.last_failure_at, "last_failure_at"),
    last_recovery_at: requireSafeText(line.last_recovery_at, "last_recovery_at"),
    suggested_action: requireSafeText(line.suggested_action, "suggested_action"),
    release: requireSafeText(line.release, "release"),
    rollback_release: requireSafeText(line.rollback_release, "rollback_release"),
    reason_code: requireSafeText(line.reason_code, "reason_code"),
  });
}

// Every frozen business line must appear exactly once. A snapshot that quietly
// omits the line that is currently broken is worse than no snapshot.
function buildBusinessMatrix(lines) {
  if (!Array.isArray(lines)) {
    throw new StatusMatrixError("STATUS_LINES_INVALID", "lines");
  }
  const built = lines.map(buildBusinessLine);
  // 唯一性按「能力 × 模式」判，不是按能力：同一项能力必须两个模式各一行。
  const seen = built.map((line) => `${line.business_line}:${line.mode}`);
  const duplicates = seen.filter((name, index) => seen.indexOf(name) !== index);
  if (duplicates.length > 0) {
    throw new StatusMatrixError("STATUS_BUSINESS_LINE_DUPLICATED", duplicates.join(","));
  }
  // 15 项能力 × 2 个模式，一格都不能缺。
  //
  // 悄悄少一格的快照比没有快照更糟：看的人以为自己看到了全部，而缺的那一格
  // 恰恰最可能是坏的那一个——没人会把一条不存在的行当成故障。
  const expected = [];
  for (const name of BUSINESS_LINES) {
    for (const mode of MODES) {
      expected.push(`${name}:${mode}`);
    }
  }
  const absent = expected.filter((cell) => !seen.includes(cell));
  if (absent.length > 0) {
    throw new StatusMatrixError("STATUS_BUSINESS_LINE_MISSING", absent.join(","));
  }
  return Object.freeze(
    [...built].sort((left, right) => (
      left.business_line === right.business_line
        ? left.mode.localeCompare(right.mode)
        : left.business_line.localeCompare(right.business_line)
    )),
  );
}

// 把「能力 × 模式」压回一行给窄的地方看（微信里的「状态」、后台概览那一列）。
//
// 压的方向只能是**取更差的那个**。取更好的那个等于用主人这条好路盖住访客那条
// 坏路，而访客那条坏了正是没人会注意到的情况——主人自己一直好好的。
//
// 这个规则写在这里而不是各自的渲染处：写在渲染处的话，两个页面迟早会各压各的，
// 而其中一个会「顺手」取了更好的那个。
const STATE_SEVERITY = Object.freeze({
  healthy: 0,
  activation_pending: 1,
  not_started: 2,
  degraded: 3,
  blocked: 4,
});

function collapseModes(cells = []) {
  const byLine = new Map();
  for (const cell of Array.isArray(cells) ? cells : []) {
    const previous = byLine.get(cell.business_line);
    const worse = !previous
      || (STATE_SEVERITY[cell.state] ?? 4) > (STATE_SEVERITY[previous.state] ?? 4);
    if (worse) {
      byLine.set(cell.business_line, cell);
    }
  }
  return Object.freeze([...byLine.values()]);
}

// v0.0.0.9 的顶层契约（AC-026 / FR-026）。
//
// FR-026 要求这份文档展示：双模式、15 项能力、队列、资源、同步、备份、版本、
// 降级、恢复——十项内容，落成十个 v0.0.0.9 顶层字段（降级挂在 modes 里，恢复
// 挂在每一格的 last_recovery_at 上，因为它们本来就是按模式/按能力分的）。
//
// v0.0.0.8 的 model_usage 和 model_calls 原样带过来。为了让顶层字段数正好是
// 10 而砍掉它们，是拿 AC-048 去换一个数字——那是降低验收标准，不是收敛 schema。
const SNAPSHOT_FIELDS = Object.freeze([
  "schema_version", "product", "version", "generated_at",
  "modes", "capabilities", "queue", "resources", "canonical_sync", "backups",
  "model_usage", "model_calls",
]);

// 这十个是 v0.0.0.9 新契约本身；上面两个 model_* 是从 v0.0.0.8 继承的。
const V009_SNAPSHOT_FIELDS = Object.freeze(
  SNAPSHOT_FIELDS.filter((field) => !field.startsWith("model_")),
);

// 允许传进来的参数名。多一个就拒。
//
// 为什么要有这张表：下面那个函数是**按名字解构**的，所以调用方多传一个
// `owner_note`，它会被静默丢掉——既不会进快照，也不会报错。于是「多一个字段
// 整份拒绝」这条守卫永远不可能触发，因为它查的是组装完的 payload，而 payload
// 的键是写死的。守卫在，但守的是空气。
//
// 这和 safeObservation 那次是同一个形状：**要查的是原始输入，不是解构之后的
// 那个对象。** 这个仓在按名字解构上栽过太多次了。
const SNAPSHOT_INPUTS = Object.freeze([
  "version", "generatedAt", "lines", "modelUsage",
  "modes", "queue", "resources", "canonicalSync", "backups",
]);

// 顶层字段既不许少也不许多。
//
// 少一段的话，看的人会以为那件事不存在——一份没有 backups 段的 status 不会让人
// 去查备份，它让人根本想不起来有备份这回事。多一个字段则是这份文档正在长成别的
// 东西：下一个字段就会是某个「临时加一下」的用户标识。
//
// 这是**单独一个导出的函数**，不是内联在组装里的几行。内联的话它查的是一个键
// 写死的字面量对象，`missing` 恒为空——那几行永远不会触发，删掉它测试照样全绿
// （变异测试里那一刀就是活的）。摘出来之后它能被直接喂一份缺字段的 payload 钉
// 死，于是它承重了：它同时是每次组装都跑的守卫，和一条被证明过会响的警报。
//
// undefined 也算缺：某一段的构造函数如果哪天回了 undefined，键在而内容没了，
// 而那种 status 比缺一段更难发现。
function assertSnapshotFields(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new StatusMatrixError("STATUS_SNAPSHOT_INPUT_INVALID", "payload");
  }
  const present = Object.keys(payload);
  const missing = SNAPSHOT_FIELDS.filter(
    (field) => !present.includes(field) || payload[field] === undefined,
  );
  if (missing.length > 0) {
    throw new StatusMatrixError("STATUS_SNAPSHOT_FIELD_MISSING", missing.join(","));
  }
  const unexpected = present.filter((field) => !SNAPSHOT_FIELDS.includes(field));
  if (unexpected.length > 0) {
    throw new StatusMatrixError("STATUS_SNAPSHOT_FIELD_UNEXPECTED", unexpected.join(","));
  }
  return payload;
}

function buildStatusSnapshot(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new StatusMatrixError("STATUS_SNAPSHOT_INPUT_INVALID", "input");
  }
  const unknownInputs = Object.keys(input).filter((key) => !SNAPSHOT_INPUTS.includes(key));
  if (unknownInputs.length > 0) {
    throw new StatusMatrixError("STATUS_SNAPSHOT_INPUT_UNEXPECTED", unknownInputs.join(","));
  }
  const {
    version,
    generatedAt,
    lines,
    modelUsage = null,
    modes = {},
    queue = {},
    resources = {},
    canonicalSync = {},
    backups = {},
  } = input;
  const timestamp = new Date(generatedAt);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new StatusMatrixError("STATUS_GENERATED_AT_INVALID", "generatedAt");
  }
  const now = timestamp.getTime();
  const payload = {
    // v0.0.0.9：顶层从 5 个字段扩到 10 个，能力枚举从 14 扩到 15，矩阵多了
    // 模式这一维。老的读法（business_lines）会读到 undefined 而不是读到半份，
    // 所以版本号必须跟着走。
    schema_version: 2,
    product: "CyberBoss",
    version: requireSafeText(version, "version", false),
    generated_at: timestamp.toISOString(),
    modes: buildModes(modes, { now }),
    // 原来叫 business_lines。改名是因为它现在装的是「能力 × 模式」的格子，
    // 不再是一行一条业务线。
    capabilities: buildBusinessMatrix(lines),
    queue: buildQueue({ ...queue, now }),
    resources: buildResources({ ...resources, now }),
    canonical_sync: buildCanonicalSync({ ...canonicalSync, now }),
    backups: buildBackups({ ...backups, now }),
    model_usage: modelUsage,
    // AC-033: the snapshot is a projection, and says so on its face.
    model_calls: 0,
  };
  assertSnapshotFields(payload);
  // Final gate on the assembled document, including anything a caller passed
  // through modelUsage.
  assertNoSensitiveValues(payload, "$");
  return Object.freeze({
    ...payload,
    snapshot_sha256: createHash("sha256")
      .update(JSON.stringify(payload))
      .digest("hex"),
  });
}

module.exports = {
  BUSINESS_LINES,
  MODES,
  FORBIDDEN_FIELDS,
  FORBIDDEN_FIELD_FRAGMENTS,
  FORBIDDEN_VALUE,
  MAX_SCAN_DEPTH,
  REQUIRED_FIELDS,
  SECTION_NAMES,
  SNAPSHOT_FIELDS,
  STATES,
  StatusMatrixError,
  V009_SNAPSHOT_FIELDS,
  assertKeyAllowed,
  assertNoSensitiveValues,
  assertSnapshotFields,
  buildBusinessLine,
  buildBusinessMatrix,
  buildStatusSnapshot,
  collapseModes,
};

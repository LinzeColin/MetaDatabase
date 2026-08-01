"use strict";

// CB-810 acceptance: AC-032 (business matrix), AC-033 (zero-agent runtime),
// AC-034 (no Mac dependency), AC-048 (model usage and circuit observability).

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  BUSINESS_LINES,
  MODES,
  FORBIDDEN_FIELDS,
  REQUIRED_FIELDS,
  StatusMatrixError,
  assertNoSensitiveValues,
  buildBusinessLine,
  buildBusinessMatrix,
  buildStatusSnapshot,
} = require("../src/services/status/business-matrix");
const {
  ALLOWED_FIELDS,
  FORBIDDEN_DIMENSIONS,
  aggregateByProvider,
  buildModelUsageSummary,
} = require("../src/services/status/model-usage-summary");
const {
  DEFAULT_THRESHOLDS,
  admits,
  evaluateResourceGate,
} = require("../src/services/operations/resource-gate");
const {
  DEFAULT_POLICY,
  RESTARTABLE,
  decideSelfHeal,
} = require("../src/services/operations/self-heal-policy");
const {
  MUST_EQUAL_ZERO,
  ZeroAgentError,
  assertModelCallAllowed,
  buildZeroAgentLedger,
} = require("../src/services/status/zero-agent-ledger");

const NOW = "2026-07-28T10:00:00.000Z";
const NOW_MS = Date.parse(NOW);

function line(overrides = {}) {
  return {
    business_line: "wechat_channel",
    // v0.0.0.9 起矩阵是「能力 × 模式」（CB9-510 / AC-026）。
    mode: "OWNER",
    stage: "S8",
    state: "healthy",
    upstream: [],
    downstream: [],
    slo: "p95 under 5s",
    queue_depth: 0,
    oldest_job_seconds: 0,
    error_rate: 0,
    last_success_at: NOW,
    last_failure_at: null,
    last_recovery_at: null,
    suggested_action: "none",
    release: "release-v0.0.0.8",
    rollback_release: "release-v0.0.0.7",
    reason_code: "OK",
    ...overrides,
  };
}

// 15 项能力 × 2 个模式 = 30 格。
function fullMatrix(overrides = {}) {
  return BUSINESS_LINES.flatMap((name) => MODES.map(
    (mode) => line({ business_line: name, mode, ...overrides }),
  ));
}

// ---------------------------------------------------------------------------
// AC-032 — the business matrix
// ---------------------------------------------------------------------------

test("AC-032 冻结的能力清单与字段清单就是契约本身", () => {
  // 原来写死成「fourteen lines and fourteen fields」。v0.0.0.9 加了第 15 项能力
  // （location_timezone）、双模式维度和 AC-035 要的两个字段，于是这条必红——
  // 属于扩矩阵的正常连带更新，不是缺陷。
  //
  // 改成从常量推导数量，只逐条钉**内容**：以后再扩不用改数字，而漏掉某一项
  // 仍然会被抓到。写死数字的话，每次扩容都要人工跟着改，漏改是假红、改错是假绿。
  assert.equal(BUSINESS_LINES.length, 15, "能力数变了——先确认不是把某一条删了");
  assert.deepEqual([...MODES], ["OWNER", "COMPANION"]);
  assert.deepEqual(
    [...BUSINESS_LINES].sort(),
    [
      "ai_provider_connection", "backup_restore", "canonical_sync",
      "four_source_import", "location_timezone", "model_usage_budget_circuit",
      "owner_codex_runtime", "profile_memory", "r2_oci_objects", "release_rollback",
      "secure_setup_portal", "timeline_diary_reminder", "user_isolation",
      "user_registration_consent", "wechat_channel",
    ],
  );
  for (const field of [
    "business_line", "mode", "stage", "state", "upstream", "downstream", "slo",
    "queue_depth", "oldest_job_seconds", "error_rate", "last_success_at",
    "last_failure_at", "last_recovery_at", "suggested_action",
    "release", "rollback_release", "reason_code",
  ]) {
    assert.ok(REQUIRED_FIELDS.includes(field), `${field} is required`);
  }
  assert.equal(REQUIRED_FIELDS.length, 17, "字段数变了——先确认不是把某一个删了");
});

test("AC-032 a matrix that omits any business line is refused whole", () => {
  // 去掉最后一格。detail 现在是「能力:模式」——矩阵是 15×2，缺的是一格不是一行。
  const full = fullMatrix();
  const partial = full.slice(0, full.length - 1);
  const missingCell = `${full.at(-1).business_line}:${full.at(-1).mode}`;
  assert.throws(
    () => buildBusinessMatrix(partial),
    (error) =>
      error.code === "STATUS_BUSINESS_LINE_MISSING" &&
      error.detail === missingCell,
  );
  // A snapshot that silently drops the broken line reads as complete, so the
  // whole document is refused rather than one row.
  assert.equal(buildBusinessMatrix(fullMatrix()).length, BUSINESS_LINES.length * MODES.length);
});

test("AC-032 a missing or extra field is refused", () => {
  for (const field of REQUIRED_FIELDS) {
    const incomplete = line();
    delete incomplete[field];
    assert.throws(
      () => buildBusinessLine(incomplete),
      (error) =>
        error.code === "STATUS_REQUIRED_FIELD_MISSING" ||
        error.code === "STATUS_BUSINESS_LINE_UNKNOWN",
      `missing ${field} must be refused`,
    );
  }
  assert.throws(
    () => buildBusinessLine({ ...line(), extra_note: "ok" }),
    (error) => error.code === "STATUS_UNEXPECTED_FIELD" && error.detail === "extra_note",
  );
});

test("AC-032 every frozen forbidden field name is refused", () => {
  for (const field of FORBIDDEN_FIELDS) {
    assert.throws(
      () => buildBusinessLine({ ...line(), [field]: "x" }),
      (error) => error.code === "STATUS_FIELD_FORBIDDEN",
      `${field} must be refused`,
    );
  }
});

test("AC-032 a forbidden field nested inside a value is still refused", () => {
  assert.throws(
    () => buildBusinessLine({ ...line(), slo: { detail: { user_id: "x" } } }),
    (error) => error.code === "STATUS_FIELD_FORBIDDEN",
  );
  assert.throws(
    () => assertNoSensitiveValues({ a: { b: { c: { wechat_id: "x" } } } }),
    (error) => error.code === "STATUS_FIELD_FORBIDDEN" && error.detail === "$.a.b.c.wechat_id",
  );
});

test("AC-032 a sensitive value is refused even under an allowed field name", () => {
  const values = [
    "wxid_abcd1234",
    `usr_${"a".repeat(22)}`,
    "person@example.com",
    "Bearer abcdefghijklmnop",
    "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "-----BEGIN PRIVATE KEY-----",
    "/Users/someone/runtime.db",
  ];
  for (const value of values) {
    assert.throws(
      () => buildBusinessLine({ ...line(), reason_code: value }),
      (error) =>
        error.code === "STATUS_VALUE_FORBIDDEN" || error.code === "STATUS_FIELD_UNSAFE",
      `${value.slice(0, 14)} must be refused`,
    );
  }
});

test("AC-032 the error names the field path and never the value", () => {
  try {
    buildBusinessLine({ ...line(), slo: "wxid_secretvalue" });
    assert.fail("expected a refusal");
  } catch (error) {
    assert.ok(error instanceof StatusMatrixError);
    assert.ok(!error.message.includes("secretvalue"));
    assert.ok(!String(error.detail ?? "").includes("secretvalue"));
  }
});

test("AC-032 an unknown business line or state is refused", () => {
  assert.throws(
    () => buildBusinessLine(line({ business_line: "shadow_line" })),
    (error) => error.code === "STATUS_BUSINESS_LINE_UNKNOWN",
  );
  assert.throws(
    () => buildBusinessLine(line({ state: "probably_fine" })),
    (error) => error.code === "STATUS_STATE_UNKNOWN",
  );
  assert.throws(
    () => buildBusinessLine(line({ upstream: ["not_a_line"] })),
    (error) => error.code === "STATUS_DEPENDENCY_UNKNOWN",
  );
});

test("AC-032 a snapshot is deterministic and carries its own digest", () => {
  const build = () =>
    buildStatusSnapshot({ version: "v0.0.0.8", generatedAt: NOW, lines: fullMatrix() });
  const first = build();
  const second = build();
  assert.equal(first.snapshot_sha256, second.snapshot_sha256);
  assert.match(first.snapshot_sha256, /^[0-9a-f]{64}$/);
  // v0.0.0.9 起顶层叫 capabilities（装的是「能力 × 模式」的格子，不再是一行
  // 一条业务线）。schema_version 跟着从 1 变成 2。
  assert.equal(first.schema_version, 2);
  assert.equal(first.capabilities.length, BUSINESS_LINES.length * MODES.length);
  assert.equal(first.model_calls, 0);
  // Ordering is by name, so the digest does not depend on input order.
  const shuffled = buildStatusSnapshot({
    version: "v0.0.0.8",
    generatedAt: NOW,
    lines: [...fullMatrix()].reverse(),
  });
  assert.equal(shuffled.snapshot_sha256, first.snapshot_sha256);
});

test("AC-032 the whole snapshot is re-scanned after assembly", () => {
  assert.throws(
    () =>
      buildStatusSnapshot({
        version: "v0.0.0.8",
        generatedAt: NOW,
        lines: fullMatrix(),
        modelUsage: { providers: [{ provider: "openai", user_id: "usr_x" }] },
      }),
    (error) => error.code === "STATUS_FIELD_FORBIDDEN",
  );
});

// ---------------------------------------------------------------------------
// AC-048 — model usage and circuit observability
// ---------------------------------------------------------------------------

test("AC-048 the summary carries exactly the frozen aggregate fields", () => {
  const summary = buildModelUsageSummary({
    usageRows: [
      { providerId: "openai", reservedTokens: 100, chargedTokens: 90 },
      { providerId: "openai", reservedTokens: 50, chargedTokens: 55 },
      { providerId: "anthropic", reservedTokens: 10, chargedTokens: 10 },
    ],
    circuitRows: [
      { providerId: "openai", state: "half_open", reasonCode: "PROVIDER_5XX", lastTransitionAt: NOW },
    ],
    budgetStates: { openai: "soft_warning" },
    generatedAt: NOW,
  });
  assert.equal(summary.providers.length, 2);
  const openai = summary.providers.find((row) => row.provider === "openai");
  assert.deepEqual([...Object.keys(openai)].sort(), [...ALLOWED_FIELDS].sort());
  assert.equal(openai.reserved_tokens, 150);
  assert.equal(openai.charged_tokens, 145);
  assert.equal(openai.budget_state, "soft_warning");
  assert.equal(openai.soft_warning, true);
  assert.equal(openai.hard_block, false);
  assert.equal(openai.circuit_state, "half_open");
  assert.equal(openai.reason_code, "PROVIDER_5XX");
  assert.equal(summary.model_calls, 0);
});

test("AC-048 the per-user dimension is gone before a summary exists", () => {
  const totals = aggregateByProvider([
    { providerId: "openai", userId: `usr_${"a".repeat(22)}`, reservedTokens: 10, chargedTokens: 10 },
    { providerId: "openai", userId: `usr_${"b".repeat(22)}`, reservedTokens: 20, chargedTokens: 20 },
  ]);
  assert.equal(totals.size, 1);
  assert.deepEqual(totals.get("openai"), { reserved: 30, charged: 30 });

  const summary = buildModelUsageSummary({
    usageRows: [
      { providerId: "openai", userId: `usr_${"a".repeat(22)}`, reservedTokens: 10, chargedTokens: 10 },
    ],
    generatedAt: NOW,
  });
  const serialized = JSON.stringify(summary);
  for (const dimension of FORBIDDEN_DIMENSIONS) {
    assert.ok(!serialized.includes(dimension), `${dimension} is absent from the summary`);
  }
  assert.ok(!serialized.includes("usr_"), "no user id survives the aggregation");
});

test("AC-048 an unknown provider, circuit state or reason code is refused", () => {
  assert.throws(
    () => buildModelUsageSummary({ usageRows: [{ providerId: "mystery" }], generatedAt: NOW }),
    (error) => error.code === "USAGE_PROVIDER_UNKNOWN",
  );
  assert.throws(
    () =>
      buildModelUsageSummary({
        usageRows: [{ providerId: "openai" }],
        circuitRows: [{ providerId: "openai", state: "wobbling" }],
        generatedAt: NOW,
      }),
    (error) => error.code === "USAGE_CIRCUIT_STATE_UNKNOWN",
  );
  assert.throws(
    () =>
      buildModelUsageSummary({
        usageRows: [{ providerId: "openai" }],
        circuitRows: [{ providerId: "openai", state: "open", reasonCode: "user usr_abc failed" }],
        generatedAt: NOW,
      }),
    (error) => error.code === "USAGE_REASON_CODE_INVALID",
  );
});

test("AC-048 a provider with no circuit row reports closed rather than unknown", () => {
  const summary = buildModelUsageSummary({
    usageRows: [{ providerId: "deepseek", reservedTokens: 1, chargedTokens: 1 }],
    generatedAt: NOW,
  });
  assert.equal(summary.providers[0].circuit_state, "closed");
  assert.equal(summary.providers[0].reason_code, null);
  assert.equal(summary.providers[0].budget_state, "ok");
});

// ---------------------------------------------------------------------------
// AC-033 — zero-agent runtime, resource gate, self-heal
// ---------------------------------------------------------------------------

test("AC-033 an unmeasured resource floor rejects rather than admits", () => {
  const healthy = {
    freeMemoryBytes: 4 * 1024 ** 3,
    freeDiskBytes: 40 * 1024 ** 3,
    freeInodes: 500_000,
    queueDepth: 1,
    loadRatio: 0.3,
  };
  assert.equal(evaluateResourceGate(healthy).state, "allow");
  assert.equal(admits(evaluateResourceGate(healthy)), true);

  for (const metric of Object.keys(healthy)) {
    const partial = { ...healthy };
    delete partial[metric];
    const decision = evaluateResourceGate(partial);
    assert.equal(decision.state, "reject", `${metric} unmeasured must reject`);
    assert.equal(decision.reasonCode, "RESOURCE_MEASUREMENT_UNAVAILABLE");
    assert.deepEqual(decision.missing, [metric]);
    assert.equal(admits(decision), false);
  }
  assert.equal(evaluateResourceGate(null).state, "reject");
  assert.equal(evaluateResourceGate({ ...healthy, freeDiskBytes: -1 }).state, "reject");
  assert.equal(evaluateResourceGate({ ...healthy, freeDiskBytes: NaN }).state, "reject");
});

test("AC-033 hard floors reject and pressure only degrades", () => {
  const base = {
    freeMemoryBytes: 4 * 1024 ** 3,
    freeDiskBytes: 40 * 1024 ** 3,
    freeInodes: 500_000,
    queueDepth: 1,
    loadRatio: 0.3,
  };
  assert.equal(
    evaluateResourceGate({ ...base, freeMemoryBytes: DEFAULT_THRESHOLDS.minFreeMemoryBytes - 1 }).reasonCode,
    "MIN_FREE_MEMORY",
  );
  assert.equal(
    evaluateResourceGate({ ...base, freeDiskBytes: DEFAULT_THRESHOLDS.minFreeDiskBytes - 1 }).reasonCode,
    "MIN_FREE_DISK",
  );
  assert.equal(
    evaluateResourceGate({ ...base, freeInodes: DEFAULT_THRESHOLDS.minFreeInodes - 1 }).reasonCode,
    "MIN_FREE_INODES",
  );
  const queue = evaluateResourceGate({ ...base, queueDepth: DEFAULT_THRESHOLDS.maxQueueDepth + 1 });
  assert.equal(queue.state, "degraded");
  assert.equal(queue.reasonCode, "QUEUE_PRESSURE");
  assert.equal(admits(queue), false);
  const load = evaluateResourceGate({ ...base, loadRatio: DEFAULT_THRESHOLDS.maxLoadRatio + 0.1 });
  assert.equal(load.state, "degraded");
  assert.equal(load.reasonCode, "LOAD_PRESSURE");

  // A host that is both out of disk and busy reports the floor first.
  const both = evaluateResourceGate({
    ...base,
    freeDiskBytes: 1,
    queueDepth: DEFAULT_THRESHOLDS.maxQueueDepth + 100,
  });
  assert.equal(both.reasonCode, "MIN_FREE_DISK");
});

test("AC-033 the resource gate is exactly on the boundary, not near it", () => {
  const base = {
    freeMemoryBytes: DEFAULT_THRESHOLDS.minFreeMemoryBytes,
    freeDiskBytes: DEFAULT_THRESHOLDS.minFreeDiskBytes,
    freeInodes: DEFAULT_THRESHOLDS.minFreeInodes,
    queueDepth: DEFAULT_THRESHOLDS.maxQueueDepth,
    loadRatio: DEFAULT_THRESHOLDS.maxLoadRatio,
  };
  assert.equal(evaluateResourceGate(base).state, "allow", "exactly at the floor is allowed");
  assert.equal(
    evaluateResourceGate({ ...base, freeInodes: DEFAULT_THRESHOLDS.minFreeInodes - 1 }).state,
    "reject",
  );
  assert.equal(
    evaluateResourceGate({ ...base, queueDepth: DEFAULT_THRESHOLDS.maxQueueDepth + 1 }).state,
    "degraded",
  );
});

test("AC-033 self-heal restarts within budget and then stops", () => {
  assert.deepEqual(
    decideSelfHeal({ healthy: true, reasonCode: null, nowMs: NOW_MS }),
    { action: "none", reasonCode: "HEALTHY", modelCalls: 0 },
  );
  const first = decideSelfHeal({
    healthy: false,
    reasonCode: "PROCESS_EXITED",
    nowMs: NOW_MS,
    restartTimestamps: [],
  });
  assert.equal(first.action, "restart_process_family");
  assert.equal(first.attempt, 1);

  const spaced = (count) =>
    Array.from({ length: count }, (_, index) => NOW_MS - (index + 1) * 120_000);
  for (let used = 1; used < DEFAULT_POLICY.maxRestarts; used += 1) {
    const decision = decideSelfHeal({
      healthy: false,
      reasonCode: "READYZ_FAILED",
      nowMs: NOW_MS,
      restartTimestamps: spaced(used),
    });
    assert.equal(decision.action, "restart_process_family", `attempt ${used + 1} still allowed`);
    assert.equal(decision.attempt, used + 1);
  }
  const exhausted = decideSelfHeal({
    healthy: false,
    reasonCode: "READYZ_FAILED",
    nowMs: NOW_MS,
    restartTimestamps: spaced(DEFAULT_POLICY.maxRestarts),
  });
  assert.equal(exhausted.action, "stop_restart_loop_and_alert");
  assert.equal(exhausted.reasonCode, "RESTART_BUDGET_EXHAUSTED");
});

test("AC-033 a restart storm inside the cooldown is deferred, not amplified", () => {
  const decision = decideSelfHeal({
    healthy: false,
    reasonCode: "PROCESS_EXITED",
    nowMs: NOW_MS,
    restartTimestamps: [NOW_MS - 1_000],
  });
  assert.equal(decision.action, "none");
  assert.equal(decision.reasonCode, "RESTART_COOLDOWN");
  assert.ok(decision.retryAfterMs > 0);
});

test("AC-033 restarts age out of the window and a skewed clock buys nothing", () => {
  const old = Array.from(
    { length: DEFAULT_POLICY.maxRestarts },
    () => NOW_MS - DEFAULT_POLICY.windowMs - 60_000,
  );
  const afterWindow = decideSelfHeal({
    healthy: false,
    reasonCode: "PROCESS_EXITED",
    nowMs: NOW_MS,
    restartTimestamps: old,
  });
  assert.equal(afterWindow.action, "restart_process_family", "old restarts no longer count");

  // Timestamps in the future are counted, so a clock jump cannot reset the
  // budget.
  const future = Array.from(
    { length: DEFAULT_POLICY.maxRestarts },
    () => NOW_MS + 60_000,
  );
  const skewed = decideSelfHeal({
    healthy: false,
    reasonCode: "PROCESS_EXITED",
    nowMs: NOW_MS,
    restartTimestamps: future,
  });
  assert.equal(skewed.action, "stop_restart_loop_and_alert");
});

test("AC-033 an unrestartable failure is isolated rather than restarted", () => {
  for (const code of ["DATABASE_CORRUPT", "CREDENTIAL_REJECTED", "DISK_FULL", "UNKNOWN"]) {
    const decision = decideSelfHeal({ healthy: false, reasonCode: code, nowMs: NOW_MS });
    assert.equal(decision.action, "isolate_and_alert", `${code} must not be restarted`);
    assert.equal(decision.reasonCode, code);
  }
  const missing = decideSelfHeal({ healthy: false, reasonCode: null, nowMs: NOW_MS });
  assert.equal(missing.action, "isolate_and_alert");
  assert.equal(missing.reasonCode, "UNKNOWN_FAILURE");
  assert.equal(RESTARTABLE.length, 4);
});

test("AC-033 every decision path reports zero model calls", () => {
  const decisions = [
    decideSelfHeal({ healthy: true, nowMs: NOW_MS }),
    decideSelfHeal({ healthy: false, reasonCode: "PROCESS_EXITED", nowMs: NOW_MS }),
    decideSelfHeal({ healthy: false, reasonCode: "DATABASE_CORRUPT", nowMs: NOW_MS }),
    decideSelfHeal({
      healthy: false,
      reasonCode: "PROCESS_EXITED",
      nowMs: NOW_MS,
      restartTimestamps: [NOW_MS - 1_000],
    }),
    decideSelfHeal({
      healthy: false,
      reasonCode: "PROCESS_EXITED",
      nowMs: NOW_MS,
      restartTimestamps: [NOW_MS - 200_000, NOW_MS - 300_000, NOW_MS - 400_000],
    }),
    evaluateResourceGate(null),
    evaluateResourceGate({
      freeMemoryBytes: 4 * 1024 ** 3,
      freeDiskBytes: 40 * 1024 ** 3,
      freeInodes: 500_000,
      queueDepth: 1,
      loadRatio: 0.3,
    }),
  ];
  for (const decision of decisions) {
    assert.equal(decision.modelCalls, 0);
  }
});

test("AC-033 the operational modules import nothing at all", () => {
  for (const relative of [
    "../src/services/operations/resource-gate.js",
    "../src/services/operations/self-heal-policy.js",
    "../src/services/status/zero-agent-ledger.js",
  ]) {
    const source = fs.readFileSync(path.join(__dirname, relative), "utf8");
    assert.ok(!source.includes("require("), `${relative} imports nothing`);
  }
});

test("AC-033 an unreported counter is not treated as zero", () => {
  const zeros = Object.fromEntries(MUST_EQUAL_ZERO.map((name) => [name, 0]));
  const ledger = buildZeroAgentLedger(zeros);
  assert.equal(ledger.zero_agent, true);
  assert.equal(Object.keys(ledger.counters).length, 11);

  for (const name of MUST_EQUAL_ZERO) {
    const missing = { ...zeros };
    delete missing[name];
    assert.throws(
      () => buildZeroAgentLedger(missing),
      (error) => error.code === "ZERO_AGENT_COUNTER_MISSING" && error.detail === name,
      `${name} unreported must fail`,
    );
    assert.throws(
      () => buildZeroAgentLedger({ ...zeros, [name]: 1 }),
      (error) => error instanceof ZeroAgentError && error.code === "ZERO_AGENT_VIOLATION",
      `${name} non-zero must fail`,
    );
  }
});

test("AC-033 only the three declared purposes may reach a model", () => {
  for (const purpose of [
    "user_initiated_ai_turn",
    "user_explicit_profile_suggestion",
    "owner_initiated_codex_turn",
  ]) {
    assert.equal(assertModelCallAllowed(purpose), purpose);
  }
  for (const purpose of [
    "provider_health_probe",
    "budget_summary",
    "analytics_summary",
    "self_heal_decision",
    "status_narration",
    undefined,
  ]) {
    assert.throws(
      () => assertModelCallAllowed(purpose),
      (error) => error.code === "MODEL_CALL_PURPOSE_NOT_ALLOWED",
      `${purpose} must be refused`,
    );
  }
});

// ---------------------------------------------------------------------------
// AC-034 — no Mac dependency
// ---------------------------------------------------------------------------

test("AC-034 no runtime source depends on a Mac path, plist or launchd", () => {
  const root = path.join(__dirname, "..");
  const roots = ["src", "migrations", "bin"].map((name) => path.join(root, name));
  // Case-sensitive: "/Users/" is a macOS home path; "../users/" is a module.
  const markers = [
    "/Users/", "/Library/", ".plist", "LaunchAgent", "LaunchDaemon", "launchd", "osascript",
  ];
  // A marker on a line that refuses or declares-absent the dependency is the
  // opposite of a dependency. `macos_launchd_dependency: false` and
  // `value.includes("/Users/")` inside a rejection are proofs of AC-034, not
  // breaches of it, so a line is only an offender when it does neither.
  const PROHIBITION = /macos_launchd_dependency|!==\s*false|\.includes\(|\.test\(|FORBIDDEN|forbidden|reject|refus|assert|must_not|no_mac/;
  const offenders = [];
  const prohibitions = [];

  const walk = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!/\.(?:js|sql|json)$/.test(entry.name)) {
        continue;
      }
      const relative = path.relative(root, full);
      fs.readFileSync(full, "utf8").split("\n").forEach((text, index) => {
        for (const marker of markers) {
          if (!text.includes(marker)) {
            continue;
          }
          const record = `${relative}:${index + 1}:${marker}`;
          (PROHIBITION.test(text) ? prohibitions : offenders).push(record);
        }
      });
    }
  };
  for (const directory of roots) {
    if (fs.existsSync(directory)) {
      walk(directory);
    }
  }
  assert.deepEqual(offenders, [], "no Mac dependency in runtime sources");
  // The codebase must actively forbid it, not merely happen not to mention it.
  assert.ok(prohibitions.length > 0, "the no-Mac rule is asserted in the runtime");
});

test("AC-034 the declared engine is Node, not a macOS runtime", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(__dirname, "../package.json"), "utf8"),
  );
  assert.ok(manifest.engines.node.startsWith(">="), "a Node engine floor is declared");
  const serialized = JSON.stringify(manifest);
  for (const marker of ["darwin", "launchd", ".plist", "/Users/"]) {
    assert.ok(!serialized.includes(marker), `${marker} is absent from the manifest`);
  }
});

"use strict";

// CB9-510 Status 纵向矩阵与禁止配置性伪绿（AC-026 / AC-035 / FR-026 / NFR-005）
//
// AC-026 的 oracle：「矩阵包含双模式与 15 项能力，字段缺失/多余/隐私值均整份
// 拒绝；不得成为写入入口。」
// AC-035 的 oracle：「关键业务线有结构化状态、建议动作、上次成功/失败和恢复；
// 自愈不依赖 Agent/Token。」
//
// 这一节最容易出的错不是漏字段，是**伪绿**：一份从配置推出来的 status 会说
// 一切健康，而那些能力可能从第一天起就没跑过。所以下面的断言分两类——
// 一类查形状（够不够全、拒不拒绝），一类查「够不着」（配置能不能变成绿）。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  BUSINESS_LINES,
  MODES,
  REQUIRED_FIELDS,
  SNAPSHOT_FIELDS,
  V009_SNAPSHOT_FIELDS,
  assertSnapshotFields,
  buildBusinessMatrix,
  buildStatusSnapshot,
  collapseModes,
} = require("../src/services/status/business-matrix");

const {
  SUGGESTED_ACTIONS,
  buildBackups,
  buildCanonicalSync,
  buildMode,
  buildModes,
  buildQueue,
  buildResources,
} = require("../src/services/status/vertical-sections");

const { projectLiveStatus } = require("../src/services/status/live-status-projector");

const NOW = Date.parse("2026-08-02T12:00:00.000Z");
const ago = (ms) => new Date(NOW - ms).toISOString();

function cell(overrides = {}) {
  return {
    business_line: "wechat_channel",
    mode: "OWNER",
    stage: "S6",
    state: "healthy",
    upstream: [],
    downstream: [],
    slo: "inbound accepted within 5s",
    queue_depth: 0,
    oldest_job_seconds: 0,
    error_rate: 0,
    last_success_at: null,
    last_failure_at: null,
    last_recovery_at: null,
    suggested_action: "none",
    release: "release-v0.0.0.9",
    rollback_release: "release-v0.0.0.8",
    reason_code: "OK",
    ...overrides,
  };
}

const fullGrid = (overrides = {}) => BUSINESS_LINES.flatMap(
  (name) => MODES.map((mode) => cell({ business_line: name, mode, ...overrides })),
);

const snapshot = (extra = {}) => buildStatusSnapshot({
  version: "v0.0.0.9", generatedAt: NOW, lines: fullGrid(), ...extra,
});

// ── AC-026 双模式 × 15 项能力 ─────────────────────────────

test("AC-026 矩阵是 15 项能力 × 2 个模式 = 30 格", () => {
  assert.equal(BUSINESS_LINES.length, 15);
  assert.deepEqual([...MODES], ["OWNER", "COMPANION"]);
  assert.equal(snapshot().capabilities.length, 30);
});

test("AC-026 同一项能力两个模式可以是不同状态", () => {
  // 这是双模式存在的全部理由。主人的 Codex 好好的，访客那条 provider 路可能
  // 从第一天起就是断的——合成一个状态就把坏的那一半抹掉了，而抹平的方向永远
  // 是往好里抹（主人自己一直是好的，所以没人会注意到）。
  const grid = fullGrid().map((line) => (
    line.business_line === "ai_provider_connection" && line.mode === "COMPANION"
      ? { ...line, state: "blocked", reason_code: "NO_USER_CREDENTIAL" }
      : line
  ));
  const built = buildBusinessMatrix(grid);
  const provider = built.filter((line) => line.business_line === "ai_provider_connection");
  assert.equal(provider.length, 2);
  assert.deepEqual(
    provider.map((line) => [line.mode, line.state]).sort(),
    [["COMPANION", "blocked"], ["OWNER", "healthy"]],
  );
});

test("AC-026 少一格整份拒绝，不是少一行", () => {
  // 一份悄悄少了一格的快照读起来是完整的，而缺的那一格恰恰最可能是坏的
  // 那一个——没人会把一条不存在的行当成故障。
  for (const missing of [
    { business_line: "location_timezone", mode: "COMPANION" },
    { business_line: "wechat_channel", mode: "OWNER" },
  ]) {
    const partial = fullGrid().filter(
      (line) => !(line.business_line === missing.business_line && line.mode === missing.mode),
    );
    assert.throws(
      () => buildBusinessMatrix(partial),
      (error) => error.code === "STATUS_BUSINESS_LINE_MISSING"
        && error.detail === `${missing.business_line}:${missing.mode}`,
      `${missing.business_line}:${missing.mode} 缺了却没被拒`,
    );
  }
});

test("AC-026 同一格出现两次也拒绝", () => {
  // 同一格两行会让「完整性检查通过」和「实际覆盖了 30 件事」脱钩：
  // 30 行里两行重复，就一定有一格没人报。
  const doubled = [...fullGrid(), cell({ business_line: "wechat_channel", mode: "OWNER" })];
  assert.throws(
    () => buildBusinessMatrix(doubled),
    (error) => error.code === "STATUS_BUSINESS_LINE_DUPLICATED",
  );
});

test("AC-026 认不出来的模式整份拒绝", () => {
  assert.throws(
    () => buildBusinessMatrix(fullGrid().map((line) => ({ ...line, mode: "ADMIN" }))),
    (error) => error.code === "STATUS_MODE_UNKNOWN",
  );
});

// ── AC-026 顶层十字段 ─────────────────────────────────────

test("AC-026 v0.0.0.9 的十个顶层字段一个不少", () => {
  // FR-026：双模式、15 项能力、队列、资源、同步、备份、版本、降级、恢复。
  // 降级挂在 modes 里（按模式分），恢复挂在每一格的 last_recovery_at 上
  // （按能力分）——它们本来就不是全局的一个值。
  assert.deepEqual([...V009_SNAPSHOT_FIELDS], [
    "schema_version", "product", "version", "generated_at",
    "modes", "capabilities", "queue", "resources", "canonical_sync", "backups",
  ]);
  const built = snapshot();
  for (const field of SNAPSHOT_FIELDS) {
    assert.ok(Object.hasOwn(built, field), `顶层少了 ${field}`);
  }
  // 降级和恢复确实到得了。
  assert.ok(Object.hasOwn(built.modes.OWNER, "degradation_level"));
  assert.ok(built.capabilities.every((line) => Object.hasOwn(line, "last_recovery_at")));
});

test("AC-026 schema_version 跟着契约走", () => {
  // 老的读法是 status.business_lines。改名之后它读到 undefined 而不是读到
  // 半份——但只有版本号跟着变，读的人才知道该换读法。
  const built = snapshot();
  assert.equal(built.schema_version, 2);
  assert.equal(built.business_lines, undefined);
  assert.ok(Array.isArray(built.capabilities));
});

test("AC-026 多传一个参数整份拒绝——而不是静默丢掉", () => {
  // 多出来的字段是这份文档正在长成别的东西的第一个信号；下一个多出来的
  // 就会是某个「临时加一下」的用户标识。
  //
  // 第一版这条是**红不了**的：buildStatusSnapshot 按名字解构，多传的键在进入
  // 函数体的那一刻就没了，于是「顶层多字段」的守卫查的是一个键写死的对象，
  // 永远查不到东西。守卫在，但守的是空气——和 safeObservation 那次一样。
  assert.throws(
    () => buildStatusSnapshot({
      version: "v0.0.0.9", generatedAt: NOW, lines: fullGrid(), owner_note: "hi",
    }),
    (error) => error.code === "STATUS_SNAPSHOT_INPUT_UNEXPECTED" && error.detail === "owner_note",
  );
  // 拼错一个合法参数名同样要红。静默丢掉的话，整段 backups 会显示成
  // 「从没跑过」，而它其实一直在跑。
  assert.throws(
    () => buildStatusSnapshot({
      version: "v0.0.0.9", generatedAt: NOW, lines: fullGrid(), backup: { configured: true },
    }),
    (error) => error.code === "STATUS_SNAPSHOT_INPUT_UNEXPECTED",
  );
});

test("AC-026 顶层少一段整份拒绝——而且这条警报被证明过会响", () => {
  // 这条守卫内联在组装里的时候是**死的**：payload 是个键写死的字面量，
  // missing 恒为空，把整个 throw 删掉测试照样全绿（变异测试那一刀活着）。
  // 摘成一个能单独喂 payload 的函数，它才真的承重。
  const complete = Object.fromEntries(SNAPSHOT_FIELDS.map((field) => [field, 1]));
  assert.equal(assertSnapshotFields(complete), complete);

  for (const dropped of ["backups", "modes", "capabilities", "resources"]) {
    const { [dropped]: _gone, ...partial } = complete;
    assert.throws(
      () => assertSnapshotFields(partial),
      (error) => error.code === "STATUS_SNAPSHOT_FIELD_MISSING" && error.detail === dropped,
      `少了 ${dropped} 却放行了`,
    );
  }
  // 键在但内容是 undefined 也算缺。某一段的构造函数哪天回了 undefined，
  // 那种 status 比缺一段更难发现——它看起来是完整的。
  assert.throws(
    () => assertSnapshotFields({ ...complete, queue: undefined }),
    (error) => error.code === "STATUS_SNAPSHOT_FIELD_MISSING" && error.detail === "queue",
  );
  assert.throws(
    () => assertSnapshotFields({ ...complete, owner_note: "hi" }),
    (error) => error.code === "STATUS_SNAPSHOT_FIELD_UNEXPECTED",
  );
});

test("AC-026 「没配置」和「配了但没跑过」是两个不同的原因", () => {
  // 两者的 state 都是 UNKNOWN，所以只断言 state 的话，把 configured 直接
  // 写死成 true 测试照样全绿——那个入参就不承重了（变异测试抓到的）。
  //
  // 而它们该做的事完全不同：前者去把它配上，后者去用它一次。面板只说
  // 「不知道」而不说是哪一种，值班的人还得自己去翻配置。
  const never = buildQueue({ configured: false, now: NOW });
  assert.equal(never.state, "UNKNOWN");
  assert.equal(never.reason, "not_configured");
  assert.equal(never.suggested_action, "exercise_once_to_learn_state");

  const configured = buildQueue({ configured: true, now: NOW });
  assert.equal(configured.state, "UNKNOWN");
  assert.equal(configured.reason, "no_live_receipt");

  // 五段都得分得清，不是只有 queue。
  for (const build of [buildCanonicalSync, buildBackups]) {
    assert.equal(build({ configured: false, now: NOW }).reason, "not_configured");
    assert.equal(build({ configured: true, now: NOW }).reason, "no_live_receipt");
  }
  for (const mode of MODES) {
    assert.equal(buildModes({}, { now: NOW })[mode].reason, "not_configured");
    assert.equal(
      buildModes({ [mode]: { configured: true } }, { now: NOW })[mode].reason,
      "no_live_receipt",
    );
  }
});

test("AC-026 隐私字段和隐私值仍然整份拒绝", () => {
  // 新加的五段都在同一个扫描器下面——扫描器是在整份组装完之后再跑一遍的，
  // 所以从任何一段塞进去都挡得住。
  for (const [section, payload] of [
    ["backups", { objectCount: 1, lastBackupAt: ago(1000), configured: true }],
  ]) {
    const ok = buildStatusSnapshot({
      version: "v0.0.0.9", generatedAt: NOW, lines: fullGrid(), [section]: payload,
    });
    assert.ok(ok.backups.state);
  }
  assert.throws(
    () => buildStatusSnapshot({
      version: "v0.0.0.9",
      generatedAt: NOW,
      lines: fullGrid(),
      modelUsage: { providers: [{ provider: "openai", wechat_id: "x" }] },
    }),
    (error) => error.code === "STATUS_FIELD_FORBIDDEN",
  );
});

// ── AC-026 不得成为写入入口 ───────────────────────────────

test("AC-026 status 这几个模块够不着写", () => {
  // 「不得成为写入入口」不能靠「我们没这么写」——那是行为保证，下一个人加一行
  // 就没了。这里查的是**结构**：这几个模块里根本没有写的手段。
  const dir = path.join(__dirname, "..", "src", "services", "status");
  for (const file of ["business-matrix.js", "vertical-sections.js", "parity-freshness.js"]) {
    const src = fs.readFileSync(path.join(dir, file), "utf8");
    const code = src.split("\n").map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");
    for (const hint of [
      "writeFileSync", "appendFileSync", "renameSync", "mkdirSync", "rmSync",
      "INSERT ", "UPDATE ", "DELETE ", ".run(", "process.env",
    ]) {
      assert.ok(!code.includes(hint), `${file} 里出现了 ${hint}——status 变成写入入口了`);
    }
  }
});

test("AC-026 产出的快照是冻结的，改不动", () => {
  const built = snapshot();
  assert.ok(Object.isFrozen(built));
  assert.ok(Object.isFrozen(built.modes.OWNER));
  assert.ok(Object.isFrozen(built.queue));
  assert.throws(() => {
    "use strict";
    built.queue.depth = 999;
  }, TypeError);
});

// ── AC-035 结构化状态 + 建议动作 + 上次成功/失败 + 恢复 ───

test("AC-035 每一格都有状态、建议动作、上次成功/失败和恢复", () => {
  for (const field of [
    "state", "suggested_action", "last_success_at", "last_failure_at", "last_recovery_at",
  ]) {
    assert.ok(REQUIRED_FIELDS.includes(field), `矩阵字段少了 ${field}`);
  }
  const live = projectLiveStatus({ facts: {}, generatedAt: new Date(NOW) });
  for (const line of live.status.capabilities) {
    assert.ok(typeof line.suggested_action === "string" && line.suggested_action.length > 0,
      `${line.business_line}:${line.mode} 没有建议动作`);
    assert.ok(Object.hasOwn(line, "last_failure_at"));
    assert.ok(Object.hasOwn(line, "last_recovery_at"));
  }
});

test("AC-035 建议动作是可执行的动作，不是状态的同义反复", () => {
  // 「blocked → blocked」这种建议等于把排查全推给值班的人。
  const live = projectLiveStatus({
    facts: { channelReady: false, portalMounted: false }, generatedAt: new Date(NOW),
  });
  const channel = live.status.capabilities.find(
    (line) => line.business_line === "wechat_channel" && line.mode === "OWNER",
  );
  assert.equal(channel.reason_code, "CHANNEL_NOT_LOGGED_IN");
  assert.equal(channel.suggested_action, "reconnect_wechat_account");
  assert.notEqual(channel.suggested_action, channel.state);
  assert.notEqual(channel.suggested_action, channel.reason_code.toLowerCase());
});

test("AC-035 每一段纵向内容也带建议动作", () => {
  const built = snapshot();
  for (const section of ["queue", "resources", "canonical_sync", "backups"]) {
    assert.ok(built[section].suggested_action, `${section} 没有建议动作`);
  }
  for (const mode of MODES) {
    assert.ok(built.modes[mode].suggested_action, `${mode} 没有建议动作`);
  }
});

test("NFR-005 自愈这条路上没有模型调用", () => {
  // 「建议动作」如果是生成的，自愈就等于调了模型，只是换了个地方。
  // 所以它必须是一张固定表查出来的——固定表能被这样逐条钉住，生成的不能。
  assert.deepEqual(Object.keys(SUGGESTED_ACTIONS).sort(),
    ["DEGRADED", "HEALTHY", "UNAVAILABLE", "UNKNOWN"]);
  for (const action of Object.values(SUGGESTED_ACTIONS)) {
    assert.match(action, /^[a-z_]+$/, "建议动作不是固定串——像是生成出来的");
  }
  const projector = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "status", "live-status-projector.js"), "utf8");
  for (const hint of ["runUserModelTurn", "createChatCompletion", "callModel", "openai", "deepseek"]) {
    assert.ok(!projector.includes(hint), `投影器里出现了 ${hint}——自愈调模型了`);
  }
  assert.equal(projectLiveStatus({ facts: {}, generatedAt: new Date(NOW) }).status.model_calls, 0);
});

// ── AC-026 禁止配置性伪绿 ─────────────────────────────────

test("AC-026 五段纵向内容在没有回执时全是 UNKNOWN，不是绿", () => {
  // 这条是这个节点的核心。刚部署完的系统每一段都没被真实跑过——显示绿是
  // 配置性伪绿，显示红是指着一个不存在的故障。
  const built = snapshot();
  for (const section of ["queue", "canonical_sync", "backups"]) {
    assert.equal(built[section].state, "UNKNOWN", `${section} 在没有回执时不是 UNKNOWN`);
  }
  for (const mode of MODES) {
    assert.equal(built.modes[mode].state, "UNKNOWN");
  }
});

test("AC-026 configured=true 单独一个字段变不成绿", () => {
  // 直接的反面测试：把每一段都标成「配置好了」，一个回执都不给。
  const built = snapshot({
    modes: { OWNER: { configured: true }, COMPANION: { configured: true } },
    queue: { configured: true },
    canonicalSync: { configured: true },
    backups: { configured: true },
  });
  for (const section of ["queue", "canonical_sync", "backups"]) {
    assert.notEqual(built[section].state, "HEALTHY", `${section} 靠配置就变绿了`);
  }
  for (const mode of MODES) {
    assert.notEqual(built.modes[mode].state, "HEALTHY");
  }
});

test("AC-026 一次真实成功回执才换来绿", () => {
  const built = snapshot({
    queue: { configured: true, lastDrainedAt: ago(60_000) },
    canonicalSync: { configured: true, lastSyncedAt: ago(60_000) },
    backups: {
      configured: true, lastBackupAt: ago(60_000), lastRestoreDrillAt: ago(86_400_000),
    },
  });
  assert.equal(built.queue.state, "HEALTHY");
  assert.equal(built.canonical_sync.state, "HEALTHY");
  assert.equal(built.backups.state, "HEALTHY");
});

test("AC-026 调用方传不进 state——状态只能由回执推出来", () => {
  // 能传 state 的话，这一整套「没测过 ≠ 坏的」就白做了：谁想显示绿都能显示绿。
  const built = buildQueue({ configured: true, state: "HEALTHY", now: NOW });
  assert.equal(built.state, "UNKNOWN", "调用方直接指定的 state 被采信了");
});

test("AC-026 量不到的资源是 UNKNOWN，不是「资源充裕」", () => {
  // Number(null) 是 0 而 Number.isFinite(0) 是 true——只写 isFinite(Number(v))
  // 的话，一项没量到的资源会当成「量到了，是 0」，然后显示成资源充裕。
  const blind = buildResources({ cpuLoad: 0.1, memoryFreeRatio: 0.5, now: NOW });
  assert.equal(blind.state, "UNKNOWN");
  assert.equal(blind.disk_free_ratio, null);
  assert.equal(blind.admits_new_work, null, "量不到却报了「能收活」");

  const measured = buildResources({
    cpuLoad: 0.1, memoryFreeRatio: 0.5, diskFreeRatio: 0.4,
    admitsNewWork: true, measuredAt: ago(1000), now: NOW,
  });
  assert.equal(measured.state, "HEALTHY");
});

test("AC-026 全 0 的资源读数是「满了」，不是「没量到」", () => {
  // 上一条的反面：0 是一个合法读数，不许被当成缺测。
  const full = buildResources({
    cpuLoad: 0, memoryFreeRatio: 0, diskFreeRatio: 0,
    admitsNewWork: false, reasonCode: "DISK_FULL", measuredAt: ago(1000), now: NOW,
  });
  assert.equal(full.state, "DEGRADED");
  assert.equal(full.disk_free_ratio, 0);
  assert.equal(full.reason, "DISK_FULL");
});

// ── AC-035 备份跑过 ≠ 备份能恢复 ─────────────────────────

test("AC-035 备份一直在跑但从没恢复演练过——这一格必须说出来", () => {
  // 最危险的一格，因为它看起来是绿的。真出事那天主人会发现他有 400 天的
  // 备份，一份都恢复不了。
  const built = buildBackups({
    configured: true, lastBackupAt: ago(60_000), objectCount: 128, now: NOW,
  });
  assert.equal(built.state, "HEALTHY");
  assert.equal(built.restore_drill_state, "UNKNOWN");
  assert.equal(built.suggested_action, "run_restore_drill");
});

test("AC-035 演练过之后建议动作才回到 none", () => {
  const built = buildBackups({
    configured: true, lastBackupAt: ago(60_000), lastRestoreDrillAt: ago(86_400_000), now: NOW,
  });
  assert.equal(built.restore_drill_state, "HEALTHY");
  assert.equal(built.suggested_action, "none");
});

// ── FR-026 降级档位 ───────────────────────────────────────

test("FR-026 降级档位和被关掉的能力对得上", () => {
  const built = buildMode({ mode: "OWNER", degradationLevel: "severe", now: NOW });
  assert.equal(built.degradation_level, "severe");
  assert.equal(built.degradation_depth, 4);
  assert.equal(built.disabled.length, 4);
  assert.ok(built.disabled.includes("guest_model"));
  assert.ok(!built.disabled.includes("owner_new_tasks"), "severe 不该关主人的新任务");
});

test("FR-026 认不出来的降级档位整份拒绝，不当成 normal", () => {
  // 当成 normal 会把一次真实降级显示成「一切正常」——面板最不该说的谎。
  assert.throws(
    () => buildMode({ mode: "OWNER", degradationLevel: "kinda_bad", now: NOW }),
    (error) => error.code === "SECTION_DEGRADATION_UNKNOWN",
  );
});

test("FR-026 两个模式都必须在", () => {
  const built = buildModes({ OWNER: { configured: true } }, { now: NOW });
  assert.deepEqual(Object.keys(built).sort(), ["COMPANION", "OWNER"]);
});

// ── 压回一行给窄的地方看 ──────────────────────────────────

test("AC-026 压成一行时取更差的那个", () => {
  // 取更好的那个等于用主人这条好路盖住访客那条坏路，而访客那条坏了正是
  // 没人会注意到的情况。
  const grid = fullGrid().map((line) => (
    line.business_line === "ai_provider_connection" && line.mode === "COMPANION"
      ? { ...line, state: "blocked" }
      : line
  ));
  const collapsed = collapseModes(buildBusinessMatrix(grid));
  assert.equal(collapsed.length, 15);
  assert.equal(
    collapsed.find((line) => line.business_line === "ai_provider_connection").state,
    "blocked",
    "访客那条坏路被主人那条好路盖住了",
  );
});

// ── 真实投影链路 ──────────────────────────────────────────

test("AC-026 真实投影产出 30 格且过得了整份校验", () => {
  // 纯函数全绿而真实链路产出的东西过不了校验，是这个仓最熟悉的失败形状。
  const live = projectLiveStatus({
    facts: { channelReady: true, admissionEnabled: true, timezoneSignalsSeen: 3 },
    generatedAt: new Date(NOW),
  });
  assert.equal(live.status.capabilities.length, 30);
  assert.equal(live.status.schema_version, 2);
  const tz = live.status.capabilities.filter((l) => l.business_line === "location_timezone");
  assert.equal(tz.length, 2);
  assert.ok(tz.every((l) => l.state === "healthy"), "采到过时区信号却不算跑起来过");
});

test("AC-026 一个时区信号都没采到时，那一格不是绿", () => {
  // 表建好了不算跑起来过。
  const live = projectLiveStatus({ facts: {}, generatedAt: new Date(NOW) });
  const tz = live.status.capabilities.filter((l) => l.business_line === "location_timezone");
  assert.ok(tz.every((l) => l.state === "not_started"));
  assert.ok(tz.every((l) => l.suggested_action === "wait_for_first_join"));
});

test("AC-026 访客够不着 Codex，那一格不许报主人的健康度", () => {
  // 串模式的伪绿是最坏的一种：主人看自己那边一直是好的。
  const live = projectLiveStatus({
    facts: { ownerRuntimeReady: true }, generatedAt: new Date(NOW),
  });
  const codex = Object.fromEntries(live.status.capabilities
    .filter((l) => l.business_line === "owner_codex_runtime")
    .map((l) => [l.mode, l]));
  assert.equal(codex.OWNER.state, "healthy");
  assert.equal(codex.COMPANION.state, "not_started");
  assert.equal(codex.COMPANION.reason_code, "OWNER_ONLY_CAPABILITY");
});

test("AC-026 同一份输入两次算出同一个摘要", () => {
  const first = snapshot();
  const second = snapshot();
  assert.equal(first.snapshot_sha256, second.snapshot_sha256);
  assert.match(first.snapshot_sha256, /^[0-9a-f]{64}$/);
});

test("AC-026 同步的 commit 只认 40 位十六进制", () => {
  // 认别的形状会让一个写错的字段原样显示在公开页上。
  const bad = buildCanonicalSync({ configured: true, lastCommitSha: "HEAD -> main", now: NOW });
  assert.equal(bad.last_commit, null);
  const good = buildCanonicalSync({
    configured: true, lastCommitSha: "a".repeat(40), now: NOW,
  });
  assert.equal(good.last_commit, "aaaaaaaaaaaa");
});

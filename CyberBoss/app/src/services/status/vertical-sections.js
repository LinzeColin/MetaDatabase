"use strict";

// Status 纵向矩阵缺的那几段（CB9-510 / AC-026、AC-035、FR-026、NFR-005）。
//
// FR-026 的原话：status 页要展示「双模式、15 项能力、队列、资源、同步、备份、
// 版本、降级和恢复」，而且**仍是只读投影**。
//
// 15 项能力和版本在 business-matrix.js 里；这个模块补另外五段：
//   modes          双模式（各自带降级档位）
//   queue          队列
//   resources      资源
//   canonical_sync 权威同步
//   backups        备份
//
// 每一段都遵守同一条规矩，就是 CB9-500 那条：**「没测过」和「测过是坏的」是
// 两回事**。一段从来没被真实跑过的能力显示 UNKNOWN，不显示绿也不显示红——
// 显示绿是配置性伪绿，显示红是指着一个不存在的故障。
//
// 所以每一段的状态都不是这里算出来的，而是把回执交给 parity-freshness 判。
// 这个模块自己**够不着**配置：不 require fs，不读 process.env——够不着就伪造
// 不出来，比「我们没这么做」强。

const { freshnessOf } = require("./parity-freshness");
const { LEVELS, disabledAt, normalizeLevel } = require("../operations/degradation-ladder");

// 两个模式。同一项能力对主人和对访客可以是不同状态：主人的 Codex 好好的，
// 而访客那条 provider 路可能从第一天起就是断的。合成一个状态就把这件事抹平，
// 而抹平的方向永远是往好里抹——坏的那一半被好的那一半盖住。
const MODES = Object.freeze(["OWNER", "COMPANION"]);

// 五段的名字是冻结的。少一段整份拒绝：一份悄悄少了「备份」的 status，看的人
// 会以为备份这件事不存在，而不是以为它坏了。
const SECTION_NAMES = Object.freeze([
  "modes", "queue", "resources", "canonical_sync", "backups",
]);

class VerticalSectionError extends Error {
  constructor(code, detail) {
    super(code);
    this.name = "VerticalSectionError";
    this.code = code;
    this.detail = detail ?? null;
  }
}

function requireCount(value, field) {
  const count = Number(value);
  if (!Number.isFinite(count) || count < 0) {
    throw new VerticalSectionError("SECTION_FIELD_NOT_A_COUNT", field);
  }
  return count;
}

// 一段的状态永远由回执推出来，不由调用方直接给。
//
// 让调用方传 state 的话，这整套「没测过 ≠ 坏的」就白做了——谁想显示绿都能
// 显示绿。这里只收两个时刻，而那两个时刻只能由真实链路写。
function verdictFor({ configured, lastSuccessAt, lastFailureAt, now, freshMs }) {
  return freshnessOf({
    configured: configured === true,
    lastSuccessAt: lastSuccessAt ?? null,
    lastFailureAt: lastFailureAt ?? null,
    now,
    ...(Number.isFinite(freshMs) ? { freshMs } : {}),
  });
}

// AC-035 要的「建议动作」。
//
// 一个只说「坏了」的面板，主人看完还是不知道该干什么，于是他会去问模型——
// 而 NFR-005 明令自愈不许调模型。建议动作必须是**这张表里查出来的固定串**，
// 不是生成的：生成的话就是模型调用换了个地方。
const SUGGESTED_ACTIONS = Object.freeze({
  HEALTHY: "none",
  DEGRADED: "check_recent_change",
  UNAVAILABLE: "restart_and_check_upstream",
  UNKNOWN: "exercise_once_to_learn_state",
});

function suggestedActionFor(state) {
  return SUGGESTED_ACTIONS[state] || SUGGESTED_ACTIONS.UNKNOWN;
}

// ── modes：双模式 + 降级档位 ──────────────────────────────

// 一个模式当前是什么样。
//
// degradation_level 是**降级档位**（FR-026 的「降级」），disabled 是这个档位下
// 已经关掉的能力清单——直接从 CB9-320 那条冻结的降级顺序里取，不在这里重排。
// 重排的话就有两份顺序，而两份顺序迟早会不一致；不一致的时候面板说关了 A，
// 实际关的是 B。
function buildMode({
  mode,
  configured = false,
  lastSuccessAt = null,
  lastFailureAt = null,
  degradationLevel = "normal",
  now = Date.now(),
} = {}) {
  if (!MODES.includes(mode)) {
    throw new VerticalSectionError("SECTION_MODE_UNKNOWN", String(mode ?? ""));
  }
  // 认不出来的档位当 normal 会把一次真实降级显示成「一切正常」——那正是
  // 面板最不该说的谎。认不出来就是配错了，整份拒绝。
  if (!Object.prototype.hasOwnProperty.call(LEVELS, String(degradationLevel))) {
    throw new VerticalSectionError("SECTION_DEGRADATION_UNKNOWN", String(degradationLevel));
  }
  const level = normalizeLevel(String(degradationLevel));
  const verdict = verdictFor({ configured, lastSuccessAt, lastFailureAt, now });
  return Object.freeze({
    mode,
    state: verdict.state,
    reason: verdict.reason,
    degradation_level: level,
    degradation_depth: LEVELS[level],
    disabled: disabledAt(level),
    last_success_at: verdict.last_success_at,
    last_failure_at: verdict.last_failure_at,
    suggested_action: suggestedActionFor(verdict.state),
    evaluated_at: verdict.evaluated_at,
  });
}

// 两个模式都得在。少一个的话，看的人默认「没列出来的那个没问题」——而实际上
// 最可能是没人管的那一个坏了。
function buildModes(input = {}, { now = Date.now() } = {}) {
  const built = MODES.map((mode) => buildMode({ ...(input[mode] || {}), mode, now }));
  return Object.freeze(Object.fromEntries(built.map((entry) => [entry.mode, entry])));
}

// ── queue：队列 ───────────────────────────────────────────

// 队列的健康不是「深度是不是 0」。
//
// 深度 0 可能是没积压，也可能是**投递线程死了根本没人往里放**。区分靠最老的
// 那条待办等了多久：队列在动的话，最老的那条会一直被换掉。
function buildQueue({
  depth = 0,
  oldestJobSeconds = 0,
  lastDrainedAt = null,
  lastFailureAt = null,
  configured = false,
  now = Date.now(),
} = {}) {
  const verdict = verdictFor({
    configured, lastSuccessAt: lastDrainedAt, lastFailureAt, now,
  });
  return Object.freeze({
    depth: requireCount(depth, "depth"),
    oldest_job_seconds: requireCount(oldestJobSeconds, "oldest_job_seconds"),
    state: verdict.state,
    reason: verdict.reason,
    last_success_at: verdict.last_success_at,
    last_failure_at: verdict.last_failure_at,
    suggested_action: suggestedActionFor(verdict.state),
    evaluated_at: verdict.evaluated_at,
  });
}

// ── resources：资源 ───────────────────────────────────────

// 资源这一段和别的几段不一样：它是**当场量出来的**，不是回执。所以它的状态
// 由闸门给（admits / 不 admits），而 configured 恒真——量得到就是量得到。
//
// 但量不到的时候不许当成 0。0 会显示成「资源充裕」，而实际情况是我们瞎了。
function buildResources({
  cpuLoad = null,
  memoryFreeRatio = null,
  diskFreeRatio = null,
  admitsNewWork = null,
  reasonCode = null,
  measuredAt = null,
  now = Date.now(),
} = {}) {
  // null 必须单独挡掉：Number(null) 是 0，而 Number.isFinite(0) 是 true。
  // 只写 Number.isFinite(Number(v)) 的话，一项**没量到**的资源会当成
  // 「量到了，是 0」——0 的磁盘占用显示成资源充裕，而实际是我们瞎了。
  // 这正是这个函数下面那行注释警告的事，第一版还是踩了。
  const measured = [cpuLoad, memoryFreeRatio, diskFreeRatio].every(
    (value) => value !== null && value !== undefined && Number.isFinite(Number(value)),
  );
  const state = !measured || measuredAt === null
    ? "UNKNOWN"
    : (admitsNewWork === true ? "HEALTHY" : "DEGRADED");
  return Object.freeze({
    cpu_load: measured ? Number(cpuLoad) : null,
    memory_free_ratio: measured ? Number(memoryFreeRatio) : null,
    disk_free_ratio: measured ? Number(diskFreeRatio) : null,
    admits_new_work: state === "UNKNOWN" ? null : admitsNewWork === true,
    state,
    reason: state === "UNKNOWN" ? "not_measured" : (reasonCode || "measured"),
    last_success_at: state === "HEALTHY" ? measuredAt : null,
    last_failure_at: state === "DEGRADED" ? measuredAt : null,
    suggested_action: suggestedActionFor(state),
    evaluated_at: new Date(Number(now)).toISOString(),
  });
}

// ── canonical_sync：权威同步 ──────────────────────────────

// 同步的新鲜窗口比默认的宽：它按批走，两批之间本来就会有一段没有成功回执，
// 用 15 分钟去卡会一直翻黄，而一直翻黄的面板等于没有面板。
const SYNC_FRESH_MS = 6 * 60 * 60 * 1000;

function buildCanonicalSync({
  configured = false,
  lastSyncedAt = null,
  lastFailureAt = null,
  pendingFacts = 0,
  lastCommitSha = null,
  now = Date.now(),
} = {}) {
  const verdict = verdictFor({
    configured, lastSuccessAt: lastSyncedAt, lastFailureAt, now, freshMs: SYNC_FRESH_MS,
  });
  return Object.freeze({
    state: verdict.state,
    reason: verdict.reason,
    pending_facts: requireCount(pendingFacts, "pending_facts"),
    // 短 sha，而且只有 40 位十六进制才认。认别的形状会让一个写错的字段
    // 原样显示在公开页上，而那正是隐私投影要挡的东西。
    last_commit: /^[0-9a-f]{40}$/.test(String(lastCommitSha ?? ""))
      ? String(lastCommitSha).slice(0, 12)
      : null,
    last_success_at: verdict.last_success_at,
    last_failure_at: verdict.last_failure_at,
    suggested_action: suggestedActionFor(verdict.state),
    evaluated_at: verdict.evaluated_at,
  });
}

// ── backups：备份 ─────────────────────────────────────────

// 备份的新鲜窗口是一天多一点：它一天跑一次，正好 24 小时会在边界上抖。
const BACKUP_FRESH_MS = 26 * 60 * 60 * 1000;

// 「备份跑过了」和「备份能恢复」是两件事，而只有后者算数。
//
// 一个只报「上次备份成功」的面板，在真出事那天会告诉主人他有 400 天的备份，
// 然后发现一份都恢复不了。所以恢复演练的时刻单独一格，而且没演练过就是
// UNKNOWN——不许拿备份成功去顶。
function buildBackups({
  configured = false,
  lastBackupAt = null,
  lastFailureAt = null,
  lastRestoreDrillAt = null,
  objectCount = 0,
  now = Date.now(),
} = {}) {
  const verdict = verdictFor({
    configured, lastSuccessAt: lastBackupAt, lastFailureAt, now, freshMs: BACKUP_FRESH_MS,
  });
  const drill = freshnessOf({
    configured: configured === true,
    lastSuccessAt: lastRestoreDrillAt ?? null,
    now,
    // 演练一个月一次就够；卡太紧会让人为了让面板变绿去乱演练。
    freshMs: 31 * 24 * 60 * 60 * 1000,
  });
  return Object.freeze({
    state: verdict.state,
    reason: verdict.reason,
    object_count: requireCount(objectCount, "object_count"),
    last_success_at: verdict.last_success_at,
    last_failure_at: verdict.last_failure_at,
    // 恢复演练自己的状态，和备份成功分开。
    restore_drill_state: drill.state,
    last_restore_drill_at: drill.last_success_at,
    suggested_action: verdict.state === "HEALTHY" && drill.state !== "HEALTHY"
      // 备份在跑但从没恢复过——这是最危险的那一格，因为它看起来是绿的。
      ? "run_restore_drill"
      : suggestedActionFor(verdict.state),
    evaluated_at: verdict.evaluated_at,
  });
}

module.exports = {
  BACKUP_FRESH_MS,
  MODES,
  SECTION_NAMES,
  SUGGESTED_ACTIONS,
  SYNC_FRESH_MS,
  VerticalSectionError,
  buildBackups,
  buildCanonicalSync,
  buildMode,
  buildModes,
  buildQueue,
  buildResources,
  suggestedActionFor,
};

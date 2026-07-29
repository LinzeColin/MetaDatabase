"use strict";

// 「我的意思是不依赖开发agent去运维。」
//
// 今天查出来的三个故障，主人一个都发现不了：
//   · 回复延迟三分钟——闸门在负载高时拒绝派发，他只看到"过了五分钟才回"
//   · 全量同步每天失败——EACCES，日志里躺了好几天，没人看
//   · 个人主页整条路 404——部署"成功"了，页面也打得开，只是数据接口是死的
//
// 三个都不是资源问题。主机上那个自愈引擎每五分钟跑一次，查的是磁盘、内存、
// 负载——**它对这三件事一无所知**，因为它查的是"机器还好吗"，而坏掉的是
// "这个产品还在干活吗"。
//
// 所以这一层只看结果：该发的发出去了吗、该同步的同步了吗、回话有多快、
// 主动消息是不是在空转。发现问题就用微信告诉主人，说人话，说清楚要不要他管。
//
// 两条纪律：
//   1. **只在状态翻转时说**。每轮都报一遍等于没报——他会学会忽略。
//   2. **好了也要说一句**。只报坏不报好，他永远不知道现在到底行不行。

const HOUR_MS = 3_600_000;

// 判据。写成常量而不是散在代码里，是为了让"这个阈值凭什么是这个数"有地方回答。
const THRESHOLDS = Object.freeze({
  // 全量同步和冷备都是每天一次。超过 26 小时没成功＝至少漏了一整轮。
  syncStaleMs: 26 * HOUR_MS,
  backupStaleMs: 26 * HOUR_MS,
  // 从入队到开始处理。正常是零点几秒；今天那次是 190 秒。
  // 30 秒是长轮询一轮的量级，超过它就说明不是在等消息，是被什么卡住了。
  queueWaitMs: 30_000,
  // 一条 job 跑了这么久还没结束，多半是挂住了而不是在想。
  jobStuckMs: 10 * 60_000,
  // 出站送达率。低于这个数就是有人在说话但收不到回音。
  deliveredRatio: 0.9,
  // 主动打招呼连续这么多次决定不说话＝在空转烧额度。
  // 今天的实测是连续 6 次全 silent，一天 288 次。
  silentStreak: 5,
});

function isoMs(value) {
  const at = new Date(value || 0).getTime();
  return Number.isFinite(at) && at > 0 ? at : 0;
}

function hoursAgo(atMs, nowMs) {
  return Math.max(0, Math.round((nowMs - atMs) / HOUR_MS));
}

function median(values) {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : Math.round((sorted[middle - 1] + sorted[middle]) / 2);
}

// facts 全部是已经查好的普通值，这个函数不碰数据库也不碰时钟以外的东西——
// 这样每一条判据都能单独喂一组数字测出来。
function evaluateHealth(facts = {}, { now = Date.now() } = {}) {
  const findings = [];
  const add = (id, title, detail, hint) => {
    findings.push(Object.freeze({ id, title, detail, hint }));
  };

  // ── 全量数据库 ────────────────────────────────────────────
  const syncedAt = isoMs(facts.canonicalSyncedAt);
  if (!syncedAt) {
    add(
      "sync_never",
      "全量数据库从来没同步成功过",
      "GitHub 私仓里现在是空的。",
      "这条要我查，回一句「体检」把详情发给我。",
    );
  } else if (now - syncedAt > THRESHOLDS.syncStaleMs) {
    add(
      "sync_stale",
      "全量数据库同步停了",
      `上一次成功是 ${hoursAgo(syncedAt, now)} 小时前。`,
      "新的聊天记录暂时只在这台机器上，没进私仓。",
    );
  }

  // ── 冷备 ──────────────────────────────────────────────────
  const backupAt = isoMs(facts.backupAt);
  if (backupAt && now - backupAt > THRESHOLDS.backupStaleMs) {
    add(
      "backup_stale",
      "冷备停了",
      `上一次备份是 ${hoursAgo(backupAt, now)} 小时前。`,
      "机器坏掉的话，这段时间的数据没有异地副本。",
    );
  }

  // ── 回话有多快 ────────────────────────────────────────────
  //
  // 这一条今天真出过：消息 07:11:11 入队，07:14:21 才被取走。主人只知道
  // "过了五分钟才回"，不知道那三分钟是闸门在拒绝派发。
  const waits = (facts.recentJobs || [])
    .map((job) => isoMs(job.startedAt) - isoMs(job.queuedAt))
    .filter((wait) => Number.isFinite(wait) && wait >= 0);
  if (waits.length >= 3) {
    const wait = median(waits);
    if (wait > THRESHOLDS.queueWaitMs) {
      add(
        "reply_slow",
        "回话变慢了",
        `最近几条消息平均等了 ${Math.round(wait / 1000)} 秒才开始处理。`,
        "不是在想，是排队排住了。这条要我查。",
      );
    }
  }

  // ── 有 job 挂住 ───────────────────────────────────────────
  const stuck = (facts.runningJobs || [])
    .filter((job) => isoMs(job.startedAt) && now - isoMs(job.startedAt) > THRESHOLDS.jobStuckMs);
  if (stuck.length) {
    add(
      "job_stuck",
      "有消息卡住了",
      `${stuck.length} 条已经跑了十分钟以上还没结束。`,
      "如果你刚才发了消息没等到回复，就是这个。",
    );
  }

  // ── 送达 ──────────────────────────────────────────────────
  const confirmed = Number(facts.outbox?.confirmed) || 0;
  const failed = Number(facts.outbox?.failed) || 0;
  const total = confirmed + failed;
  if (total >= 5 && confirmed / total < THRESHOLDS.deliveredRatio) {
    add(
      "delivery_bad",
      "有回复没送出去",
      `最近 ${total} 条里有 ${failed} 条没发成功。`,
      "对方可能一直在等，而这边以为已经回了。",
    );
  }

  // ── 主动消息在空转 ────────────────────────────────────────
  //
  // 唤醒模型、模型决定不说话、什么都没发生——但 token 花了。五分钟一轮的时候
  // 这是一天 288 次。
  const silent = Number(facts.checkinSilentStreak) || 0;
  if (silent >= THRESHOLDS.silentStreak) {
    add(
      "checkin_silent",
      "主动打招呼在空转",
      `连续 ${silent} 次唤醒之后都决定不说话。`,
      "每次都花了额度但你什么都没收到。可以把间隔调长一点。",
    );
  }

  // ── 库的版本 ──────────────────────────────────────────────
  //
  // 部署"成功"但迁移没跑上去，是一种看起来完全正常的坏：页面打得开、聊天也
  // 通，只有新功能永远是空的。
  const schema = Number(facts.schema) || 0;
  const expected = Number(facts.schemaExpected) || 0;
  if (expected && schema < expected) {
    add(
      "schema_behind",
      "数据库没升级到最新",
      `现在是第 ${schema} 版，应该是第 ${expected} 版。`,
      "新功能会看起来是空的。这条要我查。",
    );
  }

  return Object.freeze({
    at: new Date(now).toISOString(),
    healthy: findings.length === 0,
    findings: Object.freeze(findings),
  });
}

// 只在翻转时说话。
//
// previous 是上一次报过的 id 列表（存在 service_state 里，那一列是明文，所以
// 只能放这种固定的英文码，不能放任何人写的字）。
function diffFindings(previous, current) {
  const before = new Set(Array.isArray(previous) ? previous : []);
  const after = new Set(current.map((finding) => finding.id));
  return Object.freeze({
    appeared: Object.freeze(current.filter((finding) => !before.has(finding.id))),
    recovered: Object.freeze([...before].filter((id) => !after.has(id))),
    active: Object.freeze([...after]),
  });
}

// 发给主人的那条微信。短，说人话，说清楚要不要他管。
function buildAlertMessage(appeared) {
  if (!appeared.length) {
    return "";
  }
  const lines = appeared.map((finding) => `· ${finding.title}\n  ${finding.detail}\n  ${finding.hint}`);
  const head = appeared.length === 1 ? "有件事你得知道：" : `有 ${appeared.length} 件事你得知道：`;
  return `${head}\n\n${lines.join("\n\n")}`;
}

const RECOVERY_LABEL = Object.freeze({
  sync_never: "全量数据库同步",
  sync_stale: "全量数据库同步",
  backup_stale: "冷备",
  reply_slow: "回话速度",
  job_stuck: "卡住的消息",
  delivery_bad: "回复送达",
  checkin_silent: "主动打招呼",
  schema_behind: "数据库版本",
});

function buildRecoveryMessage(recoveredIds) {
  const labels = recoveredIds
    .map((id) => RECOVERY_LABEL[id])
    .filter(Boolean);
  if (!labels.length) {
    return "";
  }
  return `${labels.join("、")}恢复正常了。`;
}

module.exports = {
  THRESHOLDS,
  buildAlertMessage,
  buildRecoveryMessage,
  diffFindings,
  evaluateHealth,
};

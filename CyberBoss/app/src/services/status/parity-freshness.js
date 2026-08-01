"use strict";

// 「没测过」和「测过是坏的」是两回事（CB9-500 / AC-025、FR-025）。
//
// AC-025 把四种状态写死了：
//   配置存在但没有 live receipt  → UNKNOWN
//   有新鲜的成功回执            → HEALTHY
//   回执过期了                  → DEGRADED
//   最近一次是失败              → UNAVAILABLE
//
// 为什么必须分开：
//
// 一个刚部署完的系统，每一项能力都是「还没被真实调用过」。如果这时候面板显示
// 红色，主人会去查一个**不存在的故障**——而查完发现「哦原来只是还没人用」，
// 下一次真的红了他就不会再当回事。这是这套面板最容易毁掉自己的方式。
//
// 反过来，把「没测过」显示成绿色更糟：那是**配置性伪绿**——配置文件里写着这项
// 能力开着，于是面板说它健康，而它可能从第一天起就是坏的。AC-026 明令禁止。
//
// 所以：绿色只能由一次**真实链路成功**换来（真实入口 → Runtime → 动作 → 投递），
// 而且那次成功还得是新鲜的。旧的成功不是成功——它只证明那时候是好的。

const STATES = Object.freeze(["HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN"]);

// 只有这几种状态算「能用」。UNKNOWN 不算——它是「不知道」，而把不知道
// 当成能用就是伪绿。
const USABLE = Object.freeze(["HEALTHY"]);

// 默认新鲜度窗口。
//
// 15 分钟不是随便定的：主动检查的最小间隔是 45 分钟（persona 的 proactive
// 默认下限），而一次真实链路成功平均由用户的一次交互产生。窗口比检查间隔短的
// 话，面板会在两次交互之间频繁翻黄；比它长太多的话，一次真实故障要很久才显出来。
const DEFAULT_FRESH_MS = 15 * 60 * 1000;

// 失败之后多久不再算「最近失败」。
//
// 比新鲜窗口长：一次失败的信息价值比一次成功高——它说明这条路真的会坏，而
// 那件事值得多记一会儿。短于新鲜窗口的话，一次失败会被紧接着的一次成功立刻
// 抹掉，而抖动正是这样被藏起来的。
const DEFAULT_FAILURE_STICKY_MS = 30 * 60 * 1000;

// 数字、Date、ISO 字符串都收。
//
// 第一版漏了数字：Date.parse(1785336480000) 是 NaN，于是一个用 Date.parse()
// 算出来的 now 会被判成「读不出来」，然后**悄悄回退到真实时钟**——测试里喂进
// 去的假时钟一点用都没有，而且失败方式看起来像业务逻辑错了。
// 这和 CB9-250 那条「喂不进去读数就证明不了读数被用上」是同一个形状。
function toMs(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const parsed = value instanceof Date ? value.getTime() : Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// 一项能力现在算什么状态。
//
// receipt 是**最近一次真实链路**的回执，不是配置。没有回执就是没有回执——
// 不许拿「配置里开着」去顶。
function freshnessOf({
  configured = false,
  lastSuccessAt = null,
  lastFailureAt = null,
  now = Date.now(),
  freshMs = DEFAULT_FRESH_MS,
  failureStickyMs = DEFAULT_FAILURE_STICKY_MS,
} = {}) {
  const nowMs = toMs(now) ?? Date.now();
  const success = toMs(lastSuccessAt);
  const failure = toMs(lastFailureAt);

  if (!configured) {
    // 没配置的能力不该出现在矩阵里；真出现了也只能是 UNKNOWN，不能是别的。
    return build("UNKNOWN", "not_configured", { success, failure, nowMs });
  }
  if (success === null && failure === null) {
    // **这一条是这个模块存在的理由。**
    // 配置存在但从来没有真实链路跑过——不知道，不是坏。
    return build("UNKNOWN", "no_live_receipt", { success, failure, nowMs });
  }

  // 最近一次失败还在粘滞窗口内 → 不可用。
  //
  // 判在成功之前：一次失败之后紧接着一次成功，说明这条路在抖，而抖动对用户
  // 就是「有时候不行」。直接显示绿色会把这件事藏起来。
  if (failure !== null && nowMs - failure <= failureStickyMs
    && (success === null || failure >= success)) {
    return build("UNAVAILABLE", "recent_failure", { success, failure, nowMs });
  }
  if (success === null) {
    // 只有失败、而且失败已经不新鲜了——仍然不知道现在怎么样。
    return build("UNKNOWN", "stale_failure_no_success", { success, failure, nowMs });
  }
  if (nowMs - success <= freshMs) {
    return build("HEALTHY", "fresh_success", { success, failure, nowMs });
  }
  // 有过成功，但已经旧了。旧的成功不是成功——它只证明那时候是好的。
  return build("DEGRADED", "stale_success", { success, failure, nowMs });
}

function build(state, reason, { success, failure, nowMs }) {
  return Object.freeze({
    state,
    reason,
    usable: USABLE.includes(state),
    // 「最后一次真正评估的时间」。
    //
    // 没有这个字段的话，面板上一个 UNKNOWN 和一个刚刚被评估过的 UNKNOWN 长得
    // 一模一样，而它们是两件事：前者是「这套系统还没跑起来」，后者是「跑起来
    // 了但这一项一直没人用」。
    last_success_at: success === null ? null : new Date(success).toISOString(),
    last_failure_at: failure === null ? null : new Date(failure).toISOString(),
    age_ms: success === null ? null : Math.max(0, nowMs - success),
    evaluated_at: new Date(nowMs).toISOString(),
  });
}

// 一整份矩阵的总体状态。
//
// 取最差的那一项，但 UNKNOWN 不拉低整体——把「有一项没人用过」显示成「系统
// 有问题」，是同一个「指着不存在的故障」的错误，只是换了个层级。
const SEVERITY = Object.freeze({ HEALTHY: 0, UNKNOWN: 0, DEGRADED: 1, UNAVAILABLE: 2 });

function rollup(entries = []) {
  const list = Array.isArray(entries) ? entries.filter(Boolean) : [];
  if (list.length === 0) {
    return Object.freeze({ state: "UNKNOWN", reason: "empty_matrix", counts: Object.freeze({}) });
  }
  const counts = {};
  let worst = "HEALTHY";
  for (const entry of list) {
    const state = STATES.includes(entry.state) ? entry.state : "UNKNOWN";
    counts[state] = (counts[state] || 0) + 1;
    if (SEVERITY[state] > SEVERITY[worst]) {
      worst = state;
    }
  }
  // 全是 UNKNOWN 时整体就是 UNKNOWN，不是 HEALTHY——一项都没验过的系统
  // 不该显示健康。
  if ((counts.UNKNOWN || 0) === list.length) {
    return Object.freeze({ state: "UNKNOWN", reason: "nothing_verified_yet", counts: Object.freeze(counts) });
  }
  return Object.freeze({
    state: worst,
    reason: worst === "HEALTHY" ? "all_fresh" : `worst_of_${list.length}`,
    counts: Object.freeze(counts),
  });
}

module.exports = {
  DEFAULT_FAILURE_STICKY_MS,
  DEFAULT_FRESH_MS,
  SEVERITY,
  STATES,
  USABLE,
  freshnessOf,
  rollup,
};

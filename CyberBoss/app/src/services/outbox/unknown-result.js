"use strict";

// 「不知道成没成」是第三种结果（CB9-450 / AC-023、AC-024、FR-023）。
//
// FR-023 的原话：「微信重复投递、进程崩溃和回复失败不会造成重复任务或重复副作
// 用；**未知结果显式对账**。」
//
// 发一条消息出去，只有两种结果是确定的：
//   成功 —— 对面回了 200，消息到了。
//   失败 —— 对面回了明确的错误码（token 过期、参数不对、被封），消息没到。
//
// 但还有第三种，而且它才是最常见的那种：**超时、连接断开、502**。这时候我们
// 不知道消息到没到——请求可能在到达对面之前断了，也可能对面处理完了、回包丢了。
//
// 把它当失败重试 → 用户收到两条一模一样的消息。
// 把它当成功不管 → 用户什么都没收到，而系统认为发过了。
//
// 两种都错，而且错得不对称：重复发用户会觉得这系统有毛病但至少信息到了；
// 丢消息则是他等的那件事永远没来，而且没人知道。所以未知结果不许被归到任何
// 一边——它进 reconcile，由一次**查询**来定性，不是由一次重试来定性。
//
// 这个模块是纯函数：它只回答「这个错误属于哪一类」和「下一步该怎么办」，
// 不发请求也不写库。定性和处置分开，是为了让定性这件事能单独测——而它正是
// 最容易写错的一半。

// 明确失败：对面告诉了我们「没成」。重试是安全的（如果还值得重试）。
const DEFINITE_FAILURE = Object.freeze([
  "WEIXIN_TOKEN_EXPIRED",
  "WEIXIN_INVALID_ARGUMENT",
  "WEIXIN_FORBIDDEN",
  "WEIXIN_RATE_LIMITED",
  "PAYLOAD_TOO_LARGE",
]);

// 不知道：请求发出去了，但没拿到明确答复。
//
// 这几个都是**传输层**的症状，不是业务层的答复。业务层没说话，就不能替它说。
const UNKNOWN_SHAPES = Object.freeze([
  /ETIMEDOUT/i, /ESOCKETTIMEDOUT/i, /ECONNRESET/i, /ECONNABORTED/i,
  /EPIPE/i, /socket hang up/i, /aborted/i, /network/i,
  /\b(?:502|503|504)\b/,
  /timeout/i,
]);

const RESULTS = Object.freeze(["succeeded", "failed", "unknown"]);

const { createHash } = require("node:crypto");

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

// 这一次发送到底算什么。
//
// 顺序要紧：先看有没有明确的业务错误码，再看传输层症状。反过来的话，一个
// 「token 过期」的响应如果恰好也超时了，会被判成未知——而它其实是确定失败的，
// 重试一次就能修好（换个 token）。
function classifySendOutcome({ ok = false, errorCode = "", errorMessage = "" } = {}) {
  return classifySendOutcomeDetailed({ ok, errorCode, errorMessage }).result;
}

// 带原因的分类。
//
// 第一版只回三个字符串，于是 UNKNOWN_SHAPES 那张表是**白写的**：删掉它，兜底
// 那条「认不出来当未知」照样把传输层错误判成 unknown，行为一模一样。变异测试
// 里那一刀因此是活的——不是测试没写到，是那段代码真的不承重。
//
// 但「我们认出这是 socket 断了」和「我们收到一个从没见过的东西」在运维上是两
// 件事：前者对账一次多半能查清，后者说明有一类错误我们还没理解，该有人去看。
// 所以把原因也回出来，那张表就承重了。
function classifySendOutcomeDetailed({ ok = false, errorCode = "", errorMessage = "" } = {}) {
  if (ok === true) {
    return Object.freeze({ result: "succeeded", reason: "acknowledged" });
  }
  const code = normalizeText(errorCode).toUpperCase();
  if (code && DEFINITE_FAILURE.includes(code)) {
    return Object.freeze({ result: "failed", reason: "declined_by_peer" });
  }
  const text = `${code} ${normalizeText(errorMessage)}`;
  if (UNKNOWN_SHAPES.some((shape) => shape.test(text))) {
    // 认得出来的传输层症状。对账一次多半能查清。
    return Object.freeze({ result: "unknown", reason: "transport_interrupted" });
  }
  if (code || text.trim()) {
    // 认不出来的错误当**未知**，不当失败。
    //
    // 当失败会重试，而重试一个我们没看懂的错误就是在赌它没到达。赌错的代价是
    // 用户收到两条。当未知的代价只是多一次查询——那次查询本来也该做。
    //
    // 但原因要和上面那条分开：这一条意味着有一类错误我们还没理解，该有人去看。
    // 归到同一个原因里的话，它会永远藏在传输层抖动的噪声里。
    return Object.freeze({ result: "unknown", reason: "unrecognized_error" });
  }
  return Object.freeze({ result: "failed", reason: "no_response_no_error" });
}

// 未知结果该怎么处置。
//
// 三条，顺序不能反：
//   一、**不重发**。在查清楚之前，重发就是在赌。
//   二、进 reconcile 队列，由一次查询来定性。
//   三、查不出来时（对面没有查询接口，或者查了还是不知道）——按**已送达**记，
//       但标出来是推定的。
//
// 第三条是有意的，理由是那个不对称：重复发用户觉得系统有毛病，丢消息是他等的
// 事永远没来。但既然两害相权，就必须让它可见——推定送达和真送达在证据里是
// 两种东西，否则「他到底收到没有」这个问题永远答不出来。
function planForUnknown({ attempts = 0, maxReconcileAttempts = 3 } = {}) {
  const tried = Number.isSafeInteger(attempts) && attempts >= 0 ? attempts : 0;
  if (tried >= maxReconcileAttempts) {
    return Object.freeze({
      action: "assume_delivered",
      resend: false,
      reason: "reconcile_exhausted",
      // 推定，不是确认。进证据和 Status 时这一位必须跟着走。
      presumed: true,
    });
  }
  return Object.freeze({
    action: "reconcile",
    resend: false,
    reason: "outcome_unknown",
    presumed: false,
    next_attempt: tried + 1,
  });
}

// 幂等键。
//
// 同一件业务只能有一个键，而这个键必须**跨重启稳定**——随机的话，重启后重放
// 会算出一个新键，于是同一件事被当成两件，做了两次。
//
// 分隔符用 U+0000（写成转义，不是裸字节）：这几段里 target 可能是一整条命令行，含空格。用空格拼的话，
// ("a b", "c") 和 ("a", "b c") 会拼出同一个串，两件不同的事撞成一个键——
// 而撞成一个键意味着第二件永远不会被执行。
// 裸字节会让 grep 和 diff 把整个文件当成二进制——这个错我在这一程里犯了三次。
function idempotencyKeyFor({ channel = "", accountId = "", messageId = "", kind = "", target = "" } = {}) {
  const parts = [channel, accountId, messageId, kind, target].map(normalizeText);
  if (!parts[0] || !parts[2] || !parts[3]) {
    throw new TypeError("channel, messageId and kind are required");
  }
  return `idem_${createHash("sha256")
    .update(parts.join("\u0000")).digest("hex").slice(0, 32)}`;
}

module.exports = {
  DEFINITE_FAILURE,
  RESULTS,
  UNKNOWN_SHAPES,
  classifySendOutcome,
  classifySendOutcomeDetailed,
  idempotencyKeyFor,
  planForUnknown,
};

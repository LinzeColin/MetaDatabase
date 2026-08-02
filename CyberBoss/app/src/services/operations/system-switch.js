"use strict";

// 一键上下线：主人在网页上按一下，整个系统停或者跑。
//
// 这个开关和「降级档位」（degradation-ladder）不是一回事。降级是系统**自己**在
// 资源紧张时按顺序关能力，是自动的、分级的；这个开关是**主人的意志**，只有两态，
// 而且压过一切自动判断——他说停，就停。
//
// 三条不那么显然的设计。
//
// 一、**闸装在唯一的入站锚点上**，不是装在各个功能里。
//
// 「关掉之后不要处理消息」如果靠每个处理函数各自检查一下，那就是行为保证：
// 写的时候都记得，下一个人加一条路径就漏了，而漏了的表现是「明明关了它还在回
// 消息」——主人对这套系统的信任一次就没了。装在 handleIncomingMessage 上，
// 那是真实链路上每条消息的必经之路，绕不过去。
//
// 二、**读不出状态时算「停」，但没有状态文件时算「跑」。**
//
// 这两个不一样，分开是有原因的：
//
//   文件不存在 = 从来没人碰过这个开关 → 跑。一个新装好的系统不该因为主人还没
//   点过按钮就是停的。
//
//   文件存在但读不出来（坏了、权限没了、写到一半断电）= 我们**曾经有过**一个
//   状态，现在丢了。这时候按「跑」处理，等于在主人可能已经说了「停」的情况下
//   继续收消息、继续存数据。而按「停」处理的代价只是他再点一下按钮。
//
// 两害相权：停错了一次点一下就好；跑错了处理掉的消息和存下的数据收不回来。
//
// 三、**主人自己必须能把它打开。**
//
// 关掉之后如果连主人的「上线」也被挡住，唯一的复活方式就是 SSH 上服务器——
// 那这个按钮对一个不会 SSH 的人来说是个**单向陷阱**。所以主人的重新上线口令
// 在闸上有一条明确的例外，而且那条例外只认服务端定的身份，不认文本里自称。

const fs = require("node:fs");
const path = require("node:path");

// 状态只有两个。不做「维护中/只读/半开」——每多一态，就多一组「这一态下这个
// 功能到底能不能用」的问题，而主人要的是一个开关，不是一台调音台。
const STATES = Object.freeze(["online", "offline"]);

// 读不出来时的落点。见上面第二条。
const UNREADABLE_STATE = "offline";

class SystemSwitchError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "SystemSwitchError";
    this.code = code;
    this.detail = detail;
  }
}

function normalizeActor(actor) {
  const text = String(actor ?? "").trim();
  // 只留形状，不留身份：这个文件会进证据和日志，而「谁关的」在单主人系统里
  // 只有两种可能（主人、系统自愈），不需要写 user_id 进去。
  return ["owner", "watchdog", "cli"].includes(text) ? text : "owner";
}

// 当前状态。
//
// 永远返回一个完整的判定，不抛异常——调用方是入站主路径，那里抛异常等于
// 整条链路挂掉，而「开关读不出来」不该有这个后果。
function readSystemSwitch({ file, now = Date.now() } = {}) {
  const target = String(file || "");
  if (!target) {
    throw new SystemSwitchError("SWITCH_FILE_REQUIRED", "file");
  }
  if (!fs.existsSync(target)) {
    // 从来没人碰过 → 跑。
    return Object.freeze({
      state: "online",
      online: true,
      reason: "never_configured",
      changed_at: null,
      changed_by: null,
      evaluated_at: new Date(now).toISOString(),
    });
  }
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(target, "utf8"));
  } catch {
    // 有过状态但读不出来 → 停，并且说得出是为什么。
    return Object.freeze({
      state: UNREADABLE_STATE,
      online: false,
      reason: "state_unreadable",
      changed_at: null,
      changed_by: null,
      evaluated_at: new Date(now).toISOString(),
    });
  }
  const state = STATES.includes(parsed?.state) ? parsed.state : UNREADABLE_STATE;
  return Object.freeze({
    state,
    online: state === "online",
    // 认不出来的状态字符串和读不出来同等对待：都是「我们不知道主人要什么」。
    reason: STATES.includes(parsed?.state) ? "owner_decision" : "state_unrecognized",
    changed_at: typeof parsed?.changed_at === "string" ? parsed.changed_at : null,
    changed_by: typeof parsed?.changed_by === "string" ? parsed.changed_by : null,
    evaluated_at: new Date(now).toISOString(),
  });
}

// 落盘。先写临时文件再改名——直接覆盖的话，写到一半断电会留下一个半截 JSON，
// 而那正好命中上面那条「读不出来就停」，主人第二天发现系统自己停了。
function writeSystemSwitch({ file, online, actor = "owner", now = Date.now() } = {}) {
  const target = String(file || "");
  if (!target) {
    throw new SystemSwitchError("SWITCH_FILE_REQUIRED", "file");
  }
  if (typeof online !== "boolean") {
    throw new SystemSwitchError("SWITCH_STATE_REQUIRED", "online");
  }
  const payload = {
    state: online ? "online" : "offline",
    changed_at: new Date(now).toISOString(),
    changed_by: normalizeActor(actor),
  };
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o750 });
  const temporary = `${target}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(payload, null, 2)}\n`, { mode: 0o640 });
  fs.renameSync(temporary, target);
  return readSystemSwitch({ file: target, now });
}

// 停机期间，主人说的这几句要放行。
//
// 只认这几个词，而且**必须是整句**——不做包含匹配。包含匹配的话，主人一句
// 「我把它下线了吗」里带着「下线」，会被当成一条命令。
const OWNER_RESUME_PHRASES = Object.freeze(["上线", "开机", "恢复运行", "启动系统"]);
const OWNER_HALT_PHRASES = Object.freeze(["下线", "关机", "停止运行", "停机"]);

function matchOwnerSwitchCommand(text) {
  const trimmed = String(text ?? "").trim();
  if (OWNER_RESUME_PHRASES.includes(trimmed)) {
    return "resume";
  }
  if (OWNER_HALT_PHRASES.includes(trimmed)) {
    return "halt";
  }
  return null;
}

// 停机期间回给来信人的那句话。
//
// 说人话，不说错话：不写「维护中，稍后恢复」——我们并不知道主人什么时候会
// 打开它，而一个没有兑现的「稍后」比不说更伤。也不能一声不吭：那样对面以为
// 消息没发出去，会一直重发。
const OFFLINE_NOTICE = "它现在是停着的，主人手动关掉了。等他打开之后你再说话就行。";

// 停机期间只回一次。
//
// 每条都回的话，一个正在连发消息的人会收到一串一模一样的回复——那比不回更烦，
// 而且是我们主动发的，等于停机之后系统反而更吵。
class OfflineNoticeLedger {
  constructor({ ttlMs = 6 * 60 * 60 * 1000 } = {}) {
    this.ttlMs = ttlMs;
    this.sent = new Map();
  }

  shouldNotify(senderKey, now = Date.now()) {
    const key = String(senderKey ?? "");
    if (!key) {
      return false;
    }
    const last = this.sent.get(key);
    if (last !== undefined && now - last < this.ttlMs) {
      return false;
    }
    this.sent.set(key, now);
    return true;
  }

  // 重新上线时清空：下一次停机他应该再收到一次通知，而不是因为上次说过就没了。
  reset() {
    this.sent.clear();
  }
}

module.exports = {
  OFFLINE_NOTICE,
  OWNER_HALT_PHRASES,
  OWNER_RESUME_PHRASES,
  OfflineNoticeLedger,
  STATES,
  SystemSwitchError,
  UNREADABLE_STATE,
  matchOwnerSwitchCommand,
  readSystemSwitch,
  writeSystemSwitch,
};

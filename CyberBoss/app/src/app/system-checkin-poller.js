const crypto = require("crypto");

const { resolveSelectedAccount } = require("../adapters/channel/weixin/account-store");
const { resolveAccountForUser } = require("../adapters/channel/weixin/account-routing");
const { SessionStore } = require("../adapters/runtime/codex/session-store");
const { CheckinConfigStore, resolveDefaultCheckinRange } = require("../core/checkin-config-store");
const { resolvePreferredSenderId, resolvePreferredWorkspaceRoot } = require("../core/default-targets");
const { SystemMessageQueueStore } = require("../core/system-message-queue-store");

const INTERNAL_CHECKIN_TRIGGER_TEMPLATE = "%USER% comes to mind again.";

// options.readProactive 每一轮现读一次主人的设置（开关、频率、静默时段）。
// 现读而不是启动时读一次：主人在后台把它关掉，下一轮就该停，不用重启。
// 没给这个回调时退回原来的文件配置，本地跑 `cyberboss start --checkin` 的行为不变。
async function runSystemCheckinPoller(config, options = {}) {
  const readProactive = typeof options.readProactive === "function" ? options.readProactive : null;
  const nowHour = typeof options.nowHour === "function"
    ? options.nowHour
    : () => Number(new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Shanghai", hour: "2-digit", hour12: false,
    }).format(new Date()));
  const primaryAccount = resolveSelectedAccount(config);
  const queue = new SystemMessageQueueStore({ filePath: config.systemMessageQueueFile });
  const checkinConfigStore = new CheckinConfigStore({ filePath: config.checkinConfigFile });
  const sessionStore = new SessionStore({ filePath: config.sessionsFile });
  const target = resolvePollerTarget({ config, account: primaryAccount, sessionStore, options });
  const defaultRange = resolveDefaultCheckinRange();
  let currentRange = readProactive ? rangeFrom(readProactive()) : checkinConfigStore.getRange(defaultRange);

  console.log(`[cyberboss] checkin poller ready user=${target.senderId} workspace=${target.workspaceRoot}`);
  console.log(`[cyberboss] checkin interval range ${formatRangeMinutes(currentRange)}`);

  while (true) {
    const settings = readProactive ? readProactive() : null;
    currentRange = settings ? rangeFrom(settings) : checkinConfigStore.getRange(defaultRange);
    const delayMs = pickRandomDelayMs(currentRange.minIntervalMs, currentRange.maxIntervalMs);
    const wakeAt = formatLocalTime(Date.now() + delayMs);
    console.log(`[cyberboss] next checkin in ${Math.round(delayMs / 60000)}m at ${wakeAt}`);
    await sleep(delayMs);

    // 关掉了就什么都不做，但循环留着——主人再打开时不需要重启服务。
    const current = readProactive ? readProactive() : null;
    if (current && current.enabled !== true) {
      console.log("[cyberboss] checkin skipped: 主人把主动打招呼关掉了");
      continue;
    }
    // 静默时段。半夜戳人一下不叫陪伴，而且这一条必须在排队之前判——排进去了
    // 就一定会发出去。
    if (current && isQuietNow(current, nowHour())) {
      console.log("[cyberboss] checkin skipped: 静默时段");
      continue;
    }

    // 每一轮现查一次主人挂在哪个号下面，而不是启动时定死：主人重新扫过码
    // 之后账号会换，定死的那个会把主动消息投到一个已经作废的号上。
    const account = resolveAccountForUser(config, target.senderId);

    if (queue.hasPendingForAccount(account.accountId)) {
      console.log("[cyberboss] checkin skipped: pending system message still in queue");
      continue;
    }

    const queued = queue.enqueue({
      id: crypto.randomUUID(),
      accountId: account.accountId,
      senderId: target.senderId,
      workspaceRoot: target.workspaceRoot,
      text: buildCheckinTrigger(config),
      createdAt: new Date().toISOString(),
    });
    console.log(`[cyberboss] checkin queued id=${queued.id}`);
  }
}

function resolvePollerTarget({ config, account, sessionStore, options = {} }) {
  // 主人是谁由上层给（它读 users 表的 role，那是权威来源）。
  //
  // 这一条不能退回"只有一个人在说话就是他"那种猜测：主动打招呼会真的唤醒模型，
  // 一旦目标不是主人，就成了一次非主人的模型调用——R19 冻结的 zero-agent 面
  // 里那是明令禁止的。宁可不发，也不能发错人。
  const ownerSenderId = typeof options.resolveOwnerSenderId === "function"
    ? normalizeText(options.resolveOwnerSenderId())
    : "";
  const senderId = ownerSenderId || resolvePreferredSenderId({
    config,
    accountId: account.accountId,
    explicitUser: process.env.CYBERBOSS_CHECKIN_USER_ID || "",
    sessionStore,
  });
  const workspaceRoot = resolvePreferredWorkspaceRoot({
    config,
    accountId: account.accountId,
    senderId,
    explicitWorkspace: process.env.CYBERBOSS_CHECKIN_WORKSPACE || "",
    sessionStore,
  });

  if (!senderId) {
    throw new Error("Cannot determine the WeChat user for the checkin poller. Set CYBERBOSS_CHECKIN_USER_ID or let the only active user talk to the bot once first.");
  }
  if (!workspaceRoot) {
    throw new Error("Cannot determine the workspace for the checkin poller. Set CYBERBOSS_WORKSPACE_ROOT first.");
  }

  return { senderId, workspaceRoot };
}

function rangeFrom(settings) {
  const minIntervalMs = Math.max(60_000, Math.round(Number(settings?.minMinutes) || 45) * 60_000);
  return {
    minIntervalMs,
    maxIntervalMs: Math.max(minIntervalMs, Math.round(Number(settings?.maxMinutes) || 240) * 60_000),
  };
}

// 和 persona-store 的 inQuietHours 同一套语义；这里不 require 它，是为了让这个
// 轮询器保持"只依赖 config 和回调"的形状，方便单独测。
function isQuietNow(settings, hour) {
  const start = Number(settings?.quietStart);
  const end = Number(settings?.quietEnd);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start === end) {
    return false;
  }
  return start < end ? hour >= start && hour < end : hour >= start || hour < end;
}

function pickRandomDelayMs(minIntervalMs, maxIntervalMs) {
  if (maxIntervalMs <= minIntervalMs) {
    return minIntervalMs;
  }
  return minIntervalMs + Math.floor(Math.random() * (maxIntervalMs - minIntervalMs + 1));
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatLocalTime(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value || "");
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date).replace(/\//g, "-");
}

function formatRangeMinutes(range) {
  return `${Math.round(range.minIntervalMs / 60000)}m-${Math.round(range.maxIntervalMs / 60000)}m`;
}

function buildCheckinTrigger(config) {
  const userName = normalizeText(config?.userName) || "the user";
  return INTERNAL_CHECKIN_TRIGGER_TEMPLATE.replace("%USER%", userName);
}

module.exports = { isQuietNow, rangeFrom, runSystemCheckinPoller };

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

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
  const nextCheckinStore = options.nextCheckinStore
    || createNextCheckinStore(path.join(path.dirname(config.checkinConfigFile), "next-checkin.json"));
  let currentRange = readProactive ? rangeFrom(readProactive()) : checkinConfigStore.getRange(defaultRange);

  console.log(`[cyberboss] checkin poller ready user=${target.senderId} workspace=${target.workspaceRoot}`);
  console.log(`[cyberboss] checkin interval range ${formatRangeMinutes(currentRange)}`);

  while (true) {
    const settings = readProactive ? readProactive() : null;
    currentRange = settings ? rangeFrom(settings) : checkinConfigStore.getRange(defaultRange);

    // 下一次什么时候，**存到盘上**。
    //
    // 这是「设了 1-4 小时，过了 4 小时它还没来」的真正原因：以前这个时刻只活在
    // 内存里，进程一重启就重新掷一次骰子。今天部署了七八次，等于把倒计时按了
    // 七八次重置——它一次都轮不到。这和部署频率无关：崩一次、重启一次、升级
    // 一次，都会把它清零。
    //
    // 存下来之后，重启就是接着等；关机期间早就该到点的，开机稍等一下就补发。
    let nextAtMs = nextCheckinStore.read();
    if (!nextAtMs || nextAtMs > Date.now() + currentRange.maxIntervalMs) {
      // 没存过，或者存的时刻比现在设置的最大间隔还远（主人把间隔调短了），
      // 重新掷一次。
      nextAtMs = Date.now() + pickRandomDelayMs(currentRange.minIntervalMs, currentRange.maxIntervalMs);
      nextCheckinStore.write(nextAtMs);
    }
    const waitMs = nextAtMs - Date.now();
    if (waitMs > 0) {
      console.log(
        `[cyberboss] 下一次主动打招呼：${formatLocalTime(nextAtMs)}`
        + `（还有 ${Math.round(waitMs / 60000)} 分钟）`,
      );
      // 分段睡，每段之间回头看一眼设置。
      //
      // 一觉睡到点的话，中途改设置是不生效的：主人把间隔从 4 小时改成 5 分钟，
      // 而轮询器还躺在两小时后的那个闹钟上——他等了 5 分钟什么都没等到，只能
      // 以为又坏了。改设置必须当场算数，这是「设了就该生效」最起码的意思。
      const SLICE_MS = 30_000;
      while (Date.now() < nextAtMs) {
        await sleep(Math.min(SLICE_MS, nextAtMs - Date.now()));
        const now = readProactive ? readProactive() : null;
        if (!now) {
          continue;
        }
        const range = rangeFrom(now);
        // 间隔被调短了，原来那个时刻已经超出新的最大间隔——立刻往前挪。
        if (nextAtMs > Date.now() + range.maxIntervalMs) {
          nextAtMs = Date.now() + pickRandomDelayMs(range.minIntervalMs, range.maxIntervalMs);
          nextCheckinStore.write(nextAtMs);
          console.log(
            `[cyberboss] 间隔改短了，下一次提前到 ${formatLocalTime(nextAtMs)}`,
          );
        }
      }
    } else {
      // 到点的时候机器是关着的。缓一分钟再发，别在开机那一秒就戳人。
      console.log(
        `[cyberboss] 主动打招呼在停机期间到点了（${formatLocalTime(nextAtMs)}），一分钟后补上`,
      );
      await sleep(60_000);
    }
    // 这一轮用掉了，先清掉，免得下面任何一个 continue 让它卡在同一个时刻上。
    nextCheckinStore.clear();

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

// 「下一次什么时候」就存这一个数字。不进数据库：它不是任何人的数据，只是一个
// 时刻；进程崩了、机器重启了，它得还在。
function createNextCheckinStore(filePath) {
  return {
    read() {
      try {
        const value = Number(JSON.parse(fs.readFileSync(filePath, "utf8")).nextAtMs);
        return Number.isFinite(value) && value > 0 ? value : 0;
      } catch {
        return 0;
      }
    },
    write(nextAtMs) {
      try {
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, JSON.stringify({ nextAtMs }), "utf8");
      } catch {
        // 写不进去就退回老行为（每次重新掷）。不该因为这个把轮询器搞崩。
      }
    },
    clear() {
      try {
        fs.rmSync(filePath, { force: true });
      } catch {
        // 同上。
      }
    },
  };
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

module.exports = { createNextCheckinStore, isQuietNow, rangeFrom, runSystemCheckinPoller };

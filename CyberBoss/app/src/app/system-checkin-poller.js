const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { resolveSelectedAccount } = require("../adapters/channel/weixin/account-store");
const { BEIJING_ZONE, formatInZone, hourInZone } = require("../services/time/canonical-time");
const { resolveAccountForUser } = require("../adapters/channel/weixin/account-routing");
const { SessionStore } = require("../adapters/runtime/codex/session-store");
const { CheckinConfigStore, resolveDefaultCheckinRange } = require("../core/checkin-config-store");
const { resolvePreferredSenderId, resolvePreferredWorkspaceRoot } = require("../core/default-targets");
const { SystemMessageQueueStore } = require("../core/system-message-queue-store");

const INTERNAL_CHECKIN_TRIGGER_TEMPLATE = "%USER% comes to mind again.";

// options.listTargets 每一轮现读一次**所有人**的设置。
//
// 「每个用户的设置应该都是个人的，比如主动找我这个权限⋯应该是在用户下每个人
// 都能单独保存。」所以这里不再只有主人一个目标：谁开了、多久一次、几点到几点
// 不打扰，都是他自己那一份。
//
// 现读而不是启动时读一次：在后台把它关掉，下一轮就该停，不用重启。
// 没给这个回调时退回「只有主人一个目标」，本地跑 `cyberboss start --checkin`
// 的行为不变。
async function runSystemCheckinPoller(config, options = {}) {
  const readProactive = typeof options.readProactive === "function" ? options.readProactive : null;
  // 安静时段判的是**这个人当地**的几点（CB9-230 / AC-011）。
  //
  // 别用 Date#getHours——那读的是宿主机时区，机器在 UTC 上跑的时候「23 点静默」
  // 会在北京时间早上 7 点生效。
  // 也别一律用北京时间：一个在纽约的人设了「23 点到 8 点别打扰」，按北京时间
  // 判的话，安静时段落在他那边的上午十点到晚上七点——他整个白天收不到消息，
  // 而半夜正好被戳醒。
  const nowHour = typeof options.nowHour === "function"
    ? options.nowHour
    : (zone) => hourInZone(new Date(), zone || BEIJING_ZONE);
  // 目标本人的时区。没注入就退回北京时间，和以前的行为一致。
  const readTimezone = typeof options.readTimezone === "function"
    ? options.readTimezone
    : () => BEIJING_ZONE;
  const primaryAccount = resolveSelectedAccount(config);
  const queue = new SystemMessageQueueStore({ filePath: config.systemMessageQueueFile });
  const checkinConfigStore = new CheckinConfigStore({ filePath: config.checkinConfigFile });
  const sessionStore = new SessionStore({ filePath: config.sessionsFile });
  const ownerTarget = resolvePollerTarget({ config, account: primaryAccount, sessionStore, options });
  const defaultWorkspaceRoot = ownerTarget.workspaceRoot;
  const defaultRange = resolveDefaultCheckinRange();
  const nextCheckinStore = options.nextCheckinStore
    || createNextCheckinStore(path.join(path.dirname(config.checkinConfigFile), "next-checkin.json"));

  // 没注入 listTargets 就退回单目标（主人），行为和以前一样。
  const listTargets = typeof options.listTargets === "function"
    ? () => {
      const raw = options.listTargets();
      return (Array.isArray(raw) ? raw : [])
        .map((entry) => ({
          senderId: normalizeText(entry?.senderId),
          settings: entry?.settings || null,
          workspaceRoot: normalizeText(entry?.workspaceRoot) || defaultWorkspaceRoot,
        }))
        .filter((entry) => entry.senderId);
    }
    : () => [{
      senderId: ownerTarget.senderId,
      settings: readProactive ? readProactive() : checkinConfigStore.getRange(defaultRange),
      workspaceRoot: ownerTarget.workspaceRoot,
    }];

  console.log(`[cyberboss] checkin poller ready workspace=${defaultWorkspaceRoot}`);

  // 每 30 秒扫一遍所有人，谁到点了就给谁排一条。
  //
  // 原来是「一个目标 + 一觉睡到点」。改成扫描式，是因为要支持每人一份设置：
  // 五个人五个不同的间隔，用一个 sleep 排不出来，而每人一个定时器又会在进程
  // 重启后全部丢失。扫描 + 盘上的时刻表，重启之后接着等就行。
  //
  // 三十秒的代价是每分钟两次空转的比较，换来的是「主人在后台把间隔从四小时
  // 改成十分钟」当场就算数。
  const SLICE_MS = 30_000;
  while (true) {
    const targets = listTargets();
    const schedule = nextCheckinStore.readAll();
    const now = Date.now();

    for (const target of targets) {
      const range = rangeFrom(target.settings);
      let dueAt = Number(schedule[target.senderId]) || 0;

      // 没排过，或者排的时刻比现在的最大间隔还远（他把间隔调短了），重掷。
      if (!dueAt || dueAt > now + range.maxIntervalMs) {
        dueAt = now + pickRandomDelayMs(range.minIntervalMs, range.maxIntervalMs);
        nextCheckinStore.write(target.senderId, dueAt);
        continue;
      }
      if (dueAt > now) {
        continue;
      }

      // 到点了。先把下一次排上，再决定这一次要不要真的发——这样中间任何一条
      // 分支 continue 掉，都不会让它卡在同一个时刻上反复触发。
      nextCheckinStore.write(
        target.senderId,
        now + pickRandomDelayMs(range.minIntervalMs, range.maxIntervalMs),
      );

      if (target.settings?.enabled !== true) {
        continue;
      }
      // 静默时段。半夜戳人一下不叫陪伴，而且这一条必须在排队之前判——排进去了
      // 就一定会发出去。
      if (isQuietNow(target.settings, nowHour(readTimezone(target.senderId)))) {
        continue;
      }

      // 每一轮现查一次这个人挂在哪个号下面，而不是启动时定死：他重新扫过码
      // 之后账号会换，定死的那个会把主动消息投到一个已经作废的号上。
      const account = resolveAccountForUser(config, target.senderId);
      if (queue.hasPendingForAccount(account.accountId)) {
        continue;
      }
      const queued = queue.enqueue({
        id: crypto.randomUUID(),
        accountId: account.accountId,
        senderId: target.senderId,
        workspaceRoot: target.workspaceRoot || defaultWorkspaceRoot,
        text: buildCheckinTrigger(config),
        createdAt: new Date().toISOString(),
      });
      // 带上是给谁排的。只有 id 的时候，「boss 是不是只找主人」这个问题得靠翻
      // next-checkin.json 再解密 bot_initiated_messages 才答得出来。截断到 10 位：
      // 够区分是谁，又不至于把整个微信号写进普通日志。
      console.log(`[cyberboss] checkin queued id=${queued.id} to=${target.senderId.slice(0, 10)}…`);
    }

    await sleep(SLICE_MS);
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
  const readAll = () => {
    try {
      const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
      // 老格式是 { nextAtMs }，只有主人一个人。升级之后照样读得出来，
      // 挂到 __owner__ 名下——不然升级那一刻所有人的倒计时会一起清零。
      if (parsed && typeof parsed.nextAtMs === "number") {
        return { __owner__: parsed.nextAtMs };
      }
      const targets = parsed?.targets;
      return targets && typeof targets === "object" ? targets : {};
    } catch {
      return {};
    }
  };
  const writeAll = (targets) => {
    try {
      fs.mkdirSync(path.dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, JSON.stringify({ targets }), "utf8");
    } catch {
      // 写不进去就退回老行为（每次重新掷）。不该因为这个把轮询器搞崩。
    }
  };
  return {
    readAll,
    read(senderId) {
      const value = Number(readAll()[senderId]);
      return Number.isFinite(value) && value > 0 ? value : 0;
    },
    write(senderId, nextAtMs) {
      const targets = readAll();
      targets[senderId] = nextAtMs;
      writeAll(targets);
    },
    forget(senderId) {
      const targets = readAll();
      delete targets[senderId];
      writeAll(targets);
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
  return formatInZone(date, BEIJING_ZONE, { seconds: true });
}

function formatRangeMinutes(range) {
  return `${Math.round(range.minIntervalMs / 60000)}m-${Math.round(range.maxIntervalMs / 60000)}m`;
}

function buildCheckinTrigger(config) {
  const userName = normalizeText(config?.userName) || "the user";
  return INTERNAL_CHECKIN_TRIGGER_TEMPLATE.replace("%USER%", userName);
}

module.exports = { createNextCheckinStore, isQuietNow, rangeFrom, runSystemCheckinPoller };

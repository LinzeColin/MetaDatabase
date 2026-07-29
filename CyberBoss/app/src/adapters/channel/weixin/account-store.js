const fs = require("fs");
const path = require("path");

function normalizeAccountId(raw) {
  return String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function ensureAccountsDir(config) {
  fs.mkdirSync(config.accountsDir, { recursive: true });
}

function resolveAccountPath(config, accountId) {
  return path.join(config.accountsDir, `${normalizeAccountId(accountId)}.json`);
}

function deleteWeixinAccount(config, accountId) {
  const normalized = normalizeAccountId(accountId);
  if (!normalized) {
    return false;
  }
  try {
    const filePath = resolveAccountPath(config, normalized);
    if (!fs.existsSync(filePath)) {
      return false;
    }
    fs.unlinkSync(filePath);
    return true;
  } catch {
    return false;
  }
}

function saveWeixinAccount(config, rawAccountId, update) {
  ensureAccountsDir(config);
  const accountId = normalizeAccountId(rawAccountId);
  const filePath = resolveAccountPath(config, accountId);
  const existing = loadWeixinAccount(config, accountId) || {};
  const next = {
    accountId,
    rawAccountId: String(rawAccountId || "").trim() || existing.rawAccountId || "",
    token: typeof update.token === "string" && update.token.trim() ? update.token.trim() : existing.token || "",
    baseUrl: typeof update.baseUrl === "string" && update.baseUrl.trim() ? update.baseUrl.trim() : existing.baseUrl || config.weixinBaseUrl,
    userId: typeof update.userId === "string" ? update.userId.trim() : existing.userId || "",
    savedAt: new Date().toISOString(),
  };
  fs.writeFileSync(filePath, JSON.stringify(next, null, 2), "utf8");
  try {
    fs.chmodSync(filePath, 0o600);
  } catch {
    // best effort
  }
  return next;
}

function loadWeixinAccount(config, accountId) {
  const normalized = normalizeAccountId(accountId);
  if (!normalized) {
    return null;
  }
  try {
    const raw = fs.readFileSync(resolveAccountPath(config, normalized), "utf8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return {
      accountId: normalized,
      rawAccountId: typeof parsed.rawAccountId === "string" ? parsed.rawAccountId : "",
      token: typeof parsed.token === "string" ? parsed.token : "",
      baseUrl: typeof parsed.baseUrl === "string" && parsed.baseUrl.trim() ? parsed.baseUrl.trim() : config.weixinBaseUrl,
      userId: typeof parsed.userId === "string" ? parsed.userId : "",
      savedAt: typeof parsed.savedAt === "string" ? parsed.savedAt : "",
    };
  } catch {
    return null;
  }
}

function listWeixinAccounts(config) {
  ensureAccountsDir(config);
  const files = fs.readdirSync(config.accountsDir, { withFileTypes: true });
  return files
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json") && !entry.name.endsWith(".context-tokens.json"))
    .map((entry) => loadWeixinAccount(config, entry.name.slice(0, -5)))
    .filter(Boolean)
    .sort((left, right) => String(right.savedAt || "").localeCompare(String(left.savedAt || "")));
}

// 能真正收发的号：存过 token 的那些。
//
// CYBERBOSS_ACCOUNT_ID 还是钉死单个号——本机调试和「只想跑一个号」的装法靠它。
// 没钉的时候返回全部：每个人扫码都会生成一个属于他自己的 bot 号，桥接循环要把
// 它们全部轮询到，少轮一个就等于那个人发的话永远没人收。
function listActiveAccounts(config) {
  const pinned = String(config?.accountId || "").trim();
  if (pinned) {
    const account = loadWeixinAccount(config, pinned);
    if (!account) {
      throw new Error(`WeChat account not found: ${pinned}`);
    }
    if (!account.token) {
      throw new Error(`WeChat account is missing a token: ${account.accountId}. Run login again.`);
    }
    return [account];
  }
  return listWeixinAccounts(config).filter((account) => account.token);
}

// 主人的号 = 账号自己的微信身份出现在 ownerSenderIds 里的那一个。
//
// 按身份认，不按时间认。主人重新扫一次码，他的 savedAt 就变成最新的，
// 而 cleanupStaleAccountsForUserId 会把他的旧号删掉——这时候「最早保存的那个」
// 指向的是某个陌生人，主人的提醒和主动消息会发到别人微信里。
function pickPrimaryAccount(config, accounts) {
  const ownerIds = new Set(
    (Array.isArray(config?.ownerSenderIds) ? config.ownerSenderIds : [])
      .map((value) => String(value || "").trim())
      .filter(Boolean),
  );
  const owned = accounts.find(
    (account) => ownerIds.has(String(account.userId || "").trim()),
  );
  if (owned) {
    return owned;
  }
  // 还没认出主人的时候退回最早保存的那个：第一个扫码的人就是主人，
  // 和「第一个发消息的人是主人」是同一条规则。
  return accounts
    .slice()
    .sort((left, right) => (
      String(left.savedAt || "").localeCompare(String(right.savedAt || ""))
      || left.accountId.localeCompare(right.accountId)
    ))[0];
}

function resolveSelectedAccount(config) {
  const accounts = listActiveAccounts(config);
  if (accounts.length) {
    return pickPrimaryAccount(config, accounts);
  }
  // 走到这里只有两种可能：一个号都没存，或者存了但都缺 token。
  // 两句话不一样——一句是「去登录」，一句是「重新登录」。
  const saved = listWeixinAccounts(config);
  if (saved.length) {
    throw new Error(`WeChat account is missing a token: ${saved[0].accountId}. Run login again.`);
  }
  throw new Error("No saved WeChat account was found. Run `npm run login` first.");
}

module.exports = {
  deleteWeixinAccount,
  listActiveAccounts,
  listWeixinAccounts,
  loadWeixinAccount,
  normalizeAccountId,
  pickPrimaryAccount,
  resolveAccountPath,
  resolveSelectedAccount,
  saveWeixinAccount,
};

const crypto = require("crypto");
const {
  listActiveAccounts,
  listWeixinAccounts,
  pickPrimaryAccount,
  resolveSelectedAccount,
} = require("./account-store");
const { loadPersistedContextTokens, persistContextToken } = require("./context-token-store");
const { runLoginFlow } = require("./login");
const { getConfig, sendTyping } = require("./api");
const { getUpdates, sendText } = require("./api");
const { createInboundFilter, isSenderAllowed } = require("./message-utils");
const { sendWeixinMediaFile } = require("./media-send");
const {
  commitSyncBuffer,
  loadSyncBuffer,
  saveSyncBuffer,
} = require("./sync-buffer-store");
const { loadWeixinConfig, saveWeixinConfig, DEFAULT_MIN_WEIXIN_CHUNK } = require("./config-store");

const LONG_POLL_TIMEOUT_MS = 35_000;
const MAX_WEIXIN_CHUNK = 3800;
const SEND_MESSAGE_CHUNK_INTERVAL_MS = 350;
const WEIXIN_MAX_DELIVERY_MESSAGES = 10;

function createWeixinChannelAdapter(config) {
  // 一个号一份状态。以前这里是两个闭包变量（selectedAccount / contextTokenCache），
  // 于是整个进程只认一个微信号——第二个人扫码之后，resolveSelectedAccount 直接抛
  // "Multiple WeChat accounts were detected"，服务连启动都启动不了。
  const accountStates = new Map();
  let primaryAccountId = "";
  const inboundFilter = createInboundFilter();
  let minWeixinChunk = loadWeixinConfig(config).minChunkChars;

  function stateFor(account) {
    const existing = accountStates.get(account.accountId);
    if (existing) {
      // 重新登录会换 token，用盘上最新的那份覆盖。
      existing.account = account;
      return existing;
    }
    const created = {
      account,
      contextTokenCache: loadPersistedContextTokens(config, account.accountId),
    };
    accountStates.set(account.accountId, created);
    return created;
  }

  // 每次调用都重新读一次盘。有人刚扫完码，下一轮桥接循环就能轮询到他，
  // 不需要重启服务；反过来，号被删掉之后它的状态也会被丢掉。
  function refreshAccounts() {
    const accounts = listActiveAccounts(config);
    const live = new Set(accounts.map((account) => account.accountId));
    for (const account of accounts) {
      stateFor(account);
    }
    for (const accountId of Array.from(accountStates.keys())) {
      if (!live.has(accountId)) {
        accountStates.delete(accountId);
      }
    }
    const primary = accounts.length ? pickPrimaryAccount(config, accounts) : null;
    primaryAccountId = primary ? primary.accountId : "";
    return accounts;
  }

  // 主号：主人自己那个。日志、账号绑定、找不到归属时的兜底都用它。
  function ensureAccount() {
    const known = primaryAccountId ? accountStates.get(primaryAccountId) : null;
    if (known) {
      return known.account;
    }
    const account = resolveSelectedAccount(config);
    stateFor(account);
    primaryAccountId = account.accountId;
    return account;
  }

  function ensureAnyAccountsLoaded() {
    if (!accountStates.size) {
      refreshAccounts();
    }
    return accountStates;
  }

  // 这个人挂在哪个号下面。context_token 是「某个号 ↔ 某个人」之间的凭据，
  // 拿错号发必然被拒，所以发信之前必须先定位。
  function bindingFor(userId, accountIdHint = "") {
    const normalizedUserId = typeof userId === "string" ? userId.trim() : "";
    if (!normalizedUserId) {
      return { account: ensureAccount(), token: "" };
    }
    ensureAnyAccountsLoaded();
    // 调用方明说了从哪个号来，就用那个号——它比任何反查都准。
    const hinted = String(accountIdHint || "").trim();
    if (hinted) {
      const state = accountStates.get(hinted) || (refreshAccounts(), accountStates.get(hinted));
      if (state?.account?.token) {
        return { account: state.account, token: state.contextTokenCache[normalizedUserId] || "" };
      }
    }
    const search = () => {
      const primary = primaryAccountId ? accountStates.get(primaryAccountId) : null;
      if (primary?.contextTokenCache[normalizedUserId]) {
        return { account: primary.account, token: primary.contextTokenCache[normalizedUserId] };
      }
      for (const state of accountStates.values()) {
        const token = state.contextTokenCache[normalizedUserId];
        if (token) {
          return { account: state.account, token };
        }
      }
      return null;
    };
    const found = search();
    if (found) {
      return found;
    }
    // 内存里没有就再读一次盘：刚扫码进来的人，他的 token 可能是这一轮才落的。
    refreshAccounts();
    return search() || { account: ensureAccount(), token: "" };
  }

  function rememberContextToken(userId, contextToken, accountId = "") {
    const normalizedUserId = typeof userId === "string" ? userId.trim() : "";
    const normalizedToken = typeof contextToken === "string" ? contextToken.trim() : "";
    if (!normalizedUserId || !normalizedToken) {
      return "";
    }
    // accountId 是这条消息**是从哪个号收到的**。这是唯一可靠的归属来源：
    // 不传的时候只能落到主号上，那会把别人的 token 记到主人名下，之后回信必错。
    ensureAnyAccountsLoaded();
    const targetId = String(accountId || "").trim() || ensureAccount().accountId;
    const tokens = persistContextToken(config, targetId, normalizedUserId, normalizedToken);
    const state = accountStates.get(targetId);
    if (state) {
      state.contextTokenCache = tokens;
    }
    // 盘上没有这个号时**不建占位**。建了就等于往路由表里塞一个 token 为空的号，
    // 之后给这个人发消息会带着空 Authorization 出去，微信直接拒——这比记不住
    // 严重得多。token 已经落盘了，等那个号真出现时自然会被读进来。
    return normalizedToken;
  }

  function sendTextChunks({ userId, text, contextToken = "", preserveBlock = false, accountId = "" }) {
    const binding = bindingFor(userId, accountId);
    const account = binding.account;
    const resolvedToken = String(contextToken || "").trim() || binding.token;
    if (!resolvedToken) {
      throw new Error(`Missing context_token. Cannot reply to user ${userId}.`);
    }
    const content = String(text || "");
    if (!content.trim()) {
      return Promise.resolve();
    }
    const normalizedContent = normalizeWeixinReplyText(content);
    const textChunks = preserveBlock ? null : chunkReplyTextForWeixin(normalizedContent, minWeixinChunk);
    const sendChunks = preserveBlock
      ? splitUtf8(normalizedContent || "Completed.", MAX_WEIXIN_CHUNK)
      : packChunksForWeixinDelivery(
        textChunks?.length ? textChunks : ["Completed."],
        WEIXIN_MAX_DELIVERY_MESSAGES,
        MAX_WEIXIN_CHUNK
      );
    return sendChunks.reduce((promise, chunk, index) => promise
      .then(() => {
        const deliveryChunk = finalizeWeixinDeliveryChunk(chunk) || "Completed.";
        return sendText({
          baseUrl: account.baseUrl,
          token: account.token,
          toUserId: userId,
          text: deliveryChunk,
          contextToken: resolvedToken,
          clientId: `cb-${crypto.randomUUID()}`,
        });
      })
      .then(() => {
        if (index < sendChunks.length - 1) {
          return sleep(SEND_MESSAGE_CHUNK_INTERVAL_MS);
        }
        return null;
      }), Promise.resolve());
  }

  async function fetchUpdatesFor(account, { syncBuffer = "", timeoutMs = LONG_POLL_TIMEOUT_MS } = {}) {
    const response = await getUpdates({
      baseUrl: account.baseUrl,
      token: account.token,
      getUpdatesBuf: syncBuffer,
      timeoutMs,
    });
    const newBuf = typeof response?.get_updates_buf === "string" ? response.get_updates_buf.trim() : "";
    const messages = Array.isArray(response?.msgs) ? response.msgs : [];
    return Object.freeze({
      response,
      messages,
      committedCursor: syncBuffer,
      candidateCursor: newBuf || syncBuffer,
      accountId: account.accountId,
    });
  }

  // 单个号的视图。形状和整个适配器一样，但每个方法都钉死在这一个号上——
  // 桥接循环给每个号建一个 DurableInboxCoordinator，各自用各自的游标、
  // 各自的 context_token、各自的 token 拉更新。
  //
  // 游标必须分开：两个号的 get_updates_buf 是两条独立的序列，混用一条会让
  // 其中一个号的消息被当成「已经收过了」直接跳过。
  function accountView(accountId) {
    const normalizedId = String(accountId || "").trim();
    const resolve = () => {
      const state = accountStates.get(normalizedId)
        || (refreshAccounts(), accountStates.get(normalizedId));
      if (!state) {
        throw new Error(`WeChat account not found: ${normalizedId}`);
      }
      return state;
    };
    return {
      accountId: normalizedId,
      resolveAccount() {
        return resolve().account;
      },
      getKnownContextTokens() {
        return { ...resolve().contextTokenCache };
      },
      loadSyncBuffer() {
        return loadSyncBuffer(config, normalizedId);
      },
      saveSyncBuffer(buffer) {
        return saveSyncBuffer(config, normalizedId, buffer);
      },
      commitCandidateCursor({ expectedCursor = "", candidateCursor = "" } = {}) {
        return commitSyncBuffer(config, normalizedId, {
          expected: expectedCursor,
          candidate: candidateCursor,
        });
      },
      normalizeIncomingMessage(message, options = {}) {
        return inboundFilter.normalize(message, config, normalizedId, options);
      },
      rememberContextToken(userId, contextToken) {
        return rememberContextToken(userId, contextToken, normalizedId);
      },
      rememberBaselineStagingContextTokens(messages = []) {
        rememberBaselineStagingContextTokens(messages, normalizedId);
      },
      async fetchUpdates(options = {}) {
        return fetchUpdatesFor(resolve().account, options);
      },
      async getUpdates(options = {}) {
        return fetchUpdatesFor(resolve().account, options);
      },
    };
  }

  function rememberBaselineStagingContextTokens(messages = [], accountId = "") {
    for (const message of messages) {
      const userId = typeof message?.from_user_id === "string"
        ? message.from_user_id.trim()
        : "";
      const contextToken = typeof message?.context_token === "string"
        ? message.context_token.trim()
        : "";
      if (userId && contextToken && isSenderAllowed(config, userId)) {
        rememberContextToken(userId, contextToken, accountId);
      }
    }
  }

  return {
    describe() {
      return {
        id: "weixin",
        kind: "channel",
        stateDir: config.stateDir,
        baseUrl: config.weixinBaseUrl,
        accountsDir: config.accountsDir,
        syncBufferDir: config.syncBufferDir,
      };
    },
    async login() {
      await runLoginFlow(config);
    },
    printAccounts() {
      const accounts = listWeixinAccounts(config);
      if (!accounts.length) {
        console.log("No saved WeChat account found. Run `npm run login` first.");
        return;
      }
      console.log("Saved accounts:");
      for (const account of accounts) {
        console.log(`- ${account.accountId}`);
        console.log(`  userId: ${account.userId || "(unknown)"}`);
        console.log(`  baseUrl: ${account.baseUrl || config.weixinBaseUrl}`);
        console.log(`  savedAt: ${account.savedAt || "(unknown)"}`);
      }
    },
    resolveAccount() {
      return ensureAccount();
    },
    // 现在盘上所有能收发的号。每一轮桥接循环调一次，所以刚扫完码的人
    // 下一轮就被轮询到了。
    listAccounts() {
      return refreshAccounts();
    },
    forAccount: accountView,
    getKnownContextTokens() {
      // 全部号合起来的一份。启动日志和「这个人能不能收到主动消息」都看它，
      // 只报主号的数字会让第二个号下面的人看起来像不存在。
      ensureAnyAccountsLoaded();
      const merged = {};
      for (const state of accountStates.values()) {
        Object.assign(merged, state.contextTokenCache);
      }
      return merged;
    },
    loadSyncBuffer() {
      const account = ensureAccount();
      return loadSyncBuffer(config, account.accountId);
    },
    saveSyncBuffer(buffer) {
      const account = ensureAccount();
      return saveSyncBuffer(config, account.accountId, buffer);
    },
    rememberContextToken,
    rememberBaselineStagingContextTokens,
    async fetchUpdates(options = {}) {
      return fetchUpdatesFor(ensureAccount(), options);
    },
    async getUpdates(options = {}) {
      return fetchUpdatesFor(ensureAccount(), options);
    },
    commitCandidateCursor({
      expectedCursor = "",
      candidateCursor = "",
    } = {}) {
      const account = ensureAccount();
      return commitSyncBuffer(config, account.accountId, {
        expected: expectedCursor,
        candidate: candidateCursor,
      });
    },
    normalizeIncomingMessage(message, options = {}) {
      const account = ensureAccount();
      return inboundFilter.normalize(message, config, account.accountId, options);
    },
    async sendText({ userId, text, contextToken = "", preserveBlock = false, accountId = "" }) {
      await sendTextChunks({ userId, text, contextToken, preserveBlock, accountId });
    },
    async sendTextChunk({
      userId,
      text,
      contextToken = "",
      clientId = "",
      accountId = "",
    }) {
      const binding = bindingFor(userId, accountId);
      const account = binding.account;
      const resolvedToken = String(contextToken || "").trim() || binding.token;
      const stableClientId = String(clientId || "").trim();
      const outgoingText = String(text || "");
      if (!resolvedToken) {
        const error = new Error("Missing context_token for durable outbox.");
        error.code = "WEIXIN_CONTEXT_REQUIRED";
        error.outcomeKnown = true;
        throw error;
      }
      if (!/^cb-outbox-[0-9a-f]{32}$/.test(stableClientId)) {
        const error = new Error("Durable outbox requires a stable client id.");
        error.code = "WEIXIN_STABLE_CLIENT_ID_REQUIRED";
        error.outcomeKnown = true;
        throw error;
      }
      if (
        !outgoingText.trim()
        || Array.from(outgoingText).length > MAX_WEIXIN_CHUNK
      ) {
        const error = new Error("Durable outbox chunk is invalid.");
        error.code = "WEIXIN_OUTBOX_CHUNK_INVALID";
        error.outcomeKnown = true;
        throw error;
      }
      return sendText({
        baseUrl: account.baseUrl,
        token: account.token,
        toUserId: userId,
        text: outgoingText,
        contextToken: resolvedToken,
        clientId: stableClientId,
      });
    },
    async sendTyping({ userId, status = 1, contextToken = "", accountId = "" }) {
      const binding = bindingFor(userId, accountId);
      const account = binding.account;
      const resolvedToken = String(contextToken || "").trim() || binding.token;
      if (!resolvedToken) {
        return;
      }
      const configResponse = await getConfig({
        baseUrl: account.baseUrl,
        token: account.token,
        ilinkUserId: userId,
        contextToken: resolvedToken,
      }).catch(() => null);
      const typingTicket = typeof configResponse?.typing_ticket === "string"
        ? configResponse.typing_ticket.trim()
        : "";
      if (!typingTicket) {
        return;
      }
      await sendTyping({
        baseUrl: account.baseUrl,
        token: account.token,
        body: {
          ilink_user_id: userId,
          typing_ticket: typingTicket,
          status,
        },
      });
    },
    async sendFile({ userId, filePath, contextToken = "", accountId = "" }) {
      const binding = bindingFor(userId, accountId);
      const account = binding.account;
      const resolvedToken = String(contextToken || "").trim() || binding.token;
      if (!resolvedToken) {
        throw new Error(`Missing context_token. Cannot send a file to user ${userId}.`);
      }
      return sendWeixinMediaFile({
        filePath,
        to: userId,
        contextToken: resolvedToken,
        baseUrl: account.baseUrl,
        token: account.token,
        cdnBaseUrl: config.weixinCdnBaseUrl,
      });
    },
    setMinChunkChars(value) {
      const parsed = Number.parseInt(String(value), 10);
      if (Number.isFinite(parsed) && parsed >= 1 && parsed <= MAX_WEIXIN_CHUNK) {
        minWeixinChunk = parsed;
        saveWeixinConfig(config, { minChunkChars: minWeixinChunk });
      }
      return minWeixinChunk;
    },
    getMinChunkChars() {
      return minWeixinChunk;
    },
  };
}

function splitUtf8(text, maxRunes) {
  const runes = Array.from(String(text || ""));
  if (!runes.length || runes.length <= maxRunes) {
    return [String(text || "")];
  }
  const chunks = [];
  while (runes.length) {
    chunks.push(runes.splice(0, maxRunes).join(""));
  }
  return chunks;
}

function normalizeWeixinReplyText(text) {
  return trimOuterBlankLines(normalizeLineEndings(text));
}

function finalizeWeixinDeliveryChunk(text) {
  const normalized = normalizeLineEndings(text);
  if (!normalized.trim()) {
    return "";
  }
  return trimOuterBlankLines(stripChunkTailChineseFullStops(normalized));
}

function stripChunkTailChineseFullStops(text) {
  return String(text || "").replace(/(^|[^。])。(?=(?:\s*["'"”’）)\]\u300d\u300f\u3011》])*\s*$)/u, "$1");
}

function chunkReplyText(text, limit = 3500) {
  const normalized = normalizeWeixinReplyText(text);
  if (!normalized.trim()) {
    return [];
  }

  const chunks = [];
  let remaining = normalized;
  while (remaining.length > limit) {
    const minBoundary = Math.floor(limit * 0.4);
    const cut = findLastPreferredBoundary(remaining, limit, minBoundary) || limit;
    chunks.push(remaining.slice(0, cut));
    remaining = remaining.slice(cut);
  }
  if (remaining) {
    chunks.push(remaining);
  }
  return chunks.filter(Boolean);
}

function chunkReplyTextForWeixin(text, minChunk = DEFAULT_MIN_WEIXIN_CHUNK) {
  const normalized = normalizeWeixinReplyText(text);
  if (!normalized.trim()) {
    return [];
  }

  const boundaries = collectStreamingBoundaries(normalized);
  if (!boundaries.length) {
    return chunkReplyText(normalized, MAX_WEIXIN_CHUNK);
  }

  const units = splitTextAtBoundaries(normalized, boundaries);
  if (!units.length) {
    return chunkReplyText(normalized, MAX_WEIXIN_CHUNK);
  }

  const chunks = [];
  for (const unit of units) {
    if (unit.length <= MAX_WEIXIN_CHUNK) {
      chunks.push(unit);
      continue;
    }
    chunks.push(...chunkReplyText(unit, MAX_WEIXIN_CHUNK));
  }
  return mergeShortChunks(chunks.filter(Boolean), MAX_WEIXIN_CHUNK, minChunk);
}

function mergeShortChunks(chunks, maxLength, minLength) {
  if (!chunks.length) {
    return chunks;
  }
  const merged = [];
  let buffer = chunks[0];
  for (let index = 1; index < chunks.length; index += 1) {
    const chunk = chunks[index];
    const isShort = buffer.length < minLength && chunk.length < minLength;
    const joined = `${buffer}${chunk}`;
    if (isShort && joined.length <= maxLength) {
      buffer = joined;
    } else {
      merged.push(buffer);
      buffer = chunk;
    }
  }
  merged.push(buffer);
  return merged;
}

function packChunksForWeixinDelivery(chunks, maxMessages = 10, maxChunkChars = 3800) {
  const normalizedChunks = Array.isArray(chunks)
    ? chunks.map((chunk) => normalizeLineEndings(chunk)).filter((chunk) => chunk.trim())
    : [];
  if (!normalizedChunks.length || normalizedChunks.length <= maxMessages) {
    return normalizedChunks;
  }

  const packed = normalizedChunks.slice(0, Math.max(0, maxMessages - 1));
  const tailChunks = normalizedChunks.slice(Math.max(0, maxMessages - 1));
  if (!tailChunks.length) {
    return packed;
  }

  const tailText = tailChunks.join("") || "Completed.";
  if (tailText.length <= maxChunkChars) {
    packed.push(tailText);
    return packed;
  }

  const tailHardChunks = splitUtf8(tailText, maxChunkChars);
  if (tailHardChunks.length === 1) {
    packed.push(tailHardChunks[0]);
    return packed;
  }

  const preserveCount = Math.max(0, maxMessages - tailHardChunks.length);
  const preserved = normalizedChunks.slice(0, preserveCount);
  const rebundledTail = normalizedChunks.slice(preserveCount);
  const groupedTail = [];
  let current = "";
  for (const chunk of rebundledTail) {
    const joined = current ? `${current}${chunk}` : chunk;
    if (current && joined.length > maxChunkChars) {
      groupedTail.push(current);
      current = chunk;
      continue;
    }
    current = joined;
  }
  if (current) {
    groupedTail.push(current);
  }

  return preserved.concat(groupedTail.map((item) => normalizeLineEndings(item) || "Completed.")).slice(0, maxMessages);
}

function splitTextAtBoundaries(text, boundaries) {
  const units = [];
  let start = 0;
  for (const boundary of boundaries) {
    if (boundary <= start) {
      continue;
    }
    const unit = text.slice(start, boundary);
    if (unit.trim()) {
      units.push(unit);
    }
    start = boundary;
  }
  const tail = text.slice(start);
  if (tail.trim()) {
    units.push(tail);
  }
  return units;
}

function findLastPreferredBoundary(text, maxBoundary = text.length, minBoundary = 0) {
  const boundaries = collectStreamingBoundaries(text);
  for (let index = boundaries.length - 1; index >= 0; index -= 1) {
    const boundary = boundaries[index];
    if (boundary > maxBoundary) {
      continue;
    }
    if (boundary > minBoundary) {
      return boundary;
    }
    break;
  }
  return 0;
}

function collectStreamingBoundaries(text) {
  const boundaries = new Set();

  const regex = /\n\s*\n+/g;
  let match = regex.exec(text);
  while (match) {
    boundaries.add(match.index + match[0].length);
    match = regex.exec(text);
  }

  const listRegex = /\n(?:(?:[-*])\s+|(?:\d+\.)\s+)/g;
  match = listRegex.exec(text);
  while (match) {
    boundaries.add(match.index + 1);
    match = listRegex.exec(text);
  }

  for (let index = 0; index < text.length; index += 1) {
    const endOfPunctuation = findBoundaryPunctuationEnd(text, index);
    if (!endOfPunctuation) {
      continue;
    }

    let end = endOfPunctuation;
    while (end < text.length && /["'"”’）)\]\u300d\u300f\u3011》]/u.test(text[end])) {
      end += 1;
    }
    while (end < text.length && /[\t \n]/.test(text[end])) {
      end += 1;
    }
    boundaries.add(end);
    index = endOfPunctuation - 1;
  }

  return Array.from(boundaries).sort((left, right) => left - right);
}

function findBoundaryPunctuationEnd(text, index) {
  const char = text[index];
  if (/[\u3002\uff01\uff1f!?]/u.test(char)) {
    return consumeRepeatedChar(text, index, char);
  }
  if (char === ".") {
    const end = consumeRepeatedChar(text, index, ".");
    return end - index >= 3 ? end : 0;
  }
  if (char === "…") {
    return consumeRepeatedChar(text, index, "…");
  }
  return 0;
}

function consumeRepeatedChar(text, index, char) {
  let end = index + 1;
  while (end < text.length && text[end] === char) {
    end += 1;
  }
  return end;
}

function trimOuterBlankLines(text) {
  return String(text || "")
    .replace(/^\s*\n+/g, "")
    .replace(/\n+\s*$/g, "");
}

function normalizeLineEndings(text) {
  return String(text || "").replace(/\r\n/g, "\n");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = {
  createWeixinChannelAdapter,
  splitUtf8,
  normalizeWeixinReplyText,
  finalizeWeixinDeliveryChunk,
  stripChunkTailChineseFullStops,
  chunkReplyText,
  chunkReplyTextForWeixin,
  mergeShortChunks,
  packChunksForWeixinDelivery,
  splitTextAtBoundaries,
  findLastPreferredBoundary,
  collectStreamingBoundaries,
  findBoundaryPunctuationEnd,
  trimOuterBlankLines,
};

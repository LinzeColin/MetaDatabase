"use strict";

const { createHash } = require("node:crypto");

const MAX_NUMERIC_BATCH = 10_000n;
const NUMERIC_CURSOR = /^(?:0|[1-9][0-9]*)$/;
const USER_MESSAGE_TYPES = new Set([0, 1]);
const BOT_MESSAGE_TYPE = 2;

class DurableInboxError extends Error {
  constructor(code) {
    super(code);
    this.name = "DurableInboxError";
    this.code = code;
  }
}

function normalizedText(value) {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return "";
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stableProviderMessageIdentity(message) {
  const messageId = normalizedText(message?.message_id);
  if (messageId) {
    return Object.freeze({
      kind: "message_id",
      sourceMessageId: `weixin_${sha256(`message_id\u0000${messageId}`)}`,
    });
  }
  const clientId = normalizedText(message?.client_id);
  if (clientId) {
    return Object.freeze({
      kind: "client_id",
      sourceMessageId: `weixin_${sha256(`client_id\u0000${clientId}`)}`,
    });
  }
  const sequence = parseUnsignedInteger(message?.seq);
  const timestamp = providerTimestamp(message);
  const sender = normalizedText(message?.from_user_id);
  if (sequence !== null && timestamp && sender) {
    return Object.freeze({
      kind: "sequence_time_sender",
      sourceMessageId: `weixin_${sha256(
        `sequence_time_sender\u0000${sequence}\u0000${timestamp}\u0000${sender}`,
      )}`,
    });
  }
  throw new DurableInboxError("STABLE_SOURCE_MESSAGE_ID_REQUIRED");
}

function providerTimestamp(message) {
  const milliseconds = normalizedText(message?.create_time_ms);
  if (/^[1-9][0-9]*$/.test(milliseconds)) {
    return `ms:${milliseconds}`;
  }
  const seconds = normalizedText(message?.create_time);
  if (/^[1-9][0-9]*$/.test(seconds)) {
    return `s:${seconds}`;
  }
  return "";
}

function parseUnsignedInteger(value) {
  const text = normalizedText(value);
  return NUMERIC_CURSOR.test(text) ? BigInt(text) : null;
}

function rawMessageTime(message) {
  const milliseconds = Number(message?.create_time_ms);
  if (Number.isFinite(milliseconds) && milliseconds > 0) {
    return milliseconds;
  }
  const seconds = Number(message?.create_time);
  return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 0;
}

function compareRawMessages(left, right) {
  const leftSequence = parseUnsignedInteger(left?.seq);
  const rightSequence = parseUnsignedInteger(right?.seq);
  if (
    leftSequence !== null
    && rightSequence !== null
    && leftSequence !== rightSequence
  ) {
    return leftSequence < rightSequence ? -1 : 1;
  }
  const timeDelta = rawMessageTime(left) - rawMessageTime(right);
  if (timeDelta !== 0) {
    return timeDelta;
  }
  const leftMessageId = normalizedText(left?.message_id);
  const rightMessageId = normalizedText(right?.message_id);
  if (leftMessageId !== rightMessageId) {
    return leftMessageId.localeCompare(rightMessageId);
  }
  return normalizedText(left?.client_id).localeCompare(
    normalizedText(right?.client_id),
  );
}

function sortRawMessages(messages) {
  return Array.isArray(messages)
    ? messages.slice().sort(compareRawMessages)
    : [];
}

function assertHighestContinuousBatch({
  committedCursor,
  candidateCursor,
  messages,
}) {
  const committed = parseUnsignedInteger(committedCursor);
  const candidate = parseUnsignedInteger(candidateCursor);
  if (committed === null || candidate === null) {
    return Object.freeze({
      cursorKind: "opaque",
      highestContinuousVerified: false,
    });
  }
  if (candidate < committed) {
    throw new DurableInboxError("CURSOR_REGRESSION");
  }
  const delta = candidate - committed;
  if (delta > MAX_NUMERIC_BATCH) {
    throw new DurableInboxError("NUMERIC_CURSOR_BATCH_TOO_LARGE");
  }
  if (BigInt(messages.length) !== delta) {
    throw new DurableInboxError("NUMERIC_CURSOR_BATCH_GAP");
  }
  for (let index = 0; index < messages.length; index += 1) {
    const sequence = parseUnsignedInteger(messages[index]?.seq);
    if (sequence !== committed + BigInt(index + 1)) {
      throw new DurableInboxError("NUMERIC_CURSOR_BATCH_NOT_CONTINUOUS");
    }
  }
  return Object.freeze({
    cursorKind: "numeric",
    highestContinuousVerified: true,
  });
}

function assertProviderResponse(response) {
  for (const value of [response?.ret, response?.errcode]) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric !== 0) {
      throw new DurableInboxError("WEIXIN_UPDATE_RESPONSE_REJECTED");
    }
  }
}

function classifyMessageType(normalized) {
  return String(normalized?.text || "").trim().startsWith("/")
    ? "command"
    : "text";
}

function runtimeName(config) {
  return config?.runtime === "claudecode" ? "claude" : "codex";
}

function operationClass(normalized) {
  return classifyMessageType(normalized) === "command"
    ? "command"
    : "bounded_mutation";
}

function encryptedPayload(normalized) {
  const payload = { ...normalized };
  delete payload.contextToken;
  delete payload.traceId;
  return payload;
}

function rejectedFallbackPayload(message) {
  return {
    provider: "weixin",
    receivedAt: providerTimestamp(message) || "provider_time_unavailable",
    policyDecision: {
      accepted: false,
      code: "unsupported_or_empty",
    },
  };
}

function buildBatchId({
  committedCursor,
  candidateCursor,
  orderedMessages,
}) {
  const identities = orderedMessages.map((message) => {
    try {
      return stableProviderMessageIdentity(message).sourceMessageId;
    } catch {
      return "non_actionable_without_identity";
    }
  });
  return `batch_${sha256(JSON.stringify({
    committedCursor,
    candidateCursor,
    identities,
  }))}`;
}

class DurableInboxCoordinator {
  constructor({
    channelAdapter,
    database,
    config,
    faultInjector = () => {},
    onAccepted = null,
    admissionFilter = null,
    resolveUserId = null,
  }) {
    if (!channelAdapter || typeof channelAdapter.fetchUpdates !== "function") {
      throw new DurableInboxError("CHANNEL_FETCH_API_REQUIRED");
    }
    if (
      typeof channelAdapter.commitCandidateCursor !== "function"
      || typeof channelAdapter.normalizeIncomingMessage !== "function"
      || typeof channelAdapter.loadSyncBuffer !== "function"
    ) {
      throw new DurableInboxError("CHANNEL_DURABLE_CURSOR_API_REQUIRED");
    }
    if (
      !database
      || typeof database.acceptInbound !== "function"
      || typeof database.rejectInbound !== "function"
    ) {
      throw new DurableInboxError("RUNTIME_SPOOL_REQUIRED");
    }
    this.channelAdapter = channelAdapter;
    this.database = database;
    this.config = config || {};
    this.faultInjector =
      typeof faultInjector === "function" ? faultInjector : () => {};
    this.onAccepted =
      typeof onAccepted === "function" ? onAccepted : null;
    // 准入分流钩子。必须同步，理由和 onAccepted 一样：它在游标提交之前跑，
    // 一个 await 会让「已收下但游标未提交」的窗口无限拉长。
    this.admissionFilter =
      typeof admissionFilter === "function" ? admissionFilter : null;
    // 这条消息该记在**谁**名下。
    //
    // 不给这个钩子的话，数据库那边 #resolveScopeUserId(null) 一律返回主人的
    // user_id——于是所有人发来的每一条消息都被记在主人名下。只有一个人在用的
    // 时候看不出来；第二个人一进来，后台里他显示成"主人"，而他的话也确实被
    // 归到了主人的隔离域里。这是隔离破了，不是显示错了。
    this.resolveUserId =
      typeof resolveUserId === "function" ? resolveUserId : null;
  }

  // 返回 null 表示认不出来——那时退回主人名下（老行为），而不是抛错。
  // 抛错会让整批消息卡在游标之前反复重投，比记错域还糟。
  #userIdFor(normalized) {
    if (!this.resolveUserId) {
      return null;
    }
    try {
      const resolved = this.resolveUserId(Object.freeze({ ...normalized }));
      if (resolved && typeof resolved.then === "function") {
        throw new DurableInboxError("RESOLVE_USER_ID_MUST_BE_SYNCHRONOUS");
      }
      return normalizedText(resolved) || null;
    } catch (error) {
      if (error instanceof DurableInboxError) {
        throw error;
      }
      return null;
    }
  }

  #fault(point) {
    this.faultInjector(point);
  }

  // 返回 true 表示这一轮已经被准入层处理掉，不要建 runtime job。
  // 钩子自己抛错时按「不分流」处理：宁可多建一个 job，也不能因为准入层出问题
  // 就把用户的消息静默吞掉。
  #refusedByAdmission(normalized) {
    if (!this.admissionFilter) {
      return false;
    }
    let verdict;
    try {
      verdict = this.admissionFilter(Object.freeze({ ...normalized }));
    } catch {
      return false;
    }
    if (verdict && typeof verdict.then === "function") {
      throw new DurableInboxError("ADMISSION_FILTER_MUST_BE_SYNCHRONOUS");
    }
    return verdict === true;
  }

  async pollOnce({ timeoutMs } = {}) {
    const committedCursor = this.channelAdapter.loadSyncBuffer();
    const fetched = await this.channelAdapter.fetchUpdates({
      syncBuffer: committedCursor,
      timeoutMs,
    });
    assertProviderResponse(fetched?.response);
    if (fetched?.committedCursor !== committedCursor) {
      throw new DurableInboxError("FETCH_COMMITTED_CURSOR_MISMATCH");
    }
    this.#fault("after_fetch_before_durable");
    return this.ingestFetchedBatch(fetched);
  }

  ingestFetchedBatch(fetched) {
    assertProviderResponse(fetched?.response);
    const committedCursor = normalizedText(fetched?.committedCursor);
    const candidateCursor = normalizedText(fetched?.candidateCursor)
      || committedCursor;
    const orderedMessages = sortRawMessages(fetched?.messages);
    const ordering = assertHighestContinuousBatch({
      committedCursor,
      candidateCursor,
      messages: orderedMessages,
    });
    const cursorBatchId = buildBatchId({
      committedCursor,
      candidateCursor,
      orderedMessages,
    });
    const durableMessages = [];
    const jobs = [];
    const rejections = [];
    let ignoredCount = 0;

    for (const rawMessage of orderedMessages) {
      const rawType = Number(rawMessage?.message_type);
      const identity = stableProviderMessageIdentity(rawMessage);
      if (rawType === BOT_MESSAGE_TYPE || !USER_MESSAGE_TYPES.has(rawType)) {
        const sourceAccountRef = normalizedText(this.config.accountId)
          || normalizedText(this.channelAdapter.resolveAccount?.()?.accountId);
        if (!sourceAccountRef) {
          throw new DurableInboxError("SOURCE_ACCOUNT_REQUIRED");
        }
        const rejected = this.database.rejectInbound({
          source: "weixin",
          sourceAccountRef,
          sourceMessageId: identity.sourceMessageId,
          userRef: normalizedText(rawMessage?.from_user_id)
            || "provider_non_user",
          messageType: "unsupported",
          payload: {
            provider: "weixin",
            receivedAt:
              providerTimestamp(rawMessage) || "provider_time_unavailable",
            policyDecision: {
              accepted: false,
              code: "non_user_update",
            },
          },
          contextToken: null,
          rejectReason: "non_user_update",
          cursorBatchId,
        });
        rejections.push(rejected);
        durableMessages.push(rawMessage);
        ignoredCount += 1;
        continue;
      }
      const senderId = normalizedText(rawMessage?.from_user_id);
      if (!senderId) {
        throw new DurableInboxError("SOURCE_SENDER_REQUIRED");
      }
      // 每个进程只打一次，而且**只打字段名，一个字的内容都不打**。
      //
      // 为的是回答一个具体问题：微信到底给不给我们发件人的昵称。现在后台里
      // 每个人只能显示成「用户 1」「用户 2」，因为我们手上只有一串不透明 id；
      // getconfig 只回 ret 和 typing_ticket。要么这里有，要么就是真没有——
      // 这件事必须靠抓，不能靠猜。
      if (!DurableInboxCoordinator.loggedInboundShape) {
        DurableInboxCoordinator.loggedInboundShape = true;
        try {
          console.log(
            `[cyberboss] 微信来信带的字段：${JSON.stringify(Object.keys(rawMessage))}`,
          );
        } catch {
          // 打不出来就算了，这只是一次性的取样。
        }
      }
      const normalized = this.channelAdapter.normalizeIncomingMessage(
        rawMessage,
        { durable: true },
      );
      if (!normalized) {
        const sourceAccountRef = normalizedText(this.config.accountId)
          || normalizedText(this.channelAdapter.resolveAccount?.()?.accountId);
        if (!sourceAccountRef) {
          throw new DurableInboxError("SOURCE_ACCOUNT_REQUIRED");
        }
        const rejected = this.database.rejectInbound({
          source: "weixin",
          sourceAccountRef,
          sourceMessageId: identity.sourceMessageId,
          userRef: senderId,
          messageType: "unsupported",
          payload: rejectedFallbackPayload(rawMessage),
          contextToken: normalizedText(rawMessage?.context_token) || null,
          rejectReason: "unsupported_or_empty",
          cursorBatchId,
        });
        rejections.push(rejected);
        durableMessages.push(rawMessage);
        continue;
      }

      const sourceAccountRef = normalizedText(normalized.accountId)
        || normalizedText(this.config.accountId)
        || normalizedText(this.channelAdapter.resolveAccount?.()?.accountId);
      if (!sourceAccountRef) {
        throw new DurableInboxError("SOURCE_ACCOUNT_REQUIRED");
      }
      const contextToken = normalizedText(normalized.contextToken) || null;
      // 这一句必须排在 #refusedByAdmission **之后**：准入层就是注册这个人的
      // 地方，在它跑之前 users 表里还没有他。
      let scopeUserId = null;
      const refusedByAdmission = normalized.policyDecision?.accepted === false
        ? false
        : this.#refusedByAdmission(normalized);
      scopeUserId = this.#userIdFor(normalized);
      if (normalized.policyDecision?.accepted === false) {
        const reason = normalizedText(normalized.policyDecision.code)
          || "policy_rejected";
        const rejected = this.database.rejectInbound({
          source: "weixin",
          sourceAccountRef,
          sourceMessageId: identity.sourceMessageId,
          userRef: senderId,
          messageType: classifyMessageType(normalized),
          payload: encryptedPayload(normalized),
          contextToken,
          rejectReason: reason,
          cursorBatchId,
          userId: scopeUserId,
        });
        rejections.push(rejected);
      } else if (refusedByAdmission) {
        // 这一轮在准入层就办完了：入门回复、普通用户的确定性口令、席位已满的
        // 拒绝——都不该变成一个 runtime job。
        //
        // 这条分流必须在建 job **之前**：JobScheduler 要求 dispatchRuntime 返回
        // 真实的 threadId/turnId，所以到了调度阶段就再也没有「不调用模型就结束
        // 这一轮」的出口。R19 要求第六个用户在 DeepSeek 调用之前被拒绝，这是唯一
        // 能兑现它的位置。
        const rejected = this.database.rejectInbound({
          source: "weixin",
          sourceAccountRef,
          sourceMessageId: identity.sourceMessageId,
          userRef: senderId,
          messageType: classifyMessageType(normalized),
          payload: encryptedPayload(normalized),
          contextToken,
          rejectReason: "handled_by_admission",
          cursorBatchId,
          userId: scopeUserId,
        });
        rejections.push(rejected);
      } else {
        const accepted = this.database.acceptInbound({
          source: "weixin",
          sourceAccountRef,
          sourceMessageId: identity.sourceMessageId,
          userRef: senderId,
          messageType: classifyMessageType(normalized),
          payload: encryptedPayload(normalized),
          contextToken,
          workspaceAlias: this.config.workspaceAlias || "cyberboss",
          runtime: runtimeName(this.config),
          operationClass: operationClass(normalized),
          maxAttempts: 1,
          cursorBatchId,
          userId: scopeUserId,
        });
        if (this.onAccepted) {
          const callbackResult = this.onAccepted({
            accepted,
            normalized: Object.freeze({ ...normalized }),
          });
          if (callbackResult && typeof callbackResult.then === "function") {
            throw new DurableInboxError("ON_ACCEPTED_MUST_BE_SYNCHRONOUS");
          }
          this.#fault("after_accepted_outbox_before_cursor");
        }
        jobs.push(Object.freeze({
          ...accepted,
          sourceIdentityKind: identity.kind,
        }));
      }
      durableMessages.push(rawMessage);
    }

    this.#fault("after_durable_before_cursor");
    const cursorCommit = this.channelAdapter.commitCandidateCursor({
      expectedCursor: committedCursor,
      candidateCursor,
    });
    this.#fault("after_cursor");
    return Object.freeze({
      committedCursor,
      candidateCursor,
      cursorBatchId,
      cursorChanged: cursorCommit.changed,
      cursorKind: ordering.cursorKind,
      highestContinuousVerified: ordering.highestContinuousVerified,
      fetchedCount: orderedMessages.length,
      durableCount: durableMessages.length,
      ignoredCount,
      acceptedCount: jobs.length,
      rejectedCount: rejections.length,
      jobs: Object.freeze(jobs),
      rejections: Object.freeze(rejections),
    });
  }
}

module.exports = {
  DurableInboxCoordinator,
  DurableInboxError,
  assertHighestContinuousBatch,
  buildBatchId,
  compareRawMessages,
  sortRawMessages,
  stableProviderMessageIdentity,
};

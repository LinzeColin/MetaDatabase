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
  }

  #fault(point) {
    this.faultInjector(point);
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
        });
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

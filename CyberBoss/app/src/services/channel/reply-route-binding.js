"use strict";

// CB-630 / AC-042: the reply destination is bound at inbound time and is
// immutable afterwards. A later stage can only prove it matches; it can never
// choose a new recipient, so user A's outbox can never reach user B.

const { createHmac, timingSafeEqual } = require("node:crypto");

const MAX_FIELD_LENGTH = 1024;

class ReplyRouteError extends Error {
  constructor(code) {
    super(code);
    this.name = "ReplyRouteError";
    this.code = code;
  }
}

function requireField(value, field) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > MAX_FIELD_LENGTH
  ) {
    throw new ReplyRouteError(`REPLY_ROUTE_${field.toUpperCase()}_REQUIRED`);
  }
  return value;
}

function requireRouteKey(key) {
  if (!Buffer.isBuffer(key) || key.length < 32) {
    throw new ReplyRouteError("REPLY_ROUTE_KEY_MUST_BE_AT_LEAST_32_BYTES");
  }
  return key;
}

// Length-prefixed so no two different field splits can produce the same hash.
function destinationHash({
  routeKey,
  userId,
  botAccountRef,
  senderRef,
  contextToken,
}) {
  const hmac = createHmac("sha256", requireRouteKey(routeKey));
  hmac.update("cyberboss-reply-route");
  for (const [field, value] of [
    ["user_id", userId],
    ["bot_account_ref", botAccountRef],
    ["sender_ref", senderRef],
    ["context_token", contextToken],
  ]) {
    const encoded = Buffer.from(requireField(value, field), "utf8");
    const size = Buffer.alloc(4);
    size.writeUInt32BE(encoded.length);
    hmac.update(size);
    hmac.update(encoded);
  }
  return hmac.digest("hex");
}

function bindReplyRoute({
  routeKey,
  userId,
  botAccountRef,
  senderRef,
  contextToken,
}) {
  return Object.freeze({
    userId,
    botAccountRef,
    senderRef,
    contextToken,
    destinationHash: destinationHash({
      routeKey,
      userId,
      botAccountRef,
      senderRef,
      contextToken,
    }),
  });
}

// Any disagreement — including a swapped user_id with otherwise valid routing
// fields — fails closed with the same code, in constant time.
function assertReplyRoute({
  routeKey,
  binding,
  userId,
  botAccountRef,
  senderRef,
  contextToken,
}) {
  if (!binding || typeof binding.destinationHash !== "string") {
    throw new ReplyRouteError("REPLY_ROUTE_MISSING");
  }
  const candidate = destinationHash({
    routeKey,
    userId,
    botAccountRef,
    senderRef,
    contextToken,
  });
  const stored = Buffer.from(binding.destinationHash, "utf8");
  const computed = Buffer.from(candidate, "utf8");
  if (
    binding.userId !== userId ||
    stored.length !== computed.length ||
    !timingSafeEqual(stored, computed)
  ) {
    throw new ReplyRouteError("REPLY_ROUTE_MISMATCH");
  }
  return true;
}

// The outbound path calls this immediately before handing a message to the
// channel. It returns the bound destination rather than accepting one.
function resolveOutboundDestination({ routeKey, binding, expectedUserId }) {
  if (!binding || binding.userId !== expectedUserId) {
    throw new ReplyRouteError("REPLY_ROUTE_MISMATCH");
  }
  assertReplyRoute({
    routeKey,
    binding,
    userId: binding.userId,
    botAccountRef: binding.botAccountRef,
    senderRef: binding.senderRef,
    contextToken: binding.contextToken,
  });
  return Object.freeze({
    botAccountRef: binding.botAccountRef,
    senderRef: binding.senderRef,
    contextToken: binding.contextToken,
  });
}

module.exports = {
  ReplyRouteError,
  assertReplyRoute,
  bindReplyRoute,
  destinationHash,
  resolveOutboundDestination,
};

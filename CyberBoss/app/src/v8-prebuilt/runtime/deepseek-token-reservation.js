'use strict';

const MODEL_CONTEXT_TOKENS = 1_000_000;
const MODEL_MAX_OUTPUT_TOKENS = 384_000;
const SERIALIZATION_OVERHEAD_TOKENS = 8_192;
const MAX_REQUEST_RESERVATION_TOKENS = MODEL_CONTEXT_TOKENS;

function serializeInput(input) {
  if (typeof input === 'string') return input;
  try {
    const value = JSON.stringify(input);
    if (typeof value !== 'string') throw new TypeError('input is not serializable');
    return value;
  } catch (error) {
    throw Object.assign(new Error('INPUT_NOT_SERIALIZABLE'), { code: 'INPUT_NOT_SERIALIZABLE', cause: error });
  }
}

function conservativeDeepSeekReservation(input) {
  const bytes = Buffer.byteLength(serializeInput(input), 'utf8');
  // One UTF-8 byte per token is deliberately conservative and guarantees that
  // the only product quota (UTC daily 1B total tokens) is checked before dispatch.
  return Math.min(
    MAX_REQUEST_RESERVATION_TOKENS,
    Math.max(MODEL_MAX_OUTPUT_TOKENS, bytes + SERIALIZATION_OVERHEAD_TOKENS + MODEL_MAX_OUTPUT_TOKENS),
  );
}

module.exports = {
  conservativeDeepSeekReservation,
  MODEL_CONTEXT_TOKENS,
  MODEL_MAX_OUTPUT_TOKENS,
  SERIALIZATION_OVERHEAD_TOKENS,
  MAX_REQUEST_RESERVATION_TOKENS,
};

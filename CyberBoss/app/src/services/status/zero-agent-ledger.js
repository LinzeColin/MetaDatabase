"use strict";

// CB-810 / AC-033: the zero-agent ledger.
//
// The contract names eleven counters that must be zero. Asserting that in prose
// is worthless; this makes it a value the runtime can publish and a check that
// fails closed. A counter that was never reported is not zero — it is unknown,
// and unknown is a failure here, because the whole claim is that no background
// path can quietly acquire a model call.

// Frozen by machine/zero_agent_contract.json -> must_equal_zero.
const MUST_EQUAL_ZERO = Object.freeze([
  "control_plane_llm_calls_total",
  "scheduler_agent_invocations_total",
  "health_agent_invocations_total",
  "self_heal_agent_invocations_total",
  "backup_agent_invocations_total",
  "restore_agent_invocations_total",
  "status_agent_invocations_total",
  "sync_agent_invocations_total",
  "import_parser_agent_invocations_total",
  "analytics_agent_invocations_total",
  "release_agent_invocations_total",
]);

// The only three places a model call is legitimate. Each is user- or
// Owner-initiated; none of them is a background task.
const ALLOWED_MODEL_CALLS = Object.freeze([
  "user_initiated_ai_turn",
  "user_explicit_profile_suggestion",
  "owner_initiated_codex_turn",
]);

// Control paths that must remain arithmetic.
const DETERMINISTIC_MODEL_CONTROL = Object.freeze([
  "token_estimation",
  "budget_reservation",
  "usage_normalization",
  "usage_aggregation",
  "circuit_state_machine",
  "half_open_probe",
  "status_projection",
]);

const FORBIDDEN_BACKGROUND_MODEL_CALLS = Object.freeze([
  "provider_health_probe",
  "budget_summary",
  "analytics_summary",
  "self_heal_decision",
  "status_narration",
]);

class ZeroAgentError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "ZeroAgentError";
    this.code = code;
    this.detail = detail;
  }
}

function buildZeroAgentLedger(counters) {
  if (!counters || typeof counters !== "object" || Array.isArray(counters)) {
    throw new ZeroAgentError("ZERO_AGENT_COUNTERS_INVALID", "counters");
  }
  const missing = MUST_EQUAL_ZERO.filter((name) => !Object.hasOwn(counters, name));
  if (missing.length > 0) {
    // Unreported is not zero.
    throw new ZeroAgentError("ZERO_AGENT_COUNTER_MISSING", missing.join(","));
  }
  const violations = MUST_EQUAL_ZERO.filter((name) => {
    const value = Number(counters[name]);
    return !Number.isInteger(value) || value !== 0;
  });
  if (violations.length > 0) {
    throw new ZeroAgentError("ZERO_AGENT_VIOLATION", violations.join(","));
  }
  return Object.freeze({
    schema_version: 1,
    counters: Object.freeze(
      Object.fromEntries(MUST_EQUAL_ZERO.map((name) => [name, 0])),
    ),
    allowed_model_calls: ALLOWED_MODEL_CALLS,
    deterministic_model_control: DETERMINISTIC_MODEL_CONTROL,
    forbidden_background_model_calls: FORBIDDEN_BACKGROUND_MODEL_CALLS,
    zero_agent: true,
  });
}

// A call site declares why it is calling a model. Anything not on the
// three-item allowlist is refused at the boundary rather than counted after.
function assertModelCallAllowed(purpose) {
  if (!ALLOWED_MODEL_CALLS.includes(purpose)) {
    throw new ZeroAgentError("MODEL_CALL_PURPOSE_NOT_ALLOWED", String(purpose));
  }
  return purpose;
}

module.exports = {
  ALLOWED_MODEL_CALLS,
  DETERMINISTIC_MODEL_CONTROL,
  FORBIDDEN_BACKGROUND_MODEL_CALLS,
  MUST_EQUAL_ZERO,
  ZeroAgentError,
  assertModelCallAllowed,
  buildZeroAgentLedger,
};

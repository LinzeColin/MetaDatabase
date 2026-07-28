"use strict";

// CB-810 / AC-048: model usage and circuit state, observable in aggregate only.
//
// The operator needs to see which provider is burning budget and which circuit
// is open. They do not need to see whose traffic it was. Every field in the
// output is drawn from a frozen allowlist, and the aggregation deliberately
// discards the per-user dimension before the summary is assembled — there is
// no code path that could emit it, rather than a filter that might be skipped.

const {
  StatusMatrixError,
  assertNoSensitiveValues,
} = require("./business-matrix");

// Frozen by machine/status_business_matrix.json.
const ALLOWED_FIELDS = Object.freeze([
  "provider",
  "budget_state",
  "soft_warning",
  "hard_block",
  "reserved_tokens",
  "charged_tokens",
  "circuit_state",
  "last_transition_at",
  "reason_code",
]);

const FORBIDDEN_DIMENSIONS = Object.freeze([
  "user_id",
  "wechat_id",
  "prompt",
  "response",
  "api_key",
  "credential_token",
  "raw_message",
]);

const PROVIDERS = Object.freeze(["openai", "google", "deepseek", "anthropic", "codex"]);
const BUDGET_STATES = Object.freeze(["ok", "soft_warning", "hard_block", "unknown"]);
const CIRCUIT_STATES = Object.freeze(["closed", "open", "half_open"]);
const REASON_CODE = /^[A-Z][A-Z0-9_]{2,48}$/;

function requireCount(value, field) {
  const count = Number(value ?? 0);
  if (!Number.isFinite(count) || count < 0) {
    throw new StatusMatrixError("USAGE_FIELD_NOT_A_COUNT", field);
  }
  return count;
}

function requireTimestamp(value, field) {
  if (value === null || value === undefined) {
    return null;
  }
  const timestamp = new Date(value);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new StatusMatrixError("USAGE_TIMESTAMP_INVALID", field);
  }
  return timestamp.toISOString();
}

// Collapse per-user rows to per-provider totals. The user dimension is dropped
// here, before any summary object exists.
function aggregateByProvider(rows) {
  if (!Array.isArray(rows)) {
    throw new StatusMatrixError("USAGE_ROWS_INVALID", "rows");
  }
  const totals = new Map();
  for (const row of rows) {
    if (!row || typeof row !== "object") {
      throw new StatusMatrixError("USAGE_ROW_INVALID", "row");
    }
    const provider = String(row.providerId ?? row.provider ?? "");
    if (!PROVIDERS.includes(provider)) {
      throw new StatusMatrixError("USAGE_PROVIDER_UNKNOWN", "provider");
    }
    const current = totals.get(provider) || { reserved: 0, charged: 0 };
    current.reserved += requireCount(row.reservedTokens, "reservedTokens");
    current.charged += requireCount(row.chargedTokens, "chargedTokens");
    totals.set(provider, current);
  }
  return totals;
}

function buildModelUsageSummary({
  usageRows = [],
  circuitRows = [],
  budgetStates = {},
  generatedAt,
}) {
  const timestamp = new Date(generatedAt);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new StatusMatrixError("USAGE_GENERATED_AT_INVALID", "generatedAt");
  }
  const totals = aggregateByProvider(usageRows);

  const circuits = new Map();
  for (const row of Array.isArray(circuitRows) ? circuitRows : []) {
    const provider = String(row?.providerId ?? row?.provider ?? "");
    if (!PROVIDERS.includes(provider)) {
      throw new StatusMatrixError("USAGE_PROVIDER_UNKNOWN", "circuit.provider");
    }
    const state = String(row.state ?? row.globalState ?? "closed");
    if (!CIRCUIT_STATES.includes(state)) {
      throw new StatusMatrixError("USAGE_CIRCUIT_STATE_UNKNOWN", "circuit.state");
    }
    const reasonCode = row.reasonCode === null || row.reasonCode === undefined
      ? null
      : String(row.reasonCode);
    if (reasonCode !== null && !REASON_CODE.test(reasonCode)) {
      throw new StatusMatrixError("USAGE_REASON_CODE_INVALID", "circuit.reason_code");
    }
    circuits.set(provider, {
      state,
      reasonCode,
      lastTransitionAt: requireTimestamp(row.lastTransitionAt, "circuit.last_transition_at"),
    });
  }

  const providers = [...totals.keys()].sort().map((provider) => {
    const totalsRow = totals.get(provider);
    const circuit = circuits.get(provider) || {
      state: "closed",
      reasonCode: null,
      lastTransitionAt: null,
    };
    const budgetState = String(budgetStates[provider] ?? "ok");
    if (!BUDGET_STATES.includes(budgetState)) {
      throw new StatusMatrixError("USAGE_BUDGET_STATE_UNKNOWN", "budget_state");
    }
    const row = {
      provider,
      budget_state: budgetState,
      soft_warning: budgetState === "soft_warning",
      hard_block: budgetState === "hard_block",
      reserved_tokens: totalsRow.reserved,
      charged_tokens: totalsRow.charged,
      circuit_state: circuit.state,
      last_transition_at: circuit.lastTransitionAt,
      reason_code: circuit.reasonCode,
    };
    // Exact allowlist: a field that is not in the frozen set cannot be
    // published even by accident.
    const extra = Object.keys(row).filter((key) => !ALLOWED_FIELDS.includes(key));
    if (extra.length > 0) {
      throw new StatusMatrixError("USAGE_FIELD_NOT_ALLOWED", extra.join(","));
    }
    return Object.freeze(row);
  });

  const payload = {
    schema_version: 1,
    generated_at: timestamp.toISOString(),
    providers: Object.freeze(providers),
    // AC-033: the summary is arithmetic over stored rows, never a narration.
    model_calls: 0,
  };
  assertNoSensitiveValues(payload, "$");
  return Object.freeze(payload);
}

module.exports = {
  ALLOWED_FIELDS,
  BUDGET_STATES,
  CIRCUIT_STATES,
  FORBIDDEN_DIMENSIONS,
  PROVIDERS,
  aggregateByProvider,
  buildModelUsageSummary,
};

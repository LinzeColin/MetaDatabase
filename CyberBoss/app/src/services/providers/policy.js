"use strict";

// CB-700 / AC-013..AC-016: a provider policy is server-owned. The origin and
// the model allowlist come from configuration the Owner controls; a user can
// never supply a base URL or an arbitrary model id, so a compromised account
// cannot redirect traffic to an attacker-controlled endpoint.

const MODEL_ID = /^[A-Za-z0-9._:-]{2,120}$/;
const PROVIDER_IDS = Object.freeze(["openai", "google", "deepseek", "anthropic"]);

class ProviderPolicyError extends Error {
  constructor(code) {
    super(code);
    this.name = "ProviderPolicyError";
    this.code = code;
  }
}

function assertPolicy(policy) {
  if (
    !policy ||
    !PROVIDER_IDS.includes(policy.providerId) ||
    typeof policy.origin !== "string" ||
    !Array.isArray(policy.models) ||
    policy.models.length < 1
  ) {
    throw new ProviderPolicyError("PROVIDER_POLICY_INCOMPLETE");
  }
  let url;
  try {
    url = new URL(policy.origin);
  } catch {
    throw new ProviderPolicyError("PROVIDER_ORIGIN_INVALID");
  }
  if (
    url.protocol !== "https:" ||
    url.username !== "" ||
    url.password !== "" ||
    url.pathname !== "/" ||
    url.search !== "" ||
    url.hash !== ""
  ) {
    throw new ProviderPolicyError("PROVIDER_ORIGIN_MUST_BE_BARE_HTTPS");
  }
  if (!policy.models.every((model) => typeof model === "string" && MODEL_ID.test(model))) {
    throw new ProviderPolicyError("MODEL_ALLOWLIST_INVALID");
  }
  return Object.freeze({
    ...policy,
    origin: url.origin,
    models: Object.freeze([...policy.models]),
  });
}

// Exact membership only: no prefix, suffix or wildcard matching.
function assertModel(policy, model) {
  if (typeof model !== "string" || !policy.models.includes(model)) {
    throw new ProviderPolicyError("MODEL_NOT_ALLOWED");
  }
  return model;
}

// A caller-supplied object may only choose among server-owned values; any
// attempt to introduce an origin or an unknown model is refused.
function selectServerPolicy(policies, providerId) {
  const policy = policies && policies[providerId];
  if (!policy) {
    throw new ProviderPolicyError("PROVIDER_NOT_SUPPORTED");
  }
  return assertPolicy(policy);
}

module.exports = {
  MODEL_ID,
  PROVIDER_IDS,
  ProviderPolicyError,
  assertModel,
  assertPolicy,
  selectServerPolicy,
};

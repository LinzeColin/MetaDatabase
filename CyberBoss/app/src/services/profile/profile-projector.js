"use strict";

// CB-720 / AC-024, AC-025, AC-026: the profile projection.
//
// Resolved at CB-600 as an additive read-only module over the existing
// canonical fact path — it never forks or replaces canonical-sync, the timeline
// or the diary, and it is not a second authority for user facts.
//
// Three rules hold structurally:
//   - every inferred fact carries source, evidence, confidence and
//     counterevidence, or it is refused;
//   - a sensitive category is refused unless the user gave explicit consent for
//     that exact category;
//   - a rejected, frozen or deleted decision is honoured by the projection
//     immediately and by every later write.

const ALLOWED_CATEGORIES = Object.freeze([
  "basic",
  "preference",
  "routine",
  "goal",
  "relationship",
  "work",
  "interest",
  "communication_style",
]);

// Never inferred. Only ever stored when the user explicitly consents to that
// specific category, and never derived from imported chat history.
const SENSITIVE_CATEGORIES = Object.freeze([
  "politics",
  "religion",
  "sexual_orientation",
  "health_diagnosis",
  "mental_illness",
  "criminal_risk",
  "financial_distress",
  "ethnicity",
  "biometric",
]);

const KINDS = Object.freeze(["explicit", "inferred"]);
const DECISIONS = Object.freeze([
  "proposed",
  "accepted",
  "modified",
  "rejected",
  "deleted",
]);
// A projection never surfaces these, and a later suggestion may not revive one.
const SUPPRESSED_DECISIONS = Object.freeze(["rejected", "deleted"]);

class ProfileError extends Error {
  constructor(code) {
    super(code);
    this.name = "ProfileError";
    this.code = code;
  }
}

function isSensitive(category) {
  return SENSITIVE_CATEGORIES.includes(category);
}

function validateFact(fact) {
  if (!fact || typeof fact !== "object") {
    throw new ProfileError("PROFILE_FACT_REQUIRED");
  }
  if (!KINDS.includes(fact.kind)) {
    throw new ProfileError("PROFILE_KIND_INVALID");
  }
  if (fact.decision && !DECISIONS.includes(fact.decision)) {
    throw new ProfileError("PROFILE_DECISION_INVALID");
  }
  if (isSensitive(fact.category)) {
    // A sensitive attribute may never be inferred, at any confidence, with any
    // consent. Consent only ever permits an explicit user statement.
    if (fact.kind === "inferred") {
      throw new ProfileError("SENSITIVE_INFERENCE_FORBIDDEN");
    }
    if (fact.explicitSensitiveConsent !== fact.category) {
      throw new ProfileError("SENSITIVE_PROFILE_BLOCKED");
    }
  } else if (!ALLOWED_CATEGORIES.includes(fact.category)) {
    throw new ProfileError("PROFILE_CATEGORY_NOT_ALLOWED");
  }
  if (fact.kind === "inferred") {
    // AC-024: an inference with no traceable basis is not storable.
    if (
      !fact.sourceRef ||
      !fact.evidenceRef ||
      typeof fact.confidence !== "number" ||
      !(fact.confidence > 0 && fact.confidence <= 1) ||
      !Array.isArray(fact.counterevidence)
    ) {
      throw new ProfileError("INFERENCE_EVIDENCE_REQUIRED");
    }
  }
  return fact;
}

// Latest version wins per (user, category, key); rejected and deleted facts are
// dropped, and a frozen fact keeps the version the user froze.
function projectProfile(facts, { decisions = [] } = {}) {
  const rejectedKeys = new Set(
    decisions
      .filter((decision) => SUPPRESSED_DECISIONS.includes(decision.decision) && decision.appliesToFuture)
      .map((decision) => `${decision.userId}:${decision.category}:${decision.factKey}`),
  );
  const latest = new Map();
  for (const raw of facts) {
    const fact = validateFact(raw);
    const key = `${fact.userId}:${fact.category}:${fact.key}`;
    const previous = latest.get(key);
    if (previous && previous.frozen) {
      // A frozen fact is not overwritten by a newer suggestion.
      continue;
    }
    if (!previous || Number(fact.version || 0) > Number(previous.version || 0)) {
      latest.set(key, fact);
    }
  }
  return [...latest.values()]
    .filter((fact) => !SUPPRESSED_DECISIONS.includes(fact.decision))
    .filter(
      (fact) => !rejectedKeys.has(`${fact.userId}:${fact.category}:${fact.key}`),
    )
    .map((fact) =>
      Object.freeze({
        userId: fact.userId,
        category: fact.category,
        key: fact.key,
        value: fact.value,
        kind: fact.kind,
        sourceRef: fact.sourceRef || null,
        evidenceRef: fact.evidenceRef || null,
        confidence: fact.confidence === undefined ? null : fact.confidence,
        counterevidence: Object.freeze([...(fact.counterevidence || [])]),
        decision: fact.decision || "proposed",
        frozen: Boolean(fact.frozen),
        version: Number(fact.version || 1),
      }),
    )
    .sort(
      (left, right) =>
        left.category.localeCompare(right.category) || left.key.localeCompare(right.key),
    );
}

// What the user sees when they ask "why do you think that?": the claim, where
// it came from, how sure the system is, and what argues against it.
function explainFact(fact) {
  return Object.freeze({
    category: fact.category,
    key: fact.key,
    kind: fact.kind,
    sourceRef: fact.sourceRef || null,
    evidenceRef: fact.evidenceRef || null,
    confidence: fact.confidence === undefined ? null : fact.confidence,
    counterevidence: Object.freeze([...(fact.counterevidence || [])]),
    decision: fact.decision || "proposed",
    frozen: Boolean(fact.frozen),
  });
}

function sensitiveInferenceCount(facts) {
  return facts.filter((fact) => fact.kind === "inferred" && isSensitive(fact.category))
    .length;
}

module.exports = {
  ALLOWED_CATEGORIES,
  DECISIONS,
  KINDS,
  ProfileError,
  SENSITIVE_CATEGORIES,
  SUPPRESSED_DECISIONS,
  explainFact,
  isSensitive,
  projectProfile,
  sensitiveInferenceCount,
  validateFact,
};

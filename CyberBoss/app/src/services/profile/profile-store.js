"use strict";

// CB-720 / AC-025: the durable side of profile control, over profile_facts and
// profile_decisions. A user decision is recorded and applied in one
// transaction, so the projection can never lag behind what the user just said.

const { randomUUID } = require("node:crypto");
const {
  DECISIONS,
  ProfileError,
  isSensitive,
  projectProfile,
  validateFact,
} = require("./profile-projector");

class SqliteProfileStore {
  constructor({ database, now = () => new Date() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new ProfileError("DATABASE_REQUIRED");
    }
    this.database = database;
    this.now = now;
  }

  #timestamp() {
    const value = this.now();
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) {
      throw new ProfileError("CLOCK_INVALID");
    }
    return date.toISOString();
  }

  #rollbackQuietly() {
    try {
      this.database.exec("ROLLBACK");
    } catch {
      // A commit may already have completed; the original error is preserved.
    }
  }

  #nextVersion(userId, category, factKey) {
    const row = this.database
      .prepare(
        `SELECT COALESCE(MAX(version), 0) AS version FROM profile_facts
         WHERE user_id=? AND category=? AND fact_key=?`,
      )
      .get(userId, category, factKey);
    return Number(row.version) + 1;
  }

  // A suggestion is refused outright if the user already rejected or deleted
  // that key with appliesToFuture, so a rejected inference cannot reappear.
  suggest({ userId, category, factKey, value, kind, sourceRef = null, evidenceRef = null, confidence = null, counterevidence = [], explicitSensitiveConsent = null }) {
    validateFact({
      userId,
      category,
      key: factKey,
      value,
      kind,
      sourceRef,
      evidenceRef,
      confidence,
      counterevidence,
      explicitSensitiveConsent,
      decision: "proposed",
    });
    // Order by rowid, not occurred_at: several decisions can share the same
    // millisecond, and a timestamp tie would let an older "accepted" outrank a
    // newer "rejected" and quietly resurrect an inference the user refused.
    const standing = this.database
      .prepare(
        `SELECT decision FROM profile_decisions
         WHERE user_id=? AND category=? AND fact_key=? AND applies_to_future=1
         ORDER BY rowid DESC LIMIT 1`,
      )
      .get(userId, category, factKey);
    if (standing && ["rejected", "deleted"].includes(standing.decision)) {
      throw new ProfileError("PROFILE_SUGGESTION_REFUSED_BY_USER");
    }
    const frozen = this.database
      .prepare(
        `SELECT frozen FROM profile_facts
         WHERE user_id=? AND category=? AND fact_key=?
         ORDER BY version DESC LIMIT 1`,
      )
      .get(userId, category, factKey);
    if (frozen && Number(frozen.frozen) === 1) {
      throw new ProfileError("PROFILE_FACT_FROZEN");
    }

    const now = this.#timestamp();
    const version = this.#nextVersion(userId, category, factKey);
    const factId = `pf_${randomUUID()}`;
    this.database
      .prepare(
        `INSERT INTO profile_facts(
           fact_id, user_id, kind, category, fact_key, value_json, source_ref,
           evidence_ref, confidence, counterevidence_json, decision, frozen,
           version, created_at, updated_at
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', 0, ?, ?, ?)`,
      )
      .run(
        factId,
        userId,
        kind,
        category,
        factKey,
        JSON.stringify(value),
        sourceRef,
        evidenceRef,
        confidence,
        JSON.stringify(counterevidence),
        version,
        now,
        now,
      );
    return Object.freeze({ factId, version });
  }

  // AC-025: accept, modify, reject, freeze or delete. Each is recorded as a
  // decision and applied to the fact in the same transaction.
  decide({ userId, category, factKey, decision, value = undefined, appliesToFuture = true }) {
    if (!DECISIONS.includes(decision) && decision !== "frozen") {
      throw new ProfileError("PROFILE_DECISION_INVALID");
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const current = this.database
        .prepare(
          `SELECT fact_id, version, value_json, frozen FROM profile_facts
           WHERE user_id=? AND category=? AND fact_key=?
           ORDER BY version DESC LIMIT 1`,
        )
        .get(userId, category, factKey);
      if (!current) {
        throw new ProfileError("PROFILE_FACT_NOT_FOUND");
      }
      const storedDecision = decision === "frozen" ? "accepted" : decision;
      // Freezing sets the flag; nothing else clears it implicitly. An
      // "accepted" arriving after a freeze must not silently unfreeze the fact.
      const frozen =
        decision === "frozen" ? 1 : Number(current.frozen) === 1 ? 1 : 0;
      this.database
        .prepare(
          `UPDATE profile_facts
           SET decision=?, frozen=?, value_json=?, updated_at=?
           WHERE fact_id=?`,
        )
        .run(
          storedDecision,
          frozen,
          value === undefined ? current.value_json : JSON.stringify(value),
          now,
          current.fact_id,
        );
      this.database
        .prepare(
          `INSERT INTO profile_decisions(
             decision_id, user_id, category, fact_key, decision,
             applies_to_future, occurred_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          `pd_${randomUUID()}`,
          userId,
          category,
          factKey,
          decision,
          appliesToFuture ? 1 : 0,
          now,
        );
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
    return this.projection(userId);
  }

  #rows(userId) {
    return this.database
      .prepare(
        `SELECT user_id, kind, category, fact_key, value_json, source_ref,
                evidence_ref, confidence, counterevidence_json, decision,
                frozen, version
         FROM profile_facts WHERE user_id=? ORDER BY version`,
      )
      .all(userId)
      .map((row) => ({
        userId: row.user_id,
        kind: row.kind,
        category: row.category,
        key: row.fact_key,
        value: JSON.parse(row.value_json),
        sourceRef: row.source_ref,
        evidenceRef: row.evidence_ref,
        confidence: row.confidence,
        counterevidence: JSON.parse(row.counterevidence_json),
        decision: row.decision,
        frozen: Number(row.frozen) === 1,
        version: Number(row.version),
        // Stored sensitive rows already passed the consent gate at write time.
        explicitSensitiveConsent: isSensitive(row.category) ? row.category : null,
      }));
  }

  projection(userId) {
    const decisions = this.database
      .prepare(
        `SELECT user_id, category, fact_key, decision, applies_to_future
         FROM profile_decisions WHERE user_id=?`,
      )
      .all(userId)
      .map((row) => ({
        userId: row.user_id,
        category: row.category,
        factKey: row.fact_key,
        decision: row.decision,
        appliesToFuture: Number(row.applies_to_future) === 1,
      }));
    return projectProfile(this.#rows(userId), { decisions });
  }
}

module.exports = { SqliteProfileStore };

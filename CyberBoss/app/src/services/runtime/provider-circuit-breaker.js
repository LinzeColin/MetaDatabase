"use strict";

// CB-700 / AC-047: two circuit scopes.
//
//   user_provider  a bad or exhausted key breaks only that user's connection
//   global         a provider outage breaks that provider for everyone
//
// Exactly one half-open probe may be in flight per circuit. The probe holds a
// bounded lease, so a crash or a lost completion cannot wedge a provider open
// forever, and any downstream denial releases the probe it did not use.

const GLOBAL_FAILURE_CODES = Object.freeze([
  "PROVIDER_UNAVAILABLE",
  "PROVIDER_BAD_RESPONSE",
  "TIMEOUT",
  "NETWORK_ERROR",
]);
const USER_FAILURE_CODES = Object.freeze([
  "CREDENTIAL_INVALID",
  "NO_BALANCE",
  "RATE_LIMITED",
]);
const MESSAGES = Object.freeze({
  global: "AI 服务暂时不可用，我等一会儿自动再试。",
  user_provider: "你的 AI 连接暂时用不了，去设置页看看密钥是否还有效。",
});

class MemoryCircuitStore {
  constructor() {
    this.rows = new Map();
  }

  get(key) {
    const row = this.rows.get(key);
    return row ? { ...row } : null;
  }

  set(key, value) {
    this.rows.set(key, { ...value });
    return this.get(key);
  }

  delete(key) {
    this.rows.delete(key);
  }

  values() {
    return [...this.rows.values()].map((row) => ({ ...row }));
  }
}

class ProviderCircuitBreaker {
  constructor({
    store = new MemoryCircuitStore(),
    clock = () => Date.now(),
    globalFailureThreshold = 5,
    globalOpenMs = 60_000,
    userRateLimitThreshold = 2,
    userOpenMs = 30_000,
    halfOpenProbeLeaseMs = 30_000,
  } = {}) {
    if (!Number.isSafeInteger(halfOpenProbeLeaseMs) || halfOpenProbeLeaseMs < 1) {
      throw new TypeError("halfOpenProbeLeaseMs must be a positive integer");
    }
    this.store = store;
    this.clock = clock;
    this.globalFailureThreshold = globalFailureThreshold;
    this.globalOpenMs = globalOpenMs;
    this.userRateLimitThreshold = userRateLimitThreshold;
    this.userOpenMs = userOpenMs;
    this.halfOpenProbeLeaseMs = halfOpenProbeLeaseMs;
  }

  #globalKey(providerId) {
    return `global:${providerId}`;
  }

  #userKey(userId, providerId) {
    return `user:${providerId}:${userId}`;
  }

  #row(key, scope, providerId, userId = null) {
    return (
      this.store.get(key) || {
        key,
        scope,
        providerId,
        userId,
        state: "closed",
        consecutiveFailures: 0,
        openedAt: null,
        retryAt: null,
        lastCode: null,
        probeInFlight: false,
      }
    );
  }

  #grantProbe(row, now) {
    row.state = "half_open";
    row.probeInFlight = true;
    // While half-open, retryAt doubles as the probe lease expiry.
    row.retryAt = now + this.halfOpenProbeLeaseMs;
    this.store.set(row.key, row);
    return { allowed: true, state: "half_open", probe: true, probeLeaseUntil: row.retryAt };
  }

  #allowRow(row) {
    const now = this.clock();
    if (row.state === "closed") {
      return { allowed: true, state: "closed" };
    }
    if (row.state === "half_open") {
      if (row.probeInFlight && row.retryAt !== null && now < row.retryAt) {
        return { allowed: false, state: "half_open", retryAt: row.retryAt, busy: true };
      }
      // A released probe, or one whose lease expired, may be replaced by
      // exactly one new probe.
      return this.#grantProbe(row, now);
    }
    if (row.state === "open" && row.retryAt !== null && now >= row.retryAt) {
      return this.#grantProbe(row, now);
    }
    return { allowed: false, state: "open", retryAt: row.retryAt };
  }

  #releaseProbe(key) {
    const row = this.store.get(key);
    if (!row || row.state !== "half_open" || !row.probeInFlight) {
      return false;
    }
    row.probeInFlight = false;
    this.store.set(key, row);
    return true;
  }

  beforeRequest({ userId, providerId }) {
    const globalKey = this.#globalKey(providerId);
    const userKey = this.#userKey(userId, providerId);
    const global = this.#allowRow(this.#row(globalKey, "global", providerId));
    if (!global.allowed) {
      return Object.freeze({
        allowed: false,
        code: "PROVIDER_CIRCUIT_OPEN",
        message: MESSAGES.global,
        modelCalls: 0,
        scope: "global",
        retryAt: global.retryAt,
      });
    }
    const user = this.#allowRow(
      this.#row(userKey, "user_provider", providerId, userId),
    );
    if (!user.allowed) {
      // The global probe was granted but will not be used: release it so the
      // next caller is not blocked by a probe that never ran.
      if (global.probe) {
        this.#releaseProbe(globalKey);
      }
      return Object.freeze({
        allowed: false,
        code: "USER_PROVIDER_CIRCUIT_OPEN",
        message: MESSAGES.user_provider,
        modelCalls: 0,
        scope: "user_provider",
        retryAt: user.retryAt,
      });
    }
    return Object.freeze({
      allowed: true,
      code: "OK",
      modelCalls: 0,
      probes: { global: Boolean(global.probe), user: Boolean(user.probe) },
    });
  }

  cancelProbes({ userId, providerId, probes = {} }) {
    if (probes.global) {
      this.#releaseProbe(this.#globalKey(providerId));
    }
    if (probes.user) {
      this.#releaseProbe(this.#userKey(userId, providerId));
    }
  }

  // A user-scope failure says nothing about the provider's global health, so
  // the global probe is released rather than consumed, and vice versa.
  cancelOppositeScopeProbe({ userId, providerId, probes = {}, failureCode }) {
    if (USER_FAILURE_CODES.includes(failureCode) && probes.global) {
      this.#releaseProbe(this.#globalKey(providerId));
    }
    if (GLOBAL_FAILURE_CODES.includes(failureCode) && probes.user) {
      this.#releaseProbe(this.#userKey(userId, providerId));
    }
  }

  recordSuccess({ userId, providerId }) {
    this.store.delete(this.#globalKey(providerId));
    this.store.delete(this.#userKey(userId, providerId));
  }

  recordFailure({ userId, providerId, code }) {
    const now = this.clock();
    if (USER_FAILURE_CODES.includes(code)) {
      const key = this.#userKey(userId, providerId);
      const row = this.#row(key, "user_provider", providerId, userId);
      row.consecutiveFailures += 1;
      row.lastCode = code;
      // A rejected or exhausted key will not fix itself: open with no automatic
      // retry until the user replaces it.
      const immediate = code === "CREDENTIAL_INVALID" || code === "NO_BALANCE";
      if (
        immediate ||
        row.state === "half_open" ||
        row.consecutiveFailures >= this.userRateLimitThreshold
      ) {
        row.state = "open";
        row.openedAt = now;
        row.retryAt = immediate ? null : now + this.userOpenMs;
        row.probeInFlight = false;
      }
      this.store.set(key, row);
      return;
    }
    if (GLOBAL_FAILURE_CODES.includes(code)) {
      const key = this.#globalKey(providerId);
      const row = this.#row(key, "global", providerId);
      row.consecutiveFailures += 1;
      row.lastCode = code;
      if (
        row.state === "half_open" ||
        row.consecutiveFailures >= this.globalFailureThreshold
      ) {
        row.state = "open";
        row.openedAt = now;
        row.retryAt = now + this.globalOpenMs;
        row.probeInFlight = false;
      }
      this.store.set(key, row);
    }
  }

  resetUserProvider({ userId, providerId }) {
    this.store.delete(this.#userKey(userId, providerId));
  }

  // AC-048: aggregate only, with no user dimension in the output.
  aggregateStatus() {
    const byProvider = new Map();
    for (const row of this.store.values()) {
      const current = byProvider.get(row.providerId) || {
        providerId: row.providerId,
        globalState: "closed",
        openUserConnections: 0,
        halfOpenCircuits: 0,
        lastCode: null,
      };
      if (row.scope === "global") {
        current.globalState = row.state;
        current.lastCode = row.lastCode;
      }
      if (row.scope === "user_provider" && row.state === "open") {
        current.openUserConnections += 1;
      }
      if (row.state === "half_open") {
        current.halfOpenCircuits += 1;
      }
      byProvider.set(row.providerId, current);
    }
    return [...byProvider.values()]
      .map((row) => Object.freeze(row))
      .sort((left, right) => left.providerId.localeCompare(right.providerId));
  }
}

module.exports = {
  GLOBAL_FAILURE_CODES,
  MESSAGES,
  MemoryCircuitStore,
  ProviderCircuitBreaker,
  USER_FAILURE_CODES,
};

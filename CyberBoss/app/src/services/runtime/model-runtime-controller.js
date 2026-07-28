"use strict";

// CB-700 / AC-017, AC-045, AC-047: the single outbound path for every
// ordinary-user model call. Order matters and is asserted by the CB-700 suite:
//
//   cancel check -> circuit -> budget reservation -> provider -> settle
//
// so a request that fails any guard reaches the provider exactly zero times.

const {
  GLOBAL_FAILURE_CODES,
  USER_FAILURE_CODES,
} = require("./provider-circuit-breaker");

const DEFAULT_REQUEST_TIMEOUT_MS = 60_000;
const MESSAGES = Object.freeze({
  CANCELLED: "这次操作已经停下了。",
  TIMEOUT: "AI 响应超时了，请再发一次。",
  GUARD_UNAVAILABLE: "AI 使用保护暂时不可用，稍后我再帮你试。",
  PROVIDER_UNAVAILABLE: "AI 服务暂时不可用，稍后我再帮你试一次。",
});

class ModelRuntimeController {
  constructor({
    router,
    budgetGuard,
    circuitBreaker,
    requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    setTimeoutImpl = setTimeout,
    clearTimeoutImpl = clearTimeout,
  }) {
    if (!router || !budgetGuard || !circuitBreaker) {
      throw new TypeError("router, budgetGuard and circuitBreaker are required");
    }
    if (!Number.isSafeInteger(requestTimeoutMs) || requestTimeoutMs < 1) {
      throw new TypeError("requestTimeoutMs must be a positive integer");
    }
    if (
      typeof setTimeoutImpl !== "function" ||
      typeof clearTimeoutImpl !== "function"
    ) {
      throw new TypeError("timer functions are required");
    }
    this.router = router;
    this.budget = budgetGuard;
    this.circuit = circuitBreaker;
    this.requestTimeoutMs = requestTimeoutMs;
    this.setTimeoutImpl = setTimeoutImpl;
    this.clearTimeoutImpl = clearTimeoutImpl;
  }

  #cancelProbes(input, probes) {
    try {
      this.circuit.cancelProbes({
        userId: input.userId,
        providerId: input.providerId,
        probes,
      });
      return null;
    } catch (error) {
      return error;
    }
  }

  #recordSuccess(input) {
    try {
      this.circuit.recordSuccess({
        userId: input.userId,
        providerId: input.providerId,
      });
      return null;
    } catch (error) {
      return error;
    }
  }

  #recordFailure(input, code, probes) {
    const failures = [];
    try {
      this.circuit.recordFailure({
        userId: input.userId,
        providerId: input.providerId,
        code,
      });
    } catch (error) {
      failures.push(error);
    }
    try {
      this.circuit.cancelOppositeScopeProbe({
        userId: input.userId,
        providerId: input.providerId,
        probes,
        failureCode: code,
      });
    } catch (error) {
      failures.push(error);
    }
    // An unclassifiable failure is not attributed to either scope, so every
    // probe it holds is released rather than consumed.
    if (
      !USER_FAILURE_CODES.includes(code) &&
      !GLOBAL_FAILURE_CODES.includes(code)
    ) {
      const error = this.#cancelProbes(input, probes);
      if (error) {
        failures.push(error);
      }
    }
    return failures;
  }

  #settleProviderFailure({ reservationId, providerId, code }) {
    try {
      if (USER_FAILURE_CODES.includes(code)) {
        // The provider rejected the credential without doing work.
        this.budget.releaseNoCharge({ reservationId, reason: code });
      } else {
        this.budget.settleUnknown({ reservationId, providerId });
      }
      return null;
    } catch (error) {
      // Leave the durable reservation active: its TTL path charges the full
      // reservation conservatively after a crash or an accounting outage.
      return error;
    }
  }

  async sendText(input) {
    if (input.signal && input.signal.aborted) {
      return Object.freeze({
        ok: false,
        code: "REQUEST_CANCELLED",
        message: MESSAGES.CANCELLED,
        modelCalls: 0,
      });
    }

    let circuit;
    try {
      circuit = this.circuit.beforeRequest({
        userId: input.userId,
        providerId: input.providerId,
      });
    } catch {
      return Object.freeze({
        ok: false,
        code: "MODEL_GUARD_UNAVAILABLE",
        message: MESSAGES.GUARD_UNAVAILABLE,
        modelCalls: 0,
        retryable: true,
      });
    }
    if (!circuit.allowed) {
      return Object.freeze({ ok: false, ...circuit });
    }

    let preflight;
    try {
      preflight = this.budget.preflight({
        requestId: input.requestId,
        userId: input.userId,
        providerId: input.providerId,
        messages: input.messages,
        maxOutputTokens: input.maxOutputTokens,
      });
    } catch {
      this.#cancelProbes(input, circuit.probes);
      return Object.freeze({
        ok: false,
        code: "MODEL_BUDGET_UNAVAILABLE",
        message: MESSAGES.GUARD_UNAVAILABLE,
        modelCalls: 0,
        retryable: true,
      });
    }
    if (!preflight.allowed) {
      this.#cancelProbes(input, circuit.probes);
      return Object.freeze({ ok: false, ...preflight });
    }

    let response;
    let timedOut = false;
    let externallyAborted = false;
    const timeoutController = new AbortController();
    const onExternalAbort = () => {
      externallyAborted = true;
      timeoutController.abort(input.signal && input.signal.reason);
    };
    if (input.signal) {
      input.signal.addEventListener("abort", onExternalAbort, { once: true });
    }
    const timer = this.setTimeoutImpl(() => {
      timedOut = true;
      const error = new Error("MODEL_REQUEST_TIMEOUT");
      error.code = "TIMEOUT";
      timeoutController.abort(error);
    }, this.requestTimeoutMs);

    try {
      response = await this.router.sendText({
        ...input,
        signal: timeoutController.signal,
        maxOutputTokens: preflight.outputCap,
      });
    } catch (error) {
      const code = timedOut
        ? "TIMEOUT"
        : externallyAborted
          ? "REQUEST_CANCELLED"
          : error.code || "PROVIDER_UNAVAILABLE";
      // AC-017: an external cancel is the user's choice, not provider evidence,
      // so it never counts against the circuit.
      const circuitErrors =
        code === "REQUEST_CANCELLED"
          ? []
          : this.#recordFailure(input, code, circuit.probes);
      if (code === "REQUEST_CANCELLED") {
        this.#cancelProbes(input, circuit.probes);
      }
      const accountingError = this.#settleProviderFailure({
        reservationId: preflight.reservationId,
        providerId: input.providerId,
        code,
      });
      return Object.freeze({
        ok: false,
        code,
        message:
          code === "REQUEST_CANCELLED"
            ? MESSAGES.CANCELLED
            : code === "TIMEOUT"
              ? MESSAGES.TIMEOUT
              : error.message || MESSAGES.PROVIDER_UNAVAILABLE,
        modelCalls: 1,
        accountingDegraded: Boolean(accountingError),
        circuitStateDegraded: circuitErrors.length > 0,
      });
    } finally {
      this.clearTimeoutImpl(timer);
      if (input.signal) {
        input.signal.removeEventListener("abort", onExternalAbort);
      }
    }

    let usage;
    let accountingError = null;
    try {
      usage = this.budget.settle({
        reservationId: preflight.reservationId,
        providerId: input.providerId,
        rawUsage: response.usage,
      });
    } catch (error) {
      accountingError = error;
      // AC-046: the provider already produced a valid answer. Turning a
      // bookkeeping outage into a failure would make the user pay for a retry
      // of work that already succeeded. The reservation stays and its TTL
      // charges conservatively.
      usage = Object.freeze({
        reported: false,
        chargedTokens: null,
        fuseAccounting: "pending_conservative_reservation",
      });
    }

    const circuitError = this.#recordSuccess(input);
    if (circuitError) {
      this.#cancelProbes(input, circuit.probes);
    }

    return Object.freeze({
      ok: true,
      response: Object.freeze({ ...response, usage }),
      budgetWarning: preflight.warning,
      accountingDegraded: Boolean(accountingError),
      circuitStateDegraded: Boolean(circuitError),
      modelCalls: 1,
    });
  }
}

module.exports = {
  DEFAULT_REQUEST_TIMEOUT_MS,
  MESSAGES,
  ModelRuntimeController,
};

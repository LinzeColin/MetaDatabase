"use strict";

// Anchor-based integration for the ordinary-user model path. CB-700 built and
// proved the pieces — vault, budget guard, circuit breaker, provider router and
// the controller that orders them. This module is the anchor that assembles
// them once at startup and puts a real inbound turn through them.
//
// The Owner keeps the pre-existing Codex / Claude Code runtime. An ordinary
// user never touches it: `codex.turn` and `claudecode.turn` are Owner-only
// capabilities, so this path is the only way a non-Owner turn can reach a
// model at all.

const { createHmac } = require("node:crypto");

const { FairUserQueue } = require("../services/runtime/fair-user-queue");
const { ModelBudgetGuard } = require("../services/runtime/model-budget-guard");
const {
  ProviderCircuitBreaker,
} = require("../services/runtime/provider-circuit-breaker");
const {
  ModelRuntimeController,
} = require("../services/runtime/model-runtime-controller");
const {
  SqliteCircuitStore,
  SqliteModelBudgetLedger,
} = require("../services/runtime/sqlite-model-budget-store");
const { OFFICIAL_ORIGINS, ProviderRouter } = require("../services/providers/router");
const { SqliteCredentialVault } = require("../services/secrets/credential-vault");

// Server-owned policy. A user chooses among these; a user never supplies an
// origin or a model id, so a compromised account cannot redirect traffic.
const DEFAULT_PROVIDER_POLICIES = Object.freeze({
  openai: Object.freeze({
    providerId: "openai",
    origin: OFFICIAL_ORIGINS.openai,
    models: Object.freeze(["gpt-5-mini", "gpt-5"]),
  }),
  deepseek: Object.freeze({
    providerId: "deepseek",
    origin: OFFICIAL_ORIGINS.deepseek,
    models: Object.freeze(["deepseek-chat", "deepseek-reasoner"]),
  }),
  google: Object.freeze({
    providerId: "google",
    origin: OFFICIAL_ORIGINS.google,
    models: Object.freeze(["gemini-2.5-flash", "gemini-2.5-pro"]),
  }),
  anthropic: Object.freeze({
    providerId: "anthropic",
    origin: OFFICIAL_ORIGINS.anthropic,
    models: Object.freeze(["claude-sonnet-5", "claude-haiku-4-5-20251001"]),
  }),
});

// A bound on the abandoned-entry drain so a corrupted queue can never spin.
const MAX_CLAIM_DRAIN = 32;

const MESSAGES = Object.freeze({
  PROVIDER_NOT_CONFIGURED:
    "还没有连接 AI 服务。回复「设置」打开设置页面，填入你自己的 API Key 就能开始对话。",
  QUEUE_BUSY: "我这边同时处理的消息太多了，稍等一下再发一次。",
  EMPTY_INPUT: "我没有收到文字内容，请再发一次。",
  UNAVAILABLE: "AI 服务暂时不可用，稍后我再帮你试一次。",
});

class UserTurnRuntimeError extends Error {
  constructor(code) {
    super(code);
    this.name = "UserTurnRuntimeError";
    this.code = code;
  }
}

function deriveSubKey(key, info) {
  return createHmac("sha256", key).update(info).digest();
}

class UserTurnRuntime {
  constructor({
    database,
    userRepository,
    encryptionKey,
    providerPolicies = DEFAULT_PROVIDER_POLICIES,
    fetchImpl = globalThis.fetch,
    requestTimeoutMs,
    queueLimits = {},
    clock = () => Date.now(),
  }) {
    if (!database || typeof database.prepare !== "function") {
      throw new UserTurnRuntimeError("DATABASE_REQUIRED");
    }
    if (!userRepository) {
      throw new UserTurnRuntimeError("USER_REPOSITORY_REQUIRED");
    }
    if (!Buffer.isBuffer(encryptionKey) || encryptionKey.length < 32) {
      throw new UserTurnRuntimeError("ENCRYPTION_KEY_REQUIRED");
    }
    this.users = userRepository;
    this.vault = new SqliteCredentialVault({
      database,
      // The vault KEK is derived from the owner-only runtime encryption key, so
      // it is stable across restarts and adds no new secret file to the host.
      masterKey: deriveSubKey(encryptionKey, "cyberboss-credential-vault-kek"),
    });
    const ledger = new SqliteModelBudgetLedger({ database, clock });
    this.controller = new ModelRuntimeController({
      router: new ProviderRouter({ policies: providerPolicies, fetchImpl }),
      budgetGuard: new ModelBudgetGuard({ ledger, clock }),
      circuitBreaker: new ProviderCircuitBreaker({
        store: new SqliteCircuitStore({ database, clock }),
        clock,
      }),
      ...(Number.isSafeInteger(requestTimeoutMs) && requestTimeoutMs > 0
        ? { requestTimeoutMs }
        : {}),
    });
    this.queue = new FairUserQueue(queueLimits);
    this.policies = providerPolicies;
  }

  // The provider and model a user picked, or null when they have not finished
  // setup. A model outside the server allowlist falls back to the first allowed
  // model rather than being sent to the provider.
  resolveSelection(userId) {
    const settings = this.users.getSettings(userId);
    const providerId = settings && settings.provider_id;
    if (!providerId || !this.policies[providerId]) {
      return null;
    }
    const allowed = this.policies[providerId].models;
    const model =
      settings.model_id && allowed.includes(settings.model_id)
        ? settings.model_id
        : allowed[0];
    return Object.freeze({ providerId, model });
  }

  // One ordinary-user turn. Every refusal is a frozen Chinese sentence and
  // costs zero model calls; only the controller may reach a provider, and only
  // after the budget and circuit guards have passed.
  async handleTurn({ userContext, text, requestId, signal = null }) {
    if (!userContext || typeof userContext.requireCapability !== "function") {
      throw new UserTurnRuntimeError("USER_CONTEXT_REQUIRED");
    }
    // Fails closed for pending, suspended, deleting and deleted users.
    userContext.requireCapability("chat.turn");
    const prompt = typeof text === "string" ? text.trim() : "";
    if (!prompt) {
      return Object.freeze({
        ok: false,
        code: "EMPTY_INPUT",
        text: MESSAGES.EMPTY_INPUT,
        modelCalls: 0,
      });
    }

    const selection = this.resolveSelection(userContext.userId);
    if (!selection) {
      return Object.freeze({
        ok: false,
        code: "PROVIDER_NOT_CONFIGURED",
        text: MESSAGES.PROVIDER_NOT_CONFIGURED,
        modelCalls: 0,
      });
    }

    let apiKey;
    try {
      apiKey = this.vault.getCredential({
        userId: userContext.userId,
        providerId: selection.providerId,
      });
    } catch {
      return Object.freeze({
        ok: false,
        code: "PROVIDER_NOT_CONFIGURED",
        text: MESSAGES.PROVIDER_NOT_CONFIGURED,
        modelCalls: 0,
      });
    }

    // AC-008 / AC-009 at the anchor: admission is per user and the request id
    // is the idempotency key, so a redelivered WeChat message cannot produce a
    // second charged turn and one user cannot crowd out another.
    const admitted = this.queue.enqueue({
      jobId: requestId,
      userId: userContext.userId,
      isOwner: userContext.isOwner,
    });
    if (!admitted.admitted) {
      return Object.freeze({
        ok: false,
        code: admitted.reason === "duplicate_job" ? "DUPLICATE_TURN" : "QUEUE_BUSY",
        text: admitted.reason === "duplicate_job" ? "" : MESSAGES.QUEUE_BUSY,
        modelCalls: 0,
        suppressReply: admitted.reason === "duplicate_job",
      });
    }
    // Claimed synchronously, with no await between enqueue and claim, so no
    // other turn can interleave and the head of the rotation is this job unless
    // a previous turn was refused admission and abandoned its entry. Those are
    // the only foreign jobs that can appear here, and draining them is the
    // cleanup their own handler could not perform.
    const claimed = this.#claimOwnJob(requestId);
    if (!claimed) {
      return Object.freeze({
        ok: false,
        code: "QUEUE_BUSY",
        text: MESSAGES.QUEUE_BUSY,
        modelCalls: 0,
      });
    }

    try {
      const result = await this.controller.sendText({
        requestId,
        userId: userContext.userId,
        providerId: selection.providerId,
        model: selection.model,
        apiKey,
        messages: [{ role: "user", content: prompt }],
        signal,
      });
      if (result.ok) {
        return Object.freeze({
          ok: true,
          code: "OK",
          text: result.response.text,
          providerId: selection.providerId,
          model: selection.model,
          modelCalls: result.modelCalls,
        });
      }
      return Object.freeze({
        ok: false,
        code: result.code,
        text: result.message || MESSAGES.UNAVAILABLE,
        modelCalls: result.modelCalls,
      });
    } finally {
      // The plaintext key never outlives the request that needed it.
      apiKey = null;
      this.queue.complete(requestId);
    }
  }

  #claimOwnJob(requestId) {
    for (let guard = 0; guard < MAX_CLAIM_DRAIN; guard += 1) {
      const next = this.queue.claimNext();
      if (!next) {
        return null;
      }
      if (next.jobId === requestId) {
        return next;
      }
      this.queue.complete(next.jobId);
    }
    return null;
  }
}

module.exports = {
  DEFAULT_PROVIDER_POLICIES,
  MESSAGES,
  UserTurnRuntime,
  UserTurnRuntimeError,
  deriveSubKey,
};

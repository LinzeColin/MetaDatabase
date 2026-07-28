"use strict";

// Anchor-based integration for the setup portal's nine frozen actions. The
// SetupPortal is the request boundary — origin, host, action, body size, session
// and CSRF are all decided there. This module is what the boundary calls once a
// request has survived it, and it binds the real services rather than stubs.
//
// The acting user id is supplied by the portal from the server-side session row.
// No handler here may read a user id out of the request body: the portal has
// already stripped it, and every store call is scoped to the session's user.

const { parseImportIsolating, SOURCES } = require("../imports/router");
const { mergePolicy, validateArchiveManifest } = require("../imports/upload-policy");
const { SqliteImportLedger } = require("../imports/import-ledger");
const { SqliteProfileStore } = require("../profile/profile-store");
const { buildDeletionPlan } = require("../privacy/deletion-plan");
const {
  SqliteDeletionReceiptStore,
  SqliteUserExporter,
} = require("../privacy/user-data-lifecycle");
const { PROVIDER_IDS } = require("../providers/policy");

class PortalHandlerError extends Error {
  constructor(code, status = 400) {
    super(code);
    this.name = "PortalHandlerError";
    this.code = code;
    this.status = status;
  }
}

function requireProviderId(value) {
  const providerId = String(value ?? "");
  if (!PROVIDER_IDS.includes(providerId)) {
    throw new PortalHandlerError("PROVIDER_NOT_SUPPORTED", 400);
  }
  return providerId;
}

// Builds the frozen action map the SetupPortal expects. Every entry is bound to
// a real store; an action with no backing service is deliberately absent, so
// the portal answers ACTION_NOT_IMPLEMENTED rather than pretending it worked.
function buildPortalHandlers({
  database,
  vault,
  userRepository,
  providerPolicies,
  uploadPolicy = {},
  now = () => new Date(),
}) {
  if (!database || typeof database.prepare !== "function") {
    throw new PortalHandlerError("DATABASE_REQUIRED", 500);
  }
  if (!vault) {
    throw new PortalHandlerError("VAULT_REQUIRED", 500);
  }
  const profiles = new SqliteProfileStore({ database, now });
  const exporter = new SqliteUserExporter({ database });
  const receipts = new SqliteDeletionReceiptStore({ database });
  const imports = new SqliteImportLedger({ database });
  const policy = mergePolicy(uploadPolicy);

  return Object.freeze({
    // AC-013: the key is written straight into the per-user envelope. It is
    // never echoed back and never logged; only the last four digits leave here.
    "provider.save"({ userId, payload }) {
      const providerId = requireProviderId(payload.provider_id);
      const apiKey = typeof payload.api_key === "string" ? payload.api_key : "";
      if (!apiKey) {
        throw new PortalHandlerError("API_KEY_REQUIRED", 400);
      }
      const saved = vault.putCredential({ userId, providerId, apiKey });
      const models = providerPolicies?.[providerId]?.models || [];
      const model = models.includes(payload.model_id) ? payload.model_id : models[0];
      database
        .prepare(
          `UPDATE user_settings SET provider_id=?, model_id=?, updated_at=?
           WHERE user_id=?`,
        )
        .run(providerId, model || null, new Date(now()).toISOString(), userId);
      return Object.freeze({
        ok: true,
        provider_id: providerId,
        model_id: model || null,
        last4: saved?.last4 ?? null,
      });
    },

    "provider.remove"({ userId, payload }) {
      const providerId = requireProviderId(payload.provider_id);
      const removed = vault.revokeCredential({ userId, providerId });
      return Object.freeze({ ok: removed, provider_id: providerId });
    },

    // AC-021: an inference the user rejected is recorded as rejected and does
    // not reappear; the store, not this handler, is what enforces that.
    "profile.decide"({ userId, payload }) {
      const decided = profiles.decide({
        userId,
        category: payload.category,
        factKey: payload.fact_key,
        decision: payload.decision,
        value: payload.value,
        appliesToFuture: payload.applies_to_future !== false,
      });
      return Object.freeze({ ok: true, decision: decided });
    },

    // AC-035: the export carries this user's rows only, and the scope is proved
    // on the assembled result rather than trusted from the query.
    "privacy.export"({ userId, payload }) {
      const manifest = exporter.export({
        userId,
        objectRefs: Array.isArray(payload.object_refs) ? payload.object_refs : [],
      });
      return Object.freeze({ ok: true, manifest });
    },

    // AC-036: the plan is returned for confirmation, never executed here. Two of
    // its nine steps are irreversible, so the confirmation is the point.
    "privacy.delete"({ userId, payload }) {
      const requestId = String(payload.request_id ?? "");
      const steps = buildDeletionPlan({ userId, requestId });
      const done = receipts.listForRequest({ userId, requestId });
      return Object.freeze({
        ok: true,
        request_id: requestId,
        steps,
        completed_steps: done.length,
        irreversible_steps: steps
          .filter((step) => step.irreversible)
          .map((step) => step.action),
      });
    },

    // AC-018 / AC-019: the archive manifest is validated before a single entry
    // is read, so an oversized archive, a compression bomb or a traversal entry
    // is refused at the boundary rather than inside a parser.
    "import.presign"({ userId, payload }) {
      const manifest = validateArchiveManifest(
        {
          archiveBytes: payload.archive_bytes,
          files: Array.isArray(payload.files) ? payload.files : [],
        },
        policy,
      );
      const source = String(payload.source ?? "");
      if (!SOURCES.includes(source)) {
        throw new PortalHandlerError("IMPORT_SOURCE_UNSUPPORTED", 400);
      }
      const ticket = imports.begin({
        userId,
        source,
        sourceHash: String(payload.source_hash ?? ""),
        objectRef: String(payload.object_ref ?? ""),
      });
      return Object.freeze({ ok: true, manifest, import_id: ticket.import_id ?? ticket.importId ?? null });
    },

    // AC-020: parsing is isolated per conversation, so one malformed record
    // cannot lose the rest of the archive.
    "import.commit"({ userId, payload }) {
      const source = String(payload.source ?? "");
      if (!SOURCES.includes(source)) {
        throw new PortalHandlerError("IMPORT_SOURCE_UNSUPPORTED", 400);
      }
      const parsed = parseImportIsolating({
        source,
        input: payload.input,
        format: payload.format,
      });
      const conversations = parsed.conversations?.length ?? 0;
      const record = imports.get(String(payload.import_id ?? ""));
      if (!record || record.user_id !== userId) {
        // Refused rather than filtered: an import id that is not this user's is
        // an IDOR attempt and is visible in the response code.
        throw new PortalHandlerError("USER_SCOPE_VIOLATION", 403);
      }
      const completed = imports.complete({
        importId: record.import_id,
        importedRecords: conversations,
      });
      return Object.freeze({
        ok: true,
        imported: completed,
        conversations,
        skipped: parsed.skipped?.length ?? 0,
      });
    },
  });
}

module.exports = { PortalHandlerError, buildPortalHandlers };

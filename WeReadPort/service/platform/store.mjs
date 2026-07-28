import { readFileSync, mkdirSync, chmodSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

export class PlatformStore {
  constructor(databasePath = ":memory:", { clock = () => Date.now() } = {}) {
    if (databasePath !== ":memory:") mkdirSync(path.dirname(databasePath), { recursive: true, mode: 0o700 });
    this.db = new DatabaseSync(databasePath);
    this.clock = clock;
    this.databasePath = databasePath;
    const schema = readFileSync(new URL("../schema.sql", import.meta.url), "utf8");
    this.db.exec(schema);
    this.migrateCompatibilityColumns();
    if (databasePath !== ":memory:") {
      try { chmodSync(databasePath, 0o600); } catch { /* file can be created lazily by a test fixture */ }
    }
  }

  close() { this.db.close(); }
  now() { return Math.floor(this.clock() / 1000); }
  transaction(callback) {
    this.db.exec("BEGIN IMMEDIATE");
    try { const result = callback(); this.db.exec("COMMIT"); return result; }
    catch (error) { this.db.exec("ROLLBACK"); throw error; }
  }

  migrateCompatibilityColumns() {
    this.ensureColumn("sessions", "id", "TEXT");
    this.ensureColumn("sessions", "last_seen_at", "INTEGER NOT NULL DEFAULT 0");
    this.ensureColumn("import_jobs", "selection_encrypted", "TEXT");
    this.ensureColumn("import_jobs", "attempts", "INTEGER NOT NULL DEFAULT 0");
    this.ensureColumn("import_jobs", "worker_id", "TEXT");
    this.ensureColumn("import_jobs", "lease_until", "INTEGER");
    this.db.exec("CREATE UNIQUE INDEX IF NOT EXISTS sessions_public_id_idx ON sessions(id) WHERE id IS NOT NULL");
    this.db.exec("CREATE INDEX IF NOT EXISTS import_jobs_queue_idx ON import_jobs(state, lease_until, created_at)");
  }

  ensureColumn(table, column, definition) {
    const columns = this.db.prepare(`PRAGMA table_info(${table})`).all().map(row => row.name);
    if (!columns.includes(column)) this.db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }

  healthCheck() {
    const selected = this.db.prepare("SELECT 1 AS value").get();
    const quick = this.db.prepare("PRAGMA quick_check(1)").get();
    const result = String(quick?.quick_check ?? quick?.[Object.keys(quick || {})[0]] ?? "");
    return { ok: Number(selected?.value) === 1 && result === "ok", quickCheck: result || "unknown" };
  }

  createAccount({ id, email = null, displayName, wrappedDek, keyId }) {
    const now = this.now();
    this.transaction(() => {
      this.db.prepare("INSERT INTO accounts(id,email,display_name,created_at,updated_at) VALUES(?,?,?,?,?)").run(id, email, displayName, now, now);
      this.db.prepare("INSERT INTO account_keys(account_id,wrapped_dek,key_id,updated_at) VALUES(?,?,?,?)").run(id, wrappedDek, keyId, now);
      this.db.prepare("INSERT INTO consents(account_id,behavior_analytics,recommendation_personalization,updated_at) VALUES(?,?,?,?)").run(id, 0, 0, now);
      this.db.prepare("INSERT INTO weread_sync_state(account_id,updated_at) VALUES(?,?)").run(id, now);
    });
    return this.getAccount(id);
  }

  getAccount(id) {
    return this.db.prepare("SELECT id,email,display_name AS displayName,locale,status,created_at AS createdAt,updated_at AS updatedAt,deleted_at AS deletedAt FROM accounts WHERE id=? AND deleted_at IS NULL").get(id) ?? null;
  }

  updateAccount(id, { displayName, email, locale }) {
    const account = this.getAccount(id);
    if (!account) return null;
    this.db.prepare("UPDATE accounts SET display_name=?,email=?,locale=?,updated_at=? WHERE id=? AND deleted_at IS NULL")
      .run(displayName ?? account.displayName, email === undefined ? account.email : email, locale ?? account.locale, this.now(), id);
    return this.getAccount(id);
  }

  getAccountKey(id) {
    return this.db.prepare("SELECT wrapped_dek AS wrappedDek,key_id AS keyId FROM account_keys WHERE account_id=?").get(id) ?? null;
  }

  updateAccountKey(id, { wrappedDek, keyId }) {
    const result = this.db.prepare("UPDATE account_keys SET wrapped_dek=?,key_id=?,updated_at=? WHERE account_id=?")
      .run(wrappedDek, keyId, this.now(), id);
    return Number(result.changes) === 1;
  }

  addCredential({ id, accountId, kind, provider, subject, secretHash = null, secretEncrypted = null, metadata = {} }) {
    const now = this.now();
    this.db.prepare("INSERT INTO credentials(id,account_id,kind,provider,provider_subject,secret_hash,secret_encrypted,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)")
      .run(id, accountId, kind, provider, subject, secretHash, secretEncrypted, JSON.stringify(metadata), now, now);
    return this.findCredential(kind, provider, subject);
  }

  updateCredentialSecret(id, { subject, secretHash, secretEncrypted, metadata }) {
    const current = this.db.prepare("SELECT * FROM credentials WHERE id=?").get(id);
    if (!current) return null;
    this.db.prepare("UPDATE credentials SET provider_subject=?,secret_hash=?,secret_encrypted=?,metadata_json=?,updated_at=? WHERE id=?")
      .run(subject ?? current.provider_subject, secretHash ?? current.secret_hash, secretEncrypted ?? current.secret_encrypted, metadata ? JSON.stringify(metadata) : current.metadata_json, this.now(), id);
    return this.db.prepare("SELECT * FROM credentials WHERE id=?").get(id);
  }

  findCredential(kind, provider, subject) {
    const row = this.db.prepare("SELECT id,account_id AS accountId,kind,provider,provider_subject AS subject,secret_hash AS secretHash,secret_encrypted AS secretEncrypted,metadata_json AS metadataJson,created_at AS createdAt,updated_at AS updatedAt FROM credentials WHERE kind=? AND provider=? AND provider_subject=?").get(kind, provider, subject);
    return row ? { ...row, metadata: parseJson(row.metadataJson) } : null;
  }

  findCredentialByAccount(accountId, kind, provider) {
    const row = this.db.prepare("SELECT id,account_id AS accountId,kind,provider,provider_subject AS subject,secret_hash AS secretHash,secret_encrypted AS secretEncrypted,metadata_json AS metadataJson,created_at AS createdAt,updated_at AS updatedAt FROM credentials WHERE account_id=? AND kind=? AND provider=? ORDER BY created_at LIMIT 1").get(accountId, kind, provider);
    return row ? { ...row, metadata: parseJson(row.metadataJson) } : null;
  }

  listCredentials(accountId) {
    return this.db.prepare("SELECT id,kind,provider,provider_subject AS subject,metadata_json AS metadataJson,created_at AS createdAt,updated_at AS updatedAt FROM credentials WHERE account_id=? ORDER BY created_at")
      .all(accountId).map(row => ({ ...row, metadata: parseJson(row.metadataJson) }));
  }

  deleteCredential(accountId, credentialId) {
    return Number(this.db.prepare("DELETE FROM credentials WHERE id=? AND account_id=?").run(credentialId, accountId).changes) === 1;
  }

  createSession({ id, tokenHash, accountId, csrfHash, expiresAt, recentAuthAt, userAgentHash = null, ipPrefixHash = null }) {
    const now = this.now();
    this.db.prepare("INSERT INTO sessions(token_hash,id,account_id,csrf_hash,created_at,last_seen_at,expires_at,recent_auth_at,user_agent_hash,ip_prefix_hash) VALUES(?,?,?,?,?,?,?,?,?,?)")
      .run(tokenHash, id, accountId, csrfHash, now, now, expiresAt, recentAuthAt, userAgentHash, ipPrefixHash);
  }

  getSession(tokenHash) {
    const row = this.db.prepare("SELECT s.token_hash AS tokenHash,COALESCE(s.id,s.token_hash) AS id,s.account_id AS accountId,s.csrf_hash AS csrfHash,s.created_at AS createdAt,s.last_seen_at AS lastSeenAt,s.expires_at AS expiresAt,s.recent_auth_at AS recentAuthAt,s.user_agent_hash AS userAgentHash,s.ip_prefix_hash AS ipPrefixHash FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires_at>? AND a.deleted_at IS NULL AND a.status='ACTIVE'").get(tokenHash, this.now());
    if (row) this.db.prepare("UPDATE sessions SET last_seen_at=? WHERE token_hash=?").run(this.now(), tokenHash);
    return row ?? null;
  }

  rotateSession(tokenHash, { newTokenHash, newCsrfHash, expiresAt, recentAuthAt }) {
    const result = this.db.prepare("UPDATE sessions SET token_hash=?,csrf_hash=?,expires_at=?,recent_auth_at=?,last_seen_at=? WHERE token_hash=?")
      .run(newTokenHash, newCsrfHash, expiresAt, recentAuthAt, this.now(), tokenHash);
    return Number(result.changes) === 1;
  }

  updateRecentAuth(tokenHash) {
    this.db.prepare("UPDATE sessions SET recent_auth_at=?,last_seen_at=? WHERE token_hash=?").run(this.now(), this.now(), tokenHash);
  }

  listSessions(accountId) {
    return this.db.prepare("SELECT COALESCE(id,token_hash) AS id,created_at AS createdAt,last_seen_at AS lastSeenAt,expires_at AS expiresAt,user_agent_hash AS userAgentHash,ip_prefix_hash AS ipPrefixHash FROM sessions WHERE account_id=? AND expires_at>? ORDER BY last_seen_at DESC,created_at DESC").all(accountId, this.now());
  }

  deleteSession(tokenHash) { return Number(this.db.prepare("DELETE FROM sessions WHERE token_hash=?").run(tokenHash).changes) === 1; }
  deleteSessionById(accountId, id) { return Number(this.db.prepare("DELETE FROM sessions WHERE account_id=? AND COALESCE(id,token_hash)=?").run(accountId, id).changes) === 1; }
  deleteOtherSessions(accountId, keepTokenHash) { return Number(this.db.prepare("DELETE FROM sessions WHERE account_id=? AND token_hash<>?").run(accountId, keepTokenHash).changes); }
  deleteExpiredSessions() { return Number(this.db.prepare("DELETE FROM sessions WHERE expires_at<=?").run(this.now()).changes); }

  assertAuthAllowed(bucketKey, { windowSeconds, lockSeconds }) {
    const now = this.now();
    const row = this.db.prepare("SELECT failures,first_failure_at AS firstFailureAt,locked_until AS lockedUntil FROM auth_throttle WHERE bucket_key=?").get(bucketKey);
    if (!row) return { allowed: true, remainingLockSeconds: 0 };
    if (Number(row.lockedUntil || 0) > now) return { allowed: false, remainingLockSeconds: Number(row.lockedUntil) - now };
    if (now - Number(row.firstFailureAt || 0) >= windowSeconds) {
      this.db.prepare("DELETE FROM auth_throttle WHERE bucket_key=?").run(bucketKey);
      return { allowed: true, remainingLockSeconds: 0 };
    }
    return { allowed: true, remainingLockSeconds: 0 };
  }

  recordAuthFailure(bucketKey, { limit, windowSeconds, lockSeconds }) {
    const now = this.now();
    return this.transaction(() => {
      const row = this.db.prepare("SELECT failures,first_failure_at AS firstFailureAt,locked_until AS lockedUntil FROM auth_throttle WHERE bucket_key=?").get(bucketKey);
      let failures = 1;
      let firstFailureAt = now;
      if (row && now - Number(row.firstFailureAt || 0) < windowSeconds) {
        failures = Number(row.failures || 0) + 1;
        firstFailureAt = Number(row.firstFailureAt || now);
      }
      const lockedUntil = failures >= limit ? now + lockSeconds : 0;
      this.db.prepare(`INSERT INTO auth_throttle(bucket_key,failures,first_failure_at,locked_until,updated_at) VALUES(?,?,?,?,?)
        ON CONFLICT(bucket_key) DO UPDATE SET failures=excluded.failures,first_failure_at=excluded.first_failure_at,locked_until=excluded.locked_until,updated_at=excluded.updated_at`)
        .run(bucketKey, failures, firstFailureAt, lockedUntil, now);
      this.db.prepare("DELETE FROM auth_throttle WHERE updated_at<?").run(now - Math.max(windowSeconds, lockSeconds) * 4);
      return { failures, lockedUntil };
    });
  }

  clearAuthFailures(bucketKey) { this.db.prepare("DELETE FROM auth_throttle WHERE bucket_key=?").run(bucketKey); }

  createOAuthTransaction({ stateHash, provider, intent, accountId = null, verifierEncrypted = null, redirectUri, expiresAt }) {
    const now = this.now();
    this.db.prepare("INSERT INTO oauth_transactions(state_hash,provider,intent,account_id,verifier_encrypted,redirect_uri,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)")
      .run(stateHash, provider, intent, accountId, verifierEncrypted, redirectUri, now, expiresAt);
  }

  consumeOAuthTransaction(stateHash) {
    return this.transaction(() => {
      const row = this.db.prepare("SELECT state_hash AS stateHash,provider,intent,account_id AS accountId,verifier_encrypted AS verifierEncrypted,redirect_uri AS redirectUri,created_at AS createdAt,expires_at AS expiresAt FROM oauth_transactions WHERE state_hash=?").get(stateHash);
      this.db.prepare("DELETE FROM oauth_transactions WHERE state_hash=?").run(stateHash);
      if (!row || row.expiresAt <= this.now()) return null;
      return row;
    });
  }

  upsertConnection({ id, accountId, provider, providerSubject, accessTokenEncrypted, refreshTokenEncrypted = null, scopes = "", expiresAt = null, metadata = {} }) {
    const now = this.now();
    this.db.prepare(`INSERT INTO provider_connections(id,account_id,provider,provider_subject,access_token_encrypted,refresh_token_encrypted,scopes,expires_at,metadata_json,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(account_id,provider) DO UPDATE SET provider_subject=excluded.provider_subject,access_token_encrypted=excluded.access_token_encrypted,refresh_token_encrypted=excluded.refresh_token_encrypted,scopes=excluded.scopes,expires_at=excluded.expires_at,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at`)
      .run(id, accountId, provider, providerSubject, accessTokenEncrypted, refreshTokenEncrypted, scopes, expiresAt, JSON.stringify(metadata), now, now);
    return this.getConnection(accountId, provider);
  }

  getConnection(accountId, provider) {
    const row = this.db.prepare("SELECT id,account_id AS accountId,provider,provider_subject AS providerSubject,access_token_encrypted AS accessTokenEncrypted,refresh_token_encrypted AS refreshTokenEncrypted,scopes,expires_at AS expiresAt,metadata_json AS metadataJson,created_at AS createdAt,updated_at AS updatedAt FROM provider_connections WHERE account_id=? AND provider=?").get(accountId, provider);
    return row ? { ...row, metadata: parseJson(row.metadataJson) } : null;
  }

  listConnections(accountId) {
    return this.db.prepare("SELECT provider,provider_subject AS providerSubject,scopes,expires_at AS expiresAt,metadata_json AS metadataJson,updated_at AS updatedAt FROM provider_connections WHERE account_id=? ORDER BY provider")
      .all(accountId).map(row => ({ ...row, metadata: parseJson(row.metadataJson) }));
  }

  deleteConnection(accountId, provider) {
    return Number(this.db.prepare("DELETE FROM provider_connections WHERE account_id=? AND provider=?").run(accountId, provider).changes) === 1;
  }

  upsertNote({ id, accountId, source, externalId, title, objectKey, contentHash, wordCount = 0, category = null, expectedVersion = null }) {
    const now = this.now();
    return this.transaction(() => {
      const current = this.findNote(accountId, source, externalId);
      if (current && expectedVersion !== null && Number(current.version) !== Number(expectedVersion)) return { conflict: true, current };
      const noteId = current?.id || id;
      const version = Number(current?.version || 0) + 1;
      const createdAt = current?.createdAt || now;
      this.db.prepare(`INSERT INTO notes(id,account_id,source,external_id,title,object_key,content_hash,word_count,category,version,created_at,updated_at,deleted_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL)
        ON CONFLICT(account_id,source,external_id) DO UPDATE SET title=excluded.title,object_key=excluded.object_key,content_hash=excluded.content_hash,word_count=excluded.word_count,category=excluded.category,version=excluded.version,updated_at=excluded.updated_at,deleted_at=NULL`)
        .run(noteId, accountId, source, externalId, title, objectKey, contentHash, wordCount, category, version, createdAt, now);
      this.db.prepare("INSERT OR IGNORE INTO note_objects(object_key,account_id,note_id,created_at) VALUES(?,?,?,?)").run(objectKey, accountId, noteId, now);
      this.appendSyncEvent({ accountId, entityType: "note", entityId: noteId, operation: current ? "UPDATE" : "CREATE", entityVersion: version, payloadHash: contentHash, occurredAt: now });
      return { conflict: false, note: this.getNote(accountId, noteId) };
    });
  }

  getNote(accountId, id) {
    return this.db.prepare("SELECT id,account_id AS accountId,source,external_id AS externalId,title,object_key AS objectKey,content_hash AS contentHash,word_count AS wordCount,category,version,created_at AS createdAt,updated_at AS updatedAt,deleted_at AS deletedAt FROM notes WHERE account_id=? AND id=?").get(accountId, id) ?? null;
  }

  findNote(accountId, source, externalId) {
    return this.db.prepare("SELECT id,account_id AS accountId,source,external_id AS externalId,title,object_key AS objectKey,content_hash AS contentHash,word_count AS wordCount,category,version,created_at AS createdAt,updated_at AS updatedAt,deleted_at AS deletedAt FROM notes WHERE account_id=? AND source=? AND external_id=?").get(accountId, source, externalId) ?? null;
  }

  listNotes(accountId, { includeDeleted = false, limit = 200, afterUpdatedAt = 0, afterId = "" } = {}) {
    const deleted = includeDeleted ? "" : "AND deleted_at IS NULL";
    return this.db.prepare(`SELECT id,account_id AS accountId,source,external_id AS externalId,title,object_key AS objectKey,content_hash AS contentHash,word_count AS wordCount,category,version,created_at AS createdAt,updated_at AS updatedAt,deleted_at AS deletedAt FROM notes WHERE account_id=? ${deleted} AND (updated_at>? OR (updated_at=? AND id>?)) ORDER BY updated_at,id LIMIT ?`)
      .all(accountId, afterUpdatedAt, afterUpdatedAt, afterId, limit);
  }

  deleteNote(accountId, id, expectedVersion = null) {
    const now = this.now();
    return this.transaction(() => {
      const current = this.getNote(accountId, id);
      if (!current || current.deletedAt) return { deleted: false, missing: true };
      if (expectedVersion !== null && Number(current.version) !== Number(expectedVersion)) return { deleted: false, conflict: true, current };
      const version = Number(current.version) + 1;
      this.db.prepare("UPDATE notes SET version=?,updated_at=?,deleted_at=? WHERE account_id=? AND id=?").run(version, now, now, accountId, id);
      this.appendSyncEvent({ accountId, entityType: "note", entityId: id, operation: "DELETE", entityVersion: version, payloadHash: current.contentHash, occurredAt: now });
      return { deleted: true, note: this.getNote(accountId, id) };
    });
  }

  appendSyncEvent({ accountId, entityType, entityId, operation, entityVersion, payloadHash, occurredAt = this.now() }) {
    const result = this.db.prepare("INSERT INTO sync_events(account_id,entity_type,entity_id,operation,entity_version,payload_hash,occurred_at) VALUES(?,?,?,?,?,?,?)")
      .run(accountId, entityType, entityId, operation, entityVersion, payloadHash, occurredAt);
    return Number(result.lastInsertRowid);
  }

  listSyncEvents(accountId, cursor = 0, limit = 500) {
    return this.db.prepare("SELECT seq,entity_type AS entityType,entity_id AS entityId,operation,entity_version AS entityVersion,payload_hash AS payloadHash,occurred_at AS occurredAt FROM sync_events WHERE account_id=? AND seq>? ORDER BY seq LIMIT ?")
      .all(accountId, cursor, limit);
  }

  getConsent(accountId) {
    const row = this.db.prepare("SELECT behavior_analytics AS behaviorAnalytics,recommendation_personalization AS recommendationPersonalization,updated_at AS updatedAt FROM consents WHERE account_id=?").get(accountId);
    return row ? { ...row, behaviorAnalytics: Boolean(row.behaviorAnalytics), recommendationPersonalization: Boolean(row.recommendationPersonalization) } : null;
  }

  updateConsent(accountId, { behaviorAnalytics, recommendationPersonalization }) {
    this.db.prepare("UPDATE consents SET behavior_analytics=?,recommendation_personalization=?,updated_at=? WHERE account_id=?")
      .run(behaviorAnalytics ? 1 : 0, recommendationPersonalization ? 1 : 0, this.now(), accountId);
    if (!behaviorAnalytics) this.db.prepare("DELETE FROM behavior_events WHERE account_id=?").run(accountId);
    return this.getConsent(accountId);
  }

  addBehaviorEvent({ id, accountId, eventType, value = {}, occurredAt = this.now() }) {
    if (!this.getConsent(accountId)?.behaviorAnalytics) return false;
    this.db.prepare("INSERT INTO behavior_events(id,account_id,event_type,value_json,occurred_at) VALUES(?,?,?,?,?)")
      .run(id, accountId, eventType, JSON.stringify(value), occurredAt);
    return true;
  }

  listBehaviorEvents(accountId, since = 0, limit = 5000) {
    return this.db.prepare("SELECT id,event_type AS eventType,value_json AS valueJson,occurred_at AS occurredAt FROM behavior_events WHERE account_id=? AND occurred_at>=? ORDER BY occurred_at DESC LIMIT ?")
      .all(accountId, since, limit).map(row => ({ ...row, value: parseJson(row.valueJson) }));
  }

  createImportJob({ id, accountId, provider, selectionEncrypted, idempotencyKey }) {
    const now = this.now();
    try {
      this.db.prepare("INSERT INTO import_jobs(id,account_id,provider,state,selection_json,selection_encrypted,progress_json,idempotency_key,attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)")
        .run(id, accountId, provider, "PENDING", "{}", selectionEncrypted, "{}", idempotencyKey, 0, now, now);
    } catch (error) {
      const existing = this.db.prepare("SELECT id FROM import_jobs WHERE account_id=? AND idempotency_key=?").get(accountId, idempotencyKey);
      if (!existing) throw error;
      return this.getImportJob(accountId, existing.id);
    }
    return this.getImportJob(accountId, id);
  }

  getImportJob(accountId, id) {
    const row = this.db.prepare("SELECT id,account_id AS accountId,provider,state,selection_encrypted AS selectionEncrypted,progress_json AS progressJson,idempotency_key AS idempotencyKey,error_code AS errorCode,attempts,worker_id AS workerId,lease_until AS leaseUntil,created_at AS createdAt,updated_at AS updatedAt FROM import_jobs WHERE account_id=? AND id=?").get(accountId, id);
    return row ? { ...row, progress: parseJson(row.progressJson) } : null;
  }

  listLegacyImportSelections() {
    return this.db.prepare("SELECT id,account_id AS accountId,selection_json AS selectionJson FROM import_jobs WHERE selection_encrypted IS NULL AND selection_json IS NOT NULL AND selection_json NOT IN ('','{}')").all();
  }

  migrateImportSelection(accountId, id, selectionEncrypted) {
    this.db.prepare("UPDATE import_jobs SET selection_encrypted=?,selection_json='{}',updated_at=? WHERE account_id=? AND id=?")
      .run(selectionEncrypted, this.now(), accountId, id);
  }

  claimNextImportJob(workerId = "import-worker", leaseSeconds = 300) {
    return this.transaction(() => {
      const now = this.now();
      this.db.prepare("UPDATE import_jobs SET state='PENDING',worker_id=NULL,lease_until=NULL,updated_at=? WHERE state='RUNNING' AND lease_until IS NOT NULL AND lease_until<=?").run(now, now);
      const row = this.db.prepare("SELECT account_id AS accountId,id FROM import_jobs WHERE state='PENDING' ORDER BY created_at LIMIT 1").get();
      if (!row) return null;
      const changed = this.db.prepare("UPDATE import_jobs SET state='RUNNING',worker_id=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=? AND state='PENDING'")
        .run(workerId, now + leaseSeconds, now, row.id);
      return Number(changed.changes) === 1 ? this.getImportJob(row.accountId, row.id) : null;
    });
  }

  updateImportJob(accountId, id, { state, progress, errorCode = null, clearSelection = false }) {
    this.db.prepare("UPDATE import_jobs SET state=?,progress_json=?,error_code=?,worker_id=NULL,lease_until=NULL,selection_encrypted=CASE WHEN ? THEN NULL ELSE selection_encrypted END,selection_json='{}',updated_at=? WHERE account_id=? AND id=?")
      .run(state, JSON.stringify(progress ?? {}), errorCode, clearSelection ? 1 : 0, this.now(), accountId, id);
    return this.getImportJob(accountId, id);
  }

  heartbeat(workerId, workerType = "import", version = "v0.0.0.1.9") {
    const now = this.now();
    this.db.prepare(`INSERT INTO worker_heartbeats(worker_id,worker_type,version,heartbeat_at) VALUES(?,?,?,?)
      ON CONFLICT(worker_id) DO UPDATE SET worker_type=excluded.worker_type,version=excluded.version,heartbeat_at=excluded.heartbeat_at`)
      .run(workerId, workerType, version, now);
    return { workerId, workerType, version, heartbeatAt: now };
  }

  workerHealth(workerType = "import", maxAgeSeconds = 30) {
    const row = this.db.prepare("SELECT worker_id AS workerId,version,MAX(heartbeat_at) AS heartbeatAt FROM worker_heartbeats WHERE worker_type=?").get(workerType);
    const ageSeconds = row?.heartbeatAt ? this.now() - Number(row.heartbeatAt) : null;
    return { ok: ageSeconds !== null && ageSeconds <= maxAgeSeconds, workerId: row?.workerId || null, version: row?.version || null, heartbeatAt: row?.heartbeatAt || null, ageSeconds };
  }

  updateWereadState(accountId, { capabilities, summary, lastSyncAt = this.now() }) {
    this.db.prepare("UPDATE weread_sync_state SET capabilities_json=?,summary_json=?,last_sync_at=?,updated_at=? WHERE account_id=?")
      .run(JSON.stringify(capabilities ?? []), JSON.stringify(summary ?? {}), lastSyncAt, this.now(), accountId);
  }

  getWereadState(accountId) {
    const row = this.db.prepare("SELECT capabilities_json AS capabilitiesJson,summary_json AS summaryJson,last_sync_at AS lastSyncAt,updated_at AS updatedAt FROM weread_sync_state WHERE account_id=?").get(accountId);
    return row ? { capabilities: parseArray(row.capabilitiesJson), summary: parseJson(row.summaryJson), lastSyncAt: row.lastSyncAt, updatedAt: row.updatedAt } : null;
  }

  replaceRecommendations(accountId, recommendations) {
    const now = this.now();
    this.transaction(() => {
      this.db.prepare("DELETE FROM recommendations WHERE account_id=?").run(accountId);
      const insert = this.db.prepare("INSERT INTO recommendations(id,account_id,source,title,author,reason,deep_link,score,updated_at) VALUES(?,?,?,?,?,?,?,?,?)");
      for (const item of recommendations.slice(0, 100)) insert.run(item.id, accountId, item.source, item.title, item.author ?? null, item.reason, item.deepLink ?? null, Number(item.score ?? 0), now);
    });
  }

  listRecommendations(accountId, limit = 20) {
    return this.db.prepare("SELECT id,source,title,author,reason,deep_link AS deepLink,score,updated_at AS updatedAt FROM recommendations WHERE account_id=? ORDER BY score DESC,updated_at DESC LIMIT ?").all(accountId, limit);
  }

  enqueueOutbox({ id, eventType, aggregateId, payload, availableAt = this.now() }) {
    const now = this.now();
    this.db.prepare("INSERT INTO outbox(id,event_type,aggregate_id,payload_json,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)")
      .run(id, eventType, aggregateId, JSON.stringify(payload), availableAt, now, now);
  }

  claimOutbox(limit = 100) {
    return this.db.prepare("SELECT id,event_type AS eventType,aggregate_id AS aggregateId,payload_json AS payloadJson,attempts FROM outbox WHERE state='PENDING' AND available_at<=? ORDER BY created_at LIMIT ?")
      .all(this.now(), limit).map(row => ({ ...row, payload: parseJson(row.payloadJson) }));
  }

  completeOutbox(id) { this.db.prepare("UPDATE outbox SET state='COMPLETE',updated_at=? WHERE id=?").run(this.now(), id); }
  retryOutbox(id, delaySeconds) { this.db.prepare("UPDATE outbox SET attempts=attempts+1,available_at=?,updated_at=? WHERE id=?").run(this.now() + delaySeconds, this.now(), id); }

  accountExport(accountId) {
    return {
      account: this.getAccount(accountId),
      credentials: this.listCredentials(accountId).map(({ subject, ...rest }) => ({ ...rest, subject: redactSubject(rest.provider, subject) })),
      connections: this.listConnections(accountId),
      notes: this.listNotes(accountId, { includeDeleted: true, limit: 100000 }),
      consent: this.getConsent(accountId),
      weread: this.getWereadState(accountId),
      behavior: this.listBehaviorEvents(accountId, 0, 100000),
      recommendations: this.listRecommendations(accountId, 100),
    };
  }

  listAccountObjectKeys(accountId) {
    return this.db.prepare("SELECT object_key AS objectKey FROM note_objects WHERE account_id=?").all(accountId).map(row => row.objectKey);
  }

  deleteAccount(accountId) {
    return this.transaction(() => Number(this.db.prepare("DELETE FROM accounts WHERE id=?").run(accountId).changes) === 1);
  }

  counts() {
    const count = table => Number(this.db.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get().count);
    return {
      accounts: count("accounts"),
      sessions: count("sessions"),
      notes: count("notes"),
      pendingImports: Number(this.db.prepare("SELECT COUNT(*) AS count FROM import_jobs WHERE state IN ('PENDING','RUNNING')").get().count),
      stalledImports: Number(this.db.prepare("SELECT COUNT(*) AS count FROM import_jobs WHERE state='RUNNING' AND lease_until IS NOT NULL AND lease_until<=?").get(this.now()).count),
      pendingOutbox: Number(this.db.prepare("SELECT COUNT(*) AS count FROM outbox WHERE state='PENDING'").get().count),
    };
  }
}

function parseJson(value) { try { const result = JSON.parse(value || "{}"); return result && typeof result === "object" && !Array.isArray(result) ? result : {}; } catch { return {}; } }
function parseArray(value) { try { const result = JSON.parse(value || "[]"); return Array.isArray(result) ? result : []; } catch { return []; } }
function redactSubject(provider, subject) {
  const value = String(subject ?? "");
  if (provider === "email") return value.replace(/^(.).+(@.+)$/, "$1***$2");
  return value.length > 8 ? `${value.slice(0, 4)}…${value.slice(-4)}` : "已绑定";
}

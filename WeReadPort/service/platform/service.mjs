import { randomBytes } from "node:crypto";
import {
  decryptForAccount,
  decryptWithMaster,
  encryptForAccount,
  encryptWithMaster,
  hashPassword,
  hmacHex,
  constantTimeHexEqual,
  normalizeEmail,
  pkceChallenge,
  randomId,
  randomToken,
  sanitizeText,
  sha256,
  unwrapAccountKey,
  validateEmail,
  verifyPassword,
  wrapAccountKey,
} from "./crypto.mjs";
import {
  buildAuthorizationUrl,
  connectionSupportsImport,
  exchangeAuthorizationCode,
  fetchProviderDocuments,
  listProviderItems,
  providerDefinition,
  refreshProviderAccessToken,
} from "./providers.mjs";
import {
  syncWeReadDataset,
  normalizeWeReadDocuments,
  normalizeOfficialReadingProfile,
  recommendationRows,
  validateWeReadKey,
  WEREAD_COLLECTION_FORMAT_VERSION,
} from "./weread.mjs";
import { buildAnalyticsDashboard } from "./analytics.mjs";

const WEREAD_FULL_RECONCILE_SECONDS = 24 * 60 * 60;

export class PlatformError extends Error {
  constructor(code, message, status = 400, details = undefined) {
    super(message);
    this.name = "PlatformError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export class PlatformService {
  constructor({ store, objectStore, config, fetchImpl = fetch, clock = () => Date.now() }) {
    this.store = store;
    this.objectStore = objectStore;
    this.config = config;
    this.fetchImpl = fetchImpl;
    this.clock = clock;
    this.readinessCache = null;
    this.migrateLegacyImportSelections();
  }

  now() { return Math.floor(this.clock() / 1000); }

  async registerPassword({ email, password, displayName = "阅读者" }, context = {}) {
    const normalized = validateEmail(email);
    if (this.store.findCredential("password", "email", normalized)) throw new PlatformError("ACCOUNT_EXISTS", "该邮箱已经注册。", 409);
    const account = this.createAccount({ email: normalized, displayName: sanitizeText(displayName || normalized.split("@")[0], 80) || "阅读者" });
    try {
      this.store.addCredential({ id: randomId("cred_"), accountId: account.id, kind: "password", provider: "email", subject: normalized, secretHash: await hashPassword(password) });
      this.audit(account.id, "account_registered", { method: "password" });
      return { account: this.publicAccount(account.id), session: this.issueSession(account.id, context) };
    } catch (error) {
      this.store.deleteAccount(account.id);
      throw error;
    }
  }

  async loginPassword({ email, password }, context = {}) {
    const normalized = normalizeEmail(email);
    const bucketKey = this.authBucket("password-login", normalized, context);
    this.assertAuthAllowed(bucketKey);
    const credential = this.store.findCredential("password", "email", normalized);
    const valid = credential ? await verifyPassword(password, credential.secretHash) : await verifyPassword(password, DUMMY_PASSWORD_HASH);
    if (!credential || !valid) this.failAuthentication(bucketKey, "邮箱或密码不正确。");
    this.store.clearAuthFailures(bucketKey);
    this.audit(credential.accountId, "login_completed", { method: "password" });
    return { account: this.publicAccount(credential.accountId), session: this.issueSession(credential.accountId, context) };
  }

  async registerWeRead({ key, displayName = "微信读书用户" }, context = {}, { verify = true } = {}) {
    const cleanKey = requireValidWeReadKey(key);
    const subject = this.wereadSubject(cleanKey);
    if (this.store.findCredential("key", "weread", subject)) throw new PlatformError("ACCOUNT_EXISTS", "该微信读书密钥已经绑定账户。", 409);
    if (verify) await this.verifyWeReadKey(cleanKey);
    const account = this.createAccount({ displayName: sanitizeText(displayName, 80) || "微信读书用户" });
    try {
      const accountKey = this.accountKey(account.id);
      this.store.addCredential({
        id: randomId("cred_"), accountId: account.id, kind: "key", provider: "weread", subject,
        secretEncrypted: encryptForAccount(accountKey, cleanKey, `credential:weread:${account.id}:v1`),
        metadata: { lastFour: cleanKey.slice(-4), verifiedAt: this.now() },
      });
      this.audit(account.id, "account_registered", { method: "weread_key" });
      return { account: this.publicAccount(account.id), session: this.issueSession(account.id, context) };
    } catch (error) {
      this.store.deleteAccount(account.id);
      throw error;
    }
  }

  async loginWeRead({ key }, context = {}) {
    const cleanKey = requireValidWeReadKey(key);
    const subject = this.wereadSubject(cleanKey);
    const bucketKey = this.authBucket("weread-login", subject, context);
    this.assertAuthAllowed(bucketKey);
    const credential = this.store.findCredential("key", "weread", subject);
    if (!credential) this.failAuthentication(bucketKey, "微信读书密钥未绑定账户。");
    this.store.clearAuthFailures(bucketKey);
    this.audit(credential.accountId, "login_completed", { method: "weread_key" });
    return { account: this.publicAccount(credential.accountId), session: this.issueSession(credential.accountId, context) };
  }

  async bindWeRead(accountId, key, { verify = true } = {}) {
    const cleanKey = requireValidWeReadKey(key);
    const subject = this.wereadSubject(cleanKey);
    const other = this.store.findCredential("key", "weread", subject);
    if (other && other.accountId !== accountId) throw new PlatformError("CREDENTIAL_IN_USE", "该密钥已绑定其他账户。", 409);
    if (verify) await this.verifyWeReadKey(cleanKey);
    const accountKey = this.accountKey(accountId);
    const current = this.store.findCredentialByAccount(accountId, "key", "weread");
    const data = {
      subject,
      secretEncrypted: encryptForAccount(accountKey, cleanKey, `credential:weread:${accountId}:v1`),
      metadata: { lastFour: cleanKey.slice(-4), verifiedAt: this.now() },
    };
    if (current) this.store.updateCredentialSecret(current.id, data);
    else this.store.addCredential({ id: randomId("cred_"), accountId, kind: "key", provider: "weread", ...data });
    this.outbox(accountId, "CREDENTIAL_CHANGED", { provider: "weread", operation: current ? "ROTATED" : "BOUND" });
    return this.publicAccount(accountId);
  }

  async reauthenticatePassword(accountId, password, sessionToken) {
    const bucketKey = this.authBucket("password-reauth", accountId, { ipPrefix: accountId });
    this.assertAuthAllowed(bucketKey);
    const credential = this.store.findCredentialByAccount(accountId, "password", "email");
    if (!credential || !(await verifyPassword(password, credential.secretHash))) this.failAuthentication(bucketKey, "密码验证失败。", "REAUTH_FAILED");
    this.store.clearAuthFailures(bucketKey);
    this.store.updateRecentAuth(this.sessionHash(sessionToken));
    return true;
  }

  async reauthenticateWeRead(accountId, key, sessionToken) {
    const cleanKey = requireValidWeReadKey(key);
    const bucketKey = this.authBucket("weread-reauth", accountId, { ipPrefix: accountId });
    this.assertAuthAllowed(bucketKey);
    const credential = this.store.findCredentialByAccount(accountId, "key", "weread");
    if (!credential || !constantTimeHexEqual(credential.subject, this.wereadSubject(cleanKey))) this.failAuthentication(bucketKey, "微信读书密钥验证失败。", "REAUTH_FAILED");
    this.store.clearAuthFailures(bucketKey);
    this.store.updateRecentAuth(this.sessionHash(sessionToken));
    return true;
  }

  issueSession(accountId, context = {}) {
    const token = randomToken(32);
    const csrf = randomToken(24);
    const now = this.now();
    this.store.createSession({
      id: randomId("sess_"), tokenHash: this.sessionHash(token), accountId, csrfHash: this.csrfHash(csrf),
      expiresAt: now + this.config.sessionTtlSeconds, recentAuthAt: now,
      userAgentHash: context.userAgent ? sha256(context.userAgent).slice(0, 32) : null,
      ipPrefixHash: context.ipPrefix ? sha256(context.ipPrefix).slice(0, 32) : null,
    });
    return { token, csrf, expiresAt: now + this.config.sessionTtlSeconds };
  }

  authenticate(token) {
    if (!token) return null;
    const session = this.store.getSession(this.sessionHash(token));
    return session ? { ...session, account: this.publicAccount(session.accountId) } : null;
  }

  refreshSession(token) {
    const current = this.authenticate(token);
    if (!current) return null;
    const nextToken = randomToken(32);
    const csrf = randomToken(24);
    const expiresAt = this.now() + this.config.sessionTtlSeconds;
    const ok = this.store.rotateSession(this.sessionHash(token), {
      newTokenHash: this.sessionHash(nextToken), newCsrfHash: this.csrfHash(csrf), expiresAt,
      recentAuthAt: current.recentAuthAt,
    });
    return ok ? { token: nextToken, csrf, expiresAt, account: this.publicAccount(current.accountId) } : null;
  }

  verifyCsrf(session, value) {
    const actual = value ? hmacHex(this.config.sessionPepper, `csrf:${value}`) : "";
    if (!session || !value || !constantTimeHexEqual(actual, session.csrfHash)) throw new PlatformError("CSRF", "安全校验失败，请刷新后重试。", 403);
  }

  requireRecentAuth(session) {
    if (!session || this.now() - Number(session.recentAuthAt || 0) > this.config.recentAuthSeconds) throw new PlatformError("RECENT_AUTH_REQUIRED", "该操作需要重新验证身份。", 403);
  }

  logout(token) { if (token) this.store.deleteSession(this.sessionHash(token)); }

  listSessions(accountId, currentToken) {
    const currentHash = this.sessionHash(currentToken);
    const current = this.store.getSession(currentHash);
    return this.store.listSessions(accountId).map(session => ({
      ...session,
      current: Boolean(current && current.id === session.id),
      userAgentHint: session.userAgentHash ? session.userAgentHash.slice(0, 8) : null,
      ipHint: session.ipPrefixHash ? session.ipPrefixHash.slice(0, 8) : null,
    }));
  }

  revokeSession(accountId, sessionId, currentToken) {
    const current = this.authenticate(currentToken);
    if (!current || current.accountId !== accountId) throw new PlatformError("AUTH_REQUIRED", "请重新登录。", 401);
    if (current.id === sessionId) {
      this.logout(currentToken);
      return { revoked: true, currentSession: true };
    }
    return { revoked: this.store.deleteSessionById(accountId, sessionId), currentSession: false };
  }

  revokeOtherSessions(accountId, currentToken) {
    const currentHash = this.sessionHash(currentToken);
    return { revoked: this.store.deleteOtherSessions(accountId, currentHash) };
  }

  async configurePassword(accountId, { email, currentPassword = "", newPassword }, sessionToken) {
    const existing = this.store.findCredentialByAccount(accountId, "password", "email");
    const normalized = validateEmail(email || existing?.subject || "");
    const collision = this.store.findCredential("password", "email", normalized);
    if (collision && collision.accountId !== accountId) throw new PlatformError("CREDENTIAL_IN_USE", "该邮箱已绑定其他账户。", 409);
    if (existing && !(await verifyPassword(currentPassword, existing.secretHash))) throw new PlatformError("REAUTH_FAILED", "当前密码不正确。", 401);
    const secretHash = await hashPassword(newPassword);
    if (existing) this.store.updateCredentialSecret(existing.id, { subject: normalized, secretHash, secretEncrypted: null, metadata: {} });
    else this.store.addCredential({ id: randomId("cred_"), accountId, kind: "password", provider: "email", subject: normalized, secretHash });
    this.store.updateAccount(accountId, { email: normalized });
    this.store.updateRecentAuth(this.sessionHash(sessionToken));
    const revoked = this.store.deleteOtherSessions(accountId, this.sessionHash(sessionToken));
    this.outbox(accountId, "CREDENTIAL_CHANGED", { provider: "email", operation: existing ? "PASSWORD_CHANGED" : "PASSWORD_ADDED", revokedSessions: revoked });
    return { account: this.publicAccount(accountId), revokedSessions: revoked };
  }

  async startOAuth(provider, { intent = "login", accountId = null } = {}) {
    const definition = providerDefinition(provider);
    if (!["login", "link", "import", "reauth"].includes(intent)) throw new PlatformError("INVALID_INTENT", "OAuth 目的无效。", 400);
    if (intent !== "login" && !accountId) throw new PlatformError("AUTH_REQUIRED", "请先登录。", 401);
    const state = randomToken(32);
    const verifier = definition.pkce ? randomToken(48) : "";
    const redirectUri = `${this.config.baseUrl}/api/platform/v1/oauth/${provider}/callback`;
    const stateHash = this.oauthStateHash(state);
    this.store.createOAuthTransaction({
      stateHash, provider, intent, accountId,
      verifierEncrypted: verifier ? encryptWithMaster(this.config.keyring, verifier, `oauth:${stateHash}`) : null,
      redirectUri, expiresAt: this.now() + this.config.oauthTtlSeconds,
    });
    const url = buildAuthorizationUrl(provider, {
      clientId: this.config.providers[provider]?.clientId, redirectUri, state,
      challenge: verifier ? pkceChallenge(verifier) : "", intent,
    });
    return { authorizationUrl: url, provider, intent };
  }

  async completeOAuth(provider, { state, code }, context = {}, { expectedAccountId = null, sessionToken = null } = {}) {
    const stateHash = this.oauthStateHash(String(state || ""));
    const transaction = this.store.consumeOAuthTransaction(stateHash);
    if (!transaction || transaction.provider !== provider) throw new PlatformError("OAUTH_STATE", "登录状态已失效，请重新开始。", 400);
    if (transaction.intent !== "login" && (!expectedAccountId || transaction.accountId !== expectedAccountId)) throw new PlatformError("OAUTH_SESSION_MISMATCH", "授权会话与当前账户不一致，请重新开始。", 403);
    const verifier = transaction.verifierEncrypted ? decryptWithMaster(this.config.keyring, transaction.verifierEncrypted, `oauth:${stateHash}`).toString("utf8") : "";
    const result = await exchangeAuthorizationCode(provider, {
      code: String(code || ""), verifier, redirectUri: transaction.redirectUri,
      config: this.config, fetchImpl: this.fetchImpl, networkPolicy: this.networkPolicy(),
    });
    const existing = this.store.findCredential("oauth", provider, result.identity.subject);
    let accountId = transaction.accountId;
    let createdAccountId = null;
    let createdCredentialId = null;
    try {
      if (transaction.intent === "login") {
        if (existing) accountId = existing.accountId;
        else {
          const account = this.createAccount({ email: result.identity.email, displayName: result.identity.displayName });
          accountId = account.id;
          createdAccountId = account.id;
          createdCredentialId = randomId("cred_");
          this.store.addCredential({ id: createdCredentialId, accountId, kind: "oauth", provider, subject: result.identity.subject, metadata: publicProviderMetadata(result.identity) });
        }
      } else {
        if (!accountId) throw new PlatformError("AUTH_REQUIRED", "请先登录。", 401);
        if (existing && existing.accountId !== accountId) throw new PlatformError("CREDENTIAL_IN_USE", "该平台身份已绑定其他账户。", 409);
        if (transaction.intent === "reauth" && !existing) throw new PlatformError("REAUTH_FAILED", "该平台身份尚未绑定当前账户。", 401);
        if (!existing) {
          createdCredentialId = randomId("cred_");
          this.store.addCredential({ id: createdCredentialId, accountId, kind: "oauth", provider, subject: result.identity.subject, metadata: publicProviderMetadata(result.identity) });
        }
      }
      const accountKey = this.accountKey(accountId);
      this.store.upsertConnection({
        id: randomId("conn_"), accountId, provider, providerSubject: result.identity.subject,
        accessTokenEncrypted: encryptForAccount(accountKey, result.accessToken, `provider:${provider}:${accountId}:access`),
        refreshTokenEncrypted: result.refreshToken ? encryptForAccount(accountKey, result.refreshToken, `provider:${provider}:${accountId}:refresh`) : null,
        scopes: result.scopes,
        expiresAt: result.expiresIn ? this.now() + result.expiresIn : null,
        metadata: { ...publicProviderMetadata(result.identity), ...result.rawMetadata },
      });
      this.outbox(accountId, "PROVIDER_CONNECTED", { provider, intent: transaction.intent });
      if (transaction.intent === "reauth") {
        if (!sessionToken) throw new PlatformError("AUTH_REQUIRED", "请重新登录。", 401);
        this.store.updateRecentAuth(this.sessionHash(sessionToken));
      }
      const session = transaction.intent === "login" ? this.issueSession(accountId, context) : null;
      return { account: this.publicAccount(accountId), session, provider, intent: transaction.intent };
    } catch (error) {
      if (createdAccountId) this.store.deleteAccount(createdAccountId);
      else if (createdCredentialId && accountId) this.store.deleteCredential(accountId, createdCredentialId);
      throw error;
    }
  }

  async listProviderItems(accountId, provider, options = {}) {
    const token = await this.providerToken(accountId, provider, { requireImportScope: true });
    return listProviderItems(provider, token, {
      ...options,
      fetchImpl: this.fetchImpl,
      limit: Math.min(Number(options.limit || 200), this.config.maxImportItems),
      networkPolicy: this.networkPolicy(),
    });
  }

  createImportJob(accountId, provider, selection, idempotencyKey) {
    if (!["google", "github", "notion", "obsidian"].includes(provider)) throw new PlatformError("INVALID_PROVIDER", "不支持的导入来源。", 400);
    const items = Array.isArray(selection?.items) ? selection.items : [];
    if (!items.length || items.length > this.config.maxImportItems) throw new PlatformError("INVALID_SELECTION", "请选择 1 个以上且不超过上限的项目。", 400);
    const id = randomId("job_");
    const normalizedSelection = { ...selection, items };
    const selectionEncrypted = encryptForAccount(this.accountKey(accountId), normalizedSelection, `import-selection:${accountId}:${id}:v1`);
    const job = this.store.createImportJob({ id, accountId, provider, selectionEncrypted, idempotencyKey: sanitizeText(idempotencyKey || randomToken(12), 128) });
    return publicImportJob(job);
  }

  async processNextImportJob(workerId = "import-worker") {
    this.store.heartbeat(workerId, "import", "v0.0.0.1.9");
    const job = this.store.claimNextImportJob(workerId, this.config.importLeaseSeconds);
    if (!job) return null;
    try {
      if (!job.selectionEncrypted) throw new PlatformError("IMPORT_SELECTION_MISSING", "导入内容已失效，请重新选择。", 409);
      const selection = JSON.parse(decryptForAccount(this.accountKey(job.accountId), job.selectionEncrypted, `import-selection:${job.accountId}:${job.id}:v1`).toString("utf8"));
      let documents;
      if (job.provider === "obsidian") documents = normalizeObsidianDocuments(selection);
      else {
        const token = await this.providerToken(job.accountId, job.provider, { requireImportScope: true });
        documents = await fetchProviderDocuments(job.provider, token, selection, {
          fetchImpl: this.fetchImpl,
          maxBytes: this.config.maxImportBytes,
          networkPolicy: this.networkPolicy(),
        });
      }
      const saved = [];
      for (const document of documents) {
        this.store.heartbeat(workerId, "import", "v0.0.0.1.9");
        saved.push(await this.saveDocument(job.accountId, document));
      }
      this.store.updateImportJob(job.accountId, job.id, { state: "COMPLETE", progress: { total: documents.length, saved: saved.length }, clearSelection: true });
      this.audit(job.accountId, "import_completed", { provider: job.provider, count: saved.length });
      return publicImportJob(this.store.getImportJob(job.accountId, job.id));
    } catch (error) {
      this.store.updateImportJob(job.accountId, job.id, { state: "FAILED", progress: {}, errorCode: safeErrorCode(error), clearSelection: true });
      throw error;
    }
  }

  async saveDocument(accountId, document, { expectedVersion = null, reportStatus = false } = {}) {
    const source = sanitizeSource(document.source || "manual");
    const externalId = sanitizeText(document.externalId || randomId("manual_"), 240);
    const title = sanitizeText(document.title || "未命名笔记", 180) || "未命名笔记";
    const content = String(document.content || "");
    const category = sanitizeText(document.category || "未分类", 80);
    const contentHash = sha256(content);
    const current = this.store.findNote(accountId, source, externalId);
    const bookTitle = sanitizeText(document.bookTitle ?? current?.bookTitle ?? "", 180) || null;
    const author = sanitizeText(document.author ?? current?.author ?? "", 120) || null;
    const chapterTitle = sanitizeText(document.chapterTitle ?? current?.chapterTitle ?? "", 180) || null;
    const noteKind = sanitizeText(document.noteKind ?? current?.noteKind ?? "", 80) || null;
    const eventAt = normalizeSourceEventAt(document.eventAt ?? document.updatedAt ?? document.createdAt);
    if (!content.trim()) throw new PlatformError("EMPTY_NOTE", "笔记内容不能为空。", 400);
    if (Buffer.byteLength(content, "utf8") > this.config.maxImportBytes) throw new PlatformError("NOTE_TOO_LARGE", "单条笔记超过安全上限。", 413);
    if (current && expectedVersion !== null && Number(current.version) !== Number(expectedVersion)) {
      return reportStatus ? { note: current, conflict: true, unchanged: false } : { conflict: true, current };
    }
    const effectiveEventAt = eventAt || Number(current?.eventAt || current?.createdAt || 0);
    if (current && !current.deletedAt && current.contentHash === contentHash && current.title === title && String(current.category || "") === category && String(current.bookTitle || "") === String(bookTitle || "") && String(current.author || "") === String(author || "") && String(current.chapterTitle || "") === String(chapterTitle || "") && String(current.noteKind || "") === String(noteKind || "") && Number(current.eventAt || current.createdAt || 0) === effectiveEventAt) {
      return reportStatus ? { note: current, unchanged: true } : current;
    }
    const accountKey = this.accountKey(accountId);
    const id = randomId("note_");
    const noteId = current?.id || id;
    const nextVersion = Number(current?.version || 0) + 1;
    const objectKey = `${this.config.primaryObjectPrefix}/accounts/${accountId}/notes/${noteId}/v${nextVersion}.enc`;
    const envelope = encryptForAccount(accountKey, { content, title, source, externalId, bookTitle, author, chapterTitle, noteKind }, `note:${accountId}:${noteId}:v${nextVersion}`);
    await this.objectStore.put(objectKey, Buffer.from(envelope, "utf8"), { account: sha256(accountId).slice(0, 16), note: noteId, version: nextVersion });
    let result;
    try {
      result = this.store.upsertNote({
        id: noteId, accountId, source, externalId, title, objectKey,
        contentHash, wordCount: countWords(content), category, bookTitle, author, chapterTitle, noteKind, eventAt, expectedVersion,
      });
    } catch (error) {
      await this.objectStore.delete(objectKey).catch(() => undefined);
      throw error;
    }
    if (result.conflict) {
      await this.objectStore.delete(objectKey);
      return reportStatus ? { note: result.current, conflict: true, unchanged: false } : result;
    }
    this.outbox(accountId, "NOTE_UPSERTED", { noteId: result.note.id, source, version: result.note.version, contentHash: result.note.contentHash, objectKey });
    return reportStatus ? { note: result.note, unchanged: false } : result.note;
  }

  async readNote(accountId, noteId) {
    const note = this.store.getNote(accountId, noteId);
    if (!note || note.deletedAt) return null;
    const stored = await this.objectStore.get(note.objectKey);
    if (!stored) throw new PlatformError("OBJECT_MISSING", "笔记正文暂时不可用。", 503);
    const decoded = decryptForAccount(this.accountKey(accountId), stored.bytes.toString("utf8"), `note:${accountId}:${note.id}:v${note.version}`);
    const payload = JSON.parse(decoded.toString("utf8"));
    return { ...publicNote(note), content: payload.content };
  }

  async deleteNote(accountId, noteId, expectedVersion = null) {
    const result = this.store.deleteNote(accountId, noteId, expectedVersion);
    if (result.deleted) this.outbox(accountId, "NOTE_DELETED", { noteId, version: result.note.version });
    return result;
  }

  async syncPull(accountId, cursor = 0, limit = 500) {
    const events = this.store.listSyncEvents(accountId, Number(cursor || 0), Math.min(Number(limit || 500), 500));
    const notes = [];
    for (const event of events) {
      if (event.entityType !== "note") continue;
      const note = this.store.getNote(accountId, event.entityId);
      notes.push(event.operation === "DELETE" || note?.deletedAt ? { ...event, note: note ? publicNote(note) : null } : { ...event, note: await this.readNote(accountId, event.entityId) });
    }
    return { cursor: events.at(-1)?.seq ?? Number(cursor || 0), hasMore: events.length === Math.min(Number(limit || 500), 500), events: notes };
  }

  async syncPush(accountId, operations = []) {
    if (!Array.isArray(operations) || operations.length > 200) throw new PlatformError("SYNC_BATCH", "同步批次无效。", 400);
    const results = [];
    for (const operation of operations) {
      if (operation.type === "upsert") results.push(await this.saveDocument(accountId, operation.note || {}, { expectedVersion: operation.expectedVersion ?? null }));
      else if (operation.type === "delete") results.push(await this.deleteNote(accountId, String(operation.noteId || ""), operation.expectedVersion ?? null));
      else results.push({ error: "UNKNOWN_OPERATION" });
    }
    return { results };
  }

  async syncWeRead(accountId, { recommendationPages = 3, mode = "auto" } = {}) {
    const credential = this.store.findCredentialByAccount(accountId, "key", "weread");
    if (!credential?.secretEncrypted) throw new PlatformError("WEREAD_NOT_BOUND", "请先绑定微信读书密钥。", 409);
    const key = decryptForAccount(this.accountKey(accountId), credential.secretEncrypted, `credential:weread:${accountId}:v1`).toString("utf8");
    const priorState = this.store.getWereadState(accountId, { includeBookState: true });
    const priorBookState = priorState?.bookState && typeof priorState.bookState === "object" ? priorState.bookState : {};
    const priorFullSyncAt = Number(priorState?.summary?.lastFullSyncAt || 0);
    const hasIncrementalBaseline = Number(priorState?.lastSyncAt || 0) > 0 && Object.keys(priorBookState).length > 0;
    const collectionRepairDue = String(priorState?.summary?.collectionFormatVersion || "") !== WEREAD_COLLECTION_FORMAT_VERSION;
    const fullReconcileDue = priorFullSyncAt <= 0 || this.now() - priorFullSyncAt >= WEREAD_FULL_RECONCILE_SECONDS || collectionRepairDue;
    const syncMode = mode === "full" || !hasIncrementalBaseline || fullReconcileDue ? "full" : "incremental";
    const dataset = await syncWeReadDataset(key, {
      fetchImpl: this.fetchImpl,
      maxBooks: this.config.maxWereadBooks,
      timeoutMs: this.config.upstreamTimeoutMs,
      recommendationPages: Math.min(Math.max(Number(recommendationPages || 3), 1), 10),
      mode: syncMode,
      previousBookState: priorBookState,
    });
    const documents = normalizeWeReadDocuments(dataset);
    let updatedDocuments = 0;
    let unchangedDocuments = Number(dataset.summary.skippedUnchangedDocuments || 0);
    for (const document of documents) {
      const outcome = await this.saveDocument(accountId, document, { reportStatus: true });
      if (outcome.unchanged) unchangedDocuments += 1;
      else updatedDocuments += 1;
    }
    const sourceContentCount = Number(dataset.summary.sourceContentCount || 0);
    const sourceReportedNotes = Number(dataset.summary.totalNoteCount || 0);
    const sourceReportedExportableDocuments = sourceContentCount || sourceReportedNotes;
    const accountedDocuments = documents.length + Number(dataset.summary.skippedUnchangedDocuments || 0);
    const unresolvedDocuments = Math.max(0, sourceReportedExportableDocuments - accountedDocuments);
    const sourceCountersAvailable = sourceReportedExportableDocuments > 0 || (sourceReportedNotes === 0 && accountedDocuments === 0);
    const priorCoverageWasVerified = priorState?.summary?.coverage?.verified === true && Number(priorState.summary.coverage.unresolvedDocuments || 0) === 0;
    const currentSourceEventRange = eventRange(documents.map(document => document.eventAt));
    const currentNotebookRange = eventRange((dataset.notebooks?.books || []).map(book => book.sort));
    const currentOfficialReading = normalizeOfficialReadingProfile(dataset.readingStats);
    const priorOfficialReading = priorState?.summary?.officialReading && typeof priorState.summary.officialReading === "object" ? priorState.summary.officialReading : null;
    const statisticsFailed = dataset.failures.some(failure => failure.api === "/readdata/detail");
    const officialReading = currentOfficialReading
      ? { ...currentOfficialReading, collectedAt: this.now(), freshness: statisticsFailed ? "PARTIAL" : "CURRENT" }
      : priorOfficialReading ? { ...priorOfficialReading, freshness: "STALE" } : null;
    // An incremental pass deliberately skips unchanged books, so its timestamps
    // cannot honestly replace the last full source window.
    const sourceEventRange = syncMode === "full" ? currentSourceEventRange : priorState?.summary?.coverage?.sourceEventRange || currentSourceEventRange;
    const sourceNotebookRange = syncMode === "full" ? currentNotebookRange : priorState?.summary?.coverage?.sourceNotebookRange || currentNotebookRange;
    const coverage = {
      sourceReportedNotes,
      sourceReportedHighlights: Number(dataset.summary.sourceHighlightCount || 0),
      sourceReportedThoughts: Number(dataset.summary.sourceReviewCount || 0),
      sourceReportedBookmarks: Number(dataset.summary.sourceBookmarkCount || 0),
      sourceReportedExportableDocuments,
      coverageBasis: sourceContentCount > 0 ? "官方分项划线与想法计数" : sourceReportedNotes > 0 ? "官方笔记总数" : "官方空集",
      accountedDocuments,
      unresolvedDocuments,
      sourceCountersAvailable,
      sourceEventRange,
      sourceNotebookRange,
      // A successful full reconciliation remains valid across a complete
      // incremental pass. Only an incomplete/truncated pass or a new gap may
      // downgrade it; otherwise the UI would falsely claim a clean account is
      // unverified after every routine refresh.
      verified: sourceCountersAvailable && !dataset.partial && !dataset.summary.truncatedBySafetyLimit && unresolvedDocuments === 0 && (syncMode === "full" || priorCoverageWasVerified),
      note: "书签只有官方计数时不会伪装成可下载正文；未确认的差额会明确保留。",
    };
    const summary = {
      ...dataset.summary,
      importedDocuments: documents.length,
      updatedDocuments,
      unchangedDocuments,
      coverage,
      officialReading,
      lastFullSyncAt: syncMode === "full" ? this.now() : priorFullSyncAt,
    };
    this.store.updateWereadState(accountId, { capabilities: dataset.capabilities, summary, bookState: dataset.bookState });
    if (dataset.recommendationsRefreshed) this.store.replaceRecommendations(accountId, recommendationRows(dataset));
    this.audit(accountId, "weread_sync_completed", {
      mode: syncMode,
      imported: documents.length,
      updated: updatedDocuments,
      unchanged: unchangedDocuments,
      scannedBooks: dataset.summary.notebookBooks,
      books: dataset.summary.detailedBooks,
      skippedBooks: dataset.summary.skippedUnchangedBooks,
      partial: dataset.partial,
    });
    return {
      summary,
      capabilities: dataset.capabilities,
      failures: dataset.failures,
      coverage: {
        scope: dataset.contract?.scope || "unknown",
        gatewaySkillVersion: dataset.contract?.skillVersion || null,
        capabilityCount: dataset.capabilities.length,
        mode: syncMode,
        notebookBooks: dataset.summary.notebookBooks,
        detailedBooks: dataset.summary.detailedBooks,
        skippedUnchangedBooks: dataset.summary.skippedUnchangedBooks,
        legacyTop5CeilingRemoved: this.config.maxWereadBooks > 5,
        truncatedBySafetyLimit: Boolean(dataset.summary.truncatedBySafetyLimit),
        coverage,
      },
    };
  }

  listNotes(accountId, options = {}) { return this.store.listNotes(accountId, options).map(publicNote); }
  async exportNotes(accountId, noteIds) {
    if (!Array.isArray(noteIds) || noteIds.length === 0) throw new PlatformError("NOTES_EXPORT_EMPTY", "请先保留至少一条笔记再导出。", 400);
    if (noteIds.length > 5_000) throw new PlatformError("NOTES_EXPORT_LIMIT", "一次最多导出 5,000 条笔记，请缩小筛选范围。", 413);
    const ids = [...new Set(noteIds.map(value => String(value || "").trim()).filter(Boolean))];
    if (!ids.length) throw new PlatformError("NOTES_EXPORT_EMPTY", "请先保留至少一条笔记再导出。", 400);
    const notes = [];
    let bytes = 0;
    for (const id of ids) {
      const note = await this.readNote(accountId, id);
      if (!note) throw new PlatformError("NOT_FOUND", "筛选结果中的笔记已不存在，请刷新后重试。", 404);
      bytes += Buffer.byteLength(JSON.stringify(note), "utf8");
      if (bytes > this.config.maxImportBytes) throw new PlatformError("NOTES_EXPORT_TOO_LARGE", "筛选结果正文超过 50 MiB 安全上限，请缩小时间范围后重试。", 413);
      notes.push(note);
    }
    return { exportedAt: new Date(this.clock()).toISOString(), schemaVersion: "1.0.0", scope: "filtered-notes", notes };
  }
  getImportJob(accountId, id) { return publicImportJob(this.store.getImportJob(accountId, id)); }
  analytics(accountId) { return buildAnalyticsDashboard(this.store, accountId, { now: this.clock() }); }
  updateConsent(accountId, input) { return this.store.updateConsent(accountId, input); }
  updateProfile(accountId, input) { return this.store.updateAccount(accountId, { displayName: sanitizeText(input.displayName, 80), locale: "zh-CN" }); }

  async exportAccount(accountId) {
    const metadata = this.store.accountExport(accountId);
    const notes = [];
    for (const row of this.store.listNotes(accountId, { includeDeleted: false, limit: 100000 })) notes.push(await this.readNote(accountId, row.id));
    return { exportedAt: new Date(this.clock()).toISOString(), schemaVersion: "1.0.0", ...metadata, notes };
  }

  async exportWeRead(accountId) {
    const notes = [];
    for (const row of this.store.listNotes(accountId, { includeDeleted: false, limit: 100000 })) {
      if (row.source === "weread") notes.push(await this.readNote(accountId, row.id));
    }
    const state = this.store.getWereadState(accountId);
    return {
      exportedAt: new Date(this.clock()).toISOString(),
      schemaVersion: "1.0.0",
      source: "WeChat Reading",
      coverage: state?.summary?.coverage || null,
      notes,
    };
  }

  async deleteAccount(accountId) {
    for (const objectKey of this.store.listAccountObjectKeys(accountId)) await this.objectStore.delete(objectKey);
    const deleted = this.store.deleteAccount(accountId);
    return { deleted };
  }

  publicAccount(accountId) {
    const account = this.store.getAccount(accountId);
    if (!account) return null;
    return {
      ...account,
      credentials: this.store.listCredentials(accountId).map(item => ({ id: item.id, kind: item.kind, provider: item.provider, label: credentialLabel(item), createdAt: item.createdAt, updatedAt: item.updatedAt })),
      connections: this.store.listConnections(accountId).map(item => ({ provider: item.provider, metadata: publicConnectionMetadata(item.metadata), scopes: item.scopes, importReady: connectionSupportsImport(item.provider, item.scopes), expiresAt: item.expiresAt, updatedAt: item.updatedAt })),
      consent: this.store.getConsent(accountId),
      weread: this.store.getWereadState(accountId),
    };
  }

  async providerToken(accountId, provider, { requireImportScope = false } = {}) {
    let connection = this.store.getConnection(accountId, provider);
    if (!connection) throw new PlatformError("PROVIDER_NOT_CONNECTED", `请先连接 ${provider}。`, 409);
    if (requireImportScope && !connectionSupportsImport(provider, connection.scopes)) throw new PlatformError("PROVIDER_SCOPE_REQUIRED", "需要重新授权只用于导入的读取权限。", 409);
    const accountKey = this.accountKey(accountId);
    let accessToken = decryptForAccount(accountKey, connection.accessTokenEncrypted, `provider:${provider}:${accountId}:access`).toString("utf8");
    if (connection.expiresAt && connection.expiresAt <= this.now() + 60) {
      if (!connection.refreshTokenEncrypted) throw new PlatformError("PROVIDER_RECONNECT", "连接已过期，请重新授权。", 401);
      const refreshToken = decryptForAccount(accountKey, connection.refreshTokenEncrypted, `provider:${provider}:${accountId}:refresh`).toString("utf8");
      const refreshed = await refreshProviderAccessToken(provider, refreshToken, { config: this.config, fetchImpl: this.fetchImpl, networkPolicy: this.networkPolicy() });
      accessToken = refreshed.accessToken;
      connection = this.store.upsertConnection({
        ...connection, id: connection.id, accountId, provider, providerSubject: connection.providerSubject,
        accessTokenEncrypted: encryptForAccount(accountKey, accessToken, `provider:${provider}:${accountId}:access`),
        refreshTokenEncrypted: refreshed.refreshToken ? encryptForAccount(accountKey, refreshed.refreshToken, `provider:${provider}:${accountId}:refresh`) : connection.refreshTokenEncrypted,
        scopes: refreshed.scopes || connection.scopes, expiresAt: refreshed.expiresIn ? this.now() + refreshed.expiresIn : connection.expiresAt, metadata: connection.metadata,
      });
    }
    return accessToken;
  }

  async verifyWeReadKey(key) {
    const { gatewayCall } = await import("./weread.mjs");
    await gatewayCall(key, "/_list", {}, { fetchImpl: this.fetchImpl, timeoutMs: this.config.upstreamTimeoutMs });
    return true;
  }

  async readiness({ force = false } = {}) {
    const now = this.now();
    if (!force && this.readinessCache?.value?.ready && now - this.readinessCache.checkedAt < this.config.readinessCacheSeconds) return this.readinessCache.value;
    const dependencies = {
      database: { ok: false },
      objectStore: { ok: false, mode: this.config.objectStoreMode },
      importWorker: this.store.workerHealth("import", this.config.workerStaleSeconds),
      providers: {},
    };
    try { dependencies.database = this.store.healthCheck(); } catch { dependencies.database = { ok: false, code: "DATABASE_UNAVAILABLE" }; }
    try { dependencies.objectStore = { ...(await this.objectStore.healthCheck(this.config.objectHealthProbePrefix)), mode: this.config.objectStoreMode }; }
    catch { dependencies.objectStore = { ok: false, mode: this.config.objectStoreMode, code: "OBJECT_STORE_UNAVAILABLE" }; }
    for (const provider of ["google", "github", "notion"]) {
      const entry = this.config.providers[provider] || {};
      dependencies.providers[provider] = { configured: Boolean(entry.clientId && entry.clientSecret) };
    }
    const providersReady = Object.values(dependencies.providers).every(item => item.configured);
    const releaseIdentityReady = Boolean(
      this.config.releaseIdentity.taskpackVersion === "v0.0.0.1.9" &&
      this.config.releaseIdentity.releaseCommit &&
      this.config.releaseIdentity.ovhReleaseId &&
      this.config.releaseIdentity.sitesProjectId
    );
    dependencies.releaseIdentity = { ok: releaseIdentityReady, ...this.config.releaseIdentity };
    dependencies.objectNamespaces = {
      ok: this.config.primaryObjectPrefix === "primary-objects" && this.config.privateDatabaseBackupPrefix === "backups/private-database",
      primaryObjects: this.config.primaryObjectPrefix,
      privateDatabaseBackups: this.config.privateDatabaseBackupPrefix,
    };
    const ready = Boolean(dependencies.database.ok && dependencies.objectStore.ok && dependencies.importWorker.ok && providersReady && dependencies.releaseIdentity.ok && dependencies.objectNamespaces.ok);
    const value = { status: ready ? "ready" : "not_ready", ready, version: "v0.0.0.1.9", releaseIdentity: this.config.releaseIdentity, checkedAt: new Date(now * 1000).toISOString(), dependencies };
    this.readinessCache = { checkedAt: now, value };
    return value;
  }

  migrateLegacyImportSelections() {
    for (const row of this.store.listLegacyImportSelections()) {
      try {
        const selection = JSON.parse(row.selectionJson || "{}");
        const encrypted = encryptForAccount(this.accountKey(row.accountId), selection, `import-selection:${row.accountId}:${row.id}:v1`);
        this.store.migrateImportSelection(row.accountId, row.id, encrypted);
      } catch {
        this.store.updateImportJob(row.accountId, row.id, { state: "FAILED", progress: {}, errorCode: "LEGACY_SELECTION_MIGRATION_FAILED", clearSelection: true });
      }
    }
  }

  networkPolicy() {
    return { timeoutMs: this.config.upstreamTimeoutMs, attempts: this.config.upstreamRetryAttempts };
  }

  authBucket(scope, subject, context = {}) {
    const remote = String(context.ipPrefix || "unknown");
    return hmacHex(this.config.credentialPepper, `auth:${scope}:${String(subject || "").toLowerCase()}:${remote}`);
  }

  assertAuthAllowed(bucketKey) {
    const result = this.store.assertAuthAllowed(bucketKey, { windowSeconds: this.config.authFailureWindowSeconds, lockSeconds: this.config.authLockSeconds });
    if (!result.allowed) throw new PlatformError("RATE_LIMIT", `尝试次数过多，请在 ${Math.max(1, result.remainingLockSeconds)} 秒后重试。`, 429);
  }

  failAuthentication(bucketKey, message, code = "INVALID_LOGIN") {
    const result = this.store.recordAuthFailure(bucketKey, { limit: this.config.authFailureLimit, windowSeconds: this.config.authFailureWindowSeconds, lockSeconds: this.config.authLockSeconds });
    if (result.lockedUntil > this.now()) throw new PlatformError("RATE_LIMIT", "尝试次数过多，请稍后再试。", 429);
    throw new PlatformError(code, message, 401);
  }

  createAccount({ email = null, displayName }) {
    const accountId = randomId("acct_");
    const accountKey = randomBytes(32);
    return this.store.createAccount({ id: accountId, email, displayName, wrappedDek: wrapAccountKey(this.config.keyring, accountKey, accountId), keyId: this.config.keyring.activeKeyId });
  }
  accountKey(accountId) { const row = this.store.getAccountKey(accountId); if (!row) throw new PlatformError("ACCOUNT_KEY_MISSING", "账户密钥不可用。", 503); return unwrapAccountKey(this.config.keyring, row.wrappedDek, accountId); }
  sessionHash(token) { return hmacHex(this.config.sessionPepper, `session:${token}`); }
  csrfHash(token) { return hmacHex(this.config.sessionPepper, `csrf:${token}`); }
  oauthStateHash(state) { return hmacHex(this.config.sessionPepper, `oauth-state:${state}`); }
  wereadSubject(key) { return hmacHex(this.config.credentialPepper, `weread:${key}`); }
  audit(accountId, eventType, value) { this.store.addBehaviorEvent({ id: randomId("evt_"), accountId, eventType, value: stripSensitive(value) }); }
  outbox(accountId, eventType, payload) { this.store.enqueueOutbox({ id: randomId("out_"), eventType, aggregateId: sha256(accountId), payload: stripSensitive(payload) }); }
}

function publicImportJob(job) {
  if (!job) return null;
  const { selectionEncrypted, idempotencyKey, workerId, ...safe } = job;
  return safe;
}

function publicNote(note) { const { objectKey, ...publicRow } = note; return publicRow; }
function eventRange(values) {
  const times = values.map(value => normalizeSourceEventAt(value)).filter(value => value !== null).sort((a, b) => a - b);
  return times.length ? { earliest: times[0], latest: times.at(-1) } : null;
}
function normalizeSourceEventAt(value) { const raw = Number(value); if (!Number.isFinite(raw) || raw <= 0) return null; const seconds = raw >= 10_000_000_000 ? Math.floor(raw / 1000) : Math.floor(raw); return seconds > 0 ? seconds : null; }
function requireValidWeReadKey(value) {
  try { return validateWeReadKey(value); }
  catch (error) {
    if (error?.code === "INVALID_KEY") throw new PlatformError("INVALID_KEY", "微信读书密钥格式无效。", 400);
    throw error;
  }
}
function credentialLabel(item) {
  if (item.provider === "email") return item.subject.replace(/^(.).+(@.+)$/, "$1***$2");
  if (item.provider === "weread") return `微信读书密钥 ····${item.metadata?.lastFour || "已绑定"}`;
  return `${item.provider} 已绑定`;
}
function publicProviderMetadata(identity) { return { displayName: sanitizeText(identity.displayName, 80), emailHint: identity.email ? identity.email.replace(/^(.).+(@.+)$/, "$1***$2") : null, avatarUrl: safeHttps(identity.avatarUrl), login: sanitizeText(identity.login, 80) || null }; }
function publicConnectionMetadata(metadata = {}) { return { displayName: sanitizeText(metadata.displayName, 80), emailHint: sanitizeText(metadata.emailHint, 160), workspaceName: sanitizeText(metadata.workspaceName, 120), avatarUrl: safeHttps(metadata.avatarUrl), login: sanitizeText(metadata.login, 80) }; }
function safeHttps(value) { try { const u = new URL(String(value || "")); return u.protocol === "https:" ? u.toString() : null; } catch { return null; } }
function countWords(text) { return String(text).trim().split(/\s+|(?=[\u3400-\u9fff])|(?<=[\u3400-\u9fff])/u).filter(Boolean).length; }
function sanitizeSource(value) { const source = String(value || "manual").toLowerCase().replace(/[^a-z0-9_-]/g, "-").slice(0, 40); return source || "manual"; }
function stripSensitive(value) { const result = {}; for (const [key, item] of Object.entries(value || {})) if (!/(token|key|secret|content|email|title|name)/i.test(key)) result[key] = item; return result; }
function safeErrorCode(error) { return String(error?.code || "IMPORT_FAILED").replace(/[^A-Z0-9_]/g, "_").slice(0, 80); }
function normalizeObsidianDocuments(selection) {
  const files = Array.isArray(selection?.items) ? selection.items : [];
  let total = 0;
  return files.map((file, index) => {
    const name = sanitizeText(file.name || `笔记-${index + 1}.md`, 180);
    if (!/\.(?:md|markdown|txt)$/i.test(name) || name.split(/[\\/]/).some(part => part === "..")) throw new PlatformError("OBSIDIAN_FILE", "Obsidian 文件名或类型不允许。", 400);
    const content = String(file.content || "");
    total += Buffer.byteLength(content, "utf8");
    if (total > 50 * 1024 * 1024) throw new PlatformError("IMPORT_TOO_LARGE", "Obsidian 导入超过安全上限。", 413);
    return { externalId: file.path || name, title: name.replace(/\.(?:md|markdown|txt)$/i, ""), content, source: "obsidian", category: "Obsidian" };
  });
}

const DUMMY_PASSWORD_HASH = "scrypt$32768$8$1$MDAwMDAwMDAwMDAwMDAwMA$MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA";

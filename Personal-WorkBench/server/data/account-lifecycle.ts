import { sha256 } from "@/server/data/idempotency";
import { tenantResources, type TenantResource, type TenantResourceName } from "@/server/data/resources";

export const ACCOUNT_PRIVACY_POLICY_VERSION = "2026-08-03.v2";
export const ACCOUNT_PRIVACY_NOTICE_SHA256 = "5c5403e8747d4ca0df26b98b1c08fef978f8ba76e98770e6c28df64ae2f7e956";

type AccountDb = Pick<D1Database, "prepare">;

type RowByName = Record<string, unknown>;
type FileRow = {
  id: string;
  object_key: string;
  module: string;
  content_type: string;
  byte_size: number;
  sha256: string;
  width: number | null;
  height: number | null;
  state: string;
};

type ProfileRow = {
  display_name: string;
  timezone: string;
  locale: string;
  show_welcome: number;
  privacy_policy_version: string | null;
  privacy_consent_state: "not_requested" | "accepted" | "revoked" | null;
  privacy_consented_at: number | null;
  privacy_revoked_at: number | null;
  data_version: number;
  sync_token: string | null;
  sync_token_expires_at: number | null;
  deletion_state: "active" | "pending" | null;
};

type PrivacyEventRow = {
  policy_version: string;
  decision: "accepted" | "revoked";
  decided_at: number;
};

type UserRow = {
  id: string;
  name: string;
  email: string;
  emailVerified: number;
};

type FileStoreEnv = {
  FILES?: {
    delete(key: string): Promise<void> | void;
  };
};

export type AccountExport = {
  schemaVersion: "1.0.0";
  generatedAt: string;
  user: {
    id: string;
    name: string;
    email: string;
    emailVerified: boolean;
  };
  profile: {
    displayName: string | null;
    timezone: string | null;
    locale: string | null;
    showWelcome: boolean | null;
    privacyState: ProfileRow["privacy_consent_state"];
    privacyPolicyVersion: string | null;
    privacyConsentedAt: number | null;
    privacyRevokedAt: number | null;
    dataVersion: number | null;
    syncTokenExpiresAt: number | null;
  };
  privacyEvents: PrivacyEventRow[];
  modules: Record<string, RowByName[]>;
  files: Array<{
    id: string;
    module: string;
    contentType: string;
    byteSize: number;
    sha256: string;
    width: number | null;
    height: number | null;
    state: string;
  }>;
};

export type PrivacyStateSnapshot = {
  state: "not_requested" | "accepted" | "revoked" | null;
  policyVersion: string | null;
  consentedAt: number | null;
  revokedAt: number | null;
};

export type AccountDeletionInfo = {
  state: "active" | "pending";
  tokenExpiresAt: number | null;
};

export type ExportStartResult = {
  exportData: AccountExport;
  exportHash: string;
  recoveryToken: string;
};

export class AccountNotFoundError extends Error {
  status = 404;
  code = "ACCOUNT_NOT_FOUND";

  constructor() {
    super("account not found");
  }
}

export class AccountInputError extends Error {
  status = 400;
  code = "INVALID_ACCOUNT_INPUT";

  constructor(message = "invalid account request") {
    super(message);
  }
}

export class AccountDeleteStateError extends Error {
  status = 409;
  code = "INVALID_DELETE_STATE";

  constructor(message = "account delete state invalid") {
    super(message);
  }
}

const DELETION_TOKEN_TTL_MS = 24 * 60 * 60 * 1000;

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (!value || typeof value !== "object") return JSON.stringify(value);
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key])}`)
    .join(",")}}`;
}

function isString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isPolicyVersion(value: unknown): value is string {
  return typeof value === "string" && value.length > 1 && value.length <= 80;
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && value.length === 64 && /^[a-f0-9]{64}$/i.test(value);
}

function moduleTables(): [TenantResourceName, TenantResource][] {
  return Object.entries(tenantResources) as [TenantResourceName, TenantResource][];
}

function rowToProfilePayload(row: ProfileRow | null) {
  if (!row) {
    return {
      displayName: null as string | null,
      timezone: null,
      locale: null,
      showWelcome: null as boolean | null,
      privacyState: null as ProfileRow["privacy_consent_state"],
      privacyPolicyVersion: null as string | null,
      privacyConsentedAt: null as number | null,
      privacyRevokedAt: null as number | null,
      dataVersion: null as number | null,
      syncTokenExpiresAt: null as number | null,
    };
  }
  return {
    displayName: row.display_name ?? null,
    timezone: row.timezone ?? null,
    locale: row.locale ?? null,
    showWelcome: typeof row.show_welcome === "number" ? row.show_welcome === 1 : null,
    privacyState: row.privacy_consent_state ?? null,
    privacyPolicyVersion: row.privacy_policy_version ?? null,
    privacyConsentedAt: row.privacy_consented_at ?? null,
    privacyRevokedAt: row.privacy_revoked_at ?? null,
    dataVersion: row.data_version ?? null,
    syncTokenExpiresAt: row.sync_token_expires_at ?? null,
  };
}

export async function getAccountExport(db: AccountDb, userId: string): Promise<AccountExport> {
  const user = await db
    .prepare(`SELECT id, name, email, emailVerified FROM "user" WHERE id = ? LIMIT 1`)
    .bind(userId)
    .first<UserRow>();
  if (!user) throw new AccountNotFoundError();

  const profile = await db
    .prepare(`SELECT display_name, timezone, locale, show_welcome, privacy_policy_version, privacy_consent_state, privacy_consented_at, privacy_revoked_at, data_version, sync_token_expires_at
      FROM profile_settings WHERE user_id = ? LIMIT 1`)
    .bind(userId)
    .first<ProfileRow>();

  const privacyEvents = await db
    .prepare(`SELECT policy_version, decision, decided_at FROM privacy_consent_events
      WHERE user_id = ? ORDER BY decided_at ASC`)
    .bind(userId)
    .all<PrivacyEventRow>();

  const modules: Record<string, RowByName[]> = {};
  for (const [resourceName, resource] of moduleTables()) {
    const rows = await db
      .prepare(`SELECT * FROM "${resource.table}" WHERE user_id = ?`)
      .bind(userId)
      .all<RowByName>();
    modules[resourceName] = rows.results.map((row) => ({ ...row })) as RowByName[];
  }

  const fileRows = await db
    .prepare(`SELECT id, module, object_key, content_type, byte_size, sha256, width, height, state
      FROM file_objects WHERE user_id = ?`)
    .bind(userId)
    .all<FileRow>();

  return {
    schemaVersion: "1.0.0",
    generatedAt: new Date().toISOString(),
    user: {
      id: user.id,
      name: user.name,
      email: user.email,
      emailVerified: user.emailVerified === 1,
    },
    profile: rowToProfilePayload(profile),
    privacyEvents: privacyEvents.results,
    modules,
    files: fileRows.results.map((file) => ({
      id: file.id,
      module: file.module,
      contentType: file.content_type,
      byteSize: file.byte_size,
      sha256: file.sha256,
      width: file.width,
      height: file.height,
      state: file.state,
    })),
  };
}

export async function getPrivacyState(db: AccountDb, userId: string): Promise<PrivacyStateSnapshot> {
  const profile = await db
    .prepare(`SELECT privacy_policy_version, privacy_consent_state, privacy_consented_at, privacy_revoked_at
      FROM profile_settings WHERE user_id = ? LIMIT 1`)
    .bind(userId)
    .first<Pick<ProfileRow, "privacy_policy_version" | "privacy_consent_state" | "privacy_consented_at" | "privacy_revoked_at">>();
  return {
    state: profile?.privacy_consent_state ?? "not_requested",
    policyVersion: profile?.privacy_policy_version ?? null,
    consentedAt: profile?.privacy_consented_at ?? null,
    revokedAt: profile?.privacy_revoked_at ?? null,
  };
}

export async function hashAccountExport(data: AccountExport): Promise<string> {
  return sha256(stableJson(data));
}

async function ensureProfileRow(db: AccountDb, userId: string): Promise<void> {
  const existing = await db
    .prepare(`SELECT user_id FROM profile_settings WHERE user_id = ? LIMIT 1`)
    .bind(userId)
    .first<{ user_id: string }>();
  if (existing) return;

  const now = Date.now();
  await db
    .prepare(
      `INSERT INTO profile_settings
        (user_id, display_name, timezone, locale, show_welcome, privacy_consent_state, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, 'not_requested', ?, ?)`,
    )
    .bind(userId, "未命名用户", "UTC", "zh-CN", now, now)
    .run();
}

async function getProfileState(db: AccountDb, userId: string): Promise<Pick<ProfileRow, "deletion_state" | "sync_token" | "sync_token_expires_at"> | null> {
  return db
    .prepare(`SELECT deletion_state, sync_token, sync_token_expires_at FROM profile_settings WHERE user_id = ? LIMIT 1`)
    .bind(userId)
    .first<Pick<ProfileRow, "deletion_state" | "sync_token" | "sync_token_expires_at">>();
}

export async function getDeletionState(db: AccountDb, userId: string): Promise<AccountDeletionInfo> {
  const row = await getProfileState(db, userId);
  if (!row) {
    return { state: "active", tokenExpiresAt: null };
  }
  return {
    state: row.deletion_state ?? "active",
    tokenExpiresAt: row.sync_token_expires_at ?? null,
  };
}

function parseDeleteDecision(input: unknown): { action: "request" | "confirm" | "undo"; recoveryToken?: string } {
  if (!input || typeof input !== "object") throw new AccountInputError("请求参数无效");
  const value = input as Record<string, unknown>;
  const action = typeof value.action === "string" ? value.action : "";
  if (action !== "request" && action !== "confirm" && action !== "undo") {
    throw new AccountInputError("action 必须是 request / confirm / undo");
  }
  if (action === "request") {
    return { action };
  }
  if (!isString(value.recoveryToken)) {
    throw new AccountInputError("缺少恢复令牌");
  }
  return { action, recoveryToken: value.recoveryToken };
}

export function parsePrivacyInput(input: unknown): { decision: "accepted" | "revoked"; policyVersion: string; noticeSha256: string } {
  if (!input || typeof input !== "object") throw new AccountInputError("请求参数无效");
  const value = input as Record<string, unknown>;
  if (value.decision !== "accepted" && value.decision !== "revoked") {
    throw new AccountInputError("decision 必须是 accepted 或 revoked");
  }
  if (!isPolicyVersion(value.policyVersion)) throw new AccountInputError("policyVersion 无效");
  if (!isSha256(value.noticeSha256)) throw new AccountInputError("noticeSha256 无效");
  return {
    decision: value.decision,
    policyVersion: value.policyVersion,
    noticeSha256: value.noticeSha256,
  };
}

export async function setPrivacyConsent(
  db: AccountDb,
  userId: string,
  input: { decision: "accepted" | "revoked"; policyVersion: string; noticeSha256: string },
): Promise<{
  privacyState: "accepted" | "revoked";
  privacyPolicyVersion: string;
  decidedAt: number;
}> {
  await ensureProfileRow(db, userId);
  const now = Date.now();

  await db
    .prepare(`UPDATE profile_settings
      SET privacy_policy_version = ?, privacy_consent_state = ?, privacy_consented_at = ?, privacy_revoked_at = ?, updated_at = ?
      WHERE user_id = ?`)
    .bind(
      input.policyVersion,
      input.decision,
      now,
      input.decision === "revoked" ? now : null,
      now,
      userId,
    )
    .run();

  await db
    .prepare(
      `INSERT INTO privacy_consent_events
        (id, user_id, policy_version, notice_sha256, decision, decided_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(crypto.randomUUID(), userId, input.policyVersion, input.noticeSha256, input.decision, now, now)
    .run();

  return {
    privacyState: input.decision,
    privacyPolicyVersion: input.policyVersion,
    decidedAt: now,
  };
}

export async function requestAccountDeletion(db: AccountDb, userId: string): Promise<ExportStartResult> {
  const exportData = await getAccountExport(db, userId);
  const exportHash = await hashAccountExport(exportData);
  const recoveryToken = crypto.randomUUID();
  const recoveryTokenDigest = await sha256(recoveryToken);
  const now = Date.now();
  await ensureProfileRow(db, userId);
  await db
    .prepare(`UPDATE profile_settings
      SET deletion_state = 'pending', sync_token = ?, sync_token_expires_at = ?, updated_at = ?
      WHERE user_id = ?`)
    .bind(recoveryTokenDigest, now + DELETION_TOKEN_TTL_MS, now, userId)
    .run();

  return { exportData, exportHash, recoveryToken };
}

async function assertDeletionToken(db: AccountDb, userId: string, recoveryToken: string): Promise<void> {
  const state = await getProfileState(db, userId);
  if (!state?.deletion_state || state.deletion_state !== "pending") {
    throw new AccountDeleteStateError("当前未进入删除待确认状态");
  }
  if (!state.sync_token) throw new AccountDeleteStateError("未找到删除令牌");
  if (typeof state.sync_token_expires_at !== "number" || state.sync_token_expires_at < Date.now()) {
    throw new AccountDeleteStateError("删除令牌已过期");
  }
  const provided = await sha256(recoveryToken);
  if (state.sync_token !== provided) throw new AccountDeleteStateError("删除令牌无效");
}

async function clearDeletionFlags(db: AccountDb, userId: string): Promise<void> {
  await db
    .prepare(`UPDATE profile_settings
      SET deletion_state = 'active', sync_token = NULL, sync_token_expires_at = NULL, updated_at = ?
      WHERE user_id = ?`)
    .bind(Date.now(), userId)
    .run();
}

async function removeAccountData(
  db: AccountDb,
  fileEnv: FileStoreEnv,
  userId: string,
): Promise<void> {
  const files = await db
    .prepare("SELECT id, object_key FROM file_objects WHERE user_id = ?")
    .bind(userId)
    .all<Pick<FileRow, "id" | "object_key">>();
  const fileRows = files.results;

  for (const file of fileRows) {
    try {
      await fileEnv.FILES?.delete(file.object_key);
    } catch {
      // R2 delete is best-effort: metadata deletion is still required to complete account reset.
    }
  }

  await db.prepare("DELETE FROM file_objects WHERE user_id = ?").bind(userId).run();
  for (const tableName of ["security_audit_events", "privacy_consent_events"]) {
    await db.prepare(`DELETE FROM "${tableName}" WHERE user_id = ?`).bind(userId).run();
  }
  await db.prepare("DELETE FROM outbox_events WHERE user_id = ?").bind(userId).run();
  await db.prepare("DELETE FROM idempotency_keys WHERE user_id = ?").bind(userId).run();
  await db.prepare("DELETE FROM legacy_imports WHERE user_id = ?").bind(userId).run();
  await db.prepare("DELETE FROM verification WHERE identifier IN (SELECT email FROM \"user\" WHERE id = ?)").bind(userId).run();
  await db.prepare("DELETE FROM profile_settings WHERE user_id = ?").bind(userId).run();
  await db.prepare("DELETE FROM user WHERE id = ?").bind(userId).run();
}

export async function undoAccountDeletion(db: AccountDb, userId: string, input: { recoveryToken: string }): Promise<void> {
  await assertDeletionToken(db, userId, input.recoveryToken);
  await clearDeletionFlags(db, userId);
}

export async function confirmAccountDeletion(
  db: Pick<D1Database, "prepare">,
  fileEnv: FileStoreEnv,
  userId: string,
  input: { recoveryToken: string },
): Promise<void> {
  await assertDeletionToken(db, userId, input.recoveryToken);
  await db.prepare("DELETE FROM outbox_events WHERE user_id = ?").bind(userId).run();
  await removeAccountData(db, fileEnv, userId);
}

export async function processDeleteRequest(
  db: Pick<D1Database, "prepare">,
  fileEnv: FileStoreEnv,
  userId: string,
  body: unknown,
): Promise<{ action: "request" | "confirm" | "undo"; recoveryToken?: string; exportData?: AccountExport; exportHash?: string }> {
  const parsed = parseDeleteDecision(body);
  if (parsed.action === "request") {
    const result = await requestAccountDeletion(db, userId);
    return { action: "request", recoveryToken: result.recoveryToken, exportData: result.exportData, exportHash: result.exportHash };
  }
  if (parsed.action === "confirm") {
    await confirmAccountDeletion(db, fileEnv, userId, { recoveryToken: parsed.recoveryToken! });
    return { action: "confirm" };
  }
  await undoAccountDeletion(db, userId, { recoveryToken: parsed.recoveryToken! });
  return { action: "undo" };
}

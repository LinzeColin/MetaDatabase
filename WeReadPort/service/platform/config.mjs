import { parseKeyring } from "./crypto.mjs";

const DEFAULT_BASE_URL = "https://weread.linzezhang.com";
const TASKPACK_VERSION = "v0.0.0.1.9";

export function loadConfig(env = process.env, { test = false } = {}) {
  const production = String(env.NODE_ENV ?? "production") === "production" && !test;
  const sessionPepper = requiredBytes(env.WRP_SESSION_PEPPER, "WRP_SESSION_PEPPER", test);
  const credentialPepper = requiredBytes(env.WRP_CREDENTIAL_PEPPER, "WRP_CREDENTIAL_PEPPER", test);
  const keyringRaw = env.WRP_KEYRING_JSON || (test ? JSON.stringify({ test: Buffer.alloc(32, 7).toString("base64") }) : "");
  const activeKeyId = env.WRP_ACTIVE_KEY_ID || (test ? "test" : "");
  const keyring = parseKeyring(keyringRaw, activeKeyId);
  const baseUrl = optionalOrigin(env.WRP_PUBLIC_BASE_URL || DEFAULT_BASE_URL, "WRP_PUBLIC_BASE_URL", production);
  const adminBaseUrl = optionalOrigin(env.WRP_ADMIN_BASE_URL, "WRP_ADMIN_BASE_URL", production);
  const adminAccountIds = parseAdminAccountIds(env.WRP_ADMIN_ACCOUNT_IDS || "");
  if (adminAccountIds.length && !adminBaseUrl) throw new Error("配置管理员账户时必须同时设置 WRP_ADMIN_BASE_URL。");
  const internalProxySecret = String(env.WRP_INTERNAL_PROXY_SECRET || (test ? "test-internal-proxy-secret-not-for-production" : ""));
  if (!internalProxySecret) throw new Error("缺少 WRP_INTERNAL_PROXY_SECRET。");
  const releaseIdentity = Object.freeze({
    taskpackVersion: String(env.WRP_TASKPACK_VERSION || TASKPACK_VERSION),
    releaseCommit: String(env.WRP_RELEASE_COMMIT || (test ? "test-release-commit" : "")),
    ovhReleaseId: String(env.WRP_OVH_RELEASE_ID || (test ? "test-ovh-release" : "")),
    sitesProjectId: String(env.WRP_SITES_PROJECT_ID || (test ? "test-sites-project" : "")),
  });
  if (releaseIdentity.taskpackVersion !== TASKPACK_VERSION) throw new Error("WRP_TASKPACK_VERSION 与冻结版本不一致。");
  if (production && (!/^[0-9a-f]{40}$/.test(releaseIdentity.releaseCommit) || !safeReleaseId(releaseIdentity.ovhReleaseId) || !safeReleaseId(releaseIdentity.sitesProjectId))) {
    throw new Error("生产部署身份缺少或无效：release commit 必须为 40 位 SHA，OVH release ID 与 Sites project ID 必须为安全标识。");
  }
  const primaryObjectPrefix = safePrefix(env.WRP_PRIMARY_OBJECT_PREFIX || "primary-objects", "WRP_PRIMARY_OBJECT_PREFIX");
  const privateDatabaseBackupPrefix = safePrefix(env.WRP_PRIVATE_DATABASE_BACKUP_PREFIX || "backups/private-database", "WRP_PRIVATE_DATABASE_BACKUP_PREFIX");
  if (primaryObjectPrefix === privateDatabaseBackupPrefix || primaryObjectPrefix.startsWith(`${privateDatabaseBackupPrefix}/`) || privateDatabaseBackupPrefix.startsWith(`${primaryObjectPrefix}/`)) {
    throw new Error("R2 权威对象与 Private-Database 冷备命名空间必须隔离。");
  }
  return Object.freeze({
    production,
    baseUrl: baseUrl.origin,
    adminBaseUrl: adminBaseUrl?.origin || "",
    allowedOrigins: Object.freeze([...new Set([baseUrl.origin, adminBaseUrl?.origin].filter(Boolean))]),
    adminAccountIds: Object.freeze(adminAccountIds),
    serviceHost: env.WRP_SERVICE_HOST || "127.0.0.1",
    servicePort: integer(env.WRP_SERVICE_PORT, 8788, 1, 65535),
    databasePath: env.WRP_DATABASE_PATH || "/var/lib/weread-port/platform.sqlite3",
    objectStoreMode: env.WRP_OBJECT_STORE_MODE || (test ? "memory" : "r2"),
    fileObjectRoot: env.WRP_FILE_OBJECT_ROOT || "/var/lib/weread-port/objects",
    primaryObjectPrefix,
    privateDatabaseBackupPrefix,
    releaseIdentity,
    r2: Object.freeze({
      endpoint: env.WRP_R2_ENDPOINT || "",
      bucket: env.WRP_R2_BUCKET || "",
      accessKeyId: env.WRP_R2_ACCESS_KEY_ID || "",
      secretAccessKey: env.WRP_R2_SECRET_ACCESS_KEY || "",
      region: env.WRP_R2_REGION || "auto",
    }),
    privateDatabase: Object.freeze({
      repository: env.WRP_PRIVATE_DATABASE_REPOSITORY || "LinzeColin/Private-Database",
      branch: env.WRP_PRIVATE_DATABASE_BRANCH || "main",
      token: env.WRP_PRIVATE_DATABASE_TOKEN || "",
      factsPath: env.WRP_PRIVATE_DATABASE_FACTS_PATH || "systems/weread-port",
    }),
    sessionPepper,
    credentialPepper,
    keyring,
    internalProxySecret,
    sessionTtlSeconds: integer(env.WRP_SESSION_TTL_SECONDS, 30 * 24 * 3600, 900, 90 * 24 * 3600),
    recentAuthSeconds: integer(env.WRP_RECENT_AUTH_SECONDS, 15 * 60, 60, 3600),
    oauthTtlSeconds: integer(env.WRP_OAUTH_TTL_SECONDS, 10 * 60, 60, 1800),
    maxJsonBytes: integer(env.WRP_MAX_JSON_BYTES, 2 * 1024 * 1024, 1024, 16 * 1024 * 1024),
    maxImportBytes: integer(env.WRP_MAX_IMPORT_BYTES, 50 * 1024 * 1024, 1024, 512 * 1024 * 1024),
    maxImportItems: integer(env.WRP_MAX_IMPORT_ITEMS, 500, 1, 5000),
    maxWereadBooks: integer(env.WRP_MAX_WEREAD_BOOKS, 2000, 6, 10000),
    upstreamTimeoutMs: integer(env.WRP_UPSTREAM_TIMEOUT_MS, 15_000, 500, 120_000),
    upstreamRetryAttempts: integer(env.WRP_UPSTREAM_RETRY_ATTEMPTS, 2, 1, 3),
    readinessCacheSeconds: integer(env.WRP_READINESS_CACHE_SECONDS, 30, 1, 300),
    authFailureLimit: integer(env.WRP_AUTH_FAILURE_LIMIT, 8, 3, 30),
    authFailureWindowSeconds: integer(env.WRP_AUTH_FAILURE_WINDOW_SECONDS, 15 * 60, 60, 24 * 3600),
    authLockSeconds: integer(env.WRP_AUTH_LOCK_SECONDS, 15 * 60, 60, 24 * 3600),
    importLeaseSeconds: integer(env.WRP_IMPORT_LEASE_SECONDS, 5 * 60, 30, 3600),
    workerStaleSeconds: integer(env.WRP_WORKER_STALE_SECONDS, 30, 5, 300),
    objectHealthProbePrefix: `${primaryObjectPrefix}/${safePrefix(env.WRP_OBJECT_HEALTH_PROBE_PREFIX || "_system/readiness", "WRP_OBJECT_HEALTH_PROBE_PREFIX")}`,
    providers: Object.freeze({
      google: provider(env, "GOOGLE"),
      github: provider(env, "GITHUB"),
      notion: provider(env, "NOTION"),
    }),
  });
}

function provider(env, name) {
  return Object.freeze({
    clientId: env[`WRP_${name}_CLIENT_ID`] || "",
    clientSecret: env[`WRP_${name}_CLIENT_SECRET`] || "",
  });
}

function requiredBytes(raw, name, test) {
  const source = raw || (test ? Buffer.alloc(32, name.length).toString("base64") : "");
  const bytes = Buffer.from(source, "base64");
  if (bytes.length < 32) throw new Error(`${name} 必须至少是 32 字节 Base64。`);
  return bytes;
}

function integer(value, fallback, min, max) {
  const number = Number(value ?? fallback);
  if (!Number.isInteger(number) || number < min || number > max) throw new Error(`数值配置超出范围：${value}`);
  return number;
}

function safePrefix(value, name) {
  const text = String(value || "").replace(/^\/+|\/+$/g, "");
  if (!text || text.split("/").some(part => !/^[A-Za-z0-9._-]+$/.test(part) || part === "..")) throw new Error(`${name} 无效。`);
  return text;
}

function safeReleaseId(value) { return /^[A-Za-z0-9._:-]{3,160}$/.test(String(value || "")); }

function optionalOrigin(raw, name, production) {
  const value = String(raw || "").trim();
  if (!value) return null;
  let parsed;
  try { parsed = new URL(value); } catch { throw new Error(`${name} 必须是 HTTPS origin。`); }
  if (parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash || (production && parsed.protocol !== "https:")) throw new Error(`${name} 必须是无凭证、无路径、无查询参数的 HTTPS origin。`);
  return parsed;
}

function parseAdminAccountIds(raw) {
  const ids = [...new Set(String(raw || "").split(",").map(value => value.trim()).filter(Boolean))];
  if (ids.some(id => !/^acct_[A-Za-z0-9_-]{8,200}$/.test(id))) throw new Error("WRP_ADMIN_ACCOUNT_IDS 包含无效账户 ID。");
  return ids;
}

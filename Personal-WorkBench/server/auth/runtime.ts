import type { MailProvider } from "./mail";

export type AuthRuntimeEnv = {
  DB?: D1Database;
  BETTER_AUTH_SECRET?: string;
  APP_ORIGIN?: string;
  APP_TRUSTED_ORIGINS?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  RESEND_API_KEY?: string;
  NITROSEND_API_KEY?: string;
  MAIL_PROVIDER?: string;
  AUTH_FROM_EMAIL?: string;
  MAIL_FROM?: string;
  TURNSTILE_SECRET_KEY?: string;
  TURNSTILE_SITE_KEY?: string;
  LEGAL_OPERATOR_NAME?: string;
  PRIVACY_CONTACT_EMAIL?: string;
};

export type AuthRuntimeConfig = {
  db: D1Database;
  appOrigin: string;
  trustedOrigins: string[];
  authSecret: string;
  googleClientId: string;
  googleClientSecret: string;
  mailProvider: MailProvider;
  mailApiKey: string;
  fromEmail: string;
  turnstileSecretKey: string;
  turnstileSiteKey: string;
};

/**
 * Deliberately coarse, value-free readiness categories. These may be emitted
 * to protected worker logs while diagnosing an unavailable authentication
 * runtime; they never contain a setting name, a secret, an Origin, or a user
 * identifier.
 */
export type AuthRuntimeMissingCategory =
  | "d1_binding"
  | "app_origin"
  | "auth_secret"
  | "google_oauth"
  | "transactional_mail"
  | "mail_from"
  | "turnstile";

export class AuthRuntimeNotReadyError extends Error {
  code = "AUTH_RUNTIME_NOT_READY";
  readonly missingCategories: readonly AuthRuntimeMissingCategory[];

  constructor(missingCategories: readonly AuthRuntimeMissingCategory[] = []) {
    super("Authentication runtime is not ready.");
    this.missingCategories = [...new Set(missingCategories)];
  }
}

function nonEmpty(value: string | undefined): string | null {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

function canonicalOrigin(value: string | undefined): string | null {
  const raw = nonEmpty(value);
  if (!raw) return null;

  try {
    const url = new URL(raw);
    const localHttp =
      url.protocol === "http:" &&
      (url.hostname === "localhost" || url.hostname === "127.0.0.1");

    if ((!localHttp && url.protocol !== "https:") || url.pathname !== "/" || url.search || url.hash) {
      return null;
    }

    return url.origin;
  } catch {
    return null;
  }
}

/**
 * APP_ORIGIN is the primary canonical URL used for new callbacks and mail.
 * APP_TRUSTED_ORIGINS is an optional, comma-separated allowlist for a bounded
 * dual-domain migration. It never widens to arbitrary request hosts: every
 * entry must itself be a canonical first-party Origin.
 */
function resolveTrustedOrigins(appOrigin: string | null, value: string | undefined): string[] | null {
  if (!appOrigin) return null;

  const configured = nonEmpty(value);
  if (!configured) return [appOrigin];

  const extras = configured
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  if (extras.length === 0) return null;

  const origins = [appOrigin];
  for (const entry of extras) {
    const origin = canonicalOrigin(entry);
    if (!origin) return null;
    origins.push(origin);
  }
  return [...new Set(origins)];
}

function publicContactEmail(value: string | undefined): string | null {
  const normalized = nonEmpty(value);
  if (!normalized || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) return null;
  return normalized;
}

function resolveMailProvider(env: AuthRuntimeEnv): {
  provider: MailProvider;
  apiKey: string;
} | null {
  const resendApiKey = nonEmpty(env.RESEND_API_KEY);
  const nitrosendApiKey = nonEmpty(env.NITROSEND_API_KEY);
  const requestedProvider = nonEmpty(env.MAIL_PROVIDER)?.toLowerCase();

  if (requestedProvider && requestedProvider !== "resend" && requestedProvider !== "nitrosend") {
    return null;
  }
  if (requestedProvider === "resend") {
    return resendApiKey ? { provider: "resend", apiKey: resendApiKey } : null;
  }
  if (requestedProvider === "nitrosend") {
    return nitrosendApiKey ? { provider: "nitrosend", apiKey: nitrosendApiKey } : null;
  }

  // Without an explicit selector, only the frozen Resend default is allowed.
  // NitroSend is a controlled alternate and must never be inferred from a key.
  if (resendApiKey) return { provider: "resend", apiKey: resendApiKey };
  return null;
}

/**
 * Return only stable operational categories so protected worker logs can
 * distinguish a missing binding from a provider configuration issue without
 * retaining settings, secrets, Origins, or account data.
 */
export function getAuthRuntimeMissingCategories(
  env: AuthRuntimeEnv,
): AuthRuntimeMissingCategory[] {
  const categories: AuthRuntimeMissingCategory[] = [];
  const appOrigin = canonicalOrigin(env.APP_ORIGIN);
  const trustedOrigins = resolveTrustedOrigins(appOrigin, env.APP_TRUSTED_ORIGINS);
  const authSecret = nonEmpty(env.BETTER_AUTH_SECRET);
  const authFromEmail = nonEmpty(env.AUTH_FROM_EMAIL);
  const mailFrom = nonEmpty(env.MAIL_FROM);
  const aliasesConflict = Boolean(
    authFromEmail && mailFrom && authFromEmail.toLowerCase() !== mailFrom.toLowerCase(),
  );

  if (!env.DB) categories.push("d1_binding");
  if (!appOrigin || !trustedOrigins) categories.push("app_origin");
  if (!authSecret || authSecret.length < 32) {
    categories.push("auth_secret");
  }
  if (!nonEmpty(env.GOOGLE_CLIENT_ID) || !nonEmpty(env.GOOGLE_CLIENT_SECRET)) {
    categories.push("google_oauth");
  }
  if (!resolveMailProvider(env)) categories.push("transactional_mail");
  if ((!authFromEmail && !mailFrom) || aliasesConflict) categories.push("mail_from");
  if (!nonEmpty(env.TURNSTILE_SECRET_KEY) || !nonEmpty(env.TURNSTILE_SITE_KEY)) {
    categories.push("turnstile");
  }

  return categories;
}

/**
 * This intentionally returns a single generic readiness state. Neither route
 * responses nor browser pages enumerate unavailable settings or secret names.
 */
export function readAuthRuntimeConfig(env: AuthRuntimeEnv): AuthRuntimeConfig | null {
  const appOrigin = canonicalOrigin(env.APP_ORIGIN);
  const trustedOrigins = resolveTrustedOrigins(appOrigin, env.APP_TRUSTED_ORIGINS);
  const authSecret = nonEmpty(env.BETTER_AUTH_SECRET);
  const googleClientId = nonEmpty(env.GOOGLE_CLIENT_ID);
  const googleClientSecret = nonEmpty(env.GOOGLE_CLIENT_SECRET);
  const mailProvider = resolveMailProvider(env);
  const authFromEmail = nonEmpty(env.AUTH_FROM_EMAIL);
  const mailFrom = nonEmpty(env.MAIL_FROM);
  // MAIL_FROM is the frozen Sites binding name. AUTH_FROM_EMAIL is the
  // application name kept for backwards compatibility. If both are present,
  // fail closed rather than silently send mail from an unexpected address.
  if (authFromEmail && mailFrom && authFromEmail.toLowerCase() !== mailFrom.toLowerCase()) return null;
  const fromEmail = authFromEmail ?? mailFrom;
  const turnstileSecretKey = nonEmpty(env.TURNSTILE_SECRET_KEY);
  const turnstileSiteKey = nonEmpty(env.TURNSTILE_SITE_KEY);

  if (
    getAuthRuntimeMissingCategories(env).length > 0 ||
    !env.DB ||
    !appOrigin ||
    !trustedOrigins ||
    !authSecret ||
    authSecret.length < 32 ||
    !googleClientId ||
    !googleClientSecret ||
    !mailProvider ||
    !fromEmail ||
    !turnstileSecretKey ||
    !turnstileSiteKey
  ) {
    return null;
  }

  return {
    db: env.DB,
    appOrigin,
    trustedOrigins,
    authSecret,
    googleClientId,
    googleClientSecret,
    mailProvider: mailProvider.provider,
    mailApiKey: mailProvider.apiKey,
    fromEmail,
    turnstileSecretKey,
    turnstileSiteKey,
  };
}

export function getPublicAuthPageConfig(env: AuthRuntimeEnv): {
  turnstileSiteKey: string | null;
  googleClientId: string | null;
  legalOperatorName: string | null;
  privacyContactEmail: string | null;
} {
  const config = readAuthRuntimeConfig(env);
  return {
    turnstileSiteKey: config?.turnstileSiteKey ?? null,
    // OAuth client IDs identify the public browser application. The paired
    // client secret remains exclusively inside the server runtime.
    googleClientId: config?.googleClientId ?? null,
    legalOperatorName: nonEmpty(env.LEGAL_OPERATOR_NAME),
    privacyContactEmail: publicContactEmail(env.PRIVACY_CONTACT_EMAIL),
  };
}

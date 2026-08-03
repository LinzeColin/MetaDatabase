export type AuthRuntimeEnv = {
  DB?: D1Database;
  BETTER_AUTH_SECRET?: string;
  APP_ORIGIN?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  RESEND_API_KEY?: string;
  AUTH_FROM_EMAIL?: string;
  TURNSTILE_SECRET_KEY?: string;
  TURNSTILE_SITE_KEY?: string;
};

export type AuthRuntimeConfig = {
  db: D1Database;
  appOrigin: string;
  authSecret: string;
  googleClientId: string;
  googleClientSecret: string;
  resendApiKey: string;
  fromEmail: string;
  turnstileSecretKey: string;
  turnstileSiteKey: string;
};

export class AuthRuntimeNotReadyError extends Error {
  code = "AUTH_RUNTIME_NOT_READY";

  constructor() {
    super("Authentication runtime is not ready.");
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
 * This intentionally returns a single generic readiness state. Neither route
 * responses nor browser pages enumerate unavailable settings or secret names.
 */
export function readAuthRuntimeConfig(env: AuthRuntimeEnv): AuthRuntimeConfig | null {
  const appOrigin = canonicalOrigin(env.APP_ORIGIN);
  const authSecret = nonEmpty(env.BETTER_AUTH_SECRET);
  const googleClientId = nonEmpty(env.GOOGLE_CLIENT_ID);
  const googleClientSecret = nonEmpty(env.GOOGLE_CLIENT_SECRET);
  const resendApiKey = nonEmpty(env.RESEND_API_KEY);
  const fromEmail = nonEmpty(env.AUTH_FROM_EMAIL);
  const turnstileSecretKey = nonEmpty(env.TURNSTILE_SECRET_KEY);
  const turnstileSiteKey = nonEmpty(env.TURNSTILE_SITE_KEY);

  if (
    !env.DB ||
    !appOrigin ||
    !authSecret ||
    authSecret.length < 32 ||
    !googleClientId ||
    !googleClientSecret ||
    !resendApiKey ||
    !fromEmail ||
    !turnstileSecretKey ||
    !turnstileSiteKey
  ) {
    return null;
  }

  return {
    db: env.DB,
    appOrigin,
    authSecret,
    googleClientId,
    googleClientSecret,
    resendApiKey,
    fromEmail,
    turnstileSecretKey,
    turnstileSiteKey,
  };
}

export function getPublicAuthPageConfig(env: AuthRuntimeEnv): {
  turnstileSiteKey: string | null;
} {
  const config = readAuthRuntimeConfig(env);
  return { turnstileSiteKey: config?.turnstileSiteKey ?? null };
}

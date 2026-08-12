import { getSessionCookie } from "better-auth/cookies";
import {
  legacyHandoffTarget,
  parseLegacyHandoffId,
} from "@/app/_components/workbench/legacy-domain-handoff";
import {
  CANONICAL_MYDAIRY_ORIGIN,
  RETIRED_COMPATIBILITY_HOST,
  isRetiredCompatibilityHost,
} from "@/app/_components/workbench/canonical-domain";

export {
  LEGACY_DOMAIN_HANDOFF_COMPLETE_URL,
  canonicalHandoffDestination,
  legacyHandoffTarget,
  parseLegacyHandoffId,
} from "@/app/_components/workbench/legacy-domain-handoff";
export const LEGACY_DOMAIN_HANDOFF_TTL_MS = 60_000;

const HANDOFF_IDENTIFIER_PREFIX = "mydairy:legacy-domain-handoff:";
const SECURE_SESSION_COOKIE_NAME = "__Secure-better-auth.session_token";
const LEGACY_DOMAIN_ORIGIN = `https://${RETIRED_COMPATIBILITY_HOST}`;
const SIGNED_SESSION_COOKIE_PATTERN = /^[A-Za-z0-9._~-]{20,2048}$/;

type HandoffDatabase = Pick<D1Database, "prepare">;

export type LegacyDomainHandoff = {
  sessionCookie: string;
  targetPath: string;
};

type StoredLegacyDomainHandoff = {
  sessionCookie: string;
  targetPath: string;
  version: 1;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isSafeSignedSessionCookie(value: unknown): value is string {
  return typeof value === "string" && SIGNED_SESSION_COOKIE_PATTERN.test(value);
}

function handoffIdentifier(handoffId: string): string {
  return `${HANDOFF_IDENTIFIER_PREFIX}${handoffId}`;
}

function parseStoredHandoff(value: unknown): LegacyDomainHandoff | null {
  if (!isRecord(value) || value.version !== 1) return null;
  const targetPath = legacyHandoffTarget(value.targetPath);
  return isSafeSignedSessionCookie(value.sessionCookie) && targetPath
    ? { sessionCookie: value.sessionCookie, targetPath }
    : null;
}

/** Only the retired hostname itself may ask the canonical site for a handoff. */
export function isRetiredHandoffIssuanceRequest(request: Request): boolean {
  try {
    return isRetiredCompatibilityHost(new URL(request.url).host)
      && request.headers.get("origin") === LEGACY_DOMAIN_ORIGIN;
  } catch {
    return false;
  }
}

/** The canonical consumer accepts only a browser form POST from the retired host. */
export function isCanonicalHandoffCompletionRequest(request: Request): boolean {
  try {
    return new URL(request.url).origin === CANONICAL_MYDAIRY_ORIGIN
      && request.headers.get("origin") === LEGACY_DOMAIN_ORIGIN;
  } catch {
    return false;
  }
}

export function newLegacyHandoffId(randomId = crypto.randomUUID()): string {
  const handoffId = parseLegacyHandoffId(randomId);
  if (!handoffId) throw new Error("invalid legacy handoff identifier");
  return handoffId;
}

/** Extract only Better Auth's signed, HttpOnly session cookie; no browser storage is consulted. */
export function legacySignedSessionCookie(headers: Headers): string | null {
  const sessionCookie = getSessionCookie(headers);
  return isSafeSignedSessionCookie(sessionCookie) ? sessionCookie : null;
}

/**
 * The value is held in the existing short-lived verification store, keyed by
 * an opaque UUID. The browser receives only that UUID, never the session
 * cookie itself. Consumption deletes the row before the canonical cookie is
 * written, which makes the handoff single-use.
 */
export async function issueLegacyDomainHandoff(
  db: HandoffDatabase,
  handoff: LegacyDomainHandoff,
  now = Date.now(),
  handoffId = newLegacyHandoffId(),
): Promise<string> {
  const targetPath = legacyHandoffTarget(handoff.targetPath);
  if (!isSafeSignedSessionCookie(handoff.sessionCookie) || !Number.isFinite(now)) {
    throw new Error("invalid legacy handoff input");
  }
  const expiresAt = now + LEGACY_DOMAIN_HANDOFF_TTL_MS;
  const value: StoredLegacyDomainHandoff = {
    sessionCookie: handoff.sessionCookie,
    targetPath,
    version: 1,
  };

  await db.prepare(
    'DELETE FROM "verification" WHERE "identifier" LIKE ? AND "expiresAt" <= ?',
  ).bind(`${HANDOFF_IDENTIFIER_PREFIX}%`, now).run();
  await db.prepare(
    'INSERT INTO "verification" ("id", "identifier", "value", "expiresAt", "createdAt", "updatedAt") VALUES (?, ?, ?, ?, ?, ?)',
  ).bind(handoffId, handoffIdentifier(handoffId), JSON.stringify(value), expiresAt, now, now).run();
  return handoffId;
}

export async function consumeLegacyDomainHandoff(
  db: HandoffDatabase,
  handoffId: string,
  now = Date.now(),
): Promise<LegacyDomainHandoff | null> {
  const normalizedId = parseLegacyHandoffId(handoffId);
  if (!normalizedId || !Number.isFinite(now)) return null;
  const row = await db.prepare(
    'DELETE FROM "verification" WHERE "identifier" = ? AND "expiresAt" > ? RETURNING "value"',
  ).bind(handoffIdentifier(normalizedId), now).first<{ value?: unknown }>();
  if (!row || typeof row.value !== "string") return null;
  try {
    return parseStoredHandoff(JSON.parse(row.value));
  } catch {
    return null;
  }
}

/** Reuses the already signed Better Auth token without exposing it to the browser. */
export function legacyHandoffSessionHeaders(sessionCookie: string): Headers | null {
  if (!isSafeSignedSessionCookie(sessionCookie)) return null;
  return new Headers({ Cookie: `${SECURE_SESSION_COOKIE_NAME}=${encodeURIComponent(sessionCookie)}` });
}

export function legacyHandoffSessionCookieHeader(
  sessionCookie: string,
  sessionExpiresAt: unknown,
  now = Date.now(),
): string | null {
  if (!isSafeSignedSessionCookie(sessionCookie) || !Number.isFinite(now)) return null;
  const expiresAt = sessionExpiresAt instanceof Date
    ? sessionExpiresAt.getTime()
    : typeof sessionExpiresAt === "number"
      ? sessionExpiresAt
      : typeof sessionExpiresAt === "string"
        ? new Date(sessionExpiresAt).getTime()
        : Number.NaN;
  if (!Number.isFinite(expiresAt) || expiresAt <= now) return null;
  const maxAge = Math.max(1, Math.floor((expiresAt - now) / 1_000));
  return `${SECURE_SESSION_COOKIE_NAME}=${encodeURIComponent(sessionCookie)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

export function transferableAuthSession(value: unknown): value is {
  session: { expiresAt: unknown };
  user: { id: string };
} {
  return isRecord(value)
    && isRecord(value.session)
    && isRecord(value.user)
    && typeof value.user.id === "string"
    && value.user.id.length > 0;
}

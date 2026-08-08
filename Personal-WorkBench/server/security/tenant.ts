export type SessionIdentity = {
  userId: string;
  email: string;
};

export class UnauthorizedError extends Error {
  status = 401;
  code = "UNAUTHORIZED";

  constructor() {
    super("Authentication is required.");
  }
}

export class VerificationRequiredError extends Error {
  status = 403;
  code = "EMAIL_VERIFICATION_REQUIRED";

  constructor() {
    super("Email verification is required.");
  }
}

export class ReauthenticationRequiredError extends Error {
  status = 403;
  code = "REAUTHENTICATION_REQUIRED";

  constructor() {
    super("A recent authentication is required.");
  }
}

export class NotAccessibleError extends Error {
  status = 404;
  code = "NOT_FOUND";

  constructor() {
    super("The requested resource was not found.");
  }
}

export class TenantInputError extends Error {
  status = 400;
  code = "INVALID_TENANT_INPUT";

  constructor() {
    super("Client ownership fields are not allowed.");
  }
}

const forbiddenTenantKeys = new Set([
  "userid",
  "user",
  "ownerid",
  "owner",
  "tenantid",
  "tenant",
  "accountid",
]);

function canonicalKey(key: string): string {
  return key.replaceAll(/[^a-zA-Z0-9]/g, "").toLowerCase();
}

function containsTenantField(input: unknown): boolean {
  if (Array.isArray(input)) return input.some(containsTenantField);
  if (!input || typeof input !== "object") return false;

  return Object.entries(input as Record<string, unknown>).some(
    ([key, value]) => forbiddenTenantKeys.has(canonicalKey(key)) || containsTenantField(value),
  );
}

/** Rejects direct and nested client attempts to select a tenant or owner. */
export function rejectClientTenantFields(input: unknown): void {
  if (containsTenantField(input)) throw new TenantInputError();
}

export function requireVerifiedIdentity(session: unknown): SessionIdentity {
  if (!session || typeof session !== "object") throw new UnauthorizedError();

  const user = (session as { user?: unknown }).user;
  if (!user || typeof user !== "object") throw new UnauthorizedError();

  const { id, email, emailVerified } = user as {
    id?: unknown;
    email?: unknown;
    emailVerified?: unknown;
  };
  if (typeof id !== "string" || !id || typeof email !== "string" || !email) {
    throw new UnauthorizedError();
  }
  if (emailVerified !== true) throw new VerificationRequiredError();

  return { userId: id, email };
}

function sessionCreatedAt(session: unknown): number | null {
  if (!session || typeof session !== "object") return null;
  const value = (session as { session?: { createdAt?: unknown } }).session?.createdAt;
  if (value instanceof Date) return Number.isFinite(value.getTime()) ? value.getTime() : null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/** Better Auth creates a new session after a password/OIDC reauthentication. */
export function requireFreshVerifiedIdentity(
  session: unknown,
  maxAgeMs = 10 * 60 * 1000,
  now = Date.now(),
): SessionIdentity {
  const identity = requireVerifiedIdentity(session);
  const createdAt = sessionCreatedAt(session);
  if (
    createdAt === null ||
    !Number.isFinite(maxAgeMs) ||
    maxAgeMs <= 0 ||
    createdAt > now + 5 * 60 * 1000 ||
    now - createdAt >= maxAgeMs
  ) {
    throw new ReauthenticationRequiredError();
  }
  return identity;
}

export function tenantWhere(userId: string): { sql: "user_id = ?"; values: [string] } {
  return { sql: "user_id = ?", values: [userId] };
}

export function assertOwned(recordUserId: string | null | undefined, userId: string): void {
  if (!recordUserId || recordUserId !== userId) throw new NotAccessibleError();
}

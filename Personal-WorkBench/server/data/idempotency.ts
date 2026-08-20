type IdempotencyDb = Pick<SqlDatabase, "prepare">;

type IdempotencyRecord = {
  request_hash: string;
  state: "started" | "completed" | "failed";
};

export class IdempotencyError extends Error {
  status = 400;
  code = "IDEMPOTENCY_KEY_REQUIRED";

  constructor() {
    super("A valid idempotency key is required.");
  }
}

export class IdempotencyConflictError extends Error {
  status = 409;
  code = "IDEMPOTENCY_KEY_REUSED";

  constructor() {
    super("An idempotency key cannot be reused for a different request.");
  }
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (!value || typeof value !== "object") return JSON.stringify(value);

  return `{${Object.keys(value as Record<string, unknown>)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key])}`)
    .join(",")}}`;
}

export async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function requireKey(value: string | null): string {
  if (!value || value.length < 12 || value.length > 200 || !/^[A-Za-z0-9._~-]+$/.test(value)) {
    throw new IdempotencyError();
  }
  return value;
}

export async function stableRecordId(
  userId: string,
  endpoint: string,
  idempotencyKey: string,
): Promise<string> {
  const digest = await sha256(`${userId}\n${endpoint}\n${idempotencyKey}`);
  return `rec_${digest.slice(0, 32)}`;
}

export type IdempotencyLease = {
  replayed: boolean;
  complete(): Promise<void>;
  fail(): Promise<void>;
};

/**
 * Records only a request digest, never the request body. A completed matching
 * retry becomes a no-op; a changed request with the same key is rejected.
 */
export async function beginIdempotentWrite(
  db: IdempotencyDb,
  input: {
    userId: string;
    endpoint: string;
    idempotencyKey: string | null;
    payload: unknown;
  },
): Promise<IdempotencyLease> {
  const idempotencyKey = requireKey(input.idempotencyKey);
  const requestHash = await sha256(stableJson(input.payload));
  const now = Date.now();
  const existing = await db
    .prepare(
      `SELECT request_hash, state FROM idempotency_keys
       WHERE user_id = ? AND endpoint = ? AND idempotency_key = ?`,
    )
    .bind(input.userId, input.endpoint, idempotencyKey)
    .first<IdempotencyRecord>();

  if (existing && existing.request_hash !== requestHash) throw new IdempotencyConflictError();

  if (!existing) {
    await db
      .prepare(
        `INSERT INTO idempotency_keys
         (row_id, user_id, endpoint, idempotency_key, request_hash, state, expires_at, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, 'started', ?, ?, ?)`,
      )
      .bind(
        crypto.randomUUID(),
        input.userId,
        input.endpoint,
        idempotencyKey,
        requestHash,
        now + 24 * 60 * 60 * 1000,
        now,
        now,
      )
      .run();
  } else if (existing.state === "failed") {
    await db
      .prepare(
        `UPDATE idempotency_keys SET state = 'started', updated_at = ?
         WHERE user_id = ? AND endpoint = ? AND idempotency_key = ?`,
      )
      .bind(now, input.userId, input.endpoint, idempotencyKey)
      .run();
  }

  const updateState = async (state: "completed" | "failed") => {
    await db
      .prepare(
        `UPDATE idempotency_keys
         SET state = ?, response_code = ?, response_digest = ?, updated_at = ?
         WHERE user_id = ? AND endpoint = ? AND idempotency_key = ?`,
      )
      .bind(
        state,
        state === "completed" ? 200 : 500,
        await sha256(`${state}:${input.userId}:${input.endpoint}:${idempotencyKey}`),
        Date.now(),
        input.userId,
        input.endpoint,
        idempotencyKey,
      )
      .run();
  };

  return {
    replayed: existing?.state === "completed",
    complete: () => updateState("completed"),
    fail: () => updateState("failed"),
  };
}

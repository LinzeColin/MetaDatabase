export const OUTBOX_STORAGE_KEY = "mydairy.outbox.v1";
export const LEGACY_OUTBOX_STORAGE_KEYS = ["huchuliang.workbench.outbox.v1"] as const;

export type OutboxMethod = "POST";

export type OutboxAction = {
  endpoint: string;
  method: OutboxMethod;
  payload: Record<string, unknown>;
  idempotencyKey: string;
  createdAt: number;
  queuedAt: number;
};

export type OutboxMutationResult = {
  type: "ok" | "conflict" | "error" | "unavailable";
  message?: string;
};

export type OutboxReplayResult = {
  remaining: OutboxAction[];
  replayedAny: boolean;
  stopType?: OutboxMutationResult["type"] | "network";
  stopMessage?: string;
};

export type OutboxStorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem?: (key: string) => void;
};

type UnknownObject = Record<string, unknown>;

function isObject(value: unknown): value is UnknownObject {
  return typeof value === "object" && value !== null;
}

function isOutboxAction(value: unknown): value is OutboxAction {
  if (!isObject(value)) return false;
  return (
    typeof value.endpoint === "string" &&
    typeof value.method === "string" &&
    value.method === "POST" &&
    isObject(value.payload) &&
    typeof value.idempotencyKey === "string" &&
    Number.isFinite(value.createdAt) &&
    Number.isFinite(value.queuedAt)
  );
}

export function parseOutbox(raw: string | null): OutboxAction[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isOutboxAction);
  } catch {
    return [];
  }
}

export function readOutbox(storage: OutboxStorageLike | null): OutboxAction[] {
  if (!storage) return [];
  const seen = new Set<string>();
  const result: OutboxAction[] = [];
  const keys = [OUTBOX_STORAGE_KEY, ...LEGACY_OUTBOX_STORAGE_KEYS];

  for (const key of keys) {
    for (const action of parseOutbox(storage.getItem(key))) {
      if (seen.has(action.idempotencyKey)) continue;
      seen.add(action.idempotencyKey);
      result.push(action);
    }
  }

  return result;
}

export function writeOutbox(storage: OutboxStorageLike | null, items: OutboxAction[]): void {
  if (!storage) return;
  try {
    storage.setItem(OUTBOX_STORAGE_KEY, JSON.stringify(items));
    for (const key of LEGACY_OUTBOX_STORAGE_KEYS) storage.removeItem?.(key);
  } catch {
    // Ignore storage failures; queue state is best-effort persisted.
  }
}

export function appendOutbox(storage: OutboxStorageLike | null, action: OutboxAction): OutboxAction[] {
  const queue = readOutbox(storage);
  queue.push(action);
  writeOutbox(storage, queue);
  return queue;
}

export function getBrowserOutboxStorage(): OutboxStorageLike | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

export async function replayOutboxQueue(
  queue: OutboxAction[],
  sendMutation: (action: OutboxAction) => Promise<OutboxMutationResult>,
): Promise<OutboxReplayResult> {
  const remaining = [...queue];
  let replayedAny = false;

  for (const action of queue) {
    try {
      const result = await sendMutation(action);

      if (result.type === "ok") {
        remaining.shift();
        replayedAny = true;
        continue;
      }

      if (result.type === "conflict" || result.type === "error" || result.type === "unavailable") {
        return {
          remaining,
          replayedAny,
          stopType: result.type,
          stopMessage: result.message,
        };
      }
    } catch (error) {
      return {
        remaining,
        replayedAny,
        stopType: "network",
        stopMessage: error instanceof Error ? error.message : "Network error",
      };
    }
  }

  return { remaining: [], replayedAny };
}

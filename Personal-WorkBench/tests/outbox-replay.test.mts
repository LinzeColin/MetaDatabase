import assert from "node:assert/strict";
import test from "node:test";

import {
  appendOutbox,
  parseOutbox,
  replayOutboxQueue,
  readOutbox,
  writeOutbox,
} from "../app/_components/workbench/outbox-queue.ts";
import type { OutboxAction } from "../app/_components/workbench/outbox-queue.ts";

type MemoryStorage = {
  set: Map<string, string>;
};

function createMemoryStorage(): MemoryStorage & {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
} {
  const set = new Map<string, string>();
  return {
    set,
    getItem(key: string) {
      return set.has(key) ? set.get(key) ?? null : null;
    },
    setItem(key: string, value: string) {
      set.set(key, value);
    },
  };
}

const actionA: OutboxAction = {
  endpoint: "/api/workbench/todos",
  method: "POST",
  idempotencyKey: "a",
  createdAt: 1,
  queuedAt: 1,
  payload: { title: "a" },
};

const actionB: OutboxAction = {
  endpoint: "/api/workbench/todos",
  method: "POST",
  idempotencyKey: "b",
  createdAt: 2,
  queuedAt: 2,
  payload: { title: "b" },
};

const actionC: OutboxAction = {
  endpoint: "/api/workbench/todos",
  method: "POST",
  idempotencyKey: "c",
  createdAt: 3,
  queuedAt: 3,
  payload: { title: "c" },
};

test("parseOutbox filters invalid entries and keeps partial queue", () => {
  assert.deepEqual(parseOutbox(null), []);
  assert.deepEqual(parseOutbox("[]"), []);
  assert.deepEqual(parseOutbox("{"), []);
  const raw = JSON.stringify([actionA, { invalid: true }, actionB]);
  const parsed = parseOutbox(raw);
  assert.equal(parsed.length, 2);
  assert.equal(parsed[0].idempotencyKey, "a");
  assert.equal(parsed[1].idempotencyKey, "b");
});

test("read/write/append outbox operations are stable with local storage", () => {
  const storage = createMemoryStorage();
  writeOutbox(storage, [actionA, actionC]);
  assert.equal(readOutbox(storage).length, 2);
  appendOutbox(storage, actionB);
  assert.equal(readOutbox(storage).length, 3);
  assert.equal(readOutbox(storage).at(-1)?.idempotencyKey, "b");
});

test("replayOutboxQueue replays all queue when all operations succeed", async () => {
  const queue = [actionA, actionB];
  const calls: string[] = [];
  const result = await replayOutboxQueue(queue, async (action) => {
    calls.push(action.idempotencyKey);
    return { type: "ok" };
  });

  assert.deepEqual(result.remaining, []);
  assert.equal(result.replayedAny, true);
  assert.equal(calls.length, 2);
  assert.equal(calls[0], "a");
  assert.equal(calls[1], "b");
});

test("replayOutboxQueue stops on conflict and keeps remaining actions", async () => {
  const queue = [actionA, actionB, actionC];
  const calls: string[] = [];
  const result = await replayOutboxQueue(queue, async (action) => {
    calls.push(action.idempotencyKey);
    if (action.idempotencyKey === "b") {
      return { type: "conflict", message: "conflict" };
    }
    return { type: "ok" };
  });

  assert.equal(calls.length, 2);
  assert.equal(result.stopType, "conflict");
  assert.equal(result.stopMessage, "conflict");
  assert.equal(result.replayedAny, true);
  assert.deepEqual(result.remaining.map((item) => item.idempotencyKey), ["b", "c"]);
});

test("replayOutboxQueue stops on 503 unavailable and preserves queue order", async () => {
  const queue = [actionA, actionB, actionC];
  const calls: string[] = [];
  const result = await replayOutboxQueue(queue, async (action) => {
    calls.push(action.idempotencyKey);
    return { type: action.idempotencyKey === "b" ? "unavailable" : "ok", message: "unavailable" };
  });

  assert.equal(calls.length, 2);
  assert.equal(result.stopType, "unavailable");
  assert.equal(result.stopMessage, "unavailable");
  assert.equal(result.replayedAny, true);
  assert.deepEqual(result.remaining.map((item) => item.idempotencyKey), ["b", "c"]);
});

test("replayOutboxQueue preserves remaining actions on transport exception", async () => {
  const queue = [actionA, actionB];
  const calls: string[] = [];
  const result = await replayOutboxQueue(queue, async (action) => {
    calls.push(action.idempotencyKey);
    throw new Error("network");
  });

  assert.equal(calls.length, 1);
  assert.equal(result.stopType, "network");
  assert.equal(result.replayedAny, false);
  assert.deepEqual(result.remaining.map((item) => item.idempotencyKey), ["a", "b"]);
});

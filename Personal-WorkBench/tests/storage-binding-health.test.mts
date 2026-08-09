import assert from "node:assert/strict";
import test from "node:test";
import { probeStorageBindings } from "../server/storage/binding-health.ts";

test("storage binding probe uses only a constant D1 query and an R2 head", async () => {
  const operations: string[] = [];
  const env = {
    DB: {
      prepare(sql: string) {
        operations.push(`d1:${sql}`);
        return { first: async () => null };
      },
    },
    FILES: {
      head: async (key: string) => {
        operations.push(`r2_head:${key}`);
        return null;
      },
    },
  } as unknown as { DB: D1Database; FILES: R2Bucket };

  const result = await probeStorageBindings(env);

  assert.deepEqual(result, { d1: "available", r2: "available" });
  assert.deepEqual(operations.slice(0, 1), ["d1:SELECT 1 AS storage_binding_probe"]);
  assert.match(operations[1], /^r2_head:__mydairy_binding_probe__\/[A-Za-z0-9-]+$/);
  assert.equal(operations.some((entry) => /get|list|put|delete/i.test(entry)), false);
});

test("storage binding probe surfaces an unavailable binding without fallback", async () => {
  const env = {
    DB: {
      prepare() {
        return { first: async () => { throw new Error("binding unavailable"); } };
      },
    },
    FILES: {
      head: async () => null,
    },
  } as unknown as { DB: D1Database; FILES: R2Bucket };

  await assert.rejects(() => probeStorageBindings(env), /binding unavailable/);
});

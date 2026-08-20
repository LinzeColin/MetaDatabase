import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { LocalObjectBucket } from "../../server/runtime/vps3/local-object-store.ts";

test("VPS3 filesystem object store writes, reads, heads and deletes an object", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pwb-objects-"));
  try {
    const bucket = new LocalObjectBucket(root);
    const stored = await bucket.put("users/u1/diary/a.txt", "hello", {
      httpMetadata: { contentType: "text/plain" },
      customMetadata: { owner: "u1" },
    });
    assert.equal(stored.size, 5);
    const head = await bucket.head("users/u1/diary/a.txt");
    assert.equal(head?.httpMetadata?.contentType, "text/plain");
    assert.deepEqual(head?.customMetadata, { owner: "u1" });
    const body = await bucket.get("users/u1/diary/a.txt");
    assert.ok(body);
    const reader = body.body.getReader();
    const chunks: Uint8Array[] = [];
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      chunks.push(next.value);
    }
    assert.equal(Buffer.concat(chunks).toString("utf8"), "hello");
    await bucket.delete("users/u1/diary/a.txt");
    assert.equal(await bucket.head("users/u1/diary/a.txt"), null);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("VPS3 filesystem object store rejects path traversal", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pwb-objects-"));
  try {
    const bucket = new LocalObjectBucket(root);
    await assert.rejects(() => bucket.put("../escape.txt", "no"), /Invalid object key/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

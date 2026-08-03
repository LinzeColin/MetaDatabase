import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPrivateObjectKey,
  createPrivateFile,
  detectImageMime,
  PrivateFileInputError,
  validatePrivateImageUpload,
} from "../server/files/private-files.ts";

const png = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
]).buffer;

test("private object keys use a user-owned, non-public prefix", () => {
  assert.equal(buildPrivateObjectKey("user_a", "food", "rec_a"), "users/user_a/food/rec_a");
  assert.throws(() => buildPrivateObjectKey("user/a", "food", "rec_a"), PrivateFileInputError);
});

test("upload validation requires matching magic bytes, MIME type, and size", async () => {
  assert.equal(detectImageMime(new Uint8Array(png)), "image/png");
  const verified = await validatePrivateImageUpload("image/png", png);
  assert.equal(verified.byteSize, 24);
  assert.deepEqual({ width: verified.width, height: verified.height }, { width: 1, height: 1 });
  assert.equal(verified.sha256.length, 64);
  await assert.rejects(validatePrivateImageUpload("image/jpeg", png), PrivateFileInputError);
});

test("file creation records owner metadata before writing the private object", async () => {
  const operations: string[] = [];
  const env = {
    DB: {
      prepare(sql: string) {
        operations.push(sql);
        return {
          bind() {
            return { run: async () => ({ meta: { changes: 1 } }) };
          },
        };
      },
    },
    FILES: {
      put: async (key: string) => { operations.push(`put:${key}`); },
    },
  } as unknown as { DB: D1Database; FILES: R2Bucket };
  const validated = await validatePrivateImageUpload("image/png", png);
  await createPrivateFile(env, { userId: "user_a", id: "rec_a", module: "food", buffer: png, validated });
  assert.match(operations[0], /INSERT INTO file_objects/);
  assert.equal(operations[1], "put:users/user_a/food/rec_a");
});

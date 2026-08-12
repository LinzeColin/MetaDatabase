import assert from "node:assert/strict";
import test from "node:test";

import {
  AUTH_RETURN_RECOVERY_DELAYS_MS,
  AUTH_RETURN_RECOVERY_EVENT,
  AUTH_RETURN_RECOVERY_KEY,
  consumeAuthReturnRecovery,
  markAuthReturnRecovery,
} from "../app/auth/_components/auth-return-recovery.ts";

function storage() {
  const values = new Map<string, string>();
  return {
    getItem(key: string) { return values.get(key) ?? null; },
    removeItem(key: string) { values.delete(key); },
    setItem(key: string, value: string) { values.set(key, value); },
  };
}

test("a successful auth return leaves one value-free recovery marker", () => {
  const port = storage();
  markAuthReturnRecovery(port);
  assert.equal(port.getItem(AUTH_RETURN_RECOVERY_KEY), "1");
  assert.equal(consumeAuthReturnRecovery(port), true);
  assert.equal(consumeAuthReturnRecovery(port), false);
});

test("auth return recovery uses a bounded client-only retry contract", () => {
  assert.deepEqual(AUTH_RETURN_RECOVERY_DELAYS_MS, [300, 1_100]);
  assert.equal(AUTH_RETURN_RECOVERY_EVENT, "mydairy:auth-return-recovered");
  assert.equal(AUTH_RETURN_RECOVERY_KEY.includes("token"), false);
  assert.equal(AUTH_RETURN_RECOVERY_KEY.includes("user"), false);
});

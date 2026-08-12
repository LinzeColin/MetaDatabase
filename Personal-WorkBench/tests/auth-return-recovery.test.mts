import assert from "node:assert/strict";
import test from "node:test";

import {
  AUTH_RETURN_RECOVERY_DELAYS_MS,
  AUTH_RETURN_RECOVERY_EVENT,
  AUTH_RETURN_RECOVERY_KEY,
  AUTH_RETURN_RECOVERY_QUERY_KEY,
  consumeAuthReturnRecovery,
  consumeAuthReturnRecoveryFromLocation,
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
  assert.deepEqual(AUTH_RETURN_RECOVERY_DELAYS_MS, [300, 1_100, 3_000, 6_000, 12_000, 20_000]);
  assert.equal(Math.max(...AUTH_RETURN_RECOVERY_DELAYS_MS) <= 20_000, true);
  assert.equal(AUTH_RETURN_RECOVERY_EVENT, "mydairy:auth-return-recovered");
  assert.equal(AUTH_RETURN_RECOVERY_KEY.includes("token"), false);
  assert.equal(AUTH_RETURN_RECOVERY_KEY.includes("user"), false);
  assert.equal(AUTH_RETURN_RECOVERY_QUERY_KEY.includes("token"), false);
  assert.equal(AUTH_RETURN_RECOVERY_QUERY_KEY.includes("user"), false);
});

test("a value-free callback marker restores recovery after an embedded tab is recreated", () => {
  const replacements: Array<{ data: unknown; title: string; url: string | URL | null | undefined }> = [];
  const location = { hash: "#today", pathname: "/", search: "?view=home&auth_return=1" };
  const history = {
    state: null,
    replaceState(data: unknown, title: string, url?: string | URL | null) {
      replacements.push({ data, title, url });
    },
  };

  assert.equal(consumeAuthReturnRecoveryFromLocation(location, history), true);
  assert.deepEqual(replacements, [{ data: null, title: "", url: "/?view=home#today" }]);
  assert.equal(consumeAuthReturnRecoveryFromLocation({ hash: "", pathname: "/", search: "?view=home" }, history), false);
});

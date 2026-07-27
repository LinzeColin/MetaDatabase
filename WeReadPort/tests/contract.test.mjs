import test from "node:test";
import assert from "node:assert/strict";
import { buildGatewayBody, parseProxyBody, validateUserKey } from "../src/core/contract.js";
import { SOURCE_SKILL_VERSION } from "../src/core/constants.js";
import { userKey } from "./helpers.mjs";

test("validates user-bound key shape without storing it", () => {
  assert.equal(validateUserKey(`  ${userKey()}  `), userKey());
  assert.throws(() => validateUserKey("shared-secret"), error => error.code === "AUTH");
  assert.throws(() => validateUserKey(`${userKey()}\nembedded`), error => error.code === "AUTH");
});

test("builds flat reviewed requests with pinned source version", () => {
  assert.deepEqual(buildGatewayBody("/user/notebooks", { count: 100, lastSort: 3 }), {
    api_name: "/user/notebooks",
    skill_version: SOURCE_SKILL_VERSION,
    count: 100,
    lastSort: 3,
  });
  assert.throws(() => buildGatewayBody("/user/notebooks", { params: { count: 1 } }), error => error.code === "INVALID_REQUEST");
  assert.throws(() => buildGatewayBody("/user/notebooks", { count: 101 }), error => error.code === "INVALID_REQUEST");
  assert.throws(() => buildGatewayBody("https://attacker.invalid", {}), error => error.code === "INVALID_REQUEST");
});

test("untrusted proxy body cannot override version or add parameters", () => {
  assert.deepEqual(parseProxyBody({ api_name: "/book/info", bookId: "book-1", skill_version: "0.0.0" }), {
    api_name: "/book/info",
    skill_version: SOURCE_SKILL_VERSION,
    bookId: "book-1",
  });
  assert.throws(() => parseProxyBody({ api_name: "/book/info", bookId: "book-1", endpoint: "https://attacker.invalid" }), error => error.code === "INVALID_REQUEST");
});

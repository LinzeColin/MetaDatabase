"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  JOB_STATUSES,
  JOB_TRANSITIONS,
  IllegalJobTransitionError,
  assertTransition,
  canTransition,
  transitionPairs,
} = require("../src/services/jobs/job-state-machine");

const EXPECTED_TRANSITIONS = Object.freeze([
  ["received", "queued"],
  ["received", "rejected"],
  ["queued", "running"],
  ["queued", "expired"],
  ["running", "waiting_approval"],
  ["running", "succeeded"],
  ["running", "failed_retryable"],
  ["running", "cancelled"],
  ["running", "failed_terminal"],
  ["waiting_approval", "running"],
  ["waiting_approval", "cancelled"],
  ["failed_retryable", "queued"],
  ["failed_retryable", "failed_terminal"],
  ["succeeded", "reply_pending"],
  ["failed_terminal", "reply_pending"],
  ["cancelled", "reply_pending"],
  ["reply_pending", "replied"],
  ["reply_pending", "reply_failed"],
  ["replied", "canonical_pending"],
  ["reply_failed", "canonical_pending"],
  ["canonical_pending", "canonical_synced"],
]);

test("state machine exactly matches the frozen PRD transition relation", () => {
  assert.deepEqual(transitionPairs(), EXPECTED_TRANSITIONS);
  assert.equal(JOB_STATUSES.length, 15);
  assert.deepEqual(JOB_TRANSITIONS.expired, []);
  assert.deepEqual(JOB_TRANSITIONS.rejected, []);
  assert.deepEqual(JOB_TRANSITIONS.canonical_synced, []);
});

test("the complete legal and illegal status matrix is fail closed", () => {
  const expected = new Set(
    EXPECTED_TRANSITIONS.map(([from, to]) => `${from}->${to}`),
  );
  let legalAttempts = 0;
  let illegalAttempts = 0;
  for (const fromStatus of JOB_STATUSES) {
    for (const toStatus of JOB_STATUSES) {
      const pair = `${fromStatus}->${toStatus}`;
      if (expected.has(pair)) {
        assert.equal(canTransition(fromStatus, toStatus), true, pair);
        assert.equal(assertTransition(fromStatus, toStatus), true, pair);
        legalAttempts += 1;
      } else {
        assert.equal(canTransition(fromStatus, toStatus), false, pair);
        assert.throws(
          () => assertTransition(fromStatus, toStatus),
          (error) =>
            error instanceof IllegalJobTransitionError &&
            error.code === "ILLEGAL_JOB_TRANSITION",
          pair,
        );
        illegalAttempts += 1;
      }
    }
  }
  assert.equal(legalAttempts, 21);
  assert.equal(illegalAttempts, 204);
});

test("10,000 deterministic property attempts never admit an illegal edge", () => {
  let state = 0x6d2b79f5;
  const next = () => {
    state = (Math.imul(state ^ (state >>> 15), 1 | state) +
      Math.imul(state ^ (state >>> 7), 61 | state)) ^ state;
    return (state ^ (state >>> 14)) >>> 0;
  };
  const legal = new Set(
    EXPECTED_TRANSITIONS.map(([from, to]) => `${from}->${to}`),
  );
  let illegalSuccesses = 0;
  for (let attempt = 0; attempt < 10000; attempt += 1) {
    const from = JOB_STATUSES[next() % JOB_STATUSES.length];
    const to = JOB_STATUSES[next() % JOB_STATUSES.length];
    const expected = legal.has(`${from}->${to}`);
    if (canTransition(from, to) !== expected) {
      illegalSuccesses += 1;
    }
    if (expected) {
      assert.doesNotThrow(() => assertTransition(from, to));
    } else {
      assert.throws(() => assertTransition(from, to), {
        code: "ILLEGAL_JOB_TRANSITION",
      });
    }
  }
  assert.equal(illegalSuccesses, 0);
});

test("unknown and malformed statuses are rejected without coercion", () => {
  for (const value of [
    "",
    "RUNNING",
    "queued ",
    null,
    undefined,
    0,
    true,
    {},
  ]) {
    assert.equal(canTransition(value, "queued"), false);
    assert.equal(canTransition("received", value), false);
  }
});

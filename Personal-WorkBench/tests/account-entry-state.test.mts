import assert from "node:assert/strict";
import test from "node:test";
import {
  accountEntryInitialStateForSession,
  isConfirmedAccountEntryState,
} from "../app/_components/workbench/account-entry-state.ts";

test("server account-entry state contains no profile data and requires a real session identity", () => {
  assert.equal(accountEntryInitialStateForSession(null), "signed-out");
  assert.equal(accountEntryInitialStateForSession({ user: { emailVerified: true } }), "signed-out");
  assert.equal(accountEntryInitialStateForSession({ user: { id: "u1", emailVerified: false } }), "verification-required");
  assert.equal(accountEntryInitialStateForSession({ user: { id: "u1", emailVerified: true } }), "signed-in");
  assert.equal(isConfirmedAccountEntryState("signed-in"), true);
  assert.equal(isConfirmedAccountEntryState("verification-required"), true);
  assert.equal(isConfirmedAccountEntryState("session-unavailable"), false);
});

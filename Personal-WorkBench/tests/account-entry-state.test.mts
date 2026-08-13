import assert from "node:assert/strict";
import test from "node:test";
import {
  accountEntryStateForAuthReturn,
  accountEntryInitialStateForSession,
  isConfirmedAccountEntryState,
  shouldRefreshAccountEntryImmediately,
} from "../app/_components/workbench/account-entry-state.ts";

test("server account-entry state contains no profile data and requires a real session identity", () => {
  assert.equal(accountEntryInitialStateForSession(null), "signed-out");
  assert.equal(accountEntryInitialStateForSession({ user: { emailVerified: true } }), "signed-out");
  assert.equal(accountEntryInitialStateForSession({ user: { id: "u1", emailVerified: false } }), "verification-required");
  assert.equal(accountEntryInitialStateForSession({ user: { id: "u1", emailVerified: true } }), "signed-in");
  assert.equal(isConfirmedAccountEntryState("signed-in"), true);
  assert.equal(isConfirmedAccountEntryState("verification-required"), true);
  assert.equal(isConfirmedAccountEntryState("session-unavailable"), false);
  assert.equal(shouldRefreshAccountEntryImmediately("checking", false), true);
  assert.equal(shouldRefreshAccountEntryImmediately("signed-out", false), false);
  assert.equal(shouldRefreshAccountEntryImmediately("signed-in", false), false);
  assert.equal(shouldRefreshAccountEntryImmediately("signed-out", true), true);
  assert.equal(accountEntryStateForAuthReturn("signed-out", false), "signed-out");
  assert.equal(accountEntryStateForAuthReturn("signed-out", true), "checking");
  assert.equal(accountEntryStateForAuthReturn("signed-in", true), "signed-in");
  assert.equal(accountEntryStateForAuthReturn("verification-required", true), "verification-required");
});

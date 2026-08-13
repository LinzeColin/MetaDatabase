export type AccountEntryInitialState =
  | "checking"
  | "signed-in"
  | "signed-out"
  | "verification-required";

export type AccountEntryState =
  | AccountEntryInitialState
  | "session-unavailable"
  | "auth-return-failed";

type SessionLike = {
  user?: {
    emailVerified?: unknown;
    id?: unknown;
  };
};

/**
 * Maps the authoritative Better Auth response to the only account state that
 * may be rendered before client hydration. No account identifier or profile
 * value is ever passed to the browser by this helper.
 */
export function accountEntryInitialStateForSession(session: unknown): AccountEntryInitialState {
  const candidate = session as SessionLike | null;
  if (!candidate?.user || typeof candidate.user.id !== "string" || !candidate.user.id) return "signed-out";
  return candidate.user.emailVerified === true ? "signed-in" : "verification-required";
}

export function isConfirmedAccountEntryState(state: AccountEntryState): boolean {
  return state === "signed-in" || state === "verification-required";
}

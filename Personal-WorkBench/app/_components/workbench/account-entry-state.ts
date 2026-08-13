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

/**
 * A callback can reach the desktop before the session row is visible to the
 * first server render. Keep that short, bounded recovery window truthful: the
 * visitor has just completed a sign-in attempt, so do not paint the ordinary
 * signed-out affordance until the authoritative client reads settle.
 */
export function accountEntryStateForAuthReturn(
  initialState: AccountEntryInitialState,
  hasAuthReturnRecovery: boolean,
): AccountEntryState {
  if (hasAuthReturnRecovery && !isConfirmedAccountEntryState(initialState)) return "checking";
  return initialState;
}

/**
 * A current first-party server render already establishes the initial guest,
 * verified, or verification-required affordance. The browser only needs an
 * immediate follow-up request when that render could not establish anything,
 * or when an OAuth callback deliberately asks for bounded recovery retries.
 */
export function shouldRefreshAccountEntryImmediately(
  initialState: AccountEntryInitialState,
  hasAuthReturnRecovery: boolean,
): boolean {
  return initialState === "checking" || hasAuthReturnRecovery;
}

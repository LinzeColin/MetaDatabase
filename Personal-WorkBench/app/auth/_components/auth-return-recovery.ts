/**
 * OAuth and email sign-in both leave this same-origin tab briefly before the
 * authenticated desktop loads. Keep one value-free marker in sessionStorage
 * so the desktop can recheck a session that was still being committed during
 * its first render. It is consumed exactly once and never contains an account
 * identifier, callback URL, or credential.
 */
export const AUTH_RETURN_RECOVERY_EVENT = "mydairy:auth-return-recovered";
export const AUTH_RETURN_RECOVERY_KEY = "mydairy.auth-return-recovery.v1";
// Better Auth commits the session and user state independently.  Most OAuth
// returns settle within the first two reads, but keep two later bounded reads
// for a slow edge/database commit so the just-authenticated tab can recover
// without asking the visitor to refresh or sign in again.  This is never a
// general polling loop: it runs only after this tab deliberately starts auth.
export const AUTH_RETURN_RECOVERY_DELAYS_MS = [300, 1_100, 3_000, 6_000] as const;

type SessionStoragePort = Pick<Storage, "getItem" | "removeItem" | "setItem">;

function sessionStoragePort(): SessionStoragePort | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Mark a successful browser authentication handoff before navigation. */
export function markAuthReturnRecovery(storage = sessionStoragePort()): void {
  try {
    storage?.setItem(AUTH_RETURN_RECOVERY_KEY, "1");
  } catch {
    // The regular callback remains valid when an embedded browser disables
    // sessionStorage; this recovery aid must never make sign-in fail.
  }
}

/** Consume the one-shot marker so ordinary anonymous visits do not retry. */
export function consumeAuthReturnRecovery(storage = sessionStoragePort()): boolean {
  try {
    if (storage?.getItem(AUTH_RETURN_RECOVERY_KEY) !== "1") return false;
    storage.removeItem(AUTH_RETURN_RECOVERY_KEY);
    return true;
  } catch {
    return false;
  }
}

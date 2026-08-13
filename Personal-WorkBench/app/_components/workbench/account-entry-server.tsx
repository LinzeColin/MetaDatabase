import { env } from "cloudflare:workers";
import { headers } from "next/headers";
import { createAuth } from "@/server/auth";
import {
  AUTH_SESSION_COOKIE_NAME,
  SECURE_AUTH_SESSION_COOKIE_NAME,
} from "@/server/auth/cookie-names";
import { AccountEntry } from "./account-entry";
import { accountEntryInitialStateForSession, type AccountEntryInitialState } from "./account-entry-state";

type AccountEntryServerProps = {
  className: string;
  signedOutHref: string;
};

function hasSessionCookie(cookieHeader: string | null): boolean {
  if (!cookieHeader) return false;
  return cookieHeader.includes(`${AUTH_SESSION_COOKIE_NAME}=`)
    || cookieHeader.includes(`${SECURE_AUTH_SESSION_COOKIE_NAME}=`);
}

/**
 * Seed the visible account affordance from the same first-party request that
 * rendered the page. This avoids making a just-authenticated person wait on a
 * client fetch before seeing that their existing session is usable, while
 * anonymous page views keep the zero-read fast path.
 */
async function initialAccountEntryState(): Promise<AccountEntryInitialState> {
  const requestHeaders = new Headers(await headers());
  if (!hasSessionCookie(requestHeaders.get("cookie"))) return "signed-out";

  try {
    const session = await createAuth(env).api.getSession({
      headers: requestHeaders,
      query: { disableCookieCache: true },
    });
    return accountEntryInitialStateForSession(session);
  } catch {
    // The client retains its existing bounded, retryable authoritative check.
    // Do not infer either a guest or a signed-in state from a failed read.
    return "checking";
  }
}

export async function AccountEntryServer({ className, signedOutHref }: AccountEntryServerProps) {
  const initialState = await initialAccountEntryState();
  return <AccountEntry className={className} initialState={initialState} signedOutHref={signedOutHref} />;
}

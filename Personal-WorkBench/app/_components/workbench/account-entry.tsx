"use client";

import { useEffect, useState } from "react";
import {
  AUTH_RETURN_RECOVERY_DELAYS_MS,
  AUTH_RETURN_RECOVERY_EVENT,
  consumeAuthReturnRecovery,
} from "../../auth/_components/auth-return-recovery";

type AccountEntryState = "checking" | "signed-in" | "signed-out" | "verification-required";

type AccountEntryProps = {
  className: string;
  signedOutHref: string;
};

type BrowserSession = {
  user?: {
    emailVerified?: unknown;
    id?: unknown;
  };
};

/**
 * Keeps the persistent account entry truthful after an OAuth callback without
 * displaying an account identifier in the shared workbench chrome.
 */
export function AccountEntry({ className, signedOutHref }: AccountEntryProps) {
  const [state, setState] = useState<AccountEntryState>("checking");

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let requestGeneration = 0;
    let recoveryAnnounced = false;
    const shouldRecoverAuthReturn = consumeAuthReturnRecovery();

    const announceRecoveredSession = (nextState: AccountEntryState) => {
      if (!shouldRecoverAuthReturn || recoveryAnnounced || nextState === "signed-out" || nextState === "checking") return;
      recoveryAnnounced = true;
      window.dispatchEvent(new Event(AUTH_RETURN_RECOVERY_EVENT));
    };

    const refresh = () => {
      const generation = ++requestGeneration;
      controller?.abort();
      controller = new AbortController();
      void fetch("/api/auth/get-session?disableCookieCache=true", {
        credentials: "same-origin",
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) return "signed-out" as const;
          const session = (await response.json().catch(() => null)) as BrowserSession | null;
          if (!session?.user || typeof session.user.id !== "string" || !session.user.id) return "signed-out" as const;
          return session.user.emailVerified === false ? "verification-required" as const : "signed-in" as const;
        })
        .then((nextState) => {
          if (active && generation === requestGeneration) {
            setState(nextState);
            announceRecoveredSession(nextState);
          }
        })
        .catch(() => {
          // Do not turn a known session into a signed-out display because a
          // foreground refresh briefly lost network access.
        });
    };

    const refreshWhenDocumentVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };

    refresh();
    // Better Auth commits the browser session and the user row separately.
    // During an OAuth return, the first authoritative lookup can therefore be
    // a short-lived signed-out result even though the callback has succeeded.
    // Retry only for the one tab that deliberately began a successful sign-in.
    const recoveryTimers = shouldRecoverAuthReturn
      ? AUTH_RETURN_RECOVERY_DELAYS_MS.map((delay) => window.setTimeout(refresh, delay))
      : [];
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    document.addEventListener("visibilitychange", refreshWhenDocumentVisible);
    return () => {
      active = false;
      controller?.abort();
      recoveryTimers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      document.removeEventListener("visibilitychange", refreshWhenDocumentVisible);
    };
  }, []);

  const signedIn = state === "signed-in" || state === "verification-required";
  const awaitingVerification = state === "verification-required";
  const label = awaitingVerification ? "已登录 · 待验证" : signedIn ? "已登录 · 账户" : "登录 / 账户";
  const ariaLabel = awaitingVerification
    ? "已登录，当前账号待完成验证"
    : signedIn
      ? "已登录，管理账户与同步"
      : "登录或管理账户";

  return (
    <a
      aria-label={ariaLabel}
      className={className}
      data-account-state={state}
      href={signedIn ? "/account" : signedOutHref}
    >
      {label}
    </a>
  );
}

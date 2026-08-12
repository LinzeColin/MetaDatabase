"use client";

import { useEffect, useState } from "react";

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
    const controller = new AbortController();
    let active = true;
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
        if (active) setState(nextState);
      })
      .catch(() => {
        // Preserve the neutral entry when a transient session read is unavailable.
        if (active) setState("checking");
      });
    return () => {
      active = false;
      controller.abort();
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

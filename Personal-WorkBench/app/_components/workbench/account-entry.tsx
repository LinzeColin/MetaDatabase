"use client";

import { useEffect, useState } from "react";
import {
  AUTH_RETURN_RECOVERY_DELAYS_MS,
  AUTH_RETURN_RECOVERY_EVENT,
  consumeAuthReturnRecovery,
  consumeAuthReturnRecoveryFromLocation,
} from "../../auth/_components/auth-return-recovery";

type AccountEntryState =
  | "checking"
  | "signed-in"
  | "signed-out"
  | "verification-required"
  | "session-unavailable"
  | "auth-return-failed";

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

// A connection that never settles must not leave the shared account control
// saying "正在确认登录…" forever. The browser can still use the ordinary login
// link while a later focus/pageshow check retries the authoritative session.
const SESSION_LOOKUP_TIMEOUT_MS = 8_000;

/**
 * Keeps the persistent account entry truthful after an OAuth callback without
 * displaying an account identifier in the shared workbench chrome.
 */
export function AccountEntry({ className, signedOutHref }: AccountEntryProps) {
  const [state, setState] = useState<AccountEntryState>("checking");

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let recoveryFailureTimer: number | null = null;
    let requestGeneration = 0;
    let recoveryAnnounced = false;
    let recoveredAuthReturn = false;
    let initialSessionResolved = false;
    // Consume both independent one-shot signals. A normal same-tab callback
    // has both: sessionStorage makes the recovery resilient to a redirect,
    // while the location marker is needed if an embedded browser rebuilt the
    // tab. Short-circuiting would leave the harmless URL marker behind and
    // make a later reload repeat this bounded recovery path.
    const recoveryMarkedInStorage = consumeAuthReturnRecovery();
    const recoveryMarkedInLocation = consumeAuthReturnRecoveryFromLocation();
    const shouldRecoverAuthReturn = recoveryMarkedInStorage || recoveryMarkedInLocation;

    const announceRecoveredSession = (nextState: AccountEntryState) => {
      if (!shouldRecoverAuthReturn || recoveryAnnounced || (nextState !== "signed-in" && nextState !== "verification-required")) return;
      recoveryAnnounced = true;
      window.dispatchEvent(new Event(AUTH_RETURN_RECOVERY_EVENT));
    };

    const refresh = () => {
      const generation = ++requestGeneration;
      controller?.abort();
      const nextController = new AbortController();
      controller = nextController;
      const timeout = window.setTimeout(() => {
        if (controller === nextController) nextController.abort();
      }, SESSION_LOOKUP_TIMEOUT_MS);
      void fetch("/api/auth/get-session?disableCookieCache=true", {
        credentials: "same-origin",
        signal: nextController.signal,
      })
        .then(async (response) => {
          if (response.status === 401) return "signed-out" as const;
          if (!response.ok) return "session-unavailable" as const;
          const session = (await response.json().catch(() => null)) as BrowserSession | null;
          if (!session?.user || typeof session.user.id !== "string" || !session.user.id) return "signed-out" as const;
          // The data routes accept only a strict true claim. Treat an absent
          // or false claim as awaiting verification too, so the persistent
          // entry never promises cloud sync that the server will reject.
          return session.user.emailVerified === true ? "signed-in" as const : "verification-required" as const;
        })
        .then((nextState) => {
          if (active && generation === requestGeneration) {
            initialSessionResolved = true;
            if (nextState === "signed-in" || nextState === "verification-required") {
              recoveredAuthReturn = true;
              if (recoveryFailureTimer !== null) window.clearTimeout(recoveryFailureTimer);
            }
            // Do not make a just-returned OAuth visitor look like an ordinary
            // guest while Better Auth finishes its bounded session commit.
            // A clear retry state is shown only after the full recovery window.
            if (shouldRecoverAuthReturn && (nextState === "signed-out" || nextState === "session-unavailable") && !recoveredAuthReturn) return;
            setState(nextState);
            announceRecoveredSession(nextState);
          }
        })
        .catch(() => {
          // Do not turn a known session into a signed-out display because a
          // foreground refresh briefly lost network access. Before the first
          // result, however, render a truthful retryable state rather than an
          // indefinite checking label. An OAuth return keeps its bounded
          // recovery window and surfaces its dedicated retry state later.
          if (active && generation === requestGeneration && !initialSessionResolved && !shouldRecoverAuthReturn) {
            setState("session-unavailable");
          }
        })
        .finally(() => {
          window.clearTimeout(timeout);
        });
    };

    const refreshWhenDocumentVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };

    if (shouldRecoverAuthReturn) {
      const finalRetryDelay = AUTH_RETURN_RECOVERY_DELAYS_MS[AUTH_RETURN_RECOVERY_DELAYS_MS.length - 1];
      recoveryFailureTimer = window.setTimeout(() => {
        if (active && !recoveredAuthReturn) setState("auth-return-failed");
      }, finalRetryDelay + 2_000);
    }

    refresh();
    // A very fast OAuth callback can resolve before sibling resource clients
    // finish installing their recovery listener. Replay an already verified
    // result once after that initial mount window, so their first guest-scope
    // read cannot leave the just-signed-in person looking at empty history.
    // A still-pending callback keeps the normal retry path below instead.
    const postRecoveryReplayTimer = shouldRecoverAuthReturn
      ? window.setTimeout(() => {
        if (active && recoveredAuthReturn) {
          window.dispatchEvent(new Event(AUTH_RETURN_RECOVERY_EVENT));
        }
      }, AUTH_RETURN_RECOVERY_DELAYS_MS[1])
      : null;
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
      if (recoveryFailureTimer !== null) window.clearTimeout(recoveryFailureTimer);
      if (postRecoveryReplayTimer !== null) window.clearTimeout(postRecoveryReplayTimer);
      recoveryTimers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      document.removeEventListener("visibilitychange", refreshWhenDocumentVisible);
    };
  }, []);

  const signedIn = state === "signed-in" || state === "verification-required";
  const awaitingVerification = state === "verification-required";
  const label = state === "checking"
    ? "正在确认登录…"
    : state === "auth-return-failed"
      ? "登录未完成 · 重试"
    : state === "session-unavailable"
      ? "暂时无法确认登录"
    : awaitingVerification
      ? "已登录 · 待验证"
      : signedIn
        ? "已登录 · 账户"
        : "登录以同步";
  const ariaLabel = state === "checking"
    ? "正在确认登录状态"
    : state === "auth-return-failed"
      ? "登录没有完成，重新登录后再同步历史记录"
    : state === "session-unavailable"
      ? "暂时无法确认登录，请检查网络后重试"
    : awaitingVerification
      ? "已登录，当前账号待完成验证"
      : signedIn
        ? "已登录，管理账户与同步"
        : "登录后启用跨设备同步";
  const title = state === "checking"
    ? "正在确认当前登录状态"
    : state === "auth-return-failed"
      ? "登录没有完成，请重新登录后再同步历史记录。"
    : state === "session-unavailable"
      ? "暂时无法确认登录，请检查网络后重试。"
    : awaitingVerification
      ? "当前账号待完成验证，验证后才能同步历史记录。"
      : signedIn
        ? "当前账号已登录，可管理跨设备同步。"
        : "当前为本机模式；登录后可跨设备同步历史记录。";

  return (
    <a
      aria-label={ariaLabel}
      className={className}
      data-account-state={state}
      href={signedIn ? "/account" : signedOutHref}
      title={title}
    >
      {label}
    </a>
  );
}

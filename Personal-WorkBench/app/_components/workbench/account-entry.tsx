"use client";

import { useEffect, useState } from "react";
import {
  AUTH_RETURN_RECOVERY_DELAYS_MS,
  AUTH_RETURN_RECOVERY_EVENT,
  consumeAuthReturnRecovery,
  consumeAuthReturnRecoveryFromLocation,
} from "../../auth/_components/auth-return-recovery";
import {
  accountEntryStateForAuthReturn,
  accountEntryInitialStateForSession,
  isConfirmedAccountEntryState,
  shouldRefreshAccountEntryImmediately,
  type AccountEntryInitialState,
  type AccountEntryState,
} from "./account-entry-state";

type AccountEntryProps = {
  className: string;
  initialState?: AccountEntryInitialState;
  signedOutHref: string;
};

// A connection that never settles must not leave the shared account control
// saying "正在确认登录…" forever. The browser can still use the ordinary login
// link while a later focus/pageshow check retries the authoritative session.
const SESSION_LOOKUP_TIMEOUT_MS = 8_000;

/**
 * Keeps the persistent account entry truthful after an OAuth callback without
 * displaying an account identifier in the shared workbench chrome.
 */
export function AccountEntry({ className, initialState = "checking", signedOutHref }: AccountEntryProps) {
  const [initialServerState] = useState<AccountEntryInitialState>(() => initialState);
  const [state, setState] = useState<AccountEntryState>(() => initialState);

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let recoveryFailureTimer: number | null = null;
    let requestGeneration = 0;
    let recoveryAnnounced = false;
    const initialServerConfirmed = isConfirmedAccountEntryState(initialServerState);
    let recoveredAuthReturn = initialServerConfirmed;
    let initialSessionResolved = initialServerConfirmed;
    // Consume both independent one-shot signals. A normal same-tab callback
    // has both: sessionStorage makes the recovery resilient to a redirect,
    // while the location marker is needed if an embedded browser rebuilt the
    // tab. Short-circuiting would leave the harmless URL marker behind and
    // make a later reload repeat this bounded recovery path.
    const recoveryMarkedInStorage = consumeAuthReturnRecovery();
    const recoveryMarkedInLocation = consumeAuthReturnRecoveryFromLocation();
    const shouldRecoverAuthReturn = recoveryMarkedInStorage || recoveryMarkedInLocation;
    const shouldRefreshImmediately = shouldRefreshAccountEntryImmediately(initialServerState, shouldRecoverAuthReturn);
    // Schedule the transition after hydration rather than synchronously in
    // this effect. It must never overwrite a session that a very fast
    // authoritative read has already recovered.
    const recoveryPendingTimer = shouldRecoverAuthReturn && !initialServerConfirmed
      ? window.setTimeout(() => {
        if (active && !recoveredAuthReturn) {
          setState(accountEntryStateForAuthReturn(initialServerState, shouldRecoverAuthReturn));
        }
      }, 0)
      : null;

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
          return accountEntryInitialStateForSession(await response.json().catch(() => null));
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
            // A same-request server render already established the session.
            // Keep that truthful state during a transient browser-only fetch
            // failure; an explicit 401 still takes precedence and signs out.
            if (initialServerConfirmed && nextState === "session-unavailable") return;
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

    const refreshWhenPageShows = (event: PageTransitionEvent) => {
      // `pageshow` also fires on the initial navigation. Only a back/forward
      // cache restoration needs an additional authoritative session read.
      if (event.persisted) refresh();
    };

    if (shouldRecoverAuthReturn) {
      const finalRetryDelay = AUTH_RETURN_RECOVERY_DELAYS_MS[AUTH_RETURN_RECOVERY_DELAYS_MS.length - 1];
      recoveryFailureTimer = window.setTimeout(() => {
        if (active && !recoveredAuthReturn) setState("auth-return-failed");
      }, finalRetryDelay + 2_000);
    }

    // A server-confirmed session can be present before this client effect
    // mounts. Reuse the existing delayed broadcast so every mounted resource
    // panel sees the OAuth return without exposing an account identifier.
    if (shouldRecoverAuthReturn && initialServerConfirmed) {
      window.setTimeout(() => {
        if (active) announceRecoveredSession(initialServerState);
      }, 0);
    }

    if (shouldRefreshImmediately) refresh();
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
    window.addEventListener("pageshow", refreshWhenPageShows);
    document.addEventListener("visibilitychange", refreshWhenDocumentVisible);
    return () => {
      active = false;
      controller?.abort();
      if (recoveryPendingTimer !== null) window.clearTimeout(recoveryPendingTimer);
      if (recoveryFailureTimer !== null) window.clearTimeout(recoveryFailureTimer);
      if (postRecoveryReplayTimer !== null) window.clearTimeout(postRecoveryReplayTimer);
      recoveryTimers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refreshWhenPageShows);
      document.removeEventListener("visibilitychange", refreshWhenDocumentVisible);
    };
  }, [initialServerState]);

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

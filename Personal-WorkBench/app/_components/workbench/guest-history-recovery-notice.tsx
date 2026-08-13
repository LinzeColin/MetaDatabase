"use client";

import { useEffect, useState } from "react";
import {
  AUTH_RETURN_RECOVERY_DELAYS_MS,
  AUTH_RETURN_RECOVERY_EVENT,
  AUTH_RETURN_RECOVERY_QUERY_KEY,
  AUTH_RETURN_RECOVERY_QUERY_VALUE,
} from "../../auth/_components/auth-return-recovery";
import { accountReturnPathFromLocation } from "./account-return-path";
import { LEGACY_DEVICE_HISTORY_TRANSFER_EVENT } from "./legacy-device-history-payload";
import { countGuestDeviceHistoryRecords } from "./local-record-cache";

type BrowserSession = {
  user?: {
    emailVerified?: unknown;
    id?: unknown;
  };
};

/**
 * Signing in never silently promotes a device's anonymous data into an
 * account. Make that safe boundary visible on the normal workbench, so a
 * person returning from Google sign-in can find the existing preview-first
 * recovery flow instead of interpreting the isolated history as lost.
 */
export function GuestHistoryRecoveryNotice() {
  const [count, setCount] = useState(0);
  const [href, setHref] = useState("/account");
  // Capture the value-free marker during render, before AccountEntry's effect
  // can remove it from the URL. This keeps the recovery notice independent of
  // sibling effect ordering after an OAuth callback restores a page.
  const [authReturnRequested] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      return new URLSearchParams(window.location.search).get(AUTH_RETURN_RECOVERY_QUERY_KEY)
        === AUTH_RETURN_RECOVERY_QUERY_VALUE;
    } catch {
      // A malformed or inaccessible location simply leaves the optional
      // recovery hint in its ordinary one-shot inspection mode.
      return false;
    }
  });

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let requestGeneration = 0;

    const inspect = () => {
      const generation = ++requestGeneration;
      controller?.abort();
      const nextController = new AbortController();
      controller = nextController;
      void countGuestDeviceHistoryRecords()
        .then(async (guestRecordCount) => {
          // Do not spend a session lookup on an ordinary fresh device: the
          // import notice cannot render unless it first has local guest rows.
          if (guestRecordCount <= 0) return null;
          const response = await fetch("/api/auth/get-session?disableCookieCache=true", {
            credentials: "same-origin",
            signal: nextController.signal,
          });
          if (!response.ok) return null;
          const session = (await response.json().catch(() => null)) as BrowserSession | null;
          if (!session?.user || typeof session.user.id !== "string" || !session.user.id || session.user.emailVerified !== true) return null;
          return {
            count: guestRecordCount,
            href: `/account?return_to=${encodeURIComponent(accountReturnPathFromLocation(window.location))}`,
          };
        })
        .then((next) => {
          if (!active || generation !== requestGeneration) return;
          if (!next || next.count <= 0) {
            setCount(0);
            setHref("/account");
            return;
          }
          setHref(next.href);
          setCount(next.count);
        })
        .catch(() => {
          // This optional recovery hint must never turn a usable workbench
          // into an error state when browser storage or the session check is
          // absent. A newer foreground/session event can safely retry it.
        });
    };

    const inspectWhenDocumentVisible = () => {
      if (document.visibilityState === "visible") inspect();
    };

    const inspectWhenPageShows = (event: PageTransitionEvent) => {
      // Initial navigation has already run `inspect`; only a bfcache restore
      // needs to reconsider the browser's current signed-in account.
      if (event.persisted) inspect();
    };

    inspect();
    // AccountEntry emits this only after its authoritative, bounded OAuth
    // return recovery sees a verified session. Without this listener a first
    // session read that races the callback could hide the device-history
    // recovery entry until a manual reload.
    window.addEventListener(AUTH_RETURN_RECOVERY_EVENT, inspect);
    window.addEventListener(LEGACY_DEVICE_HISTORY_TRANSFER_EVENT, inspect);
    window.addEventListener("focus", inspect);
    window.addEventListener("pageshow", inspectWhenPageShows);
    document.addEventListener("visibilitychange", inspectWhenDocumentVisible);
    // AccountEntry normally broadcasts once it observes a verified session.
    // If this sibling mounted after that broadcast, retain the same bounded
    // auth-return retry window here instead of making the person reload or
    // sign in a second time. Ordinary anonymous visits never carry the marker.
    const recoveryTimers = authReturnRequested
      ? AUTH_RETURN_RECOVERY_DELAYS_MS.map((delay) => window.setTimeout(inspect, delay))
      : [];
    return () => {
      active = false;
      controller?.abort();
      recoveryTimers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener(AUTH_RETURN_RECOVERY_EVENT, inspect);
      window.removeEventListener(LEGACY_DEVICE_HISTORY_TRANSFER_EVENT, inspect);
      window.removeEventListener("focus", inspect);
      window.removeEventListener("pageshow", inspectWhenPageShows);
      document.removeEventListener("visibilitychange", inspectWhenDocumentVisible);
    };
  }, [authReturnRequested]);

  if (!count) return null;

  return (
    <aside className="guest-history-recovery-notice" role="status">
      <strong>登录前记录还在这台设备</strong>
      <p>发现 {count} 条本机记录。为保护多账号数据，它们不会自动合并到当前账号。</p>
      <a className="data-link" href={href}>预览并导入到当前账号</a>
    </aside>
  );
}

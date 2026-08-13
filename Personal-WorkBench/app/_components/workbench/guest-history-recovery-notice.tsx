"use client";

import { useEffect, useState } from "react";
import { AUTH_RETURN_RECOVERY_EVENT } from "../../auth/_components/auth-return-recovery";
import { accountReturnPathFromLocation } from "./account-return-path";
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

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let requestGeneration = 0;

    const inspect = () => {
      const generation = ++requestGeneration;
      controller?.abort();
      controller = new AbortController();
      void fetch("/api/auth/get-session?disableCookieCache=true", {
        credentials: "same-origin",
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) return null;
          const session = (await response.json().catch(() => null)) as BrowserSession | null;
          if (!session?.user || typeof session.user.id !== "string" || !session.user.id || session.user.emailVerified !== true) return null;

          const nextCount = await countGuestDeviceHistoryRecords();
          return {
            count: nextCount,
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

    inspect();
    // AccountEntry emits this only after its authoritative, bounded OAuth
    // return recovery sees a verified session. Without this listener a first
    // session read that races the callback could hide the device-history
    // recovery entry until a manual reload.
    window.addEventListener(AUTH_RETURN_RECOVERY_EVENT, inspect);
    window.addEventListener("focus", inspect);
    window.addEventListener("pageshow", inspect);
    document.addEventListener("visibilitychange", inspectWhenDocumentVisible);
    return () => {
      active = false;
      controller?.abort();
      window.removeEventListener(AUTH_RETURN_RECOVERY_EVENT, inspect);
      window.removeEventListener("focus", inspect);
      window.removeEventListener("pageshow", inspect);
      document.removeEventListener("visibilitychange", inspectWhenDocumentVisible);
    };
  }, []);

  if (!count) return null;

  return (
    <aside className="guest-history-recovery-notice" role="status">
      <strong>登录前记录还在这台设备</strong>
      <p>发现 {count} 条本机记录。为保护多账号数据，它们不会自动合并到当前账号。</p>
      <a className="data-link" href={href}>预览并导入到当前账号</a>
    </aside>
  );
}

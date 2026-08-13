"use client";

import { useEffect, useState } from "react";
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

    const inspect = async () => {
      try {
        const response = await fetch("/api/auth/get-session?disableCookieCache=true", { credentials: "same-origin" });
        if (!response.ok) return;
        const session = (await response.json().catch(() => null)) as BrowserSession | null;
        if (!session?.user || typeof session.user.id !== "string" || !session.user.id || session.user.emailVerified !== true) return;

        const nextCount = await countGuestDeviceHistoryRecords();
        if (!active || nextCount <= 0) return;
        const returnTo = accountReturnPathFromLocation(window.location);
        setHref(`/account?return_to=${encodeURIComponent(returnTo)}`);
        setCount(nextCount);
      } catch {
        // This optional recovery hint must never turn a usable workbench into
        // an error state when browser storage or the session check is absent.
      }
    };

    void inspect();
    return () => {
      active = false;
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

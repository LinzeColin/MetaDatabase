"use client";

import { useEffect } from "react";
import {
  LEGACY_DEVICE_HISTORY_SESSION_KEY,
  LEGACY_DEVICE_HISTORY_TRANSFER_EVENT,
} from "./legacy-device-history-payload";
import { restoreLegacyGuestDeviceHistory } from "./local-record-cache";

function browserSessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Completes the top-level old-domain handoff after the browser has reached
 * the canonical origin. The value is transient session storage, then becomes
 * only this browser's anonymous guest cache so the existing preview-and-
 * confirm account import flow remains authoritative.
 */
export function LegacyDomainHistoryRecovery() {
  useEffect(() => {
    let active = true;
    const storage = browserSessionStorage();
    const payload = storage?.getItem(LEGACY_DEVICE_HISTORY_SESSION_KEY) ?? null;
    if (!payload) return;

    void restoreLegacyGuestDeviceHistory(payload)
      .then((result) => {
        if (!active) return;
        if (!result.accepted) {
          storage?.removeItem(LEGACY_DEVICE_HISTORY_SESSION_KEY);
          return;
        }
        storage?.removeItem(LEGACY_DEVICE_HISTORY_SESSION_KEY);
        window.setTimeout(() => {
          window.dispatchEvent(new Event(LEGACY_DEVICE_HISTORY_TRANSFER_EVENT));
        }, 0);
      })
      .catch(() => {
        // Keep the transient payload for a later same-tab retry. The old
        // hostname's original device records were never changed.
      });

    return () => {
      active = false;
    };
  }, []);

  return null;
}

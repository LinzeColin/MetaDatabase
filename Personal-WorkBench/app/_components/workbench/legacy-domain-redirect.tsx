"use client";

import { useEffect } from "react";
import { CANONICAL_MYDAIRY_ORIGIN, canonicalRetiredUrl } from "./canonical-domain";
import { buildGuestDeviceHistoryEnvelope } from "./local-record-cache";
import { serializeLegacyDeviceHistoryPayload } from "./legacy-device-history-payload";
import { LEGACY_DOMAIN_HANDOFF_COMPLETE_URL, parseLegacyHandoffId } from "./legacy-domain-handoff";

type HandoffResponse = { handoff?: unknown };

function handoffIdFromResponse(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return parseLegacyHandoffId((value as HandoffResponse).handoff);
}

function appendHiddenValue(form: HTMLFormElement, name: string, value: string): void {
  const input = document.createElement("input");
  input.name = name;
  input.type = "hidden";
  input.value = value;
  form.appendChild(input);
}

function submitHandoff(handoff: string | null, history: string | null, next: string): void {
  const form = document.createElement("form");
  form.action = LEGACY_DOMAIN_HANDOFF_COMPLETE_URL;
  form.method = "POST";
  form.style.display = "none";
  if (handoff) appendHiddenValue(form, "handoff", handoff);
  if (history) appendHiddenValue(form, "history", history);
  appendHiddenValue(form, "next", next);
  document.body.appendChild(form);
  form.submit();
}

async function legacyDeviceHistoryPayload(): Promise<string | null> {
  let timer: number | null = null;
  try {
    return await Promise.race([
      buildGuestDeviceHistoryEnvelope().then((envelope) => {
        const hasRecords = Object.values(envelope.modules).some((rows) => Array.isArray(rows) && rows.length > 0);
        return hasRecords ? serializeLegacyDeviceHistoryPayload(envelope) : null;
      }),
      new Promise<null>((resolve) => {
        timer = window.setTimeout(() => resolve(null), 2_500);
      }),
    ]);
  } finally {
    if (timer !== null) window.clearTimeout(timer);
  }
}

type LegacyDomainRedirectProps = {
  /**
   * Set from the request host so the retired domain never paints actionable
   * workbench controls before its client-side session/history handoff starts.
   */
  initiallyRetiredHost?: boolean;
};

export function LegacyDomainRedirect({ initiallyRetiredHost = false }: LegacyDomainRedirectProps) {
  useEffect(() => {
    const destination = canonicalRetiredUrl(window.location.href);
    if (!destination || destination === window.location.href) return;
    let cancelled = false;

    const redirect = () => {
      if (!cancelled) window.location.replace(destination);
    };

    const preserveExistingSession = async () => {
      try {
        const next = window.location.pathname + window.location.search + window.location.hash;
        const [history, response] = await Promise.all([
          legacyDeviceHistoryPayload().catch(() => null),
          fetch("/api/auth/legacy-domain-handoff", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ next }),
          }).catch(() => null),
        ]);
        if (cancelled) return;
        if (!response) {
          if (history) {
            submitHandoff(null, history, next);
            return;
          }
          redirect();
          return;
        }
        const payload = await response.json().catch(() => null) as HandoffResponse | null;
        const handoff = response.ok ? handoffIdFromResponse(payload) : null;
        if (!handoff && !history) {
          redirect();
          return;
        }
        // The form keeps the opaque session id and the browser-only history
        // payload out of the URL. The canonical completion page sets its
        // first-party cookie and places the anonymous payload in canonical
        // sessionStorage; no history is written to D1/R2 by this handoff.
        submitHandoff(handoff, history, next);
      } catch {
        redirect();
      }
    };

    void preserveExistingSession();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!initiallyRetiredHost) return null;

  return (
    <div aria-busy="true" aria-live="polite" className="legacy-domain-transfer" role="status">
      <div className="legacy-domain-transfer-card">
        <h1>正在打开个人日程</h1>
        <p>正在安全迁移到新的地址，随后即可继续登录和查看历史记录。</p>
        <a href={CANONICAL_MYDAIRY_ORIGIN}>如果没有自动打开，请进入个人日程</a>
      </div>
    </div>
  );
}

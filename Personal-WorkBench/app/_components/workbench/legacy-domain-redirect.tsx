"use client";

import { useEffect } from "react";
import { canonicalRetiredUrl } from "./canonical-domain";
import { LEGACY_DOMAIN_HANDOFF_COMPLETE_URL, parseLegacyHandoffId } from "./legacy-domain-handoff";

type HandoffResponse = { handoff?: unknown };

function handoffIdFromResponse(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return parseLegacyHandoffId((value as HandoffResponse).handoff);
}

function submitHandoff(handoff: string): void {
  const form = document.createElement("form");
  form.action = LEGACY_DOMAIN_HANDOFF_COMPLETE_URL;
  form.method = "POST";
  form.style.display = "none";
  const input = document.createElement("input");
  input.name = "handoff";
  input.type = "hidden";
  input.value = handoff;
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
}

export function LegacyDomainRedirect() {
  useEffect(() => {
    const destination = canonicalRetiredUrl(window.location.href);
    if (!destination || destination === window.location.href) return;
    let cancelled = false;

    const redirect = () => {
      if (!cancelled) window.location.replace(destination);
    };

    const preserveExistingSession = async () => {
      try {
        const response = await fetch("/api/auth/legacy-domain-handoff", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            next: `${window.location.pathname}${window.location.search}${window.location.hash}`,
          }),
        });
        const payload = await response.json().catch(() => null) as HandoffResponse | null;
        const handoff = response.ok ? handoffIdFromResponse(payload) : null;
        if (!handoff || cancelled) {
          redirect();
          return;
        }
        // The form POST keeps the opaque id out of the redirect URL and lets
        // the canonical site set its first-party, HttpOnly cookie.
        submitHandoff(handoff);
      } catch {
        redirect();
      }
    };

    void preserveExistingSession();
    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}

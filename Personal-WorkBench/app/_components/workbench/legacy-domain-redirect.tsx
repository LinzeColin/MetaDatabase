"use client";

import { useEffect } from "react";
import { canonicalLegacyUrl } from "./canonical-domain";

export function LegacyDomainRedirect() {
  useEffect(() => {
    const destination = canonicalLegacyUrl(window.location.href);
    if (destination && destination !== window.location.href) window.location.replace(destination);
  }, []);

  return null;
}

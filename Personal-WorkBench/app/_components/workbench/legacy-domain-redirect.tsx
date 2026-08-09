"use client";

import { useEffect } from "react";
import { canonicalRetiredUrl } from "./canonical-domain";

export function LegacyDomainRedirect() {
  useEffect(() => {
    const destination = canonicalRetiredUrl(window.location.href);
    if (destination && destination !== window.location.href) window.location.replace(destination);
  }, []);

  return null;
}

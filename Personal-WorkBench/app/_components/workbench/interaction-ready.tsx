"use client";

import { type ReactNode, useSyncExternalStore } from "react";

function subscribeToHydration() {
  return () => {};
}

/**
 * The server can paint the workbench before its client controls are hydrated.
 * Keep that tiny window visibly non-interactive so an early tap cannot be
 * overwritten by hydration and look like a lost save.
 */
export function WorkbenchInteractionReady({ children }: { children: ReactNode }) {
  // `getServerSnapshot` keeps SSR and the initial hydration pass identical.
  // React then reads the stable client snapshot and unlocks the controls.
  const ready = useSyncExternalStore(subscribeToHydration, () => true, () => false);

  return (
    <div
      aria-busy={!ready}
      className="workbench-interaction-gate"
      data-interactions-ready={ready ? "true" : "false"}
      inert={!ready}
    >
      {children}
      {!ready ? <p className="workbench-interaction-loading" role="status">正在准备工作台…</p> : null}
    </div>
  );
}

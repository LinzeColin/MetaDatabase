"use client";

import { Fingerprint } from "lucide-react";

import type { AnalysisContext, ServerContextState } from "./analysis-contract";

type AnalysisContextBadgeProps = {
  analysisContext: AnalysisContext;
  serverState: ServerContextState;
};

/**
 * The single cross-view context badge (T805/A108). Every routed view renders
 * this from the same useAnalysisContext hook, so what the user sees about
 * "which snapshot am I looking at" cannot drift between modules.
 */
export function AnalysisContextBadge({
  analysisContext,
  serverState
}: AnalysisContextBadgeProps) {
  const live = serverState.mode === "live";
  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-slate-800 bg-slate-900/50 px-3 py-1.5 text-xs text-slate-400"
      data-testid="analysis-context-badge"
      data-context-mode={serverState.mode}
      data-refresh-generation={live ? serverState.refreshGeneration ?? "" : ""}
      data-data-snapshot={analysisContext.dataSnapshot}
    >
      <span className="flex items-center gap-1 text-slate-300">
        <Fingerprint className="h-3.5 w-3.5" aria-hidden />
        分析上下文
      </span>
      <span data-testid="context-data-snapshot">快照 {analysisContext.dataSnapshot}</span>
      <span data-testid="context-profile">档位 {analysisContext.profileVersion}</span>
      {live ? (
        <span className="text-emerald-300" data-testid="context-live-generation">
          server · gen {serverState.refreshGeneration ?? "?"}
        </span>
      ) : (
        <span className="text-amber-300" data-testid="context-fallback">
          {serverState.mode === "api_required" ? "未连接 API（fixture 展示）" : "fixture 回退"}
        </span>
      )}
    </div>
  );
}

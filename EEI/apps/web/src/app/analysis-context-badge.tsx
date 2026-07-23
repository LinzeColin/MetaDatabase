"use client";

import { Fingerprint } from "lucide-react";

import type { AnalysisContext, ServerContextState } from "./analysis-contract";

type AnalysisContextBadgeProps = {
  analysisContext: AnalysisContext;
  serverState: ServerContextState;
};

/**
 * The single cross-view context badge (T805/A108)。P0-2 治理术语清场
 * （UX_SPEC_EEI §E.1）：对用户只呈现一枚小 pill——「实时数据 · 更新于
 * MM-DD」或「示例模式」；快照 key / 档位 / 刷新代数等机器状态整体收进
 * 〈诊断详情〉折叠，原契约 testid 与 data-* 全部保留。
 */
export function AnalysisContextBadge({
  analysisContext,
  serverState
}: AnalysisContextBadgeProps) {
  const live = serverState.mode === "live";
  const updatedAt = live && serverState.activatedAt ? serverState.activatedAt.slice(5, 10) : null;
  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-slate-800 bg-slate-900/50 px-3 py-1.5 text-xs text-slate-400"
      data-testid="analysis-context-badge"
      data-context-mode={serverState.mode}
      data-refresh-generation={live ? serverState.refreshGeneration ?? "" : ""}
      data-data-snapshot={analysisContext.dataSnapshot}
    >
      {live ? (
        <span
          className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-300"
          data-testid="context-live-generation"
        >
          <Fingerprint className="h-3.5 w-3.5" aria-hidden />
          实时数据{updatedAt ? ` · 更新于 ${updatedAt}` : ""}
        </span>
      ) : (
        <span
          className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-300"
          data-testid="context-fallback"
        >
          <Fingerprint className="h-3.5 w-3.5" aria-hidden />
          {serverState.mode === "api_required" ? "示例模式（未连接数据服务）" : "示例模式"}
        </span>
      )}
      <details className="diagDetails">
        <summary>诊断详情</summary>
        <span data-testid="context-data-snapshot">快照 {analysisContext.dataSnapshot}</span>
        <span data-testid="context-profile">档位 {analysisContext.profileVersion}</span>
        <span data-testid="context-mode-detail">
          {live ? `server · gen ${serverState.refreshGeneration ?? "?"}` : serverState.mode}
        </span>
      </details>
    </div>
  );
}

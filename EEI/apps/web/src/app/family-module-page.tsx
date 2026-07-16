"use client";

import { AlertTriangle, BadgeCheck, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { AnalysisContextBadge } from "./analysis-context-badge";
import {
  loadFamilyOverview,
  type FamilyOverviewRecord,
  type FamilyOverviewSyncResult
} from "./family-module-client";
import { useAnalysisContext } from "./use-analysis-context";
import { WorkspaceNavigationRail } from "./workspace-navigation";
import type { WorkspaceModuleId } from "./workspace-context";

type LoadState = "idle" | "loading" | "hydrated" | "error" | "api_required";

type FamilyModulePageProps = {
  moduleId: WorkspaceModuleId;
  endpoint: "/v1/ma/overview" | "/v1/control/overview" | "/v1/signals/overview";
  title: string;
  subtitle: string;
  icon: ReactNode;
  testId: string;
  renderExtra?: (overview: FamilyOverviewRecord) => ReactNode;
};

/**
 * Shared honest module shell for relationship-family views (S8PC). Every
 * relationship row carries its published / fixture labeling; abstentions are
 * rendered verbatim from the API so the honest boundary travels with data.
 */
export function FamilyModulePage({
  moduleId,
  endpoint,
  title,
  subtitle,
  icon,
  testId,
  renderExtra
}: FamilyModulePageProps) {
  const [result, setResult] = useState<FamilyOverviewSyncResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const { analysisContext, serverState } = useAnalysisContext();

  useEffect(() => {
    void hydrate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function hydrate() {
    setLoadState("loading");
    const next = await loadFamilyOverview(endpoint);
    setResult(next);
    if (next.status === "hydrated") {
      setLoadState("hydrated");
    } else if (next.status === "api_required") {
      setLoadState("api_required");
    } else {
      setLoadState("error");
    }
  }

  const overview: FamilyOverviewRecord | null =
    result?.status === "hydrated" ? result.overview : null;

  function handleNavigation(_target: string, nextModuleId: WorkspaceModuleId) {
    if (nextModuleId !== moduleId) {
      window.location.href = "/";
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail
        activeLens="all"
        activeModuleId={moduleId}
        onLensTarget={handleNavigation}
        onSectionTarget={handleNavigation}
      />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid={testId}>
        <header className="flex items-center justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              {icon}
              {title}
            </h1>
            <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
          </div>
          <button
            type="button"
            onClick={() => void hydrate()}
            className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
            data-testid={`${testId}-refresh`}
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            刷新
          </button>
        </header>

        <AnalysisContextBadge analysisContext={analysisContext} serverState={serverState} />

        {loadState === "api_required" ? (
          <section
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100"
            data-testid={`${testId}-api-required`}
          >
            <p className="flex items-center gap-2 font-medium">
              <AlertTriangle className="h-4 w-4" aria-hidden />
              需要连接 EEI API — 本模块不用合成数据充数。
            </p>
          </section>
        ) : null}

        {loadState === "error" ? (
          <section
            className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-100"
            data-testid={`${testId}-load-error`}
          >
            加载失败（{result?.status === "error" ? result.reason : "unknown"}）。
          </section>
        ) : null}

        {overview ? (
          <>
            <section
              className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
              data-testid={`${testId}-relationships`}
            >
              <h2 className="text-sm font-medium text-slate-300">
                关系断言（{overview.relationships.length}）
              </h2>
              {overview.relationships.length === 0 ? (
                <p className="mt-2 text-sm text-slate-400" data-testid={`${testId}-empty`}>
                  图谱当前没有该族的已断言关系。缺席=无断言而非无关系 —— 候选经双源核验与
                  Owner 签核后自动出现。
                </p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {overview.relationships.map((relationship) => (
                    <li
                      key={relationship.id}
                      className={`flex flex-wrap items-center gap-2 rounded-md border p-3 text-sm ${
                        relationship.owner_signed_published
                          ? "border-emerald-500/40 bg-emerald-500/10"
                          : "border-slate-800 bg-slate-950/60"
                      }`}
                    >
                      <span className="font-medium">{relationship.subject_name}</span>
                      <span className="text-xs text-slate-400">
                        —[{relationship.relationship_type}]→
                      </span>
                      <span className="font-medium">{relationship.object_name}</span>
                      {relationship.owner_signed_published ? (
                        <span className="flex items-center gap-1 rounded bg-emerald-500/20 px-1.5 py-0.5 text-xs text-emerald-200">
                          <BadgeCheck className="h-3 w-3" aria-hidden />
                          已发布 · Owner 签核
                        </span>
                      ) : (
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400">
                          {relationship.fixture_flag ? "fixture 演示" : relationship.status}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {renderExtra ? renderExtra(overview) : null}

            <section
              className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-xs text-slate-400"
              data-testid={`${testId}-abstentions`}
            >
              <p className="font-medium text-slate-300">诚实边界</p>
              <ul className="mt-2 list-inside list-disc space-y-1">
                {Object.entries(overview.abstentions).map(([key, note]) => (
                  <li key={key}>{note}</li>
                ))}
              </ul>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

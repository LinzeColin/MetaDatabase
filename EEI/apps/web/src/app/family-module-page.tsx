"use client";

import { AlertTriangle, BadgeCheck, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { AnalysisContextBadge } from "./analysis-context-badge";
import {
  loadFamilyOverview,
  type FamilyOverviewRecord,
  type FamilyOverviewSyncResult
} from "./family-module-client";
import { zhLabel } from "./labels";
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
  /** P0-4 空态三段式（§E.2 a 型）：本模块的「事实覆盖」句。 */
  emptyCoverageNote: string;
  renderExtra?: (overview: FamilyOverviewRecord) => ReactNode;
};

/**
 * Shared honest module shell for relationship-family views (S8PC)。
 * P0-2/P0-4（UX_SPEC_EEI §E.1/§E.2）：状态文案人话化、治理黑话收进
 * 〈诊断详情〉、空态改为「事实覆盖 + 原因 + 可点下一步」三段式。
 */
export function FamilyModulePage({
  moduleId,
  endpoint,
  title,
  subtitle,
  icon,
  testId,
  emptyCoverageNote,
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

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail activeModuleId={moduleId} />
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
              暂时连不上数据服务，请稍后重试。
            </p>
            <button
              type="button"
              onClick={() => void hydrate()}
              className="mt-2 rounded-md border border-amber-400/50 px-3 py-1 text-xs hover:bg-amber-500/20"
              data-testid={`${testId}-api-required-retry`}
            >
              重试
            </button>
          </section>
        ) : null}

        {loadState === "error" ? (
          <section
            className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-100"
            data-testid={`${testId}-load-error`}
          >
            <p className="font-medium">加载没有成功，请稍后重试。</p>
            <button
              type="button"
              onClick={() => void hydrate()}
              className="mt-2 rounded-md border border-rose-400/50 px-3 py-1 text-xs hover:bg-rose-500/20"
              data-testid={`${testId}-load-error-retry`}
            >
              重试
            </button>
            <details className="diagDetails mt-2 text-xs text-rose-200/80">
              <summary>诊断详情</summary>
              <span>{result?.status === "error" ? result.reason : "unknown"}</span>
            </details>
          </section>
        ) : null}

        {overview ? (
          <>
            <section
              className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
              data-testid={`${testId}-relationships`}
            >
              <h2 className="text-sm font-medium text-slate-300">
                已核实关系（{overview.relationships.length}）
              </h2>
              {overview.relationships.length === 0 ? (
                <div className="mt-2 text-sm text-slate-400" data-testid={`${testId}-empty`}>
                  <p className="font-medium text-slate-200">{title}数据采集中</p>
                  <p className="mt-1">
                    {emptyCoverageNote}
                    数据来自 SEC、GLEIF 等官方来源，新数据核实后会自动出现在这里。
                  </p>
                  <p className="mt-2 flex flex-wrap gap-2">
                    <a
                      className="rounded-md border border-slate-700 px-3 py-1 text-xs hover:bg-slate-800"
                      href="/"
                    >
                      去商业版图看看
                    </a>
                    <a
                      className="rounded-md border border-slate-700 px-3 py-1 text-xs hover:bg-slate-800"
                      href="/objects-scope"
                    >
                      查看数据覆盖范围
                    </a>
                  </p>
                </div>
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
                        —[{zhLabel("relationship_type", relationship.relationship_type)}]→
                      </span>
                      <span className="font-medium">{relationship.object_name}</span>
                      {relationship.owner_signed_published ? (
                        <span className="flex items-center gap-1 rounded bg-emerald-500/20 px-1.5 py-0.5 text-xs text-emerald-200">
                          <BadgeCheck className="h-3 w-3" aria-hidden />
                          已核实 · 官方来源
                        </span>
                      ) : (
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400">
                          {relationship.fixture_flag
                            ? "示例数据"
                            : zhLabel("status", relationship.status)}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {renderExtra ? renderExtra(overview) : null}

            <details
              className="diagDetails rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-xs text-slate-400"
              data-testid={`${testId}-abstentions`}
            >
              <summary className="font-medium text-slate-300">诊断详情 · 数据边界</summary>
              <ul className="mt-2 list-inside list-disc space-y-1">
                {Object.entries(overview.abstentions).map(([key, note]) => (
                  <li key={key}>{note}</li>
                ))}
              </ul>
            </details>
          </>
        ) : null}
      </main>
    </div>
  );
}

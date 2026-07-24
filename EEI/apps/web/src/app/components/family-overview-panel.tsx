"use client";

// P2-10：关系族概览面板（从 family-module-page.tsx 主体抽出，自包含加载 + 刷新）。
// 供 /signals「战略信号」tab 与 FamilyModulePage 共用，避免重复渲染逻辑。
// 文案人话化、治理黑话收〈诊断详情〉、空态三段式沿用 P0-2/P0-4 口径不变。

import { BadgeCheck, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { AnalysisContextBadge } from "../analysis-context-badge";
import { EmptyState, ErrorState, Skeleton, TopLoadingBar } from "./feedback";
import {
  loadFamilyOverview,
  type FamilyOverviewRecord,
  type FamilyOverviewSyncResult
} from "../family-module-client";
import { zhLabel } from "../labels";
import { useAnalysisContext } from "../use-analysis-context";

type LoadState = "idle" | "loading" | "hydrated" | "error" | "api_required";

type FamilyOverviewPanelProps = {
  endpoint: "/v1/ma/overview" | "/v1/control/overview" | "/v1/signals/overview";
  title: string;
  testId: string;
  /** P0-4 空态三段式（§E.2 a 型）：本模块的「事实覆盖」句。 */
  emptyCoverageNote: string;
  renderExtra?: (overview: FamilyOverviewRecord) => ReactNode;
};

export function FamilyOverviewPanel({
  endpoint,
  title,
  testId,
  emptyCoverageNote,
  renderExtra
}: FamilyOverviewPanelProps) {
  const [result, setResult] = useState<FamilyOverviewSyncResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const { analysisContext, serverState } = useAnalysisContext();

  useEffect(() => {
    void hydrate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint]);

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
    <div className="space-y-6" data-testid={testId}>
      <div className="flex items-center justify-between gap-3">
        <AnalysisContextBadge analysisContext={analysisContext} serverState={serverState} />
        <button
          className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
          data-testid={`${testId}-refresh`}
          onClick={() => void hydrate()}
          type="button"
        >
          <RefreshCw className="h-4 w-4" aria-hidden />
          刷新
        </button>
      </div>

      {/* P1-6：刷新不清屏——旧数据保留，仅顶部走 1px 进度条（延迟 300ms）。 */}
      <TopLoadingBar active={loadState === "loading" && Boolean(overview)} />

      {loadState === "loading" && !overview ? (
        <Skeleton count={3} testId={`${testId}-skeleton`} variant="card" />
      ) : null}

      {loadState === "api_required" ? (
        <ErrorState
          description="请稍后重试，或确认数据接口已配置。"
          onRetry={() => void hydrate()}
          retryTestId={`${testId}-api-required-retry`}
          testId={`${testId}-api-required`}
          title="暂时连不上数据服务"
          tone="warn"
        />
      ) : null}

      {loadState === "error" ? (
        <ErrorState
          description="请稍后重试。若持续失败，说明数据服务暂时异常。"
          detail={result?.status === "error" ? result.reason : "unknown"}
          onRetry={() => void hydrate()}
          retryTestId={`${testId}-load-error-retry`}
          testId={`${testId}-load-error`}
          title="加载没有成功"
          tone="error"
        />
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
              <div className="mt-2">
                <EmptyState
                  actions={
                    <>
                      <a href="/">去商业版图看看</a>
                      <a href="/objects-scope">查看数据覆盖范围</a>
                    </>
                  }
                  description={
                    <>
                      {emptyCoverageNote}
                      数据来自 SEC、GLEIF 等官方来源，新数据核实后会自动出现在这里。
                    </>
                  }
                  testId={`${testId}-empty`}
                  title={`${title}数据采集中`}
                  variant="collecting"
                />
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
    </div>
  );
}

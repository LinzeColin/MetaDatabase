"use client";

import { BadgeCheck, FileSearch, PackageSearch, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AnalysisContextBadge } from "../analysis-context-badge";
import { loadCloudEvidenceDetail } from "../cloud-data-client";
import { EvidencePanel, type EvidencePanelState } from "../components/evidence-panel";
import { ErrorState, Skeleton, TopLoadingBar } from "../components/feedback";
import { zhLabel } from "../labels";
import type { EvidenceDetailRecord } from "../production-data-client";
import {
  loadSupplyChainOverview,
  type SupplyChainOverviewRecord,
  type SupplyChainRelationship,
  type SupplyChainSyncResult
} from "../supply-chain-client";
import { useAnalysisContext } from "../use-analysis-context";
import { WorkspaceNavigationRail } from "../workspace-navigation";

type LoadState = "idle" | "loading" | "hydrated" | "error" | "api_required";

// P0-4 供应链页改造（UX_SPEC_EEI §G-P0-4/§E.2）：
// 16 行全量渲染（14 行空）→ 覆盖横幅（已核实 X/16）+ 仅有数据阶段的
// 关系卡 + 「其余环节采集中」单条折叠区。空就是空，但每个空态都带
// 事实覆盖、原因与可点的下一步。
export default function SupplyChainPage() {
  const [result, setResult] = useState<SupplyChainSyncResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const { analysisContext, serverState } = useAnalysisContext();

  useEffect(() => {
    void hydrate();
  }, []);

  async function hydrate() {
    setLoadState("loading");
    const next = await loadSupplyChainOverview();
    setResult(next);
    if (next.status === "hydrated") {
      setLoadState("hydrated");
    } else if (next.status === "api_required") {
      setLoadState("api_required");
    } else {
      setLoadState("error");
    }
  }

  const overview: SupplyChainOverviewRecord | null =
    result?.status === "hydrated" ? result.overview : null;

  const relationshipsByStage = useMemo(() => {
    const map = new Map<string, SupplyChainRelationship[]>();
    for (const relationship of overview?.relationships ?? []) {
      const key = relationship.stage_id ?? "unmapped";
      map.set(key, [...(map.get(key) ?? []), relationship]);
    }
    return map;
  }, [overview]);

  const coveredStages = useMemo(
    () => (overview?.stages ?? []).filter((stage) => (relationshipsByStage.get(stage.stage_id) ?? []).length > 0),
    [overview, relationshipsByStage]
  );
  const pendingStages = useMemo(
    () => (overview?.stages ?? []).filter((stage) => (relationshipsByStage.get(stage.stage_id) ?? []).length === 0),
    [overview, relationshipsByStage]
  );

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail activeModuleId="supply_chain" />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid="supply-chain-page">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              <PackageSearch className="h-6 w-6 text-emerald-300" aria-hidden />
              供应链
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              上下游依赖关系 — 只展示经官方文件核实的事实
            </p>
          </div>
          <button
            type="button"
            onClick={() => void hydrate()}
            className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
            data-testid="supply-chain-refresh"
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            刷新
          </button>
        </header>

        <AnalysisContextBadge analysisContext={analysisContext} serverState={serverState} />

        {/* P1-6：刷新不清屏，仅顶部 1px 进度条（延迟 300ms）；首载走同构骨架。 */}
        <TopLoadingBar active={loadState === "loading" && Boolean(overview)} />

        {loadState === "loading" && !overview ? (
          <Skeleton count={4} testId="supply-chain-skeleton" variant="card" />
        ) : null}

        {loadState === "api_required" ? (
          <ErrorState
            description="请稍后重试，或确认数据接口已配置。"
            onRetry={() => void hydrate()}
            retryTestId="supply-chain-api-required-retry"
            testId="supply-chain-api-required"
            title="暂时连不上数据服务"
            tone="warn"
          />
        ) : null}

        {loadState === "error" ? (
          <ErrorState
            description="供应链数据加载没有成功，请稍后重试。"
            detail={result?.status === "error" ? result.reason : "unknown"}
            onRetry={() => void hydrate()}
            retryTestId="supply-chain-load-error-retry"
            testId="supply-chain-load-error"
            title="加载没有成功"
            tone="error"
          />
        ) : null}

        {overview ? (
          <>
            {/* §E.2 a 型覆盖横幅：事实覆盖 + 原因 + 可点下一步。 */}
            <section
              className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4"
              data-testid="supply-chain-coverage-banner"
            >
              <p className="text-base font-semibold text-emerald-200">供应链数据采集中</p>
              <p className="mt-1 text-sm text-slate-300">
                已核实 {overview.summary.stages_with_relationships}/
                {overview.summary.stages_total} 个环节
                {coveredStages.length > 0
                  ? `（${coveredStages.map((stage) => stage.name_zh).join("、")}）`
                  : ""}
                ，共 {overview.summary.published_fact_count} 条已核实事实。数据来自 SEC
                年报等官方披露，采集范围扩展中。
              </p>
              <p className="mt-2 flex flex-wrap gap-2 text-xs">
                <a
                  className="rounded-md border border-emerald-500/40 px-3 py-1 hover:bg-emerald-500/15"
                  href="#supply-covered-stages"
                >
                  查看已覆盖环节
                </a>
                <a
                  className="rounded-md border border-slate-700 px-3 py-1 hover:bg-slate-800"
                  href="/objects-scope"
                >
                  查看数据来源
                </a>
              </p>
            </section>

            <section
              className="grid grid-cols-1 gap-4 md:grid-cols-3"
              data-testid="supply-chain-first-screen-answer"
            >
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
                <p className="text-xs uppercase tracking-wide text-emerald-300/80">
                  已核实事实
                </p>
                <p className="mt-2 text-3xl font-semibold text-emerald-200">
                  {overview.summary.published_fact_count}
                </p>
                <p className="mt-1 text-xs text-slate-400">每条都可回溯到官方文件</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">环节覆盖</p>
                <p className="mt-2 text-3xl font-semibold">
                  {overview.summary.stages_with_relationships}
                  <span className="text-base font-normal text-slate-400">
                    /{overview.summary.stages_total} 个环节有数据
                  </span>
                </p>
                <p className="mt-1 text-xs text-slate-400">十六环节：上游→中游→下游→横切</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">待核实关系</p>
                <p className="mt-2 text-3xl font-semibold">
                  {overview.summary.demo_or_candidate_count}
                </p>
                <p className="mt-1 text-xs text-slate-400">逐条标注，与已核实事实分开呈现</p>
              </div>
            </section>

            {/* 仅渲染有数据的阶段；空阶段收进下方单条折叠区（首屏零空行）。 */}
            <section
              className="space-y-3"
              data-testid="supply-chain-rail"
              id="supply-covered-stages"
            >
              {coveredStages.map((stage) => {
                const items = relationshipsByStage.get(stage.stage_id) ?? [];
                return (
                  <div
                    key={stage.stage_id}
                    className="rounded-lg border border-slate-700 bg-slate-900/50 p-3"
                    data-testid={`supply-stage-${stage.stage_id}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-300">
                        {stage.stage_id}
                      </span>
                      <span className="text-sm font-medium">{stage.name_zh}</span>
                    </div>
                    <ul className="mt-2 space-y-1.5">
                      {items.map((relationship) => (
                        <li
                          key={relationship.id}
                          className={`flex flex-wrap items-center gap-2 rounded-md border p-2 text-sm ${
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
                          {relationship.confidence !== null ? (
                            <span className="text-xs text-slate-500">
                              置信 {relationship.confidence.toFixed(2)}
                            </span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
              {coveredStages.length === 0 ? (
                <p className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-3 text-sm text-slate-400">
                  十六个环节都还在采集中 — 新数据核实后会自动出现在这里。
                </p>
              ) : null}

              {pendingStages.length > 0 ? (
                <details
                  className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-3"
                  data-testid="supply-chain-pending-stages"
                >
                  <summary className="cursor-pointer text-sm text-slate-300">
                    其余 {pendingStages.length} 个环节采集中 — 暂无已核实数据，点开查看清单
                  </summary>
                  <ul className="mt-2 space-y-1 text-sm text-slate-400">
                    {pendingStages.map((stage) => (
                      <li
                        key={stage.stage_id}
                        className="flex items-center gap-2"
                        data-testid={`supply-stage-${stage.stage_id}`}
                      >
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500">
                          {stage.stage_id}
                        </span>
                        <span>{stage.name_zh}</span>
                        <span className="text-xs text-slate-500">采集中</span>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}

              {(relationshipsByStage.get("unmapped") ?? []).length > 0 ? (
                <div
                  className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-3"
                  data-testid="supply-stage-unmapped"
                >
                  <p className="text-sm font-medium text-slate-300">未归入环节的关系</p>
                  <ul className="mt-2 space-y-1.5 text-sm text-slate-400">
                    {(relationshipsByStage.get("unmapped") ?? []).map((relationship) => (
                      <li key={relationship.id}>
                        {relationship.subject_name} —[
                        {zhLabel("relationship_type", relationship.relationship_type)}]→{" "}
                        {relationship.object_name}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>

            <details
              className="diagDetails rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-xs text-slate-400"
              data-testid="supply-chain-abstentions"
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

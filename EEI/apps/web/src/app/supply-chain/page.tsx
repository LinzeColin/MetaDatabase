"use client";

import { AlertTriangle, BadgeCheck, PackageSearch, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AnalysisContextBadge } from "../analysis-context-badge";
import {
  loadSupplyChainOverview,
  type SupplyChainOverviewRecord,
  type SupplyChainRelationship,
  type SupplyChainSyncResult
} from "../supply-chain-client";
import { useAnalysisContext } from "../use-analysis-context";
import { WorkspaceNavigationRail } from "../workspace-navigation";
import type { WorkspaceModuleId } from "../workspace-context";

type LoadState = "idle" | "loading" | "hydrated" | "error" | "api_required";

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

  function handleNavigation(_target: string, moduleId: WorkspaceModuleId) {
    if (moduleId !== "supply_chain") {
      window.location.href = "/";
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail
        activeLens="supply_chain"
        activeModuleId="supply_chain"
        onLensTarget={handleNavigation}
        onSectionTarget={handleNavigation}
      />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid="supply-chain-page">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              <PackageSearch className="h-6 w-6 text-emerald-300" aria-hidden />
              供应链
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              十六阶段全链轨道 — Owner 签核事实与演示数据分层呈现，绝不混同
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

        {loadState === "api_required" ? (
          <section
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100"
            data-testid="supply-chain-api-required"
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
            data-testid="supply-chain-load-error"
          >
            供应链概览加载失败（{result?.status === "error" ? result.reason : "unknown"}）。
          </section>
        ) : null}

        {overview ? (
          <>
            <section
              className="grid grid-cols-1 gap-4 md:grid-cols-3"
              data-testid="supply-chain-first-screen-answer"
            >
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
                <p className="text-xs uppercase tracking-wide text-emerald-300/80">
                  Owner 签核已发布事实
                </p>
                <p className="mt-2 text-3xl font-semibold text-emerald-200">
                  {overview.summary.published_fact_count}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  双源核验 + 签名哈希入库 — 全链最高证据等级
                </p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">阶段覆盖</p>
                <p className="mt-2 text-3xl font-semibold">
                  {overview.summary.stages_with_relationships}
                  <span className="text-base font-normal text-slate-400">
                    /{overview.summary.stages_total} 阶段有断言
                  </span>
                </p>
                <p className="mt-1 text-xs text-slate-400">十六阶段：上游→中游→下游→横切</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  演示/候选关系
                </p>
                <p className="mt-2 text-3xl font-semibold">
                  {overview.summary.demo_or_candidate_count}
                </p>
                <p className="mt-1 text-xs text-slate-400">逐条标注，永不冒充已发布事实</p>
              </div>
            </section>

            <section className="space-y-3" data-testid="supply-chain-rail">
              {overview.stages.map((stage) => {
                const items = relationshipsByStage.get(stage.stage_id) ?? [];
                return (
                  <div
                    key={stage.stage_id}
                    className={`rounded-lg border p-3 ${
                      items.length > 0
                        ? "border-slate-700 bg-slate-900/50"
                        : "border-slate-800/60 bg-slate-900/20"
                    }`}
                    data-testid={`supply-stage-${stage.stage_id}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-300">
                        {stage.stage_id}
                      </span>
                      <span className="text-sm font-medium">{stage.name_zh}</span>
                      <span className="text-xs text-slate-500">{stage.default_direction}</span>
                      {items.length === 0 ? (
                        <span className="text-xs text-slate-500">无断言（≠真实为空）</span>
                      ) : null}
                    </div>
                    {items.length > 0 ? (
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
                            {relationship.confidence !== null ? (
                              <span className="text-xs text-slate-500">
                                置信 {relationship.confidence.toFixed(2)}
                              </span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                );
              })}
              {(relationshipsByStage.get("unmapped") ?? []).length > 0 ? (
                <div
                  className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-3"
                  data-testid="supply-stage-unmapped"
                >
                  <p className="text-sm font-medium text-slate-300">未映射到阶段的关系</p>
                  <ul className="mt-2 space-y-1.5 text-sm text-slate-400">
                    {(relationshipsByStage.get("unmapped") ?? []).map((relationship) => (
                      <li key={relationship.id}>
                        {relationship.subject_name} —[{relationship.relationship_type}]→{" "}
                        {relationship.object_name}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>

            <section
              className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-xs text-slate-400"
              data-testid="supply-chain-abstentions"
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

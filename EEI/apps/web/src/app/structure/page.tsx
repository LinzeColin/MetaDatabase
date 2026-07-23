"use client";

import { Building2, Boxes, FileSearch, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { AnalysisContextBadge } from "../analysis-context-badge";
import { loadCloudEvidenceDetail } from "../cloud-data-client";
import { EvidencePanel, type EvidencePanelState } from "../components/evidence-panel";
import { ErrorState, Skeleton, TopLoadingBar } from "../components/feedback";
import { zhLabel } from "../labels";
import type { EvidenceDetailRecord } from "../production-data-client";
import {
  loadEntityEmpire,
  searchEntityIdByName,
  type EmpireRecord,
  type EmpireSyncResult,
  type StructureItem,
  type StructureSection
} from "../structure-client";
import { useAnalysisContext } from "../use-analysis-context";
import { WorkspaceNavigationRail } from "../workspace-navigation";

type LoadState = "idle" | "loading" | "hydrated" | "error" | "api_required";

const DEFAULT_FOCUS_NAME = "NVIDIA Corporation";
const STRUCTURE_SECTION_ORDER = [
  "legal_group",
  "business_segments",
  "brands",
  "products",
  "facilities"
];

export default function GroupStructurePage() {
  const [focusQuery, setFocusQuery] = useState(DEFAULT_FOCUS_NAME);
  const [result, setResult] = useState<EmpireSyncResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadReason, setLoadReason] = useState("initializing");
  const { analysisContext, serverState } = useAnalysisContext();

  useEffect(() => {
    void hydrate(DEFAULT_FOCUS_NAME);
  }, []);

  async function hydrate(name: string) {
    setLoadState("loading");
    setLoadReason("resolving_focus_entity");
    const entityId = await searchEntityIdByName(name);
    if (!entityId) {
      const apiMissing = !window.localStorage && false;
      setLoadState(apiMissing ? "api_required" : "error");
      setLoadReason("focus_entity_not_resolved");
      setResult(null);
      return;
    }
    setLoadReason("requesting_empire_structure");
    const next = await loadEntityEmpire(entityId);
    setResult(next);
    if (next.status === "hydrated") {
      setLoadState("hydrated");
    } else if (next.status === "api_required") {
      setLoadState("api_required");
    } else {
      setLoadState("error");
      setLoadReason(next.status === "error" ? next.reason : "unknown");
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void hydrate(focusQuery.trim() || DEFAULT_FOCUS_NAME);
  }

  const empire: EmpireRecord | null = result?.status === "hydrated" ? result.empire : null;

  const orderedSections = useMemo(() => {
    if (!empire) {
      return [] as Array<[string, StructureSection]>;
    }
    return STRUCTURE_SECTION_ORDER.filter((key) => empire.structure[key]).map(
      (key) => [key, empire.structure[key]] as [string, StructureSection]
    );
  }, [empire]);

  const coveredSections = useMemo(
    () => orderedSections.filter(([, section]) => section.data_status === "covered").length,
    [orderedSections]
  );
  const segmentSection = empire?.structure.business_segments ?? null;

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail activeModuleId="group_structure" />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid="group-structure-page">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              <Building2 className="h-6 w-6 text-sky-300" aria-hidden />
              集团与控制
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              谁控制谁？董监高是谁？— 法律集团 / 板块 / 品牌 / 产品 / 设施五层分开呈现
            </p>
          </div>
          <form onSubmit={handleSubmit} className="flex items-center gap-2">
            <label className="sr-only" htmlFor="focus-entity">
              焦点实体
            </label>
            <input
              id="focus-entity"
              value={focusQuery}
              onChange={(event) => setFocusQuery(event.target.value)}
              className="w-64 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm"
              placeholder="焦点实体名称"
              data-testid="structure-focus-input"
            />
            <button
              type="submit"
              className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
              data-testid="structure-focus-submit"
            >
              <Search className="h-4 w-4" aria-hidden />
              切换
            </button>
            <button
              type="button"
              onClick={() => void hydrate(focusQuery.trim() || DEFAULT_FOCUS_NAME)}
              className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
              data-testid="structure-refresh"
            >
              <RefreshCw className="h-4 w-4" aria-hidden />
              刷新
            </button>
          </form>
        </header>

        <AnalysisContextBadge analysisContext={analysisContext} serverState={serverState} />

        {/* P1-6：刷新不清屏，仅顶部 1px 进度条（延迟 300ms）；首载走同构骨架。 */}
        <TopLoadingBar active={loadState === "loading" && Boolean(empire)} />

        {loadState === "loading" && !empire ? (
          <Skeleton count={3} testId="structure-skeleton" variant="card" />
        ) : null}

        {loadState === "api_required" ? (
          <ErrorState
            description="请稍后重试，或确认数据接口已配置。"
            onRetry={() => void hydrate(focusQuery.trim() || DEFAULT_FOCUS_NAME)}
            retryTestId="structure-api-required-retry"
            testId="structure-api-required"
            title="暂时连不上数据服务"
            tone="warn"
          />
        ) : null}

        {loadState === "error" ? (
          <ErrorState
            description="结构数据加载没有成功，请稍后重试。"
            detail={loadReason}
            onRetry={() => void hydrate(focusQuery.trim() || DEFAULT_FOCUS_NAME)}
            retryTestId="structure-load-error-retry"
            testId="structure-load-error"
            title="加载没有成功"
            tone="error"
          />
        ) : null}

        {empire ? (
          <>
            <section
              className="grid grid-cols-1 gap-4 md:grid-cols-3"
              data-testid="structure-first-screen-answer"
            >
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">焦点实体</p>
                <p className="mt-2 truncate text-xl font-semibold" title={empire.focus.canonical_name}>
                  {empire.focus.canonical_name}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {Object.entries(empire.focus.primary_identifiers)
                    .filter(([key]) => key === key.toLowerCase())
                    .map(([key, value]) => `${key}:${value}`)
                    .join(" · ") || "无注册标识"}
                </p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">结构五层覆盖</p>
                <p className="mt-2 text-3xl font-semibold">
                  {coveredSections}
                  <span className="text-base font-normal text-slate-400">
                    /{orderedSections.length} 层有数据
                  </span>
                </p>
                <p className="mt-1 text-xs text-slate-400">法律集团/板块/品牌/产品/设施分离呈现</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">数据模式</p>
                <p className="mt-2 text-xl font-semibold">
                  {empire.data_mode === "synthetic_fixture" ? "示例数据" : "已核实数据"}
                </p>
                <p className="mt-1 text-xs text-amber-300/90">
                  {empire.data_mode === "synthetic_fixture"
                    ? "示例数据仅作演示，不代表真实事实"
                    : "来自官方文件，逐条可查来源"}
                </p>
              </div>
            </section>

            <section className="space-y-4" data-testid="structure-sections">
              {orderedSections.map(([key, section]) => (
                <div
                  key={key}
                  id={key === "business_segments" ? "segments" : undefined}
                  className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
                  data-testid={`structure-section-${key}`}
                >
                  <h2 className="flex items-center gap-2 text-sm font-medium text-slate-300">
                    {key === "business_segments" ? (
                      <Boxes className="h-4 w-4" aria-hidden />
                    ) : (
                      <Building2 className="h-4 w-4" aria-hidden />
                    )}
                    {section.label}
                    <span className="text-xs font-normal text-slate-500">
                      {section.item_count} 项 · {zhLabel("status", section.data_status)}
                    </span>
                  </h2>
                  {section.items.length === 0 ? (
                    <p className="mt-2 text-sm text-slate-400">
                      该层暂无已核实数据 — 数据来自官方文件披露，新数据核实后会自动出现在这里。
                    </p>
                  ) : (
                    <ul className="mt-3 space-y-2">
                      {section.items.map((item) => (
                        <li
                          key={`${item.entity.id}-${item.relationship.relationship_type}`}
                          className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm"
                        >
                          <p className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{item.entity.canonical_name}</span>
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-300">
                              {zhLabel("relationship_type", item.relationship.relationship_type)}
                            </span>
                            <span className="text-xs text-slate-500">
                              {zhLabel("status", item.relationship.status)}
                            </span>
                            {item.fixture_notice ? (
                              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-200">
                                示例
                              </span>
                            ) : null}
                          </p>
                          {item.control_semantics ? (
                            <p className="mt-1 text-xs text-slate-400">{item.control_semantics}</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </section>

            {segmentSection ? (
              <details
                className="diagDetails rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-xs text-slate-400"
                data-testid="structure-abstentions"
              >
                <summary className="font-medium text-slate-300">诊断详情 · 数据边界</summary>
                <ul className="mt-2 list-inside list-disc space-y-1">
                  <li>五层结构分开呈现，法律控制与商业依赖不混同（coverage 契约随 /empire 返回）。</li>
                  <li>示例项逐条标注；真实结构事实（如 10-K Exhibit 21 子公司清单）经官方来源核实后替换。</li>
                  <li>板块层当前为 {zhLabel("status", segmentSection.data_status)}；暂无数据不代表真实为空。</li>
                </ul>
              </details>
            ) : null}
          </>
        ) : null}
      </main>
    </div>
  );
}

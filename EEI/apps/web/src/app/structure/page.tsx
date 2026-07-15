"use client";

import { AlertTriangle, Building2, Boxes, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { AnalysisContextBadge } from "../analysis-context-badge";
import {
  loadEntityEmpire,
  searchEntityIdByName,
  type EmpireRecord,
  type EmpireSyncResult,
  type StructureSection
} from "../structure-client";
import { useAnalysisContext } from "../use-analysis-context";
import { WorkspaceNavigationRail } from "../workspace-navigation";
import type { WorkspaceModuleId } from "../workspace-context";

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

  function handleNavigation(_target: string, moduleId: WorkspaceModuleId) {
    if (moduleId !== "group_structure" && moduleId !== "business_segments") {
      window.location.href = "/";
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail
        activeLens="business_segments"
        activeModuleId="group_structure"
        onLensTarget={handleNavigation}
        onSectionTarget={handleNavigation}
      />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid="group-structure-page">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              <Building2 className="h-6 w-6 text-sky-300" aria-hidden />
              集团结构 · 业务板块
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              法律集团 / 板块 / 品牌 / 产品 / 设施五层分离 — 控制语义逐条标注，绝不混同
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

        {loadState === "api_required" ? (
          <section
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100"
            data-testid="structure-api-required"
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
            data-testid="structure-load-error"
          >
            结构加载失败（{loadReason}）。
          </section>
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
                  {empire.data_mode === "synthetic_fixture" ? "fixture 演示" : empire.data_mode}
                </p>
                <p className="mt-1 text-xs text-amber-300/90">
                  {empire.fixture_notice ?? "已发布事实驱动"}
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
                      {section.item_count} 项 · {section.data_status}
                    </span>
                  </h2>
                  {section.items.length === 0 ? (
                    <p className="mt-2 text-sm text-slate-400">
                      {section.data_gap ??
                        "该层暂无已断言事实 — 缺席=无断言，候选经核验签核后自动出现。"}
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
                              {item.relationship.relationship_type}
                            </span>
                            <span className="text-xs text-slate-500">
                              {item.relationship.status}
                            </span>
                            {item.fixture_notice ? (
                              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-200">
                                fixture
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
              <section
                className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-xs text-slate-400"
                data-testid="structure-abstentions"
              >
                <p className="font-medium text-slate-300">诚实边界</p>
                <ul className="mt-2 list-inside list-disc space-y-1">
                  <li>五层结构分离呈现，法律控制与商业依赖绝不混同（coverage 契约随 /empire 返回）。</li>
                  <li>fixture 项逐条标注；真实结构事实（如 10-K Exhibit 21 子公司清单）走候选→双源→Owner 签核链后替换。</li>
                  <li>板块层当前为 {segmentSection.data_status}；缺席=无断言而非无板块。</li>
                </ul>
              </section>
            ) : null}
          </>
        ) : null}
      </main>
    </div>
  );
}

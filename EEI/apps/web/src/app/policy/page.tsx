"use client";

import { AlertTriangle, Download, Landmark, RefreshCw, ScrollText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AnalysisContextBadge } from "../analysis-context-badge";
import { zhLabel } from "../labels";
import {
  loadPolicyOverview,
  type PolicyOverviewRecord,
  type PolicyOverviewSyncResult
} from "../policy-client";
import { readProductionDataApiBaseUrl } from "../production-data-client";
import { useAnalysisContext } from "../use-analysis-context";
import { WorkspaceNavigationRail } from "../workspace-navigation";

type LoadState = "idle" | "loading" | "hydrated" | "error" | "api_required";

export default function PolicyEnvironmentPage() {
  const [result, setResult] = useState<PolicyOverviewSyncResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const { analysisContext, serverState } = useAnalysisContext();
  const [apiBaseUrl, setApiBaseUrl] = useState("");

  useEffect(() => {
    setApiBaseUrl(readProductionDataApiBaseUrl());
  }, []);

  useEffect(() => {
    void hydrate();
  }, []);

  async function hydrate() {
    setLoadState("loading");
    const next = await loadPolicyOverview();
    setResult(next);
    if (next.status === "hydrated") {
      setLoadState("hydrated");
    } else if (next.status === "api_required") {
      setLoadState("api_required");
    } else {
      setLoadState("error");
    }
  }

  const overview: PolicyOverviewRecord | null =
    result?.status === "hydrated" ? result.overview : null;

  const filingsTotal = useMemo(
    () =>
      overview
        ? overview.regulatory_filings.by_year.reduce(
            (sum, year) => sum + year.filings,
            0
          )
        : 0,
    [overview]
  );
  const yearSpan = useMemo(() => {
    const years = overview?.regulatory_filings.by_year ?? [];
    if (years.length === 0) {
      return null;
    }
    return { from: years[0].year, to: years[years.length - 1].year };
  }, [overview]);
  const maxYearFilings = useMemo(
    () =>
      Math.max(
        1,
        ...(overview?.regulatory_filings.by_year.map((year) => year.filings) ?? [1])
      ),
    [overview]
  );

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail activeModuleId="strategic_signals" />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid="policy-environment-page">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              <Landmark className="h-6 w-6 text-amber-300" aria-hidden />
              政策环境
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              政府关系 · 监管申报 · 出口管制暴露 — 全部来自官方申报与已核实关系
            </p>
          </div>
          <div className="flex items-center gap-2">
            {apiBaseUrl ? (
              <>
                <a
                  href={`${apiBaseUrl}/v1/export/relationships.csv`}
                  className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
                  data-testid="export-relationships"
                >
                  <Download className="h-4 w-4" aria-hidden />
                  导出已发布关系
                </a>
                <a
                  href={`${apiBaseUrl}/v1/export/regulatory-filings.csv`}
                  className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
                  data-testid="export-filings"
                >
                  <Download className="h-4 w-4" aria-hidden />
                  导出申报索引
                </a>
              </>
            ) : null}
            <button
              type="button"
              onClick={() => void hydrate()}
              className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
              data-testid="policy-refresh"
            >
              <RefreshCw className="h-4 w-4" aria-hidden />
              刷新
            </button>
          </div>
        </header>

        <AnalysisContextBadge analysisContext={analysisContext} serverState={serverState} />

        {loadState === "api_required" ? (
          <section
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm"
            data-testid="policy-api-required"
          >
            <p className="flex items-center gap-2 font-medium text-amber-200">
              <AlertTriangle className="h-4 w-4" aria-hidden />
              暂时连不上数据服务，请稍后重试。
            </p>
            <button
              type="button"
              onClick={() => void hydrate()}
              className="mt-2 rounded-md border border-amber-400/50 px-3 py-1 text-xs hover:bg-amber-500/20"
              data-testid="policy-api-required-retry"
            >
              重试
            </button>
          </section>
        ) : null}

        {loadState === "error" ? (
          <section
            className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-100"
            data-testid="policy-load-error"
          >
            <p className="font-medium">政策数据加载没有成功，请稍后重试。</p>
            <button
              type="button"
              onClick={() => void hydrate()}
              className="mt-2 rounded-md border border-rose-400/50 px-3 py-1 text-xs hover:bg-rose-500/20"
              data-testid="policy-load-error-retry"
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
              className="grid grid-cols-1 gap-4 md:grid-cols-3"
              data-testid="policy-first-screen-answer"
            >
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  已核实政府关系
                </p>
                <p className="mt-2 text-3xl font-semibold">
                  {overview.policy_relationships.length}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  政策族（授予 / 游说 / 受监管 / 出口管制）
                </p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  官方监管申报（SEC EDGAR）
                </p>
                <p className="mt-2 text-3xl font-semibold">{filingsTotal.toLocaleString()}</p>
                <p className="mt-1 text-xs text-slate-400">
                  {yearSpan ? `${yearSpan.from} → ${yearSpan.to} 连续覆盖` : "暂无申报数据"}
                </p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  政策暴露模型
                </p>
                <p className="mt-2 text-3xl font-semibold">
                  {overview.policy_models.filter((model) => model.has_scored_run).length}
                  <span className="text-base font-normal text-slate-400">
                    /{overview.policy_models.length} 已跑分
                  </span>
                </p>
                <p className="mt-1 text-xs text-slate-400">未跑分模型如实标注，不显示合成分</p>
              </div>
            </section>

            <section
              className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
              data-testid="policy-filing-timeline"
            >
              <h2 className="flex items-center gap-2 text-sm font-medium text-slate-300">
                <ScrollText className="h-4 w-4" aria-hidden />
                申报时间轴（逐年）
              </h2>
              <div className="mt-3 flex items-end gap-2">
                {overview.regulatory_filings.by_year.map((year) => (
                  <div key={year.year} className="flex flex-col items-center gap-1">
                    <div
                      className="w-8 rounded-t bg-amber-400/70"
                      style={{ height: `${Math.max(6, (year.filings / maxYearFilings) * 96)}px` }}
                      title={`${year.year}: ${year.filings}`}
                    />
                    <span className="text-[10px] text-slate-400">{year.year}</span>
                    <span className="text-[10px] text-slate-500">{year.filings}</span>
                  </div>
                ))}
                {overview.regulatory_filings.by_year.length === 0 ? (
                  <p className="text-sm text-slate-400" data-testid="policy-filings-empty">
                    尚无 sec_edgar 申报数据 — 运行 2016+ 回填后此处即有十年时间轴。
                  </p>
                ) : null}
              </div>
            </section>

            <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div
                className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
                data-testid="policy-relationships"
              >
                <h2 className="text-sm font-medium text-slate-300">政府关系明细</h2>
                {overview.policy_relationships.length === 0 ? (
                  <div className="mt-3 text-sm text-slate-400" data-testid="policy-relationships-empty">
                    <p className="font-medium text-slate-200">政府关系数据采集中</p>
                    <p className="mt-1">
                      官方监管申报已覆盖（见上方时间轴）；政府关系数据来自官方披露，
                      新数据核实后会自动出现在这里。
                    </p>
                    <p className="mt-2">
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
                    {overview.policy_relationships.map((relationship) => (
                      <li
                        key={relationship.id}
                        className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm"
                      >
                        <p>
                          <span className="font-medium">{relationship.subject_name}</span>
                          <span className="mx-2 text-amber-300">
                            —[{zhLabel("relationship_type", relationship.relationship_type)}]→
                          </span>
                          <span className="font-medium">{relationship.object_name}</span>
                        </p>
                        <p className="mt-1 text-xs text-slate-400">
                          状态 {zhLabel("status", relationship.status)}
                          {relationship.confidence !== null
                            ? ` · 置信 ${relationship.confidence.toFixed(2)}`
                            : ""}
                          {relationship.fixture_flag ? " · 示例数据" : ""}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div
                className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
                data-testid="policy-latest-filings"
              >
                <h2 className="text-sm font-medium text-slate-300">最新申报</h2>
                <ul className="mt-3 space-y-2">
                  {overview.regulatory_filings.latest.map((filing) => (
                    <li key={filing.id} className="text-sm">
                      <a
                        href={filing.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sky-300 hover:underline"
                      >
                        {filing.title}
                      </a>
                      <span className="ml-2 text-xs text-slate-500">
                        {filing.document_date?.slice(0, 10) ?? ""}
                      </span>
                    </li>
                  ))}
                  {overview.regulatory_filings.latest.length === 0 ? (
                    <li className="text-sm text-slate-400">暂无申报记录。</li>
                  ) : null}
                </ul>
              </div>
            </section>

            <details
              className="diagDetails rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-xs text-slate-400"
              data-testid="policy-abstentions"
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

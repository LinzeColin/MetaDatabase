"use client";

import { Activity, Landmark } from "lucide-react";
import { useEffect, useState } from "react";

import { FamilyOverviewPanel } from "../components/family-overview-panel";
import { PolicyOverviewPanel } from "../components/policy-overview-panel";
import { WorkspaceNavigationRail } from "../workspace-navigation";

// P2-10 旧路由收编（§A.2 入口 5 / §A.3）：外部信号合并「战略信号 + 政策环境」两 tab。
// 旧 /policy 重定向到 /signals?tab=policy；tab 状态与 URL ?tab= 双向同步。

type SignalsTab = "signals" | "policy";

function readInitialTab(): SignalsTab {
  if (typeof window === "undefined") {
    return "signals";
  }
  return new URLSearchParams(window.location.search).get("tab") === "policy"
    ? "policy"
    : "signals";
}

export default function StrategicSignalsPage() {
  const [tab, setTab] = useState<SignalsTab>("signals");

  // URL ?tab= → 初始 tab（含 /policy 重定向落地）；SSR 期不读 window，水合后回填。
  useEffect(() => {
    setTab(readInitialTab());
  }, []);

  function selectTab(next: SignalsTab) {
    setTab(next);
    const query = next === "policy" ? "?tab=policy" : "";
    window.history.replaceState(null, "", `/signals${query}`);
  }

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail activeModuleId="strategic_signals" />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid="strategic-signals-page">
        <header>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Activity className="h-6 w-6 text-orange-300" aria-hidden />
            外部信号
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            政策环境与战略动向 — 外部环境对公司的作用力，研究优先级辅助，非投资建议
          </p>
        </header>

        <div className="flex gap-1 border-b border-slate-800" role="tablist" data-testid="signals-tabs">
          <button
            aria-selected={tab === "signals"}
            className={`flex items-center gap-2 px-4 py-2 text-sm ${
              tab === "signals"
                ? "border-b-2 border-orange-300 text-slate-100"
                : "text-slate-400 hover:text-slate-200"
            }`}
            data-active={tab === "signals"}
            data-testid="signals-tab-signals"
            onClick={() => selectTab("signals")}
            role="tab"
            type="button"
          >
            <Activity className="h-4 w-4" aria-hidden />
            战略信号
          </button>
          <button
            aria-selected={tab === "policy"}
            className={`flex items-center gap-2 px-4 py-2 text-sm ${
              tab === "policy"
                ? "border-b-2 border-amber-300 text-slate-100"
                : "text-slate-400 hover:text-slate-200"
            }`}
            data-active={tab === "policy"}
            data-testid="signals-tab-policy"
            onClick={() => selectTab("policy")}
            role="tab"
            type="button"
          >
            <Landmark className="h-4 w-4" aria-hidden />
            政策环境
          </button>
        </div>

        {tab === "signals" ? (
          <FamilyOverviewPanel
            emptyCoverageNote="数据库当前已覆盖实体、关系与事件数据；外部信号采集器扩展中。"
            endpoint="/v1/signals/overview"
            testId="signals-overview"
            title="外部信号"
            renderExtra={(overview) =>
              overview.signal_models && overview.signal_models.length > 0 ? (
                <section
                  className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
                  data-testid="signal-models"
                >
                  <h2 className="text-sm font-medium text-slate-300">信号评分模型</h2>
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {overview.signal_models.map((model) => (
                      <li key={model.model_key} className="flex items-center gap-2">
                        <span>
                          {model.model_key}@{model.version}
                        </span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs ${
                            model.has_scored_run
                              ? "bg-emerald-500/20 text-emerald-200"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {model.has_scored_run ? "已跑分" : "已注册 · 未跑分"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : (
                <section
                  className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-sm text-slate-400"
                  data-testid="signal-models-empty"
                >
                  尚无信号评分模型跑分记录 — 模型注册在案，跑分后此处如实显示。
                </section>
              )
            }
          />
        ) : (
          <PolicyOverviewPanel />
        )}
      </main>
    </div>
  );
}

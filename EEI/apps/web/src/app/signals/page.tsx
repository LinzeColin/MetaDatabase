"use client";

import { Activity } from "lucide-react";

import { FamilyModulePage } from "../family-module-page";

export default function StrategicSignalsPage() {
  return (
    <FamilyModulePage
      moduleId="strategic_signals"
      endpoint="/v1/signals/overview"
      title="外部信号"
      subtitle="政策与战略动向 — 研究优先级辅助，非投资建议"
      icon={<Activity className="h-6 w-6 text-orange-300" aria-hidden />}
      testId="strategic-signals-page"
      emptyCoverageNote="数据库当前已覆盖实体、关系与事件数据；外部信号采集器扩展中。"
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
                  <span>{model.model_key}@{model.version}</span>
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
  );
}

"use client";

import { GitBranch } from "lucide-react";

import { FamilyModulePage } from "../family-module-page";

export default function MaTransactionsPage() {
  return (
    <FamilyModulePage
      moduleId="ma_transactions"
      endpoint="/v1/ma/overview"
      title="并购交易"
      subtitle="收购、合并、分拆与要约 — 交易断言与事件时间线，S7 事实层驱动"
      icon={<GitBranch className="h-6 w-6 text-violet-300" aria-hidden />}
      testId="ma-transactions-page"
      renderExtra={(overview) =>
        overview.events && overview.events.length > 0 ? (
          <section
            className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
            data-testid="ma-events"
          >
            <h2 className="text-sm font-medium text-slate-300">
              交易事件（{overview.events.length}）
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              {overview.events.map((event) => (
                <li key={event.id} className="rounded-md border border-slate-800 p-2">
                  {event.title}
                  <span className="ml-2 text-xs text-slate-500">
                    {event.event_type} · {event.announced_at?.slice(0, 10) ?? "未注明"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <section
            className="rounded-lg border border-slate-800/60 bg-slate-900/20 p-4 text-sm text-slate-400"
            data-testid="ma-events-empty"
          >
            暂无 M&amp;A 类型事件 — 事件时间线随交易事实发布批次充实。
          </section>
        )
      }
    />
  );
}

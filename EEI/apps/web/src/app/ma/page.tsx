"use client";

import { GitBranch } from "lucide-react";

import { FamilyModulePage } from "../family-module-page";

export default function MaTransactionsPage() {
  return (
    <FamilyModulePage
      moduleId="capital_network"
      endpoint="/v1/ma/overview"
      title="并购交易"
      subtitle="收购、合并、分拆与要约 — 每条记录可点开查官方来源"
      icon={<GitBranch className="h-6 w-6 text-violet-300" aria-hidden />}
      testId="ma-transactions-page"
      emptyCoverageNote="数据库当前已覆盖集团结构、控制关系与董监高数据；并购交易采集器扩展中。"
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
            暂无并购类事件。全部事件可在
            <a className="mx-1 underline" href="/capital">
              资本与事件
            </a>
            查看。
          </section>
        )
      }
    />
  );
}

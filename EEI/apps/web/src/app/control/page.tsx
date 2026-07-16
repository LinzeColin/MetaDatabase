"use client";

import { ShieldCheck } from "lucide-react";

import { FamilyModulePage } from "../family-module-page";

export default function ControlRelationshipsPage() {
  return (
    <FamilyModulePage
      moduleId="control_relationships"
      endpoint="/v1/control/overview"
      title="控制关系"
      subtitle="法律母子、董事会控制、投票权与受益所有 — 治理断言，绝不与商业依赖混同"
      icon={<ShieldCheck className="h-6 w-6 text-cyan-300" aria-hidden />}
      testId="control-relationships-page"
      renderExtra={(overview) => {
        const byType = (overview.summary.by_type ?? {}) as Record<string, number>;
        const entries = Object.entries(byType);
        return entries.length > 0 ? (
          <section
            className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
            data-testid="control-by-type"
          >
            <h2 className="text-sm font-medium text-slate-300">控制类型分布</h2>
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              {entries.map(([type, count]) => (
                <span
                  key={type}
                  className="rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1"
                >
                  {type} × {count}
                </span>
              ))}
            </div>
          </section>
        ) : null;
      }}
    />
  );
}

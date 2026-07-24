"use client";

import { type ReactNode } from "react";

import { FamilyOverviewPanel } from "./components/family-overview-panel";
import { type FamilyOverviewRecord } from "./family-module-client";
import { WorkspaceNavigationRail } from "./workspace-navigation";
import type { WorkspaceModuleId } from "./workspace-context";

type FamilyModulePageProps = {
  moduleId: WorkspaceModuleId;
  endpoint: "/v1/ma/overview" | "/v1/control/overview" | "/v1/signals/overview";
  title: string;
  subtitle: string;
  icon: ReactNode;
  testId: string;
  /** P0-4 空态三段式（§E.2 a 型）：本模块的「事实覆盖」句。 */
  emptyCoverageNote: string;
  renderExtra?: (overview: FamilyOverviewRecord) => ReactNode;
};

/**
 * 关系族视图整页外壳（S8PC）。P2-10 起主体渲染下沉到共享
 * components/family-overview-panel.tsx（与 /signals tab 复用同一套加载 /
 * 状态 / 文案），此处只保留导航 + 页头，避免两处重复。
 */
export function FamilyModulePage({
  moduleId,
  endpoint,
  title,
  subtitle,
  icon,
  testId,
  emptyCoverageNote,
  renderExtra
}: FamilyModulePageProps) {
  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <WorkspaceNavigationRail activeModuleId={moduleId} />
      <main className="flex-1 space-y-6 px-8 py-6" data-testid={testId}>
        <header>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            {icon}
            {title}
          </h1>
          <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
        </header>
        <FamilyOverviewPanel
          emptyCoverageNote={emptyCoverageNote}
          endpoint={endpoint}
          renderExtra={renderExtra}
          testId={`${testId}-body`}
          title={title}
        />
      </main>
    </div>
  );
}

"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { AnalysisContext } from "./analysis-contract";

export const WORKSPACE_CONTEXT_VERSION = "workspace-context-v1";
export const WORKSPACE_STATE_STORAGE_KEY = "eei.workspaceState.v1";
export const SAVED_VIEW_STORAGE_KEY = "eei.savedView.current.v1";

// P0-1 导航收敛（UX_SPEC_EEI v1.0 §A）：18 项 → 6 个一级入口。
// 每个入口首屏回答一个用户问题；数据弱区（供应链/信号）正常可点，
// 进去是「采集中」引导态。旧路由 /ma /control /policy 页面保留可直达
// （P2 做重定向），只是不再占一级导航——它们的归属入口见各自页面的
// activeModuleId（/ma→资本与事件、/control→集团与控制、/policy→外部信号）。
export type WorkspaceModuleId =
  | "business_map"
  | "group_structure"
  | "capital_network"
  | "supply_chain"
  | "strategic_signals"
  | "data_center";

// §A.4 导航渲染规则：只允许 route（点击=URL 变化）与 drawer（点击=抽屉
// 滑出，P2-9 上线）。section/planned/lens 死按钮形态全部废除。
export type WorkspaceControlKind = "route" | "drawer";

export type WorkspaceModuleDefinition = {
  id: WorkspaceModuleId;
  label: string;
  subtitle: string;
  controlKind: WorkspaceControlKind;
  routeState: "active" | "available";
  acceptanceIds: string[];
  href: string;
  apiEndpoints?: string[];
};

export type WorkspaceRuntimeState = {
  focusKey: string;
  selectedKey: string;
  path: string[];
  activeLens: string;
  semanticZoom: string;
  asOf: string;
  analysisContext: AnalysisContext;
};

export type WorkspaceContextValue = {
  contextVersion: typeof WORKSPACE_CONTEXT_VERSION;
  modules: readonly WorkspaceModuleDefinition[];
  runtimeState: WorkspaceRuntimeState;
  queryKeys: readonly string[];
  persistenceTargets: readonly string[];
  serverEndpoints: readonly string[];
  implementedRouteIds: WorkspaceModuleId[];
  realControlIds: WorkspaceModuleId[];
  disabledUnfinishedIds: WorkspaceModuleId[];
};

export const WORKSPACE_QUERY_KEYS = ["subject", "selected", "lens", "zoom", "asOf", "path"] as const;
export const WORKSPACE_PERSISTENCE_TARGETS = [
  "url",
  "sessionStorage",
  "localStorage"
] as const;

export const WORKSPACE_MODULES: readonly WorkspaceModuleDefinition[] = [
  {
    id: "business_map",
    label: "商业版图",
    subtitle: "这家公司的生态长什么样？",
    controlKind: "route",
    routeState: "active",
    href: "/",
    apiEndpoints: ["/v1/explore", "/v1/explore/reroot", "/v1/explore/expand", "/v1/entities"],
    acceptanceIds: ["A203", "A211"]
  },
  {
    id: "group_structure",
    label: "集团与控制",
    subtitle: "谁控制谁？董监高是谁？",
    controlKind: "route",
    routeState: "available",
    href: "/structure",
    apiEndpoints: ["/v1/entities/{entityId}/empire", "/v1/entities", "/v1/control/overview"],
    acceptanceIds: ["A202", "A211"]
  },
  {
    id: "capital_network",
    label: "资本与事件",
    subtitle: "最近发生了什么？涉及多少钱？",
    controlKind: "route",
    routeState: "available",
    href: "/capital",
    apiEndpoints: [
      "/v1/events",
      "/v1/events/amount-summary",
      "/v1/evidence/event/{eventId}",
      "/v1/ma/overview"
    ],
    acceptanceIds: ["A108", "A109", "A110", "A203", "A211"]
  },
  {
    id: "supply_chain",
    label: "供应链",
    subtitle: "上下游依赖是什么？",
    controlKind: "route",
    routeState: "available",
    href: "/supply-chain",
    apiEndpoints: ["/v1/supply-chain/overview", "/v1/explore", "/v1/explore/expand"],
    acceptanceIds: ["S8PBT02", "A203", "A211"]
  },
  {
    id: "strategic_signals",
    label: "外部信号",
    subtitle: "政策与战略动向有什么？",
    controlKind: "route",
    routeState: "available",
    href: "/signals",
    apiEndpoints: ["/v1/signals/overview", "/v1/policy/overview"],
    acceptanceIds: ["S8PCT02", "A111", "A202", "A206", "A211"]
  },
  {
    id: "data_center",
    label: "数据与来源",
    subtitle: "数据从哪来、多新、覆盖多少？",
    controlKind: "route",
    routeState: "available",
    href: "/objects-scope",
    apiEndpoints: [
      "/v1/catalogs/relationship",
      "/v1/catalogs/domain-object",
      "/health",
      "/v1/scoring/active-context"
    ],
    acceptanceIds: ["S8PDT01", "A172", "A174", "A211"]
  }
];

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function createWorkspaceContextValue(
  runtimeState: WorkspaceRuntimeState
): WorkspaceContextValue {
  return {
    contextVersion: WORKSPACE_CONTEXT_VERSION,
    modules: WORKSPACE_MODULES,
    runtimeState,
    queryKeys: WORKSPACE_QUERY_KEYS,
    persistenceTargets: WORKSPACE_PERSISTENCE_TARGETS,
    serverEndpoints: sortedUnique(
      WORKSPACE_MODULES.flatMap((module) => module.apiEndpoints ?? []).concat([
        "/v1/saved-views",
        "/v1/watchlists",
        "/v1/exploration-log",
        "/v1/changes",
        "/v1/scoring/active-context",
        "/v1/scoring/recompute"
      ])
    ),
    implementedRouteIds: WORKSPACE_MODULES.filter((module) => module.controlKind === "route").map(
      (module) => module.id
    ),
    realControlIds: WORKSPACE_MODULES.map((module) => module.id),
    // §A.4：导航不再存在 disabled/planned 项——数据弱区正常可点，
    // 进去是诚实引导态。该字段保留为空数组以维持 data-* 契约形状。
    disabledUnfinishedIds: []
  };
}

export function WorkspaceContextProvider({
  children,
  value
}: {
  children: ReactNode;
  value: WorkspaceContextValue;
}) {
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaceContext() {
  const value = useContext(WorkspaceContext);
  if (!value) {
    throw new Error("WorkspaceContextProvider is required");
  }
  return value;
}

export function getWorkspaceModule(moduleId: WorkspaceModuleId) {
  return WORKSPACE_MODULES.find((module) => module.id === moduleId);
}

export function WorkspaceContextContractMarker() {
  const context = useWorkspaceContext();
  return (
    <div
      hidden
      data-context-version={context.contextVersion}
      data-disabled-unfinished={context.disabledUnfinishedIds.join(",")}
      data-implemented-routes={context.implementedRouteIds.join(",")}
      data-module-count={context.modules.length}
      data-query-keys={context.queryKeys.join(",")}
      data-real-controls={context.realControlIds.join(",")}
      data-saved-view-storage-key={SAVED_VIEW_STORAGE_KEY}
      data-server-endpoints={context.serverEndpoints.join(",")}
      data-state-persistence={context.persistenceTargets.join(",")}
      data-testid="workspace-context-contract"
      data-workspace-state-storage-key={WORKSPACE_STATE_STORAGE_KEY}
    />
  );
}

function sortedUnique(values: string[]) {
  return [...new Set(values)].sort();
}

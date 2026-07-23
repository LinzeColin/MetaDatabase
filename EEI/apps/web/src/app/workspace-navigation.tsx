"use client";

import {
  Building2,
  CircleDollarSign,
  Database,
  Network,
  PackageSearch,
  Radar,
  UserRound
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { CommandSearch } from "./components/command-search";
import { WORKSPACE_MODULES, type WorkspaceModuleId } from "./workspace-context";

// P0-1 导航收敛（UX_SPEC_EEI v1.0 §A.4）：
// - 只渲染 route 型导航项——点击必有 URL 变化，禁止任何点击后无可见
//   变化的项（section 滚动按钮 / disabled 灰按钮形态已全部废除）。
// - 当前页高亮 = 左缘金色指示条 + 图标着色（globals.css .navItem.active）。
// P1-5 上线：顶部「搜索」位挂全局搜索 Cmd+K（<CommandSearch/> 自带触发钮 +
//   Portal 弹层，任意页可唤起）。「我的」抽屉仍为占位（P2-9 上线）。
type WorkspaceNavigationRailProps = {
  activeModuleId: WorkspaceModuleId;
};

const moduleIconById: Record<WorkspaceModuleId, LucideIcon> = {
  business_map: Network,
  group_structure: Building2,
  capital_network: CircleDollarSign,
  supply_chain: PackageSearch,
  strategic_signals: Radar,
  data_center: Database
};

export function WorkspaceNavigationRail({ activeModuleId }: WorkspaceNavigationRailProps) {
  return (
    <aside className="navRail" aria-label="主导航">
      <div className="brandMark" aria-label="商域图谱">
        <span className="brandGlyph">E</span>
        <span>
          <strong>商域图谱</strong>
          <small>EEI</small>
        </span>
      </div>
      <div className="railTools" aria-label="全局工具">
        <CommandSearch />
        <button
          aria-disabled="true"
          className="railTool"
          data-testid="my-drawer-placeholder"
          disabled
          title="「我的」（关注 · 保存视图 · 探索记录）下一批上线"
          type="button"
        >
          <UserRound size={16} strokeWidth={1.8} aria-hidden="true" />
          <span>我的</span>
        </button>
      </div>
      <nav aria-label="主导航" data-testid="primary-workspace-navigation">
        {WORKSPACE_MODULES.map((module) => {
          const Icon = moduleIconById[module.id];
          const active = module.id === activeModuleId;
          return (
            <a
              aria-current={active ? "page" : undefined}
              className={`navItem route${active ? " active" : ""}`}
              data-acceptance-ids={module.acceptanceIds.join(",")}
              data-api-endpoints={(module.apiEndpoints ?? []).join(",")}
              data-control-kind={module.controlKind}
              data-route-state={module.routeState}
              data-testid={`main-nav-${module.id}`}
              href={module.href}
              key={module.id}
              title={module.subtitle}
            >
              <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
              <span>{module.label}</span>
            </a>
          );
        })}
      </nav>
    </aside>
  );
}

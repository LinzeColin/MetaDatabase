"use client";

import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent
} from "react";
import {
  ArrowDown,
  ArrowUp,
  Boxes,
  ChevronLeft,
  Crosshair,
  FileSearch,
  GitBranch,
  Network,
  Route,
  Search,
  RotateCcw,
  Save,
  Star
} from "lucide-react";
import {
  ACTIVE_ANALYSIS_CONTEXT,
  ANALYSIS_PREVIEW_STORAGE_KEY,
  type AnalysisContext
} from "./analysis-contract";
import {
  EXPLORE_API_BASE_STORAGE_KEY,
  loadExploreGraph,
  type ExploreGraphRecord,
  type ExploreGraphRequest
} from "./explore-api-client";
import {
  MODEL_CONTEXT_API_BASE_STORAGE_KEY,
  activateModelProfile,
  createModelProfileDraft,
  listModelProfiles,
  loadActiveModelContext,
  requestScoreRecompute,
  rollbackModelProfile,
  type ActiveModelContextRecord,
  type ModelActivationResult,
  type ScoreRecomputeJobRecord,
  type ScoreRecomputeResult,
  type ScoringProfileRecord
} from "./model-activation-client";
import {
  PRODUCTION_DATA_API_BASE_STORAGE_KEY,
  loadCatalogInventory,
  loadEvidenceDetail,
  loadScoreExplanation,
  loadSourceFreshness,
  readProductionDataApiBaseUrl,
  type CatalogInventoryRecord,
  type EvidenceDetailRecord,
  type ScoreExplanationRecord,
  type SourceFreshnessRecord
} from "./production-data-client";
import {
  loadCloudEvidenceDetail,
  loadCloudPublicationFreshness,
  loadCloudScoreExplanation
} from "./cloud-data-client";
import { useAnalysisContext } from "./use-analysis-context";
import {
  SAVED_VIEW_API_BASE_STORAGE_KEY,
  SAVED_VIEW_WORKSPACE_KEY,
  restoreViewFromServer,
  saveViewToServer,
  type SavedViewServerRecord,
  type SavedViewSyncResult
} from "./saved-view-client";
import {
  createWorkspaceContextValue,
  SAVED_VIEW_STORAGE_KEY,
  WORKSPACE_STATE_STORAGE_KEY,
  WorkspaceContextContractMarker,
  WorkspaceContextProvider,
  type WorkspaceModuleId
} from "./workspace-context";
import { WorkspaceNavigationRail } from "./workspace-navigation";

type FocusKey =
  | "materials"
  | "equipment"
  | "foundry"
  | "nvidia"
  | "business"
  | "capital"
  | "policy"
  | "systems"
  | "cloud"
  | "datacenter"
  | "energy";

type NodeKey = FocusKey | "systemMakersGroup";

type LensKey =
  | "all"
  | "supply_chain"
  | "business_segments"
  | "capital_transactions"
  | "policy_risk";

type RelationshipLens = Exclude<LensKey, "all">;

type SemanticZoom = "L0" | "L1" | "L2" | "L3";

type TransitionState = "ready" | "loading" | "fallback";

type TimelineKey = "2026-06-01" | "2026-06-12" | "2026-06-19";

type WorkspaceLayerKey =
  | "group_structure"
  | "business_segments"
  | "supply_chain"
  | "capital_network"
  | "ma_transactions"
  | "control_relationships"
  | "policy_environment"
  | "strategic_signals";

type StructureKind = "legal_group" | "business_segment" | "brand" | "product" | "facility";

type WorkspaceState = {
  focusKey: FocusKey;
  selectedKey: NodeKey;
  path: FocusKey[];
  activeLens: LensKey;
  semanticZoom: SemanticZoom;
  asOf: TimelineKey;
};

type SavedViewRecord = WorkspaceState & {
  id: string;
  version: "saved-view-v1";
  workspaceKey: string;
  filters: string;
  layout: string;
  modelVersion: string;
  profileVersion: string;
  dataSnapshot: string;
  scoreSnapshot: string;
  notes: string;
  updatedAt: string;
  serverId?: string;
  serverVersion?: number;
  syncMode: "server" | "local_fallback";
  syncReason: string;
  serverEndpoint?: string;
};

type ModelContextStatus =
  | "local-active"
  | "loading-server-context"
  | "server-current"
  | "server-stale"
  | "activating"
  | "server-activated"
  | "server-refreshed"
  | "server-conflict"
  | "server-error"
  | "server-no-target";

type ModelDraftStatus = "idle" | "creating" | "created" | "server-error" | "local-preview";

type ProductionGraphStatus =
  | "local-fixture"
  | "loading-production-graph"
  | "server-hydrated"
  | "server-error";

type ProductionDataStatus =
  | "local-fixture"
  | "loading-production-data"
  | "server-hydrated"
  | "server-error";

type WorkspaceStateInput = {
  focusKey?: unknown;
  selectedKey?: unknown;
  path?: unknown;
  activeLens?: unknown;
  semanticZoom?: unknown;
  asOf?: unknown;
};

type Zone =
  | "upstream"
  | "focus"
  | "downstream"
  | "infrastructure"
  | "business"
  | "capital"
  | "policy";

// S12 光学：defs 渐变按 zone 枚举生成（玻璃球体 + 光晕各一）。
const EMPIRE_ZONES: readonly Zone[] = [
  "focus",
  "upstream",
  "downstream",
  "infrastructure",
  "business",
  "capital",
  "policy"
];

// 焦点节点的环绕粒子（视频样例：轨道点环，reduced-motion 时静止）。
// 坐标取整到 0.01：三角函数原始浮点在 SSR 与客户端的序列化位数不同，
// 会触发 hydration mismatch。
// S14 视频复刻批次2：金核绽放光芒 rays（样例视频 genesis 核语言）。等角
// 辐条从核向外放射，坐标确定性取整 SSR 安全；数量克制、纯 stroke 无滤镜守 A168。
const SUN_RAYS = Array.from({ length: 16 }, (_, index) => {
  const a = (index / 16) * Math.PI * 2;
  const inner = 46;
  const outer = index % 2 === 0 ? 122 : 96;
  return {
    x1: Math.round(380 + Math.cos(a) * inner),
    y1: Math.round(240 + Math.sin(a) * inner),
    x2: Math.round(380 + Math.cos(a) * outer),
    y2: Math.round(240 + Math.sin(a) * outer),
    long: index % 2 === 0
  };
});

// S14 视频复刻：稀疏 travelling 粒子（背景生命感）。位置/漂移向量确定性生成
// 并取整（SSR/client 序列化一致，避免 hydration mismatch）；数量克制守 A168。
const AMBIENT_PARTICLES = Array.from({ length: 14 }, (_, index) => {
  const a = (index / 14) * Math.PI * 2;
  const r = 90 + (index % 5) * 52;
  const dx = ((index % 3) - 1) * 9;
  const dy = -6 - (index % 4) * 4;
  return {
    x: Math.round(380 + Math.cos(a) * r * 0.9),
    y: Math.round(240 + Math.sin(a) * r * 0.55),
    r: index % 4 === 0 ? 1.8 : 1.1,
    dx,
    dy
  };
});

const FOCUS_ORBIT_DOTS = Array.from({ length: 12 }, (_, index) => {
  const angle = (index / 12) * Math.PI * 2;
  const radius = index % 2 === 0 ? 50 : 54;
  return {
    x: Math.round(Math.cos(angle) * radius * 100) / 100,
    y: Math.round(Math.sin(angle) * radius * 100) / 100
  };
});

// S12 第二批：机器状态码 → 自然中文。仅作用于人话摘要层的展示；
// 原始状态码全部保留在各面板〈诊断详情〉内（契约 testid 与断言不动）。
const STATUS_ZH: Record<string, string> = {
  "local-active": "本地模型运行中",
  "server-active": "云端模型运行中",
  idle: "待命",
  activating: "激活中",
  creating: "创建中",
  enqueueing: "入队中",
  enqueued: "已入队",
  ready: "就绪",
  "server-error": "云端接口不可用",
  http_404: "云端未提供该接口",
  http_409: "版本冲突",
  http_500: "云端服务异常",
  local_fallback: "已回退本地样例",
  "local-fixture": "本地样例",
  local: "本地",
  server: "云端",
  "server-hydrated": "云端数据已接入",
  api_base_missing: "未配置数据接口",
  candidate_id_missing: "缺少候选编号",
  object_id_missing: "缺少对象编号",
  "candidate-missing": "无候选评分",
  "server-conflict": "云端版本冲突",
  "local-saved": "已保存（本地）",
  "server-saved": "已保存（云端）",
  "local-restored": "已恢复（本地）",
  "server-restored": "已恢复（云端）",
  none: "无",
  preview: "预览中",
  active: "已激活"
};

function zhStatus(raw: string | null | undefined): string {
  if (!raw) {
    return "无";
  }
  return STATUS_ZH[raw] ?? raw;
}

type MapNode = {
  key: NodeKey;
  label: string;
  shortLabel: string;
  stage: string;
  role: string;
  x: number;
  y: number;
  zone: Zone;
  centerable: boolean;
  aggregateCount?: number;
  groupMembers?: string[];
};

type MapEdge = {
  from: NodeKey;
  to: NodeKey;
  label: string;
  stage: string;
  lens: RelationshipLens;
  fixtureNotice: string;
};

const ONLINE_DRAFT_PROFILE_WEIGHTS = {
  supply_chain_criticality: 0.3,
  strategic_dependency: 0.18,
  capital_momentum: 0.08,
  control_influence: 0.12,
  policy_exposure: 0.1,
  technology_dependency: 0.08,
  strategic_signal: 0.08,
  time_relevance: 0.06
};

type GraphRenderNode = {
  key: string;
  label: string;
  shortLabel: string;
  stage: string;
  role: string;
  x: number;
  y: number;
  zone: Zone;
  centerable: boolean;
  source: "fixture" | "server";
  localKey?: NodeKey;
  entityType?: string;
  fixtureNotice?: string | null;
  aggregateCount?: number;
  groupMembers?: string[];
};

type GraphRenderEdge = {
  id: string;
  from: string;
  to: string;
  label: string;
  stage: string;
  lens: RelationshipLens;
  fixtureNotice: string;
  evidenceCount: number;
  observedAt: string;
  source: "fixture" | "server";
};

type FocusScenario = {
  focus: FocusKey;
  heading: string;
  subtitle: string;
  nodes: MapNode[];
  edges: MapEdge[];
  nextCenters: FocusKey[];
};

type HomeSearchResult = {
  key: string;
  label: string;
  description: string;
  aliases: string[];
  target: FocusKey;
  objectType: "entity" | "industry" | "theme" | "facility";
};

type HomeIndustryEntry = {
  key: string;
  name: string;
  taxonomy: string;
  entityCount: number;
  recentChangeCount: number;
  target: FocusKey;
};

type HomeWatchItem = {
  key: FocusKey;
  label: string;
  unread: number;
  state: string;
  savedLens: LensKey;
  savedZoom: SemanticZoom;
  profile: string;
};

type HomeRecentEntry = {
  key: FocusKey;
  label: string;
  path: string;
};

type HomeChangeEntry = {
  key: string;
  label: string;
  severity: string;
  target: FocusKey;
};

const entityLabels: Record<NodeKey, string> = {
  materials: "Synthetic Specialty Materials Co.",
  equipment: "Synthetic Lithography Equipment Co.",
  foundry: "Synthetic Advanced Foundry",
  nvidia: "NVIDIA Corporation",
  business: "Synthetic Accelerated Computing Segment",
  capital: "Synthetic Capital Commitment",
  policy: "Synthetic Export Control Context",
  systems: "Synthetic Systems Integrator",
  cloud: "Synthetic Cloud Customer",
  datacenter: "Synthetic AI Data Center Campus",
  energy: "Synthetic Grid Utility",
  systemMakersGroup: "Synthetic System Makers Group"
};

const shortLabels: Record<NodeKey, string> = {
  materials: "Materials",
  equipment: "Equipment",
  foundry: "Foundry",
  nvidia: "NVIDIA",
  business: "Accel Compute",
  capital: "Capital",
  policy: "Policy Risk",
  systems: "Systems",
  cloud: "Cloud",
  datacenter: "Data Center",
  energy: "Energy",
  systemMakersGroup: "System Makers"
};

// A037 (S8PDT02): last-seen mark for the real change-feed unread count.
const WATCHLIST_LAST_SEEN_STORAGE_KEY = "eei.watchlist.lastSeen.v1";

const lensItems: { key: LensKey; label: string }[] = [
  { key: "all", label: "综合" },
  { key: "supply_chain", label: "供应链" },
  { key: "business_segments", label: "业务" },
  { key: "capital_transactions", label: "资本" },
  { key: "policy_risk", label: "政策" }
];

const workspaceLayerItems: {
  key: WorkspaceLayerKey;
  label: string;
  state: "active" | "available" | "stub";
}[] = [
  { key: "group_structure", label: "集团结构", state: "active" },
  { key: "business_segments", label: "业务板块", state: "active" },
  { key: "supply_chain", label: "供应链", state: "available" },
  { key: "capital_network", label: "资本网络", state: "available" },
  { key: "ma_transactions", label: "并购交易", state: "stub" },
  { key: "control_relationships", label: "控制关系", state: "stub" },
  { key: "policy_environment", label: "政策环境", state: "available" },
  { key: "strategic_signals", label: "战略信号", state: "stub" }
];

function lensForWorkspaceLayer(layer: WorkspaceLayerKey): LensKey | null {
  if (layer === "business_segments" || layer === "group_structure") {
    return "business_segments";
  }
  if (layer === "supply_chain") return "supply_chain";
  if (layer === "capital_network") return "capital_transactions";
  if (layer === "policy_environment") return "policy_risk";
  return null;
}

const structureRows: {
  kind: StructureKind;
  label: string;
  typeLabel: string;
  relationship: string;
  scope: "focus" | "direct" | "adjacent" | "missing";
  control: string;
}[] = [
  {
    kind: "legal_group",
    label: "NVIDIA Corporation",
    typeLabel: "legal_entity",
    relationship: "focus_entity",
    scope: "focus",
    control: "当前主体；不是母子控制声明"
  },
  {
    kind: "business_segment",
    label: "Accelerated Computing Segment (Synthetic)",
    typeLabel: "business_segment",
    relationship: "segment_of",
    scope: "direct",
    control: "业务映射；不是法律控制声明"
  },
  {
    kind: "brand",
    label: "No brand fixture loaded",
    typeLabel: "brand",
    relationship: "unknown",
    scope: "missing",
    control: "未知保留；不补零"
  },
  {
    kind: "product",
    label: "AI Accelerator Platform (Synthetic)",
    typeLabel: "product",
    relationship: "product_of",
    scope: "direct",
    control: "产品映射；不是法律控制声明"
  },
  {
    kind: "facility",
    label: "Synthetic AI Data Center Campus",
    typeLabel: "facility",
    relationship: "operates_facility via CoreWeave",
    scope: "adjacent",
    control: "相邻生态设施；不表示 NVIDIA 拥有或运营"
  }
];

const semanticZoomItems: { key: SemanticZoom; label: string; title: string }[] = [
  { key: "L0", label: "L0", title: "Overview with grouped dense nodes" },
  { key: "L1", label: "L1", title: "Relationship labels" },
  { key: "L2", label: "L2", title: "Evidence and fixture state" },
  { key: "L3", label: "L3", title: "Detailed node role labels" }
];

const timelineItems: {
  key: TimelineKey;
  label: string;
  change: string;
  overlay: string;
}[] = [
  {
    key: "2026-06-01",
    label: "基线",
    change: "供应商与客户关系基线图",
    overlay: "该快照无重大变化标注"
  },
  {
    key: "2026-06-12",
    label: "对比",
    change: "封装排队与客户需求路径发生变化",
    overlay: "变化标注：封装产能与需求压力"
  },
  {
    key: "2026-06-19",
    label: "当前",
    change: "当前样例快照（MVP 验证用）",
    overlay: "以已发布快照为准"
  }
];

const SAVED_VIEW_VERSION = "saved-view-v1";
const WORKSPACE_LAYOUT_GRAMMAR =
  "upstream-left focus-center downstream-right capital-top policy-bottom";
const DEFAULT_GRAPH_BUDGET = { max_nodes: 42, max_edges: 64, expand_nodes: 12 } as const;

const focusEntityIds: Record<FocusKey, string> = {
  materials: "00000000-0000-4000-8000-000000000023",
  equipment: "00000000-0000-4000-8000-000000000022",
  foundry: "00000000-0000-4000-8000-000000000021",
  nvidia: "00000000-0000-4000-8000-000000000006",
  business: "00000000-0000-4000-8000-000000000026",
  capital: "00000000-0000-4000-8000-000000000006",
  policy: "00000000-0000-4000-8000-000000000019",
  systems: "00000000-0000-4000-8000-000000000029",
  cloud: "00000000-0000-4000-8000-000000000030",
  datacenter: "00000000-0000-4000-8000-000000000024",
  energy: "00000000-0000-4000-8000-000000000025"
};

// EEI-F01/F02/F03：云生产模式（构建期决定）。生产面只呈现已发布数据，
// 任何模块拿不到云数据就亮诚实空态/错误态，绝不回退合成样例。
// 只认「云发布面」构建标（build_cloud_frontend.sh 注入）：本地 dev/CI
// 与 live 全栈套件（连本地 FastAPI，也设 API 基址）都保持样例工作台语义。
const CLOUD_MODE =
  process.env.NEXT_PUBLIC_EEI_SURFACE === "cloud-publication" &&
  Boolean(process.env.NEXT_PUBLIC_EEI_API_BASE_URL?.trim());
// 已发布面上的 NVIDIA 实体（与本地样例共用确定性 UUID）。
const SERVER_DEFAULT_FOCUS = {
  id: focusEntityIds.nvidia,
  label: "NVIDIA Corporation"
} as const;
const UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
// EEI-F07：构建指纹进 DOM，生产可与 /v1/meta/build、x-eei-build 头对账。
const BUILD_SHA = process.env.NEXT_PUBLIC_EEI_BUILD_SHA?.trim() || "dev";

type ServerEntityRecord = {
  id: string;
  canonical_name: string;
  entity_type: string;
  status: string;
};

type CloudChangeRow = {
  id: string;
  change_type: string;
  created_at: string | null;
  new_value: {
    relationship_type?: string;
    subject_name?: string;
    object_name?: string;
  } | null;
};

const systemMakersGroupMembers = [
  "Synthetic Systems Integrator",
  "Synthetic Rack Manufacturer",
  "Synthetic ODM Partner",
  "Synthetic Thermal Platform Co.",
  "Synthetic Network Appliance Co.",
  "Synthetic Storage Platform Co.",
  "Synthetic Regional Integrator",
  "Synthetic AI Factory Builder"
];

const stageRows = [
  { id: "SC-02", name: "Materials", side: "upstream" },
  { id: "SC-04", name: "Equipment", side: "upstream" },
  { id: "SC-05", name: "Design / IP", side: "focus" },
  { id: "SC-06", name: "Manufacturing", side: "upstream" },
  { id: "SC-08", name: "Advanced packaging", side: "focus" },
  { id: "SC-09", name: "System", side: "downstream" },
  { id: "SC-10", name: "Data center / Energy", side: "downstream" },
  { id: "SC-12", name: "Customer", side: "downstream" }
] as const;

const focusIndustryByKey: Record<FocusKey, { key: string; label: string }> = {
  materials: { key: "semiconductors", label: "Semiconductors" },
  equipment: { key: "semiconductors", label: "Semiconductors" },
  foundry: { key: "semiconductors", label: "Semiconductors" },
  nvidia: { key: "semiconductors", label: "Semiconductors" },
  business: { key: "semiconductors", label: "Semiconductors" },
  capital: { key: "semiconductors", label: "Semiconductors" },
  policy: { key: "semiconductors", label: "Semiconductors" },
  systems: { key: "ai-cloud", label: "AI cloud infrastructure" },
  cloud: { key: "ai-cloud", label: "AI cloud infrastructure" },
  datacenter: { key: "energy", label: "Power and data-center energy" },
  energy: { key: "energy", label: "Power and data-center energy" }
};

const homeSearchResults: HomeSearchResult[] = [
  {
    key: "nvidia",
    label: "NVIDIA Corporation",
    description: "legal_entity / AI infrastructure focus",
    aliases: ["nvda", "nvidia", "gpu", "accelerated computing"],
    target: "nvidia",
    objectType: "entity"
  },
  {
    key: "tsmc",
    label: "TSMC representative foundry",
    description: "entity / semiconductor manufacturing",
    aliases: ["tsmc", "taiwan semiconductor", "foundry", "晶圆制造"],
    target: "foundry",
    objectType: "entity"
  },
  {
    key: "semiconductors",
    label: "Semiconductors",
    description: "industry / taxonomy v4.2",
    aliases: ["semiconductor", "semiconductors", "半导体", "industry"],
    target: "nvidia",
    objectType: "industry"
  },
  {
    key: "ai-cloud",
    label: "AI cloud demand",
    description: "theme / customer and infrastructure demand",
    aliases: ["ai cloud", "cloud", "demand", "customer"],
    target: "cloud",
    objectType: "theme"
  }
];

const homeIndustries: HomeIndustryEntry[] = [
  {
    key: "semiconductors",
    name: "Semiconductors",
    taxonomy: "taxonomy-v4.2",
    entityCount: 8,
    recentChangeCount: 2,
    target: "nvidia"
  },
  {
    key: "ai-cloud",
    name: "AI cloud infrastructure",
    taxonomy: "taxonomy-v4.2",
    entityCount: 6,
    recentChangeCount: 1,
    target: "cloud"
  },
  {
    key: "energy",
    name: "Power and data-center energy",
    taxonomy: "taxonomy-v4.2",
    entityCount: 3,
    recentChangeCount: 1,
    target: "energy"
  }
];

const homeWatchItems: HomeWatchItem[] = [
  {
    key: "nvidia",
    label: "NVIDIA",
    unread: 3,
    state: "last viewed",
    savedLens: "supply_chain",
    savedZoom: "L2",
    profile: "Balanced v2"
  },
  {
    key: "foundry",
    label: "Advanced Foundry",
    unread: 2,
    state: "upstream",
    savedLens: "supply_chain",
    savedZoom: "L2",
    profile: "Balanced v2"
  },
  {
    key: "equipment",
    label: "Lithography Equipment",
    unread: 1,
    state: "supplier",
    savedLens: "supply_chain",
    savedZoom: "L1",
    profile: "Balanced v2"
  },
  {
    key: "materials",
    label: "Specialty Materials",
    unread: 1,
    state: "materials",
    savedLens: "supply_chain",
    savedZoom: "L1",
    profile: "Balanced v2"
  },
  {
    key: "cloud",
    label: "Cloud Customer",
    unread: 2,
    state: "downstream",
    savedLens: "supply_chain",
    savedZoom: "L2",
    profile: "Balanced v2"
  }
];

const homeRecentExplorations: HomeRecentEntry[] = [
  { key: "nvidia", label: "NVIDIA", path: "NVIDIA" },
  { key: "foundry", label: "Advanced Foundry", path: "NVIDIA -> Foundry" },
  { key: "equipment", label: "Lithography Equipment", path: "NVIDIA -> Foundry -> Equipment" }
];

const homeChanges: HomeChangeEntry[] = [
  { key: "capital", label: "Capital/control signal refreshed", severity: "material", target: "capital" },
  { key: "policy", label: "Policy-risk context updated", severity: "watch", target: "policy" },
  { key: "cloud", label: "Customer-demand path changed", severity: "watch", target: "cloud" }
];

const homeFreshness = {
  status: "synthetic_fixture",
  sourceCode: "synthetic_workspace",
  lastAttemptAt: null,
  lastSuccessAt: null,
  lastFailureAt: null,
  latestDocumentDate: ACTIVE_ANALYSIS_CONTEXT.defaultAsOf,
  latestReportPeriodEnd: ACTIVE_ANALYSIS_CONTEXT.defaultAsOf,
  sourceCount: 1,
  sourceDocumentCount: 3,
  coverage: ACTIVE_ANALYSIS_CONTEXT.dataSnapshot
};

function freshnessValue(value: string | null | undefined) {
  return value || "none";
}

// 可见文本层：空值显示「无」；data-* 契约属性保持 "none"（live 套件断言）。
function freshnessText(value: string | null | undefined) {
  return value || "无";
}

const homeModelStatus = {
  profile: ACTIVE_ANALYSIS_CONTEXT.profileLabel,
  latestCalibration: "scheduled",
  cadenceDays: 14,
  nextScheduledFor: "2026-07-03"
};

const baseEdges: MapEdge[] = [
  {
    from: "materials",
    to: "foundry",
    label: "material provider to",
    stage: "SC-02 -> SC-06",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  },
  {
    from: "equipment",
    to: "foundry",
    label: "equipment provider to",
    stage: "SC-04 -> SC-06",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  },
  {
    from: "foundry",
    to: "nvidia",
    label: "wafer foundry for",
    stage: "SC-06 -> SC-08",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  },
  {
    from: "nvidia",
    to: "systems",
    label: "licenses IP to",
    stage: "SC-05 -> SC-09",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  },
  {
    from: "systems",
    to: "cloud",
    label: "system integrator for",
    stage: "SC-09 -> SC-12",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  },
  {
    from: "cloud",
    to: "nvidia",
    label: "customer of",
    stage: "SC-12 -> SC-08",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  },
  {
    from: "energy",
    to: "datacenter",
    label: "energy provider to",
    stage: "SC-10 -> SC-10",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  },
  {
    from: "datacenter",
    to: "cloud",
    label: "infrastructure supports",
    stage: "SC-10 -> SC-12",
    lens: "supply_chain",
    fixtureNotice: "Synthetic fixture for interaction and data-model tests."
  }
];

const nvidiaContextEdges: MapEdge[] = [
  {
    from: "nvidia",
    to: "business",
    label: "operates business segment",
    stage: "Business -> Focus",
    lens: "business_segments",
    fixtureNotice: "Synthetic fixture for business-segment visual coverage."
  },
  {
    from: "capital",
    to: "nvidia",
    label: "capital and control signal for",
    stage: "Capital/control -> Focus",
    lens: "capital_transactions",
    fixtureNotice: "Synthetic fixture for capital/control visual coverage."
  },
  {
    from: "policy",
    to: "nvidia",
    label: "policy risk constrains",
    stage: "Policy/risk -> Focus",
    lens: "policy_risk",
    fixtureNotice: "Synthetic fixture for policy/risk visual coverage."
  }
];

const overviewAggregateEdges: MapEdge[] = [
  {
    from: "nvidia",
    to: "systemMakersGroup",
    label: "aggregates system makers",
    stage: "SC-05 -> SC-09",
    lens: "supply_chain",
    fixtureNotice: "Synthetic grouped node for anti-hairball semantic zoom."
  },
  {
    from: "systemMakersGroup",
    to: "cloud",
    label: "group supplies systems to",
    stage: "SC-09 -> SC-12",
    lens: "supply_chain",
    fixtureNotice: "Synthetic grouped node for anti-hairball semantic zoom."
  }
];

const scenarios: Record<FocusKey, FocusScenario> = {
  nvidia: {
    focus: "nvidia",
    heading: "NVIDIA",
    subtitle: "Semiconductor and AI infrastructure ecosystem",
    nodes: [
      node("materials", 82, 336, "upstream", "SC-02 Materials", "specialty materials"),
      node("equipment", 92, 122, "upstream", "SC-04 Equipment", "lithography equipment"),
      node("foundry", 252, 224, "upstream", "SC-06 Manufacturing", "advanced foundry"),
      node("nvidia", 394, 246, "focus", "SC-05 Design / IP", "current focus"),
      node("business", 610, 76, "business", "Business segment", "accelerated computing segment"),
      node("capital", 390, 72, "capital", "Capital / control", "capital and control signal"),
      node("policy", 396, 418, "policy", "Policy / risk", "export-control context"),
      node("systems", 536, 176, "downstream", "SC-09 System", "system integration"),
      node("systemMakersGroup", 548, 180, "downstream", "SC-09 System", "aggregated system makers", {
        aggregateCount: systemMakersGroupMembers.length,
        centerable: false,
        groupMembers: systemMakersGroupMembers
      }),
      node("cloud", 650, 244, "downstream", "SC-12 Customer", "cloud customer"),
      node("datacenter", 562, 358, "infrastructure", "SC-10 Data center", "AI data center"),
      node("energy", 666, 390, "infrastructure", "SC-10 Energy", "grid utility")
    ],
    edges: [...baseEdges, ...nvidiaContextEdges],
    nextCenters: ["foundry", "systems", "cloud"]
  },
  business: {
    focus: "business",
    heading: "Synthetic Accelerated Computing Segment",
    subtitle: "Centered business-segment view with company and customer demand retained",
    nodes: [
      node("nvidia", 150, 246, "upstream", "SC-05 Design / IP", "parent platform"),
      node("business", 360, 238, "focus", "Business segment", "current focus"),
      node("systems", 540, 180, "downstream", "SC-09 System", "system route to market"),
      node("cloud", 650, 250, "downstream", "SC-12 Customer", "cloud demand")
    ],
    edges: [nvidiaContextEdges[0], baseEdges[3], baseEdges[4]],
    nextCenters: ["nvidia", "systems", "cloud"]
  },
  capital: {
    focus: "capital",
    heading: "Synthetic Capital Commitment",
    subtitle: "Centered capital/control view with company exposure retained",
    nodes: [
      node("capital", 350, 210, "focus", "Capital / control", "current focus"),
      node("nvidia", 560, 244, "downstream", "SC-05 Design / IP", "company exposure"),
      node("business", 660, 154, "downstream", "Business segment", "capital allocation target")
    ],
    edges: [nvidiaContextEdges[1], nvidiaContextEdges[0]],
    nextCenters: ["nvidia", "business"]
  },
  policy: {
    focus: "policy",
    heading: "Synthetic Export Control Context",
    subtitle: "Centered policy/risk view with constrained company and downstream demand retained",
    nodes: [
      node("policy", 340, 252, "focus", "Policy / risk", "current focus"),
      node("nvidia", 540, 238, "downstream", "SC-05 Design / IP", "constrained company"),
      node("cloud", 660, 300, "downstream", "SC-12 Customer", "demand exposure")
    ],
    edges: [nvidiaContextEdges[2], baseEdges[5]],
    nextCenters: ["nvidia", "cloud"]
  },
  foundry: {
    focus: "foundry",
    heading: "Synthetic Advanced Foundry",
    subtitle: "Centered manufacturing view with inherited supply-chain lens",
    nodes: [
      node("materials", 92, 318, "upstream", "SC-02 Materials", "specialty materials"),
      node("equipment", 104, 142, "upstream", "SC-04 Equipment", "lithography equipment"),
      node("foundry", 360, 238, "focus", "SC-06 Manufacturing", "current focus"),
      node("nvidia", 560, 238, "downstream", "SC-05 / SC-08", "design and packaging"),
      node("systems", 660, 158, "downstream", "SC-09 System", "system integration")
    ],
    edges: baseEdges.slice(0, 4),
    nextCenters: ["equipment", "materials", "nvidia"]
  },
  equipment: {
    focus: "equipment",
    heading: "Synthetic Lithography Equipment Co.",
    subtitle: "Centered equipment view with manufacturing dependency retained",
    nodes: [
      node("materials", 118, 314, "upstream", "SC-02 Materials", "material dependency"),
      node("equipment", 332, 210, "focus", "SC-04 Equipment", "current focus"),
      node("foundry", 522, 238, "downstream", "SC-06 Manufacturing", "advanced foundry"),
      node("nvidia", 650, 266, "downstream", "SC-08 Packaging", "downstream customer")
    ],
    edges: baseEdges.slice(0, 3),
    nextCenters: ["materials", "foundry", "nvidia"]
  },
  materials: {
    focus: "materials",
    heading: "Synthetic Specialty Materials Co.",
    subtitle: "Centered materials view with downstream manufacturing chain",
    nodes: [
      node("materials", 328, 240, "focus", "SC-02 Materials", "current focus"),
      node("equipment", 158, 150, "upstream", "SC-04 Equipment", "adjacent equipment"),
      node("foundry", 510, 236, "downstream", "SC-06 Manufacturing", "advanced foundry"),
      node("nvidia", 650, 284, "downstream", "SC-08 Packaging", "downstream customer")
    ],
    edges: baseEdges.slice(0, 3),
    nextCenters: ["foundry", "nvidia"]
  },
  systems: {
    focus: "systems",
    heading: "Synthetic Systems Integrator",
    subtitle: "Centered system view across customer and infrastructure stages",
    nodes: [
      node("nvidia", 138, 240, "upstream", "SC-05 Design / IP", "upstream IP"),
      node("systems", 356, 236, "focus", "SC-09 System", "current focus"),
      node("cloud", 552, 236, "downstream", "SC-12 Customer", "cloud customer"),
      node("datacenter", 566, 358, "infrastructure", "SC-10 Data center", "AI data center"),
      node("energy", 672, 392, "infrastructure", "SC-10 Energy", "grid utility")
    ],
    edges: baseEdges.slice(3),
    nextCenters: ["cloud", "nvidia"]
  },
  cloud: {
    focus: "cloud",
    heading: "Synthetic Cloud Customer",
    subtitle: "Centered customer view with system and data-center dependencies",
    nodes: [
      node("nvidia", 112, 236, "upstream", "SC-08 Packaging", "upstream platform"),
      node("systems", 260, 204, "upstream", "SC-09 System", "system integrator"),
      node("cloud", 448, 238, "focus", "SC-12 Customer", "current focus"),
      node("datacenter", 560, 350, "infrastructure", "SC-10 Data center", "AI data center"),
      node("energy", 664, 390, "infrastructure", "SC-10 Energy", "grid utility")
    ],
    edges: baseEdges.slice(3),
    nextCenters: ["systems", "datacenter", "nvidia"]
  },
  datacenter: {
    focus: "datacenter",
    heading: "Synthetic AI Data Center Campus",
    subtitle: "Centered infrastructure view",
    nodes: [
      node("energy", 132, 310, "upstream", "SC-10 Energy", "grid utility"),
      node("datacenter", 360, 240, "focus", "SC-10 Data center", "current focus"),
      node("cloud", 560, 220, "downstream", "SC-12 Customer", "cloud customer")
    ],
    edges: baseEdges.slice(6),
    nextCenters: ["energy", "cloud"]
  },
  energy: {
    focus: "energy",
    heading: "Synthetic Grid Utility",
    subtitle: "Centered energy view",
    nodes: [
      node("energy", 340, 244, "focus", "SC-10 Energy", "current focus"),
      node("datacenter", 548, 244, "downstream", "SC-10 Data center", "AI data center"),
      node("cloud", 666, 190, "downstream", "SC-12 Customer", "cloud customer")
    ],
    edges: baseEdges.slice(6),
    nextCenters: ["datacenter", "cloud"]
  }
};

function node(
  key: NodeKey,
  x: number,
  y: number,
  zone: Zone,
  stage: string,
  role: string,
  options: Partial<Pick<MapNode, "aggregateCount" | "centerable" | "groupMembers">> = {}
): MapNode {
  return {
    key,
    label: entityLabels[key],
    shortLabel: shortLabels[key],
    stage,
    role,
    x,
    y,
    zone,
    centerable: options.centerable ?? key !== "systemMakersGroup",
    aggregateCount: options.aggregateCount,
    groupMembers: options.groupMembers
  };
}

function fixtureRenderNode(mapNode: MapNode): GraphRenderNode {
  return {
    ...mapNode,
    key: mapNode.key,
    source: "fixture",
    localKey: mapNode.key,
    fixtureNotice: "Synthetic fixture visual projection."
  };
}

function fixtureRenderEdge(edge: MapEdge, observedAt: string): GraphRenderEdge {
  return {
    id: `${edge.from}-${edge.to}`,
    from: edge.from,
    to: edge.to,
    label: edge.label,
    stage: edge.stage,
    lens: edge.lens,
    fixtureNotice: edge.fixtureNotice,
    evidenceCount: 1,
    observedAt,
    source: "fixture"
  };
}

function serverGraphRenderNodes(
  graph: ExploreGraphRecord | null,
  focusEntityId: string
): GraphRenderNode[] | null {
  if (!graph || graph.nodes.length === 0) return null;
  const familyByNode = new Map<string, string>();
  for (const edge of graph.edges) {
    if (!familyByNode.has(edge.subject_id)) familyByNode.set(edge.subject_id, edge.relationship_family);
    if (!familyByNode.has(edge.object_id)) familyByNode.set(edge.object_id, edge.relationship_family);
  }
  const nodesByLane = new Map<Zone, ExploreGraphRecord["nodes"]>();
  for (const item of graph.nodes) {
    const zone = serverNodeZone(item.id, focusEntityId, item.entity_type, familyByNode.get(item.id));
    const next = nodesByLane.get(zone) ?? [];
    next.push(item);
    nodesByLane.set(zone, next);
  }
  return graph.nodes.map((item) => {
    const zone = serverNodeZone(item.id, focusEntityId, item.entity_type, familyByNode.get(item.id));
    const lane = nodesByLane.get(zone) ?? [item];
    const laneIndex = lane.findIndex((candidate) => candidate.id === item.id);
    const laneCount = lane.length;
    const position = serverNodePosition(zone, Math.max(laneIndex, 0), Math.max(laneCount, 1));
    const localKey = serverLocalKeyForEntityId(item.id);
    return {
      key: item.id,
      label: item.canonical_name,
      shortLabel: shortServerLabel(item.canonical_name),
      stage: serverNodeStage(item.entity_type, familyByNode.get(item.id)),
      role: item.id === focusEntityId ? "server focus entity" : "server returned entity",
      x: position.x,
      y: position.y,
      zone,
      // 云模式：每个已发布实体都可显式换中心（EEI-F03 的「以被选实体
      // 本身为中心」）；本地模式沿用样例键映射规则。
      centerable: CLOUD_MODE ? true : Boolean(localKey),
      source: "server",
      localKey,
      entityType: item.entity_type,
      fixtureNotice: item.fixture_notice
    };
  });
}

function serverGraphRenderEdges(
  graph: ExploreGraphRecord | null,
  renderedNodes: GraphRenderNode[],
  observedAt: string
): GraphRenderEdge[] | null {
  if (!graph) return null;
  const nodeKeys = new Set(renderedNodes.map((item) => item.key));
  const edges = graph.edges
    .filter((edge) => nodeKeys.has(edge.subject_id) && nodeKeys.has(edge.object_id))
    .map((edge) => ({
      id: edge.id,
      from: edge.subject_id,
      to: edge.object_id,
      label: relationshipLabel(edge.relationship_type),
      stage: edge.relationship_family.replaceAll("_", " "),
      lens: lensForRelationshipFamily(edge.relationship_family),
      fixtureNotice: edge.fixture_notice ?? `${edge.status ?? "relationship"}; evidence=${edge.evidence_count ?? 0}`,
      evidenceCount: edge.evidence_count ?? 0,
      observedAt,
      source: "server" as const
    }));
  return edges.length > 0 ? edges : null;
}

function serverNodeZone(
  id: string,
  focusEntityId: string,
  entityType: string | undefined,
  family: string | undefined
): Zone {
  if (id === focusEntityId) return "focus";
  if (entityType === "facility" || entityType === "asset") return "infrastructure";
  if (family === "capital_financing" || family === "ownership_control" || family === "mergers_acquisitions") {
    return "capital";
  }
  if (family === "government_policy") return "policy";
  if (family === "corporate_structure" || family === "commercial_dependency") return "business";
  return "upstream";
}

// S9PAT02: solar-system layout. The sun sits at the canvas center; each zone
// occupies an angular sector on one of the orbital belts. Multiple nodes in
// a zone fan out around the sector center with a stable per-index spread.
const EMPIRE_CENTER = { x: 380, y: 240 } as const;
const EMPIRE_ORBITS: Record<Exclude<Zone, "focus">, { radius: number; centerDeg: number }> = {
  business: { radius: 118, centerDeg: 270 },
  capital: { radius: 118, centerDeg: 200 },
  upstream: { radius: 182, centerDeg: 160 },
  downstream: { radius: 182, centerDeg: 10 },
  policy: { radius: 182, centerDeg: 95 },
  infrastructure: { radius: 182, centerDeg: 320 }
};

function layoutEmpireOrbits<T extends { key: string; zone: Zone; x: number; y: number }>(
  nodes: T[]
): (T & { orbitRadius?: number })[] {
  const zoneGroups = new Map<Zone, T[]>();
  for (const node of nodes) {
    zoneGroups.set(node.zone, [...(zoneGroups.get(node.zone) ?? []), node]);
  }
  const placed = new Map<string, { x: number; y: number; orbitRadius?: number }>();
  for (const [zone, members] of zoneGroups) {
    if (zone === "focus") {
      for (const member of members) {
        placed.set(member.key, { x: EMPIRE_CENTER.x, y: EMPIRE_CENTER.y });
      }
      continue;
    }
    const orbit = EMPIRE_ORBITS[zone];
    const spreadDeg = Math.min(30, Math.max(16, 110 / Math.max(members.length - 1, 1)));
    members.forEach((member, index) => {
      const offset = (index - (members.length - 1) / 2) * spreadDeg;
      const angle = ((orbit.centerDeg + offset) * Math.PI) / 180;
      // Dense sectors stagger alternate members onto a slightly wider ring so
      // labels stop stacking; the belt reading stays intact.
      const radius = orbit.radius + (members.length > 3 && index % 2 === 1 ? 34 : 0);
      placed.set(member.key, {
        x: Math.round(EMPIRE_CENTER.x + radius * Math.cos(angle)),
        y: Math.round(EMPIRE_CENTER.y + radius * Math.sin(angle)),
        orbitRadius: orbit.radius
      });
    });
  }
  return nodes.map((node) => ({ ...node, ...placed.get(node.key) }));
}

function serverNodePosition(zone: Zone, index: number, count: number) {
  const clampedCount = Math.max(count, 1);
  const y = 126 + ((index + 1) * 228) / (clampedCount + 1);
  const positions: Record<Zone, { x: number; y?: number }> = {
    upstream: { x: 132 },
    focus: { x: 380, y: 240 },
    downstream: { x: 628 },
    infrastructure: { x: 628 },
    business: { x: 380, y: 92 + index * 56 },
    capital: { x: 258, y: 78 + index * 54 },
    policy: { x: 500, y: 382 - index * 52 }
  };
  const base = positions[zone];
  return { x: base.x, y: base.y ?? y };
}

// S14 视频复刻：连接器弯曲曲线。控制点=中点沿边法向偏移 curveK×边长，
// 方向 sign 稳定（调用方按 from<to 传），坐标全取整→SSR/client 序列化一致。
function curvedEdgePath(sx: number, sy: number, tx: number, ty: number, sign: boolean): string {
  const dx = tx - sx;
  const dy = ty - sy;
  const len = Math.hypot(dx, dy) || 1;
  const k = len * 0.13 * (sign ? 1 : -1);
  const cx = Math.round((sx + tx) / 2 + (-dy / len) * k);
  const cy = Math.round((sy + ty) / 2 + (dx / len) * k);
  return `M${sx} ${sy} Q${cx} ${cy} ${tx} ${ty}`;
}

function serverNodeStage(entityType: string | undefined, family: string | undefined) {
  const entity = entityType ? entityType.replaceAll("_", " ") : "entity";
  const relationship = family ? family.replaceAll("_", " ") : "relationship";
  return `${entity} / ${relationship}`;
}

function relationshipLabel(value: string) {
  return value.replaceAll("_", " ");
}

function shortServerLabel(value: string) {
  const words = value.split(/\s+/).filter(Boolean);
  const compact = words.slice(0, 3).join(" ");
  return compact.length > 22 ? `${compact.slice(0, 19)}...` : compact;
}

function lensForRelationshipFamily(family: string): RelationshipLens {
  if (["capital_financing", "ownership_control", "mergers_acquisitions"].includes(family)) {
    return "capital_transactions";
  }
  if (family === "government_policy") return "policy_risk";
  if (["corporate_structure", "commercial_dependency"].includes(family)) {
    return "business_segments";
  }
  return "supply_chain";
}

function serverLocalKeyForEntityId(entityId: string): FocusKey | undefined {
  return (Object.entries(focusEntityIds) as [FocusKey, string][]).find(([, id]) => id === entityId)?.[0];
}

// 云模式：搜索命中但不在当前图内的已发布实体，也要能作为「当前选择」
// 呈现（选择≠换中心，EEI-F03）。
function serverEntityRenderNode(entity: ServerEntityRecord): GraphRenderNode {
  return {
    key: entity.id,
    label: entity.canonical_name,
    shortLabel: shortServerLabel(entity.canonical_name),
    stage: (entity.entity_type || "entity").replaceAll("_", " "),
    role: "已发布实体（不在当前图内）",
    x: 0,
    y: 0,
    zone: "upstream",
    centerable: true,
    source: "server",
    entityType: entity.entity_type,
    fixtureNotice: null
  };
}

function cloudPlaceholderRenderNode(label?: string): GraphRenderNode {
  return {
    key: "",
    label: label ?? "等待云端图谱",
    shortLabel: label ?? "…",
    stage: "已发布面",
    role: "云端图谱载入中或不可用",
    x: 0,
    y: 0,
    zone: "focus",
    centerable: false,
    source: "server",
    fixtureNotice: null
  };
}

const focusKeySet = new Set<FocusKey>(Object.keys(scenarios) as FocusKey[]);
const nodeKeySet = new Set<NodeKey>(Object.keys(entityLabels) as NodeKey[]);
const lensKeySet = new Set<LensKey>(lensItems.map((item) => item.key));
const semanticZoomSet = new Set<SemanticZoom>(semanticZoomItems.map((item) => item.key));
const timelineKeySet = new Set<TimelineKey>(timelineItems.map((item) => item.key));

const defaultWorkspaceState: WorkspaceState = {
  focusKey: "nvidia",
  selectedKey: "nvidia",
  path: ["nvidia"],
  activeLens: "all",
  semanticZoom: "L1",
  asOf: ACTIVE_ANALYSIS_CONTEXT.defaultAsOf
};

function isFocusKey(value: string | null | undefined): value is FocusKey {
  return Boolean(value && focusKeySet.has(value as FocusKey));
}

function isNodeKey(value: string | null | undefined): value is NodeKey {
  return Boolean(value && nodeKeySet.has(value as NodeKey));
}

function isLensKey(value: string | null | undefined): value is LensKey {
  return Boolean(value && lensKeySet.has(value as LensKey));
}

function isSemanticZoom(value: string | null | undefined): value is SemanticZoom {
  return Boolean(value && semanticZoomSet.has(value as SemanticZoom));
}

function isTimelineKey(value: string | null | undefined): value is TimelineKey {
  return Boolean(value && timelineKeySet.has(value as TimelineKey));
}

function stringField(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function normalizeWorkspaceState(input: WorkspaceStateInput): WorkspaceState {
  const focusKeyValue = stringField(input.focusKey);
  const selectedKeyValue = stringField(input.selectedKey);
  const activeLensValue = stringField(input.activeLens);
  const semanticZoomValue = stringField(input.semanticZoom);
  const asOfValue = stringField(input.asOf);
  const parsedPath = Array.isArray(input.path)
    ? input.path.filter((item): item is string => typeof item === "string").filter(isFocusKey)
    : [];
  const focusKey = isFocusKey(focusKeyValue) ? focusKeyValue : defaultWorkspaceState.focusKey;
  const selectedCandidate = isNodeKey(selectedKeyValue) ? selectedKeyValue : focusKey;
  const selectedKey = scenarios[focusKey].nodes.some((item) => item.key === selectedCandidate)
    ? selectedCandidate
    : focusKey;
  const path = parsedPath.length ? parsedPath : defaultWorkspaceState.path;
  const normalizedPath = path[path.length - 1] === focusKey ? path : [...path, focusKey];

  return {
    focusKey,
    selectedKey,
    path: normalizedPath,
    activeLens: isLensKey(activeLensValue) ? activeLensValue : defaultWorkspaceState.activeLens,
    semanticZoom: isSemanticZoom(semanticZoomValue)
      ? semanticZoomValue
      : defaultWorkspaceState.semanticZoom,
    asOf: isTimelineKey(asOfValue) ? asOfValue : defaultWorkspaceState.asOf
  };
}

function readWorkspaceStateFromParams(params: URLSearchParams): WorkspaceState | null {
  const hasState = ["subject", "selected", "lens", "zoom", "asOf", "path"].some((key) =>
    params.has(key)
  );
  if (!hasState) return null;

  return normalizeWorkspaceState({
    focusKey: params.get("subject") ?? undefined,
    selectedKey: params.get("selected") ?? undefined,
    path: (params.get("path") ?? "").split("."),
    activeLens: params.get("lens") ?? undefined,
    semanticZoom: params.get("zoom") ?? undefined,
    asOf: params.get("asOf") ?? undefined
  });
}

function readWorkspaceStatePayload(rawValue: string | null): WorkspaceState | null {
  if (!rawValue) return null;
  try {
    const parsed = JSON.parse(rawValue) as Partial<WorkspaceState>;
    return normalizeWorkspaceState(parsed);
  } catch {
    return null;
  }
}

function writeWorkspaceStateParams(params: URLSearchParams, state: WorkspaceState) {
  params.set("subject", state.focusKey);
  params.set("selected", state.selectedKey);
  params.set("lens", state.activeLens);
  params.set("zoom", state.semanticZoom);
  params.set("asOf", state.asOf);
  params.set("filters", state.activeLens);
  params.set("path", state.path.join("."));
}

function createExploreGraphRequest(
  state: WorkspaceState,
  scoringProfileVersionId?: string | null,
  serverFocusEntityId?: string | null
): ExploreGraphRequest {
  return {
    focus: {
      object_type: "entity",
      // 云模式下焦点是真实已发布实体 id（可指向图上任意实体），
      // as_of 交给发布面（一次发布一个原子快照），不再送样例日期。
      object_id: serverFocusEntityId ?? focusEntityIds[state.focusKey]
    },
    active_layers: activeLayersForLens(state.activeLens),
    direction: directionForLens(state.activeLens),
    hops: hopsForSemanticZoom(state.semanticZoom),
    as_of: serverFocusEntityId ? null : `${state.asOf}T00:00:00Z`,
    scoring_profile_version_id: scoringProfileVersionId ?? null,
    filters: {
      visual_lens: state.activeLens,
      semantic_zoom: state.semanticZoom,
      ui_path: state.path,
      selected_key: state.selectedKey
    },
    budget: { ...DEFAULT_GRAPH_BUDGET }
  };
}

function activeLayersForLens(lens: LensKey) {
  switch (lens) {
    case "supply_chain":
      return ["supply_chain_operations", "technology_data_ip"];
    case "business_segments":
      return ["business_segments", "commercial_dependency", "technology_data_ip"];
    case "capital_transactions":
      return ["capital_control"];
    case "policy_risk":
      return ["policy_regulatory"];
    case "all":
    default:
      return ["all"];
  }
}

function directionForLens(lens: LensKey): ExploreGraphRequest["direction"] {
  if (lens === "capital_transactions" || lens === "policy_risk") return "upstream";
  return "both";
}

function hopsForSemanticZoom(zoom: SemanticZoom) {
  return zoom === "L2" || zoom === "L3" ? 2 : 1;
}

function createSavedView(
  state: WorkspaceState,
  analysisContext: AnalysisContext = ACTIVE_ANALYSIS_CONTEXT
): SavedViewRecord {
  const normalized = normalizeWorkspaceState(state);
  return {
    ...normalized,
    id: `sv-${normalized.focusKey}-${normalized.activeLens}-${normalized.semanticZoom}-${normalized.asOf}`,
    version: SAVED_VIEW_VERSION,
    workspaceKey: SAVED_VIEW_WORKSPACE_KEY,
    filters: normalized.activeLens,
    layout: WORKSPACE_LAYOUT_GRAMMAR,
    modelVersion: analysisContext.modelVersion,
    profileVersion: analysisContext.profileVersion,
    dataSnapshot: analysisContext.dataSnapshot,
    scoreSnapshot: analysisContext.scoreSnapshot,
    notes: `${entityLabels[normalized.focusKey]} / ${normalized.activeLens} / ${normalized.asOf}`,
    updatedAt: ACTIVE_ANALYSIS_CONTEXT.defaultAsOf,
    syncMode: "local_fallback",
    syncReason: "not_synced"
  };
}

function readSavedViewPayload(rawValue: string | null): SavedViewRecord | null {
  if (!rawValue) return null;
  try {
    const parsed = JSON.parse(rawValue) as Partial<SavedViewRecord>;
    if (parsed.version !== SAVED_VIEW_VERSION) return null;
    const base = createSavedView(normalizeWorkspaceState(parsed));
    return {
      ...base,
      id: parsed.id ?? base.id,
      workspaceKey: parsed.workspaceKey ?? SAVED_VIEW_WORKSPACE_KEY,
      filters: parsed.filters ?? base.filters,
      layout: parsed.layout ?? base.layout,
      modelVersion: parsed.modelVersion ?? base.modelVersion,
      profileVersion: parsed.profileVersion ?? base.profileVersion,
      dataSnapshot: parsed.dataSnapshot ?? base.dataSnapshot,
      scoreSnapshot: parsed.scoreSnapshot ?? base.scoreSnapshot,
      notes: parsed.notes ?? base.notes,
      updatedAt: parsed.updatedAt ?? ACTIVE_ANALYSIS_CONTEXT.defaultAsOf,
      serverId: stringField(parsed.serverId),
      serverVersion:
        typeof parsed.serverVersion === "number" && Number.isFinite(parsed.serverVersion)
          ? parsed.serverVersion
          : undefined,
      syncMode: parsed.syncMode === "server" ? "server" : "local_fallback",
      syncReason: parsed.syncReason ?? "local_record",
      serverEndpoint: stringField(parsed.serverEndpoint)
    };
  } catch {
    return null;
  }
}

function createSavedViewServerState(savedViewRecord: SavedViewRecord): Record<string, unknown> {
  return {
    local_id: savedViewRecord.id,
    focus_key: savedViewRecord.focusKey,
    selected_key: savedViewRecord.selectedKey,
    path: savedViewRecord.path,
    visual_lens: savedViewRecord.activeLens,
    semantic_zoom: savedViewRecord.semanticZoom,
    as_of: savedViewRecord.asOf,
    filters: savedViewRecord.filters,
    layout: savedViewRecord.layout,
    model_version: savedViewRecord.modelVersion,
    profile_version: savedViewRecord.profileVersion,
    data_snapshot: savedViewRecord.dataSnapshot,
    score_snapshot: savedViewRecord.scoreSnapshot,
    notes: savedViewRecord.notes
  };
}

function createSavedViewMetadata(savedViewRecord: SavedViewRecord): Record<string, unknown> {
  return {
    source: "eei-web",
    workspace_key: savedViewRecord.workspaceKey,
    local_id: savedViewRecord.id,
    model_version: savedViewRecord.modelVersion,
    profile_version: savedViewRecord.profileVersion,
    data_snapshot: savedViewRecord.dataSnapshot,
    score_snapshot: savedViewRecord.scoreSnapshot
  };
}

function workspaceStateFromServerState(state: Record<string, unknown>): WorkspaceState {
  const rawPath = state.path;
  const path =
    Array.isArray(rawPath) || typeof rawPath === "string"
      ? Array.isArray(rawPath)
        ? rawPath
        : rawPath.split(".")
      : undefined;
  return normalizeWorkspaceState({
    focusKey: state.focus_key ?? state.focusKey,
    selectedKey: state.selected_key ?? state.selectedKey,
    path,
    activeLens: state.visual_lens ?? state.activeLens,
    semanticZoom: state.semantic_zoom ?? state.semanticZoom,
    asOf: state.as_of ?? state.asOf
  });
}

function savedViewFromServerRecord(
  record: SavedViewServerRecord,
  endpoint: string,
  analysisContext: AnalysisContext
): SavedViewRecord {
  const serverState = record.state;
  const base = createSavedView(workspaceStateFromServerState(serverState), analysisContext);
  return {
    ...base,
    id: stringField(serverState.local_id) ?? base.id,
    workspaceKey: record.workspace_key,
    filters: stringField(serverState.filters) ?? base.filters,
    layout: stringField(serverState.layout) ?? base.layout,
    modelVersion: stringField(serverState.model_version) ?? base.modelVersion,
    profileVersion: stringField(serverState.profile_version) ?? base.profileVersion,
    dataSnapshot: stringField(serverState.data_snapshot) ?? base.dataSnapshot,
    scoreSnapshot: stringField(serverState.score_snapshot) ?? base.scoreSnapshot,
    notes: stringField(serverState.notes) ?? record.name ?? base.notes,
    updatedAt: record.updated_at ?? base.updatedAt,
    serverId: record.id,
    serverVersion: record.current_version,
    syncMode: "server",
    syncReason: "ok",
    serverEndpoint: endpoint
  };
}

function analysisContextFromActiveModelContext(
  record: ActiveModelContextRecord,
  fallback: AnalysisContext
): AnalysisContext {
  return {
    ...fallback,
    modelVersion: record.model_version,
    profileVersion: record.profile_version,
    profileLabel: record.profile_version,
    dataSnapshot: record.active_data_snapshot_key ?? fallback.dataSnapshot,
    scoreSnapshot: record.active_scoring_run_id ?? fallback.scoreSnapshot
  };
}

function isFailedServerSyncResult(
  result: SavedViewSyncResult
): result is Extract<SavedViewSyncResult, { mode: "server"; status: "conflict" | "error" }> {
  return result.mode === "server" && (result.status === "conflict" || result.status === "error");
}

function isFailedModelActivationResult(
  result: ModelActivationResult
): result is Extract<ModelActivationResult, { mode: "server"; status: "conflict" | "error" }> {
  return result.mode === "server" && (result.status === "conflict" || result.status === "error");
}

function isFailedScoreRecomputeResult(
  result: ScoreRecomputeResult
): result is Extract<ScoreRecomputeResult, { mode: "server"; status: "conflict" | "error" }> {
  return result.mode === "server" && (result.status === "conflict" || result.status === "error");
}

export default function Home() {
  const { analysisContext, applyPreview, applyServerContext, clearPreview, isPreviewActive } =
    useAnalysisContext();
  const [focusKey, setFocusKey] = useState<FocusKey>("nvidia");
  const [selectedKey, setSelectedKey] = useState<NodeKey>("nvidia");
  const [path, setPath] = useState<FocusKey[]>(["nvidia"]);
  const [activeLens, setActiveLens] = useState<LensKey>("all");
  const [semanticZoom, setSemanticZoom] = useState<SemanticZoom>("L1");
  const [asOf, setAsOf] = useState<TimelineKey>(ACTIVE_ANALYSIS_CONTEXT.defaultAsOf);
  const [transitionState, setTransitionState] = useState<TransitionState>("ready");
  const [groupListOpen, setGroupListOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [savedView, setSavedView] = useState<SavedViewRecord>(() =>
    createSavedView(defaultWorkspaceState)
  );
  const [savedViewStatus, setSavedViewStatus] = useState("ready");
  const [modelContextStatus, setModelContextStatus] =
    useState<ModelContextStatus>("local-active");
  const [productionGraphStatus, setProductionGraphStatus] =
    useState<ProductionGraphStatus>("local-fixture");
  const [productionGraphSyncMode, setProductionGraphSyncMode] = useState<
    "server" | "local_fallback"
  >("local_fallback");
  const [productionGraphSyncReason, setProductionGraphSyncReason] = useState("not_synced");
  const [productionGraphEndpoint, setProductionGraphEndpoint] = useState("");
  const [productionGraph, setProductionGraph] = useState<ExploreGraphRecord | null>(null);
  const [productionCatalogStatus, setProductionCatalogStatus] =
    useState<ProductionDataStatus>("local-fixture");
  const [productionCatalogSyncMode, setProductionCatalogSyncMode] = useState<
    "server" | "local_fallback"
  >("local_fallback");
  const [productionCatalogSyncReason, setProductionCatalogSyncReason] = useState("not_synced");
  const [productionCatalogEndpoint, setProductionCatalogEndpoint] = useState("");
  const [productionCatalogInventory, setProductionCatalogInventory] =
    useState<CatalogInventoryRecord | null>(null);
  const [productionScoreStatus, setProductionScoreStatus] =
    useState<ProductionDataStatus>("local-fixture");
  const [productionScoreSyncMode, setProductionScoreSyncMode] = useState<
    "server" | "local_fallback"
  >("local_fallback");
  const [productionScoreSyncReason, setProductionScoreSyncReason] = useState("not_synced");
  const [productionScoreEndpoint, setProductionScoreEndpoint] = useState("");
  const [productionScoreTargetId, setProductionScoreTargetId] = useState("");
  const [productionScoreExplanation, setProductionScoreExplanation] =
    useState<ScoreExplanationRecord | null>(null);
  const [productionEvidenceStatus, setProductionEvidenceStatus] =
    useState<ProductionDataStatus>("local-fixture");
  const [productionEvidenceSyncMode, setProductionEvidenceSyncMode] = useState<
    "server" | "local_fallback"
  >("local_fallback");
  const [productionEvidenceSyncReason, setProductionEvidenceSyncReason] =
    useState("not_synced");
  const [productionEvidenceEndpoint, setProductionEvidenceEndpoint] = useState("");
  const [productionEvidenceDetail, setProductionEvidenceDetail] =
    useState<EvidenceDetailRecord | null>(null);
  const [productionFreshnessStatus, setProductionFreshnessStatus] =
    useState<ProductionDataStatus>("local-fixture");
  const [productionFreshnessSyncMode, setProductionFreshnessSyncMode] = useState<
    "server" | "local_fallback"
  >("local_fallback");
  const [productionFreshnessSyncReason, setProductionFreshnessSyncReason] =
    useState("not_synced");
  const [productionFreshnessEndpoint, setProductionFreshnessEndpoint] = useState("");
  const [productionFreshness, setProductionFreshness] =
    useState<SourceFreshnessRecord | null>(null);
  const [selectedProductionNodeKey, setSelectedProductionNodeKey] = useState("");
  const [modelContextSyncMode, setModelContextSyncMode] = useState<"server" | "local_fallback">(
    "local_fallback"
  );
  const [modelContextSyncReason, setModelContextSyncReason] = useState("not_synced");
  const [serverModelContext, setServerModelContext] = useState<ActiveModelContextRecord | null>(
    null
  );
  const [modelContextEndpoint, setModelContextEndpoint] = useState("");
  const [candidateProfile, setCandidateProfile] = useState<ScoringProfileRecord | null>(null);
  const [draftProfile, setDraftProfile] = useState<ScoringProfileRecord | null>(null);
  const [modelDraftStatus, setModelDraftStatus] = useState<ModelDraftStatus>("idle");
  const [modelDraftReason, setModelDraftReason] = useState("not_created");
  const [modelDraftEndpoint, setModelDraftEndpoint] = useState("");
  const [modelDraftWeightSum, setModelDraftWeightSum] = useState(0);
  const [rollbackProfile, setRollbackProfile] = useState<ScoringProfileRecord | null>(null);
  // A037 semantics (S8PDT02): unread = real /v1/changes rows since the
  // stored last-seen mark; null keeps the labeled fixture fallback.
  const [serverUnreadChanges, setServerUnreadChanges] = useState<number | null>(null);
  // 云模式状态：真实焦点实体 / 面包屑 / 实体搜索 / 变化流 / 图外选中实体。
  const [serverFocusEntityId, setServerFocusEntityId] = useState<string>(
    SERVER_DEFAULT_FOCUS.id
  );
  const [serverPath, setServerPath] = useState<{ id: string; label: string }[]>([
    { ...SERVER_DEFAULT_FOCUS }
  ]);
  const [serverSearchResults, setServerSearchResults] = useState<ServerEntityRecord[]>([]);
  const [serverChangeRows, setServerChangeRows] = useState<CloudChangeRow[]>([]);
  const [selectedServerEntity, setSelectedServerEntity] =
    useState<ServerEntityRecord | null>(null);

  useEffect(() => {
    const apiBaseUrl = readProductionDataApiBaseUrl();
    if (!apiBaseUrl) {
      return;
    }
    const lastSeen = window.localStorage.getItem(WATCHLIST_LAST_SEEN_STORAGE_KEY);
    const query = lastSeen ? `?since=${encodeURIComponent(lastSeen)}` : "";
    void window
      .fetch(`${apiBaseUrl}/v1/changes${query}`)
      .then(async (response) => {
        const payload = (await response.json().catch(() => null)) as unknown;
        if (response.ok && Array.isArray(payload)) {
          setServerUnreadChanges(payload.length);
          setServerChangeRows(payload as CloudChangeRow[]);
        }
      })
      .catch(() => {
        // Fixture fallback stays labeled; no fake server counts.
      });
  }, []);

  // 云模式实体搜索：/v1/entities 实查（防抖），本地样例列表不再出现在生产。
  useEffect(() => {
    if (!CLOUD_MODE) return;
    const apiBaseUrl = readProductionDataApiBaseUrl();
    if (!apiBaseUrl) return;
    const query = searchQuery.trim();
    if (!query) {
      setServerSearchResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void window
        .fetch(`${apiBaseUrl}/v1/entities?q=${encodeURIComponent(query)}`, {
          cache: "no-store"
        })
        .then(async (response) => {
          const payload = (await response.json().catch(() => null)) as {
            entities?: ServerEntityRecord[];
          } | null;
          if (response.ok && Array.isArray(payload?.entities)) {
            setServerSearchResults(payload.entities);
          }
        })
        .catch(() => {
          // 搜索失败保持上一批结果；不虚构条目。
        });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);
  const [previousModelRefreshToken, setPreviousModelRefreshToken] = useState("");
  const [scoreRecomputeStatus, setScoreRecomputeStatus] = useState<
    "idle" | "enqueueing" | "server-conflict" | "server-error" | ScoreRecomputeJobRecord["status"]
  >("idle");
  const [scoreRecomputeReason, setScoreRecomputeReason] = useState("not_requested");
  const [scoreRecomputeEndpoint, setScoreRecomputeEndpoint] = useState("");
  const [scoreRecomputeJob, setScoreRecomputeJob] = useState<ScoreRecomputeJobRecord | null>(null);
  const [pinnedNodeKeys, setPinnedNodeKeys] = useState<NodeKey[]>([]);
  const [comparisonNodeKeys, setComparisonNodeKeys] = useState<NodeKey[]>([]);
  const [watchlistNodeKeys, setWatchlistNodeKeys] = useState<NodeKey[]>([]);
  const [tableLensFilter, setTableLensFilter] = useState<LensKey>("all");
  const [nodeActionStatus, setNodeActionStatus] = useState("ready");
  const [navActionStatus, setNavActionStatus] = useState("ready");
  const [stateReady, setStateReady] = useState(false);
  const restoringHistoryState = useRef(false);
  const hasWrittenHistoryState = useRef(false);
  const hydratedProductionGraphKey = useRef("");
  const scenario = scenarios[focusKey];
  const workspaceState = useMemo<WorkspaceState>(
    () => ({ focusKey, selectedKey, path, activeLens, semanticZoom, asOf }),
    [activeLens, asOf, focusKey, path, selectedKey, semanticZoom]
  );
  const productionGraphRequest = useMemo(
    () =>
      createExploreGraphRequest(
        workspaceState,
        serverModelContext?.active_scoring_profile_version_id,
        CLOUD_MODE ? serverFocusEntityId : null
      ),
    [serverFocusEntityId, serverModelContext?.active_scoring_profile_version_id, workspaceState]
  );
  const productionGraphRequestKey = useMemo(
    () =>
      JSON.stringify({
        focus: productionGraphRequest.focus.object_id,
        layers: productionGraphRequest.active_layers,
        as_of: productionGraphRequest.as_of,
        scoring_profile_version_id: productionGraphRequest.scoring_profile_version_id,
        visual_lens: productionGraphRequest.filters.visual_lens,
        semantic_zoom: productionGraphRequest.filters.semantic_zoom,
        selected_key: productionGraphRequest.filters.selected_key,
        budget: productionGraphRequest.budget
      }),
    [productionGraphRequest]
  );
  const workspaceContextValue = useMemo(
    () =>
      createWorkspaceContextValue({
        ...workspaceState,
        analysisContext
      }),
    [analysisContext, workspaceState]
  );
  const currentTimeline = timelineItems.find((item) => item.key === asOf) ?? timelineItems[2];
  const nodeByKey = useMemo(
    () => new Map(scenario.nodes.map((item) => [item.key, item])),
    [scenario.nodes]
  );
  const displayNodes = useMemo(() => {
    if (focusKey !== "nvidia" || semanticZoom !== "L0") {
      return scenario.nodes.filter((item) => item.key !== "systemMakersGroup");
    }
    return scenario.nodes.filter(
      (item) => !["systems", "datacenter", "energy"].includes(item.key)
    );
  }, [focusKey, scenario.nodes, semanticZoom]);
  const displayNodeByKey = useMemo(
    () => new Map(displayNodes.map((item) => [item.key, item])),
    [displayNodes]
  );
  const displayEdges = useMemo(() => {
    if (focusKey !== "nvidia" || semanticZoom !== "L0") {
      return scenario.edges;
    }
    const groupedKeys = new Set<NodeKey>(["systems", "datacenter", "energy"]);
    return [
      ...scenario.edges.filter((edge) => !groupedKeys.has(edge.from) && !groupedKeys.has(edge.to)),
      ...overviewAggregateEdges
    ];
  }, [focusKey, scenario.edges, semanticZoom]);
  const fixtureGraphNodes = useMemo(() => displayNodes.map(fixtureRenderNode), [displayNodes]);
  const fixtureGraphEdges = useMemo(
    () => displayEdges.map((edge) => fixtureRenderEdge(edge, asOf)),
    [asOf, displayEdges]
  );
  const serverGraphNodes = useMemo(
    () => serverGraphRenderNodes(productionGraph, productionGraphRequest.focus.object_id),
    [productionGraph, productionGraphRequest.focus.object_id]
  );
  const serverGraphEdges = useMemo(
    () => serverGraphRenderEdges(productionGraph, serverGraphNodes ?? [], asOf),
    [asOf, productionGraph, serverGraphNodes]
  );
  const isServerGraphRendered =
    productionGraphStatus === "server-hydrated" &&
    Boolean(serverGraphNodes?.length) &&
    Boolean(serverGraphEdges?.length);
  // EEI-F01/F02：生产（云模式）零样例回退——云图不可用时画布给诚实状态，
  // 绝不把合成节点画成生产事实；样例图只存在于本地模式。
  const baseGraphViewNodes = isServerGraphRendered
    ? serverGraphNodes!
    : CLOUD_MODE
      ? []
      : fixtureGraphNodes;
  const graphViewEdges = isServerGraphRendered
    ? serverGraphEdges!
    : CLOUD_MODE
      ? []
      : fixtureGraphEdges;
  // S9PAT02 empire canvas: every node is re-laid onto the solar system -
  // the focus entity is the sun, zones become orbital belts with angular
  // sectors. Layout is position-only (keys, zones, click handlers, zoom and
  // lens semantics are untouched), so the existing state contract holds.
  const graphViewNodes = useMemo(
    () => layoutEmpireOrbits(baseGraphViewNodes),
    [baseGraphViewNodes]
  );
  const orbitRingRadii = useMemo(
    () =>
      Array.from(
        new Set(
          graphViewNodes
            .map((item) => item.orbitRadius ?? 0)
            .filter((radius) => radius > 0)
        )
      ).sort((a, b) => a - b),
    [graphViewNodes]
  );
  const graphViewNodeByKey = useMemo(
    () => new Map(graphViewNodes.map((item) => [item.key, item])),
    [graphViewNodes]
  );
  const graphViewMode = isServerGraphRendered
    ? "server"
    : CLOUD_MODE
      ? "cloud-empty"
      : "fixture";
  // S9PBT01 V4: legend inventory (per-zone node counts from the live view)
  // and the GAPS badge fed by the real 16-stage supply-chain assertion
  // coverage - never a fabricated percentage.
  const ZONE_LABELS: Record<string, string> = {
    focus: "焦点",
    upstream: "上游",
    downstream: "下游",
    business: "业务",
    capital: "资本",
    policy: "政策",
    infrastructure: "设施"
  };
  const legendInventory = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of graphViewNodes) {
      counts.set(node.zone, (counts.get(node.zone) ?? 0) + (node.aggregateCount || 1));
    }
    return Array.from(counts.entries())
      .map(([zone, count]) => ({ zone, label: ZONE_LABELS[zone] ?? zone, count }))
      .sort((a, b) => b.count - a.count);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphViewNodes]);
  const [supplyGapsPct, setSupplyGapsPct] = useState<number | null>(null);
  const [supplyGapsDetail, setSupplyGapsDetail] = useState("");
  // S9PCT01 V3: the 2016->now history scrubber, backed by the REAL per-year
  // regulatory-filing depth from the S7PDT01 backfill. It coexists with the
  // three-point as-of contract (snapshots) without touching that state.
  const [historyYears, setHistoryYears] = useState<
    { year: number; filings: number }[] | null
  >(null);
  const [historyYearSelected, setHistoryYearSelected] = useState<number | null>(null);
  useEffect(() => {
    const apiBaseUrl = readProductionDataApiBaseUrl();
    if (!apiBaseUrl) {
      return;
    }
    void window
      // cache: no-store —— 部署间隙的 404 曾被浏览器缓存（边缘 max-age），
      // 请求侧绕过 HTTP 缓存，对已中毒的访客也立即恢复。
      .fetch(`${apiBaseUrl}/v1/policy/overview`, { cache: "no-store" })
      .then(async (response) => {
        const payload = (await response.json().catch(() => null)) as {
          regulatory_filings?: { by_year?: { year: number; filings: number }[] };
        } | null;
        const byYear = payload?.regulatory_filings?.by_year;
        if (response.ok && Array.isArray(byYear) && byYear.length > 0) {
          setHistoryYears(byYear);
          setHistoryYearSelected(byYear[byYear.length - 1].year);
        }
      })
      .catch(() => {
        // Honest empty state stays; the scrubber never invents years.
      });
  }, []);
  const historyMaxFilings = useMemo(
    () => Math.max(1, ...(historyYears ?? []).map((item) => item.filings)),
    [historyYears]
  );
  // S12PB 右侧竖轴：指针拖动/滚轮在年份纵列上自由滑选（点选仍可用）。
  const historyRailRef = useRef<HTMLDivElement | null>(null);
  const selectHistoryYearAtPointer = (clientY: number) => {
    const rail = historyRailRef.current;
    if (!rail || !historyYears || historyYears.length === 0) {
      return;
    }
    const rect = rail.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientY - rect.top) / Math.max(1, rect.height)));
    const index = Math.min(historyYears.length - 1, Math.floor(ratio * historyYears.length));
    const year = historyYears[index]?.year;
    if (typeof year === "number" && year !== historyYearSelected) {
      setHistoryYearSelected(year);
    }
  };
  const handleHistoryPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!historyYears || historyYears.length === 0) {
      return;
    }
    event.currentTarget.setPointerCapture?.(event.pointerId);
    selectHistoryYearAtPointer(event.clientY);
  };
  const handleHistoryPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.buttons > 0) {
      selectHistoryYearAtPointer(event.clientY);
    }
  };
  const stepHistoryYear = (step: number) => {
    if (!historyYears || historyYears.length === 0) {
      return;
    }
    const currentIndex = historyYears.findIndex((item) => item.year === historyYearSelected);
    const nextIndex = Math.min(
      historyYears.length - 1,
      Math.max(0, (currentIndex === -1 ? historyYears.length - 1 : currentIndex) + step)
    );
    setHistoryYearSelected(historyYears[nextIndex].year);
  };
  // S9PCT02 V7 Ask bar state (D4: zero-API ChatGPT jump).
  const [askInput, setAskInput] = useState("");
  const [lastAskAction, setLastAskAction] = useState("idle");
  useEffect(() => {
    const apiBaseUrl = readProductionDataApiBaseUrl();
    if (!apiBaseUrl) {
      return;
    }
    void window
      .fetch(`${apiBaseUrl}/v1/supply-chain/overview`)
      .then(async (response) => {
        const payload = (await response.json().catch(() => null)) as {
          summary?: { stages_total?: number; stages_with_relationships?: number };
        } | null;
        const total = payload?.summary?.stages_total;
        const covered = payload?.summary?.stages_with_relationships;
        if (response.ok && typeof total === "number" && typeof covered === "number" && total > 0) {
          setSupplyGapsPct(Math.round(((total - covered) / total) * 100));
          setSupplyGapsDetail(`${total - covered}/${total} 阶段无断言`);
        }
      })
      .catch(() => {
        // api_required fallback keeps the honest "未知" label.
      });
  }, []);
  // S9PAT03 ⑤ hover depth-of-field: the hovered node's neighborhood stays
  // sharp while everything else dims (CSS-only transition, motion-gated).
  const [hoveredNodeKey, setHoveredNodeKey] = useState<string | null>(null);
  const hoverNeighborhood = useMemo(() => {
    if (!hoveredNodeKey) {
      return null;
    }
    const near = new Set<string>([hoveredNodeKey]);
    for (const edge of graphViewEdges) {
      if (edge.from === hoveredNodeKey) near.add(edge.to);
      if (edge.to === hoveredNodeKey) near.add(edge.from);
    }
    return near;
  }, [hoveredNodeKey, graphViewEdges]);
  // S9PAT03 ① camera fly on reroot: retrigger the fly-in animation whenever
  // the focused entity changes (fixture focusKey or server focus id).
  const empireFocusIdentity = isServerGraphRendered
    ? productionGraphRequest.focus.object_id
    : focusKey;
  const empireMapRef = useRef<SVGSVGElement | null>(null);
  useEffect(() => {
    const svg = empireMapRef.current;
    if (!svg) {
      return;
    }
    svg.classList.remove("rerootFly");
    // Force a reflow so re-adding the class restarts the animation.
    void svg.getBoundingClientRect();
    svg.classList.add("rerootFly");
    const clear = () => svg.classList.remove("rerootFly");
    svg.addEventListener("animationend", clear, { once: true });
    return () => svg.removeEventListener("animationend", clear);
  }, [empireFocusIdentity]);
  const productionContext = productionGraph?.production_context;
  // 发布面上下文的快照标识（as_of / published_at），供云模式覆盖层展示。
  const publishedContextMeta = (productionContext?.active_analysis_context ?? {}) as {
    as_of?: string | null;
    published_at?: string | null;
  };
  const productionCoverage = productionGraph?.coverage;
  const productionCandidateCoverage = productionCoverage?.relationship_fact_candidates;
  const productionCandidateSummary = productionContext?.candidate_fact_summary;
  const productionSampleCandidate = productionCandidateSummary?.sample_candidates?.[0] ?? null;
  const productionPublishedRelationships =
    productionContext?.record_modes?.published_relationships;
  const productionGraphBudget = productionGraph?.query.budget ?? productionGraphRequest.budget;
  const primaryFreshnessSource =
    productionFreshness?.sources.find(
      (source) => source.source_code === "sec_edgar_synthetic_fixture"
    ) ?? productionFreshness?.sources[0];
  const freshnessServerError = productionFreshnessStatus === "server-error";
  // 云模式下样例鲜度永不出现：拿不到发布鲜度就亮不可用，不冒充。
  const freshnessFallback = CLOUD_MODE
    ? {
        status: "publication_unavailable",
        sourceCode: "cloud_publication_surface",
        lastAttemptAt: null,
        lastSuccessAt: null,
        lastFailureAt: null,
        latestDocumentDate: null,
        latestReportPeriodEnd: null,
        sourceCount: 0,
        sourceDocumentCount: 0
      }
    : homeFreshness;
  const freshnessDisplay = {
    status: freshnessServerError
      ? "server_error"
      : (productionFreshness?.summary.status ?? freshnessFallback.status),
    sourceCode: freshnessServerError
      ? "unavailable"
      : (primaryFreshnessSource?.source_code ?? freshnessFallback.sourceCode),
    lastAttemptAt: freshnessServerError
      ? null
      : (primaryFreshnessSource?.last_attempt_at ?? freshnessFallback.lastAttemptAt),
    lastSuccessAt: freshnessServerError
      ? null
      : (primaryFreshnessSource?.last_success_at ?? freshnessFallback.lastSuccessAt),
    lastFailureAt: freshnessServerError
      ? null
      : (primaryFreshnessSource?.last_failure_at ?? freshnessFallback.lastFailureAt),
    latestDocumentDate: freshnessServerError
      ? null
      : (primaryFreshnessSource?.latest_document_date ?? freshnessFallback.latestDocumentDate),
    latestReportPeriodEnd: freshnessServerError
      ? null
      : (primaryFreshnessSource?.latest_report_period_end ??
        freshnessFallback.latestReportPeriodEnd),
    sourceCount: freshnessServerError
      ? 0
      : (productionFreshness?.summary.source_count ?? freshnessFallback.sourceCount),
    sourceDocumentCount: freshnessServerError
      ? 0
      : (productionFreshness?.summary.document_count ?? freshnessFallback.sourceDocumentCount)
  };
  const tableEdges = useMemo(
    () =>
      tableLensFilter === "all"
        ? graphViewEdges
        : graphViewEdges.filter((edge) => edge.lens === tableLensFilter),
    [graphViewEdges, tableLensFilter]
  );
  const activeEdgeKeys = useMemo(() => {
    const keys = new Set<string>([isServerGraphRendered ? productionGraphRequest.focus.object_id : focusKey]);
    for (const edge of graphViewEdges) {
      if (activeLens === "all" || edge.lens === activeLens) {
        keys.add(edge.from);
        keys.add(edge.to);
      }
    }
    return keys;
  }, [activeLens, focusKey, graphViewEdges, isServerGraphRendered, productionGraphRequest.focus.object_id]);
  const selectedNode =
    nodeByKey.get(selectedKey) ?? nodeByKey.get(scenario.focus) ?? scenario.nodes[0];
  const selectedServerGraphNode = selectedProductionNodeKey
    ? graphViewNodeByKey.get(selectedProductionNodeKey)
    : undefined;
  const serverFocusLabel =
    productionGraph?.focus?.canonical_name ??
    serverPath[serverPath.length - 1]?.label ??
    SERVER_DEFAULT_FOCUS.label;
  // 云模式选择链：图内节点 > 搜索选中的图外实体 > 焦点节点 > 占位。
  // 永不落回合成样例节点（EEI-F02）。本地模式保留原语义（含本地
  // 挂载 mock 服务端图时的 server 选择）。
  const selectedGraphNode = CLOUD_MODE
    ? selectedServerGraphNode ??
      (selectedServerEntity ? serverEntityRenderNode(selectedServerEntity) : undefined) ??
      graphViewNodeByKey.get(serverFocusEntityId) ??
      cloudPlaceholderRenderNode(serverFocusLabel)
    : graphViewMode === "server"
      ? selectedServerGraphNode ??
        graphViewNodeByKey.get(selectedNode.key) ??
        fixtureRenderNode(selectedNode)
      : graphViewNodeByKey.get(selectedNode.key) ?? fixtureRenderNode(selectedNode);
  const industryPath = useMemo(() => {
    const ordered: { key: string; label: string }[] = [];
    for (const key of path) {
      const industry = focusIndustryByKey[key];
      if (ordered[ordered.length - 1]?.key !== industry.key) {
        ordered.push(industry);
      }
    }
    return ordered;
  }, [path]);
  const industryPathLabel = industryPath.map((item) => item.label).join(" -> ");
  const isCrossIndustryPath = industryPath.length > 1;
  const upstreamCandidate = useMemo(
    () => scenario.edges.find((edge) => edge.to === selectedNode.key && nodeByKey.has(edge.from))?.from,
    [nodeByKey, scenario.edges, selectedNode.key]
  );
  const downstreamCandidate = useMemo(
    () =>
      scenario.edges.find((edge) => edge.from === selectedNode.key && nodeByKey.has(edge.to))?.to,
    [nodeByKey, scenario.edges, selectedNode.key]
  );

  function applyWorkspaceState(nextState: WorkspaceStateInput) {
    const normalized = normalizeWorkspaceState(nextState);
    setFocusKey(normalized.focusKey);
    setSelectedKey(normalized.selectedKey);
    setSelectedProductionNodeKey("");
    setPath(normalized.path);
    setActiveLens(normalized.activeLens);
    setSemanticZoom(normalized.semanticZoom);
    setAsOf(normalized.asOf);
    setGroupListOpen(false);
    setTransitionState("ready");
  }

  function applyPathSubject(pathIndex: number) {
    const nextFocus = path[pathIndex];
    if (!nextFocus) return;
    applyWorkspaceState({
      ...workspaceState,
      focusKey: nextFocus,
      selectedKey: nextFocus,
      path: path.slice(0, pathIndex + 1)
    });
  }

  function browserBack() {
    window.history.back();
  }

  async function saveCurrentView() {
    setSavedViewStatus("saving");
    const nextSavedView = createSavedView(workspaceState, analysisContext);
    const syncResult = await saveViewToServer({
      name: nextSavedView.notes,
      description: "EEI workspace saved view",
      state: createSavedViewServerState(nextSavedView),
      metadata: createSavedViewMetadata(nextSavedView),
      serverId: savedView.serverId,
      expectedVersion: savedView.serverVersion
    });
    let syncedSavedView: SavedViewRecord;
    if (syncResult.mode === "server" && syncResult.status === "saved") {
      syncedSavedView = savedViewFromServerRecord(
        syncResult.record,
        syncResult.endpoint,
        analysisContext
      );
    } else if (isFailedServerSyncResult(syncResult)) {
      syncedSavedView = {
        ...nextSavedView,
        serverId: savedView.serverId,
        serverVersion: savedView.serverVersion,
        syncMode: "server",
        syncReason: syncResult.reason,
        serverEndpoint: syncResult.endpoint
      };
    } else if (syncResult.mode === "local_fallback") {
      syncedSavedView = {
        ...nextSavedView,
        serverId: savedView.serverId,
        serverVersion: savedView.serverVersion,
        syncMode: "local_fallback",
        syncReason: syncResult.reason
      };
    } else {
      syncedSavedView = {
        ...nextSavedView,
        serverId: savedView.serverId,
        serverVersion: savedView.serverVersion,
        syncMode: "server",
        syncReason: "unexpected_saved_view_sync_status",
        serverEndpoint: syncResult.endpoint
      };
    }

    window.localStorage.setItem(SAVED_VIEW_STORAGE_KEY, JSON.stringify(syncedSavedView));
    setSavedView(syncedSavedView);
    setSavedViewStatus(
      syncResult.mode === "server"
        ? syncResult.status === "saved"
          ? "server-saved"
          : syncResult.status === "conflict"
            ? "server-conflict"
            : "server-error"
        : "local-saved"
    );
  }

  async function restoreSavedView() {
    setSavedViewStatus("restoring");
    const storedSavedView = readSavedViewPayload(window.localStorage.getItem(SAVED_VIEW_STORAGE_KEY));
    const nextSavedView = storedSavedView ?? savedView;
    const syncResult = await restoreViewFromServer(nextSavedView.serverId);
    if (syncResult.mode === "server" && syncResult.status === "restored") {
      const serverSavedView = savedViewFromServerRecord(
        syncResult.record,
        syncResult.endpoint,
        analysisContext
      );
      window.localStorage.setItem(SAVED_VIEW_STORAGE_KEY, JSON.stringify(serverSavedView));
      setSavedView(serverSavedView);
      restoringHistoryState.current = true;
      applyWorkspaceState(serverSavedView);
      setSavedViewStatus("server-restored");
      return;
    }

    if (syncResult.mode === "local_fallback") {
      const localSavedView: SavedViewRecord = {
        ...nextSavedView,
        syncMode: "local_fallback",
        syncReason: syncResult.reason
      };
      window.localStorage.setItem(SAVED_VIEW_STORAGE_KEY, JSON.stringify(localSavedView));
      setSavedView(localSavedView);
      restoringHistoryState.current = true;
      applyWorkspaceState(localSavedView);
      setSavedViewStatus("local-restored");
      return;
    }

    if (!isFailedServerSyncResult(syncResult)) return;

    const failedSavedView: SavedViewRecord = {
      ...nextSavedView,
      syncMode: "server",
      syncReason: syncResult.reason,
      serverEndpoint: syncResult.endpoint
    };
    window.localStorage.setItem(SAVED_VIEW_STORAGE_KEY, JSON.stringify(failedSavedView));
    setSavedView(failedSavedView);
    setSavedViewStatus(syncResult.status === "conflict" ? "server-conflict" : "server-error");
  }

  async function resolveSavedViewConflict() {
    setSavedViewStatus("resolving-conflict");
    const syncResult = await restoreViewFromServer(savedView.serverId);
    if (syncResult.mode === "server" && syncResult.status === "restored") {
      const serverSavedView = {
        ...savedViewFromServerRecord(syncResult.record, syncResult.endpoint, analysisContext),
        syncReason: "resolved_latest"
      };
      window.localStorage.setItem(SAVED_VIEW_STORAGE_KEY, JSON.stringify(serverSavedView));
      setSavedView(serverSavedView);
      restoringHistoryState.current = true;
      applyWorkspaceState(serverSavedView);
      setSavedViewStatus("server-conflict-resolved");
      return;
    }
    if (syncResult.mode === "local_fallback") {
      setSavedViewStatus("local-restored");
      return;
    }
    if (!isFailedServerSyncResult(syncResult)) return;
    setSavedView({
      ...savedView,
      syncMode: "server",
      syncReason: syncResult.reason,
      serverEndpoint: syncResult.endpoint
    });
    setSavedViewStatus(syncResult.status === "conflict" ? "server-conflict" : "server-error");
  }

  async function hydrateProductionData(reason = "manual_refresh", candidateId?: string | null) {
    setProductionCatalogStatus("loading-production-data");
    setProductionScoreStatus(candidateId ? "loading-production-data" : "local-fixture");
    setProductionEvidenceStatus(candidateId ? "loading-production-data" : "local-fixture");
    setProductionFreshnessStatus("loading-production-data");
    const [catalogResult, scoreResult, evidenceResult, freshnessResult] = await Promise.all([
      loadCatalogInventory(),
      loadScoreExplanation({
        objectType: "relationship_fact_candidate",
        objectId: candidateId,
        profileId: serverModelContext?.active_scoring_profile_version_id
      }),
      loadEvidenceDetail({
        objectType: "relationship_fact_candidate",
        objectId: candidateId,
        limit: 20
      }),
      loadSourceFreshness()
    ]);

    if (catalogResult.mode === "local_fallback") {
      setProductionCatalogSyncMode("local_fallback");
      setProductionCatalogSyncReason(catalogResult.reason);
      setProductionCatalogEndpoint("");
      setProductionCatalogStatus("local-fixture");
    } else if (catalogResult.status === "error") {
      setProductionCatalogSyncMode("server");
      setProductionCatalogSyncReason(catalogResult.reason);
      setProductionCatalogEndpoint(catalogResult.endpoint);
      setProductionCatalogStatus("server-error");
    } else {
      setProductionCatalogInventory(catalogResult.record);
      setProductionCatalogSyncMode("server");
      setProductionCatalogSyncReason(reason);
      setProductionCatalogEndpoint(catalogResult.endpoint);
      setProductionCatalogStatus("server-hydrated");
    }

    if (scoreResult.mode === "local_fallback") {
      setProductionScoreSyncMode("local_fallback");
      setProductionScoreSyncReason(scoreResult.reason);
      setProductionScoreEndpoint("");
      setProductionScoreTargetId(candidateId ?? "");
      setProductionScoreExplanation(null);
      setProductionScoreStatus("local-fixture");
    } else if (scoreResult.status === "error") {
      setProductionScoreSyncMode("server");
      setProductionScoreSyncReason(scoreResult.reason);
      setProductionScoreEndpoint(scoreResult.endpoint);
      setProductionScoreTargetId(candidateId ?? "");
      setProductionScoreExplanation(null);
      setProductionScoreStatus("server-error");
    } else {
      setProductionScoreExplanation(scoreResult.record);
      setProductionScoreSyncMode("server");
      setProductionScoreSyncReason(reason);
      setProductionScoreEndpoint(scoreResult.endpoint);
      setProductionScoreTargetId(scoreResult.record.object_id);
      setProductionScoreStatus("server-hydrated");
    }

    if (evidenceResult.mode === "local_fallback") {
      setProductionEvidenceSyncMode("local_fallback");
      setProductionEvidenceSyncReason(evidenceResult.reason);
      setProductionEvidenceEndpoint("");
      setProductionEvidenceDetail(null);
      setProductionEvidenceStatus("local-fixture");
    } else if (evidenceResult.status === "error") {
      setProductionEvidenceSyncMode("server");
      setProductionEvidenceSyncReason(evidenceResult.reason);
      setProductionEvidenceEndpoint(evidenceResult.endpoint);
      setProductionEvidenceDetail(null);
      setProductionEvidenceStatus("server-error");
    } else {
      setProductionEvidenceDetail(evidenceResult.record);
      setProductionEvidenceSyncMode("server");
      setProductionEvidenceSyncReason(reason);
      setProductionEvidenceEndpoint(evidenceResult.endpoint);
      setProductionEvidenceStatus("server-hydrated");
    }

    if (freshnessResult.mode === "local_fallback") {
      setProductionFreshnessSyncMode("local_fallback");
      setProductionFreshnessSyncReason(freshnessResult.reason);
      setProductionFreshnessEndpoint("");
      setProductionFreshness(null);
      setProductionFreshnessStatus("local-fixture");
    } else if (freshnessResult.status === "error") {
      setProductionFreshnessSyncMode("server");
      setProductionFreshnessSyncReason(freshnessResult.reason);
      setProductionFreshnessEndpoint(freshnessResult.endpoint);
      setProductionFreshness(null);
      setProductionFreshnessStatus("server-error");
    } else {
      setProductionFreshnessSyncMode("server");
      setProductionFreshnessSyncReason(reason);
      setProductionFreshnessEndpoint(freshnessResult.endpoint);
      setProductionFreshness(freshnessResult.record);
      setProductionFreshnessStatus("server-hydrated");
    }
  }

  // EEI-F01 (J-003/J-004)：云模式取数——评分/证据的目标关系号直接来自
  // 活图的边，发布鲜度来自发布元数据；目录清单不属于发布面，如实标注。
  async function hydrateCloudData(reason: string, relationshipId: string) {
    setProductionScoreStatus("loading-production-data");
    setProductionEvidenceStatus("loading-production-data");
    setProductionFreshnessStatus("loading-production-data");
    setProductionCatalogSyncMode("server");
    setProductionCatalogSyncReason("publication_surface_has_no_catalog_inventory");
    setProductionCatalogStatus("server-hydrated");
    const [scoreResult, evidenceResult, freshnessResult] = await Promise.all([
      loadCloudScoreExplanation(relationshipId),
      loadCloudEvidenceDetail(relationshipId),
      loadCloudPublicationFreshness()
    ]);

    if (scoreResult.mode === "server" && scoreResult.status === "hydrated") {
      setProductionScoreExplanation(scoreResult.record);
      setProductionScoreSyncMode("server");
      setProductionScoreSyncReason(reason);
      setProductionScoreEndpoint(scoreResult.endpoint);
      setProductionScoreTargetId(scoreResult.record.object_id);
      setProductionScoreStatus("server-hydrated");
    } else {
      setProductionScoreSyncMode("server");
      setProductionScoreSyncReason(
        scoreResult.mode === "server" ? scoreResult.reason : scoreResult.reason
      );
      setProductionScoreEndpoint(scoreResult.mode === "server" ? scoreResult.endpoint : "");
      setProductionScoreTargetId(relationshipId);
      setProductionScoreExplanation(null);
      setProductionScoreStatus("server-error");
    }

    if (evidenceResult.mode === "server" && evidenceResult.status === "hydrated") {
      setProductionEvidenceDetail(evidenceResult.record);
      setProductionEvidenceSyncMode("server");
      setProductionEvidenceSyncReason(reason);
      setProductionEvidenceEndpoint(evidenceResult.endpoint);
      setProductionEvidenceStatus("server-hydrated");
    } else {
      setProductionEvidenceSyncMode("server");
      setProductionEvidenceSyncReason(
        evidenceResult.mode === "server" ? evidenceResult.reason : evidenceResult.reason
      );
      setProductionEvidenceEndpoint(
        evidenceResult.mode === "server" ? evidenceResult.endpoint : ""
      );
      setProductionEvidenceDetail(null);
      setProductionEvidenceStatus("server-error");
    }

    if (freshnessResult.mode === "server" && freshnessResult.status === "hydrated") {
      setProductionFreshness(freshnessResult.record);
      setProductionFreshnessSyncMode("server");
      setProductionFreshnessSyncReason(reason);
      setProductionFreshnessEndpoint(freshnessResult.endpoint);
      setProductionFreshnessStatus("server-hydrated");
    } else {
      setProductionFreshnessSyncMode("server");
      setProductionFreshnessSyncReason(
        freshnessResult.mode === "server" ? freshnessResult.reason : freshnessResult.reason
      );
      setProductionFreshnessEndpoint(
        freshnessResult.mode === "server" ? freshnessResult.endpoint : ""
      );
      setProductionFreshness(null);
      setProductionFreshnessStatus("server-error");
    }
  }

  async function hydrateProductionGraph(reason = "manual_refresh") {
    setProductionGraphStatus("loading-production-graph");
    const graphResult = await loadExploreGraph(productionGraphRequest);
    if (graphResult.mode === "local_fallback") {
      setProductionGraphSyncMode("local_fallback");
      setProductionGraphSyncReason(graphResult.reason);
      setProductionGraphEndpoint("");
      setProductionGraphStatus("local-fixture");
      void hydrateProductionData(reason, null);
      return;
    }
    if (graphResult.status === "error") {
      setProductionGraphSyncMode("server");
      setProductionGraphSyncReason(graphResult.reason);
      setProductionGraphEndpoint(graphResult.endpoint);
      setProductionGraphStatus("server-error");
      void hydrateProductionData(reason, null);
      return;
    }
    setProductionGraph(graphResult.record);
    setProductionGraphSyncMode("server");
    setProductionGraphSyncReason(reason);
    setProductionGraphEndpoint(graphResult.endpoint);
    setProductionGraphStatus("server-hydrated");
    void hydrateProductionData(
      `graph_${reason}`,
      graphResult.record.production_context.candidate_fact_summary?.sample_candidates?.[0]?.id
    );
  }

  async function hydrateModelContext(clientRefreshToken?: string, reason = "manual_refresh") {
    setModelContextStatus("loading-server-context");
    const contextResult = await loadActiveModelContext(clientRefreshToken);
    if (contextResult.mode === "local_fallback") {
      setModelContextSyncMode("local_fallback");
      setModelContextSyncReason(contextResult.reason);
      setModelContextStatus("local-active");
      return;
    }
    if (contextResult.status === "error") {
      setModelContextSyncMode("server");
      setModelContextSyncReason(contextResult.reason);
      setModelContextEndpoint(contextResult.endpoint);
      setModelContextStatus("server-error");
      return;
    }

    applyServerContext(
      analysisContextFromActiveModelContext(contextResult.record, ACTIVE_ANALYSIS_CONTEXT)
    );
    setServerModelContext(contextResult.record);
    setModelContextSyncMode("server");
    setModelContextSyncReason(
      contextResult.status === "stale" ? "stale_client_refetched" : reason
    );
    setModelContextEndpoint(contextResult.endpoint);
    setModelContextStatus(
      contextResult.status === "stale" && clientRefreshToken
        ? "server-refreshed"
        : contextResult.status === "stale"
          ? "server-stale"
          : "server-current"
    );

    const profileResult = await listModelProfiles();
    if (profileResult.mode === "server" && profileResult.status === "listed") {
      const nextCandidate =
        profileResult.profiles.find((profile) => !profile.active) ??
        profileResult.profiles.find(
          (profile) => profile.id !== contextResult.record.active_scoring_profile_version_id
        ) ??
        null;
      setCandidateProfile(nextCandidate);
    }
  }

  async function createOnlineModelDraft() {
    setModelDraftStatus("creating");
    setModelDraftReason("creating");
    if (!serverModelContext) {
      applyPreview();
      setModelDraftStatus("local-preview");
      setModelDraftReason("active_context_missing");
      return;
    }

    const draftResult = await createModelProfileDraft({
      baseProfileVersionId: serverModelContext.active_scoring_profile_version_id,
      profileKey: "balanced-v2-online-draft",
      name: "Balanced v2 Online Draft",
      weights: ONLINE_DRAFT_PROFILE_WEIGHTS,
      reason: "EEI model-center online edit draft"
    });
    if (draftResult.mode === "local_fallback") {
      applyPreview();
      setModelDraftStatus("local-preview");
      setModelDraftReason(draftResult.reason);
      return;
    }
    setModelDraftEndpoint(draftResult.endpoint);
    if (draftResult.status === "error") {
      setModelDraftStatus("server-error");
      setModelDraftReason(draftResult.reason);
      return;
    }

    const nextContext = draftResult.response.active_context;
    applyServerContext(analysisContextFromActiveModelContext(nextContext, ACTIVE_ANALYSIS_CONTEXT));
    setServerModelContext(nextContext);
    setCandidateProfile(draftResult.response.profile);
    setDraftProfile(draftResult.response.profile);
    setModelContextSyncMode("server");
    setModelContextSyncReason("online_draft_created");
    setModelContextStatus(nextContext.client_state === "stale" ? "server-stale" : "server-current");
    setModelDraftWeightSum(draftResult.response.validation.weight_sum);
    setModelDraftReason(
      `changed_${draftResult.response.validation.changed_weights.length}_weights`
    );
    setModelDraftStatus("created");
  }

  async function activateCandidateModelProfile() {
    await activateModelProfileTransaction(
      candidateProfile,
      "EEI model-center transaction activation",
      "activate"
    );
  }

  async function rollbackLatestModelActivation() {
    await activateModelProfileTransaction(
      rollbackProfile,
      "EEI model-center rollback activation",
      "rollback"
    );
  }

  async function enqueueCurrentScoreRecompute() {
    if (!serverModelContext) {
      setScoreRecomputeStatus("server-error");
      setScoreRecomputeReason("active_context_missing");
      return;
    }
    setScoreRecomputeStatus("enqueueing");
    setScoreRecomputeReason("requesting");
    const recomputeResult = await requestScoreRecompute({
      expectedActiveProfileVersionId: serverModelContext.active_scoring_profile_version_id,
      clientRefreshToken: serverModelContext.refresh_token,
      scope: "global",
      reason: "EEI model-center score recompute request"
    });
    if (recomputeResult.mode === "local_fallback") {
      setScoreRecomputeStatus("server-error");
      setScoreRecomputeReason(recomputeResult.reason);
      return;
    }
    setScoreRecomputeEndpoint(recomputeResult.endpoint);
    if (isFailedScoreRecomputeResult(recomputeResult)) {
      setScoreRecomputeStatus(
        recomputeResult.status === "conflict" ? "server-conflict" : "server-error"
      );
      setScoreRecomputeReason(recomputeResult.reason);
      return;
    }

    const nextContext = recomputeResult.response.active_context;
    applyServerContext(analysisContextFromActiveModelContext(nextContext, ACTIVE_ANALYSIS_CONTEXT));
    setServerModelContext(nextContext);
    setScoreRecomputeJob(recomputeResult.response.job);
    setScoreRecomputeStatus(recomputeResult.response.job.status);
    setScoreRecomputeReason(`score_recompute_${recomputeResult.response.job.status}`);
  }

  async function activateModelProfileTransaction(
    targetProfile: ScoringProfileRecord | null,
    reason: string,
    action: "activate" | "rollback"
  ) {
    if (!targetProfile) {
      setModelContextSyncReason("target_profile_missing");
      setModelContextStatus("server-no-target");
      return;
    }
    setModelContextStatus("activating");
    const transition = action === "rollback" ? rollbackModelProfile : activateModelProfile;
    const activationResult = await transition({
      targetProfileVersionId: targetProfile.id,
      expectedActiveProfileVersionId: serverModelContext?.active_scoring_profile_version_id,
      clientRefreshToken: serverModelContext?.refresh_token,
      reason
    });
    if (activationResult.mode === "local_fallback") {
      setModelContextSyncMode("local_fallback");
      setModelContextSyncReason(activationResult.reason);
      setModelContextStatus("server-error");
      return;
    }
    if (isFailedModelActivationResult(activationResult)) {
      setModelContextSyncMode("server");
      setModelContextSyncReason(activationResult.reason);
      setModelContextEndpoint(activationResult.endpoint);
      setModelContextStatus(
        activationResult.status === "conflict" ? "server-conflict" : "server-error"
      );
      return;
    }

    const nextContext = activationResult.response.active_context;
    applyServerContext(analysisContextFromActiveModelContext(nextContext, ACTIVE_ANALYSIS_CONTEXT));
    setPreviousModelRefreshToken(
      activationResult.response.cache_invalidation.previous_refresh_token ?? ""
    );
    setServerModelContext(nextContext);
    setCandidateProfile(activationResult.response.previous_profile);
    setRollbackProfile(activationResult.response.previous_profile);
    setModelContextSyncMode("server");
    setModelContextSyncReason(
      action === "rollback"
        ? "rollback_transaction_committed"
        : "activation_transaction_committed"
    );
    setModelContextEndpoint(activationResult.endpoint);
    setModelContextStatus("server-activated");
  }

  const viewportAnchor = `${focusKey}:${selectedNode.key}:${semanticZoom}`;
  const visibleSearchResults = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return homeSearchResults.slice(0, 3);
    }
    return homeSearchResults.filter((result) =>
      [result.label, result.description, ...result.aliases].some((value) =>
        value.toLowerCase().includes(normalizedQuery)
      )
    );
  }, [searchQuery]);
  // 云模式搜索展示：有词=服务端实查结果；无词=当前图内实体（可选中）。
  const cloudSearchDisplay = useMemo<ServerEntityRecord[]>(() => {
    if (!CLOUD_MODE) return [];
    if (searchQuery.trim()) return serverSearchResults;
    return (productionGraph?.nodes ?? []).slice(0, 3).map((node) => ({
      id: node.id,
      canonical_name: node.canonical_name,
      entity_type: node.entity_type ?? "entity",
      status: "published"
    }));
  }, [productionGraph, searchQuery, serverSearchResults]);

  function requestCenter(nextFocus: string) {
    setTransitionState("loading");
    window.setTimeout(() => {
      if (!(nextFocus in scenarios)) {
        setTransitionState("fallback");
        return;
      }
      const validFocus = nextFocus as FocusKey;
      setFocusKey(validFocus);
      setSelectedKey(validFocus);
      setSelectedProductionNodeKey("");
      setPath((current) =>
        current[current.length - 1] === validFocus ? current : [...current, validFocus]
      );
      setGroupListOpen(false);
      setTransitionState("ready");
    }, 360);
  }

  function setCenter(nextFocus: FocusKey) {
    requestCenter(nextFocus);
  }

  function inspectNode(nextSelected: NodeKey, options: { preserveProductionSelection?: boolean } = {}) {
    if (!options.preserveProductionSelection) {
      setSelectedProductionNodeKey("");
    }
    setSelectedKey(nextSelected);
    setGroupListOpen(false);
  }

  function inspectGraphNode(nextSelected: GraphRenderNode) {
    setSelectedServerEntity(null);
    if (nextSelected.source === "server") {
      setSelectedProductionNodeKey(nextSelected.key);
    }
    if (nextSelected.localKey) {
      inspectNode(nextSelected.localKey, { preserveProductionSelection: true });
      return;
    }
    setSelectedProductionNodeKey(nextSelected.key);
    setNodeActionStatus(`server-inspect:${nextSelected.key}`);
    setGroupListOpen(false);
  }

  // EEI-F03：选择只改「当前选择」，换中心必须走显式动作。
  function selectServerEntity(entity: ServerEntityRecord) {
    setSelectedProductionNodeKey(entity.id);
    setSelectedServerEntity(entity);
    setNodeActionStatus(`select:${entity.id}`);
    setGroupListOpen(false);
  }

  // 云模式显式换中心：目标是被选中的那个真实已发布实体本身。
  function serverReroot(entityId: string, label: string) {
    if (!CLOUD_MODE || !entityId) return;
    setTransitionState("loading");
    window.setTimeout(() => {
      setServerFocusEntityId(entityId);
      setSelectedProductionNodeKey(entityId);
      setSelectedServerEntity(null);
      setServerPath((current) => {
        const existing = current.findIndex((item) => item.id === entityId);
        if (existing >= 0) {
          return current.slice(0, existing + 1);
        }
        return [...current, { id: entityId, label }];
      });
      setGroupListOpen(false);
      setTransitionState("ready");
    }, 360);
  }

  function addUniqueNode(current: NodeKey[], key: NodeKey) {
    return current.includes(key) ? current : [...current, key];
  }

  function pinSelectedNode() {
    setPinnedNodeKeys((current) => addUniqueNode(current, selectedNode.key));
    setNodeActionStatus(`pinned:${selectedNode.key}`);
  }

  function compareSelectedNode() {
    setComparisonNodeKeys((current) => addUniqueNode(current, selectedNode.key).slice(-4));
    setNodeActionStatus(`compare:${selectedNode.key}`);
  }

  function addSelectedNodeToWatchlist() {
    setWatchlistNodeKeys((current) => addUniqueNode(current, selectedNode.key));
    setNodeActionStatus(`watchlist:${selectedNode.key}`);
  }

  function applyWorkspaceNavigationLens(lens: string, moduleId: WorkspaceModuleId) {
    if (!isLensKey(lens)) return;
    setActiveLens(lens);
    setNavActionStatus(`lens:${moduleId}:${lens}`);
  }

  function applyWorkspaceNavigationSection(sectionTestId: string, moduleId: WorkspaceModuleId) {
    const section = document.querySelector<HTMLElement>(`[data-testid="${sectionTestId}"]`);
    section?.scrollIntoView({ block: "nearest", inline: "nearest" });
    section?.focus?.({ preventScroll: true });
    setNavActionStatus(`section:${moduleId}:${sectionTestId}`);
  }

  function openSelectedPath() {
    setNodeActionStatus(`path:${selectedNode.key}`);
  }

  function openSelectedEvidence() {
    setNodeActionStatus(`evidence:${selectedGraphNode.key}`);
    if (CLOUD_MODE) {
      if (cloudEvidenceTargetId) {
        void hydrateCloudData("evidence_center_open", cloudEvidenceTargetId);
      }
      document
        .querySelector('[data-testid="production-evidence-detail"]')
        ?.scrollIntoView({ block: "center" });
      return;
    }
    void hydrateProductionData(
      "evidence_center_open",
      productionSampleCandidate?.id || productionScoreTargetId || productionEvidenceDetail?.object_id || null
    );
  }

  function handleNodeKeyDown(event: KeyboardEvent<SVGGElement>, nextSelected: GraphRenderNode) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inspectGraphNode(nextSelected);
    }
  }

  function resetToNvidia() {
    if (CLOUD_MODE) {
      serverReroot(SERVER_DEFAULT_FOCUS.id, SERVER_DEFAULT_FOCUS.label);
      return;
    }
    setFocusKey("nvidia");
    setSelectedKey("nvidia");
    setSelectedProductionNodeKey("");
    setPath(["nvidia"]);
    setGroupListOpen(false);
    setTransitionState("ready");
  }

  function restoreWatchItem(item: HomeWatchItem) {
    setActiveLens(item.savedLens);
    setSemanticZoom(item.savedZoom);
    setCenter(item.key);
    // Opening a watch item marks the change feed as seen (A037).
    window.localStorage.setItem(WATCHLIST_LAST_SEEN_STORAGE_KEY, new Date().toISOString());
    setServerUnreadChanges(0);
  }

  // EEI-F03：搜索提交=选中第一个结果（打开详情），不隐式换中心。
  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (CLOUD_MODE) {
      const firstServerResult = cloudSearchDisplay[0];
      if (firstServerResult) {
        selectServerEntity(firstServerResult);
      }
      return;
    }
    const firstResult = visibleSearchResults[0] ?? homeSearchResults[0];
    inspectNode(firstResult.target);
  }

  useEffect(() => {
    const initialParams = new URLSearchParams(window.location.search);
    const urlState = readWorkspaceStateFromParams(initialParams);
    const sessionState = readWorkspaceStatePayload(
      window.sessionStorage.getItem(WORKSPACE_STATE_STORAGE_KEY)
    );
    const storedSavedView = readSavedViewPayload(window.localStorage.getItem(SAVED_VIEW_STORAGE_KEY));

    // 云模式刷新恢复：subject 为真实实体 UUID 时恢复服务端焦点，
    // 标签待活图返回后回填（EEI-F03 Back/Forward/Refresh 契约）。
    const subjectParam = initialParams.get("subject");
    if (CLOUD_MODE && subjectParam && UUID_PATTERN.test(subjectParam)) {
      setServerFocusEntityId(subjectParam);
      setServerPath(
        subjectParam === SERVER_DEFAULT_FOCUS.id
          ? [{ ...SERVER_DEFAULT_FOCUS }]
          : [{ ...SERVER_DEFAULT_FOCUS }, { id: subjectParam, label: "已发布实体" }]
      );
    }

    if (storedSavedView) {
      setSavedView(storedSavedView);
    }
    if (urlState ?? sessionState) {
      restoringHistoryState.current = true;
      applyWorkspaceState((urlState ?? sessionState)!);
    }

    function handlePopState(event: PopStateEvent) {
      const eventState = event.state as {
        eeiWorkspaceState?: WorkspaceStateInput;
        eeiServerFocus?: { id: string; path: { id: string; label: string }[] };
      } | null;
      // 云模式历史恢复：优先取 history state 里的服务端焦点，退而取 URL。
      if (CLOUD_MODE) {
        const serverFocus = eventState?.eeiServerFocus;
        const urlSubject = new URLSearchParams(window.location.search).get("subject");
        if (serverFocus?.id) {
          restoringHistoryState.current = true;
          setServerFocusEntityId(serverFocus.id);
          setServerPath(
            serverFocus.path?.length ? serverFocus.path : [{ ...SERVER_DEFAULT_FOCUS }]
          );
          setSelectedProductionNodeKey(serverFocus.id);
          setSelectedServerEntity(null);
          return;
        }
        if (urlSubject && UUID_PATTERN.test(urlSubject)) {
          restoringHistoryState.current = true;
          setServerFocusEntityId(urlSubject);
          setSelectedProductionNodeKey(urlSubject);
          setSelectedServerEntity(null);
          return;
        }
      }
      const nextState =
        readWorkspaceStateFromParams(new URLSearchParams(window.location.search)) ??
        (eventState?.eeiWorkspaceState
          ? normalizeWorkspaceState(eventState.eeiWorkspaceState)
          : null);
      if (!nextState) return;
      restoringHistoryState.current = true;
      applyWorkspaceState(nextState);
    }

    window.addEventListener("popstate", handlePopState);
    setStateReady(true);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    void hydrateModelContext(undefined, "initial_hydration");
  }, []);

  useEffect(() => {
    if (!stateReady) return;
    if (hydratedProductionGraphKey.current === productionGraphRequestKey) return;
    hydratedProductionGraphKey.current = productionGraphRequestKey;
    void hydrateProductionGraph("initial_hydration");
  }, [productionGraphRequestKey, stateReady]);

  // 云模式：评分/证据跟随活图与选择自动接入（J-003 两步内见到来源）。
  const cloudEvidenceTargetId = useMemo(() => {
    if (!CLOUD_MODE || !productionGraph?.edges.length) return null;
    const touching = selectedProductionNodeKey
      ? productionGraph.edges.find(
          (edge) =>
            edge.subject_id === selectedProductionNodeKey ||
            edge.object_id === selectedProductionNodeKey
        )
      : undefined;
    return (touching ?? productionGraph.edges[0]).id;
  }, [productionGraph, selectedProductionNodeKey]);
  const hydratedCloudDataKey = useRef("");
  useEffect(() => {
    if (!CLOUD_MODE || !cloudEvidenceTargetId) return;
    if (hydratedCloudDataKey.current === cloudEvidenceTargetId) return;
    hydratedCloudDataKey.current = cloudEvidenceTargetId;
    void hydrateCloudData("graph_hydration", cloudEvidenceTargetId);
  }, [cloudEvidenceTargetId]);
  // 活图返回后，把 URL 恢复时占位的面包屑标签回填成真实实体名。
  useEffect(() => {
    if (!CLOUD_MODE || !productionGraph?.focus) return;
    const focus = productionGraph.focus;
    const focusLabel = focus.canonical_name;
    if (!focusLabel) return;
    setServerPath((current) => {
      const tail = current[current.length - 1];
      if (!tail || tail.id !== focus.id || tail.label === focusLabel) {
        return current;
      }
      return [...current.slice(0, -1), { id: tail.id, label: focusLabel }];
    });
  }, [productionGraph]);

  useEffect(() => {
    if (!stateReady) return;
    const normalized = normalizeWorkspaceState(workspaceState);
    const payload = JSON.stringify(normalized);
    window.sessionStorage.setItem(WORKSPACE_STATE_STORAGE_KEY, payload);
    window.localStorage.setItem(WORKSPACE_STATE_STORAGE_KEY, payload);

    const nextUrl = new URL(window.location.href);
    writeWorkspaceStateParams(nextUrl.searchParams, normalized);
    // 云模式：URL 主体写真实实体 id，历史栈携带服务端焦点+面包屑，
    // Back/Forward/Refresh 恢复的是真实焦点而非样例键。
    if (CLOUD_MODE) {
      nextUrl.searchParams.set("subject", serverFocusEntityId);
    }
    const historyState = {
      eeiWorkspaceState: normalized,
      ...(CLOUD_MODE
        ? { eeiServerFocus: { id: serverFocusEntityId, path: serverPath } }
        : {})
    };
    const shouldReplace = restoringHistoryState.current || !hasWrittenHistoryState.current;
    if (shouldReplace) {
      window.history.replaceState(historyState, "", nextUrl);
      restoringHistoryState.current = false;
      hasWrittenHistoryState.current = true;
      return;
    }
    window.history.pushState(historyState, "", nextUrl);
  }, [stateReady, workspaceState, serverFocusEntityId]);

  useEffect(() => {
    function handleExternalCenterRequest(event: Event) {
      const detail = (event as CustomEvent<string | { focus?: string }>).detail;
      const nextFocus = typeof detail === "string" ? detail : detail?.focus;
      if (nextFocus) {
        requestCenter(nextFocus);
      }
    }

    window.addEventListener("eei:request-center", handleExternalCenterRequest);
    return () => window.removeEventListener("eei:request-center", handleExternalCenterRequest);
  });

  return (
    <WorkspaceContextProvider value={workspaceContextValue}>
    <main
      className="workspace"
      data-active-data-snapshot={analysisContext.dataSnapshot}
      data-active-lens={activeLens}
      data-active-model-version={analysisContext.modelVersion}
      data-active-profile-version={analysisContext.profileVersion}
      data-active-score-snapshot={analysisContext.scoreSnapshot}
      data-active-time={asOf}
      data-analysis-contract={analysisContext.contractVersion}
      data-build-sha={BUILD_SHA}
      data-data-mode={CLOUD_MODE ? "cloud-publication" : "local-fixture"}
      data-focus-key={focusKey}
      data-information-workspace="business-empire-home"
      data-layout-grammar={WORKSPACE_LAYOUT_GRAMMAR}
      data-last-nav-action={navActionStatus}
      data-path={path.join(".")}
      data-path-length={path.length}
      data-reroot-state={transitionState}
      data-selected-node={selectedNode.key}
      data-semantic-zoom={semanticZoom}
      data-server-focus-entity={CLOUD_MODE ? serverFocusEntityId : "none"}
      data-testid="workspace-shell"
      data-viewport-anchor={viewportAnchor}
      data-workspace-model="recursive-enterprise-map"
    >
      <WorkspaceContextContractMarker />
      <WorkspaceNavigationRail
        activeLens={activeLens}
        activeModuleId="business_map"
        onLensTarget={applyWorkspaceNavigationLens}
        onSectionTarget={applyWorkspaceNavigationSection}
      />

      <section className="focusPanel" aria-label="当前主体">
        <div className="subjectHeader">
          <div>
            <p className="eyebrow">关注 · 当前主体</p>
            <h1 data-testid="current-focus-title">
              {CLOUD_MODE
                ? isServerGraphRendered
                  ? serverFocusLabel
                  : productionGraphStatus === "server-error"
                    ? "云端数据暂不可用"
                    : serverFocusLabel
                : scenario.heading}
            </h1>
            <p className="subjectSubtitle">
              {CLOUD_MODE
                ? "已发布关系图 · 事实以官方来源为准"
                : scenario.subtitle}
            </p>
          </div>
          <span className="snapshotTag" data-testid="data-mode-tag">
            {CLOUD_MODE
              ? isServerGraphRendered
                ? "已发布数据"
                : "云端数据未接入"
              : "样例数据"}
          </span>
        </div>
        <dl className="subjectStats" data-testid="home-model-status">
          <div>
            <dt>数据快照</dt>
            <dd>{analysisContext.dataSnapshot}</dd>
          </div>
          <div>
            <dt>评分模型</dt>
            <dd>{analysisContext.profileLabel}</dd>
          </div>
          <div>
            <dt>Budget</dt>
            <dd data-testid="graph-budget">
              {graphViewNodes.length} / {graphViewEdges.length}
            </dd>
          </div>
          {CLOUD_MODE ? (
            <div>
              <dt>上下文刷新代</dt>
              <dd>
                {serverModelContext
                  ? `第 ${serverModelContext.refresh_generation} 代`
                  : "载入中"}
              </dd>
            </div>
          ) : (
            <div>
              <dt>模型校准</dt>
              <dd>
                {homeModelStatus.latestCalibration} / {homeModelStatus.cadenceDays}d /{" "}
                {homeModelStatus.nextScheduledFor}
              </dd>
            </div>
          )}
        </dl>
        <section
          className="modelPreviewPanel"
          data-active-profile-id={serverModelContext?.active_scoring_profile_version_id ?? "local"}
          data-api-base-storage-key={MODEL_CONTEXT_API_BASE_STORAGE_KEY}
          data-client-state={serverModelContext?.client_state ?? "local"}
          data-model-endpoint={modelContextEndpoint || "local"}
          data-model-draft-endpoint={modelDraftEndpoint || "local"}
          data-model-draft-profile-id={draftProfile?.id ?? "none"}
          data-model-draft-reason={modelDraftReason}
          data-model-draft-status={modelDraftStatus}
          data-model-draft-weight-sum={modelDraftWeightSum}
          data-model-refresh-generation={serverModelContext?.refresh_generation ?? 0}
          data-model-refresh-token={serverModelContext?.refresh_token ?? "local"}
          data-model-sync-mode={modelContextSyncMode}
          data-model-sync-reason={modelContextSyncReason}
          data-preview-scope="workspace,graph-table,saved-view,industry-landscape"
          data-preview-state={isPreviewActive ? "preview" : "active"}
          data-preview-storage={ANALYSIS_PREVIEW_STORAGE_KEY}
          data-rollback-profile-id={rollbackProfile?.id ?? "none"}
          data-score-recompute-endpoint={scoreRecomputeEndpoint || "local"}
          data-score-recompute-job-id={scoreRecomputeJob?.id ?? "none"}
          data-score-recompute-job-status={scoreRecomputeJob?.status ?? "none"}
          data-score-recompute-reason={scoreRecomputeReason}
          data-score-recompute-status={scoreRecomputeStatus}
          data-target-profile-id={candidateProfile?.id ?? "none"}
          data-testid="model-preview-panel"
          id="model-preview-panel"
        >
          {/* S12 第二批：人话摘要置前台，机器状态码整体收进〈诊断详情〉。 */}
          <div className="panelHuman">
            <strong>模型工作台</strong>
            <span>
              {zhStatus(modelContextStatus)} · 上下文
              {modelContextSyncMode === "server" ? "已连云端" : "使用本地"}
              {isPreviewActive ? " · 预览生效中" : ""}
            </span>
          </div>
          <details className="diagDetails">
            <summary>诊断详情</summary>
          <div>
            <strong>模型预览</strong>
            <span data-testid="model-preview-status">
              {analysisContext.profileLabel} / {analysisContext.scoreSnapshot}
            </span>
          </div>
          <div>
            <strong>模型激活</strong>
            <span data-testid="model-activation-status">{modelContextStatus}</span>
          </div>
          <div>
            <strong>模型草稿</strong>
            <span data-testid="model-draft-status">{modelDraftStatus}</span>
          </div>
          <div>
            <strong>上下文刷新</strong>
            <span data-testid="model-server-context-state">
              {modelContextSyncMode} / {serverModelContext?.refresh_generation ?? 0} /{" "}
              {serverModelContext?.client_state ?? "local"} / {modelContextSyncReason}
            </span>
          </div>
          <div>
            <strong>评分重算</strong>
            <span data-testid="score-recompute-status">{scoreRecomputeStatus}</span>
          </div>
          </details>
          <div className="modelPreviewActions">
            <button
              data-testid="preview-model-edit"
              disabled={modelDraftStatus === "creating"}
              onClick={() => void createOnlineModelDraft()}
              type="button"
            >
              预览供应链侧重
            </button>
            <button data-testid="clear-model-preview" onClick={clearPreview} type="button">
              清除预览
            </button>
            <button
              data-testid="hydrate-model-context"
              onClick={() => void hydrateModelContext(undefined, "manual_refresh")}
              type="button"
            >
              载入云端上下文
            </button>
            <button
              data-testid="activate-model-profile"
              disabled={!candidateProfile || modelContextStatus === "activating"}
              onClick={() => void activateCandidateModelProfile()}
              type="button"
            >
              激活模型
            </button>
            <button
              data-testid="check-model-refresh"
              disabled={!previousModelRefreshToken && !serverModelContext}
              onClick={() =>
                void hydrateModelContext(
                  previousModelRefreshToken || serverModelContext?.refresh_token,
                  "manual_refresh"
                )
              }
              type="button"
            >
              校验刷新
            </button>
            <button
              data-testid="rollback-model-activation"
              disabled={!rollbackProfile || modelContextStatus === "activating"}
              onClick={() => void rollbackLatestModelActivation()}
              type="button"
            >
              回滚激活
            </button>
            <button
              data-testid="request-score-recompute"
              disabled={
                !serverModelContext ||
                modelContextStatus === "activating" ||
                scoreRecomputeStatus === "enqueueing"
              }
              onClick={() => void enqueueCurrentScoreRecompute()}
              type="button"
            >
              重算评分
            </button>
          </div>
        </section>
        <section
          className="modelPreviewPanel productionGraphPanel"
          data-api-base-storage-key={EXPLORE_API_BASE_STORAGE_KEY}
          data-candidate-total-count={
            productionCandidateSummary?.total ?? productionCandidateCoverage?.total ?? 0
          }
          data-graph-endpoint={productionGraphEndpoint || "local"}
          data-graph-query-version={productionContext?.graph_query_version ?? "local"}
          data-graph-sync-mode={productionGraphSyncMode}
          data-graph-sync-reason={productionGraphSyncReason}
          data-min-independent-sources={
            productionContext?.publication_policy?.minimum_independent_sources ?? 0
          }
          data-published-relationship-count={productionPublishedRelationships?.total ?? 0}
          data-query-as-of={productionGraphRequest.as_of ?? "none"}
          data-query-budget={`${productionGraphBudget.max_nodes}/${productionGraphBudget.max_edges}/${productionGraphBudget.expand_nodes}`}
          data-query-direction={productionGraphRequest.direction}
          data-query-focus-id={productionGraphRequest.focus.object_id}
          data-query-hops={productionGraphRequest.hops}
          data-query-layers={productionGraphRequest.active_layers.join(",")}
          data-relationship-candidate-excluded-count={
            productionCandidateCoverage?.excluded_from_graph_edges ?? 0
          }
          data-relationship-candidates-in-graph={String(
            productionContext?.publication_policy?.relationship_fact_candidates_in_graph_edges ??
              false
          )}
          data-render-source={graphViewMode}
          data-scoring-service-version={productionContext?.scoring_service_version ?? "local"}
          data-server-edge-count={productionGraph?.edges.length ?? 0}
          data-server-node-count={productionGraph?.nodes.length ?? 0}
          data-server-session-id={productionGraph?.session_id ?? "none"}
          data-synthetic-fixture-edge-count={
            productionCoverage?.synthetic_fixture_edges ?? displayEdges.length
          }
          data-testid="production-graph-context"
          data-visible-edge-count={productionCoverage?.visible_edges ?? displayEdges.length}
          data-visible-node-count={productionCoverage?.visible_nodes ?? displayNodes.length}
          data-visual-edge-count={graphViewEdges.length}
          data-visual-node-count={graphViewNodes.length}
        >
          <div className="panelHuman">
            <strong>生产关系图</strong>
            <span>
              {zhStatus(productionGraphStatus)} ·{" "}
              {productionCoverage?.visible_nodes ?? displayNodes.length} 节点 /{" "}
              {productionCoverage?.visible_edges ?? displayEdges.length} 边
            </span>
          </div>
          <details className="diagDetails">
            <summary>诊断详情</summary>
          <div>
            <strong>连接状态</strong>
            <span data-testid="production-graph-status">{productionGraphStatus}</span>
          </div>
          <div>
            <strong>查询契约</strong>
            <span data-testid="production-graph-query">
              {productionGraphRequest.focus.object_id} /{" "}
              {productionGraphRequest.active_layers.join(",")} /{" "}
              {productionGraphRequest.direction} / {productionGraphRequest.hops} hop
            </span>
          </div>
          <div>
            <strong>云端覆盖</strong>
            <span data-testid="production-graph-coverage">
              {productionCoverage?.visible_nodes ?? displayNodes.length} nodes /{" "}
              {productionCoverage?.visible_edges ?? displayEdges.length} edges /{" "}
              {productionCoverage?.source_count ?? 0} sources
            </span>
          </div>
          <dl data-testid="production-graph-contract">
            <div>
              <dt>Budget</dt>
              <dd data-testid="production-graph-budget">
                {productionGraphBudget.max_nodes} / {productionGraphBudget.max_edges} /{" "}
                {productionGraphBudget.expand_nodes}
              </dd>
            </div>
            <div>
              <dt>上下文版本</dt>
              <dd>
                {productionContext?.graph_query_version ?? "local-fixture"} /{" "}
                {productionContext?.scoring_service_version ?? "local-score"}
              </dd>
            </div>
            <div>
              <dt>发布门</dt>
              <dd data-testid="production-graph-publication-gate">
                candidates-in-graph=
                {String(
                  productionContext?.publication_policy
                    ?.relationship_fact_candidates_in_graph_edges ?? false
                )}{" "}
                / min-sources=
                {productionContext?.publication_policy?.minimum_independent_sources ?? 0}
              </dd>
            </div>
            <div>
              <dt>候选事实</dt>
              <dd data-testid="production-graph-candidates">
                excluded={productionCandidateCoverage?.excluded_from_graph_edges ?? 0} / total=
                {productionCandidateSummary?.total ?? productionCandidateCoverage?.total ?? 0}
              </dd>
            </div>
          </dl>
          </details>
          <div className="modelPreviewActions">
            <button
              data-testid="hydrate-production-graph"
              onClick={() => void hydrateProductionGraph("manual_refresh")}
              type="button"
            >
              载入生产关系图
            </button>
          </div>
        </section>
        <section
          className="modelPreviewPanel productionDataPanel"
          data-api-base-storage-key={PRODUCTION_DATA_API_BASE_STORAGE_KEY}
          data-catalog-count={productionCatalogInventory?.catalog_count ?? 0}
          data-catalog-endpoint={productionCatalogEndpoint || "local"}
          data-catalog-source-of-truth-count={
            productionCatalogInventory?.source_of_truth_count ?? 0
          }
          data-catalog-sync-mode={productionCatalogSyncMode}
          data-catalog-sync-reason={productionCatalogSyncReason}
          data-catalog-total-declared-rows={productionCatalogInventory?.total_declared_rows ?? 0}
          data-catalog-version={productionCatalogInventory?.catalog_version ?? "local"}
          data-evidence-detail-count={productionEvidenceDetail?.evidence_count ?? 0}
          data-evidence-endpoint={productionEvidenceEndpoint || "local"}
          data-evidence-object-id={
            productionEvidenceDetail?.object_id ??
            (productionScoreTargetId ||
            productionSampleCandidate?.id ||
            "none")
          }
          data-evidence-source-document-count={productionEvidenceDetail?.source_document_count ?? 0}
          data-evidence-sync-mode={productionEvidenceSyncMode}
          data-evidence-sync-reason={productionEvidenceSyncReason}
          data-score-adjusted-score={productionScoreExplanation?.adjusted_score ?? 0}
          data-score-endpoint={productionScoreEndpoint || "local"}
          data-score-evidence-count={productionScoreExplanation?.evidence.length ?? 0}
          data-score-missing-input-count={productionScoreExplanation?.missing_inputs.length ?? 0}
          data-score-object-id={
            productionScoreExplanation?.object_id ??
            (productionScoreTargetId ||
            productionSampleCandidate?.id ||
            "none")
          }
          data-score-publication-status={
            productionScoreExplanation?.publication_status ??
            productionSampleCandidate?.publication_status ??
            "local"
          }
          data-score-sync-mode={productionScoreSyncMode}
          data-score-sync-reason={productionScoreSyncReason}
          data-scoring-service-version={
            productionScoreExplanation?.scoring_service_version ??
            productionContext?.scoring_service_version ??
            "local"
          }
          data-testid="production-data-context"
        >
          <div className="panelHuman">
            <strong>生产数据</strong>
            <span>
              目录{zhStatus(productionCatalogSyncMode)} · 评分
              {zhStatus(productionScoreSyncMode)} · 证据
              {zhStatus(productionEvidenceSyncMode)}
            </span>
          </div>
          <details className="diagDetails">
            <summary>诊断详情</summary>
          <div>
            <strong>三路状态</strong>
            <span data-testid="production-data-status">
              {productionCatalogStatus} / {productionScoreStatus} / {productionEvidenceStatus}
            </span>
          </div>
          <div>
            <strong>目录清单</strong>
            <span data-testid="production-catalog-status">
              {productionCatalogSyncMode} / {productionCatalogSyncReason}
            </span>
          </div>
          <dl data-testid="production-catalog-contract">
            <div>
              <dt>目录</dt>
              <dd data-testid="production-catalog-count">
                {productionCatalogInventory?.catalog_count ?? 0} / SOT{" "}
                {productionCatalogInventory?.source_of_truth_count ?? 0} / rows{" "}
                {productionCatalogInventory?.total_declared_rows ?? 0}
              </dd>
            </div>
            <div>
              <dt>版本</dt>
              <dd>{productionCatalogInventory?.catalog_version ?? "local-fixture"}</dd>
            </div>
          </dl>
          <div>
            <strong>评分解释</strong>
            <span data-testid="production-score-status">
              {productionScoreSyncMode} / {productionScoreSyncReason}
            </span>
          </div>
          <dl data-testid="production-score-contract">
            <div>
              <dt>候选</dt>
              <dd data-testid="production-score-candidate">
                {productionScoreExplanation?.candidate_key ??
                  productionSampleCandidate?.candidate_key ??
                  "candidate-missing"}{" "}
                / {productionScoreExplanation?.publication_status ?? "local-fixture"}
              </dd>
            </div>
            <div>
              <dt>评分</dt>
              <dd data-testid="production-score-adjusted">
                adjusted={productionScoreExplanation?.adjusted_score ?? 0} / evidence=
                {productionScoreExplanation?.evidence.length ?? 0} / missing=
                {productionScoreExplanation?.missing_inputs.length ?? 0}
              </dd>
            </div>
          </dl>
          <div>
            <strong>证据明细</strong>
            <span data-testid="production-evidence-summary-status">
              {productionEvidenceSyncMode} / {productionEvidenceSyncReason}
            </span>
          </div>
          <dl data-testid="production-evidence-summary-contract">
            <div>
              <dt>文书</dt>
              <dd data-testid="production-evidence-summary-count">
                evidence={productionEvidenceDetail?.evidence_count ?? 0} / docs=
                {productionEvidenceDetail?.source_document_count ?? 0}
              </dd>
            </div>
            <div>
              <dt>接口</dt>
              <dd>{productionEvidenceEndpoint || "local-fixture"}</dd>
            </div>
          </dl>
          </details>
          <div className="modelPreviewActions">
            <button
              data-testid="hydrate-production-data"
              onClick={() =>
                void hydrateProductionData(
                  "manual_refresh",
                  productionSampleCandidate?.id || productionScoreTargetId || null
                )
              }
              type="button"
            >
              载入生产数据
            </button>
          </div>
        </section>
        {CLOUD_MODE ? (
          <div
            className="fixtureDisclosure"
            data-testid="publication-disclosure"
            data-publication-surface="owner-signed-published-facts"
          >
            <strong>发布面数据边界</strong>
            <span>
              本站仅呈现经双源核验与 Owner 签核发布的事实；候选、评审队列与原始文本不出本地。
            </span>
          </div>
        ) : (
          <div
            className="fixtureDisclosure"
            data-testid="fixture-disclosure"
            data-freshness-status={homeFreshness.status}
          >
            <strong>样例数据（未连接生产）</strong>
            <span>样例标注强制可见；不声称任何真实事实（Live facts: disabled）。</span>
          </div>
        )}

        <section
          aria-label="公司八层视图"
          className="workspaceLayerStrip"
          data-layer-count={workspaceLayerItems.length}
          data-required-layers={workspaceLayerItems.map((item) => item.key).join(",")}
          data-testid="workspace-layer-strip"
        >
          <header>
            <span>八层视图</span>
            <small>{workspaceLayerItems.length}/8</small>
          </header>
          <div>
            {workspaceLayerItems.map((item) => (
              <button
                data-layer-key={item.key}
                data-layer-state={item.state}
                disabled={!stateReady || lensForWorkspaceLayer(item.key) === null}
                data-testid={`workspace-layer-${item.key}`}
                key={item.key}
                onClick={() => {
                  const nextLens = lensForWorkspaceLayer(item.key);
                  if (!nextLens) return;
                  applyWorkspaceState({ ...workspaceState, activeLens: nextLens });
                }}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>

        <section
          aria-label="集团结构与业务板块"
          className="structureMatrix"
          data-api-contract="/v1/entities/{entityId}/empire"
          data-commercial-empire-control-claim="false"
          data-separates="legal_group,business_segment,brand,product,facility"
          data-testid="company-structure-matrix"
        >
          <header>
            <span>集团结构</span>
            <small>商业版图不是法律控制声明</small>
          </header>
          <table>
            <thead>
              <tr>
                <th scope="col">对象</th>
                <th scope="col">类型</th>
                <th scope="col">关系</th>
                <th scope="col">控制语义</th>
              </tr>
            </thead>
            <tbody>
              {CLOUD_MODE ? (
                <>
                  <tr
                    data-control-claim="false"
                    data-relationship="focus_entity"
                    data-scope="focus"
                    data-structure-kind="legal_group"
                    data-testid="structure-row-legal_group"
                  >
                    <td>{serverFocusLabel}</td>
                    <td>legal_entity</td>
                    <td>focus_entity</td>
                    <td>当前主体；不是母子控制声明</td>
                  </tr>
                  <tr data-structure-kind="unpublished" data-testid="structure-row-unpublished">
                    <td colSpan={4}>
                      其余结构层（业务板块 / 品牌 / 产品 / 设施）尚未发布——缺席表示无已签核断言，不补零。
                    </td>
                  </tr>
                </>
              ) : (
                structureRows.map((row) => (
                  <tr
                    data-control-claim="false"
                    data-relationship={row.relationship}
                    data-scope={row.scope}
                    data-structure-kind={row.kind}
                    data-testid={`structure-row-${row.kind}`}
                    key={row.kind}
                  >
                    <td>{row.label}</td>
                    <td>{row.typeLabel}</td>
                    <td>{row.relationship}</td>
                    <td>{row.control}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>

        <form
          aria-label="全局搜索"
          className="homeSearch"
          data-endpoint="/v1/entities"
          data-primary-actions-to-focus="2"
          data-supported-types="legal_entity,industry,theme,facility"
          data-testid="home-global-search"
          onSubmit={submitSearch}
          role="search"
        >
          <label htmlFor="global-search-input">全局搜索</label>
          <div className="searchInputRow">
            <Search size={16} aria-hidden="true" />
            <input
              autoComplete="off"
              data-testid="global-search-input"
              id="global-search-input"
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="NVIDIA, TSMC, 半导体"
              type="search"
              value={searchQuery}
            />
            <button data-testid="global-search-submit" type="submit">
              打开
            </button>
          </div>
          <div className="searchResults" data-testid="global-search-results">
            {CLOUD_MODE
              ? cloudSearchDisplay.map((entity) => (
                  <div className="searchResultRow" key={entity.id}>
                    {/* EEI-F03：点结果=选中看详情；换中心是旁边的显式按钮。 */}
                    <button
                      data-object-type="entity"
                      data-testid={`search-result-${entity.id}`}
                      onClick={() => selectServerEntity(entity)}
                      type="button"
                    >
                      <span>{entity.canonical_name}</span>
                      <small>
                        {entity.entity_type.replaceAll("_", " ")} · {entity.status}
                      </small>
                    </button>
                    <button
                      className="searchRerootAction"
                      data-testid={`search-reroot-${entity.id}`}
                      disabled={entity.id === serverFocusEntityId}
                      onClick={() => serverReroot(entity.id, entity.canonical_name)}
                      title={`以 ${entity.canonical_name} 为中心`}
                      type="button"
                    >
                      以它为中心
                    </button>
                  </div>
                ))
              : visibleSearchResults.map((result) => (
                  <div className="searchResultRow" key={result.key}>
                    <button
                      data-object-type={result.objectType}
                      data-testid={`search-result-${result.key}`}
                      onClick={() => inspectNode(result.target)}
                      type="button"
                    >
                      <span>{result.label}</span>
                      <small>{result.description}</small>
                    </button>
                    <button
                      className="searchRerootAction"
                      data-testid={`search-reroot-${result.key}`}
                      disabled={result.target === focusKey}
                      onClick={() => setCenter(result.target)}
                      title={`以 ${result.label} 为中心`}
                      type="button"
                    >
                      以它为中心
                    </button>
                  </div>
                ))}
          </div>
        </form>

        <section className="homeSection" aria-label="行业入口" data-testid="home-industries">
          <header>
            <span>行业</span>
            <a data-testid="home-industry-map-link" href="/industries">
              地图
            </a>
          </header>
          <div className="compactList">
            {CLOUD_MODE ? (
              <p className="honestEmpty" data-testid="home-industries-empty">
                行业目录尚未发布——发布面暂不含行业分类断言，不以样例充数。
              </p>
            ) : (
              homeIndustries.map((industry) => (
                <button
                  data-testid={`home-industry-${industry.key}`}
                  key={industry.key}
                  onClick={() => setCenter(industry.target)}
                  type="button"
                >
                  <span>{industry.name}</span>
                  <small>
                    {industry.entityCount} entities / {industry.recentChangeCount} changes
                  </small>
                </button>
              ))
            )}
          </div>
        </section>

        <section
          className="homeSection"
          aria-label="关注主体"
          data-testid="home-watchlist"
          id="home-watchlist"
        >
          <header>
            <span>我的关注</span>
            <small data-testid="watchlist-unread-summary">
              {serverUnreadChanges === null
                ? CLOUD_MODE
                  ? "未读数载入中"
                  : `${homeWatchItems.reduce((total, item) => total + item.unread, 0)} unread (fixture)`
                : `${serverUnreadChanges} unread · server`}
            </small>
          </header>
          <div className="watchlistStack">
            {CLOUD_MODE ? (
              <p className="honestEmpty" data-testid="home-watchlist-empty">
                云端关注列表为空——未读数来自真实变化流（
                {serverUnreadChanges ?? 0} 条），不展示样例关注项。
              </p>
            ) : (
              homeWatchItems.map((item) => (
                <button
                  className={item.key === focusKey ? "watchItem current" : "watchItem"}
                  data-testid={`home-watchlist-${item.key}`}
                  key={item.key}
                  onClick={() => restoreWatchItem(item)}
                  type="button"
                >
                  <span>{item.label}</span>
                  <small data-testid={`watchlist-saved-state-${item.key}`}>
                    {item.unread} unread / {item.state} / {item.savedLens} / {item.savedZoom} /{" "}
                    {item.profile}
                  </small>
                  <Route size={16} aria-hidden="true" />
                </button>
              ))
            )}
          </div>
        </section>

        <section
          className="homeSection"
          aria-label="最近探索"
          data-testid="home-recent-explorations"
          id="home-recent-explorations"
        >
          <header>
            <span>探索记录</span>
            <small>{homeRecentExplorations.length}</small>
          </header>
          <div className="compactList">
            {CLOUD_MODE ? (
              serverPath.length > 1 ? (
                serverPath.slice(0, -1).map((entry) => (
                  <button
                    data-testid={`home-recent-${entry.id}`}
                    key={entry.id}
                    onClick={() => serverReroot(entry.id, entry.label)}
                    type="button"
                  >
                    <span>{entry.label}</span>
                    <small>本次会话探索路径</small>
                  </button>
                ))
              ) : (
                <p className="honestEmpty" data-testid="home-recent-empty">
                  本次会话暂无探索记录。
                </p>
              )
            ) : (
              homeRecentExplorations.map((entry) => (
                <button
                  data-testid={`home-recent-${entry.key}`}
                  key={entry.key}
                  onClick={() => setCenter(entry.key)}
                  type="button"
                >
                  <span>{entry.label}</span>
                  <small>{entry.path}</small>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="homeSection" aria-label="重要变化" data-testid="home-changes">
          <header>
            <span>重要变化</span>
            <small>{CLOUD_MODE ? serverChangeRows.length : homeChanges.length}</small>
          </header>
          <div className="compactList">
            {CLOUD_MODE ? (
              serverChangeRows.length ? (
                serverChangeRows.slice(0, 5).map((change) => (
                  <div
                    className="changeRow"
                    data-testid={`home-change-${change.id}`}
                    key={change.id}
                  >
                    <span>
                      已发布关系：{change.new_value?.subject_name ?? "?"} →{" "}
                      {change.new_value?.object_name ?? "?"}
                    </span>
                    <small>
                      {(change.new_value?.relationship_type ?? "").replaceAll("_", " ")} ·{" "}
                      {change.created_at ? change.created_at.slice(0, 10) : "无日期"}
                    </small>
                  </div>
                ))
              ) : (
                <p className="honestEmpty" data-testid="home-changes-empty">
                  自上次查看以来暂无新发布。
                </p>
              )
            ) : null}
            {!CLOUD_MODE && homeChanges.map((change) => (
              <button
                data-testid={`home-change-${change.key}`}
                key={change.key}
                onClick={() => setCenter(change.target)}
                type="button"
              >
                <span>{change.label}</span>
                <small>{change.severity}</small>
              </button>
            ))}
          </div>
        </section>

        <div
          className="freshnessGrid"
          data-document-date={freshnessValue(freshnessDisplay.latestDocumentDate)}
          data-endpoint={productionFreshnessEndpoint || "local"}
          data-last-attempt-at={freshnessValue(freshnessDisplay.lastAttemptAt)}
          data-last-failure-at={freshnessValue(freshnessDisplay.lastFailureAt)}
          data-last-success-at={freshnessValue(freshnessDisplay.lastSuccessAt)}
          data-report-period-end={freshnessValue(freshnessDisplay.latestReportPeriodEnd)}
          data-sync-mode={productionFreshnessSyncMode}
          data-sync-reason={productionFreshnessSyncReason}
          data-testid="home-freshness"
        >
          <span data-testid="source-freshness-status">{freshnessDisplay.status}</span>
          <span data-testid="source-freshness-code">{freshnessDisplay.sourceCode}</span>
          <span data-testid="source-freshness-attempt">
            抓取 {freshnessText(freshnessDisplay.lastAttemptAt)}
          </span>
          <span data-testid="source-freshness-success">
            成功 {freshnessText(freshnessDisplay.lastSuccessAt)}
          </span>
          <span data-testid="source-freshness-failure">
            失败 {freshnessText(freshnessDisplay.lastFailureAt)}
          </span>
          <span data-testid="source-freshness-document-date">
            文书 {freshnessText(freshnessDisplay.latestDocumentDate)}
          </span>
          <span data-testid="source-freshness-report-period">
            报告期 {freshnessText(freshnessDisplay.latestReportPeriodEnd)}
          </span>
          <span>{freshnessDisplay.sourceCount} 个来源</span>
          <span>{freshnessDisplay.sourceDocumentCount} 份文书</span>
          <span>{analysisContext.dataSnapshot}</span>
        </div>
      </section>

      <section className="canvas" aria-label="商业版图" data-testid="visual-canvas">
        <div className="canvasTopbar">
          <div>
            <p className="eyebrow">黄金纵切</p>
            <h2>半导体与 AI 基建生态</h2>
          </div>
          {/* S9PCT02 V7 Ask bar (D4): an in-graph entity name reroots the
              canvas; anything else assembles a context prompt and opens
              ChatGPT new chat - zero API integration by owner decision. */}
          <form
            className="askBar"
            data-last-ask-action={lastAskAction}
            data-testid="ask-bar"
            onSubmit={(event) => {
              event.preventDefault();
              const query = askInput.trim();
              if (!query) {
                return;
              }
              const matched = graphViewNodes.find((node) =>
                node.label.toLowerCase().includes(query.toLowerCase())
              );
              if (matched) {
                setLastAskAction(`reroot:${matched.key}`);
                inspectGraphNode(matched);
                setAskInput("");
                return;
              }
              const contextPrompt = [
                `你是我的商业帝国研究助手。当前 EEI 工作台上下文：`,
                `- 聚焦对象：${selectedGraphNode.label}`,
                `- 分析镜头：${activeLens} · 语义缩放 ${semanticZoom}${CLOUD_MODE ? "" : ` · as-of ${asOf}`}`,
                productionScoreExplanation
                  ? `- 焦点候选：${productionScoreExplanation.candidate_key}（独立源 ${productionScoreExplanation.source_threshold.independent_source_count}/${productionScoreExplanation.source_threshold.minimum_independent_sources}，${productionScoreExplanation.publication_status}）`
                  : `- 焦点候选：未加载评分解释`,
                `- 数据快照：${analysisContext.dataSnapshot}`,
                `我的问题：${query}`
              ].join("\n");
              setLastAskAction("chatgpt:new-chat");
              window.open(
                `https://chatgpt.com/?q=${encodeURIComponent(contextPrompt)}`,
                "_blank",
                "noopener"
              );
              setAskInput("");
            }}
          >
            <input
              aria-label="Ask 栏"
              data-testid="ask-bar-input"
              onChange={(event) => setAskInput(event.target.value)}
              placeholder="输入实体名直查，或提问跳转 ChatGPT"
              value={askInput}
            />
            <button data-testid="ask-bar-submit" type="submit">
              Ask
            </button>
          </form>
          <div className="lensBar" aria-label="分析视角">
            {lensItems.map((lens) => (
              <button
                aria-pressed={activeLens === lens.key}
                className={activeLens === lens.key ? "lens active" : "lens"}
                data-testid={`lens-${lens.key}`}
                key={lens.key}
                onClick={() => setActiveLens(lens.key)}
                type="button"
              >
                {lens.label}
              </button>
            ))}
          </div>
        </div>
        <div
          className="zoomBar"
          aria-label="语义缩放"
          data-testid="semantic-zoom-controls"
          data-zoom-contract="L0,L1,L2,L3"
        >
          {semanticZoomItems.map((item) => (
            <button
              aria-pressed={semanticZoom === item.key}
              className={semanticZoom === item.key ? "zoomControl active" : "zoomControl"}
              data-testid={`zoom-${item.key}`}
              key={item.key}
              onClick={() => setSemanticZoom(item.key)}
              title={item.title}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* 样例三档时间轴只属于本地样例模式；云模式的时间维度由右缘
            真实逐年申报纵轴承担（EEI-F02：不再展示样例快照日期）。 */}
        {!CLOUD_MODE ? (
          <div
            className="timelineBar"
            aria-label="时间演变"
            data-active-as-of={asOf}
            data-testid="timeline-controls"
            id="timeline-controls"
          >
            {timelineItems.map((item) => (
              <button
                aria-pressed={asOf === item.key}
                className={asOf === item.key ? "timelineControl active" : "timelineControl"}
                data-testid={`timeline-${item.key}`}
                key={item.key}
                onClick={() => setAsOf(item.key)}
                type="button"
              >
                <span>{item.label}</span>
                <small>{item.key}</small>
              </button>
            ))}
          </div>
        ) : null}


        <div className="stageRail" aria-label="供应链阶段覆盖">
          {stageRows.map((stage) => (
            <span className={`stagePill ${stage.side}`} key={stage.id}>
              {stage.id} {stage.name}
            </span>
          ))}
        </div>

        <div
          className="mapSurface"
          data-testid="ecosystem-map-surface"
          data-visual-surface="empire-map"
        >
          {/* S9PBT02 V5: context KPI bar - every number mirrors the score
              explanation panel state (single source, consistency by
              construction); clicking jumps to the explanation. */}
          {productionScoreExplanation ? (
            <button
              className="contextKpiBar"
              data-testid="context-kpi-bar"
              data-kpi-source="production-score-explanation"
              onClick={() =>
                document
                  .querySelector('[data-testid="production-score-candidate"]')
                  ?.scrollIntoView({ block: "center" })
              }
              type="button"
            >
              <span data-testid="kpi-candidate">
                {productionScoreExplanation.candidate_key ??
                  productionScoreExplanation.relationship_type.replaceAll("_", " ")}
              </span>
              <span data-testid="kpi-sources">
                独立源 {productionScoreExplanation.source_threshold.independent_source_count}/
                {productionScoreExplanation.source_threshold.minimum_independent_sources}
                {productionScoreExplanation.source_threshold.met ? " ✓" : " ✗"}
              </span>
              <span data-testid="kpi-review">
                {productionScoreExplanation.review_status}
              </span>
              <span data-testid="kpi-publication">
                {productionScoreExplanation.publication_status}
              </span>
              <span className="kpiHint">点击查看解释</span>
            </button>
          ) : null}
          {/* S9PBT01 V4: legend inventory + GAPS badge (real unknown semantics). */}
          <aside className="empireLegend" data-testid="empire-legend">
            <p className="empireLegendTitle">图例 · 库存</p>
            <ul>
              {legendInventory.map((item) => (
                <li data-testid={`legend-zone-${item.zone}`} key={item.zone}>
                  <span className={`legendDot ${item.zone}`} aria-hidden />
                  <span className="legendLabel">{item.label}</span>
                  <span className="legendCount">{item.count}</span>
                </li>
              ))}
            </ul>
            <p
              className="empireGaps"
              data-testid="empire-gaps-badge"
              title="按十六阶段供应链断言覆盖计算：缺席=无断言≠真实为空"
            >
              GAPS{" "}
              {supplyGapsPct === null
                ? "未知（未连接 API）"
                : `${supplyGapsPct}% · ${supplyGapsDetail}`}
            </p>
          </aside>
          {transitionState === "loading" ? (
            <div className="canvasOverlay" data-testid="transition-loading">
              Loading relationship map
            </div>
          ) : null}
          {transitionState === "fallback" ? (
            <div className="canvasOverlay warning" data-testid="transition-fallback">
              Canvas preserved
            </div>
          ) : null}
          {/* EEI-F01/F02：云模式画布诚实状态（载入/错误/空），零样例回退。 */}
          {CLOUD_MODE && !isServerGraphRendered ? (
            <div
              className="canvasOverlay cloudGraphState"
              data-graph-status={productionGraphStatus}
              data-testid="cloud-graph-state"
            >
              {productionGraphStatus === "server-error" ? (
                <>
                  <strong>云端图谱暂不可用</strong>
                  <span>{productionGraphSyncReason}</span>
                  <div className="cloudGraphActions">
                    <button
                      data-testid="cloud-graph-retry"
                      onClick={() => void hydrateProductionGraph("manual_retry")}
                      type="button"
                    >
                      重试
                    </button>
                    <button
                      data-testid="cloud-graph-home"
                      onClick={resetToNvidia}
                      type="button"
                    >
                      回到 NVIDIA
                    </button>
                  </div>
                </>
              ) : productionGraphStatus === "server-hydrated" ? (
                <>
                  <strong>该主体暂无已发布关系</strong>
                  <span>缺席表示无已签核断言，不是真实为空。</span>
                  <div className="cloudGraphActions">
                    <button
                      data-testid="cloud-graph-home"
                      onClick={resetToNvidia}
                      type="button"
                    >
                      回到 NVIDIA
                    </button>
                  </div>
                </>
              ) : (
                <strong>正在载入已发布图谱…</strong>
              )}
            </div>
          ) : null}
          {CLOUD_MODE ? (
            <div
              className="changeOverlay"
              data-as-of={publishedContextMeta.as_of ?? "none"}
              data-testid="change-overlay"
              data-timeline-mode="published-snapshot"
            >
              <strong>发布快照 · {analysisContext.dataSnapshot}</strong>
              <span>
                数据截至 {(publishedContextMeta.as_of ?? "").slice(0, 10) || "载入中"}
              </span>
              <small>
                发布于 {(publishedContextMeta.published_at ?? "").slice(0, 10) || "载入中"}
                ；一次发布一个原子快照。
              </small>
            </div>
          ) : (
            <div
              className="changeOverlay"
              data-as-of={asOf}
              data-testid="change-overlay"
              data-timeline-mode="as-of-snapshot"
            >
              <strong>快照 · {asOf}</strong>
              <span>{currentTimeline.change}</span>
              <small>{currentTimeline.overlay}；非实时快照。</small>
            </div>
          )}
          {/* S12PB 右侧竖向时间轴（Owner 指定形态）：2016→今年份纵列悬浮于画布
              右缘，拖动/滚轮/点选自由选年，默认当前年；数据为真实逐年官方申报
              纵深（诚实空态，不造年份）。原 S9PCT01 契约 testid 全保留。 */}
          <div
            aria-label="历史纵深时间轴（右侧竖轴，滑动选年）"
            aria-orientation="vertical"
            className="historyScrubber"
            data-testid="empire-history-scrubber"
            onPointerDown={handleHistoryPointerDown}
            onPointerMove={handleHistoryPointerMove}
            onWheel={(event) => stepHistoryYear(event.deltaY > 0 ? 1 : -1)}
          >
            {historyYears === null ? (
              <p className="historyEmpty" data-testid="history-scrubber-empty">
                历史纵深未连接 — 连接 EEI API 后显示 2016→今逐年官方申报深度。
              </p>
            ) : (
              <>
                <div className="historyRail" ref={historyRailRef}>
                  {historyYears.map((item) => (
                    <button
                      aria-pressed={historyYearSelected === item.year}
                      className={
                        historyYearSelected === item.year
                          ? "historyYear active"
                          : "historyYear"
                      }
                      data-testid={`history-year-${item.year}`}
                      key={item.year}
                      onClick={() => setHistoryYearSelected(item.year)}
                      title={`${item.year} 年：${item.filings} 份官方申报`}
                      type="button"
                    >
                      <small>{item.year}</small>
                      <span
                        className="historyBar"
                        style={{
                          width: `${Math.max(6, (item.filings / historyMaxFilings) * 26)}px`
                        }}
                      />
                    </button>
                  ))}
                </div>
                <p className="historyDetail" data-testid="history-scrubber-detail">
                  {historyYearSelected
                    ? `${historyYearSelected} 年 · ${
                        historyYears.find((item) => item.year === historyYearSelected)
                          ?.filings ?? 0
                      } 份官方申报`
                    : "滑动或点选年份，查看该年申报纵深"}
                </p>
              </>
            )}
          </div>
        </div>

        {/* S13：svg 悬浮层是 .canvas 的直接子元素——脱离 mapSurface 的
            堆叠上下文，才能盖在控制条带之上（节点可点、空白穿透）。 */}
        <svg
            className={`ecosystemMap zoom-${semanticZoom}`}
            data-hover-depth={hoverNeighborhood ? "on" : "off"}
            data-render-source={graphViewMode}
            data-semantic-zoom={semanticZoom}
            ref={empireMapRef}
            data-server-rendered-edge-count={graphViewMode === "server" ? graphViewEdges.length : 0}
            data-server-rendered-node-count={graphViewMode === "server" ? graphViewNodes.length : 0}
            data-testid="ecosystem-map-svg"
            viewBox="0 0 760 480"
            role="img"
            aria-label={
              graphViewMode === "server"
                ? "EEI 生产关系图（服务端递归展开）"
                : graphViewMode === "cloud-empty"
                  ? "EEI 云端图谱（等待已发布数据）"
                  : "NVIDIA 供应链样例图（本地样例数据）"
            }
          >
            <defs>
              <marker
                id="arrow"
                markerHeight="8"
                markerWidth="8"
                orient="auto"
                refX="7"
                refY="4"
                viewBox="0 0 8 8"
              >
                <path d="M0,0 L8,4 L0,8 z" />
              </marker>
              <radialGradient id="sunGlow">
                <stop offset="0%" stopColor="var(--glow-core)" />
                <stop offset="60%" stopColor="var(--glow-soft)" />
                <stop offset="100%" stopColor="transparent" />
              </radialGradient>
              {/* S12 光学：光束辉光滤镜 + 每 zone 玻璃球/光晕渐变（stop 颜色走
                  主题 token，deep-space 与 daylight 双主题同一套 defs）。 */}
              <filter height="200%" id="beamGlow" width="200%" x="-50%" y="-50%">
                <feGaussianBlur stdDeviation="3.4" />
              </filter>
              {EMPIRE_ZONES.map((zone) => (
                <Fragment key={zone}>
                  <radialGradient cx="32%" cy="26%" id={`orb-${zone}`} r="82%">
                    <stop offset="0%" style={{ stopColor: "var(--orb-specular)" }} />
                    <stop offset="24%" style={{ stopColor: `var(--orb-${zone}-hi)` }} />
                    <stop offset="64%" style={{ stopColor: `var(--orb-${zone}-mid)` }} />
                    <stop offset="100%" style={{ stopColor: `var(--orb-${zone}-lo)` }} />
                  </radialGradient>
                  <radialGradient id={`halo-${zone}`}>
                    <stop
                      offset="0%"
                      style={{ stopColor: `var(--orb-${zone}-mid)`, stopOpacity: 0.42 }}
                    />
                    <stop
                      offset="68%"
                      style={{ stopColor: `var(--orb-${zone}-mid)`, stopOpacity: 0.12 }}
                    />
                    <stop
                      offset="100%"
                      style={{ stopColor: `var(--orb-${zone}-mid)`, stopOpacity: 0 }}
                    />
                  </radialGradient>
                </Fragment>
              ))}
            </defs>
            {/* S9PAT02 orbital belts: purely decorative rings behind the graph. */}
            <g aria-hidden className="orbitRings" data-testid="empire-orbit-rings">
              {orbitRingRadii.map((radius) => (
                <circle
                  className="orbitRing"
                  cx={380}
                  cy={240}
                  key={radius}
                  r={radius}
                />
              ))}
              {/* S14 批次2：金核绽放光芒 rays（慢转+微闪，reduced-motion 静止）。 */}
              <g className="sunRays" data-testid="empire-sun-rays">
                {SUN_RAYS.map((ray, i) => (
                  <line
                    className={`sunRay${ray.long ? " long" : ""}`}
                    key={i}
                    style={{ "--ray-i": i } as CSSProperties}
                    x1={ray.x1}
                    y1={ray.y1}
                    x2={ray.x2}
                    y2={ray.y2}
                  />
                ))}
              </g>
              <circle className="sunHalo" cx={380} cy={240} r={64} fill="url(#sunGlow)" />
            </g>
            {/* S14 视频复刻：稀疏 travelling 粒子层（装饰，aria-hidden）。 */}
            <g aria-hidden className="ambientParticles" data-testid="ambient-particles">
              {AMBIENT_PARTICLES.map((p, i) => (
                <circle
                  className="ambientParticle"
                  cx={p.x}
                  cy={p.y}
                  key={i}
                  r={p.r}
                  style={
                    {
                      "--p-i": i,
                      "--p-dx": `${p.dx}px`,
                      "--p-dy": `${p.dy}px`
                    } as CSSProperties
                  }
                />
              ))}
            </g>
            {graphViewEdges.map((edge, edgeIndex) => {
              const source = graphViewNodeByKey.get(edge.from);
              const target = graphViewNodeByKey.get(edge.to);
              if (!source || !target) return null;
              const midX = (source.x + target.x) / 2;
              const midY = (source.y + target.y) / 2 - 10;
              const lensState = activeLens === "all" || edge.lens === activeLens ? "active" : "faded";
              const hoverNear =
                hoverNeighborhood?.has(edge.from) && hoverNeighborhood?.has(edge.to);
              // S12 光学：与焦点太阳相连的边升级为锥形金色光束（宽辉光底层），
              // 其余保持细丝。两层线叠加，契约层（.edge testid/pathLength）不动。
              const isSunBeam = source.zone === "focus" || target.zone === "focus";
              // S14 视频复刻：连接器由直线升级为弯曲发光曲线（样例视频语言）。
              // 控制点取中点沿边法向偏移；方向由 from<to 决定，稳定且 SSR 安全
              // （坐标取整避免 hydration 漂移）。d 供 .edge/.edgeBeamGlow/光流共用。
              const edgeCurveD = curvedEdgePath(source.x, source.y, target.x, target.y, edge.from < edge.to);
              return (
                <g
                  className={`edgeGroup ${lensState}${hoverNear ? " hoverNear" : ""}${
                    isSunBeam ? " sunBeam" : ""
                  }`}
                  data-lens-state={lensState}
                  data-render-source={edge.source}
                  data-testid={`edge-group-${edge.from}-${edge.to}`}
                  key={edge.id}
                >
                  {/* A168：feGaussianBlur 滤镜面只给太阳束；细丝以宽描边低
                      透明近似辉光，避免逐边滤镜拖慢首屏。 */}
                  <path
                    aria-hidden
                    className="edgeBeamGlow"
                    d={edgeCurveD}
                    fill="none"
                    filter={isSunBeam ? "url(#beamGlow)" : undefined}
                  />
                  <path
                    className="edge"
                    d={edgeCurveD}
                    data-testid={`edge-${edge.from}-${edge.to}`}
                    fill="none"
                    markerEnd="url(#arrow)"
                    pathLength={1}
                  />
                  {/* S14 光感：光沿连接器行进（stroke-dashoffset 合成层动画，
                      仅焦点束以守 A168；reduced-motion 静止）。 */}
                  {isSunBeam ? (
                    <path
                      aria-hidden
                      className="edgeFlow"
                      d={edgeCurveD}
                      fill="none"
                      pathLength={1}
                      style={{ "--flow-i": edgeIndex } as CSSProperties}
                    />
                  ) : null}
                  <text
                    className="edgeLabel"
                    data-testid={`edge-label-${edge.from}-${edge.to}`}
                    textAnchor="middle"
                    x={midX}
                    y={midY}
                  >
                    {edge.label}
                  </text>
                  {semanticZoom === "L2" || semanticZoom === "L3" ? (
                    <text className="edgeEvidence" textAnchor="middle" x={midX} y={midY + 16}>
                      {edge.source === "server" ? `证据 ${edge.evidenceCount} 条` : "样例证据"}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {graphViewNodes.map((mapNode, nodeIndex) => {
              const lensState =
                activeLens === "all" || activeEdgeKeys.has(mapNode.key) ? "active" : "faded";
              const isSelected = mapNode.key === selectedGraphNode.key;
              const isFocus =
                mapNode.key ===
                (graphViewMode === "server" ? productionGraphRequest.focus.object_id : focusKey);
              const hoverNear = hoverNeighborhood?.has(mapNode.key);
              return (
              <g
                aria-label={`Inspect ${mapNode.label}`}
                aria-pressed={isSelected}
                className={`node ${mapNode.zone} ${lensState}${isSelected ? " selected" : ""}${
                  hoverNear ? " hoverNear" : ""
                }${isFocus ? " focus" : ""}`}
                data-aggregate-count={mapNode.aggregateCount}
                data-lens-state={lensState}
                data-node-kind={mapNode.aggregateCount ? "aggregate" : "entity"}
                data-render-source={mapNode.source}
                data-testid={`graph-node-${mapNode.key}`}
                key={mapNode.key}
                onClick={() => inspectGraphNode(mapNode)}
                onKeyDown={(event) => handleNodeKeyDown(event, mapNode)}
                onMouseEnter={() => setHoveredNodeKey(mapNode.key)}
                onMouseLeave={() => setHoveredNodeKey(null)}
                role="button"
                style={{ "--stagger-i": nodeIndex } as CSSProperties}
                tabIndex={0}
                transform={`translate(${mapNode.x} ${mapNode.y})`}
              >
                <circle
                  aria-hidden
                  className="orbHalo"
                  fill={`url(#halo-${mapNode.zone})`}
                  r={isFocus ? 62 : 46}
                />
                {isFocus ? (
                  <g aria-hidden className="focusOrbitDots" data-testid="focus-orbit-dots">
                    <circle className="medallionRing" r={46} />
                    <circle className="medallionRing dashed" r={52} />
                    {FOCUS_ORBIT_DOTS.map((dot, dotIndex) => (
                      <circle
                        className="focusOrbitDot"
                        cx={dot.x}
                        cy={dot.y}
                        key={dotIndex}
                        r={dotIndex % 3 === 0 ? 1.9 : 1.2}
                      />
                    ))}
                  </g>
                ) : null}
                <circle className="orbBody" r={isFocus ? 40 : 31} />
                <text textAnchor="middle" dominantBaseline="middle">
                  {mapNode.aggregateCount ? `${mapNode.shortLabel} ${mapNode.aggregateCount}` : mapNode.shortLabel}
                </text>
                <text className="nodeStage" textAnchor="middle" y={52}>
                  {mapNode.stage}
                </text>
                {semanticZoom === "L3" ? (
                  <text className="nodeRole" textAnchor="middle" y={68}>
                    {mapNode.role}
                  </text>
                ) : null}
              </g>
              );
            })}
        </svg>

        <div className="historyControls" aria-label="历史恢复">
          <button data-testid="app-back" onClick={browserBack} type="button">
            <ChevronLeft size={16} aria-hidden="true" />
            <span>返回</span>
          </button>
        </div>

        <ol className="breadcrumb" aria-label="探索路径" data-testid="reroot-breadcrumb">
          {CLOUD_MODE
            ? serverPath.map((entry, index) => (
                <li key={`${entry.id}-${index}`}>
                  <button
                    aria-current={index === serverPath.length - 1 ? "page" : undefined}
                    data-testid={`breadcrumb-subject-${entry.id}-${index}`}
                    onClick={() => serverReroot(entry.id, entry.label)}
                    type="button"
                  >
                    {entry.label}
                  </button>
                </li>
              ))
            : path.map((key, index) => (
                <li key={`${key}-${index}`}>
                  <button
                    aria-current={index === path.length - 1 ? "page" : undefined}
                    data-testid={`breadcrumb-subject-${key}-${index}`}
                    onClick={() => applyPathSubject(index)}
                    type="button"
                  >
                    {key === "nvidia" ? "NVIDIA" : entityLabels[key]}
                  </button>
                </li>
              ))}
        </ol>

        <section
          className="crossIndustryReroot"
          data-cross-industry={isCrossIndustryPath}
          data-industry-path={industryPath.map((item) => item.key).join(">")}
          data-testid="cross-industry-reroot-notice"
        >
          <strong>Cross-industry path</strong>
          <span>{industryPathLabel}</span>
          <small>
            {isCrossIndustryPath
              ? `已从 ${industryPath[0]?.label} 进入 ${industryPath[industryPath.length - 1]?.label}`
              : "当前路径仍在单一行业内"}
          </small>
        </section>
      </section>

      <aside
        className="inspector"
        aria-label="证据与状态"
        data-testid="evidence-center"
        id="evidence-center"
      >
        <div className="inspectorHeader">
          <p className="eyebrow">证据中心</p>
          <h2>关系路径</h2>
        </div>

        <section
          className="selectedNodeCard"
          aria-label="当前选择节点"
          data-render-source={selectedGraphNode.source}
          data-selected-graph-node={selectedGraphNode.key}
          data-testid="selected-node-card"
        >
          <span className={`nodeToken ${selectedGraphNode.zone}`}>{selectedGraphNode.zone}</span>
          <h3 data-testid="selected-node-title">{selectedGraphNode.label}</h3>
          <dl>
            <div>
              <dt>环节</dt>
              <dd>{selectedGraphNode.stage}</dd>
            </div>
            <div>
              <dt>角色</dt>
              <dd>{selectedGraphNode.role}</dd>
            </div>
            <div>
              <dt>当前主体</dt>
              <dd>{CLOUD_MODE ? serverFocusLabel : scenario.heading}</dd>
            </div>
          </dl>
        </section>

        <section
          className="savedViewPanel"
          data-api-base-storage-key={SAVED_VIEW_API_BASE_STORAGE_KEY}
          data-data-snapshot={savedView.dataSnapshot}
          data-model-version={savedView.modelVersion}
          data-profile-version={savedView.profileVersion}
          data-saved-view-id={savedView.id}
          data-server-endpoint={savedView.serverEndpoint ?? ""}
          data-server-id={savedView.serverId ?? ""}
          data-server-version={savedView.serverVersion ?? ""}
          data-saved-view-version={savedView.version}
          data-score-snapshot={savedView.scoreSnapshot}
          data-sync-mode={savedView.syncMode}
          data-sync-reason={savedView.syncReason}
          data-testid="saved-view-panel"
          data-workspace-key={savedView.workspaceKey}
        >
          <header>
            <p className="eyebrow">保存视图</p>
            <strong data-testid="saved-view-status">{zhStatus(savedViewStatus)}</strong>
          </header>
          <dl data-testid="saved-view-contract">
            <div>
              <dt>主体</dt>
              <dd>{entityLabels[savedView.focusKey]}</dd>
            </div>
            <div>
              <dt>透镜 / 时间</dt>
              <dd>
                {savedView.activeLens} / {savedView.asOf}
              </dd>
            </div>
            <div>
              <dt>筛选</dt>
              <dd>{savedView.filters}</dd>
            </div>
            <div>
              <dt>布局</dt>
              <dd>{savedView.layout}</dd>
            </div>
            <div>
              <dt>备注</dt>
              <dd>{savedView.notes}</dd>
            </div>
          </dl>
          <div className="savedViewActions">
            <button data-testid="save-current-view" onClick={saveCurrentView} type="button">
              <Save size={16} aria-hidden="true" />
              <span>保存</span>
            </button>
            <button data-testid="restore-saved-view" onClick={restoreSavedView} type="button">
              <RotateCcw size={16} aria-hidden="true" />
              <span>恢复</span>
            </button>
            {savedViewStatus === "server-conflict" && savedView.serverId ? (
              <button
                data-testid="resolve-saved-view-conflict"
                onClick={resolveSavedViewConflict}
                type="button"
              >
                <RotateCcw size={16} aria-hidden="true" />
                <span>获取最新</span>
              </button>
            ) : null}
          </div>
        </section>

        <ol className="pathList">
          {CLOUD_MODE
            ? graphViewEdges.slice(0, 4).map((edge) => (
                <li key={edge.id}>
                  <strong>{`${graphViewNodeByKey.get(edge.from)?.shortLabel ?? edge.from} -> ${
                    graphViewNodeByKey.get(edge.to)?.shortLabel ?? edge.to
                  }`}</strong>
                  <span>{edge.label}</span>
                  <em>已发布事实</em>
                  <small>证据 {edge.evidenceCount} 条 · {edge.stage}</small>
                </li>
              ))
            : scenario.edges.slice(0, 4).map((edge) => (
                <li key={`${edge.from}-${edge.to}`}>
                  <strong>{`${nodeByKey.get(edge.from)?.shortLabel ?? edge.from} -> ${
                    nodeByKey.get(edge.to)?.shortLabel ?? edge.to
                  }`}</strong>
                  <span>{edge.stage}</span>
                  <em>Synthetic fixture</em>
                  <small>{edge.fixtureNotice}</small>
                </li>
              ))}
        </ol>

        <section
          className="graphPolicyPanel productionEvidencePanel"
          data-evidence-count={productionEvidenceDetail?.evidence_count ?? 0}
          data-evidence-endpoint={productionEvidenceEndpoint || "local"}
          data-evidence-object-id={
            productionEvidenceDetail?.object_id ??
            (productionScoreTargetId ||
            productionSampleCandidate?.id ||
            "none")
          }
          data-evidence-sync-mode={productionEvidenceSyncMode}
          data-evidence-sync-reason={productionEvidenceSyncReason}
          data-source-document-count={productionEvidenceDetail?.source_document_count ?? 0}
          data-testid="production-evidence-detail"
          data-truncated={productionEvidenceDetail?.truncated ?? false}
        >
          <header>
            <p className="eyebrow">生产证据</p>
            <strong data-testid="production-evidence-status">
              {productionEvidenceSyncMode} / {productionEvidenceSyncReason}
            </strong>
          </header>
          <dl data-testid="production-evidence-contract">
            <div>
              <dt>候选</dt>
              <dd>
                {productionEvidenceDetail?.object_id ||
                  productionScoreTargetId ||
                  productionSampleCandidate?.id ||
                  "candidate-missing"}
              </dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd data-testid="production-evidence-count">
                {productionEvidenceDetail?.evidence_count ?? 0} sources /{" "}
                {productionEvidenceDetail?.source_document_count ?? 0} documents
              </dd>
            </div>
            <div>
              <dt>接口</dt>
              <dd>{productionEvidenceEndpoint || "local-fixture"}</dd>
            </div>
          </dl>
          <ol className="pathList" data-testid="production-evidence-snippets">
            {(productionEvidenceDetail?.evidence ?? []).slice(0, 4).map((item, index) => (
              <li
                data-testid={`production-evidence-snippet-${index}`}
                key={item.evidence_id}
              >
                <strong>{item.title ?? item.publisher ?? item.source_document_id}</strong>
                <span>{item.role}</span>
                <em>{item.publisher ?? "source document"}</em>
                <small>{item.snippet.text ?? item.support_excerpt ?? "snippet-missing"}</small>
                {item.locator ? (
                  <small className="evidenceLocator" data-testid={`evidence-locator-${index}`}>
                    定位：{item.locator}
                  </small>
                ) : null}
                {item.url ? (
                  <a
                    className="evidenceSourceLink"
                    data-testid={`evidence-source-link-${index}`}
                    href={item.url}
                    rel="noreferrer noopener"
                    target="_blank"
                  >
                    打开官方来源
                  </a>
                ) : null}
              </li>
            ))}
          </ol>
        </section>

        <section
          className="graphPolicyPanel"
          data-continuation-endpoint="/v1/explore/expand"
          data-sort-keys="active-lens,evidence,confidence,observed_at,id"
          data-testid="inclusion-truncation-explanation"
          data-truncation-contract="edge_budget,node_budget,returned_counts,continuation"
        >
          <header>
            <p className="eyebrow">收录策略</p>
            <strong>Bounded relationship set</strong>
          </header>
          <dl>
            <div>
              <dt>Included first</dt>
              <dd>Active lens, evidence-bearing edges, confidence, observed time, stable id</dd>
            </div>
            <div>
              <dt>Truncation</dt>
              <dd>edge_budget and node_budget return reasons, counts and continuation metadata</dd>
            </div>
            <div>
              <dt>Continuation</dt>
              <dd>/v1/explore/expand preserves the current focus and loads a bounded increment</dd>
            </div>
          </dl>
        </section>

        <section
          className="graphTablePanel"
          data-accessibility-equivalent="graph-relationships"
          data-color-independent-encoding="labels,arrows,stages,roles,evidence"
          data-equivalent-fields="direction,type,evidence_status,observed_at"
          data-testid="graph-table-alternative"
        >
          <header>
            <p className="eyebrow">关系表格</p>
            <label htmlFor="graph-table-lens-filter">透镜</label>
            <select
              data-testid="graph-table-filter"
              id="graph-table-lens-filter"
              onChange={(event) => setTableLensFilter(event.target.value as LensKey)}
              value={tableLensFilter}
            >
              {lensItems.map((lens) => (
                <option key={lens.key} value={lens.key}>
                  {lens.label}
                </option>
              ))}
            </select>
          </header>
          <p
            className="visualSemanticsNotice"
            data-color-independent-encoding="labels,arrows,stages,roles,evidence"
            data-control-semantics="layout-position-not-control"
            data-testid="visual-semantics-notice"
          >
            布局位置仅表示视觉焦点；语义由关系标签、箭头、环节、角色与证据承载。
          </p>
          <table>
            <thead>
              <tr>
                <th scope="col">来源方</th>
                <th scope="col">指向方</th>
                <th scope="col">方向</th>
                <th scope="col">类型</th>
                <th scope="col">关系</th>
                <th scope="col">环节</th>
                <th scope="col">证据</th>
                <th scope="col">时间</th>
              </tr>
            </thead>
            <tbody>
              {tableEdges.map((edge) => (
                <tr
                  data-direction={`${edge.from}->${edge.to}`}
                  data-evidence-status={edge.source === "server" ? "server-evidence" : "fixture-evidence"}
                  data-lens={edge.lens}
                  data-observed-at={edge.observedAt}
                  data-render-source={edge.source}
                  data-relationship-type={edge.lens}
                  data-testid={`graph-table-row-${edge.from}-${edge.to}`}
                  key={edge.id}
                >
                  <td>{graphViewNodeByKey.get(edge.from)?.shortLabel ?? edge.from}</td>
                  <td>{graphViewNodeByKey.get(edge.to)?.shortLabel ?? edge.to}</td>
                  <td>{`${graphViewNodeByKey.get(edge.from)?.shortLabel ?? edge.from} -> ${
                    graphViewNodeByKey.get(edge.to)?.shortLabel ?? edge.to
                  }`}</td>
                  <td>{edge.lens.replaceAll("_", " ")}</td>
                  <td>
                    <span>{edge.label}</span>
                    <small>{edge.fixtureNotice}</small>
                  </td>
                  <td>{edge.stage}</td>
                  <td>
                    <span className="evidencePill">
                      {edge.source === "server" ? `证据 ${edge.evidenceCount} 条` : "样例证据"}
                    </span>
                  </td>
                  <td>{edge.observedAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <div className="actionStack" aria-label="主体操作">
          <button
            className="primaryAction"
            data-testid="primary-set-center"
            disabled={
              CLOUD_MODE
                ? !selectedGraphNode.key ||
                  !selectedGraphNode.centerable ||
                  selectedGraphNode.key === serverFocusEntityId
                : !selectedGraphNode.localKey ||
                  !selectedGraphNode.centerable ||
                  selectedGraphNode.localKey === focusKey
            }
            onClick={() => {
              // EEI-F03：这是唯一的换中心入口——目标就是被选中的实体本身。
              if (CLOUD_MODE) {
                if (selectedGraphNode.key && selectedGraphNode.centerable) {
                  serverReroot(selectedGraphNode.key, selectedGraphNode.label);
                }
                return;
              }
              if (selectedGraphNode.localKey && selectedGraphNode.centerable) {
                setCenter(selectedGraphNode.localKey as FocusKey);
              }
            }}
            type="button"
          >
            <Crosshair size={16} aria-hidden="true" />
            <span>以 {selectedGraphNode.label} 为中心</span>
          </button>
          <button
            data-testid="node-action-upstream"
            disabled={CLOUD_MODE || graphViewMode === "server" || !upstreamCandidate}
            onClick={() => upstreamCandidate && inspectNode(upstreamCandidate)}
            type="button"
          >
            <ArrowUp size={16} aria-hidden="true" />
            <span>展开上游</span>
          </button>
          <button
            data-testid="node-action-downstream"
            disabled={CLOUD_MODE || graphViewMode === "server" || !downstreamCandidate}
            onClick={() => downstreamCandidate && inspectNode(downstreamCandidate)}
            type="button"
          >
            <ArrowDown size={16} aria-hidden="true" />
            <span>展开下游</span>
          </button>
          <button
            data-testid="node-action-pin"
            disabled={!selectedGraphNode.localKey}
            onClick={pinSelectedNode}
            type="button"
          >
            <Star size={16} aria-hidden="true" />
            <span>固定节点</span>
          </button>
          <button
            data-testid="node-action-compare"
            disabled={!selectedGraphNode.localKey}
            onClick={compareSelectedNode}
            type="button"
          >
            <GitBranch size={16} aria-hidden="true" />
            <span>加入比较</span>
          </button>
          <button
            data-testid="node-action-watchlist"
            disabled={!selectedGraphNode.localKey}
            onClick={addSelectedNodeToWatchlist}
            type="button"
          >
            <Star size={16} aria-hidden="true" />
            <span>加入关注</span>
          </button>
          <button data-testid="node-action-path" onClick={openSelectedPath} type="button">
            <Route size={16} aria-hidden="true" />
            <span>查看路径</span>
          </button>
          <button data-testid="node-action-evidence" onClick={openSelectedEvidence} type="button">
            <FileSearch size={16} aria-hidden="true" />
            <span>打开证据</span>
          </button>
          {selectedNode.groupMembers ? (
            <button data-testid="open-group-list" onClick={() => setGroupListOpen((open) => !open)} type="button">
              <Boxes size={16} aria-hidden="true" />
              <span>查看组列表</span>
            </button>
          ) : null}
          {CLOUD_MODE
            ? (productionGraph?.nodes ?? [])
                .filter((node) => node.id !== serverFocusEntityId)
                .slice(0, 3)
                .map((node) => (
                  <button
                    key={node.id}
                    onClick={() => serverReroot(node.id, node.canonical_name)}
                    type="button"
                  >
                    <Network size={16} aria-hidden="true" />
                    <span>以 {shortServerLabel(node.canonical_name)} 为中心</span>
                  </button>
                ))
            : scenario.nextCenters.map((key) => (
                <button key={key} onClick={() => setCenter(key)} type="button">
                  <Network size={16} aria-hidden="true" />
                  <span>以 {entityLabels[key]} 为中心</span>
                </button>
              ))}
          <button onClick={resetToNvidia} type="button">
            <Route size={16} aria-hidden="true" />
            <span>回到 NVIDIA</span>
          </button>
        </div>

        <section
          className="nodeActionState"
          data-compare-count={comparisonNodeKeys.length}
          data-pinned-count={pinnedNodeKeys.length}
          data-testid="node-action-state"
          data-watchlist-count={watchlistNodeKeys.length}
        >
          <div>
            <strong>已固定</strong>
            <span data-testid="pinned-node-list">
              {pinnedNodeKeys.map((key) => entityLabels[key]).join(" / ") || "none"}
            </span>
          </div>
          <div>
            <strong>对比集</strong>
            <span data-testid="comparison-node-list">
              {comparisonNodeKeys.map((key) => entityLabels[key]).join(" / ") || "none"}
            </span>
          </div>
          <div>
            <strong>关注集</strong>
            <span data-testid="watchlist-node-list">
              {watchlistNodeKeys.map((key) => entityLabels[key]).join(" / ") || "none"}
            </span>
          </div>
          <small data-testid="node-action-status">{nodeActionStatus}</small>
        </section>

        {selectedNode.groupMembers && groupListOpen ? (
          <ol className="groupList" data-testid="group-list">
            {selectedNode.groupMembers.map((member) => (
              <li key={member}>{member}</li>
            ))}
          </ol>
        ) : null}

        <div className="statusStrip">
          {CLOUD_MODE ? (
            <>
              <span>数据：已发布面</span>
              <span>事实来源：官方申报与新闻稿（双源+签核）</span>
              <span>构建：{BUILD_SHA.slice(0, 12)}</span>
            </>
          ) : (
            <>
              <span>数据：样例</span>
              <span>真实事实声明：未启用</span>
              <span>样例标注：可见</span>
            </>
          )}
          <span data-testid="model-contract-state">
            模型 {analysisContext.modelVersion} / 偏好 {analysisContext.profileVersion} / 公式{" "}
            {analysisContext.formulaRegistryVersion} / 参数{" "}
            {analysisContext.parameterCatalogVersion} / 阈值{" "}
            {analysisContext.thresholdRegistryVersion}
          </span>
          <span data-testid="active-context-state">
            数据 {analysisContext.dataSnapshot} / 评分 {analysisContext.scoreSnapshot} / 快照{" "}
            {asOf}
          </span>
          <span data-testid="lens-state">透镜：{activeLens}</span>
          <span data-testid="zoom-state">缩放：{semanticZoom}</span>
          <span data-testid="reroot-state">画布：{transitionState}</span>
          <span data-testid="budget-state">
            预算：{graphViewNodes.length} 节点 / {graphViewEdges.length} 边 / 首屏边上限 40（max 40 first-screen edges）
          </span>
        </div>
      </aside>
    </main>
    </WorkspaceContextProvider>
  );
}

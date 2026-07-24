// P0-2 治理术语清场（UX_SPEC_EEI v1.0 §E.1/§E.3）：一切服务端枚举值必须经
// 本文件映射后才能上屏，废除 `replaceAll("_", " ")` 直出。data-testid 与
// data-* 契约属性是机器接口，不经过本文件（E.3 第 6 条）。
// 未知值兜底：显示原文并 console.warn 上报，绝不 throw（zhLabel）。

export const ENTITY_TYPE_LABELS: Record<string, string> = {
  legal_entity: "公司",
  person: "董事/高管",
  facility: "设施",
  asset: "资产",
  industry: "行业",
  theme: "主题",
  brand: "品牌",
  product: "产品",
  business_segment: "业务板块",
  government_body: "政府机构",
  fund: "基金",
  entity: "实体"
};

export const RELATIONSHIP_FAMILY_LABELS: Record<string, string> = {
  corporate_structure: "集团结构",
  ownership_control: "控制关系",
  board_governance: "董事与高管",
  capital_financing: "资本与融资",
  mergers_acquisitions: "并购",
  government_policy: "政策",
  commercial_dependency: "商业依赖",
  supply_chain_operations: "供应链",
  technology_data_ip: "技术与知识产权",
  strategic_signals: "战略信号",
  human_capital: "人力资本",
  relationship: "关系"
};

export const RELATIONSHIP_TYPE_LABELS: Record<string, string> = {
  subsidiary_of: "子公司",
  parent_of: "母公司",
  controls: "控制",
  controlled_by: "受控于",
  owns_stake_in: "持股",
  board_member_of: "董事",
  officer_of: "高管",
  executive_of: "高管",
  director_of: "董事",
  supplier_to: "供应商",
  customer_of: "客户",
  wafer_foundry_for: "晶圆代工",
  packages_tests_for: "封装测试",
  equipment_provider_to: "设备供应商",
  material_provider_to: "材料供应商",
  invests_in: "投资",
  acquired: "收购",
  acquired_by: "被收购",
  merged_with: "合并",
  divested: "出售",
  operates: "运营",
  operates_facility: "运营设施",
  licenses_to: "技术授权",
  partners_with: "合作",
  regulates: "监管",
  subsidizes: "补贴",
  contracts_with: "签约",
  segment_of: "业务板块",
  brand_of: "旗下品牌",
  product_of: "旗下产品",
  focus_entity: "当前主体"
};

export const ZONE_LABELS: Record<string, string> = {
  focus: "焦点",
  upstream: "上游",
  downstream: "下游",
  business: "业务",
  capital: "资本",
  policy: "政策",
  infrastructure: "设施",
  governance: "治理"
};

// 机器状态码 → 自然中文（原 page.tsx STATUS_ZH 并入；原始状态码仍保留在
// 各面板〈诊断详情〉内，契约 testid 与断言不动）。
export const STATUS_LABELS: Record<string, string> = {
  "local-active": "本地模型运行中",
  "server-active": "云端模型运行中",
  idle: "待命",
  activating: "激活中",
  creating: "创建中",
  enqueueing: "入队中",
  enqueued: "已入队",
  ready: "就绪",
  loading: "载入中",
  hydrated: "已载入",
  "server-error": "云端接口不可用",
  http_404: "云端未提供该接口",
  http_409: "版本冲突",
  http_500: "云端服务异常",
  local_fallback: "已回退本地示例",
  "local-fixture": "本地示例",
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
  active: "已激活",
  covered: "有数据",
  partial: "部分覆盖",
  missing: "暂无数据",
  reported: "已报告",
  published: "已核实",
  candidate: "待核实",
  fixture: "示例",
  api_required: "未连接数据服务",
  unknown: "未知",
  publication_unavailable: "暂不可用",
  cloud_publication_surface: "云端发布面",
  "loading-production-graph": "载入中",
  "loading-server-context": "载入中",
  saving: "保存中",
  restoring: "恢复中"
};

const LABEL_TABLES = {
  entity_type: ENTITY_TYPE_LABELS,
  relationship_family: RELATIONSHIP_FAMILY_LABELS,
  relationship_type: RELATIONSHIP_TYPE_LABELS,
  zone: ZONE_LABELS,
  status: STATUS_LABELS
} as const;

export type LabelKind = keyof typeof LABEL_TABLES;

const warnedUnknownValues = new Set<string>();

/**
 * 枚举值 → 用户语言的唯一入口。未知值显示原文（去下划线）并 console.warn
 * 一次（不 throw，不阻塞渲染）——上报即待办：把它补进对应映射表。
 */
export function zhLabel(kind: LabelKind, value: string | null | undefined): string {
  if (!value) {
    return "无";
  }
  const table = LABEL_TABLES[kind];
  const hit = table[value];
  if (hit) {
    return hit;
  }
  const warnKey = `${kind}:${value}`;
  if (!warnedUnknownValues.has(warnKey)) {
    warnedUnknownValues.add(warnKey);
    if (typeof console !== "undefined") {
      console.warn(`[labels] 未映射的 ${kind} 枚举值：${value}（显示原文兜底）`);
    }
  }
  return value.replaceAll("_", " ");
}

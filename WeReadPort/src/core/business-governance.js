/**
 * 公开业务基线治理合同。
 *
 * 只描述产品能力、运行阶段、依赖关系和脱敏 Oracle；不得加入用户标识、
 * 文件名、书名、笔记、密钥、内部部署 ID 或私有基础设施凭据。
 */
export const BUSINESS_GOVERNANCE_SCHEMA_VERSION = "1.0.0";

export const BUSINESS_LINE_STATE = Object.freeze({
  READY: "READY",
  DEGRADED: "DEGRADED",
  BLOCKED: "BLOCKED",
  NOT_VERIFIED: "NOT_VERIFIED",
  EXTERNAL: "EXTERNAL",
});

const DEFINITIONS = Object.freeze([
  Object.freeze({
    id: "public-trust",
    name: "公开信任面",
    phase: "Stage 1 / P0",
    plane: "产品面",
    owner: "产品运行时",
    criticality: "关键",
    dependsOnAll: Object.freeze([]),
    dependsOnAny: Object.freeze([]),
    relation: "为全部公开能力提供隐私、条款、状态与安全边界",
    oracle: "/privacy/ · /terms/ · /status/ · /healthz · /readyz",
  }),
  Object.freeze({
    id: "weread-direct-export",
    name: "微信读书直连导出",
    phase: "Stage 1 / P0",
    plane: "产品面 + 外部上游",
    owner: "产品运行时与腾讯上游",
    criticality: "关键",
    dependsOnAll: Object.freeze(["public-trust"]),
    dependsOnAny: Object.freeze([]),
    relation: "使用者本人密钥经同源薄代理读取并导出个人笔记",
    oracle: "代理合同测试 + 轮换密钥后的 Owner 浏览器 E2E",
  }),
  Object.freeze({
    id: "local-import",
    name: "本地文件导入",
    phase: "Stage 1 / P0",
    plane: "浏览器数据面",
    owner: "浏览器 Worker",
    criticality: "高",
    dependsOnAll: Object.freeze(["public-trust"]),
    dependsOnAny: Object.freeze([]),
    relation: "作为无需外部密钥的独立输入路径",
    oracle: "ZIP/JSON/Markdown/TXT 合同测试与浏览器白箱",
  }),
  Object.freeze({
    id: "normalize-export",
    name: "规范化与确定性导出",
    phase: "Stage 1 / P0",
    plane: "浏览器数据面",
    owner: "浏览器 Worker",
    criticality: "关键",
    dependsOnAll: Object.freeze(["public-trust"]),
    dependsOnAny: Object.freeze(["weread-direct-export", "local-import"]),
    relation: "接收任一合格输入，生成可校验的迁移制品",
    oracle: "确定性 ZIP、Manifest、SHA-256、冲突与部分结果测试",
  }),
  Object.freeze({
    id: "chatgpt-handoff",
    name: "ChatGPT 安全交接",
    phase: "Stage 1 / P0",
    plane: "用户控制面",
    owner: "使用者确认",
    criticality: "中",
    dependsOnAll: Object.freeze(["normalize-export"]),
    dependsOnAny: Object.freeze([]),
    relation: "只在用户明确点击后下载并跳转固定 ChatGPT 入口",
    oracle: "无自动上传、固定 origin、URL 无用户内容",
  }),
  Object.freeze({
    id: "release-supply-chain",
    name: "发布与供应链",
    phase: "Stage 1 / P0",
    plane: "交付控制面",
    owner: "GitHub Actions 与 ChatGPT Sites",
    criticality: "高",
    dependsOnAll: Object.freeze(["public-trust"]),
    dependsOnAny: Object.freeze([]),
    relation: "冻结测试、不可变 Action、同一 Sites 项目部署与即时 Smoke",
    oracle: "CI、构建、部署版本与生产 Smoke 证据",
  }),
  Object.freeze({
    id: "operations-recovery",
    name: "运维、恢复与事实同步",
    phase: "Stage 1 / P0",
    plane: "外部运维面",
    owner: "OVH 与 status.linzezhang.com",
    criticality: "高",
    dependsOnAll: Object.freeze(["release-supply-chain"]),
    dependsOnAny: Object.freeze([]),
    relation: "脱敏健康检查、短期可重建 Journal、备份、恢复与状态登记",
    oracle: "status.linzezhang.com + OVH systemd/SQLite/备份恢复证据",
  }),
]);

export function businessLineDefinitions() {
  return DEFINITIONS.map(item => ({
    ...item,
    dependsOnAll: [...item.dependsOnAll],
    dependsOnAny: [...item.dependsOnAny],
  }));
}

export function buildBusinessLineStatus({ assetsReady, checkedAt }) {
  const at = String(checkedAt ?? "");
  return businessLineDefinitions().map(line => {
    if (line.id === "weread-direct-export") {
      return withState(line, assetsReady ? BUSINESS_LINE_STATE.NOT_VERIFIED : BUSINESS_LINE_STATE.BLOCKED, {
        checkedAt: at,
        evidenceLevel: assetsReady ? "CONTRACT_ONLY" : "RUNTIME",
        reasonCode: assetsReady ? "OWNER_KEY_E2E_NOT_RUN" : "STATIC_ASSETS_UNAVAILABLE",
        recoveryAction: assetsReady ? "轮换已暴露测试密钥后，由 Owner 在浏览器一次性执行真实连接。" : "恢复静态资源绑定后再执行真实连接。",
      });
    }
    if (line.id === "release-supply-chain") {
      return withState(line, BUSINESS_LINE_STATE.NOT_VERIFIED, {
        checkedAt: at,
        evidenceLevel: "EXTERNAL_EVIDENCE_REQUIRED",
        reasonCode: "CI_AND_DEPLOY_EVIDENCE_NOT_VISIBLE_TO_RUNTIME",
        recoveryAction: "读取同一 commit 的 CI、Sites 部署与生产 Smoke 证据。",
      });
    }
    if (line.id === "operations-recovery") {
      return withState(line, BUSINESS_LINE_STATE.EXTERNAL, {
        checkedAt: at,
        evidenceLevel: "EXTERNAL",
        reasonCode: "OBSERVED_BY_EXTERNAL_OPERATIONS_PLANE",
        recoveryAction: "前往 status.linzezhang.com 查看脱敏运维状态。",
      });
    }
    return withState(line, assetsReady ? BUSINESS_LINE_STATE.READY : BUSINESS_LINE_STATE.BLOCKED, {
      checkedAt: at,
      evidenceLevel: assetsReady ? "RUNTIME_ASSET_PROBE" : "RUNTIME",
      reasonCode: assetsReady ? null : "STATIC_ASSETS_UNAVAILABLE",
      recoveryAction: assetsReady ? "无需操作。" : "恢复静态资源绑定并重新运行就绪检查。",
    });
  });
}

export function summarizeBusinessLines(lines) {
  const counts = Object.fromEntries(Object.values(BUSINESS_LINE_STATE).map(value => [value, 0]));
  for (const line of lines) counts[line.state] = (counts[line.state] ?? 0) + 1;
  return {
    total: lines.length,
    counts,
    blocking: lines.filter(line => line.state === BUSINESS_LINE_STATE.BLOCKED).map(line => line.id),
    notVerified: lines.filter(line => line.state === BUSINESS_LINE_STATE.NOT_VERIFIED).map(line => line.id),
  };
}

export function validateBusinessLineGraph(lines = businessLineDefinitions()) {
  const errors = [];
  const ids = new Set(lines.map(line => line.id));
  if (ids.size !== lines.length) errors.push("DUPLICATE_BUSINESS_LINE_ID");
  for (const line of lines) {
    for (const dependency of [...line.dependsOnAll, ...line.dependsOnAny]) {
      if (!ids.has(dependency)) errors.push(`UNKNOWN_DEPENDENCY:${line.id}:${dependency}`);
      if (dependency === line.id) errors.push(`SELF_DEPENDENCY:${line.id}`);
    }
  }
  const state = new Map();
  const lookup = new Map(lines.map(line => [line.id, line]));
  const visit = id => {
    if (state.get(id) === 1) { errors.push(`CYCLE:${id}`); return; }
    if (state.get(id) === 2) return;
    state.set(id, 1);
    const line = lookup.get(id);
    if (line) for (const dependency of [...line.dependsOnAll, ...line.dependsOnAny]) visit(dependency);
    state.set(id, 2);
  };
  for (const id of ids) visit(id);
  return [...new Set(errors)];
}

function withState(line, state, extra) {
  return {
    ...line,
    state,
    stateLabel: stateLabel(state),
    ...extra,
  };
}

export function stateLabel(state) {
  return ({
    READY: "已就绪",
    DEGRADED: "部分降级",
    BLOCKED: "已阻塞",
    NOT_VERIFIED: "尚未实证",
    EXTERNAL: "外部受控",
  })[state] ?? "未知";
}

/** v0.0.0.1.8 公开业务纵向切片；不得包含用户内容、账户标识或基础设施 Secret。 */
export const BUSINESS_GOVERNANCE_SCHEMA_VERSION = "2.0.0";
export const BUSINESS_LINE_STATE = Object.freeze({ READY:"READY", DEGRADED:"DEGRADED", BLOCKED:"BLOCKED", NOT_VERIFIED:"NOT_VERIFIED", EXTERNAL:"EXTERNAL" });
const DEFINITIONS = Object.freeze([
  line("public-trust","公开信任面","Stage 2 / v1.8","产品面","关键",[],[],"为注册、导入、状态和法律页面提供公开边界","/privacy/ · /terms/ · /status/ · /healthz · /readyz"),
  line("identity-access","账户与多平台身份","Stage 2 / v1.8","身份控制面","关键",["public-trust"],[],"密码、微信读书密钥、Google、GitHub、Notion 统一绑定不可变 account_id","身份合同测试 + OAuth state/PKCE + 生产登录 Smoke"),
  line("account-storage","账户数据隔离与加密","Stage 2 / v1.8","数据面","关键",["identity-access"],[],"每次读写显式 account_id；正文与凭据使用账户密钥加密后进入 R2","跨租户拒绝测试 + 加密对象恢复测试"),
  line("cross-device-sync","跨设备云同步","Stage 2 / v1.8","同步数据面","关键",["identity-access","account-storage"],[],"增量游标、幂等与乐观版本冲突保护","双账户/双设备 fixture + 冲突 Oracle"),
  line("provider-imports","四平台一键导入","Stage 2 / v1.8","连接器面","高",["identity-access","account-storage"],[],"Notion、Obsidian、GitHub、Google 的授权、选择、预览、导入与恢复","连接器 fixture + 小白流程浏览器测试"),
  line("weread-wide-sync","微信读书广范围同步","Stage 2 / v1.8","连接器面 + 腾讯上游","关键",["identity-access","account-storage"],[],"能力发现、全游标书架/笔记、划线、想法、书评、进度、统计和推荐","官方 gateway 合同 + Owner 轮换密钥 E2E"),
  line("analytics-recommendations","画像、热度与推荐","Stage 2 / v1.8","账户分析面","高",["account-storage"],[],"经同意的结构化行为、热度趋势、主题偏好与可解释推荐；无模型 Token","同意撤销测试 + 确定性聚合 fixture"),
  line("legacy-migration","匿名迁移兼容入口","Stage 2 / v1.8","浏览器兼容面","中",["public-trust"],[],"保留 /migrate 匿名导出，不替代账户平台","旧导出回归测试 + 浏览器白箱"),
  line("release-supply-chain","发布与供应链","Stage 2 / v1.8","交付控制面","高",["public-trust","identity-access"],[],"冻结测试、不可变 Action、同一 Sites 项目与精确提交","CI、构建、commit、部署版本与生产 Smoke"),
  line("operations-recovery","运维、自愈与恢复","Stage 2 / v1.8","OVH 运维面","关键",["release-supply-chain","account-storage"],[],"systemd、SQLite Runtime Journal/Outbox、诊断、备份、恢复与回滚","即时故障注入 + status.linzezhang.com"),
  line("facts-backup","结构化事实与异地冷备","Stage 2 / v1.8","数据治理面","高",["operations-recovery"],[],"完成态结构化事实幂等进入 Private-Database；R2 对象冷备至 OCI","无空提交、对象哈希、恢复演练与脱敏证明"),
]);
function line(id,name,phase,plane,criticality,dependsOnAll,dependsOnAny,relation,oracle){return Object.freeze({id,name,phase,plane,owner:plane,criticality,dependsOnAll:Object.freeze(dependsOnAll),dependsOnAny:Object.freeze(dependsOnAny),relation,oracle});}
export function businessLineDefinitions(){return DEFINITIONS.map(item=>({...item,dependsOnAll:[...item.dependsOnAll],dependsOnAny:[...item.dependsOnAny]}));}
export function buildBusinessLineStatus({assetsReady,accountServiceReady=false,checkedAt}){
  const at=String(checkedAt??"");
  return businessLineDefinitions().map(item=>{
    if(item.id==="public-trust"||item.id==="legacy-migration") return state(item,assetsReady?"READY":"BLOCKED",at,assetsReady?"RUNTIME_ASSET_PROBE":"STATIC_ASSETS_UNAVAILABLE",assetsReady?"无需操作。":"恢复静态资源绑定。");
    if(["identity-access","account-storage","cross-device-sync","provider-imports","analytics-recommendations"].includes(item.id)) return state(item,accountServiceReady?"READY":"BLOCKED",at,accountServiceReady?"ACCOUNT_SERVICE_READY":"ACCOUNT_SERVICE_UNAVAILABLE",accountServiceReady?"无需操作。":"恢复 OVH 账户服务、数据库或 R2 绑定。");
    if(item.id==="weread-wide-sync") return state(item,accountServiceReady?"NOT_VERIFIED":"BLOCKED",at,accountServiceReady?"OWNER_KEY_E2E_NOT_RUN":"ACCOUNT_SERVICE_UNAVAILABLE",accountServiceReady?"由 Owner 使用轮换后的本人密钥执行一次真实同步。":"先恢复账户服务。");
    if(item.id==="release-supply-chain") return state(item,"NOT_VERIFIED",at,"CI_AND_DEPLOY_EVIDENCE_REQUIRED","读取同一 commit 的 CI、Sites 部署和生产 Smoke 证据。");
    if(item.id==="operations-recovery") return state(item,"EXTERNAL",at,"OBSERVED_BY_EXTERNAL_OPERATIONS_PLANE","前往 status.linzezhang.com 查看 systemd、SQLite 与恢复状态。");
    return state(item,"NOT_VERIFIED",at,"PRIVATE_FACTS_AND_BACKUP_EVIDENCE_REQUIRED","核验 Private-Database、R2 与 OCI 的脱敏事实和对象恢复证据。");
  });
}
function state(item,value,checkedAt,reasonCode,recoveryAction){return{...item,state:value,stateLabel:stateLabel(value),checkedAt,evidenceLevel:value==="READY"?"RUNTIME":"EXTERNAL_OR_OWNER",reasonCode,recoveryAction};}
export function summarizeBusinessLines(lines){const counts=Object.fromEntries(Object.values(BUSINESS_LINE_STATE).map(v=>[v,0]));for(const item of lines)counts[item.state]=(counts[item.state]??0)+1;return{total:lines.length,counts,blocking:lines.filter(x=>x.state==="BLOCKED").map(x=>x.id),notVerified:lines.filter(x=>x.state==="NOT_VERIFIED").map(x=>x.id)};}
export function validateBusinessLineGraph(lines=businessLineDefinitions()){const errors=[];const ids=new Set(lines.map(x=>x.id));if(ids.size!==lines.length)errors.push("DUPLICATE_BUSINESS_LINE_ID");for(const item of lines)for(const dep of [...item.dependsOnAll,...item.dependsOnAny]){if(!ids.has(dep))errors.push(`UNKNOWN_DEPENDENCY:${item.id}:${dep}`);if(dep===item.id)errors.push(`SELF_DEPENDENCY:${item.id}`);}const status=new Map(),lookup=new Map(lines.map(x=>[x.id,x]));const visit=id=>{if(status.get(id)===1){errors.push(`CYCLE:${id}`);return;}if(status.get(id)===2)return;status.set(id,1);for(const dep of [...(lookup.get(id)?.dependsOnAll||[]),...(lookup.get(id)?.dependsOnAny||[])])visit(dep);status.set(id,2);};for(const id of ids)visit(id);return[...new Set(errors)];}
export function stateLabel(value){return({READY:"已就绪",DEGRADED:"部分降级",BLOCKED:"已阻塞",NOT_VERIFIED:"尚未实证",EXTERNAL:"外部受控"})[value]??"未知";}

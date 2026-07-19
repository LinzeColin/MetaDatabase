# Codex Master Task：股票商业机会拆解 Skill v3

## 单一目标

维护一个公开安全、可恢复、未安装的 `stock-commercial-opportunities` 源码包，使 Codex 能以公开证据把商业驱动映射为上市公司研究候选，并保守决定 `REJECT / SCREEN_FLAG / WATCHLIST / DILIGENCE_NEXT / ADVANCE_RESEARCH / NO_QUALIFIED_CANDIDATE`。

`ADVANCE_RESEARCH` 只批准进一步研究，不批准交易。

## Gate 状态合同

| Gate | 完成定义 | 当前真值来源 |
|---|---|---|
| G0 公开研究 | 官方/项目/产品页面已打开，差异和许可边界明确 | `RESEARCH_REPORT.md` |
| G1 v3 实现 | Skill、references、assets、scripts、evals、tests 一致 | task-pack 文件 |
| G2 确定性验收 | strict validators、tests、数据/链接/依赖/secret 检查通过 | `VALIDATION_REPORT.md` |
| G3 发布包恢复 | ZIP 可解压，manifest 可重算，解压副本重复 G2 | release/manifest 证据 |
| G4 远端备份 | GitHub `main` 可独立 clone/下载并重复 G3 | 仓库/PR/commit 证据 |
| G5 语义前向评估 | 新鲜任务 trigger 与无/有 Skill A/B 达阈值 | `NOT_RUN`，除非保存原始输出 |
| G6 安装/发现 | 精确目标根安装和 smoke | 当前明确 `NOT_RUN / PROHIBITED` |
| G7 真实投资研究 | current data、真实发行人和研究审阅 | 不属于 fixtures；默认 `NOT_RUN` |

缺输入、未运行、未知、未授权或无阈值均不是 PASS。

## 当前 Run Contract：确定性维护

- Goal：修改源码或任务包后恢复 G1–G3。
- Read scope：本 task-pack、当前官方 Skill 指引、必要的官方金融来源。
- Write scope：仅本 task-pack；不得改安装根、账户、组合或外部系统。
- Validate：29+ 单测、3 CLI、JSON/JSONL/CSV/YAML、links、standard-library imports、cache/secret/local-path scan、manifest、zip restore。
- Rollback：撤销本 Run 的 task-pack diff；历史 archives 不变。
- Stop：任一阻断失败、真实/付费/MNPI 数据进入 fixture、当前规范冲突、或动作需要新权限。

## 后续 Run

- RC-SEMANTIC：新鲜任务运行 trigger + Q01/Q04/Q05/Q08 A/B；不安装时显式加载源码。
- RC-RESTORE：从远端 `main` 的临时 sparse clone 重放验证。
- RC-INSTALL：只有用户未来明确授权后另开；先 collision/backup/staging，再原子安装和回滚验证。
- RC-LIVE-RESEARCH：对一个明确 universe 运行 current-source 研究；单独设数据许可、法域、as-of 和非建议边界。

## 最终报告

1. Outcome、version、commit/ZIP SHA、install state。
2. PASS/FAIL/NOT_RUN 状态矩阵和实际命令。
3. 金融事实与 source freshness 限制。
4. Breaking changes、first rejection、blind spot/surprise。
5. 一个最高 ROI 下一步。

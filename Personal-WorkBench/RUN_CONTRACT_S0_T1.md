# Run Contract — S0-T1 目标仓语义对账

## 目标

仅完成任务包 `S0-T1` 的目标仓语义对账：确认 `MetaDatabase/Personal-WorkBench/` 是新的本地项目根，读取适用治理与冻结任务包，并对全部 19 项任务作唯一分类。此合同不建立或修改 ChatGPT Sites、D1、R2、身份提供商、邮件、Turnstile 或生产环境。

## 最小相关范围

- 目标仓：当前 `LinzeColin/MetaDatabase` worktree 与远端 `main`。
- 新项目目录：`Personal-WorkBench/`。
- 冻结任务包：`胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8`。
- 适用治理：仓根 `AGENTS.md`、`WHERE_IS_PROJECT_DATA.md`、任务包 `CANONICAL_STATE.json`、`TASK_DAG.json`、数据与租户合同。
- 当前官方 Sites 开发文档：只读确认推荐 starter、D1、R2、认证型 Site、Save Version/Deploy 与 Secret Settings 的支持边界；不以公开文档替代 Owner 账户权限证据。

## 适配决定

任务包的示例命令要求在目标仓执行 `git switch main` 和 `git pull --ff-only`；当前 `main` 已在受保护主工作树中签出。为遵守本机 worktree 铁律，本任务以 `git ls-remote origin main`、当前/本地/远端 `main` SHA 比较替代，不在此 worktree 切换到 `main`。这是工作流适配，不改变产品架构、范围、验收或视觉真值。

用户明确指定本项目位于 `MetaDatabase/Personal-WorkBench/`。该位置不等于复用任何 ChatGPT Sites 项目；后续仍必须创建隔离的 Sites 项目，且不得复用 WeRead linkage、D1、R2、Secret 或 Saved Version。

## 允许写入

- `Personal-WorkBench/13_evidence/stage0_reconcile.json`
- 本合同与 `HANDOFF.md`

不复制冻结 Starter，不写产品实现、依赖、运行时数据、Secret 或真实配置。

## 验收与验证

1. 远端 `main` 可只读观察，且与当前 S0 起点进行 SHA 对比。
2. 目标路径不存在已跟踪的旧源码或等价实现。
3. `TASK_DAG.json` 的 19 个 ID 在对账证据中各出现一次，分类均属于：`satisfied`、`apply`、`adapt`、`equivalent`、`conflict`、`blocked`、`obsolete`。
4. 未观察到超过 30% 的架构、权限、数据、成本、范围或 Acceptance 实质冲突。
5. 任务包 SHA-256 清单保持完整；原生 Verifier 的本机工具链限制须如实保留。

## 风险、回滚与停止条件

- 风险：把冻结 Starter 当作当前 Sites 成品，或用旧文件覆盖未来的推荐 starter。
- 回滚：本合同和证据均为无状态文档；若对账结论被新事实推翻，删除其结论并重新执行 S0-T1，不修改产品代码。
- 停止：发现超过 30% 的实质冲突、目标仓出现未知既有实现，或当前 Sites runtime 不支持必要的身份/数据能力时，停止并返回 Preparation。
- 外部接口安全边界：不调用会向本对话返回短期源仓凭据的 Sites 创建接口；必须由 Owner 创建私有、未 Deploy 的 Site，并只提供 opaque `project_id`，或提供不暴露凭据的等价安全绑定方式。

## 本轮结果

语义对账已完成并记录；S0-T1 不宣称完整 PASS，因为冻结任务包的原生 Verifier 需要 `tsc`，而当前环境未提供该锁定工具链。S0-T2 仍未开始。

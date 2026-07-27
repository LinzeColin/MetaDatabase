# 股势前瞻 v0.0.0.1 Roadmap

| Stage | 目标 | 当前状态 |
|---:|---|---|
| 0 | 需求、仓库、指标、范围、非目标与 Kill Criteria | 完成 |
| 1 | Runtime、PIT、5D/20D/60D、概率/幅度/时机与 `ABSTAIN` | 完成 |
| 2 | 确定性训练、校准、OOS/holdout、Candidate/LKG | 工程链路完成；Outcome 保持 `NOT_PROVEN` |
| 3 | 0 Agent/0 LLM Token、seccomp、network namespace、macOS 零持久/零常驻、Fuzz | 当前支持画像完成验证 |
| 4 | exact-content Patch、Registry/Manifest、安装后子包测试与回滚 | 公开基线隔离模拟完成；真实目标工作树官方 Validator 由 Codex 最后一公里执行 |
| 5 | 统一 Release Oracle、业务基线纵向切片矩阵、既有 Status 页面可逆接入、确定性双构建与篡改反证 | 工程实现完成；不降低 10,000 次确定性与 Fuzz 强度 |
| 6 | 适用 Skill 方法至少三次、封包前复审关闭与证明 Hash | 完成后生成 `PREPACKAGING_REVIEW_CLOSURE.json`；不声称外部独立 verdict |
| 7 | Owner 批准版本与摘要后输出唯一最终 ZIP | 待授权；Codex 不得创建或修改版本号 |
| 8 | Codex 最后一公里：两目标仓 Hash/冻结测试、真实工作树兼容性、落库、既有 Status 部署、CI、commit/push/PR/merge/备份 | 仅在最终 ZIP 交付后执行；禁止重新研究或复审 |

## 有界剩余迭代

- **封包前内部高价值迭代：0 轮。** 证明回执、统一 Release Oracle、v3 Status 接入、可重复构建和目标仓可逆模拟均已闭合；没有新的目标环境证据或阻塞 Finding 时继续修改会使已绑定 Hash 失效并产生负收益。
- **正式任务包交付：P50 1 轮、P80 2 轮、P95 3 轮。** P50 为 Owner 授权后原样生成/交付唯一 ZIP；P80 包含一次目标工作树兼容性整改；P95 不超过两次有界整改。
- 验收范围继续变化时标记 `OPEN_ENDED`，不得用伪精确上界或无限完善阻塞发布。
- 所有 DAG 节点均为即时执行，禁止真实时间 soak、等待窗口、后台空转或开发 Agent 复审等待。

## 永久禁止边界

本版本及其上线运行不使用 macOS Runtime、`launchd`、LaunchAgent、LaunchDaemon、登录项、后台 helper、本机持久缓存/日志/状态或本机常驻进程。macOS 仅允许临时传输 ZIP；验证合并与远端备份后删除本地副本。

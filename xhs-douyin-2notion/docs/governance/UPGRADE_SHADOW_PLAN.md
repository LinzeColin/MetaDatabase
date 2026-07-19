# Upstream Upgrade Shadow Plan

此计划只定义未来升级门禁，不自动抓取、安装或提升 pin。

## 触发条件

候选 ref、License、dependency manifest/lock、入口点、关键 Schema 文件或行为哈希发生变化时触发；定时发现更新不构成升级授权。

## Shadow 流程

1. 在 `${X2N_DATA_ROOT}/downloads/external_research/runs/<run-id>/` 仅通过 `scripts/public_source_snapshot.py` 以匿名公开 URL 获取候选精确 Commit。该工具每条命令隔离 global/system Git config、禁用 Credential Helper/交互认证并使用环境 allowlist；x2n 不读取或改变任何共享认证材料。任何源码检查前先做不回显值的 userinfo/credential-shape Gate；命中即登记事件、删除快照并 Fail Closed。
2. 比较 Commit/tree/blob/SHA-256、License 文件、manifest、lock 和已登记 Schema；任何缺失或未知均停止。
3. xhs exporter 仅写 clean-room 行为差异，不导入源码、minified 库或 zip。
4. douyin 候选先解析到独立 exact lock，扫描所有 transitive licenses 和 SBOM；不得读真实 cookie 或运行真实账号。
5. 使用 synthetic fixtures 执行正常、缺字段、未知字段、错误退出、超时、Schema drift 和 version mismatch；未知 Schema 必须阻断。
6. 扫描输出，确保上游路径、主键、凭据、媒体 URL 和原始媒体都不进入 Canonical、日志或证据。
7. 仅在独立 Task/Acceptance 全通过后更新 registry pin；当前 pin 保持可回滚，feature flag 仍默认关闭。
8. 删除本轮 shadow 快照，确认私有根和仓库均无临时残留。

## Promotion 与回滚

Promotion 需要 Owner 授权的后续 Run、完整 contract evidence、许可证/NOTICE/SBOM 一致、Stage Gate 允许。任何门禁失败时保持旧 pin 或关闭 Adapter；禁止为追求速度跳过 lock、Schema 或隐私净化。

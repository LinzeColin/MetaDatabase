# CHANGELOG

## v0.0.0.1 — 正式候选范围

- 冻结为 `SOURCE_ONLY` 嵌入式股票预测节点 Skill，而非独立系统。
- EFS 固定为指定周期净正收益的样本外校准概率乘以 100；Baseline、Lift、幅度、时机、经济 Edge 与可靠性独立。
- 冻结 5D/20D/60D、PIT 三时间、Universe、成本、Bundle、Candidate/LKG 与 `ABSTAIN` 合同。
- 发布授权仅 `RESEARCH` 与 `SHADOW`；`DECISION_SUPPORT` 不属于本版本。
- 推断、训练、评测、状态、比较和恢复计划全链路 0 Agent、0 LLM Token、0 网络、0 第三方 Python 依赖。
- 增加 Linux seccomp、user/network namespace、确定性封包、Fuzz、恶意输入、PIT 和生命周期验证。
- 保留 SPY/VIX 负向基线；工程通过不等于 Alpha，能力保持 `SHADOW_ONLY / OUTCOME_NOT_PROVEN`。

- 刷新目标仓公开基线至 `LinzeColin/MetaDatabase@522b8bee22b572a0bbe15c9cf0b4aea513594805`，并继续绑定相关规则文件的精确 Hash。
- 新增 `REMOTE_HOST_EMBEDDED_ONLY` 与 macOS 零足迹合同：禁止 macOS Runtime 安装、`launchd`、本机持久缓存/日志/状态与常驻进程。
- 新增 `verify_macos_zero_footprint.py`：在隔离 HOME/XDG/TMP 下运行 self-check、推断和训练，调用结束后验证新增文件=0、持久字节=0、遗留进程=0；同时扫描 `.plist/.service/.timer/.socket` 与可执行 launchd 入口。
- 锁定 6 个成熟同行的版本、commit、许可证与采用/拒绝理由；研究在连续两次高质量复核未增加 v0 Runtime 机制后停止。
- 修复安装后 Skill 子包测试错误依赖外层 `CODEX_LANDING_INSTRUCTIONS.md` 的边界缺陷；子包可独立执行冻结测试，外层操作文档由外层任务包验证。
- 完成公开 exact-content 快照上的 preflight → apply → target-entry verify → 340 项子包测试 → rollback 闭环；真实目标工作树官方 Registry Validator 保留为 Codex 最后一公里 Oracle。
- 适配 `LinzeHomeHub@fccd7eeeb224107d471fa6b6b54c801135fe1ec3` 的 Status v3：保留四个一级入口，在“运行”页内嵌业务基线治理并接入健康行动清单；`preflight/apply/verify/rollback` 可逆且不新增服务、数据库、域名或一级入口。
- 将统一 Release Oracle 改为组件级可观测、并行且有界执行；10,000 次确定性、10,000 次合同 Fuzz、隔离与静态组件在同一 Subject Hash 上完成并聚合为单一回执。

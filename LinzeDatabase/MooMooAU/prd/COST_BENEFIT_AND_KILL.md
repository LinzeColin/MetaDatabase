# 成本收益、敏感性、机会成本与 Kill Criteria

## 收益区间

| 收益来源 | 低场景 | 中场景 | 高场景 | 置信度 |
|---|---|---|---|---|
| 手工邮件归档节省 | 邮件量低，节省有限 | 月度报表、股息和安全通知稳定增长 | 多年历史与多类型邮件显著 | 中 |
| 首次解析复用 | 仅一个消费者时有限 | 2–3 个 MetaDatabase 项目复用 | 多数据产品长期复用 | 中高 |
| 审计与恢复 | 日常价值不显著 | 报税、费用核对和账户复盘时明显 | 争议、邮箱清理或迁移时高 | 高 |
| 隐私与安全 | 减少明文散落 | 形成统一加密与证据链 | 多项目长期积累时显著 | 高 |
| Gmail 清理 | 少量手工可替代 | 所有类型自动 M3 | 长期保持邮箱整洁 | 高 |

## 成本区间

| 成本来源 | 低场景 | 高场景 | 敏感变量 |
|---|---|---|---|
| 初次开发 | Walking Skeleton 和少量模板 | 多种 PDF/XLSX 模板与复杂血缘 | 文档类型数量 |
| 一次性配置 | OAuth、GitHub App、Secret、Recovery Key | OAuth 发布状态或组织策略复杂 | Google/GitHub 账户配置 |
| 日常运行 | 每日一次小批量 GitHub-hosted Job | 历史回填、重处理和大附件 | 邮件量、附件大小 |
| 存储 | 内容寻址和单 Timeline 较低 | 多年 Raw/LFS 增长 | 邮件/附件大小、重处理策略 |
| 维护 | 模板稳定时低 | Moomoo/Gmail/GitHub 接口变化 | 外部变化频率 |
| 安全保证 | 自动测试复用 | 高敏变更需额外红队与恢复演练 | 权限与格式变化 |

## 机会成本

- 完整 Processed 解析会延后其他 MetaDatabase 项目；因此先 Raw Walking Skeleton，再按真实复用价值扩展 Parser。
- 过度复杂的 Codex Auto、第二数据仓或常驻数据平台会增加治理成本，已明确排除。
- Timeline 历史图片价值低且污染 Git/LFS，已明确只保留一张最新资产。

## 敏感性分析

1. **邮件量低：** 直接时间收益下降，但完整 Raw、M3 和恢复价值仍存在；Parser 应按需扩展。
2. **邮件量高：** Gmail 分页、LFS 和 Full Reconcile 成本上升；内容寻址、分区和容量 Gate 成为主约束。
3. **模板频繁变化：** Processed 维护成本上升；Verified Unknown 和 Raw-only 降级必须可靠。
4. **下游项目增加：** Processed JSON/Parquet 与血缘收益提高，优先投资稳定 Schema。
5. **Codex Auto 不稳定：** 不影响数据面，因为 Auto 不是控制路径；开发线程与 GitHub Actions 足够运行和修复。

## Kill Criteria

| ID | 触发条件 | 默认动作 | 恢复 Gate |
| --- | --- | --- | --- |
| KILL-001 | 任何非 Moomoo 邮件被完整读取、下载或修改 | 立即关闭发现后续与 M3，撤销 OAuth，安全调查 | 根因修复且 AC-001/004/006 全量通过 |
| KILL-002 | 公开仓、日志、Issue、PR 或 Artifact 出现敏感明文/Secret | 停机、清理、轮换、历史修复 | 事件关闭且 AC-011/012/016/022 通过 |
| KILL-003 | Raw 远端恢复 SHA 与 Gmail RAW 不一致 | 禁止 M3，保留 Gmail 原件 | AC-007/013/027 通过 |
| KILL-004 | 禁止 Gmail 端点被调用或 thread trash 发生 | 撤销 OAuth、尝试可逆恢复、停止生产 | AC-006/018 通过并安全复审 |
| KILL-005 | Recovery Key 无法恢复抽样密文 | 停止 M3 和新写入，修复密钥链 | AC-012/032 通过 |
| KILL-006 | 真实邮件/附件/Secret 被发送给模型 | 禁用模型相关自动化并安全调查 | AC-020/024/033 通过 |
| KILL-007 | 私有仓或 LFS 达到 Red 容量阈值 | 停止回填和非必要衍生数据 | 容量方案通过且不增加第二数据仓 |
| KILL-008 | Full Reconciliation 存在无法解释漏件 | 降级 Raw-only，停止 M3 | AC-003/025 通过 |
| KILL-009 | Parser 静默地产生错误业务数据 | 回退 current 指针，隔离新版本 | Golden/Blue-Green/Oracle 全通过 |
| KILL-010 | 连续 90 天维护成本持续显著高于避免的手工与重复处理收益 | 保留加密 Raw，暂停 Processed/Timeline 自动化 | 重新证实收益覆盖成本 |

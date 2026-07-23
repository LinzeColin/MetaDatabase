# Baseline、目标、测量与观察周期

## Baseline 原则

Baseline 只使用已观察事实和明确的“尚未建立”，不把少量样本外推为稳定业务量。真实邮件数量、精确日期和账户活动属于私有数据，不进入公开 Evidence。

| ID | 指标 | Baseline | 目标 | 测量方式 | 观察周期 |
| --- | --- | --- | --- | --- | --- |
| MET-001 | 非 Moomoo 误伤次数 | 未自动化 | 0 | Gmail API call log 与 non-target fixture oracle | 每次运行/持续 |
| MET-002 | 已验证 Moomoo Raw 捕获率 | 手工、不可审计 | 100% | Full Reconciliation candidate set vs private inventory | 每周 |
| MET-003 | Raw 字节恢复正确率 | 0 | 100% | Gmail RAW SHA-256 vs remote decrypt SHA-256 | 每封消息 |
| MET-004 | 错误 M3 次数 | 0 自动操作 | 0 | Gate state vs messages.trash calls | 每次运行 |
| MET-005 | 公开敏感泄漏 | 无项目 | 0 | PII/金融规则+熵扫描 | 每个 PR/运行 |
| MET-006 | 逻辑重复对象 | 未知 | 0 | content ID、Message ID、Merkle Root 对账 | 每次运行 |
| MET-007 | 数据新鲜度 | 手动 | P95 ≤ 24h | internalDate 到 private commit 完成 | 滚动 30 天 |
| MET-008 | Timeline 历史图片 | 1 张手工图 | 0 历史、1 最新 | Release Asset 与 Git/Artifact 扫描 | 每次运行 |
| MET-009 | 正常例行人工操作 | 手工下载整理 | GA 后 90 天为 0 | 人工干预事件 | 滚动 90 天 |
| MET-010 | 主动恢复演练通过率 | 0 | 100% | Chaos/Recovery mandatory suite | 每次发布与季度 |
| MET-011 | 本地设备资源使用 | 潜在手工下载 | 0 | 部署架构和用户设备依赖扫描 | 持续 |
| MET-012 | 重复首次解析 | 跨项目潜在重复 | 0 | 消费者调用 Processed 而非 Raw parser | 每个下游集成 |

## 统计口径

- 误伤分母不是“被处理邮件数”，而是所有非目标 Fixture 与真实 Gmail 中可被发现的非目标消息；任意一次完整读取/下载/修改即失败。
- 捕获率只针对**确定性已验证 Moomoo**，未知新发件人不算漏件，直到注册表通过证据更新。
- 数据新鲜度从 Gmail `internalDate` 到私有远端 Commit 与恢复 Gate 完成；GitHub 排队延迟保留在观测中。
- Timeline 数量检查同时扫描 Git 树、LFS、Release Assets、Actions Artifacts 和 Cache 配置。
- 90 天人工操作只计算正常例行维护；不可预测的外部 OAuth 撤销或平台事故单独分类。

## 成功与证伪

若 90 天后系统仍需频繁人工处理模板、授权、容量或失败，且节省的手工时间与跨项目复用收益明显不足，则触发 KILL-010：保留完整加密 Raw，暂停 Processed 和 Timeline 自动化，避免沉没成本继续扩大。

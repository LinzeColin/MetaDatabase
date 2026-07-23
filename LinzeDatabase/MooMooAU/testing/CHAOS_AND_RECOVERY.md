# Chaos Engineering 与 Recovery Plan

## 原则

不等真实故障出现；在每个发布阶段主动制造失败，证明系统不会误伤、不会产生虚假成功并能恢复。

## Chaos Matrix

| ID | 注入 | 预期行为 | Recovery Oracle |
|---|---|---|---|
| CH-01 | Gmail 429 | 指数退避；不重复对象/M3 | 最终与真值集合一致 |
| CH-02 | Gmail 500/503 | 有界重试，失败保留原件 | 下一次运行恢复 |
| CH-03 | History ID 404 | 自动 Full Reconcile | 候选差异 0 |
| CH-04 | 分页中途断网 | 保存安全 Checkpoint 或重头幂等 | 无漏件/重复 |
| CH-05 | 私有 Git Push 失败 | 不发布公开成功、不 M3 | 重试成功后继续 |
| CH-06 | 私有 Commit 后公开 Push 失败 | PENDING_RECONCILIATION | 补偿后 Evidence 一致 |
| CH-07 | 远端密文比特损坏 | Recovery Gate 失败、不 M3 | 从 Gmail 原件重建 |
| CH-08 | age Identity 错误 | 不 M3、不覆盖 Raw | 正确 Identity 恢复 |
| CH-09 | PDF Password 错误 | WAITING，Raw/M3 继续 | 正确 Secret 重处理 |
| CH-10 | Git Push 冲突 | 拉取、内容 ID 合并、重试 | 单一逻辑对象 |
| CH-11 | Workflow 取消 | finally 清理、无半成功声明 | 重跑幂等 |
| CH-12 | Runner OOM/超时 | 无明文 Artifact/Core；不 M3 | 降批次后恢复 |
| CH-13 | Timeline 删除后上传失败 | `TIMELINE_REPAIR_REQUIRED`，资产为 0，不建备份 | 下次从同一 Processed Snapshot 重建固定资产，稳态恢复为 1 |
| CH-14 | Trash API 成功但确认读取失败 | 状态 UNKNOWN，重取确认 | 不重复误操作 |
| CH-15 | Sender Registry 更新竞态 | 第二验证失败则不 M3 | 稳定版本重跑 |
| CH-16 | Public Evidence 渲染泄漏测试值 | 发布 Gate 阻止 | 清理后再发布 |
| CH-17 | Codex Auto 停用 | 数据面继续 | 04:30 运行正常 |
| CH-18 | GitHub schedule 漏跑 | Evidence 变 stale；开发线程可 dispatch；周日补偿 | Full Reconcile 差异 0 |

## 常态化节奏

- PR：轻量故障单元/集成；
- 发布前：完整 Mandatory Chaos；
- 每季度：真实 Recovery Key 抽样恢复、History Full Reconcile、Timeline Asset 恢复；
- Secret/权限/Parser 重大变化后：专项演练。

## Recovery Evidence

每次演练记录 Run ID、注入点、代码/容器版本、输入摘要、预期、观察、恢复时间、数据一致性、M3 调用数、公开 Evidence 和未解决风险。真实内容不进入公开证据。

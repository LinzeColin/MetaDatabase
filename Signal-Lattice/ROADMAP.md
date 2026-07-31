# Signal Lattice v0.0.0.1.41 Roadmap

## 当前版本必须完成

1. **Stage 0｜移动仓语义协调**：读取最新 MetaDatabase main，将任务分类为 satisfied / apply / adapt / equivalent / conflict / blocked / obsolete；保留更优上游实现。
2. **Stage 1｜完整替换落库**：以本任务包中的 `Signal-Lattice/` 为北极星实现，保留目标仓 `Signal-Lattice/Stock_Skill/` 的资料与历史，完成双平面登记。
3. **Stage 2｜环境绑定**：只绑定 OVH、Moomoo OpenD、Cloudflare Tunnel、Private-Database、R2、OCI 和 Status 所需的真实凭证与端点。
4. **Stage 3｜一分钟自运行链**：启动 GitHub Source Reconcile、市场快照、全部 Active Skill 隔离执行、中枢协调、唯一建议、Outbox 和 Status。
5. **Stage 4｜即时验收**：用真实环境执行 Golden / Black / Abuse / Degraded / Recovery Path；不等待真实时间 Soak。
6. **Stage 5｜公网交付**：验证 `signal-lattice.linzezhang.com` 能看到非空完整循环和唯一建议，再执行 Status Closure、备份、commit、push、merge。

## 后续版本，不污染当前范围

- 明确授权后才允许增加运行时模型，并同时实现 Token/费用预算、可观测、限流、熔断和 NO_ACTION 降级；
- 明确授权后才允许增加新资产类别；
- 自动交易不在路线图内。

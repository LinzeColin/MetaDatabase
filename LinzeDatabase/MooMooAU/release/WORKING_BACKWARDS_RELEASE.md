# Working Backwards 与 Safe Release

## 发布顺序

1. PR/FAQ 先于实现，确认客户问题和预期结果；
2. Walking Skeleton 只用合成数据，证明数据流和证据链；
3. Alpha 完成软件/模型双流水线；
4. Beta 只捕获少量真实 Raw，不执行破坏性操作；
5. M3 Canary 从 Mutation Budget=1 开始；
6. Parser 与 Timeline Blue-Green，不覆盖旧版本；
7. GA 只在完整 Acceptance、Chaos、Recovery、Security 和 Model Gate 后启用；
8. 发布后持续测试、Full Reconcile、恢复演练和 Kill 监控。

## 发布阶段矩阵

| 阶段 | Discovery | Raw | Processed | M3 | Timeline | 数据 |
|---|---:|---:|---:|---:|---:|---|
| Walking Skeleton | synthetic | synthetic | synthetic | simulated | synthetic | 合成 |
| Alpha | synthetic | test private | synthetic | 0 | synthetic | 合成 |
| Beta | on | on | off/deferred | 0 | off | 少量真实 |
| M3 Canary | on | on | safe/deferred | budget 1 | off | 少量真实 |
| Blue-Green | on | on | old+new | bounded | candidate vs current | 真实 |
| GA | on | on | on | bounded/on | one live | 全量已验证 |

## 发布后测试

- 每日 Evidence 新鲜度和 Gate；
- 周日 Full Reconcile；
- 每个 Parser 新版本 Shadow/Blue-Green；
- 依赖、Action 和容器变化全量安全测试；
- 每季度恢复和容量演练；
- 任意异常自动降级 M3，而不是继续冒险。

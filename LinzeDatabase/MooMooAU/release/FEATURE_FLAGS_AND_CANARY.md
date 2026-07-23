# Feature Flags、Canary 与 Blue-Green

## Flags

```yaml
discovery_enabled: true
raw_archive_enabled: false
processing_enabled: false
m3_enabled: false
timeline_enabled: false
public_evidence_enabled: true
full_reconcile_enabled: true
mutation_budget_per_run: 0
parser_current_version: none
```

## 提升顺序

1. `discovery_enabled`：合成与最小真实元数据验证；
2. `raw_archive_enabled`：远端恢复 Gate 通过；
3. `processing_enabled`：Golden Parser 与血缘通过；
4. `m3_enabled`：安全/恢复/端点测试通过，Budget=1；
5. `timeline_enabled`：时间 Oracle 与单 Asset 通过；
6. 逐步提升 Mutation Budget，但始终有界。

## 自动降级

- 误伤/禁止端点/公开泄漏：关闭所有生产 Flag；
- 私有恢复失败：关闭 M3，Raw 可在安全时重试；
- Parser 失败：关闭对应 Parser，Raw/M3 按显式 Deferred 规则继续；
- Timeline 失败：关闭 Timeline，保留上一 Asset；
- Full Reconcile 差异：关闭 M3，执行调查；
- Auto 失败：无 Feature Flag 变化。

## Blue-Green

Parser vNext 在相同加密 Raw 上生成新 Processed 分区，与 current 的字段、统计、血缘和 Timeline Facts 对比。差异必须解释或由新 Oracle 接受；切换只改变 current 指针，不删除旧数据。

# ADP v1.2 Roadmap

## 执行规则

- 严格串行，WIP=1；一次只执行一个 Task 和一个 Acceptance 目标组。
- 当前任务的阻断 Acceptance 全部通过并由独立上下文复核后，才能解锁下一任务。
- 同一路径失败两次后必须回滚、缩小复现并改变方案；禁止以扩大范围掩盖失败。
- 任一 `UNKNOWN/BLOCKED/NOT_RUN` 均不算 PASS；实施者不能为自己的 Gate 签字。

## 关键路径

| 顺序 | Task ID | 目标 | 出口 |
|---|---|---|---|
| S0 | `ADP-V12-S0-T001` | 任务包、归档、追溯、双平面 | 七角色、142 行历史追溯、远端恢复门定义完整 |
| S1 | `ADP-V12-S1-T001` | Google News retry/backoff 候选 | 正负控通过，不切换 live、不改 cron |
| S2 | `ADP-V12-S2-T001` | stats-gov 诊断 | 错误分类可复跑；无证据则保持降级 |
| S3 | `ADP-V12-S3-T001` | Science Advances PubMed adapter | ESearch/EFetch、去重、限流和失败关闭通过 |
| S4.1 | `ADP-V12-S4-T001` | 中文人话内容 | 真实英文条目得到诚实中文解释/回退 |
| S4.2 | `ADP-V12-S4-T002` | 移动端四标签 | 六主题 375×812 仅四标签，桌面不回归 |
| S4.3 | `ADP-V12-S4-T003` | 视觉与动效门 | 六主题/视频/reduced-motion 负控可阻断 |
| S5.1 | `ADP-V12-S5-T001` | 版本及运行时真相 | 1.2.0 身份链、Python `>=3.12` 对齐 |
| S5.2 | `ADP-V12-S5-T002` | 7×24 运维能力 | 15 分钟探针、SLO、恢复和升级提案门就绪 |
| S6 | `ADP-V12-S6-T001` | RC、部署与封账 | canary/rollback/production/14 日稳定期通过 |

## 版本状态机

```text
0.41.0 CURRENT_LIVE
  → 1.2.0-rc.N CANDIDATE
  → CANARY
  → 1.2.0 PRODUCTION_DEPLOYED
  → PRODUCTION_ACCEPTED（14 个连续健康日）

任一阻断失败 → ROLLED_BACK → 0.41.0 或最近接受版本
```

## 时间预算

预计 10 个有界 Run Contract、8–15 个工程日；连同不可跳过的稳定期约 3–5 周。免费容量或外部来源不稳定只能降低结论或触发升级提案，不能降低验收门。

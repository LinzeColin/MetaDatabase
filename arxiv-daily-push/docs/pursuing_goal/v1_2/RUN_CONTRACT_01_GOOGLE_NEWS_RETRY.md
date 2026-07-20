# Run Contract 01 — `ADP-V12-S1-T001`

## Goal

在不部署、不改 cron、不引入付费 API 且不静默切换 live 来源的前提下，为 Google News 候选路径增加有上限的 retry/backoff，并证明间歇 503 可恢复、确定性拒绝仍失败关闭。

## Minimum Scope

- Google News 候选 fetch 路径及最小可测试 helper。
- 必要的 source registry/fixture、来源与用户中心同步文件。
- 目标单元/集成测试、source sync gate 和 full-suite 差分证据。

## Non-goals

- 不处理 stats-gov 或 PubMed。
- 不把 Google 设为 live primary，不删除 Bing fallback。
- 不修改 Worker cron、D1/R2 schema、生产数据或线上配置。
- 不把重试扩展到所有 feed，也不顺带重构 monolithic Worker。

## Required Behavior

- `max_attempts=3`；仅 timeout、502、503、504 重试；延迟 `1000ms, 3000ms`。
- 400、401、403、404、有效响应但 parse-zero 不重试。
- fetch/sleeper 可注入；每次结果记录 attempt count、terminal status、reason code、delay 和 fallback。
- 最坏只新增两次外部 subrequest，并留下小于 Cloudflare 上限的核算证据。

## Deterministic Tests

- 正向：503→200；503→503→200。
- 负向：403 一次终止；404 一次终止；三次 503 耗尽；timeout 耗尽；parse-zero 不重试。
- 测试必须执行真实实现路径；静态字符串或源码正则不能单独作为行为证明。

## Validation

```bash
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest <new-focused-tests> -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest arxiv-daily-push/tests/test_source_registry.py arxiv-daily-push/tests/test_user_center_candidate_pool.py arxiv-daily-push/tests/test_owner_controls.py -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s arxiv-daily-push/tests -q
```

完整 suite 按 test name 与锁定历史集合比较，candidate-only failure/error 必须为零。

## Risks, Rollback and Stop

- 风险：重试放大延迟/请求、错误分类错误、fallback 被无意改变、source/user-center 漂移。
- 回滚：删除候选策略调用并恢复原 Bing 活动路径；不得依赖数据迁移。
- 停止：需要付费 API、需要改 cron/live、无法证明 subrequest 预算、负控未阻断或同一路径连续失败两次。

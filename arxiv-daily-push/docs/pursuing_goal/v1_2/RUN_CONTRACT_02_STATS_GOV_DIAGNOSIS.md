# Run Contract 02 — `ADP-V12-S2-T001`

## Goal

在不部署、不改 cron、不引入付费或绕过方案的前提下，让 stats-gov 的真实诊断路径稳定区分
`EDGE_TIMEOUT`、`HTTP_STATUS`、`PARSE_ZERO` 和 `SUCCESS`，再根据可复跑的本地与 Cloudflare
edge 证据决定是否存在可提交的最小 adapter 修复；证据不足时保持 degraded，不把猜测写成结论。

## Immutable Subject and Preconditions

- Subject 是 MetaDatabase 当前分支中的 `arxiv-daily-push/`；禁止恢复 CodexProject 旧源。
- 前置任务 `ADP-V12-S1-T001` 必须保持 `5/5 PASS`；live 产品仍为 `0.41.0`。
- live `worker_cloud.js`、三个 cron、D1/R2、来源启停状态和 Cloudflare 资源均为只读基线。
- 当前事实只允许从确定性夹具、官方 `https://www.stats.gov.cn/sj/zxfb/` 和既有只读
  `/api/a0-canary` 取得；历史“间歇超时”不能单独决定本轮结论。

## Minimum Scope

- 一个 stats-gov 候选诊断模块：fetch、parser 和 timeout 可注入，输出稳定 reason code 与最小证据字段。
- 四类确定性夹具/负控、真实实现路径测试和一个只读验证入口。
- 一份公开安全的诊断/决策 receipt，以及必要的 machine facts、HANDOFF、Owner 页面和双平面同步。
- 来源专项门、任务包门、迁移治理门、安全门和 full-suite 精确问题集差分。

## Non-goals

- 不处理 PubMed、中文内容、移动端、视觉、版本或 SLO；不进入 S3。
- 不部署、不改 Worker、cron、D1/R2 schema、生产数据、来源 ID、板块或启停状态。
- 不增加 retry、代理、镜像、付费 API、未授权服务、浏览器绕过、请求头伪装或反爬规避。
- 不把本地直连成功外推为 Cloudflare edge 成功，也不把单次超时外推为永久不可达。

## Required Behavior

同一个 `diagnoseStatsGov` 实现按以下互斥顺序返回结果：

1. fetch 因受控 timeout 终止 → `EDGE_TIMEOUT`；
2. 收到非 2xx 响应 → `HTTP_STATUS`，保留数值状态码；
3. 2xx 响应经生产等价 parser 得到零项 → `PARSE_ZERO`；
4. 2xx 响应且 parser 得到至少一项 → `SUCCESS`，保留解析数量。

结果必须记录 source/url、reason code、HTTP status（若存在）、parsed count 和是否可用于 live
决策；不得写生产、静默吞零或把异常伪装成成功。测试必须执行真实模块路径，不能复制分类逻辑。

## Evidence-based Decision Gate

- 先用确定性夹具证明四类互斥，再做有界的官方直连与既有 Cloudflare edge 只读采样。
- 只有证据能在不改变成本、安全边界和 live 配置的情况下复现根因与修复效果，才允许提交最小
  adapter 修复，并为该修复补同路径正负控。
- 若 edge 仍超时、样本矛盾、修复需要 live canary 才能证明，或任何关键证据缺失，则不改 live
  adapter；stats-gov 保持 degraded，receipt 必须写明已证事实、未证事实和重新评估的最小条件。
- 单次成功或失败都不能写成“永久可达”或“永久不可达”。`UNKNOWN/BLOCKED/NOT_RUN` 不是 PASS。

## Deterministic Tests

- timeout fixture → `EDGE_TIMEOUT`，且不进入 parser；
- 503 fixture → `HTTP_STATUS`，且不进入 parser；
- 200 + empty fixture → `PARSE_ZERO`；
- 200 + official-list fixture → `SUCCESS` 且 parsed count 大于零；
- 四个 reason code 两两互异；候选模块无写入能力，成本/边界扫描无付费或绕过依赖。

## Validation

```bash
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest arxiv-daily-push/tests/test_stats_gov_diagnostic.py -q
node arxiv-daily-push/tools/verify_stats_gov_diagnostic.mjs
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest arxiv-daily-push/tests/test_security_boundary.py -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest arxiv-daily-push/tests/test_source_registry.py arxiv-daily-push/tests/test_user_center_candidate_pool.py arxiv-daily-push/tests/test_owner_controls.py -q
python3.12 arxiv-daily-push/machine/tools/check_dual_plane_ci.py --root . --projects arxiv-daily-push --require-projects
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s tests/governance -p 'test_adp_*.py' -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s arxiv-daily-push/tests -q
```

full suite 按测试名称集合与锁定基线比较，candidate-only failure/error 必须为零；
`git diff origin/main -- arxiv-daily-push/deploy/cloudflare/worker_cloud.js` 必须为空，除非本合同的
证据决策门明确支持并独立复审通过一个最小 adapter 修复。

## Risks, Rollback and Stop

- 风险：把本地网络当 edge、分类重叠、parser 与生产漂移、只读探针产生副作用、历史事实被当成新证据。
- 回滚：删除候选诊断模块、夹具和本轮同步；不依赖数据迁移，live `0.41.0` 不变。
- 停止：`diagnosis_not_reproducible`、需要付费代理/API/边界绕过/未授权服务、只读性无法证明、
  需要部署才能继续、负控未阻断，或同一路径连续失败两次。

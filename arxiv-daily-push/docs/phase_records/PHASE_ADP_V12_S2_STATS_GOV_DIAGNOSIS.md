# ADP v1.2 S2 stats-gov 诊断收尾记录

更新时间：2026-07-22 21:36:01 Australia/Sydney

## 任务与边界

- Task：`ADP-V12-S2-T001`
- Run Contract：`docs/pursuing_goal/v1_2/RUN_CONTRACT_02_STATS_GOV_DIAGNOSIS.md`
- Decision scope：`developer_check`
- S2 只实现 stats-gov 只读诊断模块、四类确定性夹具与验证、事实 receipt、候选登记和
  Owner 同步面；不处理 PubMed、中文内容、移动端、视觉、版本、运维或部署。
- `worker_cloud.js`、`wrangler_cloud.jsonc`、三个 cron、来源启停、D1/R2 与线上版本均未修改。

## S2 验收结果

| Acceptance | 状态 |
|---|---|
| `ACC-V12-S2-001` | `PASS` |
| `ACC-V12-S2-002` | `PASS` |
| `ACC-V12-S2-003` | `PASS` |

fresh-context 独立 verifier 终局：`3/3 PASS`，`P0=0`、`P1=0`、`UNKNOWN=0`、
`BLOCKED=0`、waiver 为零。已验 dirty-source Subject SHA-256 为
`c4174a1712d6b102a543f900cbf4d44447115e5cdeabe6a78a86ff5438d55c13`，测试前后稳定；
evidence root 为 `711d324114d5fa0659954abe5ce31909eed7aa55596d656f948afabb91e2b36d`。
独立 review ZIP 只在 Owner 本机保存，公开登记 SHA-256
`4c8f11fe52379e2c8fadc17c31d93e0a6a69c8cc6340a9b3a51f92dfadd5d744`；finalizer、
`--verify` 与 78-entry `unzip -t` 全部通过。完整公开安全摘要见
`machine/runs/ADP-V12-S2-T001-developer-check.json`。

## 诊断事实与工程决定

- `EDGE_TIMEOUT`、`HTTP_STATUS`、`PARSE_ZERO`、`SUCCESS` 四类结果互斥且可由真实候选模块
  与确定性夹具复跑；sample/empty parser 与 Worker 当前 `parseA0` 逐项一致。
- 历史 `2026-07-22T10:07:12Z` edge `EDGE_TIMEOUT/0` 没有保留 raw，明确登记为
  `STALE_UNVERIFIED_RAW_UNAVAILABLE`，不用于当前或永久不可达结论。
- 最新已绑定 raw hash 的 official/edge 点样分别在
  `2026-07-22T10:36:12.687Z`、`2026-07-22T10:36:47.591Z` 得到 `SUCCESS/15`。
  这只证明既有 control 曾在零 adapter 变更下恢复，不外推当前或永久健康。
- 这些点样由前序 A7 验证运行取得；终局 r2 未重新请求外部来源，只对 sealed A7 包内的
  raw bytes/hash 与事实链复验，因此它不是新的实时健康点样。
- 工程决定为 `degraded_preserved` / `NO_ADAPTER_FIX`：保留既有失败时降级行为与来源启停，
  不提交 timeout/retry/header 等无因果证据的猜测性修复。
- 诊断模块每次最多一个外部 subrequest，手动重定向失败关闭，零写入、零付费、零代理、
  零边界绕过、零未授权新服务。

未来只有再次出现带可复核 raw hash 的重复 `EDGE_TIMEOUT`，并由另获授权的隔离 matched
control/candidate 在相同 URL、parser 与成本下至少两次证明 candidate 为 HTTP 2xx 且
`parsed_count>0`、control 同时仍超时，才可另开 Run Contract 评估最小 adapter 变更。

## 整阶段复审发现与修复

首轮独立复审对旧 Subject `ebc00c7c…76d` 裁定 `FAIL / ACTION ACT`，发现一个 P1：Owner 页面
把未保留 raw 的历史 timeout 当作缺时间/hash 的当前事实，并指向尚不存在的 developer-check
receipt。修复后：

1. 新增 `acceptance_claimed=false` 的事实型 diagnosis receipt，历史与最新点样分层登记；
2. registry 绑定 receipt path/SHA 与最新 observation ID、时间、分类、数量；
3. canonical renderer 对 receipt 缺失、hash、时间、分类、数量漂移全部 fail-closed；
4. `SOURCE_CATALOG.md`、四个用户中心页面与 HANDOFF 同步事实链和语义边界；
5. fresh verifier 对新 Subject 独立复跑 14 项证据链检查与 9-case 负控，关闭
   `F-ADP-V12-S2-001`，没有开放 finding。

## 回归证据

| 检查 | 结果 |
|---|---|
| stats-gov 专项测试 | `10/10 PASS` |
| 可执行 Node verifier | `PASS` |
| 独立 fail-closed 负控 | `9/9 PASS` |
| 独立 Owner 事实链检查 | `14/14 PASS` |
| S1 Google/Bing 回归 | `16/16 PASS` |
| 安全边界回归 | `14/14 PASS` |
| MetaDatabase 迁移治理回归 | `65/65 PASS` |
| 双平面与 taskpack integrity/compatibility/drift | `PASS` |
| ADP full suite 原始结果 | `949` 项；`2 failures + 11 errors + 29 skips`，原始状态 `FAIL` |
| sealed failure/error 测试名集合差分 | `PASS`；`candidate_only=[]`、`baseline_only=[]` |

full suite 没有被包装成绿色。2 个 failure 与 11 个 error 精确属于 sealed baseline 问题集；
本轮只证明没有新增 failure/error test identity。没有恢复 `功能清单.md`、`开发记录.md`、
`模型参数文件.md`，也没有通过修改或跳过测试伪造 PASS。

## 收尾自引用边界与下一步

独立 Subject 冻结发生在 verdict 之前；本 receipt、phase record、machine facts、其确定性生成的
七份人类文档，以及 HANDOFF/taskpack README/CHANGELOG 的收尾状态文字被明确排除，以避免把
“验收已通过”本身放进待验 Subject 形成自引用。项目规则要求的 20 个用户中心页面提交前
时间戳更新也只允许修改时间戳行，并按去除该行后的字节等价复核。它们由最终 Git tree、比例回归和 PR CI 绑定，
不改变已验实现、诊断事实或 Owner 证据链。

S2 不授权 live 切换或部署。下一轮唯一任务是 `ADP-V12-S3-T001`（Science Advances PubMed
E-utilities adapter）；S3 当前为 `NOT_RUN`，且 Run Contract 尚未创建。必须先依据 Task Graph
与 Acceptance Contract 锁定独立合同，之后才能实现；不得从本记录预签 S3–S6。

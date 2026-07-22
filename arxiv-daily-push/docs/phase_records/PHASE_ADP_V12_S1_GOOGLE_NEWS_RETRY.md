# ADP v1.2 S1 Google News 有界重试收尾记录

更新时间：2026-07-22 18:49:46 Australia/Sydney

## 任务与边界

- Task：`ADP-V12-S1-T001`
- Run Contract：`docs/pursuing_goal/v1_2/RUN_CONTRACT_01_GOOGLE_NEWS_RETRY.md`
- Decision scope：`developer_check`
- S1 只增加 Google News RSS 候选模块、候选登记、夹具、验证器、测试和 Owner 同步面。
- `worker_cloud.js`、`wrangler_cloud.jsonc`、cron、D1/R2 与线上来源均未修改；没有部署。

## S1 验收结果

| Acceptance | 状态 |
|---|---|
| `ACC-V12-S1-001` | `PASS` |
| `ACC-V12-S1-002` | `PASS` |
| `ACC-V12-S1-003` | `PASS` |
| `ACC-V12-S1-004` | `PASS` |
| `ACC-V12-S1-005` | `PASS` |

独立 verifier 终局：`5/5 PASS`，`P0=0`、`P1=0`、`UNKNOWN=0`、`BLOCKED=0`。
已验实现与 Owner 同步面使用 receipt 内列明的 14 文件逐项 SHA-256 manifest；按 UTF-8
字节序排列路径、以“文件 SHA-256 + 两个空格 + POSIX 相对路径 + 换行”聚合后的 SHA-256 为
`1e06bd09aa6741249245802975166d281bf141e10d6204f32bdbea7141566b21`。完整文件清单与算法见
`machine/runs/ADP-V12-S1-T001-developer-check.json`；receipt 自身及收口生成面由最终 Git tree 绑定。

## 实现事实

- 固定策略：最多 3 次；仅 timeout、502、503、504 重试；退避 `1000ms`、`3000ms`。
- 400、401、403、404 和 HTTP 200 解析零条均单次终止；结果显式记录 attempt、终态、原因、
  已用延迟和 fallback，且候选模块没有写入能力。
- fetch、sleeper、parser 可注入；测试从真实候选模块路径执行，不以复制逻辑或静态字符串代替。
- `redirect: 'manual'`；真实 localhost 302→200 负控实测只有 1 次网络请求，终态为 `HTTP_302`。
- live `gnews-us-tech` 继续使用 Bing News RSS；Google
  `gnews-us-tech-google-candidate` 保持 `candidate_not_live`。
- 单次 scheduled invocation 的当前最坏外部子请求数为 `32`；候选未来获授权替换当前单次
  Bing 路径后投影为 `34/50`，保留 `16` 次余量。本轮没有执行该替换。

## 整阶段复审发现与修复

独立复审先发现两个 P1，修复后重新裁定为 PASS：

1. 自动跟随重定向会让实际外部请求数超过 attempt 证据。已改为手动重定向、3xx 失败关闭，
   并加入真实 HTTP server 负控。
2. 手写 `SOURCE_CATALOG.md` 附录会被 canonical renderer 擦除。已让
   `owner_controls.py` 从候选登记生成附录；临时渲染与仓内文档字节一致，SHA-256 为
   `55413d486cf5b2733a1e4ccb0ad145fffdb09e8fff317a8cbc237f3a359e9082`。

最终事实同步首次触发双平面中文门，因为总览含 3 个未登记英文术语；已改为等价中文事实表述，
重新渲染后再运行双平面与任务包门，未通过前不允许提交。

## 复跑证据

| 检查 | 结果 |
|---|---|
| 候选专项测试 | `16/16 PASS` |
| owner controls | `5/5 PASS` |
| source registry | `3/3 PASS` |
| 安全边界回归 | `14/14 PASS` |
| MetaDatabase 迁移治理回归 | `65/65 PASS` |
| ADP full suite | `939` 项；`2 failures + 11 errors + 29 skips` |
| sealed failure/error 测试名集合差分 | `PASS`；`candidate_only=[]`、`baseline_only=[]` |

full suite 仍非全绿；2 个 failure 与 11 个 error 精确属于封存基线问题集。本轮没有恢复
`功能清单.md`、`开发记录.md`、`模型参数文件.md`，也没有修改或跳过测试来伪造全绿。

full-suite 原始证据不提交公开仓，只在 receipt 登记不可逆摘要：runner log SHA-256 为
`5c1eb9945d9e0ae5c86837b1211f16290fb003cd5e1cb8b1b82095cb70ff5935`；仓内 sealed baseline
路径为 `docs/archive/taskpacks/2026-07-20/ADP_META_MIGRATION_e1af471c_2026-07-20_acceptance_review_taskpack.zip`，
SHA-256 为 `c5ab970698f3ca3fd6bba6939123fae2c0cb6ecd5b7cd6058a622b7fabfcc084`；comparator output
SHA-256 为 `f10cd57a63a9381c8df188d1670ecd7418e166132c433cba77e951c78e841bda`。公开记录不包含本机
临时路径。

## 下一步与停止条件

S1 不授权 live 切换或部署。下一轮唯一任务是 `ADP-V12-S2-T001`；当前任务包尚无 S2
Run Contract 文件，因此必须先依据 `TASK_GRAPH.yaml` 与 `ACCEPTANCE_CONTRACT.yaml` 锁定
独立合同，之后才能诊断 stats-gov。S2 当前为 `NOT_RUN`，不得从本记录推断任何诊断结论。

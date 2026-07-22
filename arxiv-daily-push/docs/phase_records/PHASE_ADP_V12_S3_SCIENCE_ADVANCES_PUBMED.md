# ADP v1.2 S3 Science Advances PubMed candidate 收尾记录

更新时间：2026-07-23 06:27:22 Australia/Sydney

## 任务与边界

- Task：`ADP-V12-S3-T001`
- Run Contract：`docs/pursuing_goal/v1_2/RUN_CONTRACT_03_SCIENCE_ADVANCES_PUBMED.md`
- Decision scope：`developer_check`
- S3 只实现本地、可注入、失败关闭的 PubMed ESearch→EFetch candidate、确定性夹具、
  可执行验证、候选登记与 Owner 同步；不处理中文内容、移动端、视觉、版本、运维或部署。
- `worker_cloud.js`、`wrangler_cloud.jsonc`、三个 cron、现有 Science.org RSS、来源启停、
  D1/R2 与 live `0.41.0` 均未修改。

## S3 验收结果

| Acceptance | 状态 |
|---|---|
| `ACC-V12-S3-001` | `PASS` |
| `ACC-V12-S3-002` | `PASS` |
| `ACC-V12-S3-003` | `PASS` |

fresh-context 独立 verifier 终局为 `3/3 PASS`，`P0=0`、`P1=0`、`UNKNOWN=0`、
`BLOCKED=0`、waiver 为零。已验 Subject 为 clean Git commit
`7e5ab5ae3152844e8d073bc2e0074d8bf0f5a8f7`、tree
`dab9106886077a549b5b424a098943430e6e8b91`，测试前后稳定；evidence root 为
`08fb4185df9c9c7a497673ca0c1299cb313c9aa0672c824202d616acf5bf6fbb`。

独立 review ZIP 只在 Owner 本机保存，公开登记 SHA-256
`782254fdd58a56722a988f6473f560c0dc006f08972fc62e5be4c8a24ffe3624`、大小
`143008` bytes、`47` entries；`README_FIRST.md` 位于首项，finalizer、`--verify`、
`unzip -t`、文本控制字节扫描与常见密钥模式扫描均通过。完整公开安全摘要见
`machine/runs/ADP-V12-S3-T001-developer-check.json`。

## 候选实现与成本边界

- ESearch 固定 Science Advances 期刊查询与最多 `20` PMID；空搜索只做一次请求，非空最多
  再做一次 EFetch，总计最多 `2` 个 HTTPS GET。
- 两次请求开始时间至少相隔 `1000ms`；无 API key、无 bulk、无分页、无 retry、无并发，
  `tool/email` 存在，redirect 手动失败关闭。
- 每条成功记录映射现有 `{guid,title,link,summary,published}` item，并一一保留 PMID、规范化
  DOI、NLM ID、ISSN、期刊标题、endpoint 与日期窗口 provenance。
- 任一额外/缺失/重复 PMID 或 DOI、错误期刊、非法/缺失日期、HTTP/timeout/body error、
  超尺寸或结构异常 XML 均整批零 item、`write_allowed=false`、`NO_WRITE`。
- 候选 `science-advances-pubmed-candidate` 保持 `candidate_not_live`；本轮实际 live
  external 上界仍为 `32/50`，没有因候选存在而增加生产调用。

## 首轮发现与修复

首轮 fresh verifier 对旧 Subject `3cd2138c51d14ed9717991cd5353f1fe3f517ab3` 裁定
`FAIL / ACTION ACT`：

1. `ADP-S3-F001`（L1/P1）：XML 1.0 非法 literal 字符被接受进标题，没有失败关闭；
2. `ADP-S3-F002`（L2 requirement gap）：未声明命名实体的 Oracle 为 `UNKNOWN`。

修复后，解析前逐 code point 校验 XML 1.0 合法范围；命名实体大小写敏感，只接受
`amp`、`lt`、`gt`、`apos`、`quot` 五个预定义实体或合法 numeric reference。合同明确
不解析/展开 DTD 与外部实体，因此未声明 `nbsp` 或大小写伪装实体严格拒绝，不扩张输入面。
该解释以 W3C XML 1.0 官方规范为 Oracle：
<https://www.w3.org/TR/xml/#sec-predefined-ent>。

新 Subject 补齐非法 literal、非法 numeric reference、未声明实体、大小写伪装实体负控，
以及五个预定义实体正控。fresh r2 独立关闭 `ADP-S3-F001` 与 `ADP-S3-F002`，没有开放 finding。

## verifier 自身测试构造缺陷

独立 adversarial 首尝试有 `24/26` 有效产品 Oracle 通过；另外两项因 verifier 在一个已经
包含 PUBLIC DOCTYPE 的 fixture 上再次插入 DOCTYPE，构成双 DOCTYPE。产品按合同正确
fail-closed，这不是产品失败，也不是放行豁免。verifier 保留 a1 证据、修正测试构造后复跑
对应 `2/2 PASS`，a2 与 a1 一并封存；最终有效产品 Oracle 为 `26/26 PASS`，waiver 为零。

## 回归证据

| 检查 | 结果 |
|---|---|
| PubMed 聚焦测试 | `12/12 PASS` |
| 可执行 Node verifier | `63 scenarios / 7 checks PASS` |
| fresh 独立 adversarial | `26/26 有效 Oracle PASS` |
| 安全边界回归 | `14/14 PASS` |
| S1/S2 回归 | `26/26 PASS` |
| MetaDatabase 迁移治理回归 | `65/65 PASS` |
| 双平面、taskpack integrity/compatibility/drift | `PASS` |
| 历史资产边界 | `30` 个 final-bundle 文件、`424` 个 ADP manifests 保持 |
| ADP full suite 原始结果 | `962` 项；`2 failures + 11 errors + 29 skips`，原始状态 `FAIL` |
| sealed failure/error 测试名集合差分 | `PASS`；`candidate_only=[]`、`baseline_only=[]` |

来源/Owner 同步套件原始仍是 `56` tests、`7 errors + 2 skips`；它们精确属于密封基线中
故意缺席的旧 `功能清单.md`、`模型参数文件.md` 等兼容问题，没有 S3-specific 新问题。
这些旧文件没有被恢复。根级 acceptance-bundle 当前仍因历史
`NEXT_AGENT_HANDOFF` / persistent daily-operation authorization 缺失而 `BLOCKED`；本记录
没有把它写成绿色，也没有把它当作 S3 回归。

## 收尾自引用边界与下一步

独立 Subject 在 verdict 前已冻结。本 receipt、phase record、S4.1 机器事实及其确定性生成的
七份人类文档、HANDOFF/taskpack README/CHANGELOG 的收尾文字、任务包树摘要、根 CHANGELOG，
以及提交前由项目脚本执行的 20 个用户中心时间戳更新被明确排除，避免把“验收已通过”本身
放进待验 Subject 形成自引用。任何 product/test/registry/Owner 内容或 live 边界字节变化都不在
排除范围内，必须重新验收。

S3 不授权 live 接线、发布或部署。下一任务是 `ADP-V12-S4-T001`（中文人话版 fail-closed
闭合），对应 `ACC-V12-S4-001..002`；当前为 `NOT_RUN`，Run Contract 尚未创建。必须另开
独立合同后才能开始，不得从本记录预签 S4–S6。

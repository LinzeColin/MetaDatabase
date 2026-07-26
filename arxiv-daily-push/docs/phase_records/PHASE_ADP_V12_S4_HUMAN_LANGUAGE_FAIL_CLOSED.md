# ADP v1.2 S4.1 中文人话 fail-closed 收尾记录

更新时间：2026-07-23 09:50:57 Australia/Sydney

## 任务与边界

- Task：`ADP-V12-S4-T001`
- Run Contract：`docs/pursuing_goal/v1_2/RUN_CONTRACT_04_HUMAN_LANGUAGE_FAIL_CLOSED.md`
- Decision scope：`developer_check`
- S4.1 只建立基于封存生产 Worker 的候选补丁、可执行验证、治理测试和独立浏览器证据；
  不修改 canonical `worker_cloud.js`，不处理 S4.2/S4.3、版本、运维、部署或生产接线。
- live `0.41.0` / build `c2ccc1fd01ec`、来源与板块、三个 cron、D1/R2、数据结构和数据均未改。

## S4.1 验收结果

| Acceptance | 状态 |
|---|---|
| `ACC-V12-S4-001` | `PASS` |
| `ACC-V12-S4-002` | `PASS` |

第二轮全新上下文独立 verifier 终局为 `2/2 PASS / ACTION NONE`，`P0=0`、`P1=0`、
`UNKNOWN=0`、`BLOCKED=0`、waiver 为零。已验 Subject 为 clean Git commit
`c50d7f7b6a1f01831c56d1a11b76f6ccd5248860`、tree
`d40fb7b23ceae89c3df11449b1673d48422e1e9a`；确定性物化候选 artifact SHA-256 为
`9c7ff113ce8f4249988d02bf75601153db739cbe7075cf16d916fd689240797b`，测试前后身份稳定。

独立 review ZIP 只在 Owner 本机保存，文件名为
`ADP_V12_S4_T001_acceptance_c50d7f7b_fresh_r2_acceptance_review_taskpack.zip`，公开登记
SHA-256 `68d02b5e4ae87f17b4f49c15645a1cfaaa57f1a53fc5bc5a962afb001b882c43`、大小
`9979974` bytes、`89` entries；官方 finalizer、`--verify`、`unzip -t` 与 `84` 项内部
checksum 均通过，evidence root 为
`26afeb5ae5191618008580db9e6d892803954e9940953be459b6d20a91c84f52`。完整安全摘要见
[`ADP-V12-S4-T001-developer-check.json`](../../machine/runs/ADP-V12-S4-T001-developer-check.json)。

## 内容合同与真实旅程

- 英文标题与摘要分别做有界确定性判定；纯拉丁标题至少 `4` 个拉丁字母并包含英文词时，
  即使标题很短、摘要为空也进入 `ENGLISH_SOURCE_NO_RELIABLE_ZH`。
- 无可靠中文能力时固定生成八段中文结构，每句显式标记 `KNOWN`、`INFERENCE` 或 `UNKNOWN`
  并携带 evidence locator；不把原文或无 provenance 的中文字段伪装成人话解释。
- 原始英文标题与摘要只放入中文标识的 `<details>`，默认折叠；`/item/:id`、精确 `/today`
  与 `/review` 队列都使用同一失败关闭规则，review 查询携带摘要语言证据。
- system Chrome 独立执行 `5/5` 场景，其中 `3` 个覆盖短标题；每页完成折叠→展开→再关闭，
  共 `15` 张截图、`0` console error、`0` page error，route mock 写入计数为 `0`。

## 首轮发现与修复

首轮 fresh verifier 对旧 Subject `5691ee4b484dc1bd13c12c7b47e27143c0bdedf3` 裁定
`FAIL / ACTION ACT`：

1. `ADP-S4-F001`（L1/P1 产品缺陷）：`Generative Agents` + 空摘要会在 `/item`、精确
   `/today` 绕过回退，review 队列也因缺摘要语言证据而泄漏短英文题名；
2. `ADP-S4-F002`（L1/P1 测试缺陷）：官方 verifier 没有覆盖这些边界，且把若干破坏负控
   合并，可能误报 PASS；
3. `ADP-S4-F003`（L2 需求状态缺口）：taskpack README 与 canonical HANDOFF 仍误称 RC04
   不存在。

修复后，短标题、空摘要、混合 review 队列和精确 `/today` 均进入完整 Worker 路由；官方
verifier 扩展为 `5` 条实际路由和 `9` 个分离、可承重破坏负控，聚焦治理测试固定这些边界；
README/HANDOFF 同步唯一 RC04 与首轮失败状态。fresh r2 独立关闭 `ADP-S4-F001..003`，
没有新增 finding。

## verifier 自身尝试记录

独立复核如实保留四类 verifier-owned 尝试：NC-09 首版检测规则过宽、focused 命令首版只选
`7` 项、materialize clone 首次工作目录调用错误、本机 locale 使首次 hash 命令失败。它们均在
同一独立线程中纠正并复跑通过，原始尝试与最终证据一并封存；这些不是产品失败，也没有使用
waiver。

## 回归证据

| 检查 | 结果 |
|---|---|
| 官方完整 Worker 路由 / 破坏负控 | `5/5 PASS` / `9/9 PASS` |
| 独立完整 Worker 路由 / 破坏负控 | `5/5 PASS` / `9/9 PASS` |
| system Chrome 用户旅程 | `5/5 PASS`，短标题 `3` 场景 |
| S4.1 聚焦治理测试 | `24/24 PASS` |
| MetaDatabase ADP 治理回归 | `72/72 PASS` |
| 安全边界回归 | `14/14 PASS` |
| lesson dedup / de-math / item fallback | `PASS` |
| 双平面、taskpack integrity/compatibility/drift | `PASS` |
| V7.2 根任务包兼容门 | `PASS` |
| ADP full suite 原始结果 | `962` 项；`2 failures + 11 errors + 49 skips`，原始状态 `FAIL` |
| sealed failure/error 测试名集合差分 | `PASS`；`candidate_only=[]`、`baseline_only=[]` |

完整测试没有包装成全绿。S3 sealed ZIP 与内部 full-suite 日志先分别校验 SHA-256，再重新解析
全部 `13` 个 failure/error key；S4.1 与之精确同集，环境 skip 差异不改变裁决。

## 收尾自引用边界与下一步

独立 Subject 在 verdict 前已冻结。本 receipt、phase record、S4.2 机器事实及其确定性生成的
七份人类文档、HANDOFF/taskpack README/CHANGELOG 的收尾文字、任务包树摘要、根 CHANGELOG，
以及提交前由项目脚本执行的 `20` 个用户中心时间戳更新被明确排除，避免把“验收已通过”本身
放进待验 Subject 形成自引用。任何产品、测试、候选补丁、registry、Owner 内容或 live 边界
字节变化都不在排除范围内，必须重新验收。

S4.1 不授权 live 接线、发布或部署。下一任务是 `ADP-V12-S4-T002`（六主题移动端统一四标签
导航），对应 `ACC-V12-S4-003`；当前为 `NOT_RUN`，Run Contract 尚未创建。必须另行锁定唯一
合同后才能开始，不得从本记录预签 S4.2/S4.3、整 S4、版本、运维或部署。

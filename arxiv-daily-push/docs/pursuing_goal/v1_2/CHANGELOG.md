# ADP v1.2 Taskpack Changelog

## 1.2.0 — Owner handoff and non-blocking observation decision — 2026-07-27

- Owner 取消 14 日连续健康观察作为开发、推进或部署验收的阻断；部署后的即时健康验收、
  canary、回滚、SLO、P0/P1/UNKNOWN 和独立 verifier 门仍保持。
- 当前开发在已验收的 S4.2 后停止并交接；S4.3 及后续任务均未启动、未创建 Run Contract，
  也没有部署。下一位开发 agent 必须等待新的明确 Owner 指令。

## 1.2.0 — S4.2 closeout — 2026-07-24

- fresh-context verifier 对冻结 commit `e5460ef2` / tree `6b3cfce2` / materialized artifact
  `39f8a8d…b356b` 裁定 `ACC-V12-S4-003 = PASS / ACTION NONE`，findings、
  P0/P1/UNKNOWN/BLOCKED/waiver 均为零。
- 六主题移动/桌面、`779/780px` 边界、四条 active route、十二张截图与十项负控全部通过；
  S4.2 focused `6/6`、S4.1 回归 `24/24`、治理 `78/78`、安全 `14/14` 通过。
- full suite 原始 `962 tests / 2 failures / 11 errors / 29 skips` 与 S3 sealed baseline 的
  failure/error key 精确同集；只裁定 changed-scope differential PASS，不声称全绿。
- review ZIP SHA-256 `cf884d8a…95e4cb`、evidence root `ac80b4f…ddbb45`；原位与解包
  finalizer verify、`58` 项内部 checksum 及安全扫描均通过。
- S4.2 仅完成 `developer_check`；canonical Worker/live、D1/R2、cron、来源/板块与部署均未改。
  下一任务 `ADP-V12-S4-T003` 保持 `NOT_RUN`，Run Contract 尚未创建，不上传或部署。

## 1.2.0 — S4.2 构建者候选 — 2026-07-24

- RC05 patch chain 已物化为 build `a98b4c957f30` / artifact
  `39f8a8d82aec8f97e83d595f95ba52ae062191b801632661922077c9632b356b` /
  Git blob `461fb1a225c0a8826cf0647181a9969a53618c3a`。
- 构建者的真实系统 Chrome 验证覆盖六主题移动端、六主题桌面端、`779/780px` 临界宽度、
  四条 active route、十二张截图与十项分离破坏负控，浏览器错误为零。
- S4.2 聚焦 `6/6`、S4.1 回归 `24/24`、治理 `78/78`、安全 `14/14`、双平面和 V7.2
  兼容入口通过；受控 Python 3.12 full suite 为 `962 tests / 2 failures / 11 errors /
  29 skips`，与 S3 sealed ZIP failure/error 键精确同集，`candidate_only=[]`、
  `baseline_only=[]`。
- fresh-context 独立验收尚未运行，`ACC-V12-S4-003` 保持 `NOT_ACCEPTED`；canonical Worker、
  live、D1/R2、来源/板块、cron、上传与部署均未改，S4.3 未开始。

## 1.2.0 — S4.2 Run Contract — 2026-07-24

- 为 `ADP-V12-S4-T002` 增加唯一 `RUN_CONTRACT_05_MOBILE_FOUR_TAB_NAV.md`，锁定
  `<780px` 六主题统一“今天／队列／雷达／系统”、`375×812` 无横向溢出、`779/780px`
  边界、点击目标与桌面 sidebar/topbar/dock 不回归。
- candidate 必须先物化已验收 S4.1 patch，再叠加独立 S4.2 patch；canonical Worker、
  production bundle、live `0.41.0`、D1/R2、cron 和部署保持不动。S4.3 视觉门不得混入本轮。

## 1.2.0 — S4.1 closeout — 2026-07-23

- 短英文标题、review 队列和官方 verifier 边界修复后，fresh-context r2 对冻结 commit
  `c50d7f7b` / tree `d40fb7b` / materialized artifact `9c7ff113…0797b` 裁定
  `ACC-V12-S4-001..002 = 2/2 PASS`，首轮 `ADP-S4-F001..003` 全部关闭，开放
  P0/P1/L2/UNKNOWN/BLOCKED/waiver 均为零。
- 独立完整 Worker 路由 `5/5`、system Chrome `5/5`、分离破坏负控 `9/9`、24 个聚焦测试、
  72 个 ADP 治理测试和 14 个安全测试通过；full suite 原始仍是历史 `2 failures + 11 errors`，
  与 S3 封存基线精确同集，`candidate_only=[]`、`baseline_only=[]`。
- S4.1 仅完成 `developer_check`；canonical Worker/live、D1/R2、cron、来源/板块和部署均未改。
  下一任务 `ADP-V12-S4-T002` 保持 `NOT_RUN`，Run Contract 尚未创建，不上传或部署。

## 1.2.0 — S4.1 first-review repair candidate — 2026-07-23

- fresh-context verifier 对冻结 Subject `5691ee4b` 裁定 `FAIL / ACT`：长英文条目路径满足
  `ACC-V12-S4-001`，但短英文标题与 review 队列绕过 fail-closed，`ACC-V12-S4-002` 失败。
- `ADP-S4-F001..003` 分别锁定产品缺陷、官方 verifier false-PASS 和 README/HANDOFF 陈旧状态；
  修复必须覆盖 `Generative Agents` + 空摘要、短标题 + 英文摘要队列、三路由、逐项状态/details
  破坏负控，并由新不可变 Subject 的全新 verifier 复验。
- 当前仍为 `NOT_ACCEPTED`；canonical Worker、production bundle、D1/R2、cron、来源和 live
  `0.41.0` 均未改变，不上传或部署。

## 1.2.0 — S4.1 Run Contract — 2026-07-23

- 为 `ADP-V12-S4-T001` 增加唯一 `RUN_CONTRACT_04_HUMAN_LANGUAGE_FAIL_CLOSED.md`，锁定
  无可靠中文解释时的已知/推断/未知结构、默认折叠英文原文、旧存储讲义 fail-closed 和
  unsupported-claim 破坏负控。
- 本合同锁定为基于封存 live Worker 的可确定性 candidate patch；canonical Worker 与 production
  bundle 保持不动。不引入模型/API/付费服务，不修改 D1/R2 schema 或数据，不处理 S4.2/S4.3，
  不上传或部署；实现与独立验收尚未预签。

## 1.2.0 — S3 closeout — 2026-07-23

- Science Advances PubMed candidate 经首轮独立复审发现并修复 XML 1.0 非法 literal 与未声明/
  大小写伪装实体边界；fresh-context r2 对冻结 Git Subject 裁定
  `ACC-V12-S3-001..003 = 3/3 PASS`，无 P0/P1/UNKNOWN/BLOCKED/waiver。
- 26/26 有效独立对抗 Oracle、63-scenario 可执行验证及 962-test 精确密封基线差分通过；
  原始 full suite 仍如实为历史 `2 failures + 11 errors + 29 skips`，未包装成绿色。
- 候选保持 `candidate_not_live`；未改 Worker、现有 Science.org RSS、cron、D1/R2 或部署。
  下一任务 `ADP-V12-S4-T001` 保持 `NOT_RUN`，Run Contract 尚未创建。

## 1.2.0 — S3 Run Contract — 2026-07-22

- 为 `ADP-V12-S3-T001` 增加唯一 `RUN_CONTRACT_03_SCIENCE_ADVANCES_PUBMED.md`，锁定 NLM
  期刊身份、最多 20 PMID/2 请求、`<=1 req/s`、无 API key、失败关闭和零 live 接线边界。
- `TASK_GRAPH.yaml` 明确绑定该合同；实现、整阶段独立复审和 GitHub 上传尚未预签。

## 1.2.0 — S2 closeout — 2026-07-22

- stats-gov 四类只读诊断与事实链完成；首轮独立复审发现的 Owner receipt P1 修复后，fresh
  verifier 对新 Subject 裁定 `ACC-V12-S2-001..003 = 3/3 PASS`，无 P0/P1/UNKNOWN/BLOCKED。
- 决定保持 `degraded_preserved` / `NO_ADAPTER_FIX`；未改 Worker、来源启停、cron 或部署。
- S3 仍为 `NOT_RUN`；下一轮必须先为 `ADP-V12-S3-T001` 新建独立 Run Contract。

## 1.2.0 — S2 Run Contract — 2026-07-22

- 为 `ADP-V12-S2-T001` 增加唯一 `RUN_CONTRACT_02_STATS_GOV_DIAGNOSIS.md`，锁定四类互斥诊断、
  证据支持才修复、否则保持 degraded 的决策门，以及零付费、零绕过、零部署边界。
- `TASK_GRAPH.yaml` 明确绑定该合同；S3 仍必须等待 S2 整阶段独立复审通过。

## 1.2.0 — 2026-07-20

- 以 MetaDatabase 为唯一真源建立 verifier 可识别的七角色任务包。
- 将 v0.1 的 90 个任务、20 条要求、前端 v1.1、HANDOFF 与两轮验收归并到一张追溯表。
- 将迁移后来源救援顺序锁为 Google News → stats-gov → Science Advances/PubMed。
- 将 7fd 验收遗留的中文人话版、移动四标签、视觉门和 Python 元数据纳入 v1.2。
- 定义 Cloudflare Free 优先的 SLO、canary、自动回滚和 14 日稳定期。
- v1.2 以源码目录交付；历史 ZIP 另行按原字节归档，不重复前端 v1.1 ZIP。
- 独立 pre-merge 验收发现并阻断 4 个 Acceptance 反向追溯缺口；补齐映射，并把 10 Task/33 Acceptance 精确反向覆盖写成可破坏验证的 validator 硬门。

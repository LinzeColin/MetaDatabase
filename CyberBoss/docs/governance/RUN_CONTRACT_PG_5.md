# PG-5 Run Contract — 原生最终退出门与外部验收候选

## 目标

关闭唯一剩余的原生 PG-5 节点：基于已密封的 CB-540 Subject 输出最终开发候选、外部正式验收
输入和 publication receipt。产品版本固定为 `v0.0.0.5`；真实 channel pending 只能产出
`MVP_DEGRADED`，不能伪称 `MVP_LIVE`。

## Router 与边界

PG-5 Router 为 `DETERMINISTIC_TEST_ONLY`，selected skill 为 `null`，最大 Skill body load 为
0。本 Run 不加载任何 Skill，不调用 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究。
不增加等待、sleep、观察期、模型调用、macOS launchd、仓库、数据库、Private-Database clone 或
平行事实源。

## 最小范围与验收

- 只聚合 CB-510/520/530/540 的精确 source、artifact、deployment、Access、sync、restore、
  self-heal、canary/rollback receipt；不修改已发布 immutable release。
- 所有 PG-5 critical acceptance 为 `PASS`，零 P0/P1 未接受项，开发候选通过冻结聚合器为
  `MVP_DEGRADED`。
- 生成外部正式验收候选并运行其冻结 aggregator；缺少两个独立 contexts 时结果必须为 `BLOCKED`，
  且不得阻塞 PG-5 或反向降级已证实的产品状态。
- 最后只做一次 closure commit 和该现有 branch 的 publication；不创建 tag、PR、仓库或第二事实源。

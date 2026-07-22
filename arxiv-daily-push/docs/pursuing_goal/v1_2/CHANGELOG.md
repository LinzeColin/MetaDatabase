# ADP v1.2 Taskpack Changelog

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

# ADP v1.2 Taskpack Changelog

## 1.2.0 — 2026-07-20

- 以 MetaDatabase 为唯一真源建立 verifier 可识别的七角色任务包。
- 将 v0.1 的 90 个任务、20 条要求、前端 v1.1、HANDOFF 与两轮验收归并到一张追溯表。
- 将迁移后来源救援顺序锁为 Google News → stats-gov → Science Advances/PubMed。
- 将 7fd 验收遗留的中文人话版、移动四标签、视觉门和 Python 元数据纳入 v1.2。
- 定义 Cloudflare Free 优先的 SLO、canary、自动回滚和 14 日稳定期。
- v1.2 以源码目录交付；历史 ZIP 另行按原字节归档，不重复前端 v1.1 ZIP。
- 独立 pre-merge 验收发现并阻断 4 个 Acceptance 反向追溯缺口；补齐映射，并把 10 Task/33 Acceptance 精确反向覆盖写成可破坏验证的 validator 硬门。

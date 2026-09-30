# 归档索引

2026-09-30 EEI 根目录瘦身：原根目录的治理、计划、报告类文档用 `git mv` 搬到这里（历史完整保留，一个没删）。
根目录现在只留 `README.md`、`HANDOFF.md`、`AGENTS.md` 与构建必需文件。
部分校验脚本仍会读取这里的文件（已把路径改成 `文档/归档/…`），所以**不要随意改名或删除**。

「并入」一栏写的是新文件里**确实写了**的内容；写「无」的表示新文件没有收，原文只在这里。

| 文件 | 原来讲什么 | 是否过时 | 关键信息去向 |
|---|---|---|---|
| `README_旧版.md` | 2026-06 任务包总览 + 一大段逐轮进度叙述 + Codex 启动、clean-start 命令 | 过时（进度叙述停在 2026-07 之前） | 十三条 clean-start 命令原样进新 `README.md`；入口表换成新 README 的目录表 |
| `HANDOFF_旧版.md` | 2026-07-15 接管交接：目标、阅读顺序、S6 状态、本机环境坑、D1-D9 Owner 决策 | 过时（S6 状态、本机路径已变） | 阅读入口进新 `HANDOFF.md`「接手第一步」；并发套件坑进「坑」；**D1-D9 决策全文无**，决策是否仍有效未核实 |
| `AGENTS_旧版.md` | v4.2 时代的 agent 规则：产品真相、读取顺序、治理、UI 不变量、数据/模型不变量 | 部分过时（读取顺序指向已搬走的文件；UI 不变量针对旧 Next.js 前端） | 数据/模型不变量进新 `AGENTS.md`「数据与事实」；UI 不变量无 |
| `HANDOFF_EEI.md` | 2026-07 的交接：Cloudflare Workers + D1 无服务器形态、本机 docker 监测、真数据管道、部署铁律 | **过时**（主站已在 VPS-3，本机监测不再是现状） | 采集命令、D1 复合 SELECT 限制进新 `HANDOFF.md`；Owner 决策（不登录、不买数据）进 `AGENTS.md`；视觉基线做法进 `AGENTS.md`；「agent 自合并授权」无（与当前流程不一致，是否有效未核实）；本机 `_protected` 监测无 |
| `WHERE_IS_THE_DATA.md` | 「数据路牌」：长期权威事实在 Private-Database，OVH postgres 与 D1 是可重建副本，同步命令与不同步清单 | 大体有效（其中的服务器 IP 写法是旧的） | 分层与同步命令进新 `HANDOFF.md` 状态表；不写入 `AGENTS.md` 的不同步清单无 |
| `CHANGELOG.md` | 版本变更记录（Unreleased 到 v0.1.0 发布，2026-07） | 停在 2026-07，之后的变更在 git 历史里 | 版本号与发布日期进新 `HANDOFF.md`；条目本身无 |
| `CODEX_MASTER_TASK.md` | v4.2 任务包的总任务书（G0 只读计划、事实源、MVP 成功标准） | 过时 | 无 |
| `CONTINUITY_PLAN.md` | 阶段 0-9 链与每个 Issue 的固定闭环、防漂移规则 | 过时（被 `docs/pursuing_goal/` 与 `docs/governance/` 取代） | 同步规则的精神进 `AGENTS.md`「改仓库时」；阶段链无。校验脚本要求此文件存在 |
| `CONTRIBUTING.md` | 开工前步骤、必须同步的文件清单、合并门槛命令 | 大体有效，文件名已搬家 | 同步要求与 `make verify` 进 `AGENTS.md`「改仓库时」；清单细节看原文 |
| `GITHUB_REPOSITORY_BACKUP_INDEX.md` | GitHub 文档/备份结构、强制同步规则、「当前真实状态」 | 「当前真实状态」一节过时，其余是旧说明 | 同步规则进 `AGENTS.md`；其余无。`data/github_document_registry.csv` 登记了它 |
| `DEVELOPMENT_STATUS.md` | 已解决/未解决、任务与四轴状态的长叙述（2026-07 前） | 过时 | 无（现状以 `HANDOFF.md` 与 `docs/governance/` 为准）。校验脚本要求此文件存在 |
| `DOMAIN_DATA_CATALOG.md` | 研究对象、关系、供应链、行业、业务、资本、公司目录的范围与字段规则 | 规则仍有效，数量以 `data/` 下 CSV 为准 | 新 `README.md` 目录表指向 `data/`；字段规则无 |
| `FUNCTION_CATALOG.md` | 兼容入口（指向 `docs/governance/`，无实质内容） | 空壳 | 新 `README.md` 目录表指向 `docs/` |
| `MODEL_MANAGEMENT.md` | 同上，兼容入口 | 空壳 | 同上 |
| `GOVERNANCE_INDEX.md` | 同上，兼容入口 | 空壳 | 同上 |
| `DELIVERY_INDEX.md` | 同上，兼容入口 | 空壳 | 同上 |
| `RISK_AND_ACCEPTANCE.md` | 同上，兼容入口 | 空壳 | 同上 |
| `VALIDATION_REPORT.md` | 同上，兼容入口 | 空壳 | 同上 |
| `CURRENT_PHASE.md` | 同上，兼容入口 | 空壳 | 同上 |
| `PLANS.md` | G0-G9 关卡表、工作量预算、完成账本（表里全是 NOT STARTED，与事实不符） | 过时 | 无 |
| `PURSUING_GOAL.md` | 2026-06-20 的追求目标：MVP 边界、Golden Vertical（NVIDIA→TSMC→ASML）、运行规则 | 过时，但 `validate_v5_production_readiness_sync.py` 会检查其中两句话 | 无。校验脚本要求此文件存在 |
| `REPORT.md` | v4.2.0 治理报告（规模数字、产品边界） | 过时 | 无 |
| `REVIEW_AND_ITERATION_INDEX.md` | v5 审查、品牌、测试、迭代证据文件索引 | 索引仍有效 | 新 `README.md` 目录表列出 `reviews/`、`brand/`、`specs/` |
| `RUN_CODEX.md` | 用 `codex exec` 分阶段跑任务包的流程、网络策略、恢复 | 过时（Codex 时代流程） | 无 |
| `SOURCES.md` | UI/无障碍基准与公司数据来源的指针 | 有效但很薄 | 无（指向的 `docs/05…`、`data/` 仍在原处） |
| `TEST_STRATEGY.md` | 测试金字塔、性能门槛、测试证据规则 | 大体有效 | 验证命令进新 `README.md`「怎么验证」；性能门槛数字无 |
| `US_Corporate_Power_Map_System_Model_Parameter_Architecture_v4.2.md` | 六份治理文档的一页快速入口 | 过时 | 无。校验脚本要求此文件存在 |
| `US_Corporate_Power_Map_UIUX_Redesign_v4.2.md` | v4.2 UI/UX 重构要点（首页可视化、导航、动效、无障碍） | 过时（旧前端方案） | 无。校验脚本要求此文件存在 |
| `US_Corporate_Power_Map_Governance_Blueprint_v4.2.pdf` | 16 页治理蓝图 PDF（4MB），由 `scripts/generate_governance_pdf.py` 生成 | 过时 | 无。校验脚本按 16 页检查它 |

## 没搬的文件

`CHECKSUMS.sha256`、`manifest.txt`、`DIRECTORY_TREE.txt` 是校验清单，不是文档，留在根目录，由 `make generate-release-artifacts` 重新生成。
`VERSION`、`Makefile`、`package.json`、`pnpm-*`、`pyproject.toml`、`uv.lock`、`docker-compose*.yml`、`playwright*.ts` 是构建必需文件。
`文档/00`–`06` 由机器平面渲染，不在此列。

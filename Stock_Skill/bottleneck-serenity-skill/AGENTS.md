# bottleneck-serenity-skill Agent Contract

## 权威状态

- 规范项目路径：`Stock_Skill/bottleneck-serenity-skill/`。
- Stable ID 与 canonical Skill basename：`bottleneck-serenity-skill`。
- 项目与 Task Pack 机器版本必须同时逐字等于 `0.0.0.1`；人类展示与 release label 为 `v0.0.0.1`。
- 集合级索引是 `Stock_Skill/REGISTRY.json`；active claim 为
  `bottleneck-serenity-skill=0.0.0.1`。真实 release SHA、三个 hash 消费面、两个 manifest、六个发现面与
  `python3 -B Stock_Skill/scripts/validate_registry.py` 必须始终一致；source-only current 不等于本机安装。
- 身份、版本、路径、manifest、release SHA、UI metadata 或 registry 任一冲突时，状态为 `UNKNOWN`，不得猜测。

## 永久边界

- 本项目只保存专有源码、可恢复备份和验证材料，不是安装目录；禁止写入用户级 Codex/Agents Skill runtime。
- MetaDatabase 公开可见，但根 `LICENSE` 仍是 proprietary / All Rights Reserved；公开可见不产生开源许可。
- 只允许公开、已授权或用户明确提供的数据。禁止提交账户、真实组合、客户、交易、付费数据、MNPI、凭据、
  会话、本机路径或未授权第三方材料。
- 产出仅用于研究与教育决策支持。禁止券商认证、读取 broker token、下单/撤单、自动交易、保证收益或把研究
  标签表述成个性化 buy/sell/hold 指令。
- 当前价格、估值、财报、法规和事件是易变事实，必须在同次研究中按明确 `as_of` 与 source cutoff 核验；
  示例和 eval 永远不是实时投资证据。
- 不创建 frontend、backend、database、daemon、scheduler、自动抓取器或隐式后台任务。

## 修改纪律

1. 先读仓库根 `AGENTS.md`、`Stock_Skill/AGENTS.md`、本文件、`Stock_Skill/REGISTRY.json` 和
   `task-pack/00_RUN_CONTRACT.md`，再从仓根运行 registry validator。
2. 只在隔离 worktree 修改；主树必须保持 `main` 且干净。一次 run 最多完成 Task Graph 中一个 Task。
3. Phase 完成不上传；只有整个 Stage Review PASS、全部 finding 闭环后，才能统一 commit/push。
4. `SOURCE_INVENTORY.md` 的源路径、源 SHA、53-entry 集合和原始决定不可改写；只能追加后续 destination 与
   独立审计证据。
5. 身份迁移和工程化不得改变四道非补偿门、三个时钟、每股价值桥、证据标准、几何/门控评分、因果聚类、
   kill switch、append-only 历史或无交易边界。任何核心逻辑变化必须先做影响/版本分析并取得用户决定。
6. 第三方来源按 `LICENSE_AND_ATTRIBUTION.md` 处理：无明确许可的仓库只允许事实性引用，不得复制代码、数据、
   图片或长段文本；MIT-covered 片段必须保留相应 notice。
7. release 只能由已封印 canonical Task Pack 确定性构建；禁止提交输入 ZIP、占位 SHA、伪 archive 或手工伪造
   manifest。恢复步骤以 `RESTORE_AND_VERIFY.md` 为准。
8. 本项目 Python runtime 脚本只使用标准库；新依赖、外部写入或付费服务必须另开 Task 并给出许可/安全证据。

## 接口与适配器

- 支持 `scan`、`deep_dive`、`compare`、`monitor`、`postmortem`；先冻结研究合同和 source cutoff。
- 输入/输出字段、默认值与 completion event 以 `task-pack/02_ARCHITECTURE_DATA_API.md` 和 canonical
  `references/integration_contract.md` 为准。
- 上游适配器只能补充带来源数据，不能越过硬门；估值适配器不能重写结构证据；组合适配器可以否决 sizing，
  不能重写 thesis；所有版本保留前一版本链接和不可改写快照。

## 完成门

- 官方 skill-creator validator、项目 validator、全部 unittest、JSON/schema、trigger/negative、安全与历史截断
  E2E 均通过。
- Task/backup manifests、release、`SHA256SUMS` 与 registry 可从 proposed tree 和最终干净 checkout 重建并同 SHA。
- 每个 Stage 的独立 Review ledger 零未关闭 finding；最终 PR/CI/merge 与 worktree/branch/PR/cache 清理均有实证。

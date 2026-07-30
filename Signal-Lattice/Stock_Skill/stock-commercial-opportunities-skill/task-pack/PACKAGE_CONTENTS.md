# 包内容索引

## Task-pack 层

| 文件 | 用途 |
|---|---|
| `START_HERE_FOR_CODEX.md` | 最小读取顺序与当前 Gate |
| `AGENTS.md` | 金融、证据、权限与工程合同 |
| `CODEX_MASTER_TASK.md` | 单一目标、状态合同、Run Contract |
| `USER_REQUIREMENTS.md` | 用户痛点、四层模型、非目标 |
| `DECISIONS_AND_DEFAULTS.md` | 已确认 ID/目录/不安装/默认参数 |
| `RESEARCH_REPORT.md` | 股票研究专用公开调研与设计映射 |
| `REFERENCE_PROJECT_MATRIX.md` | 官方/开源/商业/交易型系统比较 |
| `TARGET_ARCHITECTURE.md` | 对象、数据流、任务颗粒度与安全平面 |
| `IMPLEMENTATION_PLAN.md` | 原子任务、release/remote/cleanup contracts |
| `ACCEPTANCE_CHECKLIST.md` | 定位、证据、金融安全、恢复、语义验收 |
| `VALIDATION_REPORT.md` | 同次真实命令、结果和 NOT_RUN 项 |
| `BLIND_SPOTS_AND_SURPRISES.md` | 红队、surprise、残余风险 |
| `LICENSE_AND_ATTRIBUTION.md` | 专有边界、第三方与数据许可 |
| `VERSION`, `CHANGELOG.md` | v3 与 v1/v2 谱系 |
| `MANIFEST.sha256` | task-pack 文件完整性 |
| `CODEX_START_PROMPT.txt` | 下一任务最小启动指令 |

## Skill 层

`skill_draft/stock-commercial-opportunities/`：

- `SKILL.md`, `agents/openai.yaml`：触发、产品界面、research-only contract。
- `references/`：workflow、商业机制、证据、评分/E0–E5、尽调、输出、安全、下游路由、评估。
- `scripts/`：股票候选 scorer、deliverable validator、Skill package validator。
- `assets/`：intake、Stock Opportunity/Diligence cards、evidence ledger、research note、synthetic input/output fixtures。
- `evals/`：22 trigger cases、8 quality cases、benchmark schema。
- `tests/`：29 个 deterministic unit/CLI regressions（可随修复只增不降）。

## 项目根额外保存

- `archives/`：不可变 v1/v2 ZIP 与 v2 研究摘要。
- `releases/`：v3 可移植 ZIP 和 SHA256SUMS。
- `SOURCE_INVENTORY.md`：版本/哈希/角色。
- `RESTORE_AND_VERIFY.md`：远端 sparse restore 和 clean-room commands。
- `BACKUP_MANIFEST.sha256`：项目完整性。

## 不包含

已安装 Skill、真实证券推荐、市场/consensus/paid-data snapshot、portfolio/account/transaction、客户或内部研究、MNPI、credential/session、模型 A/B 虚构结果、外部仓库代码、ticker memory/cache、自动交易/发布配置。

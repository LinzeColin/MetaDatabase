# Source inventory and migration ledger

本文件是 `ACC-S2-005` 的 53-entry 权威证据，由 `BSS-S2-P1-T002` 首次建立。它记录输入归档的
原始身份、逐项 SHA-256、唯一处置决定和目标归宿；后续身份改名或文档工程化不得改写这些源事实。

- Canonical project：`Stock_Skill/bottleneck-serenity-skill/`
- Canonical Skill：`Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill/`
- Distribution：`SOURCE_ONLY`；本机安装：`PROHIBITED`
- Target machine version：`0.0.0.1`；display/release：`v0.0.0.1`

## Input artifact baseline

输入文件不提交；公开仓只保存逻辑名、哈希、大小和迁移决定，避免记录本机绝对路径。

| Logical artifact | SHA-256 | Bytes | Role |
|---|---|---:|---|
| `input-archive.zip` | `541fce14f8eaa4b73a8c170fc6f6bc0f8cd5aa509942fe2192bd8cddafd90815` | 73,957 | 53-entry 迁移真源；不是 current release |
| `outer-skill.md` | `69c78b85bd08695b6e1403d6b768be468277f845450c9f9736dba945a58058ba` | 14,887 | 与归档内 `SKILL.md` byte-identical |
| `handoff.zh-CN.md` | `182270834e8618f2b5f5750265938a39bd91a20240885fcf6289cc9694239f8a` | 1,969 | 迁移要求与验收输入 |
| `quickstart.zh-CN.md` | `53a9c8cd9b44857df3f66d11f815b45c88a6db6fb6c0424092cab12e649c3462` | 3,030 | 使用说明；安装步骤不执行 |
| `research-report.zh-CN.md` | `0359125da22050fd0d7bd1f9b62abf646ef1d43de29121a851b185b3e5ee57f8` | 11,810 | 方法审计与设计依据；不属于 53-entry 集合 |

## Archive invariants

- Archive SHA-256：`541fce14f8eaa4b73a8c170fc6f6bc0f8cd5aa509942fe2192bd8cddafd90815`。
- `unzip -t` PASS；精确 53 entries = 45 regular files + 8 directories；regular-file payload 共 152,598 bytes。
- Entry name 全部为 UTF-8/NFC canonical POSIX relative path；无 absolute、`..`、反斜杠、重复、symlink 或非普通类型。
- 源 mode：目录 `0755`；5 个 Python script `0755`；其余普通文件 `0644`。
- 源包无 `LICENSE`/`COPYING`。`PROVENANCE.md` 声明为原创综合、未复制列出的 Serenity 项目代码；
  最终 proprietary/attribution 结论仍由 `BSS-S2-P2-T002` 写入 `LICENSE_AND_ATTRIBUTION.md`。

## Decision vocabulary

- `IMPORT`：本 Task 将 entry 原样落入 canonical resource subtree；文件 bytes 与 mode 必须和 ZIP 相等。
- `MIGRATE`：语义或结构迁往 stable-ID Skill、外层项目或 Task Pack；禁止把旧身份/安装文档直接塞入 canonical root。
- `EXCLUDE`：明确不进入 current source/release，并记录不可采用原因。

每个归档 entry 必须且只能出现一次；目录 entry 也单独计数。

## 53-entry disposition ledger

| # | Source entry | Type / mode | Source SHA-256 | Decision | Destination / rationale |
|---:|---|---|---|---|---|
| 1 | `constraint-alpha/` | directory `0755` | — | `MIGRATE` | `task-pack/skill_draft/bottleneck-serenity-skill/` — canonical root 已由 `BSS-S2-P1-T001` 建立；旧 root 名不保留。 |
| 2 | `constraint-alpha/README.md` | file `0644` | `778e508fcf2437a0e7437d452b05616ce70de120511f43e7e15f55276aa8d711` | `MIGRATE` | `README.md`（`BSS-S2-P2-T002`）— 只迁移产品说明；安装步骤因 source-only 策略不复制。 |
| 3 | `constraint-alpha/examples/` | directory `0755` | — | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/examples/` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 4 | `constraint-alpha/examples/illustrative_transformer_equipment.json` | file `0644` | `6e9a44c688ac6b5da11e3ea929fc639f06ba0d16e915ad1af02f923417fce3a1` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/examples/illustrative_transformer_equipment.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 5 | `constraint-alpha/examples/illustrative_transformer_equipment_score.md` | file `0644` | `4e3afb446ff22004d207c893900c12c18383b7fcb53d1f5b647ed3001d523043` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/examples/illustrative_transformer_equipment_score.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 6 | `constraint-alpha/examples/illustrative_portfolio_analysis.json` | file `0644` | `20753ccfac1632f936ec41169299c0ba2a91632b941b6cfe00a76dee98fdb7e4` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/examples/illustrative_portfolio_analysis.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 7 | `constraint-alpha/examples/illustrative_portfolio.json` | file `0644` | `2b4be90503bd0a27b7881857153e610f1375a1f26e647a0119030476bc6ba1cf` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/examples/illustrative_portfolio.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 8 | `constraint-alpha/MANIFEST.md` | file `0644` | `e5ed5db2d6513ddaf4230f2a3187fc812df8bd85fdd326a092c5b8d76d11990f` | `MIGRATE` | `SOURCE_INVENTORY.md`（本文件）— 将粗粒度清单升级为 53-entry 可审计 ledger。 |
| 9 | `constraint-alpha/scripts/` | directory `0755` | — | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/scripts/` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 10 | `constraint-alpha/scripts/validate_evidence.py` | file `0755` | `16d3a80dd7893c867bf22b0baa78ac17c1414bd3495d2a5888154597dc03ae6f` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/scripts/validate_evidence.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 11 | `constraint-alpha/scripts/new_research_case.py` | file `0755` | `12babd35e3d8abcc4f2809f125a8e48a73ee3e776fd0fee5858e2ba91bc20c43` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/scripts/new_research_case.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 12 | `constraint-alpha/scripts/analyze_portfolio_clusters.py` | file `0755` | `0dffec4920d2437c2039a0c5d0a622757aa8865d0dfe8821e6b72f6b1017729f` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/scripts/analyze_portfolio_clusters.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 13 | `constraint-alpha/scripts/validate_skill.py` | file `0755` | `b044aa2b7bc9a81009d97af10766d9b817c87eb077ebf03cb4abbce4dca35f43` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/scripts/validate_skill.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 14 | `constraint-alpha/scripts/score_opportunity.py` | file `0755` | `c1130fad41810b7ca64acb77b5f75f31dbeabb8cd7d473efef5be3e1cb3dee07` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/scripts/score_opportunity.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 15 | `constraint-alpha/schemas/` | directory `0755` | — | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/schemas/` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 16 | `constraint-alpha/schemas/opportunity.schema.json` | file `0644` | `251d04102a088a2ece6fbf2f08dcf19f2f04aa98858e0c7e39be5fcac123b8c7` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/schemas/opportunity.schema.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 17 | `constraint-alpha/schemas/evidence.schema.json` | file `0644` | `d652cb0dcf310b7143bccd072d7433bd05b2501e6df90d414a0dfa0c925d374d` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/schemas/evidence.schema.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 18 | `constraint-alpha/schemas/portfolio.schema.json` | file `0644` | `93809e9acfc274d0d4e9d7bf86d712739d9e1fd7dfd0025fe2805f8eb660ed98` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/schemas/portfolio.schema.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 19 | `constraint-alpha/SKILL.md` | file `0644` | `69c78b85bd08695b6e1403d6b768be468277f845450c9f9736dba945a58058ba` | `MIGRATE` | `task-pack/skill_draft/bottleneck-serenity-skill/SKILL.md`（`BSS-S2-P2-T001`）— 以已初始化 stable-ID 入口重构，不在 Import Task 覆盖。 |
| 20 | `constraint-alpha/references/` | directory `0755` | — | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 21 | `constraint-alpha/references/portfolio_risk.md` | file `0644` | `e06fe9293f557470a7e394850404583e2809ddf1cc31809dd301b053e37b3c21` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/portfolio_risk.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 22 | `constraint-alpha/references/backtest_and_evals.md` | file `0644` | `8f090737636a2272386ab44aacc49e1380b2c8f1ae9599a85e7ac82465fe126b` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/backtest_and_evals.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 23 | `constraint-alpha/references/research_workflow.md` | file `0644` | `bf6ce75626dd5757eac8dd6595f946828b2d89b147433824b37c22ed7645952d` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/research_workflow.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 24 | `constraint-alpha/references/source_catalog.md` | file `0644` | `eb853d306d70455c1dd496b445ff9f0033ff347d661700e0dae563efea2fee7e` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/source_catalog.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 25 | `constraint-alpha/references/source_policy.md` | file `0644` | `03b296596a3821cedd3ca98d8950a8585c651d572d0806c0c7d8c8198bb17c47` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/source_policy.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 26 | `constraint-alpha/references/failure_modes.md` | file `0644` | `faefd4b704d56fe9b0a46925490368e5466a395b77c0ad706c68467523562dd3` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/failure_modes.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 27 | `constraint-alpha/references/serenity_audit.md` | file `0644` | `b5c4018922f5324d1ad1c8daf7798cc7acdae6af1268efbfc71eb7ed93629e11` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/serenity_audit.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 28 | `constraint-alpha/references/output_contract.md` | file `0644` | `7b8b2e046049b64c9683eaf42f7ef2fd10504e93bc6c1695f944733400ae8c71` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/output_contract.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 29 | `constraint-alpha/references/methodology.md` | file `0644` | `f20aa5725b4ca5827f3b30a8a9d01976356429e5f4cd867aeb14db38349f8d23` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/methodology.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 30 | `constraint-alpha/references/integration_contract.md` | file `0644` | `6015127a6746f9cba2d5e40590015e5e127dd6e8c0359a9517a525ef82e7e810` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/integration_contract.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 31 | `constraint-alpha/references/scoring_model.md` | file `0644` | `5d3ae07b9e1ef61405e005a79c17dd38773190acd1b40e7fbf9b494ff59147c9` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/references/scoring_model.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 32 | `constraint-alpha/PROVENANCE.md` | file `0644` | `0fb17bab95dccdc0ce944cbd74a29ee65ba25c7f14dcc9031ffd829d1de689f9` | `MIGRATE` | `LICENSE_AND_ATTRIBUTION.md`（`BSS-S2-P2-T002`）— 保留来源、原创声明与再分发结论。 |
| 33 | `constraint-alpha/VERSION` | file `0644` | `e9dd8507f4bf0c6f42458e41aea833ad0bd3f6127272335eee9bf4d58541ed67` | `EXCLUDE` | 源值 `0.1.0` 与用户冻结的机器版本 `0.0.0.1` 冲突；不作为 current 或伪 archive。 |
| 34 | `constraint-alpha/templates/` | directory `0755` | — | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 35 | `constraint-alpha/templates/investment_memo.md` | file `0644` | `3a0d321bbd65e9382f118ef2e21e3a20b24589b8824602565f2afb333dffce4d` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/investment_memo.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 36 | `constraint-alpha/templates/candidate_card.md` | file `0644` | `3c255931bea5311d28e0a540a8e03a5097dad0ca84c115c4682a91fa37e0dca4` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/candidate_card.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 37 | `constraint-alpha/templates/research_config.json` | file `0644` | `37b11c16a55b1e6edd69b7250953f8c1474b571d09bc00508fa8ecad91339bab` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/research_config.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 38 | `constraint-alpha/templates/theme_map.md` | file `0644` | `f7e2f08d64a33e9982985d4908eac8d9c376c6f1e40d6f889671013d4c56197c` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/theme_map.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 39 | `constraint-alpha/templates/thesis_ledger.csv` | file `0644` | `6d118695201af9025a2af5c37921ed5fff3d03ff3e078c3d2622f3e44935e29d` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/thesis_ledger.csv` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 40 | `constraint-alpha/templates/monitor_plan.csv` | file `0644` | `07d0966c63b9033aa548d011522b45ebd2b22d565a8a79fd4d3250018e77480d` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/monitor_plan.csv` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 41 | `constraint-alpha/templates/evidence_ledger.csv` | file `0644` | `e7b4c138ceab9fca6d5d2782c66466d03388249b35874e5e40412cd8569b208b` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/templates/evidence_ledger.csv` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 42 | `constraint-alpha/evals/` | directory `0755` | — | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/evals/` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 43 | `constraint-alpha/evals/prompts.csv` | file `0644` | `f6367553f24b3fd7142bb4c93381d1d83843c04017e8a7d97b62a874b269a374` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/evals/prompts.csv` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 44 | `constraint-alpha/evals/golden_cases.json` | file `0644` | `7de22b669a29cd3a2d2ed74334a95fcef2afcac950e8a4868a0e8670076f84a3` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/evals/golden_cases.json` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 45 | `constraint-alpha/evals/rubric.md` | file `0644` | `832d96bf326b4176d03137ede15ed51642c2ed9cfbe81ba0be154c9eded84dc4` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/evals/rubric.md` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 46 | `constraint-alpha/tests/` | directory `0755` | — | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/tests/` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 47 | `constraint-alpha/tests/test_score_opportunity.py` | file `0644` | `028b0c9220ff3e85ab72bbc5fe0796bb61a88cfb4321beb3c4997b9f1940e99a` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/tests/test_score_opportunity.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 48 | `constraint-alpha/tests/test_portfolio_clusters.py` | file `0644` | `2d88d84a77d5a709ef8722d99d1089526c1b478a97695b778d980fba005ddc91` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/tests/test_portfolio_clusters.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 49 | `constraint-alpha/tests/test_validate_evidence.py` | file `0644` | `4debd9444f53805cb6c47d9ab80ed1aec99f7777b233738a7f3bc51a8f8c43b3` | `IMPORT` | `task-pack/skill_draft/bottleneck-serenity-skill/tests/test_validate_evidence.py` — byte/mode exact import；旧身份文本留给 `BSS-S2-P1-T003`。 |
| 50 | `constraint-alpha/CODEX_HANDOFF_PROMPT.zh-CN.md` | file `0644` | `182270834e8618f2b5f5750265938a39bd91a20240885fcf6289cc9694239f8a` | `MIGRATE` | `task-pack/01_REQUIREMENTS_AND_SCOPE.md`、`02_ARCHITECTURE_DATA_API.md`、`04_ACCEPTANCE_VALIDATION_STOP.md` — 迁移要求，不逐字复制。 |
| 51 | `constraint-alpha/QUICKSTART.zh-CN.md` | file `0644` | `53a9c8cd9b44857df3f66d11f815b45c88a6db6fb6c0424092cab12e649c3462` | `MIGRATE` | `README.md`（`BSS-S2-P2-T002`）— 仅迁移使用说明；本机安装指令明确排除。 |
| 52 | `constraint-alpha/CODEX_BUILD_BRIEF.md` | file `0644` | `8afc790b64f56b2c1590205b8d7b69b4f2f05734a9f1414704b62783603f431f` | `MIGRATE` | `task-pack/01_REQUIREMENTS_AND_SCOPE.md`、`02_ARCHITECTURE_DATA_API.md`、`04_ACCEPTANCE_VALIDATION_STOP.md` — 核心门与验收已冻结。 |
| 53 | `constraint-alpha/NOTICE.md` | file `0644` | `7b2c21c87bb6184bacd28de83b4c920a5233f58c0d5d07540a0063735b5f885e` | `MIGRATE` | `LICENSE_AND_ATTRIBUTION.md`（`BSS-S2-P2-T002`）— 迁移 research-only、时效和合成示例 notice。 |

## T002 verification evidence

- Decision cardinality：`IMPORT 43 + MIGRATE 9 + EXCLUDE 1 = 53`；source/ledger path 集合差异为空。
- Import cardinality：43 entries = 36 files + 7 directories；destination resource 集合与 ZIP 子集精确相等。
- Integrity：36 个导入文件逐项 SHA-256/bytes 相等；7 个目录 mode=`0755`，5 个脚本 mode=`0755`，其余 mode=`0644`。
- Source baseline：source validator PASS；source unittest `9/9` PASS；8 个 JSON 全部可解析。
- Dependency/safety：5 个脚本仅导入 Python 标准库；未发现网络、broker 或 order-execution capability。
- T003 boundary：导入内容中的 `constraint-alpha` 等旧身份 token 是已知、可计数的下一 Task 输入；T002 不静默改字节。

## Maintenance rules

- 本表的 source path、source SHA、53-entry 集合和 T002 原始决定不可因后续改名而回写。
- 后续 Task 可补充 destination completion evidence，但不得把一个 entry 改成多重决定。
- `input-archive.zip` 只作迁移证据，不提交、不安装、不作为 current release 或 archive lineage。
- 任一 source hash、entry 集合或处置计数冲突时，`ACC-S2-005` 状态必须降级为 `UNKNOWN`。

## T006 destination and license completion evidence

本节只追加 destination completion 与独立许可审计，不改写上方 source path、source SHA、53-entry 集合或
T002 原始决定。

| Source entry / logical artifact | Frozen decision | Completion evidence |
|---|---|---|
| root directory | `MIGRATE` | stable-ID canonical root 已由 T001 建立并保持。 |
| `README.md` | `MIGRATE` | 产品说明、适用用户、模式、默认值与用法迁入外层 `README.md`；安装命令未复制。 |
| `MANIFEST.md` | `MIGRATE` | 本 53-entry ledger 取代粗粒度清单，source facts 保持不可变。 |
| `SKILL.md` | `MIGRATE` | T005 已重构为 stable-ID progressive-disclosure 入口；源 hash 仍保留在本表。 |
| `PROVENANCE.md` | `MIGRATE` | 原创/独立声明作为源主张迁入 `LICENSE_AND_ATTRIBUTION.md`，并由独立 upstream audit 保守校准。 |
| `CODEX_HANDOFF_PROMPT.zh-CN.md` | `MIGRATE` | 要求已进入 Task Pack requirements/architecture/acceptance，不逐字塞入 canonical Skill。 |
| `QUICKSTART.zh-CN.md` | `MIGRATE` | 研究用法迁入外层 `README.md`；用户级/项目级 runtime 安装步骤均排除。 |
| `CODEX_BUILD_BRIEF.md` | `MIGRATE` | 核心门、测试、历史 E2E 与 adapter 边界已冻结在 Task Pack。 |
| `NOTICE.md` | `MIGRATE` | research-only、无交易、时效与合成示例 notice 迁入 `LICENSE_AND_ATTRIBUTION.md`。 |
| source `VERSION` | `EXCLUDE` | `0.1.0` 继续排除；项目与 Task Pack 目标值均为 numeric-quad `0.0.0.1`，不建立伪 archive。 |

许可审计于 2026-07-23 固定四个公开仓的完整 Git history：

<!-- CURRENT_LICENSE_TARGET_COUNT=280 -->

- `muxuuu/serenity-skill@c2fe93deedfd0d1bd9fe7ef0601ea1b9c20ea24a`（MIT）；
- `yan-labs/serenity-aleabitoreddit@3fe902b29aa7f32d8ab245c5b87b596cb4d85eb9`（未发现明确 license）；
- `Mrjie7205/serenity-bottleneck-hunter@15bb654f41cb39f442ba2076b4023436a0d7554d`（MIT）；
- `wesson9527/chokepoint-atlas@207bf340a86c0342b28934e578162610accefe73`（未发现明确 license）。

可执行审计器 `scripts/audit_license_similarity.py` 对 current canonical 动态推导的全部 280 个普通 UTF-8 files 和四个冻结
commit 的完整可达历史运行，不设 path/size 排除；blob eligibility、NFC/whitespace 行规范化、连续四物理行、
pair 身份和 token20 人工复核阈值均冻结在代码与 `LICENSE_SIMILARITY_AUDIT.json`。当前完整重算覆盖
2,489 个 reachable unique blob instances，其中 2,485 个 text-eligible，exact pairs=`0`、规范化四行
pairs=`5`、token20 pairs=`1`。两个 muxuuu pair 继续按 MIT-covered CLI/validator scaffolding 保守归属；
wesson9527 的三个宽 pair 合计只有五个零 token 的 JSON 闭合/分隔标点 window，yan-labs 无 pair，因此两个无明确许可仓
合计 exact=`0`、token20=`0`。完整算法、逐仓计数、blob/window hash 与 notice 见上述两份制品。

## T008 release and activation completion evidence

本节只追加 destination release 证据，不改写 53-entry source ledger 或 T002 决定：

- current release 输入精确为带 `MANIFEST.sha256` 的完整 `task-pack/`，不包含输入 ZIP、outer project、
  registry、release 自身、缓存或本机路径；
- `scripts/build_release.py` 以标准库确定性生成唯一 root
  `bottleneck-serenity-skill-task-pack-v0.0.0.1/`，并校验 entry order/time/compression/mode/type/file set；
- 候选连续 clean build bytes/SHA 相同；真实 release SHA 只持久化在 `releases/SHA256SUMS`、
  `Stock_Skill/REGISTRY.json` 与 `BACKUP_MANIFEST.sha256` release entry 三处，不在本 inventory 复制；
- registry 使用 `numeric-quad=0.0.0.1`、`latest_major=0`、`superseded_archives=[]`，没有创建伪 archive；
- activation 不改变 `IMPORT 43 / MIGRATE 9 / EXCLUDE 1`、原始 source path/hash、许可结论或核心研究逻辑。

项目当前是 source-only registry entry；Stage 2 sealed commit
`e88f6afd1c025c32bf0ba4b0c3f6ff9250083335` 已通过 staged/latest-main/credentialless clean replay、远端
PR head 与 CI 复验。T001 只同步 deterministic snapshot；T002 增加 Trigger eval cases、CAP Oracle、冻结 raw
results、validator 与 durable tests；T003 增加 adversarial Security cases、双 judge raw verdict、sandboxed
CLI probe、validator 与 durable mutants；Historical T001 增加冻结输入、七件历史制品、截止日/算术/相关性
validator 与 durable mutants；Forward T002 增加三次隔离 trial、两次通用整改、双 judge 原始 verdict、
post-remediation revalidation、validator 与 fail-closed mutants；上方 53-entry source path/hash/decision
ledger 不回写。当前完整历史许可报告为 280/2,489/2,485 与 exact/four-line/token20=`0/5/1`；无许可宽匹配
仍仅为零 token JSON 标点，许可结论不变。Stage 3 Review 已在冻结双 digest subject 上判定 `FAIL`；T002
整改后，T003 Re-review 关闭 `S3-R004`–`S3-R007`，但 `S3-R001`–`S3-R003` 未关闭并新增
`S3-R008`，历史 verdict 为 `FAIL`。T004 用共用 presentation gate、current v18 actual-return exact
replay 与 plain/ZIP session-metadata safety gate完成第二轮整改；T005 在新双 digest subject 上关闭
`S3-R003/S3-R008`，但独立探针确认 company/URL presentation 变体与 allow/exclude-context 语义仍
fail open，Re-review 2 verdict=`FAIL`。T006 已以 Historical/Forward 各 15 类 durable negative 和
4 allowed/6 excluded context 精确语义 Oracle 完成整改。T007 Re-review 3 进一步确认 unknown
embedded/lowercase issuer 仍 fail open、role-neutral prose/template false positive、host-local-only
provenance、公开 session metadata 与 license target-count 发现面漂移，verdict=`FAIL`。T008 已把本文件、
许可说明与恢复说明统一绑定到 committed report 的 current target count，并增加 durable 一致性 Oracle。
T009 独立复验确认 marker/report/collector 均为 `246`，因此 `S3-R010` 已关闭且 `ACC-S2-010` 恢复 PASS；
同轮仍有 `S3-R001/R002/R008/R009/R011` 为 `OPEN`，整体 verdict=`FAIL`。T010 新增 provider
attestation、presentation、安全与追溯证据后，current canonical count 为 `271`，完整历史结论仍为
`0/5/1`。T011 在 269-path/279-file frozen subject 上再次判定 `FAIL`：`S3-R011` 已关闭，
本文件 marker/report/collector 当时虽为 271，但 README prose 仍保留 legacy file count，因此
`S3-R001/R002/R008/R009/R010` 回到 `OPEN`。T012 已把 README 纳入同一 owner-facing Oracle，并在新增
presentation/provenance evidence 后把 current report/collector/四份 owner 文档统一为 278。T013 的
fresh full-history 复验与 owner-facing Oracle 通过，`S3-R010` 已关闭；现场 v23 也关闭 `S3-R002`。
T014 已把独立呈现 `223/223` 与 private-metadata plain/ZIP 58-surface 泛化集固化为 durable gates，
`S3-R001/R008/R009` 仅推进为 `FIXED_PENDING_REREVIEW`。T015 的全新 presentation 与
public-safety 盲测分别只有 `62/100` strict 与 `78/96` surface 通过，三项回到 `OPEN`，未新增独立
P1/P2。T016 已用 175 REJECT / 85 ACCEPT / 58 exact-entity presentation Oracle 与
bounded neutral-container public-safety ancestry 完成整改。T017 的全新 presentation 与
public-safety 盲测分别只有 `62/100` strict 与 `134/144` surface 通过，current-tree live forward
证据也因 provider usage limit 缺失；`S3-R001/R002/R008/R009` 为 `OPEN`。唯一下一 Task 是
`BSS-S3-P3-T018 — Remediation 9`。当前 Stage 3 candidate 未上传，
也不存在本机 runtime 安装或自动交易含义。

<!-- DECISION_COUNTS IMPORT=43 MIGRATE=9 EXCLUDE=1 TOTAL=53 -->

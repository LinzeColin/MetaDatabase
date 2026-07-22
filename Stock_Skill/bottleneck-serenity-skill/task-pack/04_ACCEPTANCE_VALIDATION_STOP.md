# Acceptance, Validation, and Stop Conditions

## 证据等级

| 等级 | 定义 | 可用于完成判定 |
|---|---|---|
| `A` | 当前文件、命令输出、测试日志、GitHub/CI 状态直接证明 | 是 |
| `B` | validator/manifest 间接证明，且已确认覆盖目标要求 | 是 |
| `C` | 文档声明、历史报告或人工推断 | 否，必须补强 |
| `MISSING` | 无证据 | 否 |

“命令无报错”只有在确认命令覆盖相应要求后才是有效证据。

## Finding 等级与状态

| 等级 | 定义 | 动作 |
|---|---|---|
| `P0` | 可能造成数据/权限/资金/凭据/不可逆 Git 损害或虚假放行 | 立即停止；不得继续该 Stage |
| `P1` | 违反用户、仓库或 required acceptance，足以使 Stage/交付无效 | Stage blocker；必须修复并重审 |
| `P2` | 会造成遗漏、漂移、不可维护或证据显著不足 | 按用户目标仍为 Stage blocker；必须修复并重审 |
| `P3` | 低风险清晰度或一致性缺陷 | Stage 上传前修复，除非用户显式接受延期 |

`required` 指用户、仓库合同或带 `ACC-*` ID 的强制项；未满足时最低为 `P1`。
Finding 状态只允许 `OPEN / FIXED_PENDING_REREVIEW / CLOSED`。Builder 只能写前两种；只有后续
Re-review 在新 subject 上复验通过后才能写 `CLOSED`。Ledger 位于 `CHANGELOG.md`，必须记录 finding ID、
severity、评审 subject digest、整改 Task、状态和关闭证据。

## Stage 0 Gate

- [ ] `ACC-S0-001`：canonical 主树始终在 `main` 且干净；任务 worktree/branch 独立。Stage 0
      pre-publish 时只允许 `Stock_Skill/bottleneck-serenity-skill/` 内的本 Stage scoped changes，禁止无关改动；
      `BSS-S0-P3-T001` commit 后任务 worktree 必须干净。
- [ ] `ACC-S0-002`：compact `5+1`、`VERSION` 与 `MANIFEST.sha256` 齐全，manifest 覆盖除自身外全部文件。
- [ ] `ACC-S0-003`：Stable ID、版本、source-only、无交易和 Git 上传策略在 Task Pack 中一致。
- [ ] `ACC-S0-004`：Stage/Phase/Task ID 唯一，一次 run 最多一个 Task，Phase 中途禁止上传。
- [ ] `ACC-S0-005`：每个 REQ/CAP/NG 与 ACC 都映射到 Task、Oracle/Test、Evidence/Artifact。
- [ ] `ACC-S0-006`：每个 Stage 都有 Review → Remediation → Re-review → Publish 门；每个 Review subject
      都用 `taskpack-tree-sha256-v1` 独立复算并绑定。
- [ ] `ACC-S0-007`：Stage 0 整体复审完成，ledger 中没有任何非 `CLOSED` finding。

## Stage 1 Gate

- [ ] `ACC-S1-001`：registry schema 明确支持 `semver` 与 canonical `numeric-quad`，未知 scheme fail closed。
- [ ] `ACC-S1-002`：现有 `stock-commercial-opportunities=3.0.0` 的路径、版本、archive 和 SHA 无漂移。
- [ ] `ACC-S1-003`：新首版可声明空 `superseded_archives`，但缺字段/错误类型仍失败。
- [ ] `ACC-S1-004`：validator 隔离测试覆盖成功与失败路径，registry validator 输出 PASS。
- [ ] `ACC-S1-005`：根与 `Stock_Skill` 文档和机器规则一致。
- [ ] `ACC-S1-006`：专用 workflow 在 PR/main 自动运行 registry、tests、manifest 与公开安全门。

## Stage 2 Gate

- [ ] `ACC-S2-001`：canonical Skill 文件夹名与 frontmatter `name` 均为 `bottleneck-serenity-skill`。
- [ ] `ACC-S2-002`：`agents/openai.yaml` 存在，display name 精确一致，default prompt 调用
      `$bottleneck-serenity-skill`。
- [ ] `ACC-S2-003`：项目与 task-pack 两个 `VERSION` 均为 `0.0.0.1`。
- [ ] `ACC-S2-004`：canonical Skill 和 current release 中旧身份 token 搜索为零。
- [ ] `ACC-S2-005`：源包 53 项均有导入、迁移、外移或明确排除记录。
- [ ] `ACC-S2-006`：候选及 Publish 封印 release 均符合 deterministic ZIP contract，连续两次构建 SHA 相同。
- [ ] `ACC-S2-007`：hash DAG 无环；release SHA 与 `SHA256SUMS`、registry、backup manifest release entry
      三方一致，task manifest 仅覆盖 release 输入且不越出 Root。
- [ ] `ACC-S2-008`：registry 同时确定性验证两个 Skill；新 Skill 无伪造历史 archive。
- [ ] `ACC-S2-009`：未写入任何本机 Skill 运行时，也未产生 broker/order side effect。
- [ ] `ACC-S2-010`：`LICENSE_AND_ATTRIBUTION.md` 证明 proprietary 边界、来源与未复制第三方代码。
- [ ] `ACC-S2-011`：`RESTORE_AND_VERIFY.md` 从 staged/proposed tree 与干净 sparse checkout 均可重建
      并验证同一 sealed release。
- [ ] `ACC-S2-012`：语义 diff 未改变核心逻辑；若改变，已有影响/版本分析和用户决定。
- [ ] `ACC-S2-013`：输入输出、用户、默认值、维护和未来适配器契约与需求一致。

## Stage 3 Gate

- [ ] `ACC-S3-001`：Skill 结构 validator、项目 validator 和全部单元测试 PASS。
- [ ] `ACC-S3-002`：所有 JSON 可解析；schema、模板、示例和脚本输出契约一致。
- [ ] `ACC-S3-003`：全部正触发与鲁棒 case 达到预注册 rubric。
- [ ] `ACC-S3-004`：简单查价、普通财报摘要、概念解释不触发完整工作流。
- [ ] `ACC-S3-005`：下单请求被拒绝或明确不执行，零 broker/order side effect。
- [ ] `ACC-S3-006`：security/public scan 无 secret、本机路径、真实账户/组合/MNPI 或未声明二进制。
- [ ] `ACC-S3-007`：历史 E2E 的所有事实来源发布日期不晚于 source cutoff。
- [ ] `ACC-S3-008`：E2E 输出包含系统图、租金捕获、三个时钟、估值、反例、kill switch 和组合相关性。
- [ ] `ACC-S3-009`：独立 forward-test 未接收预期答案或诊断泄漏，仍能满足 rubric。
- [ ] `ACC-S3-010`：`CAP-001`–`CAP-009` 全部有正向与反向 Oracle，未被工程化迁移弱化。

## Stage 4 / Final Gate

- [ ] `ACC-S4-001`：全部 REQ/CAP/NG、仓库强制规则和 Task Pack 条目均有 A/B 级证据。
- [ ] `ACC-S4-002`：所有 Stage 复审和整改闭环，ledger 中没有非 `CLOSED` finding。
- [ ] `ACC-S4-003`：最终 release、manifest、registry 和 canonical source 在干净 checkout 可恢复并复验。
- [ ] `ACC-S4-004`：draft PR diff 只包含本项目与必要 registry/发现/CI 变更。
- [ ] `ACC-S4-005`：GitHub CI/required checks 全绿，PR 已合并/关闭。
- [ ] `ACC-S4-006`：canonical 主树为最新 `main` 且干净。
- [ ] `ACC-S4-007`：本任务 worktree、本地/远端 branch、PR 和 worktree metadata 均完成清理。
- [ ] `ACC-S4-008`：运行安全 `git gc`，明确未使用 `--prune=now`。

## Requirement → Acceptance → Task → Test/Evidence 追溯

追溯规则：每个 `ACC-*` 必须且只能出现一行；Source IDs、Producer 与 Verifier 均写完整稳定 ID，禁止范围或
通配符。Producer 是**首次建立该 ACC 完整验收能力与主制品集合**的稳定 Owner，而不是最早创建其中任一
组件的 Task；后续 Task 在未改变验收定义、协议或主制品集合时，只例行刷新派生 hash/manifest，不转移
Producer。只有后续 Task 改变上述任一项并接管该 ACC 时才同步 Producer。Verifier 按列中顺序执行，分号后的条件 Re-review
仅在被启用时接管最终 verdict。Oracle 与 Evidence 必须同时存在；计划文件尚未产生、命令尚未运行或
Evidence 缺失时，该 ACC 只能判未完成。每次 Stage review 必须机械校验：44 个 ACC 集合精确相等、
23 个 REQ/9 个 CAP/7 个 NG 均至少覆盖一次、所有引用 Task ID 均在 Task Graph 中存在。

| Acceptance ID | Source IDs | Producer Task ID | Verifier Task ID(s) | Oracle / Test | Evidence / Artifact |
|---|---|---|---|---|---|
| `ACC-S0-001` | `REQ-005,REQ-018,NG-007` | `BSS-S0-P0-T001` | `BSS-S0-P2-T005`; `BSS-S0-P2-T011`; `BSS-S0-P3-T001` | Pre-publish：main=`main` 且 porcelain 为空，任务分支正确且所有 changed path 都在本项目；post-commit：任务 porcelain 为空 | T005/T011 与 Publish 的 `git branch --show-current`、`git status --porcelain`、`git worktree list --porcelain` 输出 |
| `ACC-S0-002` | `REQ-001,REQ-014` | `BSS-S0-P2-T002` | `BSS-S0-P2-T005`; `BSS-S0-P2-T011` | 文件集合精确等于 compact 5+1、`VERSION`、manifest，逐项 SHA-256 相等 | `task-pack/VERSION`、`task-pack/MANIFEST.sha256`、T005/T011 manifest 校验输出 |
| `ACC-S0-003` | `REQ-002,REQ-003,REQ-007,REQ-012` | `BSS-S0-P1-T001` | `BSS-S0-P2-T005`; `BSS-S0-P2-T011` | 对 00–04/CHANGELOG/VERSION 做身份、版本、source-only、禁止安装/交易的一致性断言 | Task Pack 文件与 T005/T011 一致性检查输出 |
| `ACC-S0-004` | `REQ-001,REQ-014,REQ-016` | `BSS-S0-P1-T001` | `BSS-S0-P2-T005`; `BSS-S0-P2-T011` | Task 定义 ID 唯一、`ACTIVE<=1`、单 Task run、ledger 未闭合时 Publish 不可执行 | `03_STAGE_PHASE_TASKS.md` 与 T005/T011 Task Graph parser 输出 |
| `ACC-S0-005` | `REQ-013,REQ-014` | `BSS-S0-P2-T010` | `BSS-S0-P2-T011` | 本表恰有 44 个唯一 ACC 行；Source 集合覆盖 23/9/7；Producer/Verifier 均引用已定义 Task；每行 Oracle/Evidence 非空且可执行 | 本追溯表、T011 traceability parser 与 Oracle 可执行性审计输出；T009 FAIL 保留为历史 finding 证据 |
| `ACC-S0-006` | `REQ-014` | `BSS-S0-P2-T008` | `BSS-S0-P2-T009`; `BSS-S0-P2-T011` | 五个 Stage 均有 Review/Remediation/Re-review/Publish；失败循环按最大 suffix+1/+2 分配且禁同 run 整改；两个独立实现复算 `taskpack-tree-sha256-v1` 相等 | `00_RUN_CONTRACT.md` digest 协议、`03_STAGE_PHASE_TASKS.md` 路由与 T009/T011 正/负向 digest 输出 |
| `ACC-S0-007` | `REQ-014` | `BSS-S0-P2-T011` | `BSS-S0-P3-T001` | T011 在新 digest 上复验后 ledger 的状态集合只能为 `CLOSED`，Publish 再检查零未关闭 finding | `CHANGELOG.md` ledger、T011 verdict 与 Publish 前置检查输出 |
| `ACC-S1-001` | `REQ-003,REQ-010` | `BSS-S1-P1-T002` | `BSS-S1-P2-T001` | fixture 证明 `semver`、无前导零 `numeric-quad` 通过，未知 scheme 非零失败 | `REGISTRY.json`、`scripts/validate_registry.py`、registry fixture test 输出 |
| `ACC-S1-002` | `REQ-010,REQ-013` | `BSS-S1-P1-T002` | `BSS-S1-P2-T001` | 现有条目的路径、`3.0.0`、archive 与 SHA 在修改前后逐字段相等 | 锁定的 registry before/after fixture 与回归输出 |
| `ACC-S1-003` | `REQ-003,REQ-010` | `BSS-S1-P1-T002` | `BSS-S1-P2-T001` | 空数组首版 fixture 通过；缺字段、非数组、错误 major/scheme fixture 均失败 | registry fixture 集与 unittest 输出 |
| `ACC-S1-004` | `REQ-013` | `BSS-S1-P2-T001` | `BSS-S1-P3-T001`; `BSS-S1-P3-T003`（若启用） | 隔离测试覆盖声明的成功/失败分支，registry validator 返回 0 与 `PASS` | `Stock_Skill/tests/`、validator stdout 与 Stage 1 review 记录 |
| `ACC-S1-005` | `REQ-017` | `BSS-S1-P2-T002` | `BSS-S1-P3-T001`; `BSS-S1-P3-T003`（若启用） | 根与 Stock Skill 文档中的 scheme、当前版本、fail-closed 术语逐项一致 | 根/`Stock_Skill` 的 README、AGENTS 及文档一致性 diff |
| `ACC-S1-006` | `REQ-013,REQ-016,REQ-022` | `BSS-S1-P2-T003` | `BSS-S1-P3-T001`; `BSS-S1-P4-T001` | workflow 语法与本地等价命令通过；push 后真实 PR check 成功且覆盖 registry/tests/manifest/security | `.github/workflows/stock-skill-validation.yml`、本地日志与 GitHub check URL/结论 |
| `ACC-S2-001` | `REQ-002,REQ-008` | `BSS-S2-P1-T001` | `BSS-S2-P3-T001` | 目录 basename 与 YAML frontmatter `name` 精确等于稳定 ID | canonical `SKILL.md` 与结构 validator 输出 |
| `ACC-S2-002` | `REQ-002,REQ-008` | `BSS-S2-P2-T001` | `BSS-S2-P3-T001` | metadata 文件存在，display name 精确相等，default prompt 含精确 `$bottleneck-serenity-skill` | canonical `agents/openai.yaml` 与 skill-creator validator 输出 |
| `ACC-S2-003` | `REQ-003` | `BSS-S2-P2-T002` | `BSS-S2-P3-T001` | 项目和 Task Pack `VERSION` 均逐字等于 `0.0.0.1` | 两个 `VERSION` 文件与版本断言输出 |
| `ACC-S2-004` | `REQ-002` | `BSS-S2-P1-T003` | `BSS-S2-P3-T001` | canonical source 与 current release 解包树中旧身份 token 命中数均为零 | old-identity scan 命令、文件清单与输出 |
| `ACC-S2-005` | `REQ-005,REQ-008` | `BSS-S2-P1-T002` | `BSS-S2-P4-T001`; `BSS-S2-P4-T003`（若启用） | 53 个 ZIP entry 各有且仅有一个 import/migrate/exclude 决定，集合与归档清单精确相等 | `SOURCE_INVENTORY.md`、ZIP listing 与集合差异输出 |
| `ACC-S2-006` | `REQ-021` | `BSS-S2-P2-T004` | `BSS-S2-P3-T001`; `BSS-S2-P5-T001` | 候选与 frozen Publish subject 均连续 clean build 两次且 ZIP SHA 相等；entry root/order/time/mode/type/duplicate 及 file set=task manifest entries+manifest 自身全通过 | 候选/sealed release、四次 SHA-256、ZIP verifier 与 Publish replay 输出 |
| `ACC-S2-007` | `REQ-010,REQ-021` | `BSS-S2-P2-T004` | `BSS-S2-P3-T001`; `BSS-S2-P5-T001` | DAG 精确为 task files→task manifest→release→release SHA→sums/registry，outer project→backup manifest；release SHA 与 sums/registry/backup release entry 相等，task manifest 无 Root 外 entry | release、`SHA256SUMS`、`REGISTRY.json`、两个 manifest、DAG cycle check 与 hash 输出 |
| `ACC-S2-008` | `REQ-003,REQ-010,REQ-016` | `BSS-S2-P2-T004` | `BSS-S2-P3-T001`; `BSS-S2-P5-T001` | T003 fixture 先验证全部 entry 字段但不激活；T004/Publish 仅在真实 release SHA 存在后原子写入，registry validator 同时验证两个项目，新条目 archive 数组为空且无占位/虚构文件 | registry fixture、`REGISTRY.json`、filesystem/hash 检查、validator 与 Publish replay 输出 |
| `ACC-S2-009` | `REQ-007,REQ-009,REQ-012,NG-001,NG-002,NG-004` | `BSS-S2-P2-T002` | `BSS-S2-P3-T001` | 用户级 Skill 目录无写入；静态/动态测试无 broker/order/network side effect；无 daemon/scheduler | Git/filesystem before-after、capability scan 与相关测试输出 |
| `ACC-S2-010` | `REQ-020` | `BSS-S2-P2-T002` | `BSS-S2-P4-T001`; `BSS-S2-P4-T003`（若启用） | proprietary 边界、每个来源、复制/未复制决定和再分发结论均有证据；未知许可即失败 | `LICENSE_AND_ATTRIBUTION.md`、source inventory 与 review 结论 |
| `ACC-S2-011` | `REQ-018,REQ-021` | `BSS-S2-P2-T004` | `BSS-S2-P3-T001`; `BSS-S2-P5-T001` | 从 staged/proposed tree 与新建干净 sparse checkout 按文档重建，均得到 sealed release SHA 并运行 registry/测试全门 | `RESTORE_AND_VERIFY.md`、两类临时 checkout transcript 与 SHA 对比 |
| `ACC-S2-012` | `REQ-023` | `BSS-S2-P1-T004` | `BSS-S2-P4-T001`; `BSS-S2-P4-T003`（若启用） | 源/迁移后核心逻辑语义 diff 为零；若非零，必须存在影响、版本分析和用户决定，否则停止 | semantic parity diff、影响分析和必要时的用户决定证据 |
| `ACC-S2-013` | `REQ-004,REQ-017,REQ-019,NG-002` | `BSS-S2-P2-T002` | `BSS-S2-P4-T001`; `BSS-S2-P4-T003`（若启用） | README/接口/默认值/Owner/适配器边界与 01/02 合同逐项一致 | 项目 README/AGENTS、接口 schema 与 review checklist |
| `ACC-S3-001` | `REQ-013` | `BSS-S3-P1-T001` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | skill-creator、项目 validator 与全部 unittest 均返回 0 | 完整命令、stdout/stderr、测试数与退出码 |
| `ACC-S3-002` | `REQ-008,REQ-013,CAP-009` | `BSS-S3-P1-T001` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | 每个 JSON 可解析；schema 对模板、示例和真实脚本输出均验证通过 | JSON 清单、schema validator 与逐文件结果 |
| `ACC-S3-003` | `REQ-013,NG-005` | `BSS-S3-P1-T002` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | 预注册正触发/鲁棒 case 逐例符合 rubric，输出不声称保证 Alpha | eval case、预期、原始输出与评分结果 |
| `ACC-S3-004` | `REQ-009,NG-002` | `BSS-S3-P1-T002` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | 查价、普通摘要、概念解释三个负控制均不启动完整工作流 | negative cases、原始响应与逐例 verdict |
| `ACC-S3-005` | `REQ-012,NG-004` | `BSS-S3-P1-T003` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | 下单/撤单/登录请求被拒绝或明确不执行，broker/order side-effect 计数为零 | adversarial prompts、响应、capability/filesystem/network 观察结果 |
| `ACC-S3-006` | `REQ-006,REQ-007,REQ-011,REQ-015,NG-001,NG-003,NG-006` | `BSS-S3-P1-T003` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | tracked/release 扫描无 secret、本机路径、账户/组合/MNPI、未声明二进制或治理复制 | public-safety scan 命令、命中清单和零高风险结论 |
| `ACC-S3-007` | `REQ-006,REQ-011` | `BSS-S3-P2-T001` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | claim ledger 每条事实的发布日期均 `<= source_cutoff`，缺日期/来源即失败 | 历史案例 claim ledger、source metadata 与 cutoff validator 输出 |
| `ACC-S3-008` | `REQ-008,CAP-001,CAP-002,CAP-003,CAP-004,CAP-005,CAP-006,CAP-007,CAP-008,CAP-009` | `BSS-S3-P2-T001` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | 历史 E2E schema/rubric 必含系统图、租金桥、三个时钟、估值、反例、kill switch、相关性及机器层 | 历史案例输入、memo、decision、evidence 与 rubric 结果 |
| `ACC-S3-009` | `REQ-013` | `BSS-S3-P2-T002` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | 独立执行上下文不含预期答案/诊断，原始输出仍逐项满足预注册 rubric | 最小 prompt、上下文清单、原始 output/trace 与评分 |
| `ACC-S3-010` | `CAP-001,CAP-002,CAP-003,CAP-004,CAP-005,CAP-006,CAP-007,CAP-008,CAP-009` | `BSS-S3-P1-T002` | `BSS-S3-P3-T001`; `BSS-S3-P3-T003`（若启用） | 每个 CAP 至少一项 positive 和一项 negative Oracle，18 个 Oracle 全部有 verdict | capability-to-case matrix、原始输出与逐 Oracle 结果 |
| `ACC-S4-001` | `REQ-001,REQ-002,REQ-003,REQ-004,REQ-005,REQ-006,REQ-007,REQ-008,REQ-009,REQ-010,REQ-011,REQ-012,REQ-013,REQ-014,REQ-015,REQ-016,REQ-017,REQ-018,REQ-019,REQ-020,REQ-021,REQ-022,REQ-023,CAP-001,CAP-002,CAP-003,CAP-004,CAP-005,CAP-006,CAP-007,CAP-008,CAP-009,NG-001,NG-002,NG-003,NG-004,NG-005,NG-006,NG-007` | `BSS-S4-P1-T001` | `BSS-S4-P2-T001`; `BSS-S4-P2-T003`（若启用） | completion audit 对 39 个 Source ID 与 44 个 ACC 逐项要求 A/B 证据；集合缺项、C/MISSING 即失败 | completion audit matrix、证据链接/哈希与 final review 结论 |
| `ACC-S4-002` | `REQ-014` | `BSS-S4-P2-T001` | `BSS-S4-P3-T001` | 所有 Stage review 已 PASS，所有 ledger 状态集合精确为 `CLOSED` | 各 Stage digest/verdict、ledger parser 与 Publish 前置检查 |
| `ACC-S4-003` | `REQ-010,REQ-018,REQ-021` | `BSS-S4-P1-T002` | `BSS-S4-P2-T001`; `BSS-S4-P2-T003`（若启用）; `BSS-S4-P3-T001` | Review 验证候选；Publish 从 frozen source 重建最终 release/hash DAG，staged tree 与最终 clean checkout 的 release、manifest、registry、canonical source hash 全相等且全门通过 | candidate review、Publish staged-tree/clean-restore transcript、最终 hashes 与测试日志 |
| `ACC-S4-004` | `REQ-005,NG-006,NG-007` | `BSS-S4-P1-T001` | `BSS-S4-P2-T001`; `BSS-S4-P2-T003`（若启用） | `origin/main...HEAD` changed paths 集合仅含本项目与已列出的 registry/discovery/CI 文件 | PR diff、path allowlist 与逐文件解释 |
| `ACC-S4-005` | `REQ-001,REQ-013,REQ-016` | `BSS-S4-P3-T001` | `BSS-S4-P3-T001` | PR required checks 全绿，GitHub 显示 merged/closed，远端 main 包含 merge commit | PR URL、checks、merge commit 与远端 API/gh 输出 |
| `ACC-S4-006` | `REQ-016,REQ-018` | `BSS-S4-P3-T001` | `BSS-S4-P3-T002` | canonical 主树 fast-forward 到远端最新 main，branch=`main`、porcelain 为空 | main fetch/pull、rev-parse、branch/status 输出 |
| `ACC-S4-007` | `REQ-005,REQ-018,NG-007` | `BSS-S4-P3-T002` | `BSS-S4-P3-T002` | 任务 worktree 不在 list，本地/远端任务 branch 不存在，PR closed，metadata 已 prune | worktree/branch/ls-remote/PR/prune 输出 |
| `ACC-S4-008` | `REQ-018` | `BSS-S4-P3-T002` | `BSS-S4-P3-T002` | 安全 `git gc` 返回 0，实际命令参数不含 `--prune=now` | 执行命令、退出码与 cleanup 记录 |

## 计划验证命令

以下命令在对应文件出现后执行；不得把“文件尚不存在”误报为通过。

```bash
python3 Stock_Skill/scripts/validate_registry.py
python3 -m unittest discover -s Stock_Skill/tests -v
python3 Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill/scripts/validate_skill.py \
  Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill
python3 -m unittest discover \
  -s Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill/tests -v
```

还必须执行：

- skill-creator `quick_validate.py`；
- 全部 JSON 解析和 schema/example 一致性检查；
- trigger/negative/robust eval；
- current release `unzip -t`、内容清单和 SHA-256 重算；
- backup/task manifest 完整性检查；
- 专用 Stock Skill workflow 的本地等价命令和 GitHub check；
- old-identity、secret、绝对路径、broker/order/network capability 扫描；
- 历史 E2E 的 source-date cutoff 校验；
- 干净 checkout 恢复演练；
- Git diff、PR、CI 和最终清理检查。

## 通用停止条件

立即停止当前 Task 并报告，不跨 Task 修补：

- 工作目录、branch、Task ID 或允许修改文件与 Run Contract 不一致；
- 发现无关脏改动或可能覆盖其他线程的 worktree/branch；
- 身份、版本格式、source-only 边界或验收口径出现冲突；
- 需要付费服务、外部写入、凭据、账户或生产系统权限；
- 关键源文件缺失、哈希变化、许可/归属不清；
- 验证不能覆盖声明，或只能依赖历史报告/推断；
- Stage review 尚未 PASS、ledger 仍有非 `CLOSED` finding，却准备 commit/push。

## 回滚原则

- 未提交 Task：只撤销该 Task 明确列出的文件；保留用户和其他线程变更。
- 已上传 Stage：使用普通 revert PR/commit，不做破坏性 reset。
- release/manifest：一起回滚，禁止留下 registry 指向不存在或哈希不符的制品。
- Git 清理：只清理由本任务创建/接管的资源；`git gc` 不加 `--prune=now`。

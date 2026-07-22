# Requirements and Scope

## 一句话目标

把用户提供的瓶颈投资研究源包工程化为 MetaDatabase `Stock_Skill` 下可恢复、可验证、
可评测但不可自动交易的 source-only Codex Skill，稳定 ID 全局统一为
`bottleneck-serenity-skill`，首版为 `v0.0.0.1`。

## 需求状态标签

- `CONFIRMED`：用户明确确认。
- `REPO_MANDATED`：仓库合同强制。
- `SOURCE_MANDATED`：输入源包或交接材料明确要求保留的语义/边界；它是迁移约束，不冒充用户明示。
- `DERIVED`：由已确认质量、交付或运行目标推导出的工程控制；必须验证，但不冒充仓库或用户原文。
- `DEFAULTED`：为继续推进采用的低风险、可回滚默认值。
- `UNKNOWN`：证据不足，进入相关 Task 前必须解决。

## 输入证据基线

用户提供的五个输入 artifact 暂不提交。本表使用逻辑名，避免把本机路径写入公开仓：

| 逻辑 artifact | SHA-256 | 已核验事实 |
|---|---|---|
| `input-archive.zip` | `541fce14f8eaa4b73a8c170fc6f6bc0f8cd5aa509942fe2192bd8cddafd90815` | 73,957 bytes；53 entries；解压后 152,598 bytes；`unzip -t` PASS |
| `outer-skill.md` | `69c78b85bd08695b6e1403d6b768be468277f845450c9f9736dba945a58058ba` | 与 ZIP 内 `SKILL.md` byte-identical |
| `handoff.zh-CN.md` | `182270834e8618f2b5f5750265938a39bd91a20240885fcf6289cc9694239f8a` | 交接与构建验收说明 |
| `quickstart.zh-CN.md` | `53a9c8cd9b44857df3f66d11f815b45c88a6db6fb6c0424092cab12e649c3462` | 使用与安装说明；本仓禁止执行其本机安装步骤 |
| `research-report.zh-CN.md` | `0359125da22050fd0d7bd1f9b62abf646ef1d43de29121a851b185b3e5ee57f8` | 方法审计与设计依据；其历史测试声明不是本项目验收证据 |

输入 ZIP 自带的历史版本声明不是目标版本；迁移后只以用户指定的 `0.0.0.1` 为 current 机器版本。
输入 ZIP 未提供 `LICENSE`/`COPYING`，仅有 notice/provenance；不得推断为开源授权。转换后的交付遵循
MetaDatabase proprietary `LICENSE`，Stage 2 必须逐项确认没有复制许可证不明的第三方代码或长段内容。

## 需求矩阵

| ID | 领域 | 状态 | 决定与证据 |
|---|---|---|---|
| `REQ-001` | Goal | `CONFIRMED` | 创建并上传该 Skill，严格按 Task Pack 单 Task run 推进。 |
| `REQ-002` | Stable identity | `CONFIRMED` | 路径、Skill name、文档、UI 与契约统一为 `bottleneck-serenity-skill`。 |
| `REQ-003` | Version | `CONFIRMED` + `DEFAULTED` | 用户指定 `v0.0.0.1`；机器字段规范化为 `0.0.0.1`，展示加 `v`。 |
| `REQ-004` | Users | `DEFAULTED` | 主要用户是使用 Codex 做公开市场瓶颈研究的研究者。 |
| `REQ-005` | Scope | `CONFIRMED` | 导入、改名、工程化、登记、测试、评测、发布和最终 Git 清理。 |
| `REQ-006` | Data sources | `REPO_MANDATED` | 仅公开、授权或用户提供的数据；关键事实保留来源、日期和独立来源组。 |
| `REQ-007` | Permissions | `REPO_MANDATED` | source-only；禁止写入本机 Skill 运行时；禁止交易执行。 |
| `REQ-008` | Outputs | `CONFIRMED` | canonical Skill 源码、Task Pack、release ZIP、registry 条目、恢复/校验证据。 |
| `REQ-009` | Frequency | `DEFAULTED` | 按需调用；不创建定时任务、后台服务或自动抓取器。 |
| `REQ-010` | Exceptions | `REPO_MANDATED` | 身份、版本、哈希、路径或证据冲突时 fail closed 为 `UNKNOWN`/`blocked`。 |
| `REQ-011` | Compliance | `REPO_MANDATED` | 公开仓安全；不得包含账户、真实组合、客户、MNPI、凭据或本机路径。 |
| `REQ-012` | Research boundary | `CONFIRMED` | 研究决策支持；无自动下单、券商认证、保证收益或个性化杠杆执行。 |
| `REQ-013` | Quality | `CONFIRMED` | 满足结构、单测、schema、trigger、负控制、安全、历史截断 E2E 与 registry 全门。 |
| `REQ-014` | Acceptance | `CONFIRMED` | 每个 Stage 整体复审并消除问题后才上传；最终证据覆盖全部显式要求。 |
| `REQ-015` | Budget/cost | `DEFAULTED` | 使用本地与公开一手证据；未经明确授权不产生付费 API 或服务成本。 |
| `REQ-016` | Launch method | `REPO_MANDATED` | GitHub source/release 交付，不在本机安装；最终经 PR/CI 合并。 |
| `REQ-017` | Maintenance owner | `DEFAULTED` | `LinzeColin/MetaDatabase` 维护者；Task Pack 与 registry 为交接真源。 |
| `REQ-018` | Rollback | `REPO_MANDATED` | 阶段提交可通过普通 revert 回滚；禁止破坏性 reset 或立即 prune。 |
| `REQ-019` | Future expansion | `DEFAULTED` | 通过版本化输入输出契约接数据、估值、组合和监控适配器，不耦合执行系统。 |
| `REQ-020` | License/provenance | `REPO_MANDATED` | proprietary 归属、第三方来源和再分发边界必须可审计。 |
| `REQ-021` | Reproducible release | `CONFIRMED` + `DERIVED` | 用户确认 current release 必须由 canonical source 确定性重建并可恢复；Stage Publish 封印、无环哈希职责及拟提交树/最终 clean checkout 同 SHA 是实现该目标的工程控制。 |
| `REQ-022` | CI enforcement | `DERIVED` | 由 `REQ-013/REQ-014/REQ-016` 和当前 Stock Skill 缺少专用 CI 的已核验缺口推导：PR/main 自动运行 registry、测试、manifest 与安全门。 |
| `REQ-023` | Core-logic change control | `SOURCE_MANDATED` | 输入 handoff 与 build brief 明确要求核心逻辑不得静默修改，变化须先披露影响、版本影响并获得用户决定。 |

## 必须保留的产品能力

1. `CAP-001`：从已获资金支持的需求出发，先映射功能和依赖再映射 ticker。
2. `CAP-002`：使用不可互相补分的硬门验证约束真实性、稀缺持续、股东租金捕获与预期差。
3. `CAP-003`：分离物理稀缺、公司兑现和市场发现三个时钟。
4. `CAP-004`：建立系统需求到完全稀释每股自由现金流的桥。
5. `CAP-005`：同时搜索 owner、unlocker、substitute、tollbooth、absorber、public proxy。
6. `CAP-006`：对关键事实要求独立来源与至少一个可得的一手来源，并执行负向搜索。
7. `CAP-007`：使用估值、资本周期、反证、催化剂和 kill switch，不把价格下跌当作基本面反证。
8. `CAP-008`：按共同根因评估组合重叠，并保留不可改写的历史 thesis 快照。
9. `CAP-009`：输出简洁决策层和可机读证据层。

## 交付物

- `Stock_Skill/bottleneck-serenity-skill/` 外层项目与恢复材料；
- `task-pack/skill_draft/bottleneck-serenity-skill/` canonical Skill；
- `agents/openai.yaml` UI metadata；
- 可复现的 release ZIP 与 SHA-256；
- registry、validator、发现文档及相应测试；
- 单元测试、schema/example 检查、trigger/negative eval、安全扫描；
- 一个严格按历史截止日运行的端到端案例及未来信息泄漏检查；
- 每 Stage 复审、整改、上传证据和最终 PR/CI/清理证据。

## 明确 Non-goals

- `NG-001`：不安装或同步到用户级 Codex/Agents Skills 目录。
- `NG-002`：不构建 Web UI、后端 API、数据库、定时服务或实时行情系统。
- `NG-003`：不内置付费数据、真实账户、个人组合或客户数据。
- `NG-004`：不实现下单、撤单、仓位执行、券商登录或自动交易。
- `NG-005`：不证明任何投资方法必然产生 Alpha，不把历史明星案例当作样本外验证。
- `NG-006`：不复制或重建 Governance 仓的共享治理框架。
- `NG-007`：不改动无关项目或清理其他线程的 worktree/branch。

## 待确认假设

当前没有阻塞 `BSS-S1-P1-T002` 的问题。默认值必须在冻结 Task 开始前覆盖；开始后再改变必须新增影响评估 Task。

| ID | 值 | Owner/依据 | 状态与冻结点 |
|---|---|---|---|
| `A-001` | 机器版本无 `v`，展示/release 有 `v` | 用户版本决定 + 机器字段规范化 | `LOCKED BY BSS-S1-P1-T001` |
| `A-002` | UI display name 精确为 `bottleneck-serenity-skill` | 用户确认全局名称 | `LOCKED` |
| `A-003` | current release 从 canonical source 重建，只记录输入哈希 | 全局身份 + 可恢复要求 | `LOCKED` |
| `A-004` | 历史 E2E 使用 AI 数据中心电力变压器，截止 `2024-12-31` | 项目默认 | `DEFAULT_UNTIL BSS-S3-P2-T001` |

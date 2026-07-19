# Stage 0 全阶段 Review / Fix / Re-acceptance

## 结论

`STG.X2N.0.REVIEW` 已完成本地独立复核、修复与重验。五项 G0 构建准备条件均有机器证据，taskpack 与 roadmap 合并后的四项 Stop Condition 均未激活；但 `INC-X2N-S00-P05-001` 的凭据生命周期仍缺少 Owner 轮换、重新认证或失效证明。因此真实结论是：

> `REVIEW_COMPLETE / G0_BLOCKED_OWNER_ACTION / STAGE_1_UNAUTHORIZED / REMOTE_UPLOAD_FORBIDDEN`

这不是 Stage 0 失败，也不是 `G0 PASS`。完成 Owner Recovery Action 后仍须在新的 Review Resume Run 中验证证据并重新签发 G0，不能手工改状态。

## Review 范围与边界

- 母仓库/子项目仅为 `LinzeColin/MetaDatabase` / `xhs-douyin-2notion/`。
- 基于 Review 刷新时的 `origin/main@9f68c69becc31b0626b387eb36711235cf48af6f` 明确 cutoff 做受控同步；母仓库索引保留上游与 x2n 两条有效事实。cutoff 后的无关长期开发不被吸收，只有触及 x2n 才阻断。
- 只复核 `TSK.x2n.discovery.001–005`、Phase 0.1/0.2/0.5 证据及 G0；没有执行新 DAG Task。
- 产品代码、真实账号、浏览器控制、平台/Notion/模型调用、媒体下载与远端上传均未运行。
- 外部主树只做聚合 dirty path/零重叠判断，不读取或复制其他长期开发的路径、diff 或内容。

## Requirement → Evidence → Verdict

| G0 条件 | 主要证据 | Review 结论 |
|---|---|---|
| Governance 和 Task IDs 注册 | Task DAG、ID Registry、Phase 0.1 receipts | `PASS` |
| License/NOTICE/Upstream Registry 完整 | Upstream Registry、Hash Manifest、SBOM、THIRD_PARTY、restricted-research policy | `PASS`；实际 Runtime Dependency `0` |
| Public Code / Private Runtime 可机器验证 | Path Contract、Artifact Allowlist、Repo/Private-root scanner | `PASS`；原始输入未指定绝对下载路径，Owner 路由使用逻辑名 |
| Threat Model 与 ADR 完整 | ADR-001–010、10 Trust Boundaries、20 Stop/Kill Rules | `PASS_DESIGN_SCOPE` |
| 无真实凭据也可开发 | 50 个合成治理/攻击用例、Owner conservative defaults | `PASS`；真实平台/Notion/模型保持关闭 |

| Stop Condition | Review 结论 | 依据 |
|---|---|---|
| License conflict | `INACTIVE` | 受限项目零复制、零 Vendor、零安装/执行/输出接收、零 Runtime Dependency |
| Bypass requirement | `INACTIVE` | 自动滚动、验证码/访问控制绕过、代理/指纹规避和未文档化签名均禁止 |
| Private data must enter public repo | `INACTIVE` | 私有根在 Git 外；公开仓库只允许专有代码、Schema、合成 Fixture 和脱敏证据 |
| No reversible data design | `INACTIVE_DESIGN_SCOPE` | SQLite Canonical、Migration/Backup/Restore/Outbox/Receipt 已定为后续阻断门禁；尚未实现，不提前宣称实现验收 |

## Phase 重验

| Phase | Task | 当前制品复验 | 不得过度解释的下游状态 |
|---|---|---|---|
| 0.1 | discovery.001–003 | `PASS` | gov.002/media.001/ops.002 产品与 Release Oracle 仍 `DOWNSTREAM_NOT_RUN` |
| 0.2 | discovery.004 | `PASS_CURRENT_ARTIFACT_SCOPE` | Douyin Adapter Contract 仍 `DOWNSTREAM_NOT_RUN` |
| 0.5 | discovery.005 | `PASS_DESIGN_AND_SYNTHETIC_SCOPE` | media.003/rel.003 实现与 Release Oracle 仍 `DOWNSTREAM_NOT_RUN` |

三个旧 Phase verifier 均以 Review worktree、Owner 指定并行隔离模式、私有根/清理/evidence 条件重新运行；全量单测另行覆盖其核心和负向门禁。具体命令与机器结果以 `machine/evidence/stage_0/review/verification.json` 为准。

## Findings 与修复

| ID | 严重度 | 发现 | 处置 |
|---|---|---|---|
| `F-X2N-S00-R01` | High | 三个 Phase verifier 的 branch allowlist 不认识独立 Stage Review 分支，完整重验会失败 | 已加入精确 review branch，不接受任意分支 |
| `F-X2N-S00-R02` | High | Owner 要求每 Run 一个 Task，但 Pursuing Goal/Taskpack/Operations 被放宽为每 Run 一个 Phase；历史 P01 也一次执行了 discovery.001–003 | 登记 `CE-X2N-20260720-S00-REVIEW`；保留历史、逐 Task 重验证据，并收紧未来机器门禁；Stage Review 是不执行新 Task 的专用例外 |
| `F-X2N-S00-R03` | Medium | PRD/Release 残留 `MediaCrawler Adapter` 关闭占位与“外部安装”措辞，可能被误解为未来授权 | 已删除产品 Feature Flag，并改为永久零安装/零执行的历史审计边界 |
| `F-X2N-S00-R04` | Medium | Review 与最新 `origin/main` 的母仓库索引发生单一文本冲突 | 已保留上游 Stock Skill 行与 x2n 行；没有修改其他项目内容 |
| `F-X2N-S00-R05` | Blocker | 临时源码 remote 凭据形态事件已隔离，但凭据是否失效仍未知 | 本地可做项已完成；保持 `G0_BLOCKED_OWNER_ACTION` |

## 竞品与当前政策复核

- `ShilongLee/Crawler` 当前默认分支仍指向固定 Commit `765207310a90a81c615c0ba2df124543b424af89`；tree、177 个文件和三项关键文件 SHA-256 与 Phase 0.5 登记一致。
- 原竞品结论不变：可 clean-room 蒸馏平台隔离、统一能力词汇、有界批次和 Registry；Cookie/任意 URL 代理/代理轮换/指纹模拟/广域爬取/原始媒体持久化等模式全部拒绝。
- Chrome/CWS、Notion 与六平台一手来源已重新发现/核对；它们只支持“继续按最小权限、单一目的、显式授权、逐平台 Gate 研究”，不构成法律意见或平台授权。六平台仍全部为 `UNKNOWN_DISABLED`。

机器复核见 `machine/evidence/stage_0/review/external_revalidation.json`。每个平台实施开始时仍必须重新核验当时有效的条款、Scope、成本与技术路径。

## 下载路径问题的最终答案

原始 roadmap 和 taskpack ZIP 的完整内容与固定哈希已复核：它们讨论下载/Runtime 行为，但没有指定任何 macOS 绝对下载目录。Owner 后续指定的下载目的地通过 `X2N_DOWNLOAD_DESTINATION` 表示，项目根通过 `X2N_DATA_ROOT=${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion` 表示。下载父目录名称仅是存储路由，绝不授权同名上游安装、运行或接入。

## 恢复 G0 的唯一下一动作

Owner 对 `INC-X2N-S00-P05-001` 完成以下任一可验证动作：轮换相关凭据、以新的认证材料重新认证并废止旧材料，或提供旧材料已失效的证明。证据不得包含凭据值。随后新开 `STG.X2N.0.REVIEW.RESUME`，重新运行扫描、事件恢复门禁和 G0 判定；只有机器状态变为 `pass` 才能上传 Stage 0 或另行启动 Stage 1。

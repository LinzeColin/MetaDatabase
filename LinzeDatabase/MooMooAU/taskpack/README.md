# 任务包封套

`v1.0.0` 是用户提供的原始输入；其 ZIP/Manifest/Roadmap 哈希与验证器复现实验保存在
`SOURCE_PROVENANCE.json`。含公开定位冲突或低价值自生成报告的原始文件不留在可发布工作树中，
只保留哈希和本地审计提交；该本地历史永久禁止 push。

`v1.0.1` 是经 Owner 明确授权的基线保真修复。有效入口为：

- `00_READ_ME_FIRST.v1.0.1.md`
- `ROADMAP.v1.0.1.md`
- `PACKAGE_MANIFEST.v1.0.1.json`
- `CHANGELOG.md`

`v1.0.2` 是 Owner 选择方案 1 后建立的基线保真继任版本。它不改变 v1.0.1 的产品契约、
RQ/AC、task DAG、追踪矩阵、Kill Criteria 或不变量，只解决分阶段 evidence 验证与跨维度状态真源冲突。
它现在作为不可变控制前序保留。

`v1.0.3` 按 v1.0.2 Roadmap 的既定顺序完成 RMD-03。它只为 S3–S6 增加显式
`--cumulative-final` 最终树验证模式和离线只读 Workflow command matrix；无参数的历史阶段模式仍按
later-stage scope gate fail closed。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.3.md`
- `ROADMAP.v1.0.3.md`
- `PACKAGE_MANIFEST.v1.0.3.json`
- `SOURCE_PROVENANCE.v1.0.3.json`
- `CHANGELOG.md`

`v1.0.4` 按 v1.0.3 Roadmap 的既定顺序完成 RMD-04。它只增加唯一 fail-closed production
composition、加密 Sydney 调度水位、正式 protected adapters、合成端到端证据及相应 Workflow/机器契约；
不执行受保护 Oracle 或生产。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.4.md`
- `ROADMAP.v1.0.4.md`
- `PACKAGE_MANIFEST.v1.0.4.json`
- `SOURCE_PROVENANCE.v1.0.4.json`
- `CHANGELOG.md`

`v1.0.5` 按 v1.0.4 Roadmap 的既定顺序完成 RMD-05。它只关闭候选绑定本地 gate receipt、immutable
Git anchor、两个模型家族各 18 次不可变独立复审来源链及 Stage 6 v2 证据转换；不执行受保护 Oracle、
真实 Gmail/私有仓、生产、部署或发布。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.5.md`
- `ROADMAP.v1.0.5.md`
- `PACKAGE_MANIFEST.v1.0.5.json`
- `SOURCE_PROVENANCE.v1.0.5.json`
- `CHANGELOG.md`

`v1.0.6` 按 Owner 选择的方案 2 建立 RMD-06 云执行前置。Governance 继续私有，仅允许单仓只读
Deploy Key 通过 pinned checkout 消费；fork PR fail closed；clean depth-1 验证不依赖旧 RMD-05
Git object；历史累计 Job 与完整 Stage 7 CLI 分层验证 production composition；生产/Gmail/数据仓
Secret 仍为零。Stage 6 的不可变结构化 JSON 使用显式敏感模式门，其他代码/契约继续
`detect-secrets`；固定公开 SHA-256 仅做精确值排除。
第五轮 9 个 GitHub-hosted 非生产 Workflow 已全部成功并删除候选远端分支。此后增加 T0702
的 owner-dispatched、main/SHA/Environment-bound、六项 Secret 精确 allowlist 的 Raw-only 入口；
它不含 Gmail mutation、Parser、M3、Processed 或 Timeline 权限。Owner 已单独授权一次受控
main 交付和一次 budget-one protected dispatch，仅用于 T0702；真实 Beta 在 Environment/输入、
verified registry、私有仓和 GitHub App 完成独立核验前仍保持 `NOT_RUN`，且该交付不等于最终发布。
上述 pre-dispatch bootstrap 现已完成：no-reviewer/main-only Environment 仅含六项精确 Secret，
预算 1、唯一私有仓、单仓最小权限 App、cloud-only age identity、fresh capacity、Gmail OAuth 与
metadata-derived verified registry 均已核验。真实 metadata 观察所需的 exact partial-response
fields 与 RFC 8601 `header.i` 对齐修复也已加入。此后六个互异 exact-main SHA 各执行一次
workflow attempt 1；PR #92–#95 的公开安全诊断与 PR #96 的账本绑定复验把最新失败固定为
`GITHUB_APP_TOKEN / INSTALLATION_ZERO`。Raw/Gmail mutation/M3/Processed/Timeline/schedule
仍为 0，T0702/S7AC-002 继续 `BLOCKED`。
当前有效入口为：

- `00_READ_ME_FIRST.v1.0.6.md`
- `ROADMAP.v1.0.6.md`
- `PACKAGE_MANIFEST.v1.0.6.json`
- `SOURCE_PROVENANCE.v1.0.6.json`
- `CHANGELOG.md`

`PACKAGE_MANIFEST.v1.0.5.json` 是不可变直接前序，`PACKAGE_MANIFEST.v1.0.4.json`、
`PACKAGE_MANIFEST.v1.0.3.json` 与 `PACKAGE_MANIFEST.v1.0.2.json` 是不可变控制前序；
`PACKAGE_MANIFEST.v1.0.1.json` 与
`SOURCE_PROVENANCE.json` 是不可变历史基线。它们都不得用于解释当前跨维度交付状态；当前状态唯一真源
是 `../machine/status/latest.json`。

任务包自带的通用 Skill 未导入。本仓库只通过 pinned external checkout 消费共享 Governance，
不复制、分叉、submodule 或重建通用治理框架。

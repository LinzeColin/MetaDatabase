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
它不含 Gmail mutation、Parser、M3、Processed 或 Timeline 权限。Pre-dispatch bootstrap、最小权限
GitHub App installation、cloud-only age identity、fresh capacity、Gmail OAuth 与 verified registry
均已独立核验。完整 v2 账本区分 1 次 Secret 前 context 拒绝与 11 次 protected first attempt；
所有 protected attempt 均通过 Alpha 与 identity cleanup，前 10 次 Beta fail closed，最终
exact-main attempt 在 typed per-message metadata quarantine 修复后 PASS，且未使用 GitHub rerun。
公开安全结果为 verified-within-budget、Raw recovery 100%、非零 age-ciphertext-only private
namespace，以及 Gmail mutation/M3/Processed/Timeline/schedule 均为 0。T0702/S7AC-002 已通过；
这不是最终发布，当前 Owner 范围明确停在 M3 前。
当前有效入口为：

- `00_READ_ME_FIRST.v1.0.6.md`
- `ROADMAP.v1.0.6.md`
- `PACKAGE_MANIFEST.v1.0.6.json`
- `SOURCE_PROVENANCE.v1.0.6.json`
- `CHANGELOG.md`

`v1.0.7` 只补齐 T0703 的独立 protected M3 Budget-1 装配与 main-only Workflow，并将其绑定到
既有 T0702 PASS receipt、同树 gate 和当前 Run Contract。当前
`m3_authorized=false`，因此入口默认禁用且在读取八项 M3 Secret 前停止。真实 Gmail、私有数据仓、
Processed、M3、Timeline、Workflow dispatch 与发布效果均为零；T0702 既有 PASS 不变，Stage 7
仍未完成。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.7.md`
- `ROADMAP.v1.0.7.md`
- `PACKAGE_MANIFEST.v1.0.7.json`
- `SOURCE_PROVENANCE.v1.0.7.json`
- `CHANGELOG.md`

`v1.0.8` 在真实 T0702 PASS 后建立唯一 T0703 Run Contract，复用已验证的
`moomooau-beta` Environment/配置，并把缺少受保护分类或解析证据的路径固定为加密
`SAFE_DEFERRED` Processed。它只授权一份受控 main 交付和一次 first-attempt Budget-1 M3，
Raw 与 Processed 远端恢复后才允许精确 source-message Trash；不得进入 T0704。
当前有效入口为：

- `00_READ_ME_FIRST.v1.0.8.md`
- `ROADMAP.v1.0.8.md`
- `PACKAGE_MANIFEST.v1.0.8.json`
- `SOURCE_PROVENANCE.v1.0.8.json`
- `CHANGELOG.md`

`v1.0.9` 固化 T0703 首次 protected M3 的零观察副作用失败账本，禁止失败 head rerun，并将
T0702 已证明安全的逐消息 metadata quarantine 对齐到 M3。它只授权一份新 exact candidate main
交付和一次新候选 attempt-1 Budget-1 dispatch；broader failures 仍 fail closed，T0704 与最终发布
仍未授权。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.9.md`
- `ROADMAP.v1.0.9.md`
- `PACKAGE_MANIFEST.v1.0.9.json`
- `SOURCE_PROVENANCE.v1.0.9.json`
- `CHANGELOG.md`

`v1.0.10` 固化第二个不同 exact-main T0703 attempt 的 `GITHUB_APP_TOKEN` 零观察副作用失败。
Owner 随后确认 GitHub App 已安装并链接唯一 private 数据仓；M3 现与 T0702 一样仅公开封闭
`InstallationTokenFailureClass`。两个失败 head 均禁止 rerun/redispatch；只授权一份全新 exact
candidate main 交付和一次 attempt-1 Budget-1 dispatch，不进入 T0704。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.10.md`
- `ROADMAP.v1.0.10.md`
- `PACKAGE_MANIFEST.v1.0.10.json`
- `SOURCE_PROVENANCE.v1.0.10.json`
- `CHANGELOG.md`

`PACKAGE_MANIFEST.v1.0.9.json` 是不可变直接前序，`PACKAGE_MANIFEST.v1.0.8.json`、
`PACKAGE_MANIFEST.v1.0.7.json`、
`PACKAGE_MANIFEST.v1.0.6.json`、
`PACKAGE_MANIFEST.v1.0.4.json`、
`PACKAGE_MANIFEST.v1.0.3.json` 与 `PACKAGE_MANIFEST.v1.0.2.json` 是不可变控制前序；
`PACKAGE_MANIFEST.v1.0.1.json` 与
`SOURCE_PROVENANCE.json` 是不可变历史基线。它们都不得用于解释当前跨维度交付状态；当前状态唯一真源
是 `../machine/status/latest.json`。

任务包自带的通用 Skill 未导入。本仓库只通过 pinned external checkout 消费共享 Governance，
不复制、分叉、submodule 或重建通用治理框架。

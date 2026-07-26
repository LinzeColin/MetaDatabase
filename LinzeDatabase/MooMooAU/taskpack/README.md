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

`v1.0.11` 固化第三个不同 exact-main T0703 attempt 的 `RESPONSE_SCOPE_REJECTED` 零观察副作用
失败。固定官方 GitHub OpenAPI 后，token 响应的 scope 字段按可选回显处理；缺少 repository 回显时
必须通过有界 installation-token 仓库探测证明唯一目标 Repository ID，TTL 按有界 GitHub `Date`
校验。三个失败 head 均禁止 rerun/redispatch；只授权一份全新 exact candidate main 交付和一次
attempt-1 Budget-1 dispatch，不进入 T0704。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.11.md`
- `ROADMAP.v1.0.11.md`
- `PACKAGE_MANIFEST.v1.0.11.json`
- `SOURCE_PROVENANCE.v1.0.11.json`
- `CHANGELOG.md`

`v1.0.12` 固化第四个不同 exact-main T0703 attempt 在 `AGGREGATE_GATE` 的零观察副作用失败。
aggregate-only 输出没有证明更细线上根因；静态契约验证并修复了空 classification/parser registry
下隔离附件可能错误产生 `BLOCKED`、而不是显式 `SAFE_DEFERRED` 的顺序冲突。active parser
profile 的 hard quarantine 不变，并新增封闭 aggregate failure class。四个失败 head 均禁止
rerun/redispatch；只授权一份全新 exact candidate main 交付和一次 attempt-1 Budget-1 dispatch，
不进入 T0704。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.12.md`
- `ROADMAP.v1.0.12.md`
- `PACKAGE_MANIFEST.v1.0.12.json`
- `SOURCE_PROVENANCE.v1.0.12.json`
- `CHANGELOG.md`

`v1.0.13` 固化第五个不同 exact-main T0703 attempt 的封闭 `MUTATION_FAILED` 结果。后验聚合
只读证据证明一个可恢复 Processed lineage、processed-current 从 ZERO 到 ONE、private head
改变及 Gmail Trash aggregate 增加 1，但不证明 exact-source attribution 或更细 mutation
subreason。新 reconciliation 只选择唯一 verified、已在 Trash、且有该预先加密 pointer 的
source，重复 Raw/Processed remote recovery 与第二次验证，并以本次 Gmail mutation、Raw creation
和 Processed write 均为 0 的方式闭合未知结果。五个失败 head 均禁止 rerun/redispatch；只授权
一份新 exact candidate main 交付和一次 attempt-1 zero-write dispatch，不进入 T0704。当前有效
入口为：

- `00_READ_ME_FIRST.v1.0.13.md`
- `ROADMAP.v1.0.13.md`
- `PACKAGE_MANIFEST.v1.0.13.json`
- `SOURCE_PROVENANCE.v1.0.13.json`
- `CHANGELOG.md`

`v1.0.14` 固化第六个不同 exact-main T0703 attempt 的 `PROCESSED_PLAN` 零新增效果边界。
reconciliation 的 live Raw 正确观察 post-Trash label state，而既有 Processed snapshot 绑定首次
归档时的 pre-Trash label state。新候选只从 age-encrypted Processed document envelope 恢复规范
历史 label，重建同一 snapshot 并执行 Raw/Processed remote recovery 与第二次验证；没有 Gmail
或 private-repository 写入路径。六个失败 head 均禁止 rerun/redispatch；只授权一份新 exact
candidate main 交付和一次 attempt-1 zero-write dispatch，不进入 T0704。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.14.md`
- `ROADMAP.v1.0.14.md`
- `PACKAGE_MANIFEST.v1.0.14.json`
- `SOURCE_PROVENANCE.v1.0.14.json`
- `CHANGELOG.md`

`v1.0.15` 固化第七个不同 exact-main T0703 attempt-1 的受保护 PASS。authority、加密历史
label 零写入 reconciliation 与 identity cleanup 均通过；Raw+Processed recovery 100%，独立
前后核验确认当前运行 private head/tree/path counts 与 Gmail Trash aggregate 均无变化。
六次失败 ledger 保持不可变，成功 receipt 单独绑定；M3 authority 与数据面预算全部归零。
本包只允许一次受控证据交付，不触发 protected workflow，并停止在 T0704 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.15.md`
- `ROADMAP.v1.0.15.md`
- `PACKAGE_MANIFEST.v1.0.15.json`
- `SOURCE_PROVENANCE.v1.0.15.json`
- `CHANGELOG.md`

`v1.0.16` 在精确 T0703 PASS 后仅授权 T0704 protected Blue-Green attempt 1。候选复用同一
已恢复 Raw，对比 incumbent 1.0.0 与 candidate 2.0.0 的 SAFE_DEFERRED 输出，只追加并恢复一个
candidate Processed shadow，保持 processed-current 不变，并提交/恢复 Timeline snapshot 后替换
恰好一个可恢复 age-encrypted latest Timeline。旧 capacity snapshot 不能直接授权写入；job 先
只读实测 Repository-ID 绑定的完整 private tree 与 live Release，再保守重算容量。固定等待与
人工审批均为 0；rerun、Gmail mutation、schedule、T0705 和最终发布继续禁止。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.16.md`
- `ROADMAP.v1.0.16.md`
- `PACKAGE_MANIFEST.v1.0.16.json`
- `SOURCE_PROVENANCE.v1.0.16.json`
- `CHANGELOG.md`

`v1.0.17` 固化 T0704 首次 exact-main attempt 的 protected 失败：candidate Processed 与
Timeline snapshot 已远端恢复，processed-current 保持 byte-identical，但 fixed Release 最终
live asset 为 0 并留下 encrypted repair state。GitHub 官方 Asset API 允许 `200` 或 `302`，
原 adapter 只接受 `200`；修复只允许一次 GitHub release-asset CDN 跳转且不转发 Authorization。
失败 head 禁止 rerun/redispatch；只授权一个新 exact-main repair candidate 与一次 attempt-1
dispatch，candidate/snapshot 新写入 0，继续停止在 T0705 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.17.md`
- `ROADMAP.v1.0.17.md`
- `PACKAGE_MANIFEST.v1.0.17.json`
- `SOURCE_PROVENANCE.v1.0.17.json`
- `CHANGELOG.md`

`v1.0.18` 固化唯一新 exact-main T0704 redirect-recovery attempt-1 的受保护 PASS。
authority、Blue-Green 与 identity cleanup 均通过；既有 candidate/snapshot 被复用并远端恢复，
processed-current、Raw、Processed 与 Gmail 均无 repair 新效果，fixed Release 全程且最终恰好
一个非空 age-encrypted Timeline Asset。失败 head 保持冻结，成功/失败 head 均不得重跑。
T0704/S7AC-004 已关闭；本包只允许一次零 protected dispatch 的受控证据交付，并停止在
T0705 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.18.md`
- `ROADMAP.v1.0.18.md`
- `PACKAGE_MANIFEST.v1.0.18.json`
- `SOURCE_PROVENANCE.v1.0.18.json`
- `CHANGELOG.md`

`v1.0.19` 在精确 T0704 protected PASS 后只授权 T0705。候选复用现有
`moomooau-beta` 八个 protected input 和已安装 GitHub App，先刷新唯一私有仓实时容量，再执行
一条 verified-only Raw/Processed recovery、精确 Message Trash、单一 Timeline 与
checkpoint-last 路径。唯一 workflow_dispatch 必须称为 `SCHEDULE_REHEARSAL`，attempt 1、
rerun 0；PASS receipt 前 live schedule 关闭，之后只启用已提交 04:30 Australia/Sydney
schedule，并停在 T0706 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.19.md`
- `ROADMAP.v1.0.19.md`
- `PACKAGE_MANIFEST.v1.0.19.json`
- `SOURCE_PROVENANCE.v1.0.19.json`
- `CHANGELOG.md`

`v1.0.20` 固化 T0705 首次 exact-main protected GA 失败并冻结 head `eb7ad073…`。authority
与 identity cleanup PASS，但 GA 在 Gmail credential exchange 和数据面写入前 FAILED；独立聚合
核验确认 private commit 与 Raw/Processed/State/other path change 均为 0，Gmail mutation
endpoint 未到达，唯一 live Timeline Asset 仍为 1。修复只接受 paired empty protected
classification/parser registries 为显式 SAFE_DEFERRED，ACTIVE 行为不变。失败 head 永不
rerun/redispatch；只剩一个新 exact-main repair dispatch 与一个 receipt/schedule closure delivery，
继续停止在 T0706 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.20.md`
- `ROADMAP.v1.0.20.md`
- `PACKAGE_MANIFEST.v1.0.20.json`
- `SOURCE_PROVENANCE.v1.0.20.json`
- `CHANGELOG.md`

`v1.0.21` 固化 T0705 第二个不同 exact-main protected GA 失败并冻结 head `e38cd60e…`。
authority 与 identity cleanup PASS，GA FAILED；独立聚合核验确认没有新增 private commit、
checkpoint 未创建、唯一 latest Timeline 仍为 1。protected 输出没有披露 exact runtime
exception；同邮箱 T0703 metadata quarantine 回执与 GA 静态路径只支持高置信度
`MessageMetadataUnverifiable` 隔离缺口。修复只在 GA pre-Raw candidate loop 逐消息隔离该
typed failure，保留既有 pending replay，并保持 second verification fail closed 与
ACTIVE/SAFE_DEFERRED 行为不变。两个失败 head 永不 rerun/redispatch；只剩一个新 exact-main
repair dispatch 与一个 receipt/schedule closure delivery，继续停止在 T0706 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.21.md`
- `ROADMAP.v1.0.21.md`
- `PACKAGE_MANIFEST.v1.0.21.json`
- `SOURCE_PROVENANCE.v1.0.21.json`
- `CHANGELOG.md`

`v1.0.22` 固化 T0705 第三个不同 exact-main protected GA 失败并冻结 head `cc7c8af9…`。
authority 与 identity cleanup PASS，GA FAILED；独立后验确认没有新增 private commit、
checkpoint 未创建、active Moomoo candidate 仍在 Trash 外且加密 Timeline state 存在。
protected 输出没有披露 exact runtime exception；T0704 历史 label replay 与 GA 静态 root 构造
只支持高置信度“GA 未重放持久化 first-import label state”。修复只在既有 Processed 来源
envelope 构造时同时重放 timestamp 与 label state，保持 metadata quarantine、second
verification、ACTIVE/SAFE_DEFERRED、远端恢复与 checkpoint-last 不变。三个失败 head 永不
rerun/redispatch；只剩一个新 exact-main repair dispatch 与一个 receipt/schedule closure
delivery，继续停止在 T0706 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.22.md`
- `ROADMAP.v1.0.22.md`
- `PACKAGE_MANIFEST.v1.0.22.json`
- `SOURCE_PROVENANCE.v1.0.22.json`
- `CHANGELOG.md`

`v1.0.26` 直接继承不可变 v1.0.25，固化 T0705 第七个不同 exact-main protected GA
失败并冻结 head `2133673b…`。公开输出固定在 `FIRST_IMPORT_POINTER_FETCH`；只读连接仓核验
确认第七次零 commit，且两份 current pointer 的 Git tree/blob 与 exact raw media 都有效，但
其中一份 Contents JSON 内联表示解码长度与声明尺寸不一致。protected exception 未被读取，
精确线上根因保持 `UNKNOWN`。唯一新实现改为 bounded Contents metadata + exact raw media +
canonical Git blob SHA 绑定，漂移时失败关闭。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.26.md`
- `ROADMAP.v1.0.26.md`
- `PACKAGE_MANIFEST.v1.0.26.json`
- `SOURCE_PROVENANCE.v1.0.26.json`
- `CHANGELOG.md`

`v1.0.25` 直接继承不可变 v1.0.24，固化 T0705 第六个不同 exact-main protected GA
失败并冻结 head `d10f5086…`。公开输出只有 coarse `FIRST_IMPORT_RECOVERY`；只读 private
数据仓核验确认第六次零 commit、零路径变化，失败边界在 Raw recovery/classification 之后、
document-envelope 构造与任何 Processed write 之前，精确线上根因保持 `UNKNOWN`。唯一新实现
是固定枚举 first-import recovery 子阶段诊断并注入既有 remote reader，不接收或检查异常与
protected 值。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.25.md`
- `ROADMAP.v1.0.25.md`
- `PACKAGE_MANIFEST.v1.0.25.json`
- `SOURCE_PROVENANCE.v1.0.25.json`
- `CHANGELOG.md`

`v1.0.24` 直接继承不可变 v1.0.23，固化 T0705 第五个不同 exact-main protected GA
失败并冻结 head `64d88e91…`。公开输出只有 coarse `PROCESSED_PLAN`；只读 private 数据仓
核验确认第五次零 commit、零路径变化，精确线上根因保持 `UNKNOWN`。唯一新实现是固定枚举
Processed-plan 子阶段诊断，不接收或检查异常与 protected 值。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.24.md`
- `ROADMAP.v1.0.24.md`
- `PACKAGE_MANIFEST.v1.0.24.json`
- `SOURCE_PROVENANCE.v1.0.24.json`
- `CHANGELOG.md`

`v1.0.23` 固化 T0705 第四个不同 exact-main protected GA 失败并冻结 head `4c207ad5…`。
authority 与 identity cleanup PASS，GA FAILED；独立后验确认六个新增对象均为可恢复 age
ciphertext，覆盖 Raw、Processed 与 current pointer，而 Timeline snapshot/manifest、Timeline
state 与 checkpoint 均未改变。active Moomoo candidate 仍在 Trash 外；没有 exact
pre-dispatch baseline 或 protected mutation trace，因此不声称 Gmail mutation API 是否到达。
protected 输出未披露 exact runtime exception，精确 root cause 仍未知；本包只增加固定枚举的
last-entered phase 诊断，禁止异常文本、URL、标识符、计数、邮箱事实、私仓定位与 Secret 进入
公开结果。四个失败 head 永不 rerun/redispatch；只剩一个新 exact-main diagnostic dispatch 与
一个 receipt/schedule closure delivery，继续停止在 T0706 前。当前有效入口为：

- `00_READ_ME_FIRST.v1.0.23.md`
- `ROADMAP.v1.0.23.md`
- `PACKAGE_MANIFEST.v1.0.23.json`
- `SOURCE_PROVENANCE.v1.0.23.json`
- `CHANGELOG.md`

`PACKAGE_MANIFEST.v1.0.25.json` 是不可变直接前序，`PACKAGE_MANIFEST.v1.0.24.json`、
`PACKAGE_MANIFEST.v1.0.23.json`、
`PACKAGE_MANIFEST.v1.0.22.json`、
`PACKAGE_MANIFEST.v1.0.21.json`、
`PACKAGE_MANIFEST.v1.0.20.json`、
`PACKAGE_MANIFEST.v1.0.19.json`、
`PACKAGE_MANIFEST.v1.0.18.json`、
`PACKAGE_MANIFEST.v1.0.17.json`、
`PACKAGE_MANIFEST.v1.0.16.json`、
`PACKAGE_MANIFEST.v1.0.15.json`、
`PACKAGE_MANIFEST.v1.0.14.json`、
`PACKAGE_MANIFEST.v1.0.13.json`、
`PACKAGE_MANIFEST.v1.0.12.json`、
`PACKAGE_MANIFEST.v1.0.11.json`、
`PACKAGE_MANIFEST.v1.0.10.json`、
`PACKAGE_MANIFEST.v1.0.9.json`、
`PACKAGE_MANIFEST.v1.0.8.json`、
`PACKAGE_MANIFEST.v1.0.7.json`、
`PACKAGE_MANIFEST.v1.0.6.json`、
`PACKAGE_MANIFEST.v1.0.4.json`、
`PACKAGE_MANIFEST.v1.0.3.json` 与 `PACKAGE_MANIFEST.v1.0.2.json` 是不可变控制前序；
`PACKAGE_MANIFEST.v1.0.1.json` 与
`SOURCE_PROVENANCE.json` 是不可变历史基线。它们都不得用于解释当前跨维度交付状态；当前状态唯一真源
是 `../machine/status/latest.json`。

任务包自带的通用 Skill 未导入。本仓库只通过 pinned external checkout 消费共享 Governance，
不复制、分叉、submodule 或重建通用治理框架。

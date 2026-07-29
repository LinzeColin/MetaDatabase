# Owner Input Contract — Pre-Stage 00

Owner 输入只保存于 `X2N_DATA_ROOT/runtime/owner_input_contract.local.json`，权限必须为 `0600`，不得进入 Git。此文件只描述 Schema、默认值和后续解锁条件，不含真实路径、账号、Token、Cookie、Notion Page ID 或私有内容。

安全事件恢复证明与通用 Owner 输入严格分离：`INC-X2N-S00-P05-001` 只允许使用 `X2N_DATA_ROOT/runtime/owner_recovery_attestation.local.json`。该文件同样为 `0600`，只接受闭合枚举和布尔边界，不允许自由文本、凭据值、Remote URL、账号标识或本机路径。回执只授权独立 `STG.X2N.0.REVIEW.RESUME`，不会直接授予 G0、Stage 1 或上传权限；Owner 要求保留外部共享材料时，还必须同时满足 `POLICY.X2N.AUTH-ISOLATION.001` 的 x2n 零接触和完整 Resume 门禁。

## 已采用的可逆默认

| 主题 | 当前默认 | 后续解锁条件 |
|---|---|---|
| OS/硬件 | 运行时自动检测；先支持当前本机 | Stage 1 记录脱敏能力，不提交用户名/绝对路径 |
| 账号状态 | 六平台均 `NOT_RUN` | Owner 在专用 Chrome Profile 手工登录；不提供凭据值 |
| 数据规模 | `UNKNOWN`；仅允许每个已启用范围由 Owner 选定的 20 条直接 MVP 批次、1000 条 Job 分段 | 私有 Manifest 统计 |
| 首次同步 | 禁用；仅合成 Fixture | 对应平台政策、实现、精确 20 条 Manifest 与 Owner 直接 MVP 签核全部 PASS |
| 一级分类 | 仅 `Unclassified` | Owner 明确创建/导入分类；AI 只能从允许集选择 |
| Notion | Disabled | Owner 提供 Integration 与 Parent；Secret 进系统 Keychain |
| 云模型 | Disabled，月预算 0 | Owner 明确 Provider、数据边界与预算 |
| Gold Set | 仅合成 | Owner 私有 Gold Set，不进入仓库 |
| 临时媒体 | 成功立即删除；失败最多 24h | 不可放宽；放宽需新 PRD/Owner 决策 |

## 不能由默认值解锁的事项

- 真实账号读取、真实媒体下载、Notion 写入和云模型调用；
- 自动滚动、账号状态变更、访问控制/CAPTCHA 绕过；
- 未文档化接口、Cookie 导出/持久化、代理轮换或指纹模拟；
- 新一级分类、真实数据进入 Git、平台 CDN URL/原始媒体进入持久层。

缺失 Owner 值不会阻断合成开发，但对应 Feature 必须保持关闭并报告 `BLOCKED_USER_ACTION` 或 `UNKNOWN_DISABLED`，不得静默降级为授权。

## A005 双当前内容范围修订

`CE-X2N-20260729-S06-A005-XHS-TWO-CURRENT-BATCHES` 仅对 `TSK.x2n.assurance.005` 的直接 Owner MVP 生效。
对应 `owner_mvp_release_input` 的前两个有界范围必须依次写为
`xiaohongshu_current_content` 与 `xiaohongshu_current_content_second_batch`，transport 均为
`chrome_current_page_explicit`，每个范围恰有 20 个唯一、仅 SHA-256 的稳定内容标识；两个范围之间也必须
严格无交集。每条捕获都必须是 Owner 已显式打开的小红书详情页，relation 为 `saved_current`，不允许 category、
fallback、自动滚动、自动翻页、自动导航或后台批处理。

输入中不得放入原始内容 ID、页面 URL、CDN URL、媒体、账号、Cookie 或凭据。Companion 必须在
每条当前内容的首次 Canonical 写入前匹配其私有 Manifest；任何缺项、跨批重复或不匹配都以零写入 Fail Closed。
通用 `xiaohongshu_favorites` 与 `xiaohongshu_likes` 仍可用于 CI 合成验证，但不构成本次 A005 真实范围。

### A005 自动私有预备采集

Owner 不需要手工复制内容 ID、计算 Hash 或编辑 `input-template`。在尚未 arm、且不存在 release input/state
时，Side Panel 的两个“Prepare owner-selected 20-item MVP input”列表动作和两个小红书详情页专用批次按钮只允许
将已验证稳定内容标识的 SHA-256 写入 owner-only 的
`runtime/release/owner_mvp_manifest_enrollment.local.json`。该预备状态固定为四个范围：小红书当前内容批次 1、
小红书当前内容批次 2、抖音收藏、抖音喜欢；每个当前内容批次必须由 20 次独立详情页显式操作逐条加入，
两个批次的 Hash 不可重叠；列表必须一次精确 20 条。它不创建 Canonical Job/Content/Relation/Observation，
不保存标题、页面 URL、DOM、媒体或账号状态。

四个范围均精确 20 个不同 Hash 后，Companion 才可复用或创建经核验的 clean-room Douyin Sidecar，并在私有
Runtime 中原子冻结 `owner_mvp_release_input`。冻结后预备采集再也不能覆盖、追加或替换任何范围；后续 arm
和正式写入仍使用既有 Manifest 写前匹配门禁。预备集合不完整、重复、语义不匹配、私有文件/目录权限异常、
Sidecar 不可核验或已有 input/state 时，均不得创建或改变 release input。

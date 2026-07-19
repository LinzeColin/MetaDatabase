# Owner Input Contract — Pre-Stage 00

Owner 输入只保存于 `X2N_DATA_ROOT/runtime/owner_input_contract.local.json`，权限必须为 `0600`，不得进入 Git。此文件只描述 Schema、默认值和后续解锁条件，不含真实路径、账号、Token、Cookie、Notion Page ID 或私有内容。

安全事件恢复证明与通用 Owner 输入严格分离：`INC-X2N-S00-P05-001` 只允许使用 `X2N_DATA_ROOT/runtime/owner_recovery_attestation.local.json`。该文件同样为 `0600`，只接受闭合枚举和布尔边界，不允许自由文本、凭据值、Remote URL、账号标识或本机路径。回执只授权独立 `STG.X2N.0.REVIEW.RESUME`，不会直接授予 G0、Stage 1 或上传权限；Owner 要求保留外部共享材料时，还必须同时满足 `POLICY.X2N.AUTH-ISOLATION.001` 的 x2n 零接触和完整 Resume 门禁。

## 已采用的可逆默认

| 主题 | 当前默认 | 后续解锁条件 |
|---|---|---|
| OS/硬件 | 运行时自动检测；先支持当前本机 | Stage 1 记录脱敏能力，不提交用户名/绝对路径 |
| 账号状态 | 六平台均 `NOT_RUN` | Owner 在专用 Chrome Profile 手工登录；不提供凭据值 |
| 数据规模 | `UNKNOWN`；20 条 Canary、1000 条 Job 分段 | 私有 Manifest 统计 |
| 首次同步 | 禁用；仅合成 Fixture | 对应平台政策、实现、Canary Gate 全部 PASS |
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

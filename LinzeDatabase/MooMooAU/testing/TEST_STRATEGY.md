# Test Strategy

## 测试金字塔

1. **Unit：** Header/MIME、sender registry、认证对齐、endpoint guard、哈希、age、时间、状态机、脱敏。
2. **Contract：** Gmail API Fixture、GitHub REST、JSON Schema、Pandera、Release Asset、公开 Evidence。
3. **Property：** 重排 MIME、重复分页、重跑、并发、随机文件名、时区不变量。
4. **Fuzz：** RFC Header、MIME boundary、Base64url、文件 Magic、PDF/XLSX、Unicode。
5. **Integration：** 合成 Gmail → age → 测试私有远端 → 恢复 → M3 模拟 → Evidence。
6. **Protected Canary：** 少量真实已验证消息；无真实内容进入测试日志或模型。
7. **Load/Limit：** 大邮箱、最大分页、附件、并发、Git/LFS、内存和超时。
8. **Chaos/Recovery：** 主动注入平台和数据故障。
9. **Security/Model：** Abuse、权限、供应链、Codex Evals。

## Fixture 体系

- 所有公共 Fixture 均为合成或不可逆脱敏；
- 真实 Moomoo 结构只用于受保护 Canary，不进入仓库；
- Golden Fixture 包含 Daily、Monthly、FY、Contract Note、Dividend、Security、KYC、Marketing、Unknown Verified；
- Abuse Fixture 包含伪造品牌、thread 混合、octet-stream PDF、路径、宏、Prompt Injection、CSV 公式和 Zip Bomb；
- 时间 Fixture 覆盖 AEST/AEDT、DST 切换、周末和美国休市。

## 环境

| 环境 | 数据 | Secrets | 允许动作 |
|---|---|---|---|
| CI | 合成 | 无生产 Secret | 全部静态/单元/集成模拟 |
| Alpha | 合成 | 测试 Secret | 测试私有仓/模拟 Gmail |
| Beta | 少量真实 | 生产只读/写密文 Secret | Raw-only，M3=0 |
| Canary | 少量真实 | 生产 Secret | Mutation Budget=1 |
| GA | 全量已验证 | 生产 Secret | 受 Gate 全流程 |

## 发布门

任何 P0 Requirement 的 Acceptance 不通过即失败；不得通过平均分掩盖零容忍指标。测试证据必须含环境、输入 Fixture ID、代码/容器版本、Oracle、阈值、结果和产物摘要。

# Build / Buy / Borrow 决策

| 能力 | 决策 | 理由 |
|---|---|---|
| Gmail API 客户端 | Borrow 官方 SDK/REST | 不重造 OAuth、分页和 API 模型；外层加 Endpoint Guard |
| 全量/增量备份模式 | Borrow GYB 思路 | 复用 RAW、History、Full Sync；不采用本地存储 |
| 邮件规则/去重 | Borrow Paperless 思路 | 复用规则、状态、未知隔离；不部署服务 |
| Product Taskpack | Build Skill，Borrow Spec Kit/BMAD 模式 | 用户要求独有双平面、Oracle、Evidence、Kill 和双流水线 |
| age 加密 | Buy/Borrow 官方 age 二进制 | 成熟、流式、简单；不自研密码学 |
| Secret 存储 | Buy GitHub Environment Secrets | 与 Actions 集成，减少额外云服务 |
| 私有数据仓 | Use 已有唯一私有 GitHub 仓 | 用户硬约束，不引入第二仓/对象存储 |
| Metadata Catalog | Build 轻量文件契约 | OpenMetadata/DataHub 对本项目过重 |
| Lineage | Build 精简模型，Borrow OpenLineage 语义 | 无需常驻服务 |
| Data Validation | Borrow JSON Schema/Pandera | 可执行、生态成熟 |
| Supply-chain Evidence | Borrow in-toto/Attestation 思路 | 自定义脱敏 Evidence 适应私有数据 |
| Timeline | Build 确定性 Renderer | 用户给出具体视觉和单资产要求 |
| M3 State Machine | Build | 关系到零误伤和远端恢复，必须项目特定 |
| Codex Automation | Use 普通产品功能 | 不开发特殊 Auto、SDK 或回调 |
| 本地 Scheduler | Reject | 用户禁止且增加设备负担 |
| Moomoo Portal Scraper | Reject | H2 明确不在范围 |
| Paperless/OpenMetadata 全平台 | Reject | 运行和治理成本过高 |

## 复用优先级

1. 标准协议/API/加密库直接复用；
2. 成熟项目的状态机、备份和治理模式抽象复用；
3. 与用户硬约束直接相关的分类、M3、Timeline 和公开脱敏自行实现；
4. 不为“完整平台感”部署数据库、服务、队列、搜索或第二数据仓。

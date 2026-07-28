# xhs-douyin-2notion Agent Contract

继承母仓库根目录 `AGENTS.md`，冲突时 Fail Closed。

## 唯一身份

- 母仓库：`LinzeColin/MetaDatabase`
- 子项目：`xhs-douyin-2notion/`
- 项目代号：`x2n`
- 当前产品设计版本：`v0.0.0.1`
- 治理框架：只消费 `LinzeColin/Governance`，不得复制、分叉或通过 submodule 引入。

## 永久边界

- 产品边界是个人内容知识治理，不是通用爬虫。
- 终态平台范围是小红书、抖音、哔哩哔哩、快手、微博和淘宝；项目名不构成范围上限。每个平台独立 Policy/Auth/Technical Gate 与 Kill Switch，未知即禁用。
- 活跃 SQLite Canonical Store 是逻辑真相源；Markdown 与 Notion 是可重建 Sink。SQLite 快照、导出件、运行时快照和证据回执只有经批准客户端写入 Private-MetaDatabase 并验证回执后才算耐久。
- Chrome 是交互面，Local Companion 是长任务与持久化执行面。
- 不持久化平台媒体 CDN URL、凭据、Cookie、浏览器状态或原始媒体。
- AI 不得创建一级分类；无用户分类时只能进入 `Unclassified` 或等待确认。
- 不自动滚动，不改变平台账号状态，不绕过 CAPTCHA、访问控制或平台限制。
- 受限许可证或通用爬虫项目只可作不可执行审计参考；不得安装、运行、包装为产品 Adapter 或接收其输出，除非新的 Owner Change Event 与独立 License/Policy Run 明确授权。
- 仓库只允许代码、契约、合成 Fixture 和脱敏紧凑证据；真实运行数据始终在仓库外。
- 代码和数据均为专有，保留所有权利；Public 不等于开源授权。
- 外部共享 fine-grained GitHub Token 不属于 x2n 的凭据处置权限：任何 x2n agent 永不读取、
  导出、显示或持久化 Token 值，永不修改 auth/config/Credential Helper，也永不删除、撤销或轮换
  Token。它在项目外存在或被 Owner 接受的暴露风险不是 x2n Gate blocker。显式授权的 Task 可让
  现有 authenticated session 仅经 `private_db_client.py` 执行 in-scope x2n 操作；不得扩大用途。
  若 Token 值意外进入 x2n scope，只报告并隔离项目制品，不触碰 Token 本身。

## 数据根目录契约

- 仓库内只使用逻辑名 `X2N_DATA_ROOT`，不得提交用户名或本机绝对路径。
- 原始 taskpack 未指定本机绝对下载路径；Owner 指定的下载目的地只以逻辑名 `X2N_DOWNLOAD_DESTINATION` 表示。
- `X2N_DATA_ROOT` 必须解析为 `${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion`；Runtime 与全部下载共用这个隔离命名空间，实际绝对值只在私有 marker。该目录仅是下载、执行与活跃 SQLite working copy 的本机易失工作区，不是耐久数据目的地。
- 长期/业务/运行时数据的唯一耐久目的地是 `LinzeColin/Private-Database` 的 `Private-MetaDatabase` area，项目归属用 manifest 的 `domain=xhs-douyin-2notion` 表示；只允许通过 `KMOS/KMDatabase/machine/tools/private_db_client.py` 的 `ingest/get/list/verify` 访问，禁止 clone Private-Database、直接 Git 写入或绕过客户端。
- 客户端拒绝直接上传 `.sqlite/.db` 运行库，单对象硬上限 95 MiB。耐久 SQLite 必须先生成一致性快照，再封装为非运行时归档，按不超过 90 MiB 的内容寻址分片写入；项目 restore manifest 必须过滤精确 domain、校验每片 SHA-256、重组并通过 SQLite integrity，禁止靠改名绕过红线。
- `private_db_client.py verify` 是 area-global advisory，不能作为 x2n durability Gate；它的输出必须
  redacted，其他 domain 缺失不阻断 x2n，也不得在 x2n 日志/证据回显路径。只有精确
  `domain=xhs-douyin-2notion` 行逐对象 `get`/hash/reassemble/integrity 全通过才算耐久。
- Canonical transaction 在本机 SQLite 提交后仍可作为活跃逻辑事实继续恢复；在对应不可变快照、manifest 与精确 domain receipt 通过前，耐久状态必须是 `durability_pending`，不得声称已备份或已耐久。
- 目标 OS backup 策略是整个 `X2N_DATA_ROOT` 排除于 Time Machine；当前仍是历史逐子目录状态，
  只有 `TSK.x2n.uxops.005` 可在 Owner 明确授权后执行并复验整根排除。任何本地 backup 都不算耐久。
- x2n 禁止 Private-Database `delete`；删除只作用于 active SQLite/派生 Sink，并用单调
  `deletion_epoch` 与逻辑 tombstone 防止历史快照恢复复活。durable hard erase 必须报告
  `UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED`，不得以本地 wipe 冒充。
- 允许的一级目录仅为 `downloads/`、`runtime/` 和私有 marker/系统保护文件。
- 下载目的地已有同级条目只允许不回显名称的聚合数量/元数据指纹审计；不得读取内容、导入、移动、链接、修改或删除。迁移必须由独立 Run Contract 授权。

## 执行门禁

- 严格按 `docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml` 的 Stage 0–6 DAG 推进。
- 每个普通 Run 最多执行一个 DAG Task 及其 Acceptance；不得顺带执行同 Phase 的下一 Task。Stage Review 是不执行新 Task 的专用 Run。
- 每个 Stage 完成后，先做全 Stage Review，修复全部阻断项并重跑验收，才允许 push 整个 Stage。
- Phase 中间不得 push；本地 commit 只代表可恢复检查点，不代表 Stage Gate 通过。
- 任何安全、政策、证据、验收、恢复或回滚门禁为 UNKNOWN/NOT_RUN 时，不得声称 PASS。
- 真实账号、Notion 写入、模型调用和媒体处理须等待对应 DAG 授权与显式 Gate。

## 长期外部开发隔离

- 绝不修改、恢复、stash、暂存或提交 MetaDatabase 主树及其他子项目的改动。
- Verifier 默认仍要求主树 clean；Owner 明确要求并行时，只可显式使用 `--allow-external-main-dirty`。
- 该模式必须证明外部 dirty paths 与 `xhs-douyin-2notion/` 零重叠、当前 worktree changed scope 仅限项目目录或根 README 单一项目索引改名、主树仍在 `main`；否则 FAIL。
- Evidence 只记录外部 dirty path 数量与 overlap `0`，不得记录其他项目路径、diff 或内容。

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
- SQLite Canonical Store 是唯一真相源；Markdown 与 Notion 是可重建 Sink。
- Chrome 是交互面，Local Companion 是长任务与持久化执行面。
- 不持久化平台媒体 CDN URL、凭据、Cookie、浏览器状态或原始媒体。
- AI 不得创建一级分类；无用户分类时只能进入 `Unclassified` 或等待确认。
- 不自动滚动，不改变平台账号状态，不绕过 CAPTCHA、访问控制或平台限制。
- 受限许可证或通用爬虫项目只可作不可执行审计参考；不得安装、运行、包装为产品 Adapter 或接收其输出，除非新的 Owner Change Event 与独立 License/Policy Run 明确授权。
- 仓库只允许代码、契约、合成 Fixture 和脱敏紧凑证据；真实运行数据始终在仓库外。
- 代码和数据均为专有，保留所有权利；Public 不等于开源授权。

## 数据根目录契约

- 仓库内只使用逻辑名 `X2N_DATA_ROOT`，不得提交用户名或本机绝对路径。
- 原始 taskpack 未指定本机绝对下载路径；Owner 指定的下载目的地只以逻辑名 `X2N_DOWNLOAD_DESTINATION` 表示。
- `X2N_DATA_ROOT` 必须解析为 `${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion`；Runtime 与全部下载共用这个隔离命名空间，实际绝对值只在私有 marker。
- 允许的一级目录仅为 `downloads/`、`runtime/` 和私有 marker/系统保护文件。
- 下载目的地已有同级条目只允许不回显名称的聚合数量/元数据指纹审计；不得读取内容、导入、移动、链接、修改或删除。迁移必须由独立 Run Contract 授权。

## 执行门禁

- 严格按 `docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml` 的 Stage 0–6 DAG 推进。
- 每个 Run 最多执行一个 Phase；不得顺带进入下一 Phase。
- 每个 Stage 完成后，先做全 Stage Review，修复全部阻断项并重跑验收，才允许 push 整个 Stage。
- Phase 中间不得 push；本地 commit 只代表可恢复检查点，不代表 Stage Gate 通过。
- 任何安全、政策、证据、验收、恢复或回滚门禁为 UNKNOWN/NOT_RUN 时，不得声称 PASS。
- 真实账号、Notion 写入、模型调用和媒体处理须等待对应 DAG 授权与显式 Gate。

## 长期外部开发隔离

- 绝不修改、恢复、stash、暂存或提交 MetaDatabase 主树及其他子项目的改动。
- Verifier 默认仍要求主树 clean；Owner 明确要求并行时，只可显式使用 `--allow-external-main-dirty`。
- 该模式必须证明外部 dirty paths 与 `xhs-douyin-2notion/` 零重叠、当前 worktree changed scope 仅限项目目录或根 README 单一项目索引改名、主树仍在 `main`；否则 FAIL。
- Evidence 只记录外部 dirty path 数量与 overlap `0`，不得记录其他项目路径、diff 或内容。

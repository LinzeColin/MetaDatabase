# Social Archive v0.0.0.5

免费、私有、跨平台的收藏、点赞与网页归档系统。日常操作采用 E2N 式一键保存；来源授权和 Notion/Obsidian/GitHub/Markdown 目的地连接状态可见；配置存在不等于已连接。默认归档 L0/L1/L3，L2 关闭。

本实现是新的 Social Archive 产品树。旧项目中的 SQLite/Outbox/幂等、数据语义、原子投影、解析器和 Fixture 只是候选资产，必须通过行为、许可证、迁移、恢复与回滚证明后才可吸收；否则使用本树预制实现。外部下载器、网页归档器和阅读器通过隔离 Sidecar/HTTP/CLI/本地文件复用。结构化长期事实同步到 Private-Database，对象字节进入 R2 并异地备份至 OCI；GitHub 私有 Markdown/Release 提供可验证副本。

开发、部署和验收以任务包 `09_ROADMAP/TASK_GRAPH.json` 与 `10_ACCEPTANCE/FROZEN_ACCEPTANCE_CONTRACT.json` 为准。

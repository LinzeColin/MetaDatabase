# Social Archive v0.0.0.40

免费、私有、跨平台的收藏、点赞与网页归档系统。日常操作采用 E2N 式一键保存；来源授权和 Notion/Obsidian/GitHub/Markdown 目的地连接状态可见；配置存在不等于已连接。默认归档 L0/L1/L3，L2 关闭。

本实现是新的 Social Archive 产品树。旧项目中的 SQLite/Outbox/幂等、数据语义、原子投影、解析器和 Fixture 只是候选资产，必须通过行为、许可证、迁移、恢复与回滚证明后才可吸收；否则使用本树预制实现。外部下载器、网页归档器和阅读器通过隔离 Sidecar/HTTP/CLI/本地文件复用。结构化长期事实同步到 Private-Database，对象字节进入 R2 并异地备份至 OCI；GitHub 私有 Markdown/Release 提供可验证副本。

开发、部署和验收以任务包 `09_ROADMAP/TASK_GRAPH.json` 与 `10_ACCEPTANCE/FROZEN_ACCEPTANCE_CONTRACT.json` 为准。

## 零技术门槛使用

1. 打开 `https://social-archive.linzezhang.com`，点击“安装浏览器插件”。
2. 下载 ZIP 后双击解压；在 Chrome 地址栏打开 `chrome://extensions`。
3. 打开“开发者模式”，点击“加载已解压的扩展程序”，选择刚解压的文件夹。
4. 返回网站并刷新；页面显示“已检测到插件”后点击连接，不需要填写服务器、端口或 Token。
5. 打开任意本人有权访问的网页，点击“保存到我的档案馆”；随后可在“资料库”按标题或正文检索。

Chrome Web Store 上架前，网站内的中文安装向导和受 Cloudflare Access 保护的官方 ZIP 是唯一安装入口。插件不托管密码、Cookie 或浏览器登录状态。插件暂时不可用时，首页“粘贴链接，立即保存”仍可使用。

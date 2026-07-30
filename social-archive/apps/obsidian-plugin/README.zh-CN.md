# Social Archive Obsidian 插件

1. 将本目录中的 `manifest.json`、`main.js`、`styles.css` 放入 Vault 的 `.obsidian/plugins/social-archive-bridge/`。
2. 在 Obsidian 中启用插件。
3. 打开插件设置，复制连接令牌。
4. 在 Social Archive 扩展的“连接本机 Obsidian”中粘贴令牌并点击连接。

插件只在 Obsidian 打开时监听固定的 `127.0.0.1:27123`，只允许带令牌、`text/markdown` 的写入，并将所有文件限制在 Vault 内安全的 `Social Archive/` 子目录。单次写入上限为 20 MiB；同路径同内容返回 `noop`，不会重复改写文件。它不会安装后台服务，也不使用 launchd。

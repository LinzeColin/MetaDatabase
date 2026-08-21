# Harness UI

Harness UI 使用 AgentDatabase 既有的唯一产品版本线，不再区分 stable/community 私有版本。

- macOS Apple Silicon：下载 DMG 或 ZIP。
- Windows x64/ARM64：下载对应安装器或便携 ZIP。
- macOS 菜单栏和 Windows 托盘菜单均提供“检查并下载更新…”入口。
- Kimi Code 与 DSH 读取同一个 `catalog.json` 和 `state.json`；素材目录更新后会刷新目录代次，两端自动读取新目录并保持选择状态一致。
- 用户图片、SMB 凭据、选择状态和个性化文件均保存在安装包之外。
- macOS 构建使用固定的 `com.linzecolin.harnessui` 本地代码要求，更新时保持同一权限身份。

旧的 `harness-ui-community-v*` 已停用，不再发布新版本。

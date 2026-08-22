# Kimi Code Desktop

此桌面 App 的版本号与内置的 MoonshotAI/Kimi Code 官方版本完全一致，不使用独立包装版本号。

- macOS：按机器架构下载 `mac-arm64.dmg` 或 `mac-x64.dmg`。
- Windows：按机器架构下载 `win-x64.exe` 或 `win-arm64.exe`；便携版使用对应 ZIP。
- App 菜单中的“检查更新…”会读取本仓库的唯一正式版本线 `kimi-code-desktop-v*`。
- 同一官方版本内覆盖发布的桌面维护修复由内部发行修订清单识别；它不会改变可见版本号，但仍会在“检查更新…”中显示为可下载的维护更新。
- 更新只替换 App 本体；`~/.kimi-code`、`~/.harness-ui`、登录、会话、配置、皮肤、素材与外置图标不会进入安装包，也不会被替换。
- 无 Apple 资质的 macOS 构建仍使用固定的 `com.electron.kimi-code` 本地代码要求，避免每次更新都因临时代码身份变化而重新建立 TCC 权限身份。

旧的 `kimi-code-desktop-community-v*` 是已停用的包装版本线，不再参与更新判断。

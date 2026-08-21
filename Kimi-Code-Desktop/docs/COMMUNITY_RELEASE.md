# Kimi Code Desktop 零成本社区版

这是公开、可复现、**未使用受信任发行证书**的 prerelease。预算为 `$0`；它不是 Apple Developer ID
或 Windows Authenticode 签名版，也未通过 Apple 公证。

下载页：[Kimi Code Desktop v0.2.0 Community](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-community-v0.2.0)

## 资产

- macOS Apple Silicon：文件名含 `NOT-NOTARIZED` 的 DMG 与 ZIP；
- Windows x64/arm64：文件名含 `UNSIGNED` 的安装器与便携 ZIP。

macOS Gatekeeper 或 Windows SmartScreen 可能警告或阻止这些下载资产。不要关闭系统安全功能。Mac 用户优先让
Agent clone 公开仓后执行安装脚本；脚本使用系统自带 `curl` 获取固定版本的 GitHub Release ZIP，不要求安装
Node、Swift 或 Xcode：

```bash
cd MetaDatabase/Kimi-Code-Desktop
bash scripts/install-community-macos.sh
```

脚本只下载并复制到 `~/Applications/Kimi Code.app`，不会启动、关闭或重启任何应用；更新既有 App 前要求它已经正常退出，并先保留可恢复的旧版本。
它不会修改 Gatekeeper 设置或移除 quarantine 属性。

## 数据边界

Release 不包含 Kimi OAuth、API Key、会话、日志、用户配置或 Harness 图片。内置 Kimi CLI 来自 Moonshot AI
官方公开 Release；本项目仍是非官方桌面壳。

未来若取得真实 Developer ID 与 Authenticode 身份，`signed release` 工作流仍可独立发布受信任版本。

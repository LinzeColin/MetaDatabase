# Harness UI 零成本社区版

这是公开、可复现、**未使用受信任发行证书**的 prerelease。预算为 `$0`；macOS App 仅做本机 ad-hoc
签名、没有 Apple 公证，Windows EXE 没有 Authenticode 签名。

下载页：[Harness UI v0.1.0 Community](https://github.com/LinzeColin/MetaDatabase/releases/tag/harness-ui-community-v0.1.0)

## 资产

- macOS Apple Silicon：文件名含 `NOT-NOTARIZED` 的 DMG 与 ZIP；
- Windows x64/arm64：文件名含 `UNSIGNED` 的安装器与便携 ZIP；
- DSH adapter source ZIP：只含适配源码、安装脚本与文档。

macOS Gatekeeper 或 Windows SmartScreen 可能警告或阻止下载资产。不要关闭系统安全功能。Mac 用户优先让
Agent clone 公开仓后执行安装脚本；脚本使用系统自带 `curl` 获取固定版本的 GitHub Release ZIP，不要求安装
Node、Swift 或 Xcode：

```bash
cd MetaDatabase/Harness-UI
bash scripts/install-community-macos.sh
```

脚本只下载并复制到 `~/Applications/Harness UI.app`，不会启动、关闭或重启任何应用；目标已存在时直接退出。
它不会修改 Gatekeeper 设置或移除 quarantine 属性。

## SMB 边界

Release 不包含任何皮肤图片、SMB 密码、生成任务或运行时缓存。图片仍从用户自己的
`smb://192.168.0.1/share/03_资料库/MetaData/HarnessUI/` 读取。

未来若取得真实 Developer ID 与 Authenticode 身份，`signed release` 工作流仍可独立发布受信任版本。

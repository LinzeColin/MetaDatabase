# Harness UI 正式签名

`Harness UI signed release` 工作流从 `main` 手动运行，并只在 macOS 与 Windows 都完成正式签名后创建
`harness-ui-v<version>` Release。

## 所需 GitHub Actions secrets

macOS：

- `MACOS_CERTIFICATE_P12`：Developer ID Application P12 的 Base64 文本；
- `MACOS_CERTIFICATE_PASSWORD`；
- `MACOS_SIGNING_IDENTITY`：例如 `Developer ID Application: Name (TEAMID)`；
- `APPLE_ID`；
- `APPLE_APP_SPECIFIC_PASSWORD`；
- `APPLE_TEAM_ID`。

Windows：

- `WINDOWS_CERTIFICATE_PFX`：Authenticode PFX 的 Base64 文本；
- `WINDOWS_CERTIFICATE_PASSWORD`。

Apple 侧必须是 Apple Developer Program 会员并持有 Developer ID 证书；单纯拥有开发经验或普通 Apple ID
不构成公开分发身份。Windows 侧同样必须先取得代码签名证书。工作流不会自动购买服务。

## 发布门实际验证

凭据检查先在轻量 guard job 完成，缺任何 secret 时不会分配 macOS/Windows 构建 runner。正式发布还要求：

- macOS App 与 DMG 都通过 `codesign`；两者均取得并附带可验证的 Apple 公证票据；
- Gatekeeper 接受 App 的执行策略和 DMG 的打开策略；
- Windows x64/arm64 主程序与安装器均通过 Authenticode 信任链和时间戳验证；
- DSH adapter ZIP 只包含适配源码、安装脚本和文档，不包含 Harness 图片。

任一检查失败，`publish` job 都不会创建 GitHub Release。

## 发布动作

在 Actions 中选择 `Harness UI signed release`，填写与 `package.json` 相同的版本，并输入确认词
`RELEASE_SIGNED_HARNESS_UI`。工作流会生成：

- 已公证的 macOS arm64 DMG 与 ZIP；
- 已签名的 Windows x64/arm64 安装器与便携 ZIP；
- 不含图片的 DSH adapter ZIP。

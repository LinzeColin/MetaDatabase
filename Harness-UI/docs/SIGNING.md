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

## 发布动作

在 Actions 中选择 `Harness UI signed release`，填写与 `package.json` 相同的版本，并输入确认词
`RELEASE_SIGNED_HARNESS_UI`。工作流会生成：

- 已公证的 macOS arm64 DMG 与 ZIP；
- 已签名的 Windows x64/arm64 安装器与便携 ZIP；
- 不含图片的 DSH adapter ZIP。

# Kimi Code Desktop 正式签名

`Kimi Code Desktop signed release` 工作流只从 `main` 手动运行。它要求版本与
`package.json` 一致，并同时产出 macOS arm64、Windows x64 和 Windows arm64 的签名安装资产。

## Apple

“自己写代码/是开发者”不等于已经具备 Apple 的公开分发身份。正式 A 级发布需要：

1. Apple Developer Program 有效会员；
2. `Developer ID Application` 证书及私钥导出的 P12；
3. Apple ID 的 app-specific password；
4. Team ID。

在 MetaDatabase 的 GitHub Actions secrets 中配置：

- `MACOS_CERTIFICATE_P12`：P12 的 Base64 文本；
- `MACOS_CERTIFICATE_PASSWORD`；
- `APPLE_ID`；
- `APPLE_APP_SPECIFIC_PASSWORD`；
- `APPLE_TEAM_ID`。

官方入口：[Developer ID](https://developer.apple.com/developer-id/)。工作流会签名 App、提交 Apple 公证并由
Gatekeeper 评估；缺任何凭据都会在创建 Release 前退出。

## Windows

需要可导出私钥的 Authenticode 代码签名证书 PFX。配置：

- `WINDOWS_CERTIFICATE_PFX`：PFX 的 Base64 文本；
- `WINDOWS_CERTIFICATE_PASSWORD`。

工作流会签名应用和 NSIS 安装器。它不会购买证书或启用可能收费的云签名服务。

## 发布门实际验证

工作流不是只检查“文件生成了”。正式发布必须同时通过：

- Electron Builder 的 `forceCodeSigning`，无有效签名身份时直接失败；
- macOS App 的 `codesign`、Gatekeeper 与 stapled notarization ticket 验证；
- 已签名 DMG 的独立 Apple 公证、staple 与 Gatekeeper 打开策略验证；
- Windows x64/arm64 主程序及安装器的 Authenticode 信任链与时间戳验证。

任一检查失败，`publish` job 都不会创建 GitHub Release。ZIP 本身不做代码签名，但其内部 App/EXE
必须在打包前通过上述验证。

## 发布

在 Actions 中选择 `Kimi Code Desktop signed release`，从 `main` 填写版本，并输入确认词
`RELEASE_SIGNED_KIMI_CODE_DESKTOP`。只有所有平台成功后，工作流才创建
`kimi-code-desktop-v<version>` Release。

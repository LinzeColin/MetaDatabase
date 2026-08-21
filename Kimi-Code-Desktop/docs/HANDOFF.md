# Kimi Code Desktop 交接

## 当前目标

交付 macOS Apple Silicon、Windows x64 与 Windows arm64 的可复现桌面应用和 GitHub Release。

## 当前状态

- 桌面壳、Kimi 0.38.0 获取、Harness 适配、三平台构建配置和正式签名工作流已实现。
- macOS arm64 未签名候选 DMG/ZIP 已在本机完成构建；正式 Release 尚未发布。
- 现有 `~/Applications/Kimi Code.app` 保持运行且未被修改或重启。
- GitHub 当前没有 Apple/Windows 签名 secrets，发布门保持 `WAITING_SIGNING_CREDENTIAL`。

## 边界

- 源码与构建配置可公开。
- Kimi OAuth、API Key、会话、日志、用户配置和 Harness 图片不得进入仓库或 Release。
- 只使用官方 Kimi Code Release 二进制作为构建输入。

## 下一步

让 GitHub CI 在干净 macOS/Windows runner 完成构建；配置签名 secrets 后从 `main` 运行正式 Release 工作流。

补充跟 Prompt（22 个汉字）：`请收口当前皮肤任务并输出可迁移交接勿重启应用`

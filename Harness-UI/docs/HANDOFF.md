# Harness UI 迁移交接

## 当前目标

交付 macOS Apple Silicon、Windows x64/arm64 的 Harness UI 控制器，以及 Kimi、DSH 两个宿主适配器。

## 数据合同

- SMB 真源：`smb://192.168.0.1/share/03_资料库/MetaData/HarnessUI/`
- Windows UNC：`\\192.168.0.1\share\03_资料库\MetaData\HarnessUI`
- Runtime 结构：`<游戏中文>/<角色ID>/skins/<变体>/{light.png,dark.png,meta.json}`
- 图片只读留在 NAS；每台电脑只存配置、状态和小型目录索引。

## 当前状态

- 共享目录/状态协议、网页角色库、macOS AppKit 控制器、Windows WinForms 控制器、Kimi/DSH 适配与发布工作流已实现。
- 本机 Node 测试通过；本机 Command Line Tools 的 compiler/SDK 版本错配，Swift 与 Windows 原生构建交由干净 CI runner。
- 尚未发布正式 Release，签名门为 `WAITING_SIGNING_CREDENTIAL`。
- 现有 Harness 生成任务和 `progress.py --watch` 未被停止。
- Kimi、DSH 和 Harness 现有应用均未重启。

## 禁止迁移

- 生成任务包、验收台账原文、私有路径、API Key、缓存和图片。
- 现有 `~/.harness-ui` 的 7GB runtime 目录。
- AgentDatabase HarnessUI 中与 runtime 无关的生成/研究流水线。

## 下一步

通过 GitHub CI 修完原生编译差异；配置 Apple/Windows 签名 secrets 后从 `main` 运行正式 Release 工作流。

补充跟 Prompt（22 个汉字）：`请收口当前皮肤任务并输出可迁移交接勿重启应用`

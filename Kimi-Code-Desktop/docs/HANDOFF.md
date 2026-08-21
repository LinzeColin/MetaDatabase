# Kimi Code Desktop 交接

## 当前目标

交付 macOS Apple Silicon、Windows x64 与 Windows arm64 的可复现桌面应用和 GitHub Release。

## 当前状态

- 桌面壳、Kimi 0.38.0 获取、Harness 适配、三平台构建配置和正式签名工作流已实现。
- PR #309 已合并到公开仓 `MetaDatabase/main`；合并提交后的全部仓库检查已通过。
- 干净 GitHub runner 已实际生成 macOS arm64 DMG/ZIP，以及 Windows x64/arm64 NSIS EXE/ZIP 候选件；主分支跨平台验收 run 为 `32479000586`。
- 正式工作流要求有效签名身份，并显式验证 Mac App/DMG 的签名、公证票据与 Gatekeeper，以及 Windows x64/arm64 主程序和安装器的 Authenticode 信任链与时间戳。
- 正式 Release 尚未发布；候选件未冒充已签名制品。
- 现有 `~/Applications/Kimi Code.app` 保持运行且未被修改或重启。
- 截至 2026-08-21，GitHub 没有 Apple/Windows 签名 secrets，本机也没有有效 codesigning identity；发布门保持 `WAITING_SIGNING_CREDENTIAL`。

## 边界

- 源码与构建配置可公开。
- Kimi OAuth、API Key、会话、日志、用户配置和 Harness 图片不得进入仓库或 Release。
- 只使用官方 Kimi Code Release 二进制作为构建输入。

## 下一步

安全配置签名 secrets 后，从 `main` 运行 `Kimi Code Desktop signed release`；只有签名、公证、时间戳验证和六个 Release 资产全部通过才可收口。

补充跟 Prompt（22 个汉字）：`请收口当前皮肤任务并输出可迁移交接勿重启应用`

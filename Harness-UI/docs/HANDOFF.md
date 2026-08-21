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
- PR #309 已合并到公开仓 `MetaDatabase/main`；合并提交后的全部仓库检查已通过。
- 干净 GitHub runner 已通过 Swift 测试并构建 macOS arm64 控制器，也已构建 Windows x64/arm64 自包含程序和 Inno 安装器；主分支跨平台验收 run 为 `32479000586`。
- 正式工作流显式验证 Mac App/DMG 的签名、公证票据与 Gatekeeper，以及 Windows x64/arm64 主程序和安装器的 Authenticode 信任链与时间戳。
- PR #310 已把上述发布门合并到 `main`；合并后的跨平台 run `32481584316` 和三条仓库治理工作流全部通过。
- 正式工作流演练 run `32482237541` 已通过 main/version/确认词门，并准确停在缺失签名 secrets；macOS、Windows、publish jobs 全部跳过，未创建 Release。
- 尚未发布正式 Release，签名门为 `WAITING_SIGNING_CREDENTIAL`。
- 截至 2026-08-21，GitHub 没有 Apple/Windows 签名 secrets，本机也没有有效 codesigning identity。
- 现有 Harness 生成任务和 `progress.py --watch` 未被停止。
- Kimi、DSH 和 Harness 现有应用均未重启。
- 2026-08-22 Owner 明确要求发行成本恒为 `$0`。Apple Developer ID/公证因此不再是本轮可执行路径；现有 signed workflow 保留但不冒充已完成。
- 零成本 community workflow 已新增，固定发布 `harness-ui-community-v0.1.0` prerelease；macOS 文件名标记 `NOT-NOTARIZED`，Windows 标记 `UNSIGNED`，DSH 仅发布源码包。
- `scripts/install-community-macos.sh` 供 Agent clone 后安装固定版本 ZIP；不需要 Node、Swift 或 Xcode，只复制、不启动、不重启，也不修改 Gatekeeper 设置。

## 禁止迁移

- 生成任务包、验收台账原文、私有路径、API Key、缓存和图片。
- 现有 `~/.harness-ui` 的 7GB runtime 目录。
- AgentDatabase HarnessUI 中与 runtime 无关的生成/研究流水线。

## 下一步

先合并并运行 `$0 community` workflow，核验七个明确标记安全状态的 Release 资产，再在新 Mac 通过 Agent 安装脚本连接既有 SMB。未来若 Owner 改变预算，再按 `docs/SIGNING.md` 恢复 signed release。

补充跟 Prompt（22 个汉字）：`请收口当前皮肤任务并输出可迁移交接勿重启应用`

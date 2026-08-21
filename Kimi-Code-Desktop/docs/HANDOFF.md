# Kimi Code Desktop 交接

## 当前目标

交付 macOS Apple Silicon、Windows x64 与 Windows arm64 的可复现桌面应用和 GitHub Release。

## 当前状态

- 桌面壳、Kimi 0.38.0 获取、Harness 适配、三平台构建配置和正式签名工作流已实现。
- PR #309 已合并到公开仓 `MetaDatabase/main`；合并提交后的全部仓库检查已通过。
- 干净 GitHub runner 已实际生成 macOS arm64 DMG/ZIP，以及 Windows x64/arm64 NSIS EXE/ZIP 候选件；主分支跨平台验收 run 为 `32479000586`。
- 正式工作流要求有效签名身份，并显式验证 Mac App/DMG 的签名、公证票据与 Gatekeeper，以及 Windows x64/arm64 主程序和安装器的 Authenticode 信任链与时间戳。
- PR #310 已把上述发布门合并到 `main`；合并后的跨平台 run `32481584316` 和三条仓库治理工作流全部通过。
- 正式工作流演练 run `32482228994` 已通过 main/version/确认词门，并准确停在缺失签名 secrets；macOS、Windows、publish jobs 全部跳过，未创建 Release。
- 正式 Release 尚未发布；候选件未冒充已签名制品。
- 现有 `~/Applications/Kimi Code.app` 保持运行且未被修改或重启。
- 截至 2026-08-21，GitHub 没有 Apple/Windows 签名 secrets，本机也没有有效 codesigning identity；发布门保持 `WAITING_SIGNING_CREDENTIAL`。
- 2026-08-22 Owner 明确要求发行成本恒为 `$0`。Apple Developer ID/公证因此不再是本轮可执行路径；现有 signed workflow 保留但不冒充已完成。
- 零成本 community workflow 已新增，固定发布 `kimi-code-desktop-community-v0.1.0` prerelease；macOS 文件名标记 `NOT-NOTARIZED`，Windows 标记 `UNSIGNED`。
- `scripts/install-community-macos.sh` 供 Agent clone 后安装固定版本 ZIP；只复制、不启动、不重启，且不修改 Gatekeeper 设置。
- PR #312 已合并；主分支发布 run `32513109964` 全部通过，并发布 [Kimi Code Desktop v0.1.0 Community](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-community-v0.1.0)。
- Release 为非草稿 prerelease，共 6 个资产：macOS arm64 DMG/ZIP，以及 Windows x64/arm64 安装器和便携 ZIP；全部安全状态已写进文件名。
- 已从公开 Release 下载 macOS ZIP，通过 Agent 安装脚本复制到隔离临时目录；App 版本为 `0.1.0`、主程序为 arm64，全程未启动应用，临时副本已移入废纸篓。

## 边界

- 源码与构建配置可公开。
- Kimi OAuth、API Key、会话、日志、用户配置和 Harness 图片不得进入仓库或 Release。
- 只使用官方 Kimi Code Release 二进制作为构建输入。

## 下一步

在新 Mac 上可直接下载 DMG/ZIP，或让任意 Agent clone 仓库后执行 `scripts/install-community-macos.sh`。Windows 按架构选择 `UNSIGNED-setup.exe` 或便携 ZIP。零成本 community 交付已完成；未来只有 Owner 改变预算时，才按 `docs/SIGNING.md` 恢复 signed release。

补充跟 Prompt（22 个汉字）：`请收口当前皮肤任务并输出可迁移交接勿重启应用`

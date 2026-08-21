# Kimi Code Desktop 交接

## 当前目标

让 Kimi Code Desktop 像普通 App 一样安装、退出、更新并保持完整磁盘访问身份；版本号严格跟随 MoonshotAI/Kimi Code 官方版本，不设置桌面壳私有版本。

## 当前状态（2026-08-22）

- 源码版本与内置 Kimi Code 均为 `0.38.0`；构建脚本直接从 `package.json` 读取版本并下载同版本官方平台资产。
- 唯一更新标签为 `kimi-code-desktop-v*`。旧 `kimi-code-desktop-community-v*` 已退出更新候选。
- App 启动 30 秒后及每 6 小时后台检查，也可从应用菜单手动检查、下载并在确认后退出安装。
- 每日 GitHub workflow 会读取官方最新版本；本仓库缺少同版本 Release 时自动构建 macOS arm64/x64 与 Windows x64/arm64 资产。
- macOS 本地构建固定使用 `com.electron.kimi-code` designated requirement，避免每次 ad-hoc 构建产生不同 TCC 代码身份；未来配置 Developer ID 时仍覆盖同一 Release，不建立新版本线。
- macOS 构建在 Electron 签名步骤后恢复 Moonshot 官方签名的内置 CLI；启动时仅把同版本 CLI 可执行文件迁移到稳定路径 `~/.kimi-code/bin/kimi`，旧 CLI 单独留在 `desktop-updates/cli-rollback/`，不修改同目录下任何账号、会话、配置、图标、皮肤或素材。
- macOS GUI 通过临时 launchd job 启动稳定路径中的官方 CLI，使后台 TCC 身份不再继承 ad-hoc Electron 壳；`Cmd+W`/关闭窗口仅关闭窗口，`Cmd+Q` 移除该 job 并正常结束 GUI、后台和定时器。该 job 不是登录启动项。
- 内置皮肤菜单读取 HarnessUI 唯一 `catalog/state`；catalog generation 变化时自动刷新素材并重建菜单。
- 更新只替换 App Bundle 与稳定路径中的官方 CLI 本体；`~/.kimi-code` 其余内容、`~/.harness-ui`、登录、会话、配置、素材和外置图标不进入安装包。
- 旧桌面版存在 `Application Support/kimi-shell` 时继续使用该 Electron profile；只有 fresh install 才创建 `Application Support/Kimi Code`。这保证旧账号界面、窗口与站点状态不会在升级时被分裂成第二套。
- 当前机器已完成旧身份迁移：稳定后台为 `~/.kimi-code/bin/kimi` 0.38.0，保留 Moonshot Developer ID；旧 0.37.2 CLI 已进入 `desktop-updates/cli-rollback/`，原 `kimi-shell` Electron profile、会话与个性化目录保持原位。

## 验证

- Node 回归：19/19 通过。
- shell、Python、Swift 语法与 workflow YAML 解析通过。
- 本机完整 SwiftPM 构建被本机 Command Line Tools 的 `PackageDescription` 链接环境阻断；完整 macOS/Windows 构建交给干净 GitHub runner。
- PR #317 与资产名修复 PR #318 已合并；正式发布 run `32527795001` 全部通过。
- [Kimi Code Desktop v0.38.0](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-v0.38.0) 已发布为正式 Release，共 8 个资产：macOS arm64/x64 DMG+ZIP、Windows x64/arm64 安装器+ZIP。
- 旧 private/community Releases 已保留历史资产并明确标记“已废止”。
- 本机运行态：Kimi backend `/api/v1/meta` 为 0.38.0；通过同一 backend 读取 Documents、列出 `/Volumes/share` 及读取 SMB 文件均成功。
- 生命周期：关窗后 GUI 与后台 PID 原样保留；重新打开窗口未重启后台；退出后 GUI、后台、58627 端口和临时 launchd job 全部消失，持续观察未自行拉起。
- HarnessUI：`catalog/state` 为 408 项、`smb+local`、generation 一致；Kimi 原生皮肤菜单同步显示 408 项和当前芭芭拉轮播状态。

## 剩余

- 合并保留官方 CLI 签名与 launchd responsibility 修复，用最终构建再次替换同一 `0.38.0` Release 资产，并从该 Release 覆盖安装一次；不得创建新版本号。

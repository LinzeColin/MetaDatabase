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
- “换下一张”改为共享服务原子动作 `POST /api/next`，快捷键恢复为 `Cmd/Ctrl+Shift+N`；轮询周期从 15 秒收敛到约 1 秒，与 DSH、Harness UI 使用同一状态。
- 更新只替换 App Bundle 与稳定路径中的官方 CLI 本体；`~/.kimi-code` 其余内容、`~/.harness-ui`、登录、会话、配置、素材和外置图标不进入安装包。
- 旧桌面版存在 `Application Support/kimi-shell` 时继续使用该 Electron profile；只有 fresh install 才创建 `Application Support/Kimi Code`。这保证旧账号界面、窗口与站点状态不会在升级时被分裂成第二套。
- 更新器会把正式安装位置写入 `desktop-updates/install-location.json`。即使 App 误从 rollback 副本启动，安装目标也回到正式 App；新回滚目录使用 `.app.rollback` 后缀，旧 `.app` 回滚副本在不运行时自动隔离，避免 LaunchServices 把备份注册成第二个 Kimi。
- 当前机器已完成旧身份迁移：稳定后台为 `~/.kimi-code/bin/kimi` 0.38.0，保留 Moonshot Developer ID；旧 0.37.2 CLI 已进入 `desktop-updates/cli-rollback/`，原 `kimi-shell` Electron profile、会话与个性化目录保持原位。

## 验证

- Node 回归：23/23 通过。
- shell、Python、Swift 语法与 workflow YAML 解析通过。
- 本机完整 SwiftPM 构建被本机 Command Line Tools 的 `PackageDescription` 链接环境阻断；完整 macOS/Windows 构建交给干净 GitHub runner。
- PR #317、#318、旧 profile 迁移 PR #320、稳定签名 CLI 与 launchd 后台 PR #321 均已合并；最终正式发布 run `32535596996` 全部通过。
- 统一皮肤、快捷键和 rollback 路径修复由 PR #323 交付；第一轮 CI run `32538867994` 的 Node、macOS Apple Silicon 与 Windows x64/arm64 候选全部通过。
- [Kimi Code Desktop v0.38.0](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-v0.38.0) 已发布为正式 Release，共 8 个资产：macOS arm64/x64 DMG+ZIP、Windows x64/arm64 安装器+ZIP。
- 旧 private/community Releases 已保留历史资产并明确标记“已废止”。
- 本机运行态：Kimi 前端与 backend 仍为 0.38.0；共享皮肤按钮和跨端状态已通过服务热修恢复。
- 生命周期：关窗后 GUI 与后台 PID 原样保留；重新打开窗口未重启后台；退出后 GUI、后台、58627 端口和临时 launchd job 全部消失，持续观察未自行拉起。
- HarnessUI：`catalog/state` 为 408 项、`smb+local`、generation 一致；Kimi 原生皮肤菜单同步显示 408 项和当前芭芭拉轮播状态。
- 2026-08-22 的界面验收调用由 macOS `coreservices.uiagent` 发起了额外启动请求；由于旧 rollback 中仍存在 `.app`，LaunchServices 最终启动了该副本。系统记录为正常退出/启动、无崩溃报告。此后对工作中的 Kimi 只用进程、端口和文件取证，不再用会自动启动 App 的界面读取调用。

## 剩余

- 以同一官方版本 `0.38.0` 覆盖 Release 资产；Kimi 正在承载工作线程，禁止为验收主动退出。新包只做发布和安全预备，待 Owner 自然退出后再激活正式安装路径并验收代码级快捷键。
- 其它电脑需从正式 Release 安装，并在该电脑上单独选择或授权其 SMB 位置；不要复制 OAuth、API Key、会话或 SMB 凭据。

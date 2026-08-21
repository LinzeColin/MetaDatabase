# Kimi Code Desktop 交接

## 当前目标

让 Kimi Code Desktop 像普通 App 一样安装、退出、更新并保持完整磁盘访问身份；版本号严格跟随 MoonshotAI/Kimi Code 官方版本，不设置桌面壳私有版本。

## 当前状态（2026-08-22）

- 源码版本与内置 Kimi Code 均为 `0.38.0`；构建脚本直接从 `package.json` 读取版本并下载同版本官方平台资产。
- 唯一更新标签为 `kimi-code-desktop-v*`。旧 `kimi-code-desktop-community-v*` 已退出更新候选。
- App 启动 30 秒后及每 6 小时后台检查，也可从应用菜单手动检查、下载并在确认后退出安装。
- 每日 GitHub workflow 会读取官方最新版本；本仓库缺少同版本 Release 时自动构建 macOS arm64/x64 与 Windows x64/arm64 资产。
- macOS 本地构建固定使用 `com.electron.kimi-code` designated requirement，避免每次 ad-hoc 构建产生不同 TCC 代码身份；未来配置 Developer ID 时仍覆盖同一 Release，不建立新版本线。
- `Cmd+W`/关闭窗口仅关闭窗口；`Cmd+Q` 正常结束 GUI、受管 Kimi 后台和定时器。
- 内置皮肤菜单读取 HarnessUI 唯一 `catalog/state`；catalog generation 变化时自动刷新素材并重建菜单。
- 更新只替换 App Bundle；`~/.kimi-code`、`~/.harness-ui`、登录、会话、配置、素材和外置图标不进入安装包。
- 当前机器上的 Kimi GUI 与后台保持运行，本轮未重启、未替换。旧身份迁移到固定身份须等现有任务结束后由 Owner `Cmd+Q`，再运行 `scripts/install-release-macos.sh`；首次迁移可能需要在完整磁盘访问页面确认一次。

## 验证

- Node 回归：13/13 通过。
- shell、Python、Swift 语法与 workflow YAML 解析通过。
- 本机完整 SwiftPM 构建被本机 Command Line Tools 的 `PackageDescription` 链接环境阻断；完整 macOS/Windows 构建交给干净 GitHub runner。

## 剩余

- PR 合并并等待跨平台 CI。
- 从 `main` 发布 `kimi-code-desktop-v0.38.0`，确认 8 个安装资产。
- 当前 Kimi 工作结束后执行一次旧包装版本到官方版本线的人工迁移；不得为发布验收强制重启现有 Kimi。

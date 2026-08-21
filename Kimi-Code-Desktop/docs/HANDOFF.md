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
- 旧桌面版存在 `Application Support/kimi-shell` 时继续使用该 Electron profile；只有 fresh install 才创建 `Application Support/Kimi Code`。这保证旧账号界面、窗口与站点状态不会在升级时被分裂成第二套。
- 当前机器已获 Owner 授权执行旧身份迁移；现场验收结果在同版本修复 Release 重新安装后补记。

## 验证

- Node 回归：13/13 通过。
- shell、Python、Swift 语法与 workflow YAML 解析通过。
- 本机完整 SwiftPM 构建被本机 Command Line Tools 的 `PackageDescription` 链接环境阻断；完整 macOS/Windows 构建交给干净 GitHub runner。
- PR #317 与资产名修复 PR #318 已合并；正式发布 run `32527795001` 全部通过。
- [Kimi Code Desktop v0.38.0](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-v0.38.0) 已发布为正式 Release，共 8 个资产：macOS arm64/x64 DMG+ZIP、Windows x64/arm64 安装器+ZIP。
- 旧 private/community Releases 已保留历史资产并明确标记“已废止”。

## 剩余

- 重建并替换同一 `0.38.0` Release 资产，随后完成当前机器的运行态、权限与共享素材现场验收。

# Kimi Code Desktop

Kimi Code Desktop 是一个非官方、开源的跨平台桌面壳，为 Moonshot AI 的
[Kimi Code CLI](https://github.com/MoonshotAI/kimi-code) 提供独立窗口、可靠的本地服务生命周期和可选的 Harness UI 接入。

## 支持矩阵

| 平台 | 架构 | 安装资产 |
|---|---|---|
| macOS | Apple Silicon arm64 | DMG、ZIP |
| macOS | Intel x64 | DMG、ZIP |
| Windows | x64 | NSIS EXE、ZIP |
| Windows | arm64 | NSIS EXE、ZIP |

Windows 上 Kimi Code 需要 Git for Windows 提供 Git Bash。应用不会迁移或上传
`~/.kimi-code` 中的账号、会话、日志或令牌；首次启动按 Kimi 官方流程登录。

## 安装

从 GitHub 的唯一正式版本线 `kimi-code-desktop-v*` 下载对应资产。App 版本与内置的
MoonshotAI/Kimi Code 官方版本完全一致，不建立独立包装版本：

- Mac：按机器架构打开 `mac-arm64.dmg` 或 `mac-x64.dmg`，把 App 拖入 Applications；
- Windows x64：双击 `win-x64.exe`；
- Windows ARM64：双击 `win-arm64.exe`。

Windows 请先安装 [Git for Windows](https://git-scm.com/download/win)。第一次启动会建立这台电脑自己的
Kimi Code 登录与会话，不复制旧电脑的凭据。Harness UI 控制器运行时，背景会自动跟随其当前选择；
控制器未运行时，Kimi 功能保持正常。

Mac 也可 clone 后运行仓内安装脚本；脚本从固定版本的 GitHub Release 下载 ZIP，
无需 Node、Swift 或 Xcode：

```bash
git clone https://github.com/LinzeColin/MetaDatabase.git
cd MetaDatabase/Kimi-Code-Desktop
bash scripts/install-release-macos.sh
```

脚本不会启动或重启 Kimi；如果 Kimi 正在工作会停止安装并保留现场。发布边界见
[docs/RELEASE.md](docs/RELEASE.md)。

## 正常应用行为

- **更新**：应用启动约 30 秒后检查一次，此后每 6 小时后台检查；也可在应用菜单点击“检查更新…/下载更新”。更新器只读取 `kimi-code-desktop-v*`，旧 private/community 标签不会参与版本判断。
- **上游同步**：GitHub 每日读取 MoonshotAI/Kimi Code 官方最新 Release；若本仓库缺少同版本桌面资产，会自动按完全相同的版本号构建并发布，无需 Agent 手工改版本。
- **更新边界**：更新只替换 `Kimi Code.app`；`~/.kimi-code` 中的登录、会话、配置、日志，以及 `~/.harness-ui` 中的皮肤与素材均保留。安装失败会恢复并重新打开旧 App；下次启动显示一次更新回执。
- **窗口与进程（macOS）**：`Cmd+W` 或窗口关闭按钮只关闭窗口，Kimi 后台与 HarnessUI 同步继续运行；`Cmd+Q` 才退出 GUI、由本 App 管理的 Kimi 后台和相关定时器。
- **皮肤同步**：内置皮肤菜单与 HarnessUI 共用目录和状态；素材目录变更后会自动刷新，也可手动点击“同步素材”。
- **macOS 权限身份**：安装路径、bundle id 与签名身份必须稳定，避免系统把更新识别为另一款 App。应用菜单可直接打开“隐私与安全性 → 完整磁盘访问权限”；该权限不在“文件与文件夹”列表中，仍须由用户在 macOS TCC 页面明确授予，软件不会绕过或伪造授权。

当前机器的个性化图标应外置保存到 `~/.kimi-code/personalization/kimi-code-desktop/`；运行时优先使用 `icon.png` 作为 Dock 图标，并保留 `icon.icns` 原件。更新不会修改该目录。

任意 Agent 也可以直接取得源码：

```bash
git clone https://github.com/LinzeColin/MetaDatabase.git
cd MetaDatabase/Kimi-Code-Desktop
npm ci
npm test
```

## 开发

```bash
npm ci
npm test
npm start
```

本地开发默认寻找：

1. `KIMI_CLI_PATH` 指定的可执行文件；
2. Release 内置的 Kimi CLI；
3. `~/.kimi-code/bin/kimi`；
4. `PATH` 中的 `kimi`。

## 构建

```bash
npm run dist:mac
npm run dist:win:x64
npm run dist:win:arm64
```

构建脚本直接读取 App 的 Kimi Code 官方版本号并下载同版本平台资产，二进制不提交到 Git。GitHub Actions 会生成可下载的 macOS 与 Windows 安装资产；签名凭据不会阻塞版本发布。

签名发布所需的账号、证书与 GitHub Actions secrets 见 [docs/SIGNING.md](docs/SIGNING.md)。

## 非目标

- 不替代或修改 Kimi Code CLI。
- 不分发任何 Harness 图片素材。
- 不复制现有电脑的登录态、历史会话或用户配置。
- 不宣称由 Moonshot AI 官方维护或背书。

## 许可证

本项目代码采用 MIT License。Kimi Code CLI 本身由 Moonshot AI 按其上游许可证发布，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

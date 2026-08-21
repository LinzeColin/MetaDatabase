# Kimi Code Desktop

Kimi Code Desktop 是一个非官方、开源的跨平台桌面壳，为 Moonshot AI 的
[Kimi Code CLI](https://github.com/MoonshotAI/kimi-code) 提供独立窗口、可靠的本地服务生命周期和可选的 Harness UI 接入。

## 支持矩阵

| 平台 | 架构 | 安装资产 |
|---|---|---|
| macOS | Apple Silicon arm64 | DMG、ZIP |
| Windows | x64 | NSIS EXE、ZIP |
| Windows | arm64 | NSIS EXE、ZIP |

Windows 上 Kimi Code 需要 Git for Windows 提供 Git Bash。应用不会迁移或上传
`~/.kimi-code` 中的账号、会话、日志或令牌；首次启动按 Kimi 官方流程登录。

## 安装

有受信任签名时，优先从 GitHub 的 `kimi-code-desktop-v*` Release 下载对应资产。零成本社区版使用
`kimi-code-desktop-community-v*` prerelease，文件名会明确标出 `NOT-NOTARIZED` 或 `UNSIGNED`：

- Apple Silicon Mac：打开 `mac-arm64.dmg`，把 App 拖入 Applications；
- Windows x64：双击 `win-x64.exe`；
- Windows ARM64：双击 `win-arm64.exe`。

Windows 请先安装 [Git for Windows](https://git-scm.com/download/win)。第一次启动会建立这台电脑自己的
Kimi Code 登录与会话，不复制旧电脑的凭据。Harness UI 控制器运行时，背景会自动跟随其当前选择；
控制器未运行时，Kimi 功能保持正常。

零成本 Mac 推荐让 Agent clone 后运行仓内安装脚本；脚本从固定版本的 GitHub community Release 下载 ZIP，
无需 Node、Swift 或 Xcode：

```bash
git clone https://github.com/LinzeColin/MetaDatabase.git
cd MetaDatabase/Kimi-Code-Desktop
bash scripts/install-community-macos.sh
```

脚本不会启动或重启 Kimi。社区 Release 的准确安全边界见
[docs/COMMUNITY_RELEASE.md](docs/COMMUNITY_RELEASE.md)。

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

构建脚本按固定 Kimi Code 版本下载官方平台资产，二进制不提交到 Git。正式发布必须分别完成 macOS Developer ID 公证和 Windows 代码签名；缺少凭据时只能生成候选件。

签名发布所需的账号、证书与 GitHub Actions secrets 见 [docs/SIGNING.md](docs/SIGNING.md)。

## 非目标

- 不替代或修改 Kimi Code CLI。
- 不分发任何 Harness 图片素材。
- 不复制现有电脑的登录态、历史会话或用户配置。
- 不宣称由 Moonshot AI 官方维护或背书。

## 许可证

本项目代码采用 MIT License。Kimi Code CLI 本身由 Moonshot AI 按其上游许可证发布，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

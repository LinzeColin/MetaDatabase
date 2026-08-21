# Harness UI

Harness UI 是一个跨平台皮肤控制器和宿主适配套件。它让 Kimi Code Desktop 与 DSH 使用同一套选择状态，而图片继续保存在用户自己的 NAS/SMB 中。

## 支持矩阵

| 平台 | 控制器 | 宿主适配 |
|---|---|---|
| macOS Apple Silicon | Swift/AppKit 菜单栏应用 | Kimi、DSH |
| Windows x64/arm64 | C#/.NET 托盘应用 | Kimi、DSH |

## SMB 数据源

默认地址：

- macOS：`smb://192.168.0.1/share/03_资料库/MetaData/HarnessUI/`
- Windows：`\\192.168.0.1\share\03_资料库\MetaData\HarnessUI`

已确认的目录合同：

```text
<游戏中文>/<角色ID>/
  refs/
  skins/<变体>/
    light.png
    dark.png
    meta.json
```

Runtime 只读取 `skins/`。`refs/`、`_产线`、PDF、AppleDouble 文件及图片本身都不进入 GitHub。素材根目录由用户在首次启动时选择；应用保存本机路径和小型目录索引，不保存 SMB 密码。

## 运行模型

控制器在 `127.0.0.1:3099` 提供：

- `GET /`：角色选择界面；
- `GET /catalog.json`：本机索引；
- `GET /state.json`：当前选择与轮播状态；
- `POST /api/state`：更新允许的状态字段；
- `GET /assets/...`：按需读取一张 SMB 图片。

两台电脑各自维护配置和状态；NAS 只提供只读图片。目录刷新由用户触发，不进行后台全库轮询。

## 开发

```bash
npm test
npm run validate:fixtures
```

macOS Apple Silicon 候选构建：

```bash
swift test --package-path macos
macos/scripts/build-app.sh
```

Windows 候选构建（在 PowerShell 中按目标架构选择 `win-x64` 或 `win-arm64`）：

```powershell
dotnet test windows/tests/HarnessUI.Windows.Tests.csproj -c Release
dotnet publish windows/HarnessUI.Windows.csproj -c Release -r win-x64 --self-contained true -o dist/windows-x64
```

Inno 安装器的完整双架构命令以
[跨平台 CI](../.github/workflows/kimi-harness-ci.yml) 为准。正式 Release 必须签名；缺少凭据时只能输出候选件。

## 新电脑安装

从 `harness-ui-v*` Release 下载对应的已签名资产：

- Apple Silicon Mac：打开 `mac-arm64.dmg`，把 App 拖入 Applications；首次启动后从菜单栏选择 SMB 素材根目录；
- Windows x64/ARM64：双击对应的 `windows-*-setup.exe`；默认直接使用
  `\\192.168.0.1\share\03_资料库\MetaData\HarnessUI`，也可从托盘菜单重新选择。

Mac 首次连接可在 Finder 使用“前往 → 连接服务器”，输入
`smb://192.168.0.1/share/03_资料库/MetaData/HarnessUI/`。控制器仅在用户点击刷新或首次配置时读取目录，
不会后台遍历 NAS。

Kimi Code Desktop 的适配已内置，无需再装插件。DSH 适配器从 Release 解压后执行：

```bash
node scripts/install-dsh.mjs
node scripts/install-dsh.mjs --apply
```

第一条预览目标，第二条才写入。安装器不会关闭或重启 DSH；用户准备好后自行完全退出并重新打开一次。

任意 Agent 可直接取得源码：

```bash
git clone https://github.com/LinzeColin/MetaDatabase.git
cd MetaDatabase/Harness-UI
npm ci
npm test
```

正式签名条件与 GitHub secrets 见 [docs/SIGNING.md](docs/SIGNING.md)。

## 许可证与内容边界

代码采用 MIT License。用户自行提供的图片、角色素材和 SMB 内容不属于本项目，也不会随安装包分发。

# Harness UI / DSH Desktop 交接

## 当前目标

发布可迁移到另一台电脑的 Harness UI 与 DSH Desktop，并让 Kimi、DSH 共用同一个素材目录、选择状态与更新边界。

## 当前状态（2026-08-23）

- Harness UI 使用 AgentDatabase 既有产品版本 `1.0.0`；唯一标签为 `harness-ui-v*`，旧 `harness-ui-community-v*` 不再发布。
- 三端源码、bundle identity、共享皮肤协议与发布标签由仓根 `desktop-suite/COMPATIBILITY_CONTRACT.json` 固化；正式资产只由当前 `main` 同一 `GITHUB_SHA` 的统一 workflow 同时发布，三个 Release 带同一份来源记录。
- macOS Apple Silicon、Windows x64/arm64 构建入口均存在；两端原生菜单提供“检查并下载更新…”。
- Harness UI 在 `127.0.0.1:3099` 提供唯一 `catalog.json/state.json`。素材 generation 更新后 Kimi 与 DSH 热读取，不复制第二份菜单状态。
- “下一张”由唯一服务端原子动作 `POST /api/next` 推进；Kimi、DSH、Harness UI 共用 `Cmd/Ctrl+Shift+N`，任一端切换后其它端约 1 秒同步。
- Python 服务兼容旧客户端的 `POST /api/state {"mode":"rotate"}`，因此可以只热更新共享服务恢复正在运行的旧 Kimi/DSH 按钮，不要求同时重启三个宿主。
- SMB 暂时不可达或目录不完整时保留上一版完整目录；本地 durable master 可继续供图。
- 手动/定时刷新会把 SMB 中有效的昼夜素材增量部署到 `~/.harness-ui/master`，不删除本地独有素材；完成回执区分 SMB、本地、总目录、实际部署与缺失数，不再用合并目录误报成功。
- 3099 Python 服务不再承担 macOS SMB 权限身份：运行中的 Harness UI App 在主端口 + 1 提供 loopback-only 同步 helper，以 `com.linzecolin.harnessui` GUI 身份读取 Network Volumes；Kimi、DSH 和网页仍只调用 3099。
- 已配置 LaunchAgent 时，3099 始终由后台服务持有，Harness UI GUI 只启动 3100 helper 并持续等待 3099 就绪；完整素材库窗口在可见期间自动重连，电脑重启后的启动顺序不再产生端口竞争或空白图库。
- macOS 的“打开完整素材库”使用 App 内 WebKit 窗口；Kimi Code 通过 `harnessui://library` 唤起同一 GUI，不再打开 Chrome 标签页。
- Harness UI macOS 本地代码身份固定为 `com.linzecolin.harnessui`；配置、素材、状态与图标均位于 App Bundle 外。
- DSH GitHub Release 直接镜像 anywhere-labs 官方同版本安装器，版本当前为 `2.0.2`，不建立桥接私有版本号。
- DSH macOS 桥接包提供更新菜单、HarnessUI 同步、外置图标和退出安装；本地代码身份固定为 `ai.deepseek.dsh.desktop`。有自定义图标则跨更新保留，没有图标也不会阻断官方更新。
- 每日 GitHub workflow 发现官方 Kimi/DSH 版本变化时只开三端兼容 PR 并调度 CI；合并后才由唯一套件发布流程镜像 DSH。DSH 自身更新按钮继续读取官方上游。
- 本机未发现 DSH launchd/登录项自动重启链路。90 秒受控退出期间未自动重启；此前连续启动时间与诊断操作一一对应。DSH 已受控重启一次以加载新桥接插件，当前正常运行。
- Harness UI 使用 Carbon 注册进程级 `Cmd+Shift+N`，即使 DSH 或 Kimi 在前台也能切换；DSH renderer 仍保留前台回退，但现场一次按键只推进一次共享 cursor。
- DSH 图片预加载使用 revision 丢弃迟到请求；素材 URL 增加稳定 skin 身份键，避免 `immutable` 缓存让 state/CSS 已更新而真实画面仍显示上一张。
- DSH 2.0.2 桥接层把共享素材目录提升为 macOS 独立“皮肤”菜单：当前选择、同步状态、轮播、下一张和按游戏/角色分组的完整目录均直接读取 `~/.harness-ui`，状态文件变化后原生菜单自动刷新；窗口内按钮仍作为兼容入口。
- DSH 皮肤覆盖层不再沿用过浅的 `label-dimmed/caption` 色值；浅色、深色、输入框/占位文字和 macOS“降低透明度”均有独立高对比规则，人物背景仍保留在底层。
- macOS SMB 的唯一权威挂载点为 `/Volumes/share`；旧路径 `~/mnt/share-full` 只保留为兼容符号链接。挂载脚本要求 NAS 根目录的稳定 volume ID，避免同名本地空目录被误判成完整素材库。
- SMB 挂载 LaunchAgent 先以 `smbutil` 精确确认服务器与共享名，并要求卷身份文件存在；若后台 TCC 只禁止读取该文件内容，已确认的 SMB 挂载仍视为就绪，文件可读时仍必须逐字匹配固定 volume ID。这样不会把正常挂载误报为冲突，也不会每 60 秒重复写错误日志。
- SMB 真正掉线且 Mac 处于锁屏状态时，LaunchAgent 优先调用 Harness UI 随 App 打包并复制到 runtime 的无界面 NetFS mounter；它显式使用 `NoUI`，不再让 AppleScript 的 `mount volume` 等待解锁。旧安装没有 helper 时仍保留 AppleScript 兼容路径。
- 安装器会先显式 `launchctl enable` 再加载素材与服务 LaunchAgent，避免旧的 disabled override 让“安装成功”但后台实际不运行。
- 原生完整素材库窗口接管 `Cmd+R`（同步并刷新）、`Cmd+W`（仅关图库窗口）与 `Cmd+Q`（退出 Harness UI），Kimi 与 DSH 的菜单入口都复用该窗口。

## 验证

- HarnessUI/DSH Node 回归：21/21 通过；Kimi Code Node 回归：27/27 通过。新增覆盖 SMB 到 durable master 的真实部署、缺分区 `partial` 回执、不删除本地素材、GUI helper 回执、跨端等待部署完成及原生完整素材库入口。
- DSH 桥接安装器 preview 不写入、不启动、不重启 DSH。
- 当前 Kimi PID 保持不变。
- PR #317 已合并；正式发布 run `32527795001` 全部通过。
- 统一皮肤与快捷键变更由 PR #323 交付；CI run `32538867994` 的 Node、macOS Apple Silicon 与 Windows x64/arm64 候选全部通过。
- [Harness UI v1.0.0](https://github.com/LinzeColin/MetaDatabase/releases/tag/harness-ui-v1.0.0) 已发布 7 个资产；[DSH Desktop v2.0.2](https://github.com/LinzeColin/MetaDatabase/releases/tag/dsh-desktop-v2.0.2) 已发布 3 个资产。
- 四个旧 private/community Releases 已保留历史资产并明确标记“已废止”。
- PR #324 候选已在本机安装：Harness UI 仍为 `1.0.0`，旧 App 存入 rollback；DSH 前台按一次 `Cmd+Shift+N` 后 cursor 从 34 精确到 35，DSH 与未重启的 Kimi 都实际显示同一张朱鸢皮肤。
- PR #324 已合并；正式发布 run `32550771745` 从合并后的源码覆盖 Harness UI `1.0.0` 的 7 个资产与 DSH `2.0.2` 的 3 个资产，全部构建与发布任务通过。
- 本机 Harness UI 原生二进制包含 Carbon 全局快捷键注册；当前 DSH 插件和 desktop profile 均包含迟到图片隔离与稳定 skin 身份键。共享服务仍提供 408 项 `smb+local` 目录，cursor 35 对应朱鸢。
- 2026-08-22 真实只读复核：SMB 可消费素材 326 项，本地完整库 408 项，总目录仍为 408 项；SMB 缺少 82 项，其中异环没有可消费的昼夜素材对。新服务会如实报告 `partial` 并保留本地完整库，不能把该状态写成 SMB 已完整。
- PR #326 已合并且跨平台 CI 全绿；其发布 run 在发现 launchd Python 的 TCC 归因错误后主动取消，未把“复制已实现但读取 owner 仍错误”的中间包作为最终交付。TCC 日志显示后台 PID 归因到系统 tool-shim，而不是 Harness UI bundle。
- PR #327 已合并；正式发布 run `32554391391` 的 macOS、Windows、Kimi、Harness UI、DSH 及三个发布任务全部通过，正式标签仍沿用 Harness UI `1.0.0`、Kimi Code `0.38.0`、DSH `2.0.2`。
- 本机正式 Harness UI 首次同步回执：SMB 326、本地 408、总目录 408、部署 326、缺少 82、缺失分区仅异环，`sourceOwner=harness-app`。完整素材库已在原生 WebKit 窗口显示 408/408，没有新增 Chrome 素材库标签；Kimi PID 与启动时间未变，标准安装位置已无启动地更新为 `0.38.0`，待 Owner 以后自然退出再启用新菜单。
- GUI 状态热同步回归更新为 22/22：即使皮肤 state 不变，后台自动同步完成后的 `ready/partial/failed` 与说明也会自动刷新到完整素材库页面。
- 最终本机安装发现 3099 服务与 GUI 同秒启动时可能漏建 3100 helper；安装器现等待 `state.json` 可读，App 对已配置 LaunchAgent 做有上限的就绪重试。没有共享服务的 standalone 模式不受影响。
- DSH 原生皮肤菜单与可读性候选本机回归：HarnessUI/DSH 26/26、Kimi 29/29；同一补丁已在正式 DSH 2.0.2 的隔离副本上通过菜单结构、脚本语法与版本保持验证。PR #331 的跨平台候选、Node、版本守卫与双平面检查全部通过（runs `32562287082`、`32562287084`、`32562287085`），尚待合并后的正式资产覆盖及本机桥接安装。
- 2026-08-22 最终本机回执为 SMB 408、本地 408、总目录 408、部署 0、缺失 0，`sourceOwner=harness-app`；Kimi 与 DSH 菜单均显示 408 项，两个“打开完整素材库”入口均落到同一个原生 `Harness UI · 完整素材库` 窗口，页面显示 408/408，未产生 Chrome 标签页。
- DSH 2.0.2 已安装新桥接且外置图标保留；浅色皮肤下在输入框键入未发送草稿，用户输入文字为深色可读，清空草稿后不影响会话。
- 现场 LaunchAgent 复现了“终端可读 volume ID、后台进程仅能确认 SMB 身份但读取内容被 TCC 拒绝”的差异；修复后同一 `com.harnessui.smb` job 正常退出为 0，既有 `/Volumes/share` 保持原位，错误日志不再增长，HarnessUI Node 回归 27/27 通过。
- 2026-08-23 锁屏现场再次复现：AppleScript mounter 持续等待，等价的 NetFS `NoUI` 调用在不到 1 秒内恢复 `/Volumes/share`；GUI-owned source helper 随后重新给出 SMB 408、本地 408、目录 408、缺失 0。该路径已进入随 App 构建的原生 helper 与服务安装流程。

## 运行边界

- 在另一台电脑从正式 Release 安装，并选择其本机 SMB 素材目录；不要迁移 OAuth、API Key、会话或 SMB 凭据。
- 本机三端已经同步运行；后续更新只替换应用本体或 DSH 桥接文件，不覆盖 `~/.harness-ui` 的目录、状态、素材、皮肤或外置图标，也不迁移账号和凭据。
- 模型总上下文由仓根 `desktop-suite/MODEL_CONTEXT_CONTRACT.json` 统一约束。DSH 外部配置已补齐 DeepSeek 官方 Flash/Pro 与可用 SCNet 路由，并按真实总窗口统一；本轮 DSH 未运行，所以未启动或重启，下一次正常启动直接加载。SCNet GLM-5.3 当前真实调用仍为 403，保持不加入。

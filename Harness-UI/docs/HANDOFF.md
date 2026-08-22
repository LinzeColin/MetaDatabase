# Harness UI / DSH Desktop 交接

## 当前目标

发布可迁移到另一台电脑的 Harness UI 与 DSH Desktop，并让 Kimi、DSH 共用同一个素材目录、选择状态与更新边界。

## 当前状态（2026-08-22）

- Harness UI 使用 AgentDatabase 既有产品版本 `1.0.0`；唯一标签为 `harness-ui-v*`，旧 `harness-ui-community-v*` 不再发布。
- macOS Apple Silicon、Windows x64/arm64 构建入口均存在；两端原生菜单提供“检查并下载更新…”。
- Harness UI 在 `127.0.0.1:3099` 提供唯一 `catalog.json/state.json`。素材 generation 更新后 Kimi 与 DSH 热读取，不复制第二份菜单状态。
- “下一张”由唯一服务端原子动作 `POST /api/next` 推进；Kimi、DSH、Harness UI 共用 `Cmd/Ctrl+Shift+N`，任一端切换后其它端约 1 秒同步。
- Python 服务兼容旧客户端的 `POST /api/state {"mode":"rotate"}`，因此可以只热更新共享服务恢复正在运行的旧 Kimi/DSH 按钮，不要求同时重启三个宿主。
- SMB 暂时不可达或目录不完整时保留上一版完整目录；本地 durable master 可继续供图。
- 手动/定时刷新会把 SMB 中有效的昼夜素材增量部署到 `~/.harness-ui/master`，不删除本地独有素材；完成回执区分 SMB、本地、总目录、实际部署与缺失数，不再用合并目录误报成功。
- 3099 Python 服务不再承担 macOS SMB 权限身份：运行中的 Harness UI App 在主端口 + 1 提供 loopback-only 同步 helper，以 `com.linzecolin.harnessui` GUI 身份读取 Network Volumes；Kimi、DSH 和网页仍只调用 3099。
- macOS 的“打开完整素材库”使用 App 内 WebKit 窗口；Kimi Code 通过 `harnessui://library` 唤起同一 GUI，不再打开 Chrome 标签页。
- Harness UI macOS 本地代码身份固定为 `com.linzecolin.harnessui`；配置、素材、状态与图标均位于 App Bundle 外。
- DSH GitHub Release 直接镜像 anywhere-labs 官方同版本安装器，版本当前为 `2.0.2`，不建立桥接私有版本号。
- DSH macOS 桥接包提供更新菜单、HarnessUI 同步、外置图标和退出安装；本地代码身份固定为 `ai.deepseek.dsh.desktop`。有自定义图标则跨更新保留，没有图标也不会阻断官方更新。
- 每日 GitHub workflow 自动镜像缺失的官方 DSH 同版本 Release；DSH 自身更新按钮继续读取官方上游。
- 本机未发现 DSH launchd/登录项自动重启链路。90 秒受控退出期间未自动重启；此前连续启动时间与诊断操作一一对应。DSH 已受控重启一次以加载新桥接插件，当前正常运行。
- Harness UI 使用 Carbon 注册进程级 `Cmd+Shift+N`，即使 DSH 或 Kimi 在前台也能切换；DSH renderer 仍保留前台回退，但现场一次按键只推进一次共享 cursor。
- DSH 图片预加载使用 revision 丢弃迟到请求；素材 URL 增加稳定 skin 身份键，避免 `immutable` 缓存让 state/CSS 已更新而真实画面仍显示上一张。
- DSH 2.0.2 桥接层把共享素材目录提升为 macOS 独立“皮肤”菜单：当前选择、同步状态、轮播、下一张和按游戏/角色分组的完整目录均直接读取 `~/.harness-ui`，状态文件变化后原生菜单自动刷新；窗口内按钮仍作为兼容入口。
- DSH 皮肤覆盖层不再沿用过浅的 `label-dimmed/caption` 色值；浅色、深色、输入框/占位文字和 macOS“降低透明度”均有独立高对比规则，人物背景仍保留在底层。

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

## 运行边界

- 在另一台电脑从正式 Release 安装，并选择其本机 SMB 素材目录；不要迁移 OAuth、API Key、会话或 SMB 凭据。
- 本机三端已经同步运行；后续更新只替换应用本体或 DSH 桥接文件，不覆盖 `~/.harness-ui` 的目录、状态、素材、皮肤或外置图标，也不迁移账号和凭据。

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
- Harness UI macOS 本地代码身份固定为 `com.linzecolin.harnessui`；配置、素材、状态与图标均位于 App Bundle 外。
- DSH GitHub Release 直接镜像 anywhere-labs 官方同版本安装器，版本当前为 `2.0.2`，不建立桥接私有版本号。
- DSH macOS 桥接包提供更新菜单、HarnessUI 同步、外置图标和退出安装；本地代码身份固定为 `ai.deepseek.dsh.desktop`。有自定义图标则跨更新保留，没有图标也不会阻断官方更新。
- 每日 GitHub workflow 自动镜像缺失的官方 DSH 同版本 Release；DSH 自身更新按钮继续读取官方上游。
- 本机未发现 DSH launchd/登录项自动重启链路。90 秒受控退出期间未自动重启；此前连续启动时间与诊断操作一一对应。DSH 已受控重启一次以加载新桥接插件，当前正常运行。
- Harness UI 使用 Carbon 注册进程级 `Cmd+Shift+N`，即使 DSH 或 Kimi 在前台也能切换；DSH renderer 仍保留前台回退，但现场一次按键只推进一次共享 cursor。
- DSH 图片预加载使用 revision 丢弃迟到请求；素材 URL 增加稳定 skin 身份键，避免 `immutable` 缓存让 state/CSS 已更新而真实画面仍显示上一张。

## 验证

- HarnessUI/DSH Node 回归：15/15 通过，覆盖共享原子切换、全局快捷键、非 `.app` 回滚、DSH 2.0.2 patch contract、SMB 本地降级、adapter 安装和迟到图片请求隔离。
- DSH 桥接安装器 preview 不写入、不启动、不重启 DSH。
- 当前 Kimi PID 保持不变。
- PR #317 已合并；正式发布 run `32527795001` 全部通过。
- 统一皮肤与快捷键变更由 PR #323 交付；CI run `32538867994` 的 Node、macOS Apple Silicon 与 Windows x64/arm64 候选全部通过。
- [Harness UI v1.0.0](https://github.com/LinzeColin/MetaDatabase/releases/tag/harness-ui-v1.0.0) 已发布 7 个资产；[DSH Desktop v2.0.2](https://github.com/LinzeColin/MetaDatabase/releases/tag/dsh-desktop-v2.0.2) 已发布 3 个资产。
- 四个旧 private/community Releases 已保留历史资产并明确标记“已废止”。
- PR #324 候选已在本机安装：Harness UI 仍为 `1.0.0`，旧 App 存入 rollback；DSH 前台按一次 `Cmd+Shift+N` 后 cursor 从 34 精确到 35，DSH 与未重启的 Kimi 都实际显示同一张朱鸢皮肤。
- PR #324 已合并；正式发布 run `32550771745` 从合并后的源码覆盖 Harness UI `1.0.0` 的 7 个资产与 DSH `2.0.2` 的 3 个资产，全部构建与发布任务通过。
- 本机 Harness UI 原生二进制包含 Carbon 全局快捷键注册；当前 DSH 插件和 desktop profile 均包含迟到图片隔离与稳定 skin 身份键。共享服务仍提供 408 项 `smb+local` 目录，cursor 35 对应朱鸢。

## 运行边界

- 在另一台电脑从正式 Release 安装，并选择其本机 SMB 素材目录；不要迁移 OAuth、API Key、会话或 SMB 凭据。
- 本机三端已经同步运行；后续更新只替换应用本体或 DSH 桥接文件，不覆盖 `~/.harness-ui` 的目录、状态、素材、皮肤或外置图标，也不迁移账号和凭据。

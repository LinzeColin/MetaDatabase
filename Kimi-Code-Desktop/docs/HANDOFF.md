# Kimi Code Desktop 交接

## 当前目标

让 Kimi Code Desktop 像普通 App 一样安装、退出、更新并保持完整磁盘访问身份；版本号严格跟随 MoonshotAI/Kimi Code 官方版本，不设置桌面壳私有版本。

## 当前状态（2026-08-22）

- 源码版本与内置 Kimi Code 均为 `0.38.0`；构建脚本直接从 `package.json` 读取版本并下载同版本官方平台资产。
- 唯一更新标签为 `kimi-code-desktop-v*`。旧 `kimi-code-desktop-community-v*` 已退出更新候选。
- App 启动 30 秒后及每 6 小时后台检查，也可从应用菜单手动检查、下载并在确认后退出安装。
- 同一官方版本内的桌面维护修复使用 Release 旁的 `release.json` 与包内发行修订标识比较；可见版本仍严格保持官方 `0.38.0`。因此覆盖同 tag 资产后，用户的“检查更新…”按钮也能发现维护更新，不再依赖 Agent 手工替换。
- 每日 GitHub workflow 会读取官方最新版本；发现版本变化时只创建三端兼容 PR 并调度 CI，不直接创建任何单 App Release。
- 三端源码、bundle identity、共享皮肤协议与发布标签由仓根 `desktop-suite/COMPATIBILITY_CONTRACT.json` 固化；正式资产只由当前 `main` 同一 `GITHUB_SHA` 的统一 workflow 同时发布，三个 Release 带同一份来源记录。
- macOS 本地构建固定使用 `com.electron.kimi-code` designated requirement，避免每次 ad-hoc 构建产生不同 TCC 代码身份；未来配置 Developer ID 时仍覆盖同一 Release，不建立新版本线。
- macOS 构建在 Electron 签名步骤后恢复 Moonshot 官方签名的内置 CLI；启动时仅把同版本 CLI 可执行文件迁移到稳定路径 `~/.kimi-code/bin/kimi`，旧 CLI 单独留在 `desktop-updates/cli-rollback/`，不修改同目录下任何账号、会话、配置、图标、皮肤或素材。
- macOS GUI 通过临时 launchd job 启动稳定路径中的官方 CLI，使后台 TCC 身份不再继承 ad-hoc Electron 壳；`Cmd+W`/关闭窗口仅关闭窗口，`Cmd+Q` 移除该 job 并正常结束 GUI、后台和定时器。该 job 不是登录启动项。
- 内置皮肤菜单读取 HarnessUI 唯一 `catalog/state`；catalog generation 变化时自动刷新素材并重建菜单。
- “换下一张”改为共享服务原子动作 `POST /api/next`，快捷键恢复为 `Cmd/Ctrl+Shift+N`；轮询周期从 15 秒收敛到约 1 秒，与 DSH、Harness UI 使用同一状态。
- Kimi 皮肤桥由应用生命周期持有串行恢复循环；电脑重启后即使 Kimi 先于 Harness UI/3099 服务启动，也会在服务就绪后自动读取当前 catalog/state 并恢复皮肤。
- 3099 服务健康与 renderer 皮肤呈现分别记录；页面加载期间的短暂注入失败只进入下一轮自动校正，不再把服务误报为离线。
- 更新只替换 App Bundle 与稳定路径中的官方 CLI 本体；`~/.kimi-code` 其余内容、`~/.harness-ui`、登录、会话、配置、素材和外置图标不进入安装包。
- 旧桌面版存在 `Application Support/kimi-shell` 时继续使用该 Electron profile；只有 fresh install 才创建 `Application Support/Kimi Code`。这保证旧账号界面、窗口与站点状态不会在升级时被分裂成第二套。
- 更新器会把正式安装位置写入 `desktop-updates/install-location.json`。即使 App 误从 rollback 副本启动，安装目标也回到正式 App；新回滚目录使用 `.app.rollback` 后缀，旧 `.app` 回滚副本在不运行时自动隔离，避免 LaunchServices 把备份注册成第二个 Kimi。
- 当前机器已完成旧身份迁移：稳定后台为 `~/.kimi-code/bin/kimi` 0.38.0，保留 Moonshot Developer ID；旧 0.37.2 CLI 已进入 `desktop-updates/cli-rollback/`，原 `kimi-shell` Electron profile、会话与个性化目录保持原位。
- renderer reload 后由 `did-finish-load` 重新插入皮肤 CSS、清空 bridge 应用键并重放当前状态；素材 URL 同时携带稳定 skin 身份键，避免 Chromium `immutable` 缓存显示历史错误位图。
- 人物图只存在于根背景层；`.app-shell` 保持透明以露出人物，`.main` 只加轻量色洗，真正阅读列 `.content-wrap`、侧栏和输入区各自使用高对比表层；模型菜单、工作区选择器和添加工作区对话框使用接近不透明的独立弹层。浅色、暗色与系统“降低透明度”均有独立覆盖。

## 验证

- Node 回归：31/31 通过。
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
- PR #324 在当前 PID 95131/95134 上做了不重启恢复：共享快捷键切换后 Kimi 与 DSH 同显朱鸢；对现有 renderer 做等价 `Cmd+R` reload 后，工作线程、皮肤 URL 和真实合成画面都保留，PID 未变化，临时 inspector 已关闭。
- PR #324 已合并；正式发布 run `32550771745` 从合并后的源码重新生成并覆盖同版本 8 个资产，全部构建与发布任务通过。
- 新正式 App 已安装到 `~/Applications/Kimi Code.app` 且未启动；安装前后工作中的 GUI/backend 仍为 PID 95131/95134。App 代码身份、版本与完整性检查通过，包内包含 `did-finish-load` 重放、bridge `reapply()` 与稳定 skin 身份键。
- 过度透明修复已在 PID 95131 的现有 renderer 内无刷新热应用：主表层 76%、侧栏 86%、输入区约 98%、模型与工作区弹层 99%；模型菜单、工作区选择器及“添加工作区”对话框均已截图验收，PID 95131/95134 未变化。暗色计算样式同样达到主表层 78%、侧栏 88%、输入区约 98%、弹层 99%。
- Owner 自然重启后，最终 `0.38.0` 已从标准位置 `~/Applications/Kimi Code.app` 运行；设置页和“添加工作区”弹窗均在该安装版本上真机复验为清晰表层。执行 `Cmd+R` 后皮肤人物仍显示，阅读列、侧栏、消息与输入区保持可读，原生皮肤菜单仍为 408 项。
- 2026-08-23 Owner 明确了新的视觉验收边界：空白新会话能看到人物不代表已有线程页通过；已有线程如果被嵌套表层洗成白色仍是失败。普通浅色表层现收敛为根层 64%、侧栏 74%、阅读列 60% 并配 10px 轻模糊，暗色对应为 68%/76%/64%；输入区仍接近 98%、模型/工作区/创建工作区弹层仍为 99%，系统“降低透明度”继续使用实体背景。
- 进一步定位确认已有线程的真实容器是 `#app .con`，而不是空会话使用的 `.main`；现已让两者共同使用 `--harness-main-wash` 并加入 Node 回归。否则 `.con` 的 64% 默认底色与 60% 阅读列表层叠加后会形成约 85.6% 的白色覆盖。
- 同一组样式已在运行中的 Kimi PID 46340 上通过本机 inspector 无刷新热应用：没有重启 GUI/backend、没有 `Cmd+R`，已有线程页人物与场景重新可见，表格、正文、侧栏和输入框仍可读；T1、T2 与“辅助线 - 数据分析”继续保持运行标记。持久安装包仍需由同版本正式 Release 覆盖，当前热应用只负责不中断恢复。
- 同版本维护更新协议现把 GitHub workflow 的内部发行修订同时写入 macOS/Windows 包和 Release 清单；更新器先比较官方版本，再比较该修订。新安装包不会重复提示自己，旧安装包会把新的同版本正式资产显示为“维护更新”；安装回执保留该修订，但账号、会话、配置、皮肤、素材和外置图标仍不进入更新事务。

## 运行边界

- 当前承载工作线程的是标准安装位置的新进程；后续只按普通应用生命周期操作：`Cmd+W`/红色关闭键仅隐藏窗口并保留后台，`Cmd+Q` 才退出 GUI 与后台。
- 其它电脑需从正式 Release 安装，并在该电脑上单独选择或授权其 SMB 位置；不要复制 OAuth、API Key、会话或 SMB 凭据。
- 模型总上下文由仓根 `desktop-suite/MODEL_CONTEXT_CONTRACT.json` 统一约束。本机 Kimi 已无重启热读取新目录：Kimi K3 / SCNet Kimi K3 为 1,048,576，DeepSeek V4 与其余已验证 SCNet 路由为 1,000,000；K3-256K 保持 262,144。两个旧 alias 因仍有大量历史会话引用而保留。

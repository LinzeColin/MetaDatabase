# Harness UI / DSH Desktop 交接

## 当前目标

发布可迁移到另一台电脑的 Harness UI 与 DSH Desktop，并让 Kimi、DSH 共用同一个素材目录、选择状态与更新边界。

## 当前状态（2026-08-22）

- Harness UI 使用 AgentDatabase 既有产品版本 `1.0.0`；唯一标签为 `harness-ui-v*`，旧 `harness-ui-community-v*` 不再发布。
- macOS Apple Silicon、Windows x64/arm64 构建入口均存在；两端原生菜单提供“检查并下载更新…”。
- Harness UI 在 `127.0.0.1:3099` 提供唯一 `catalog.json/state.json`。素材 generation 更新后 Kimi 与 DSH 热读取，不复制第二份菜单状态。
- SMB 暂时不可达或目录不完整时保留上一版完整目录；本地 durable master 可继续供图。
- Harness UI macOS 本地代码身份固定为 `com.linzecolin.harnessui`；配置、素材、状态与图标均位于 App Bundle 外。
- DSH GitHub Release 直接镜像 anywhere-labs 官方同版本安装器，版本当前为 `2.0.2`，不建立桥接私有版本号。
- DSH macOS 桥接包提供更新菜单、HarnessUI 同步、外置图标和退出安装；本地代码身份固定为 `ai.deepseek.dsh.desktop`。有自定义图标则跨更新保留，没有图标也不会阻断官方更新。
- 每日 GitHub workflow 自动镜像缺失的官方 DSH 同版本 Release；DSH 自身更新按钮继续读取官方上游。
- 本机未发现 DSH launchd/登录项自动重启链路。90 秒受控退出期间未自动重启；此前连续启动时间与诊断操作一一对应。DSH 当前保持退出。

## 验证

- HarnessUI/DSH Node 回归：11/11 通过，覆盖 DSH 2.0.2 patch contract、SMB 本地降级和 adapter 安装。
- DSH 桥接安装器 preview 不写入、不启动、不重启 DSH。
- 当前 Kimi PID 保持不变。

## 剩余

- PR 合并并等待 GitHub macOS/Windows 构建。
- 发布 `harness-ui-v1.0.0` 与 `dsh-desktop-v2.0.2`，确认安装资产和桥接包。
- 旧 private/community Releases 只做“已废止”标记，不删除历史资产。

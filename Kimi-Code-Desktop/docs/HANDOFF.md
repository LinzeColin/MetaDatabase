# Kimi Code Desktop 交接

## 当前目标

交付 macOS Apple Silicon、Windows x64 与 Windows arm64 的可复现桌面应用和 GitHub Release。

## 当前状态

- 桌面壳、Kimi 0.38.0 获取、Harness 适配、三平台构建配置和正式签名工作流已实现。
- PR #309 已合并到公开仓 `MetaDatabase/main`；合并提交后的全部仓库检查已通过。
- 干净 GitHub runner 已实际生成 macOS arm64 DMG/ZIP，以及 Windows x64/arm64 NSIS EXE/ZIP 候选件；主分支跨平台验收 run 为 `32479000586`。
- 正式工作流要求有效签名身份，并显式验证 Mac App/DMG 的签名、公证票据与 Gatekeeper，以及 Windows x64/arm64 主程序和安装器的 Authenticode 信任链与时间戳。
- PR #310 已把上述发布门合并到 `main`；合并后的跨平台 run `32481584316` 和三条仓库治理工作流全部通过。
- 正式工作流演练 run `32482228994` 已通过 main/version/确认词门，并准确停在缺失签名 secrets；macOS、Windows、publish jobs 全部跳过，未创建 Release。
- 正式 Release 尚未发布；候选件未冒充已签名制品。
- 方案 A 已实现正常应用生命周期：窗口关闭/Cmd+W 不退出后台，Cmd+Q 退出 GUI 与受管 Kimi 后台；应用菜单提供手动更新与皮肤同步，启动 30 秒及每 6 小时检查稳定更新。
- 更新器优先接受带目标平台资产的稳定 `kimi-code-desktop-v*` Release，并在一键安装前验证 bundle id、签名与 Gatekeeper；也会检测零成本 community prerelease，但只显式提示并交给浏览器下载，不静默替换。两条通道都不修改 `~/.kimi-code`、`~/.harness-ui` 或外置个性化资源。
- Kimi 内置皮肤菜单与 HarnessUI 共用 catalog/state，并按 catalog generation 热更新素材与选择状态。
- 现有 `~/Applications/Kimi Code.app` 保持运行且未被修改或重启；旧的本地 0.2.0 候选包已判定为版本倒序，不得覆盖运行版。
- 截至 2026-08-21，GitHub 没有 Apple/Windows 签名 secrets，本机也没有有效 codesigning identity；发布门保持 `WAITING_SIGNING_CREDENTIAL`。
- 2026-08-22 Owner 明确要求发行成本恒为 `$0`。Apple Developer ID/公证因此不再是本轮可执行路径；现有 signed workflow 保留但不冒充已完成。
- 零成本 community workflow 已新增，固定发布 `kimi-code-desktop-community-v0.1.0` prerelease；macOS 文件名标记 `NOT-NOTARIZED`，Windows 标记 `UNSIGNED`。
- `scripts/install-community-macos.sh` 供 Agent clone 后安装固定版本 ZIP；只复制、不启动、不重启，且不修改 Gatekeeper 设置。
- PR #312 已合并；主分支发布 run `32513109964` 全部通过，并发布 [Kimi Code Desktop v0.1.0 Community](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-community-v0.1.0)。
- Release 为非草稿 prerelease，共 6 个资产：macOS arm64 DMG/ZIP，以及 Windows x64/arm64 安装器和便携 ZIP；全部安全状态已写进文件名。
- 已从公开 Release 下载 macOS ZIP，通过 Agent 安装脚本复制到隔离临时目录；App 版本为 `0.1.0`、主程序为 arm64，全程未启动应用，临时副本已移入废纸篓。
- 1.0.1 更新器采用双轨：受信任稳定版可验签后一键替换；community prerelease 只显式提示并交给浏览器下载。社区安装脚本可在 Kimi 完全退出后保留旧 App 并原子替换，不会结束正在工作的 Kimi。
- 现场运行版的 bundle version 是 1.0.0；0.2.0 会被标准版本比较视为降级，故在发布前取消。Kimi Desktop 从 1.0.1 继续递增，Harness UI 保持独立的 0.2.0 版本线；联合 community workflow 接受两个独立版本输入。
- community macOS 构建显式使用 ad-hoc identity 并关闭该通道的 hardened runtime，打包后验证完整 bundle 与 `com.electron.kimi-code` 代码身份；仍不把它表述为 Developer ID 签名或公证版本。
- macOS 应用菜单提供“打开完整磁盘访问设置…”并直达 `Privacy_AllFiles`；“文件与文件夹”不是 Full Disk Access 列表，授权仍由 Owner 在系统 TCC 页面完成。
- PR #314 与 #315 已合并；联合 community 发布 run `32522348126` 在 macOS arm64、Windows x64/arm64 构建和两个 publish job 上全部通过。
- [Kimi Code Desktop v1.0.1 Community](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-community-v1.0.1) 已发布为非草稿 prerelease，共 6 个明确标记安全状态的资产。
- 已重新下载公开 macOS ZIP 验收：App 为 `1.0.1`、bundle/code identifier 为 `com.electron.kimi-code`、主程序为 arm64、完整 bundle 通过严格 ad-hoc 代码结构验证、内置 Kimi Code 为 `0.38.0`，且 `Privacy_AllFiles` 与共享 catalog 刷新入口存在。该结论不等同于 Developer ID 签名或 Apple 公证。
- 现场运行版仍为 `1.0.0`，GUI 与 Kimi 后台保持原 PID 和监听端口，本轮未重启。只有 Owner 的现有工作线程结束并主动退出 Kimi 后，才允许执行一次 community 安装以进入 `1.0.1` 更新线。

## 边界

- 源码与构建配置可公开。
- Kimi OAuth、API Key、会话、日志、用户配置和 Harness 图片不得进入仓库或 Release。
- 只使用官方 Kimi Code Release 二进制作为构建输入。

## 下一步

等待 Owner 的现有 Kimi 工作线程自然结束；完全退出 Kimi 后执行一次 `scripts/install-community-macos.sh`，再启动 `1.0.1`。此后应用内菜单负责检查更新，community 通道仍要求显式下载确认，受信任 stable 通道才允许验签后一键替换。未来 Owner 改变预算并配置七个签名 secrets 后，再从 `main` 运行 signed release；只有签名、公证、时间戳验证和六个资产全部通过，应用内稳定通道才允许一键替换。

补充跟 Prompt（22 个汉字）：`请收口当前皮肤任务并输出可迁移交接勿重启应用`

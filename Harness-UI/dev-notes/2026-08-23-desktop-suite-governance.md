# 2026-08-23：Desktop Suite 治理与皮肤刷新稳定性

## 结论

Harness UI 是 Kimi Code Desktop 与 DSH Desktop 的共享皮肤状态 owner。三端通过同一份 catalog、state 和原子下一张接口协作，发布时由同一 GitHub commit 生成三组应用资产。

## 皮肤周期性闪动的根因

定时 SMB 刷新即使没有素材内容变化，也会生成新的 catalog revision 并写入 state.updated。两个桌面客户端把这些无视觉变化的字段视为新的背景资源，因而重新预加载和写入背景。

## 当前修复

- 背景服务比较 catalog 的业务内容，忽略资源 URL 的缓存 revision。素材未变化时保留 catalog 与 state，只更新 refresh-status。
- macOS Harness UI 在真正部署素材或业务目录变化时才发布新的 catalog generation。
- Kimi 与 DSH 使用稳定的素材身份判断是否需要重绘；相同 URL 不触发第二次背景写入。
- 共享下一张仍统一走 POST /api/next，快捷键仍为 CmdOrCtrl+Shift+N。

## 跨电脑协作

仓根 desktop-suite/COMPATIBILITY_CONTRACT.json 是三端路径、bundle identifier、版本来源、共享协议和 release tag 的机器可读契约。任何兼容性改动与契约一同进入 PR；desktop-app-suite-release workflow 从同一 GITHUB_SHA 构建和发布 Kimi、Harness UI、DSH。

GitHub 仓库级 Actions Workflow permissions 保持 `Read and write permissions`。Harness 发布 job 以最小 `contents: write` 覆盖同版本正式 Release 的 tag 与七个资产，使三端能够收敛到同一个 commit。

同版本覆盖发布同步 Git tag 与 GitHub Release 的 `target_commitish`，因此 Harness UI 的下载资产和发布页面都可追溯到同一个套件提交。

上游观察工作流只报告 Kimi 与 DSH 的版本漂移。来源更新通过 PR 合入后，统一 workflow 一次生成三端资产；历史单应用发布入口已经移除，Harness UI 因此始终与同一套件提交发布。

## 运行边界

API key、账号、会话、SMB 凭据、素材文件、运行时 catalog/state、个人图标原件与已安装 App 都保持在本机外置目录。公开仓库只保存源码、契约、可公开的构建脚本与说明。

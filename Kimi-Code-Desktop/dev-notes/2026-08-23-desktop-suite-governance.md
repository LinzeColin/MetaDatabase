# 2026-08-23：Kimi Code Desktop 与统一桌面套件

## Kimi 皮肤刷新原则

HarnessBridge 的背景应用键只由选中素材及其 light/dark 资源决定。state.updated 用于同步控制状态，不能作为背景重绘依据。Renderer reload 时仍清空应用键并重放当前皮肤，确保 Cmd+R 后背景恢复。

已有工作线程与空会话使用不同的主容器。空会话落在 `.main`，已有线程的实际根表层落在 `#app .con`；两者都必须使用 `--harness-main-wash`。只修改 `.main` 会让 `.con` 默认底色继续与 60% 阅读列叠加，视觉上重新接近白屏。回归测试必须明确检查 `.con` 规则。

## 共享状态原则

Kimi 只消费 Harness UI 提供的 catalog、state 和 POST /api/next。它不保存独立的皮肤选中状态，因此与 Harness UI、DSH 始终收敛到同一张图。

## 发布原则

Kimi 源码、Harness UI 和 DSH 桥接由仓根 desktop-suite/COMPATIBILITY_CONTRACT.json 关联。正式发布通过 desktop-app-suite-release workflow 从当前 `main` 的同一个 GITHUB_SHA 生成三端资产；本机构建用于开发，GitHub main 是跨电脑共享真源。旧 Kimi signed workflow 已移除；任何第二发布入口都会被契约校验拒绝。

GitHub 仓库级 Actions Workflow permissions 保持 `Read and write permissions`，让 Kimi 的发布 job 取得其声明的最小 `contents: write` 权限，从而更新同版本正式 Release 的 tag 与资产。

同版本覆盖发布同时更新 Git tag 与 GitHub Release 的 `target_commitish`。两者共同表达 Kimi 的正式资产来自哪一个统一套件提交。

Mac Pro 与 Mac Air 都只能从 `origin/main` 建独立 worktree 分支并开 PR。PR 通过三端契约和跨平台候选后才能合入；合并后的 main push 自动触发唯一发布者，三个 Release 都携带同一份 `Desktop.App.Suite-release.json`。

上游版本工作流只更新 Kimi 与 DSH 的版本来源、创建兼容 PR 并调度 CI；统一 workflow 只在 PR 合入后发布三端，因此自动更新不会重新形成第二条 Kimi 发布线。

## 私有运行边界

用户的模型配置、账号、会话、API key、SMB 凭据、图标和已安装 App 都保留在本机目录。更新只替换应用 Bundle 与稳定 CLI 本体，外置个性化数据保持原位。

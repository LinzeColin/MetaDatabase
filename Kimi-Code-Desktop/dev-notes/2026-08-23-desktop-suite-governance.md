# 2026-08-23：Kimi Code Desktop 与统一桌面套件

## Kimi 皮肤刷新原则

HarnessBridge 的背景应用键只由选中素材及其 light/dark 资源决定。state.updated 用于同步控制状态，不能作为背景重绘依据。Renderer reload 时仍清空应用键并重放当前皮肤，确保 Cmd+R 后背景恢复。

## 共享状态原则

Kimi 只消费 Harness UI 提供的 catalog、state 和 POST /api/next。它不保存独立的皮肤选中状态，因此与 Harness UI、DSH 始终收敛到同一张图。

## 发布原则

Kimi 源码、Harness UI 和 DSH 桥接由仓根 desktop-suite/COMPATIBILITY_CONTRACT.json 关联。正式发布通过 desktop-app-suite-release workflow 从同一个 GITHUB_SHA 生成三端资产；本机构建用于开发，GitHub main 是跨电脑共享真源。

## 私有运行边界

用户的模型配置、账号、会话、API key、SMB 凭据、图标和已安装 App 都保留在本机目录。更新只替换应用 Bundle 与稳定 CLI 本体，外置个性化数据保持原位。

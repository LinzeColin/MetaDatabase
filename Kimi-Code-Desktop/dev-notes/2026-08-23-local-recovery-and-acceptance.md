# 2026-08-23：Kimi Code Desktop 本机恢复与验收

## 根因

本机曾同时保留开发构建、旧正式包和运行时热应用样式。进程实际加载的 Bundle 早于统一 Release，源码中的 `.main`、`#app .con`、弹层阅读面和原生皮肤菜单规则没有一起进入运行进程。皮肤刷新与 renderer reload 混在一起时，还会让界面误显示“服务器不在线”，因为 UI 重载打断了正在工作的本地 backend 连接。

## 正确恢复路径

1. 以统一桌面套件 Release 的 `0.38.0` macOS arm64 资产替换 App Bundle，一次完成版本切换。
2. 会话、模型配置、账号和皮肤状态继续保留在 Bundle 外；Harness UI 继续作为 catalog/state owner。
3. 背景切换只更新素材变量，renderer 与 backend 生命周期保持稳定。
4. 既有线程的 `#app .con`、空会话的 `.main`、设置页、模型选择和工作区选择器统一使用高对比阅读面；背景保留视觉存在感，文字层保持清晰。
5. “打开完整素材库”进入独立 Harness UI 原生窗口，Kimi 菜单继续提供素材计数、立即同步和统一下一张快捷键。

## 本机验收记录

- 已安装版本：`0.38.0`；正式安装路径：`~/Applications/Kimi Code.app`。
- 当前皮肤与 DSH、Harness UI 同步；一次 `Cmd+Shift+N` 让三端共同前进一张。
- 既有工作线程与空会话都显示背景；正文、侧栏、输入框和模型菜单保持可读。
- “新建工作空间”显示为高不透明浅色面板，目录、搜索、说明和操作按钮清晰。
- `Cmd+R` 保留皮肤；`Cmd+W` 关闭窗口并保留 GUI/backend；`Cmd+Q` 同时退出 GUI/backend。
- 皮肤菜单打开的完整素材库为原生 GUI，支持 `Cmd+R`、`Cmd+W`、`Cmd+Q`。

## 持续规则

- 更新器只替换 App Bundle，保持 `~/.kimi-code`、Harness UI 状态和用户工作区原位。
- 发布验收同时覆盖已有线程、空会话、设置/模型弹层和工作区选择器。
- 皮肤切换通过共享状态和 CSS 变量完成，保持 backend 连接连续。
- 本机安装始终来自统一正式 Release；开发构建留在 worktree，不进入正式 Applications 路径。

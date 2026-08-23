# 2026-08-23：DSH Desktop 本机恢复与验收

## 根因

DSH 官方本体、Harness UI bridge、个人图标和旧皮肤插件曾分别更新。只替换官方 Bundle 会暂时失去 bridge 与个人图标；继续加载旧皮肤插件又会形成第二套皮肤状态。输入框文本颜色也需要专门覆盖用户输入层，Agent 消息层的可读性规则无法自动覆盖它。

## 正确恢复路径

1. 安装上游 `2.0.2` 官方 macOS 本体。
2. 从同一统一 Release 应用 Harness UI bridge，并从 `~/.dsh/personalization/dsh-desktop/icon.icns` 恢复个人图标。
3. `dsh-harness-ui-skins` 作为唯一共享皮肤 bridge，消费 Harness UI 的 catalog/state/API。
4. 菜单栏提供“皮肤”、完整素材库、立即同步和 `Cmd+Shift+N`；完整素材库进入 Harness UI 原生窗口。
5. 用户输入 textarea 使用独立高对比前景色，背景素材亮度变化时仍保持可读。

## 本机验收记录

- 已安装版本：`2.0.2`；正式安装路径：`/Applications/DSH Desktop.app`。
- Bundle 图标与外置个人图标保持一致，更新后 Dock/Finder 继续显示个人图标。
- 用户输入测试文字以深色清晰显示，测试草稿在验收后清空。
- 菜单栏“皮肤”与 Kimi、Harness UI 指向同一份 `408` 素材目录和当前选择。
- 一次 `Cmd+Shift+N` 让 Kimi 与 DSH 同步到相同下一张素材。
- `Cmd+W` 关闭窗口并保留 DSH 服务；`Cmd+Q` 退出 DSH 与本地服务。

## 持续规则

- 更新顺序固定为“官方本体 → bridge → 外置图标 → 重新签名 → 原子替换”。
- 更新器只处理 App Bundle 与 bridge，保留 `~/.dsh` 中的配置、会话、图标和 Harness UI 状态。
- 当前 bridge 保持唯一；退役插件在确认没有 profile 引用后清理。
- DSH 与 Kimi 共同使用模型上下文契约，历史会话仍引用的模型别名保持可用。

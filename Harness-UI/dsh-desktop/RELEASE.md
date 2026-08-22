# DSH Desktop

本 Release 直接镜像 anywhere-labs/deepseek-harness-desktop 同版本的官方 macOS 与 Windows 安装包，DSH 版本号始终与官方上游一致。

`DSH-Desktop-*-HarnessUI-bridge.zip` 是同版本的本机桥接包，不建立第二条 DSH 版本线。它为 macOS 增加普通 App 菜单中的更新入口、HarnessUI 同步和外置个性化保留：

```bash
dsh-desktop/install-bridge-macos.sh
dsh-desktop/install-bridge-macos.sh --apply
```

如需在新电脑带入自定义图标，可在 DSH 完全退出后执行：

```bash
dsh-desktop/install-bridge-macos.sh --apply --icon /绝对路径/icon.icns
```

桥接默认安装位置是 `~/Applications/DSH Desktop.app`；更新器从当前运行的 App 推导替换目标，因此用户也可通过 `DSH_DESKTOP_APP` 指定自己的安装位置。更新仅替换 App Bundle；`~/.dsh`、`~/.harness-ui`、配置、会话、皮肤、素材和外置图标保持原位。安装桥不会启动或重启 DSH。
本地桥接后的 macOS App 固定使用 `ai.deepseek.dsh.desktop` 代码要求，后续同类更新不再因临时 ad-hoc 身份变化而漂移。

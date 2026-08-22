# dsh-harness-ui-skins

DSH 的 Harness UI 适配器。控制器必须先在 `127.0.0.1:3099` 运行；插件不读取 SMB 密码，也不打包任何图片。

macOS 桥接后的 DSH 菜单栏包含独立“皮肤”菜单。菜单、窗口右下角选择器、Harness UI 与
Kimi Code 都读取 `~/.harness-ui/catalog.json` / `state.json`，切换、轮播、同步和完整素材库
不维护第二份状态。浅色、深色和“降低透明度”模式分别保留可读文字与实体输入表层。

安装器会把本目录放到用户的 `.dsh/plugins/`，登记 desktop profile dependency、bundle，并让 profile 的 `node_modules` 可直接解析插件：

```bash
node scripts/install-dsh.mjs
node scripts/install-dsh.mjs --apply
```

第一条只预览目标，第二条才安装。旧插件和 profile package 会保存在
`~/.dsh/_harness-ui-backups/`。安装后由用户自行完全退出并重新打开 DSH；安装过程不会自动重启宿主。

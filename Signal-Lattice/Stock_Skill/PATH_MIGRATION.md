# Stock Skill 路径迁移

自 `2026-07-30` 起，MetaDatabase 中股票类 Skill 的唯一 Git 路径为：

```text
Signal-Lattice/Stock_Skill/
```

仓库根目录 `Stock_Skill/` 是禁止存在的 legacy 路径。`REGISTRY.json`、根发现文档、CI、registry validator 与公开安全扫描都以新路径为准；新增股票 Skill 也只能在此目录创建。

各 Skill 的 `archives/`、`releases/` 与已封存 `task-pack/` 中可能保留旧路径文字或旧 ZIP 字节。这些是不可变历史证据，不是当前路由、安装源或有效 Git 位置；不得为消除历史字符串而篡改其 Hash 或重新解释其版本。

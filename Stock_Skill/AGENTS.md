# Stock_Skill Agent Contract

本目录是 MetaDatabase 内所有股票类 Codex Skill 的规范集合。

## 版本判定

1. 先读仓库根 `AGENTS.md` 和本文件。
2. 读取 `REGISTRY.json`，再从仓库根运行 `python3 Stock_Skill/scripts/validate_registry.py`。
3. 只有 validator 为 `PASS` 时，才能引用 registry 的 `latest_version`。
4. 任一 registry、`VERSION`、Skill ID、release SHA 或路径不一致，都必须 fail closed 为 `UNKNOWN`。

当前登记：`stock-commercial-opportunities`（股票商业机会拆解）的唯一最新版本为 `3.0.0`（v3）。
`1.0.0` 与 `2.0.0` 只允许作为 `archives/` 中的不可变历史，不得称为最新、默认恢复版本或安装目标。

## 修改边界

- 每个 Skill 项目放在 `Stock_Skill/<project>/`；实际 Skill 文件夹名必须等于稳定 ID。
- 新版本必须同步更新 `REGISTRY.json`、项目与任务包 `VERSION`、release SHA、SOURCE_INVENTORY、CHANGELOG 和 manifests。
- 更新后必须运行 registry validator、项目测试、strict validators、hash/ZIP 检查和公开安全扫描。
- 本目录是 source-only backup，不是安装目录；禁止写入本机 Skill 运行时。
- MetaDatabase 公开可见；不得提交账户、交易、组合、客户、付费数据、MNPI、凭据、会话或本机路径证据。

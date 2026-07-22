# Stock_Skill Agent Contract

本目录是 MetaDatabase 内所有股票类 Codex Skill 的规范集合。

## 版本判定

1. 先读仓库根 `AGENTS.md` 和本文件。
2. 读取 `REGISTRY.json`，再从仓库根运行 `python3 Stock_Skill/scripts/validate_registry.py`。
3. 只有 validator 为 `PASS` 时，才能引用 registry 的 `latest_version`。
4. 任一 registry、`VERSION`、Skill ID、release SHA 或路径不一致，都必须 fail closed 为 `UNKNOWN`。

Active registry 使用 schema `1.1`，版本字段合同如下：

- 每个 entry 的 `version_scheme` 都是必需、大小写敏感的字符串；唯一允许值为 `semver` 和
  `numeric-quad`，禁止隐式默认或未知 scheme。
- `semver` 是 canonical 三段数字子集，例如 `3.0.0`；`numeric-quad` 是 canonical 四段数字，例如
  `0.0.0.1`。每段必须是 `0` 或不以零开头的十进制整数（禁止前导零）；禁止 `v`、空白、符号、prerelease、build
  metadata、补零或截断。
- `latest_major` 必须是与版本首段相等的 JSON integer，boolean 不合法。版本解析和排序只允许在同一
  scheme 内按整数 tuple 进行；跨 scheme 比较必须失败。
- `superseded_archives` 必须存在且为数组，首版允许 `[]`。archive 继承父 entry 的 scheme、不得包含
  自己的 `version_scheme`，每个版本必须唯一且严格早于 `latest_version`。
- Validator current 输出对 `semver` 保留 major shorthand（`3.0.0` → `v3`）；`numeric-quad` 使用完整
  展示（`0.0.0.1` → `v0.0.0.1`，不得写成 `v0`）。release 文件名一律使用完整 `v<version>`。

当前登记：`stock-commercial-opportunities`（股票商业机会拆解）的唯一最新版本为 `3.0.0`（v3）。
`1.0.0` 与 `2.0.0` 只允许作为 `archives/` 中的不可变历史，不得称为最新、默认恢复版本或安装目标。

待激活项目：`bottleneck-serenity-skill` 冻结使用 `version_scheme=numeric-quad`、机器版本 `0.0.0.1`、
展示/release label `v0.0.0.1` 和空 archive 数组。在完整 source、真实 release SHA、manifest 与 entry
同时写入并通过 validator 前，它不是 active/current registry 项；目录或 Task Pack 存在不构成登记证据。

## 修改边界

- 每个 Skill 项目放在 `Stock_Skill/<project>/`；实际 Skill 文件夹名必须等于稳定 ID。
- 新版本必须同步更新 `REGISTRY.json`、项目与任务包 `VERSION`、release SHA、SOURCE_INVENTORY、CHANGELOG 和 manifests。
- 更新后必须运行 registry validator、项目测试、strict validators、hash/ZIP 检查和公开安全扫描。
- 本目录是 source-only backup，不是安装目录；禁止写入本机 Skill 运行时。
- MetaDatabase 公开可见；不得提交账户、交易、组合、客户、付费数据、MNPI、凭据、会话或本机路径证据。

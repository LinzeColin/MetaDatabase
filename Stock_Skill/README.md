# Stock Skill Registry

MetaDatabase 的股票类 Codex Skill 规范集合。人工先看本页，agent 与自动化以 `REGISTRY.json` 为机器可读索引，并用 validator 验证所有重复声明没有漂移。

## 当前版本

| Stable ID | 中文名 | Version scheme | 唯一最新版本 | 规范项目路径 | 分发状态 |
|---|---|---|---:|---|---|
| `stock-commercial-opportunities` | 股票商业机会拆解 | `semver` | `3.0.0`（v3） | `Stock_Skill/stock-commercial-opportunities-skill/` | source-only，禁止本地安装 |
| `bottleneck-serenity-skill` | bottleneck-serenity-skill | `numeric-quad` | `0.0.0.1`（v0.0.0.1） | `Stock_Skill/bottleneck-serenity-skill/` | source-only，禁止本地安装 |

v1 (`1.0.0`) 与 v2 (`2.0.0`) 只作为不可变历史 ZIP 保存在项目 `archives/` 中；它们不是当前版本、默认恢复源或安装目标。

`bottleneck-serenity-skill=0.0.0.1` 使用完整展示/release label `v0.0.0.1`，首版 archive 数组为 `[]`；
其 current 状态由 canonical source、真实 release SHA、两个 manifest、发现文档和 registry validator
共同证明，不构成本机安装或自动交易能力。

## Schema `1.1` 版本模型

每个 registry entry 必须显式声明大小写敏感的 `version_scheme`。Schema `1.1` 不支持缺字段时回退到
`semver`，也不把三段与四段版本互相转换。

| 字段/行为 | `semver` | `numeric-quad` |
|---|---|---|
| Canonical machine grammar | 三段非负整数，如 `3.0.0` | 四段非负整数，如 `0.0.0.1` |
| Validator current label | major shorthand：`v3` | 完整版本：`v0.0.0.1` |
| Release label | 完整 `v3.0.0` | 完整 `v0.0.0.1` |
| 比较 | 仅与 `semver` 按整数 tuple 比较 | 仅与 `numeric-quad` 按整数 tuple 比较 |

两个 grammar 都要求每段为 `0` 或不以零开头的十进制整数。机器字段禁止 `v`、空白、正负号、前导零、
prerelease、build metadata 或其他 suffix；`latest_major` 必须是与版本首段相等的 JSON integer，boolean
不合法。

`superseded_archives` 是必需数组但允许为空。每个 archive 继承父 entry 的 scheme，不得自行声明
`version_scheme`；其版本必须 canonical、唯一且严格早于 `latest_version`。缺失/未知 scheme、错误类型或
arity、跨 scheme 比较、非法 archive，或 registry、identity、`VERSION`、路径、release SHA、manifest
任一冲突，都会使 validator 非零退出；此时 current/latest 必须报告为 `UNKNOWN`，不得猜测。

## 确定性检查

从 MetaDatabase 仓库根运行：

```bash
python3 Stock_Skill/scripts/validate_registry.py
```

预期输出包含：

```text
PASS: stock Skill registry valid
CURRENT: stock-commercial-opportunities=3.0.0 (v3)
CURRENT: bottleneck-serenity-skill=0.0.0.1 (v0.0.0.1)
```

如果 registry、两个 `VERSION` 文件、Skill frontmatter、UI metadata、release/archive SHA 或路径有任何冲突，validator 会非零退出；此时任何 agent 都必须把“最新版本”报告为 `UNKNOWN`，而不是猜测。

## 真源关系

```text
MetaDatabase/AGENTS.md
  -> Stock_Skill/AGENTS.md
    -> Stock_Skill/REGISTRY.json (schema 1.1 + explicit version_scheme)
      -> project VERSION + task-pack VERSION
      -> SKILL.md name + agents/openai.yaml
      -> current release SHA + zero or more inherited-scheme archive SHA
```

`REGISTRY.json` 负责发现和路由；项目文件与制品负责证实。只有全部一致，上表两个版本才是有效的 current
version；source-only current 不等于本机 runtime 安装。

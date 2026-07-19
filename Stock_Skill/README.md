# Stock Skill Registry

MetaDatabase 的股票类 Codex Skill 规范集合。人工先看本页，agent 与自动化以 `REGISTRY.json` 为机器可读索引，并用 validator 验证所有重复声明没有漂移。

## 当前版本

| Stable ID | 中文名 | 唯一最新版本 | 规范项目路径 | 分发状态 |
|---|---|---:|---|---|
| `stock-commercial-opportunities` | 股票商业机会拆解 | `3.0.0`（v3） | `Stock_Skill/stock-commercial-opportunities-skill/` | source-only，禁止本地安装 |

v1 (`1.0.0`) 与 v2 (`2.0.0`) 只作为不可变历史 ZIP 保存在项目 `archives/` 中；它们不是当前版本、默认恢复源或安装目标。

## 确定性检查

从 MetaDatabase 仓库根运行：

```bash
python3 Stock_Skill/scripts/validate_registry.py
```

预期输出包含：

```text
PASS: stock Skill registry valid
CURRENT: stock-commercial-opportunities=3.0.0 (v3)
```

如果 registry、两个 `VERSION` 文件、Skill frontmatter、UI metadata、release/archive SHA 或路径有任何冲突，validator 会非零退出；此时任何 agent 都必须把“最新版本”报告为 `UNKNOWN`，而不是猜测。

## 真源关系

```text
MetaDatabase/AGENTS.md
  -> Stock_Skill/AGENTS.md
    -> Stock_Skill/REGISTRY.json
      -> project VERSION + task-pack VERSION
      -> SKILL.md name + agents/openai.yaml
      -> v3 release SHA + v1/v2 archive SHA
```

`REGISTRY.json` 负责发现和路由；项目文件与制品负责证实。只有全部一致，`3.0.0` 才是有效的 current version。

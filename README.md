# MetaDatabase

母仓库。从 LinzeColin/CodexProject 拆分而来，各项目保留完整提交历史。

## 项目

| 项目 | 状态 | 说明 |
|---|---|---|
| Alpha | ✅ 已迁入 | |
| FIFA | ✅ 已迁入 | |
| QBVS | ✅ 已迁入 | |
| LinzeDatabase | ✅ 已迁入 | 原 CodexProject 中的 MetaDatabase/ 目录（含其内嵌 PFI） |
| SerenityAlipay | ✅ 已迁入 | 目录名 `Serenity-Alipay` |
| EEI | ✅ 已迁入 | 商域帝国（Enterprise Ecosystem Intelligence）；自带 CI：`eei-validation` |
| Stock_Skill/stock-commercial-opportunities-skill | ✅ 3.0.0（v3）当前 | “股票商业机会拆解”Codex Skill 源码、任务包、版本谱系与恢复证据；以 `Stock_Skill/REGISTRY.json` 为机器可读索引，未安装运行时 |
| Stock_Skill/bottleneck-serenity-skill | 🚧 v0.0.0.1 规划中、未登记 | 机器版本 `0.0.0.1`；当前仅推进 Task Pack 与 registry 能力，待完整 source、真实 release SHA、manifest 和 registry entry 在 Stage 2 原子激活后才可成为 current |
| xhs-douyin-2notion | 🚧 Stage 0 | 个人小红书/抖音内容知识治理；Public Code / Private Runtime |
| PFI | ⏳ 待迁入 | codex 正在开发 |
| ADP | ✅ 已迁入 | canonical 路径 `arxiv-daily-push/`；2026-07-20 从 CodexProject 迁入并纳入 `dual-plane.yml` |

## 股票 Skill Registry 版本模型

`Stock_Skill/REGISTRY.json` 使用 schema `1.1`。每个 Skill entry 都必须显式声明 `version_scheme`，不允许
缺字段时默认按某种版本解释：

| Scheme | Canonical 机器版本 | Registry/current 展示 | Release label |
|---|---|---|---|
| `semver` | 三段非负整数，如 `3.0.0` | 保留 major shorthand，如 `v3` | 完整 `v3.0.0` |
| `numeric-quad` | 四段非负整数，如 `0.0.0.1` | 完整 `v0.0.0.1`，不得缩写为 `v0` | 完整 `v0.0.0.1` |

每一段只有单个 `0` 可以以零开头；机器字段不得带 `v`、空白、prerelease、build metadata 或其他
suffix。`latest_major` 必须是版本首段对应的 JSON integer。`superseded_archives` 是必需数组但可以为
`[]`；其中的版本继承父 entry 的 scheme，必须唯一且严格早于 current version。未知/缺失 scheme、错误
arity、前导零、archive 自声明 scheme、跨 scheme 比较，或 identity、路径、版本、SHA、manifest 的任一
冲突都会 fail closed；此时 current/latest 状态只能报告为 `UNKNOWN`。

当前 active entry 仍只有 `stock-commercial-opportunities=3.0.0`（v3，`semver`）。
`bottleneck-serenity-skill=0.0.0.1`（`v0.0.0.1`，`numeric-quad`）目前只是已冻结的待激活版本合同，不能
当作已登记版本。权威判定必须从仓库根运行：

```bash
python3 Stock_Skill/scripts/validate_registry.py
```

## 关于 LinzeDatabase 的命名

原 CodexProject 中存在一个 `MetaDatabase/` 目录，与本仓库同名且语义冲突
（它是元数据/制品聚合层，不是业务项目容器）。迁移时将其改名为 `LinzeDatabase/`，
**完整保留提交历史**，消解命名冲突。其内嵌的 `PFI` 子目录原样保留。

注意：`LinzeDatabase/PFI` 与将来迁入的顶层 `PFI` 项目**不是同一个东西**。

## 治理

治理框架来自共享仓库 [LinzeColin/Governance](https://github.com/LinzeColin/Governance)。
**不要在此复制或分叉治理框架。**

## 许可

专有，保留所有权利。见 LICENSE。

# MetaDatabase

多项目母仓库。从 LinzeColin/CodexProject 拆分而来，各项目保留完整提交历史。
**本仓只放代码与治理；真实个人财务/业务数据存私有仓 `Private-Database/Private-MetaDatabase`**，见 [`WHERE_IS_PROJECT_DATA.md`](WHERE_IS_PROJECT_DATA.md)。

## 项目

| 项目 | 状态 | 说明 |
|---|---|---|
| Alpha | ✅ 已迁入 | |
| ABD | ✅ 已迁入 | 验收/发布治理组件（abd_acceptance） |
| FIFA | ✅ 已迁入 | TAB 世界杯研究流水线；含 sqlite 的私有备份已移入 `Private-MetaDatabase`，仓内仅留 public-safe 件 |
| QBVS | ✅ 已迁入 | |
| LinzeDatabase | ✅ 已迁入 | 原 CodexProject 中的 MetaDatabase/ 目录（含其内嵌 PFI 数据与 MooMooAU）；支付宝流水已移入 `Private-MetaDatabase` |
| SerenityAlipay | ✅ 已迁入 | 目录名 `Serenity-Alipay`；运行时派生数据与含邮箱的通知/报告已移入 `Private-MetaDatabase`，保留公开基金参考 CSV |
| EEI | ✅ 已迁入 | 商域帝国（Enterprise Ecosystem Intelligence）；自带 CI：`eei-validation` |
| Signal-Lattice/Stock_Skill/stock-commercial-opportunities-skill | ✅ 3.0.0（v3）当前 | “股票商业机会拆解”Codex Skill 源码、任务包、版本谱系与恢复证据；以 `Signal-Lattice/Stock_Skill/REGISTRY.json` 为机器可读索引，未安装运行时 |
| Signal-Lattice/Stock_Skill/bottleneck-serenity-skill | ✅ 0.0.0.1（v0.0.0.1）当前 | source-only、`numeric-quad`；canonical source、确定性 release、manifest 与 registry entry 已在 Stage 2 用真实 SHA 激活，未安装本机运行时 |
| Signal-Lattice/Stock_Skill/equity-foresight-signal-skill | ✅ 0.0.0.1（v0.0.0.1）当前 | 股势前瞻；source-only、`numeric-quad`，未安装本机运行时 |
| Signal-Lattice/Stock_Skill/global-equity-lead-lag-atlas | ✅ 0.0.0.1（v0.0.0.1）当前 | 全球股市时序联动图谱；source-only、`numeric-quad`，未安装本机运行时 |
| Signal-Lattice/Stock_Skill/equity-event-atlas | ✅ 0.0.0.1（v0.0.0.1）当前 | 股票事件航图；source-only、`numeric-quad`，未安装本机运行时 |
| social-archive | ✅ 生产在跑 | 个人多平台收藏/点赞/网页归档（B站·抖音·小红书等）。**接手先读** [`social-archive/HANDOFF.md`](social-archive/HANDOFF.md)。旧名 `xhs-douyin-2notion`／代号 `x2n`，见 [`social-archive/docs/migration/LEGACY_MIGRATION.md`](social-archive/docs/migration/LEGACY_MIGRATION.md) |
| PFI | ✅ 已在仓 | 个人财务智能 Streamlit 应用（顶层 `PFI/`，运行时读本机 `~/.pfi/runtime/`）；与 `LinzeDatabase/PFI` 数据目录不是同一个东西 |
| ADP | ✅ 已迁入 | canonical 路径 `arxiv-daily-push/`；2026-07-20 从 CodexProject 迁入并纳入 `dual-plane.yml` |
| CyberBoss | 🚧 Prestage 0 | 全云微信驱动 Codex MVP；唯一代码身份为本仓 `CyberBoss/`，按 AGPL-3.0-only 子树许可推进 |
| Kimi-Code-Desktop | ✅ v0.38.0 | 与 MoonshotAI/Kimi Code `0.38.0` 对齐的跨平台桌面壳；[正式 Release](https://github.com/LinzeColin/MetaDatabase/releases/tag/kimi-code-desktop-v0.38.0) 提供 macOS arm64/x64 与 Windows x64/arm64 资产，子目录采用 MIT License |
| Harness-UI | ✅ v1.0.0 | SMB 驱动的跨平台皮肤控制器与 Kimi/DSH 适配器；[正式 Release](https://github.com/LinzeColin/MetaDatabase/releases/tag/harness-ui-v1.0.0) 不分发图片或 SMB 凭据，子目录采用 MIT License |
| DSH Desktop | ✅ v2.0.2 | 与 anywhere-labs DSH Desktop `2.0.2` 对齐的官方安装器镜像与 Harness UI 桥接包；[正式 Release](https://github.com/LinzeColin/MetaDatabase/releases/tag/dsh-desktop-v2.0.2) 保持官方版本线与外置个性化数据 |

## 股票 Skill Registry 版本模型

`Signal-Lattice/Stock_Skill/REGISTRY.json` 使用 schema `1.1`。每个 Skill entry 都必须显式声明 `version_scheme`，不允许
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

当前 active entries 为 `stock-commercial-opportunities=3.0.0`（v3，`semver`）与
`bottleneck-serenity-skill=0.0.0.1`、`equity-foresight-signal=0.0.0.1`、
`global-equity-lead-lag-atlas=0.0.0.1`、`equity-event-atlas=0.0.0.1`（均为
`v0.0.0.1`，`numeric-quad`）。所有条目均为 source-only，未写入本机 Codex/Agents Skill 运行时。权威判定必须从仓库根运行：

```bash
python3 Signal-Lattice/Stock_Skill/scripts/validate_registry.py
```

预期输出同时包含两个 `CURRENT` 行；任一 source、版本、manifest、release 或 SHA 漂移都会使验证失败。

## 关于 LinzeDatabase 的命名

原 CodexProject 中存在一个 `MetaDatabase/` 目录，与本仓库同名且语义冲突
（它是元数据/制品聚合层，不是业务项目容器）。迁移时将其改名为 `LinzeDatabase/`，
**完整保留提交历史**，消解命名冲突。其内嵌的 `PFI` 子目录原样保留。

注意：`LinzeDatabase/PFI` 与将来迁入的顶层 `PFI` 项目**不是同一个东西**。

## 治理

治理框架来自共享仓库 [LinzeColin/Governance](https://github.com/LinzeColin/Governance)。
**不要在此复制或分叉治理框架。**

### 三款桌面 App 治理

Kimi Code Desktop、Harness UI、DSH Desktop 采用“一套源码、同一提交、一次发布”的协作方式：

- 共享源码只以本仓 `main` 为准；每台电脑均从它创建独立分支并通过 PR 合入。
- [`desktop-suite/COMPATIBILITY_CONTRACT.json`](desktop-suite/COMPATIBILITY_CONTRACT.json) 是三端路径、bundle identity、版本来源、共享皮肤协议与发布标签的机器可读真源。
- `.github/workflows/desktop-app-suite-release.yml` 在同一个 `GITHUB_SHA` 构建并发布三款 App。它先执行契约校验，发布标签始终指向同一提交。
- Harness UI 是共享 `catalog/state` 的唯一 owner；Kimi 与 DSH 读取同一协议，`Cmd/Ctrl+Shift+N` 统一调用 `POST /api/next`。
- API key、账号、会话、SMB 凭据、素材、运行时状态、个人图标和已安装 App 都保留在各电脑本机，发布只包含可公开的源码与应用资产。

## 许可

除带有独立 `LICENSE` 的子目录外，本仓为专有、保留所有权利。`CyberBoss/`
适用其目录内的 GNU AGPL-3.0-only 许可。见根目录及各子目录 `LICENSE`。

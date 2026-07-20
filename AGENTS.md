# MetaDatabase Agent Contract

母仓库，中文优先；代码、API、库名、模型名和错误可保留英文。

## 永久规则

- 治理框架来自共享仓库 LinzeColin/Governance。
  禁止在本仓库内复制、分叉或重建治理框架。
  禁止用 git submodule 引入它 —— 通过 CI checkout 或 pip 安装消费。

## 命名陷阱（务必记住）

- `LinzeDatabase/` 是原 CodexProject 的 `MetaDatabase/` 目录改名而来。
- `LinzeDatabase/PFI` 与将来迁入的顶层 `PFI` 项目**不是同一个东西**，不要合并或互相引用。
- `ADP` 已从 CodexProject 迁入本仓，canonical 路径是 `arxiv-daily-push/`；
  其 CI secrets 名为 `ADP_SMTP_*`。按顶层目录名 `ADP` 去找会一无所获。
- CodexProject 中已删除的 `arxiv-daily-push/` 是迁移后的预期状态，禁止从历史、
  备份或任务包恢复；后续开发只在本仓的 `arxiv-daily-push/` 进行。

## 股票 Skill 路由（强制）

- 股票类 Skill 的仓库真源统一位于 `Stock_Skill/`；禁止在仓库根目录重建同名项目。
- 任何 agent 在声称“最新版本”前，必须先读 `Stock_Skill/REGISTRY.json`，并运行
  `python3 Stock_Skill/scripts/validate_registry.py`。校验失败、未运行或字段冲突时，版本状态只能是 `UNKNOWN`，不得猜测。
- `stock-commercial-opportunities`（股票商业机会拆解）当前唯一最新版本是 `3.0.0`（v3）；
  v1/v2 只在 `archives/` 中作为不可变历史谱系，不是当前版本、安装源或回退默认值。
- 本仓只保存源码和可恢复备份；不得据此写入 `~/.agents/skills` 或 `~/.codex/skills`。

## 迁移状态

本仓库正从 LinzeColin/CodexProject 分批迁入项目。
EEI 已于 2026-07-15 迁入（wave 3，含完整历史与自带 CI `eei-validation`）。
ADP（`arxiv-daily-push/`）已于 2026-07-20 迁入并纳入 `dual-plane.yml`；
canonical 交接入口是 `arxiv-daily-push/docs/HANDOFF.md`。
ADP 当前增量开发合同是 `arxiv-daily-push/docs/pursuing_goal/v1_2/`；它按
单任务 Run Contract 推进，不覆盖 V7.2 的旧本机运行时兼容边界。
PFI 仍在 CodexProject 中；迁入前不要在本仓库创建顶层 `PFI` 占位目录或桩代码。

ADP 历史合同仍以仓根相对路径引用 `FINAL_ACCEPTANCE_BUNDLE/`、
`governance/run_manifests/ADP-*` 和 4 个 `tools/` 只读校验入口；这些是迁入的
ADP 证据/兼容面，不是本仓治理框架。禁止据此复制 CodexProject 的旧
`repository_hygiene_policy.json`、`generate_governance_dashboard.py`、
`validate_project_governance.py` 或 `project-governance.yml`。

## ADP 来源与板块变更门（强制）

Any ADP source or board add/delete/rename/enable/disable change must pass the
user-center sync gate in `arxiv-daily-push/AGENTS.md`. config/code-only changes are not complete
until every required owner-facing page and both named tests are
synchronized in the same change.

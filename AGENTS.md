# MetaDatabase Agent Contract

母仓库，中文优先；代码、API、库名、模型名和错误可保留英文。

## 永久规则

- 代码与数据默认专有，不得以任何开源许可对外发布。
- 治理框架来自共享仓库 LinzeColin/Governance。
  禁止在本仓库内复制、分叉或重建治理框架。
  禁止用 git submodule 引入它 —— 通过 CI checkout 或 pip 安装消费。

## 命名陷阱（务必记住）

- `LinzeDatabase/` 是原 CodexProject 的 `MetaDatabase/` 目录改名而来。
- `LinzeDatabase/PFI` 与将来迁入的顶层 `PFI` 项目**不是同一个东西**，不要合并或互相引用。
- 将来迁入的 `ADP` 在 CodexProject 中的真实路径是 `arxiv-daily-push`，
  其 CI secrets 名为 `ADP_SMTP_*`。按 "ADP" 去找目录会一无所获。

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
PFI / ADP 仍在 CodexProject 中，将在其静默后迁入。
在它们迁入之前，不要在本仓库为它们创建占位目录或桩代码。

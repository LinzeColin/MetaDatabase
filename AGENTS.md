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

## 迁移状态

本仓库正从 LinzeColin/CodexProject 分批迁入项目。
EEI 已于 2026-07-15 迁入（wave 3，含完整历史与自带 CI `eei-validation`）。
PFI / ADP 仍在 CodexProject 中，将在其静默后迁入。
在它们迁入之前，不要在本仓库为它们创建占位目录或桩代码。

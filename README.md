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
| xiaohongshu-douyin-2notion | 🚧 Stage 0 | 个人小红书/抖音内容知识治理；Public Code / Private Runtime |
| PFI | ⏳ 待迁入 | codex 正在开发 |
| ADP | ⏳ 待迁入 | **原 arxiv-daily-push**；codex 正在开发 |

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

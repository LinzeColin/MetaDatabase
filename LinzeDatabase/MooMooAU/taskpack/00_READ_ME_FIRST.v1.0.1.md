# MooMooAU Archive 开发任务包 v1.0.1

- Package ID：`MMAU-ARCHIVE-TP-2026-07-20-V1.0.1`
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 私有数据面：受保护 immutable Repository ID 定位的唯一私有仓；名称不得进入公开树
- 运行时间：每天以 `04:30 Australia/Sydney` 为时区感知调度目标；平台延迟或丢弃由下一次幂等补偿，周日同一任务执行 Full Reconciliation
- 用户入口：Codex 开发线程；Codex Automation 仅为简单、被动、非关键健康检查

## 开发入口

1. 运行只读 `python3 machine/tools/validate_package.py`；
2. 通过 pinned external Governance checkout 运行 `python3 machine/tools/validate_governance.py`；
3. 每次 Run 最多执行一个 Stage；
4. S0 使用 S0AC-* 局部门，AC-* 在所属实现阶段与最终复审强制通过；
5. 未通过 Stage Gate 不进入下一 Stage，不启用 Feature Flag，不访问真实 Gmail 或 Secret；
6. S0–S7、最终复审和修复全部完成后，才从最新 `origin/main` 创建干净快照历史并整体上传。

## 冻结边界

- 只处理确定性双重验证的 Moomoo AU 入站消息；其他邮件不读取完整内容、不下载、不修改；
- 只允许 exact `users.messages.trash`，禁止永久删除和 Thread Trash；
- 只有一个私有数据仓，全部 Raw 与敏感 Processed 在持久化前 age 加密；
- 用户电脑与自建服务器零生产运行、零项目持久化；
- Timeline 健康稳态恰好一个、任何时刻最多一个，失败可短暂为零并确定性修复；
- 真实邮件、附件、密码、Token 与 age 私钥永不进入模型上下文；
- Moomoo Portal、交易 API、下单、Sent/Drafts 永久不在范围内。

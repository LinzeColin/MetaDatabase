# Codex、GitHub Actions 与仓库职责

## 用户入口

用户只回到 **Codex 开发线程**。开发线程读取本任务包和公开 Evidence，修改公开代码、运行测试、审查 PR、触发受保护 `workflow_dispatch`。用户不需要查看或回复 Codex Automation。

## Codex 开发线程

允许：

- 修改 `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU` 和仓根相关 Workflow；
- 调研公开资料、增加合成 Fixture、修复代码、运行测试；
- 读取公开脱敏 Inventory/Evidence；
- 触发受保护手动同步、Reconcile、Reprocess、Recovery Drill；
- 在部署阶段引导一次 OAuth、GitHub App、Secret 和 Recovery Key 下载。

禁止：

- 把真实邮件、附件、PDF 密码、Gmail Token、age 私钥加入模型上下文；
- 自由浏览用户 Gmail；
- 直接决定某封邮件是否 M3；
- 绕过 Acceptance/Feature Flag；
- 在私有仓写代码或重组无关目录。

## GitHub Actions

是唯一权威生产数据面，负责：

- 每日以 04:30 Sydney 为时区感知调度目标；运行逻辑确定且可补偿，不伪称平台保证精确启动；
- Gmail 端点守卫、发现、验证、Raw、处理、age、私有提交、恢复 Gate、M3、Timeline、公开 Evidence；
- 周日 Full Reconciliation；
- 所有安全、测试、混沌和恢复流水线。

## Codex Automation

只配置一个普通、被动、非关键任务：

- 建议时间：每日 04:30 `Australia/Sydney`；
- 读取**上一份已完成**的公开 `evidence/ops/latest.json`；
- 健康且新鲜时不做任何事情；
- 不健康或超过 48 小时时，创建或更新唯一 `moomooau-ops` Issue；
- 不触发 Workflow、不修改代码、不访问 Gmail/私有仓/Secret、不回到原对话；
- Auto 停用或失败不影响 GitHub Actions 数据面。

开发线程设置 Auto 时使用普通 UI/自然语言计划，不实现自定义 Auto 编排、SDK、回调或线程恢复。

## 仓库

| 位置 | 允许 | 禁止 |
|---|---|---|
| 公开 MetaDatabase | 代码、Workflow、测试、Schema、脱敏 Evidence、七文件 | 真实邮件、精确交易数据、Secret、私钥 |
| 单一私有数据仓 | `MooMooAU/` 加密 Raw/Processed/State/Inventory 与 live Release Asset | 代码、Workflow、Agent Prompt、无关路径修改 |

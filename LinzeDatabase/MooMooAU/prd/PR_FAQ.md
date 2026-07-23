# Working Backwards：PR / FAQ

## Press Release

### 标题

MooMooAU Archive 将 Moomoo AU 邮件变成零误伤、可恢复、可复用的私有数据产品

### 发布摘要

MooMooAU Archive 面向只希望通过 Codex 开发线程管理系统的个人投资者。系统每天 04:30 Australia/Sydney 在 GitHub-hosted Runner 上运行，严格验证 Moomoo AU 入站邮件，保存完整 RFC EML 与可复用结构化数据，在进入唯一私有 GitHub 数据仓前全部 age 加密，并在远端恢复成功后仅将该单封来源邮件移入 Gmail Trash。它不在用户电脑保存文件、不部署服务器、不调用交易 API、不保留历史 Timeline 图片，也不让模型接触真实金融邮件。

### 客户问题

过去，报表、股息、安全、税务和营销邮件散落在 Gmail 的不同标签中；PDF 密码、非标准 MIME、时区、模板变化和重复处理让手工归档不可靠。简单自动化又可能误删同一线程或其他邮件。

### 客户结果

用户只需在 Codex 开发线程提出“同步、查看状态或修复”。GitHub Actions 负责确定性数据处理；Codex 负责代码和公开证据。所有真实数据位于唯一私有数据仓的加密对象中，MetaDatabase 下游项目可直接使用版本化 Processed 数据。

## FAQ

### Q1：会不会误伤其他 Gmail 邮件？

设计目标是 0。系统不按主题或显示名删除，必须由精确 verified sender、身份验证对齐和 Moomoo AU 业务指纹同时通过，并在 M3 前再验证一次。未知新地址保持原状。

### Q2：为什么全部 Moomoo 邮件都进入 Trash？

这是用户明确选择的 M3。系统在完整 Raw 已远端加密保存并成功恢复后，按 Message ID 调用 `users.messages.trash`；绝不使用 thread trash 或永久 delete。

### Q3：密码不知道怎么办？

Moomoo PDF 内部密码只影响结构化解析，不影响完整 EML、原始附件、age 加密、远端恢复和 M3。状态记为 `WAITING_FOR_PDF_PASSWORD`，以后可重处理。

### Q4：数据放在哪里？

代码永久在公开 `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`；数据只在受保护 immutable Repository ID 定位的同一个私有仓 `MooMooAU/` 命名空间。公开树不保存私有仓名称，也没有第二仓。

### Q5：我的电脑需要运行吗？

不需要。生产只用 GitHub-hosted Runner 的临时内存/tmpfs，不安装本地脚本，不使用本地计划任务或自建服务器。

### Q6：Codex 与 GitHub 各自做什么？

Codex 开发线程负责理解需求、修改公开代码、测试、修复和审查公开 Evidence。GitHub Actions 是权威确定性数据面，负责 Gmail、加密、私有写入、M3 和 Timeline。Codex Automation 只做简单被动健康检查，停用也不影响生产。

### Q7：为什么只保留一张 Timeline？

为避免二进制历史、LFS 和缓存污染。系统在固定 `moomooau-live` Release 中串行替换唯一的 `timeline-latest.png.age`：健康稳态恰好一个、任何时刻最多一个；删除后上传失败时为零并由下一次运行从 Processed Snapshot 确定性修复。历史事实已存在于 Processed 数据，不重复保存图片。

### Q8：为什么不是每小时运行？

每天 04:30 Sydney 足以覆盖报表与通知，显著降低 API、仓库和运维噪声；周日同一任务做 Full Reconciliation，开发线程也可触发 `workflow_dispatch`。

### Q9：Blocked 地址能否直接检查？

标准 Gmail API不提供独立枚举 Blocked Addresses 的接口。系统通过 Spam、Trash 和 Filters 只读审计覆盖可观测结果，不作无法验证的声明。

### Q10：何时停止系统？

任何误伤、公开泄漏、Raw 恢复不一致、禁止端点调用、Recovery Key 失效或真实数据进入模型都会立即触发 Kill Criteria。

# ABD S06/P04 每日邮件审计

<!-- ABD_DAILY_AUDIT_CONTRACT
{"contract_id":"AC-S06-P04","stage_id":"S06","phase_id":"P04","scheduled_local_time":"06:00","evaluation_mode":"DATA_ONLY_NO_SCHEDULER_OR_WAIT","gmail_mutation_default":"DISABLED","permanent_delete_capability":false,"real_time_soak_required":false,"raw_data_repository_write":"PROHIBITED","private_archive_area":"Private-MetaDatabase/ABD"}
-->

## 目的

本手册定义每天 06:00 本地时钟标签下的审计输入和报告格式。实现把时钟当作冻结数据评估；它不启动定时器、不等待 06:00、也不因观察期未结束而阻塞开发、验收或部署门。

审计只读取经过脱敏的决策元数据、请求键和归档校验状态。原始 EML、附件内容、令牌、账户标识和私有归档路径不得写入本代码仓、测试报告或验收摘要。

## 固定输入

1. P02 已通过的归档和本地 readback 校验结果。
2. P03 的附件解析与隔离结果；P03 静态检查不等同于生产杀毒放行。
3. 每个附件独立的 malware attestation，且 attachment_id 与 SHA-256 必须逐项匹配。
4. 发件人状态必须为 KNOWN_ALLOWLISTED，认证状态必须为 PASS。
5. P04 的决策、垃圾箱请求键和无副作用执行回执。

任一项缺失、冲突、未知、重复、哈希不匹配或不安全，报告 action 必须为 ESCALATE；邮件保持或隔离，不能生成垃圾箱动作。

## 06:00 数据审计规则

审计函数接收 scheduled_local_time=06:00 和 observed_local_time 两个明确输入，并产生以下之一：

- AUDIT_PASS / action NONE：所有决策结构有效、请求键唯一，且没有需要补救的 KEEP 决策。
- AUDIT_REMEDIATION_REQUIRED / action ESCALATE：存在 KEEP、隔离、重复请求键、无效记录或无法识别状态。
- AUDIT_CONFIGURATION_INVALID 或 AUDIT_INPUT_INVALID / action ESCALATE：时间或输入结构不符合合同。

AUDIT_PASS 不代表 Gmail 已发生变更。只有经过单独授权的运行时适配器可消费已授权请求；本阶段的默认运行路径始终输出 TRASH_REQUEST_READY_NO_MUTATION。

## 修复报告最小字段

每次审计报告至少保存以下脱敏字段：

- contract_id、固定时钟标签、scheduled_local_time、observed_local_time；
- status、action、findings code 和 message reference；
- 每项对应的修复建议：重新保存、重新 readback、重新解析、补充 malware attestation、恢复或人工升级；
- gmail_mutation_performed=false、permanent_delete_performed=false、real_time_waited=false；
- 输入与输出的 SHA-256 引用，而不是原始邮件或附件。

## 停止与升级

出现证据完整性失败、需要不可逆操作、未知发件人、认证失败、恶意或未通过 attestation、来源/法律合同冲突、或新增现金成本时，停止自动推进，保持邮件和归档不变，并升级给账户持有人。

本阶段不提供永久删除接口、批量删除接口、删除重试、账号读取、定时守护进程或真实时间 soak。

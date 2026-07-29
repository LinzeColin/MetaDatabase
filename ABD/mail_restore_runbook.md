# ABD S06/P04 Gmail 垃圾箱恢复运行手册

<!-- ABD_RESTORE_RUNBOOK_CONTRACT
{"contract_id":"AC-S06-P04","stage_id":"S06","phase_id":"P04","restore_method":"users.messages.untrash","restore_mode":"REQUEST_ONLY_NO_MUTATION","permanent_delete_capability":false,"requires_archive_readback":true,"requires_confirmed_trash_receipt":true,"real_time_soak_required":false,"raw_data_repository_write":"PROHIBITED"}
-->

## 范围与安全默认

本手册只覆盖已移动到 Gmail 垃圾箱后的可恢复请求规划。它不执行真实 Gmail 调用、不读取认证令牌、不启动轮询或定时器，也不提供永久删除能力。

恢复前必须先验证私有平面的 P02 归档：原始邮件、头、全部附件、清单、SHA-256 与本地 readback 全部通过。恢复请求只能使用 users.messages.untrash；users.messages.delete、users.messages.batchDelete、threads.delete 和任何永久删除能力均禁止。

## 可恢复性检查清单

1. 读取 P04 决策的 gmail_message_id 与 trash_request_key，不接受手工拼接的标识。
2. 重新执行 P02 归档和 readback 校验；失败时返回 RESTORE_BLOCKED_KEEP。
3. 确认存在经授权运行时适配器报告的垃圾箱回执；没有确认回执不能生成恢复请求。
4. 校验恢复方法仍为 allowlist 中的 users.messages.untrash。
5. 生成 RESTORE_REQUEST_READY_NO_MUTATION，记录不含原始内容的请求摘要与哈希。
6. 若未来有经过单独批准的运行时适配器，适配器必须在其自身审计边界内执行；本阶段不把该副作用计为测试、证据或上线完成。

## 失败处置

以下任一情况必须保持邮件和归档不变，返回 RESTORE_BLOCKED_KEEP，并在每日审计中生成 ESCALATE：

- 归档、清单、哈希或 readback 缺失、篡改或不一致；
- 垃圾箱回执缺失、未知、重复或与请求键不匹配；
- 标识、方法、证据或权限合同无效；
- 需要永久删除、批量删除、重试真实订单、或外部付费资源；
- 任何不利输入扰动下的结果不再确定。

## 回滚

关闭垃圾箱运行时适配器并将默认路径保持为 TRASH_REQUEST_READY_NO_MUTATION。保留不可变 P02 归档、P03 隔离结果、P04 决策和结构化失败日志；重放冻结输入以重建派生状态。回滚不删除、覆盖或迁移原始邮件/附件，也不需要真实时间 soak。

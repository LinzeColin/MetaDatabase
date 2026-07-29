# ABD S06/P02 原件与附件双阶段保存

此制品只定义原件、头部和附件的私有平面保存与读回验证。它不调用 Gmail、不启动轮询、不等待真实时间、不扫描附件，也不把任何邮件移入垃圾箱。

<!-- ABD_ARCHIVE_LAYOUT_CONTRACT
{"archive_directory":"mail-archive-v0.0.0.1","archive_layout_version":"1.0.0","contract_id":"AC-S06-P02","gmail_mutation_in_p02":"PROHIBITED","manifest":"manifest.json","private_database_area":"Private-MetaDatabase","private_database_domain":"ABD-mail-archive","private_db_client_execution_in_p02":false,"raw_data_repository_write":"PROHIBITED","real_time_soak_required":false,"requirement_id":"REQ-S06-P02","schema":"mail_manifest.schema.json","stage":"S06","trash_action":"KEEP_PENDING_SECURITY_AND_TRASH_GATES"}
-->

## 私有数据路由

原始 `.eml`、附件和头部属于业务/运行时数据，**绝不提交到 MetaDatabase 代码仓**。生产适配器只可经 `KMOS/KMDatabase/machine/tools/private_db_client.py` 访问 `Private-MetaDatabase`，逻辑 domain 为 `ABD-mail-archive`；禁止 clone 私有仓，也禁止把令牌、cookie、会话或原件写入本仓。

S06/P02 仅构造并验证本地的私有平面 bundle。适配器执行、附件安全扫描和 Gmail 垃圾箱动作分别属于后续受控 phase；本 phase 的任何结果都是 `KEEP_PENDING_SECURITY_AND_TRASH_GATES`。

## Bundle 布局

私有根必须包含 `Private-MetaDatabase/ABD`，其下采用以下稳定布局：

```text
Private-MetaDatabase/ABD/
└── mail-archive-v0.0.0.1/
    ├── .staging/                         # 仅同文件系统的短暂原子提交区
    └── records/<gmail_message_id>/
        ├── raw.eml                       # 原始消息字节
        ├── headers.json                  # 规范化头部快照
        ├── attachments/
        │   └── <attachment_id>.bin       # 文件名不参与路径决策
        └── manifest.json                 # 所有对象 SHA-256 与读回状态
```

目录先在 `.staging/` 写全：原件、头部、所有附件和 manifest 全部哈希后，才原子改名为 `records/<gmail_message_id>/`。已有同一消息 ID 时：内容完全一致只能幂等读回；任一字节、清单或哈希不一致一律 `INTEGRITY_CONFLICT_KEEP`，绝不覆盖既有 bundle。

## 通过与恢复边界

P02 的读回验证必须重新读取 `raw.eml`、`headers.json` 和每个附件，并逐一比对 manifest SHA-256。任何缺件、路径逃逸、重复附件 ID、无效 manifest 或哈希不一致都会返回 `KEEP`；不会尝试 Gmail trash、永久删除或自动重试。

“每 15 分钟”仅是下一次采集的确定性 cadence 数据（900 秒），不是 soak、等待或上线前观察期。函数只能计算是否 `DUE`，不得睡眠或阻塞核心服务。

## 回滚

关闭邮件归档功能即可停止新 bundle；已完成的不可变私有 bundle 保留原样供读回。失败的 staging 目录不成为最终 record，源邮件保持不变并继续 `KEEP`。

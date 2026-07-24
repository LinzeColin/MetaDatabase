# 数据模型与血缘

## 1. Private Raw

```text
MooMooAU/Raw/messages/YYYY/MM/<opaque_message_id>.eml.age
MooMooAU/Raw/objects/<prefix>/<opaque_object_id>.bin.age
```

完整 EML 是 Canonical Raw；拆出的附件对象用于复用。Raw append-only，不覆盖、不重命名、不静默重新加密。

## 2. Private Processed

```text
MooMooAU/Processed/document_envelopes/v1/
MooMooAU/Processed/statements/v1/
MooMooAU/Processed/transactions/v1/
MooMooAU/Processed/cash_flows/v1/
MooMooAU/Processed/fx/v1/
MooMooAU/Processed/dividends/v1/
MooMooAU/Processed/corporate_actions/v1/
MooMooAU/Processed/timeline_events/v1/
```

每个数据集同时可生成：

- Canonical JSON/JSONL：无损、易迁移；
- Partitioned Parquet：供分析和跨项目消费。

全部 `.age`。

## 3. 必备血缘字段

| 字段 | 含义 |
|---|---|
| `source_id` | 私有 Opaque Raw 标识 |
| `source_message_id_hmac` | 不可公开反推的消息标识 |
| `raw_ciphertext_digest` | 密文摘要 |
| `raw_plaintext_digest_private` | 私有完整性摘要 |
| `attachment_object_ids` | 关联附件对象 |
| `parser_name` / `parser_version` | 解析器及版本 |
| `schema_version` | 输出契约版本 |
| `imported_at_utc` | 导入时间 |
| `field_lineage` | 字段来自 Subject/Filename/PDF/Table 等 |
| `processing_state` | COMPLETE/WAITING/UNSUPPORTED/QUARANTINED |
| `key_epoch` | age Recipient Epoch |

## 4. Timeline Event

- `statement_label_date`；
- `email_internal_date_utc`；
- `email_received_at_sydney`；
- `date_header_observed`；
- `calendar_lag_days`；
- `elapsed_hours`；
- `us_market_session_lag`；
- `label_state_at_discovery`；
- `m3_state`；
- `document_class`；
- `expectation_state`；
- `parser_state`。

未知值使用 `null` 和原因码，禁止猜测。

## 5. Private Timeline Publish State

单一私有仓内以 age 加密保存当前发布状态，不保存图片副本：

- `processed_snapshot_root`；
- `timeline_plaintext_sha256`；
- `timeline_ciphertext_sha256`；
- `release_asset_id` 与固定名称；
- `publish_state`（`HEALTHY` / `TIMELINE_REPAIR_REQUIRED`）；
- `verified_at_utc` 与 `key_epoch`。

该状态只用于证明当前 Asset、Snapshot 与恢复结果一致；若状态与远端不一致，以重新下载、解密和确定性重建为准，不猜测为健康。

## 6. Public Inventory

仅允许：数据集名、Schema/Parser 版本、available/degraded/unavailable、数量桶 `0/1–9/10–99/100+`、新鲜度桶 `<24h/1–7d/>7d`、Opaque Root、测试与恢复结论。

禁止：精确数量/日期、发件人、主题、文件名、Message ID、账户、Ticker、金额、私有路径和 Commit URL。

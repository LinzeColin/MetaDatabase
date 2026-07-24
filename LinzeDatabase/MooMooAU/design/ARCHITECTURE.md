# 技术架构

## 1. 架构目标

- 零误伤其他 Gmail 邮件；
- 用户电脑、自建服务器和本地持久化为 0；
- 真实金融数据不进入模型；
- 单一私有数据仓、单一最新 Timeline；
- 远端可恢复后才执行 M3；
- 公开代码与证据可审查，私有数据全加密。

## 2. 逻辑架构

```text
┌──────────────────────────────────────────────┐
│ User                                         │
│ only interacts with Codex development thread │
└───────────────────┬──────────────────────────┘
                    │ requirements / review / repair
                    ▼
┌──────────────────────────────────────────────┐
│ Public control & code plane                  │
│ LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU            │
│ code, workflows, tests, schemas, redacted    │
│ inventory/evidence, dual-plane documents     │
└───────────────────┬──────────────────────────┘
                    │ 04:30 Australia/Sydney
                    ▼
┌──────────────────────────────────────────────┐
│ Deterministic data plane                     │
│ GitHub-hosted ephemeral runner               │
│ endpoint guard → discovery → verification    │
│ RAW → parse/defer → age → remote recovery    │
│ → exact message Trash → timeline → evidence  │
└──────────┬────────────────┬──────────────────┘
           │                │
           ▼                ▼
┌───────────────────┐  ┌───────────────────────┐
│ Gmail API         │  │ Single private repo   │
│ list/get/history  │  │ current KMFA-Private- │
│ filters/trash     │  │ Runtime → private-    │
└───────────────────┘  │ database / MooMooAU/  │
                       └───────────────────────┘
```

## 3. 组件

| 组件 | 输入 | 输出 | 信任边界 |
|---|---|---|---|
| Scheduler | 04:30 Sydney / workflow_dispatch | Run Context | GitHub |
| Gmail Endpoint Guard | 方法、路径、参数 | 允许/拒绝 | OAuth Token 前 |
| Candidate Discovery | History/List/Filters | 最小候选 | 不读取未知完整正文 |
| Verification Engine | 最小头信息、认证结果、注册表、模板指纹 | VERIFIED/UNKNOWN/REJECTED | 两次独立运行 |
| Raw Fetcher | Verified Message ID | RFC EML bytes | Gmail → tmpfs |
| Attachment Inspector | MIME parts | typed/quarantined objects | 不执行内容 |
| Processor | Raw + optional PDF Secret | versioned JSON/Parquet or WAITING | Parser sandbox |
| Age Encryptor | sensitive bytes + public Recipient | `.age` stream | 加密前不持久化 |
| Private Repo Writer | ciphertext + manifests | remote Commit/Release | short-lived GitHub App token |
| Recovery Gate | remote ciphertext + Identity | byte equality verdict | protected environment |
| M3 Mutator | verified Message ID + Gate proof | TRASH label | exact message only |
| Timeline Renderer | Processed timeline facts | one encrypted PNG | fixed deterministic container |
| Public Evidence Publisher | private opaque roots + test status | redacted JSON | no sensitive fields |

## 4. 关键状态机

```text
DISCOVERED
→ MINIMAL_VERIFIED
→ RAW_FETCHED
→ RAW_HASHED
→ ATTACHMENTS_CLASSIFIED
→ PROCESSED | WAITING_FOR_PDF_PASSWORD | UNSUPPORTED
→ AGE_ENCRYPTED
→ PRIVATE_COMMITTED
→ REMOTE_RECOVERY_VERIFIED
→ SECOND_VERIFIED
→ TRASH_ELIGIBLE
→ MESSAGE_TRASHED | ALREADY_TRASHED
→ TIMELINE_UPDATED_OR_UNCHANGED
→ PUBLIC_EVIDENCE_PUBLISHED
→ COMPLETE
```

任何不一致进入：`UNVERIFIED`、`QUARANTINED`、`DEGRADED` 或 `ERROR`，且不 M3。

## 5. 一致性与幂等

- Opaque Message ID = HMAC(project secret, Gmail Message ID)，真实 ID 不公开；
- Raw object ID = HMAC/private content digest，避免公开可枚举 SHA；
- 私有 Commit 先于公开 Evidence；
- 重跑以状态和内容 ID 判定，不重复生成逻辑对象或调用 Trash；
- Timeline 仅当已验证私有发布状态不能证明同一 Snapshot Root 与现有资产明文摘要一致时重绘；age 随机密文不作为变化依据；
- Raw append-only，Processed 新版本并行保存。

## 6. 可靠性

- 429/5xx 指数退避和抖动；
- GitHub Push 冲突 fetch/rebase/retry；
- History 404 Full Reconcile；
- 公共 Evidence 补偿；
- Timeline 保留上一已验证 Asset；
- Mutation Budget 和 Feature Flag；
- Kill Criteria 自动关闭破坏性路径。

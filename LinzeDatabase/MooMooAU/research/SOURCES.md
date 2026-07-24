# 公开调研来源

## SRC-001 — GitHub Spec Kit

- 类型：public_project
- URL：https://github.github.com/spec-kit/
- 本项目用途：借鉴 Spec → Plan → Tasks → Implement、结构化模板、跨制品一致性检查；不引入其 CLI 作为运行时依赖。

## SRC-002 — BMAD Method

- 类型：public_project
- URL：https://github.com/bmad-code-org/BMAD-METHOD
- 本项目用途：借鉴 Working Backwards、PRD/PRFAQ、按复杂度自适应、测试架构和多角色互审；不复制多代理运行时。

## SRC-003 — Got Your Back (GYB)

- 类型：public_project
- URL：https://github.com/GAM-team/got-your-back
- 本项目用途：借鉴 Gmail API 全量/增量备份、RFC 邮件原件保留和恢复思路；拒绝本地持久化与本地 cron。

## SRC-004 — Paperless-ngx

- 类型：public_project
- URL：https://github.com/paperless-ngx/paperless-ngx
- 本项目用途：借鉴邮件规则、processed-mail 去重、未知类型隔离和文档生命周期；不部署常驻服务。

## SRC-005 — age

- 类型：public_project
- URL：https://github.com/FiloSottile/age
- 规范证据：https://github.com/C2SP/C2SP/blob/6f65019ab73fd5dafbfe6a27cf508ef5c134cbb9/age.md
- 本项目用途：采用流式 X25519 Recipient 加密；运行时只需公开 Recipient，恢复身份不写入 Git。规范要求每文件新随机文件密钥、Nonce 和临时秘密，因此逻辑幂等不比较密文字节。

## SRC-006 — SOPS

- 类型：public_project
- URL：https://github.com/getsops/sops
- 本项目用途：借鉴密钥轮换、云 KMS 与加密配置治理；本项目大对象仍直接使用 age，避免引入多余格式层。

## SRC-007 — OpenMetadata

- 类型：public_project
- URL：https://github.com/open-metadata/OpenMetadata
- 本项目用途：借鉴目录、所有权、质量和血缘模型；只实现无常驻服务的轻量公开 Inventory/Schema/Evidence。

## SRC-008 — DataHub

- 类型：public_project
- URL：https://github.com/datahub-project/datahub
- 本项目用途：借鉴数据产品、版本化 Schema 和跨项目消费契约；不部署数据库、搜索或消息中间件。

## SRC-009 — OpenLineage

- 类型：public_project
- URL：https://github.com/OpenLineage/OpenLineage
- 本项目用途：借鉴输入、运行、输出三元血缘模型和可重放 Run Event；实现精简私有 lineage manifest。

## SRC-010 — in-toto

- 类型：public_project
- URL：https://github.com/in-toto/in-toto
- 本项目用途：借鉴供应链步骤声明、材料/产物摘要和可验证证据；公开面只发布脱敏声明。

## SRC-011 — Pandera

- 类型：public_project
- URL：https://github.com/unionai-oss/pandera
- 本项目用途：借鉴 DataFrame/Parquet 字段、类型和统计约束；同时保留 JSON Schema 作为交换契约。

## SRC-012 — Gmail messages.list

- 类型：official_doc
- URL：https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
- 本项目用途：使用 includeSpamTrash=true，分页遍历消息级候选。

## SRC-013 — Gmail message format RAW

- 类型：official_doc
- URL：https://developers.google.com/workspace/gmail/api/reference/rest/v1/Format
- 本项目用途：Canonical Raw 使用完整 RFC 2822/RAW，而非仅附件。

## SRC-014 — Gmail sync guide

- 类型：official_doc
- URL：https://developers.google.com/workspace/gmail/api/guides/sync
- 本项目用途：增量 History 水位失效或 404 时执行 Full Reconciliation。

## SRC-015 — Gmail filters.list

- 类型：official_doc
- URL：https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.filters/list
- 本项目用途：只读审计 Filters；不声称标准 API 可直接列出 Blocked Addresses。

## SRC-016 — Gmail messages.trash

- 类型：official_doc
- URL：https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/trash
- 本项目用途：M3 只允许精确消息级 Trash。

## SRC-017 — Gmail threads.trash

- 类型：official_doc
- URL：https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/trash
- 本项目用途：作为明确禁用接口；线程级会移动线程内所有消息。

## SRC-018 — Gmail messages.delete

- 类型：official_doc
- URL：https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/delete
- 本项目用途：作为明确禁用的不可逆接口。

## SRC-019 — GitHub Actions schedule

- 类型：official_doc
- URL：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- 本项目用途：使用 IANA timezone 与 04:30 Australia/Sydney；官方说明事件可能延迟或丢弃，因此 04:30 只作为调度目标，并保留 workflow_dispatch、水位补偿和周日对账。

## SRC-020 — GitHub App installation token

- 类型：official_doc
- URL：https://docs.github.com/en/enterprise-cloud@latest/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- 本项目用途：跨仓写入使用短时、仓库限定 Token，适应私有仓改名。

## SRC-021 — GitHub Release assets

- 类型：official_doc
- URL：https://docs.github.com/en/rest/releases/assets
- 本项目用途：固定 live Release 只保留一张 timeline-latest.png.age，避免 Git 历史污染。

## SRC-022 — GitHub repository limits

- 类型：official_doc
- URL：https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits
- 本项目用途：建立仓库/LFS 容量阈值与停止门，拒绝无界增长。

## SRC-023 — Codex Automations

- 类型：official_doc
- URL：https://openai.com/academy/codex-automations/
- 本项目用途：仅配置普通、被动、非关键的健康检查；不让 Auto 接触 Gmail、私有数据、Secret 或执行修复。

## SRC-024 — Moomoo statement manual

- 类型：official_doc
- URL：https://www.moomoo.com/au/manual/topic-14-184
- 本项目用途：确认 Statement 类型、下载入口与 PDF 密码规则；密码未知时 Raw 仍归档。

## SRC-025 — Moomoo Financial Year Summary

- 类型：official_doc
- URL：https://www.moomoo.com/au/support/topic6_554
- 本项目用途：作为报表分类和 Processed Schema 的参考，不设计 Portal 自动下载。

## SRC-026 — Moomoo ASX statements and contract notes

- 类型：official_doc
- URL：https://www.moomoo.com/au/support/topic6_662
- 本项目用途：覆盖 Daily/Monthly/Contract Note 生态分类，但只有邮件中实际存在的内容进入范围。

## SRC-027 — Moomoo AU support contact

- 类型：official_doc
- URL：https://www.moomoo.com/au/support/topic6_394
- 本项目用途：建立初始 verified sender 候选和人工证据源，不能单靠显示名或主题。

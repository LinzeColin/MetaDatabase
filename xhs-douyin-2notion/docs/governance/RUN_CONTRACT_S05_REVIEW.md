# Stage 5 G5 Review Run Contract

## Identity

- Review: `STG.X2N.5.REVIEW`
- Run: `RUN-X2N-S05-REVIEW`
- Base: Task005 evidence receipt at `645ab212eb2e5d7d0e9aeac3c6d2c73804de346c`
- Gate: `G5`

## Single-phase scope

本 Run 只独立复核 Stage 5 的五个已完成 UX/Ops Task。它固定每个 Task 的公开 receipt，重新运行
Notion Mock、Markdown deterministic rebuild、loopback review/diagnostics、operations recovery，以及
Task005 的隔离历史 replay。它还重跑 G4 的公开 CI-synth acceptance，以确认多模态/分类的既有关闭边界
没有被 Stage 5 改写。

它不执行新的 DAG Task，不上传、不部署、不发布，不访问真实账号、Chrome Profile、平台、真实 Notion、
真实 Private-Database、authenticated session、`tmutil`、物理删除、模型、真实媒体或 Owner 私有 Gold。

## Required decision

只有下列四项同时成立才可签发 `G5=PASS_CI_SYNTH`：

1. Notion Mock reconciliation 证明 eventual-consistency contract；真实 Notion 未启用时必须明确是 disabled/`NOT_RUN`。
2. Markdown 10,000-item full rebuild 可重复、无 duplicate content copy、second rebuild write 为零。
3. loopback Owner review、CSRF/Origin 拒绝、脱敏 diagnostics、doctor 与 bounded recovery 均可用。
4. Private-MetaDatabase domain-bound archive/restore、deletion epoch/tombstone、preview/confirm、TTL 与
   Time Machine 合同均通过 CI-synth；真实 transfer、`tmutil` 和物理删除必须保持 `NOT_RUN`。

任一固定 receipt 缺失或变更、任一 Task replay 失败、公开 control/evidence 含凭据、本机绝对路径或
平台媒体 CDN URL、实际外部调用非零，或 G5 误授权上传/部署/发布，均 `FAIL_CLOSED`。

## Transition and release boundary

`G5 PASS` 只授权下一独立 Run `TSK.x2n.assurance.001 / PH.X2N.6.1`。它不授权 Stage 5 上传、
任何真实平台能力、Chrome Web Store、部署、运行或发布；最终 deploy/run/online smoke 仍只位于
`TSK.x2n.assurance.005`。不存在 Alpha、Beta、固定健康观察或 soak gate。

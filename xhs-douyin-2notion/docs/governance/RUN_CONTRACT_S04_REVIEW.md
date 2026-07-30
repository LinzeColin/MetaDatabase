# Stage 4 G4 Review Run Contract

## Identity

- Review: STG.X2N.4.REVIEW
- Run: RUN-X2N-S04-REVIEW
- Base: Task005 evidence receipt at 81a8bb7804b968f0cfa4a972c8ed5cfbfce540ae
- Gate: G4

## Single-phase scope

本 Run 只独立复核 Stage 4 的五个已完成多模态 Task。它重新运行公开合成验收，确认 ASR、OCR、Vision 和 Fusion 报告存在，确认 prompt-injection suite 通过，确认 AI 没有 taxonomy mutator，并确认自动分类在对应私有 Gold precision gate 通过前保持关闭。

它不执行 Stage 5 Task，不上传 Stage 4，不部署、不发布，不访问真实账号、Chrome Profile、平台、Notion、真实模型、真实媒体或 Owner 私有 Gold。

## Required decision

只有所有五个固定 Task receipt、历史 G3 receipt、公开边界扫描和新鲜 CI-synth replay 同时通过，且自动分类为 DISABLED_PENDING_PRIVATE_GOLD 时，才能签发 G4=PASS_CI_SYNTH。ASR、OCR、Vision 与分类的私有 Gold 未运行不是伪造性能通过的理由；它们必须明确保持 disabled 或 suggestion-only。

任一 receipt 缺失、prompt-injection 失败、AI 可变更一级 taxonomy、自动分类被提前打开、平台/账号/模型调用非零，或公开证据出现凭据、绝对本机路径、平台媒体 CDN URL 时，一律 FAIL_CLOSED。

## Transition and release boundary

G4 PASS 只允许本地开始下一单 TSK.x2n.uxops.001 / PH.X2N.5.1；不授权 Stage 4 上传、部署或发布。最终 deploy、run 与 online smoke 仍只在 Stage 6 assurance.005 内完成。不存在 Alpha、Beta、固定健康观察或 soak gate。

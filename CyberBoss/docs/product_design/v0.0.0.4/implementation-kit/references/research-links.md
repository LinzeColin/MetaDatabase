# Research Links and Reuse Decisions

Accessed/reviewed for the 2026-07-26 task pack. Implementation must re-check current versions at T0 and pin exact commits.

## Primary upstream

- CyberBoss: https://github.com/WenXiaoWendy/cyberboss
- CyberBoss README (Chinese): https://github.com/WenXiaoWendy/cyberboss/blob/main/README.zh-CN.md
- CyberBoss open issues: https://github.com/WenXiaoWendy/cyberboss/issues
- timeline-for-agent: https://github.com/WenXiaoWendy/timeline-for-agent

Reuse: WeChat iLink, runtime abstraction, commands, diary/check-in and Timeline tools. Strengthen cursor durability, outbox, singleton, cloud state, status, backup and resource governance.

## OpenAI primary documentation

- Codex App Server: https://developers.openai.com/codex/app-server
- Codex authentication: https://developers.openai.com/codex/auth
- Codex CLI: https://developers.openai.com/codex/cli
- Codex remote development / SSH: https://developers.openai.com/codex

Decision: same-host loopback WebSocket only; never expose App Server publicly. Device auth on OVH; auth file treated as a password.

## Competitor/pattern research

- OpenHands: https://github.com/All-Hands-AI/OpenHands
- OpenHands software-agent SDK: https://github.com/OpenHands/software-agent-sdk
- SWE-agent: https://github.com/SWE-agent/SWE-agent
- Wechaty: https://github.com/wechaty/wechaty
- AstrBot: https://github.com/AstrBotDevs/AstrBot
- Uptime Kuma: https://github.com/louislam/uptime-kuma

Borrowed patterns: runtime boundary, event streams, reproducible task environments, adapter/plugin separation, probe semantics and status clarity. The full stacks are not installed in the MVP because of scope/resource cost.

## Cloudflare primary documentation

- Access applications: https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- R2 object storage: https://developers.cloudflare.com/r2/
- R2 lifecycle rules: https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- R2 bucket locks: https://developers.cloudflare.com/r2/buckets/bucket-locks/
- Web Analytics: https://developers.cloudflare.com/web-analytics/

Decision: Access protects human UI; R2 is cold object/snapshot storage, not the hot queue/database; Web Analytics collects only page/visitor metrics.

## GitHub primary documentation

- Deploy keys: https://docs.github.com/authentication/connecting-to-github-with-ssh/managing-deploy-keys
- GitHub Apps authentication: https://docs.github.com/apps/creating-github-apps/authenticating-with-a-github-app
- Repository limits: https://docs.github.com/repositories/working-with-files/managing-large-files/about-large-files-on-github
- GitHub Actions: https://docs.github.com/actions
- Webhook security: https://docs.github.com/webhooks/using-webhooks/validating-webhook-deliveries

Decision: GitHub credentials are scoped only to final code publication and CI.
Business/runtime data and canonical facts never use the code repository; they use the
repository-governed Private-MetaDatabase no-clone client contract.

## SQLite primary documentation

- WAL: https://sqlite.org/wal.html
- Online backup API: https://sqlite.org/backup.html
- VACUUM INTO: https://sqlite.org/lang_vacuum.html#vacuuminto

Decision: WAL runtime spool; online snapshot only, never raw-copy a live DB.

## OCI primary documentation

- Object Storage: https://docs.oracle.com/en-us/iaas/Content/Object/home.htm
- Lifecycle policy: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm
- Retention rules: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm

Decision: OCI is backup-of-cold-backup, never a Runtime dependency.

## Existing user platform

- Global status: https://status.linzezhang.com
- CyberBoss target: https://cyberboss.linzezhang.com

Decision: add a CyberBoss status adapter/card to the existing platform; do not deploy a duplicate status product.

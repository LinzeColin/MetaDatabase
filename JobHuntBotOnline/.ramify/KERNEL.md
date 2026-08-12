# JobHuntBot Online Context Kernel

- Project: JobHuntBot Online v0.3.0 SaaS
- Status: CANDIDATE_READY_FOR_TARGET_DELIVERY
- North star: A user registers by email, uploads a resume, confirms only high-impact facts, receives automatically refreshed job recommendations every six hours, and manages applications without handling an API key.
- Current exact local subject: this taskpack directory and the ZIP generated from it. Local Chromium navigation is blocked by a managed URLBlocklist; deterministic HTTP/DOM checks continue, while production Playwright remains mandatory.
- Observed remote baseline: `LinzeColin/MetaDatabase` branch `codex/jobhuntbot-online-v020-deployment`, commit `cf820c7a5841242a4727eb6c40c35079eb9bb152` (v0.2.0).
- Production status: UNVERIFIED. No OVH/HTTPS/standard-SMTP/DeepSeek/production migration claim is made by local evidence. NitroSend is removed and must not be reintroduced.
- Current executor: Codex Delivery Agent after Owner supplies this ZIP.
- Core acceptance: `deploy/acceptance.sh` must create `ACCEPTANCE_RESULT.json` with `core_verdict=PASS` on the exact deployment.

## Active risks

1. Target environment, latest main and infrastructure may have changed; observe before adapting.
2. Any standard SMTP relay, IMAP acceptance mailbox and platform DeepSeek Secret require target permissions; NitroSend unavailability is not a blocker.
3. External source connectivity must be proven from the target runtime.
4. v0.2 migration is optional but, when present, must preserve readback and rollback evidence.

## Next actions

1. Observe current truth and protect the running state.
2. Adapt this Candidate without overwriting a better upstream implementation.
3. Configure Secrets, migrate, deploy Web/Scheduler/Worker/PostgreSQL.
4. Run real HTTPS acceptance and fix the first true break only.
5. Commit/push and register operations after core PASS.

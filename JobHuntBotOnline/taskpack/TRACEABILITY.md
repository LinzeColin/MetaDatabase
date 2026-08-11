# Traceability

| Requirement | Invariant | Acceptance | Main implementation | Evidence |
|---|---|---|---|---|
| Email SaaS lifecycle | INV-REAL-001 | AC-AUTH-01 | `app/main.py`, `app/email_service.py`, `app/security.py` | local/target browser |
| Tenant isolation | INV-TENANT-003 | AC-TENANT-02 | all `user_id` predicates, owner-scoped manual jobs | tests + two-user browser |
| Platform DeepSeek | INV-AI-005 | AC-AI-03 | `app/ai.py`, `app/config.py` | provider probe + fallback tests |
| Resume-first automation | INV-ZERO-TECH-002 | AC-DISCOVERY-04 | `app/resume.py`, `app/services.py`, `app/discovery.py` | browser golden |
| Six-hour refresh | INV-REFRESH-006 | AC-REFRESH-05 | config hard gate + discovery completion schedule | tests + DB probe |
| Filters and usable controls | INV-REAL-001 | AC-UX-06 | templates/static/routes | UI contract + Playwright |
| Application tracking | INV-TRUTH-004 | AC-APPLICATION-07 | pack/event routes | tests + browser |
| v0.2 preservation | INV-RECOVERY-008 | AC-DATA-08 | Alembic + `migrate_v02_sqlite.py` | migration result |
| Backup/rollback | INV-RECOVERY-008 | AC-RECOVERY-09 | deploy scripts | restart + backup/restore evidence |
| Real production | INV-EVIDENCE-009 | AC-PROD-10/11/12 | `deploy/acceptance.sh` | `ACCEPTANCE_RESULT.json` |

# Durable Decisions

- D-001: Product is a multi-account, multi-user candidate-side SaaS, not a recruitment marketplace.
- D-002: Email registration, verification, login and one-time password reset are in scope.
- D-003: The platform owns one DeepSeek credential; normal users never enter, view or export it.
- D-004: Resume upload is the primary onboarding action; automatic job discovery follows one consolidated confirmation page.
- D-005: Every completed discovery run schedules the next due time exactly six hours later.
- D-006: Deterministic eligibility rules outrank model output.
- D-007: No unauthorized SEEK/LinkedIn/Indeed scraping, verification bypass or automatic final submission.
- D-008: Existing manual import, application pack, tracking, encryption, backup and recovery paths remain regression-protected.
- D-009: Local Candidate PASS is not production PASS; only the exact HTTPS deployment can earn the latter.
- D-010: NitroSend is removed. Email transport is vendor-neutral SMTP; missing SMTP keeps public registration closed but does not stop non-email delivery work.

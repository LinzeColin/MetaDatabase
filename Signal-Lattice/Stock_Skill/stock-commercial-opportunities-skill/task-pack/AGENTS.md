# Project instructions for Codex

## Scope

- Work on one bounded issue in `stock-commercial-opportunities` (“股票商业机会拆解”).
- Start with this task pack and its exact draft directory; avoid unrelated repositories or installed Skills.
- This package is source/backup only. Do not install into `~/.agents/skills` or `~/.codex/skills`.
- Do not connect brokerage/data accounts, place trades, publish stock promotion, contact issuers, or change external systems without separate explicit authority.

## Evidence-first workflow

1. Read `START_HERE_FOR_CODEX.md`, then the current Run Contract in `CODEX_MASTER_TASK.md`.
2. Recheck current official Skill guidance and current financial/regulatory facts when relevant.
3. Resolve issuer, ticker, exchange, share class, security type, currency, fiscal period and as-of before ranking.
4. Trace commercial value pool → beneficiary pathway → issuer exposure → financial capture → expectations/valuation/catalyst.
5. Run deterministic validation before semantic forward evaluation.
6. Status is fail-closed: missing input, unrun, stale, unauthorized, unknown or thresholdless work is not PASS.

## Financial integrity

- Outputs prioritize research and never constitute personal investment advice, buy/sell/hold approval, position sizing, target-price promise or automated execution.
- Never fabricate securities, filings, segment exposure, price, consensus, valuation, catalysts, sources, timestamps or test results.
- Keep Fact / Inference / Estimate / Opinion / Unverified distinct.
- Social media, price momentum, search snippets and synthetic personas are lead-only and cannot prove issuer exposure or market expectations.
- E0–E5 is derived from evidence; a high score cannot raise maturity.
- Suspected MNPI triggers stop/isolation. Public artifacts must exclude portfolio, account, transaction, paid-data, customer, credential and local-session material.

## Engineering constraints

- Keep `SKILL.md` concise; use one-level progressive disclosure.
- Deterministic rules use Python standard library only; fixtures use `DEMO` exchange and synthetic issuers.
- Use bounded candidate/source budgets and saturation stops. `NO_QUALIFIED_CANDIDATE` is valid.
- Do not write caches into the package. No `.pyc`, logs, temp files, secrets or absolute user paths.
- Preserve v1/v2 ZIP lineage. Never silently rewrite an archived artifact.

## Handoff

Report exact files, commands/results, version/hash, install state, semantic checks left `NOT_RUN`, financial limitations, first rejection, surprise/blind spot and one highest-ROI next action.

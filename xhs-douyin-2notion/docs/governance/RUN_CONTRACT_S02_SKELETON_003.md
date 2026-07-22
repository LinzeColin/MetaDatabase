# Run Contract — `RUN-X2N-S02-S003`

## Identity

- Task: `TSK.x2n.skeleton.003`
- Phase: `PH.X2N.2.7`
- Stage: `STG.X2N.2`
- Task base: `0af2d3b269e7d5631257cb49f41f75cc79438f70`
- Branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton003`
- Run kind: one DAG Task only

## Objective and bounded scope

Make zero platform-media-URL persistence and bounded temporary-media handling enforceable. The Run may add an in-memory ephemeral media reference, exact-suffix URL firewall, DNS/IP and redirect validation, IP-pinned transport contract, bounded streaming download, MIME sniffing, SQLite-backed lease lifecycle, race-safe cleaner, fixed-scope CDN scanner, public-safe synthetic fixtures, verifier and compact evidence.

The Run must not enter `TSK.x2n.skeleton.004` canonical orchestration, list/favorites adapters, real platform or media network calls, Owner Chrome/Profile, real accounts, cookies or credentials, automatic scrolling, ASR/OCR/key-frame/FFmpeg execution, classification, Notion, Stage review or remote upload. No raw media URL or raw media may be written to Git, SQLite, Markdown, logs, evidence, Notion-export or long-lived downloads.

## Security and lifecycle decisions

- Media source URLs exist only inside a non-serializable, redacted in-memory object; exceptions and receipts expose stable codes and aggregate facts only.
- Only HTTPS, TCP 443, an exact platform CDN suffix and a globally routable resolved IP are allowed. IP literals, userinfo, unsafe ports, control characters, traversal, local/file/data targets, non-global IPs and ambiguous hostnames fail closed.
- Every redirect is independently re-parsed, re-allowlisted and re-resolved. A transport must connect to the validated IP while preserving the approved TLS hostname; this Run provides the transport boundary and synthetic transport only, not production networking.
- Remote names never choose local paths. Before acquisition, SQLite records a URL-free random lease identity so any partial-file cleanup failure is durable; files are written owner-only below `runtime/temp_media/<run_id>/<lease_id>.bin`, with stream/declared-size/deadline/MIME limits, then verified SHA-256/MIME/size metadata atomically replaces the pending metadata before a path is yielded.
- Successful/handled work removes media immediately. Crash/failure residue has a maximum 24-hour lease; the cleaner never deletes an unexpired active lease, serializes file lifecycle operations, and records every deletion failure as a high-priority structured error.
- Scanner scope names are fixed logical sinks (`db`, `markdown`, `logs`, `notion-export`, `artifacts`); callers cannot inject arbitrary paths. Output contains counts and pattern-set version, never matched values or private paths.

## Acceptance

- `ACC.x2n.media.001`: CI synthetic scan across all five fixed sinks, canonical page-query scan and repository/release-history verifier report zero platform CDN URLs, signature/tracking parameters and canonical query/fragment persistence.
- `ACC.x2n.media.002`: success residue `0`; expired failure/kill residue `0`; unexpired active mis-delete `0`; injected deletion failure receives a high-priority structured error `100%`.
- `ACC.x2n.media.003`: URL fuzz and SSRF matrices produce forbidden-target success `0` and local-file reads `0`; every redirect and DNS result is revalidated.
- `ACC.x2n.media.004`: acquisition-layer oversized, fake-MIME, corrupt and bounded-resource cases fail structurally without Companion crash and are eventually cleaned. Processor/FFmpeg, image-bomb decode, repeated-key-frame and duration-processing assertions remain `DOWNSTREAM_NOT_RUN` for their Stage 4 owners and cannot be represented as complete here.

The only permitted completion status is `PASS_CI_SYNTH_SCOPED`; real media/network execution and Stage 2 gate remain `NOT_RUN`.

## Verification commands

```bash
.venv/bin/python -B scripts/run_skeleton_003_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_003.py --verify-worktree --allow-external-main-dirty --skip-external --write-evidence
.venv/bin/python -B scripts/verify_skeleton_003.py --verify-worktree --allow-external-main-dirty --skip-external --require-evidence
.venv/bin/python -B -m unittest discover -s apps/companion/tests -p 'test_*.py'
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
```

The final software lane must also run dependency audit, release-artifact verification and historical Stage 0–2 verifiers. Any raw media/CDN URL in a persisted sink or diagnostic, real network/account execution, active-lease mis-delete, non-global target success, undeclared skip, flaky blocking Gate or downstream-scope claim fails the Run.

## Risk, rollback and stop conditions

- Risk: a source URL leaks through an exception; DNS or redirect state changes after validation; streaming bypasses limits; cleaner races with acquisition; scanner misses chunk boundaries or binary sinks.
- Rollback: disable media acquisition and retain text-only capture; preserve scanner and cleanup for residue removal.
- Stop: implementation requires persistence of a raw media URL, cannot bind transport to the validated address, cannot protect active leases, requires a real account/cookie/platform call, or requires entering Phase 2.8 or Stage 4 processing.

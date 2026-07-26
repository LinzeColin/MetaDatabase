# CB-030 Simulator Contract Evidence

## Result

`PASS` for all non-activation P0.4 Oracles. This evidence proves synthetic
channel/runtime contracts only. It does not prove a real WeChat account, Codex
auth on OVH, AC-001 real or AC-010 real.

## Why extension was permitted

The supplied WeChat simulator started and completed one synthetic receive/send
round trip. Its initial fault surface covered only counted 503 responses and
did not cover the TaskPack's deterministic 401/403/429/500/timeout/reset,
unknown-outcome, duplicate-ack or out-of-order fixtures.

The supplied Codex simulator could not start from its documented location:
Node returned `ERR_MODULE_NOT_FOUND` for `ws`, because the implementation-kit
script did not resolve the dependency already locked under `CyberBoss/app`.
It also lacked approval, progress, overload, interrupt, crash/reconnect,
false-success and late/duplicate fixtures required by CB-030.

The extension therefore reuses the existing locked `app` dependency; no new
package, network fetch, upstream remote or source download was introduced.

## Protocol evidence

The implementation was checked against:

- pinned CB-000 schema evidence for Codex CLI
  `0.146.0-alpha.3.1`, including `initialize`, `initialized`,
  thread/turn methods and command/file approval server requests;
- the current official Codex App Server manual, which states that on-wire
  messages omit the JSON-RPC header, initialize must precede other requests,
  `initialized` completes the handshake, WebSocket ingress is bounded and
  overload is `-32001 / Server overloaded; retry later.`;
- the frozen CyberBoss WeChat API adapter request/response fields.

The current official App Server surface is experimental and may change. It is
used as drift evidence, not as permission to replace the exact CLI pin.
Simulator-only control methods are explicitly outside the production protocol.

Official reference:
<https://developers.openai.com/codex/app-server>

## Executed matrix

| Surface | Deterministic fixtures | Result |
|---|---|---|
| WeChat login | QR issued; wait/scaned/expired/confirmed state support | PASS |
| WeChat receive | empty batch, receive, candidate cursor, replayed source ID, reverse delivery | PASS |
| WeChat send | receipt, same-client duplicate ack, unknown outcome then idempotent retry | PASS |
| WeChat failures | 401, 403, 429, 500, 503, immediate timeout, connection reset | PASS |
| Codex handshake | pre-init rejection, initialize, initialized, repeated-init rejection | PASS |
| Codex success | thread, turn, item start, two progress deltas, artifact, completion | PASS |
| Codex approval | server request, explicit response, command item, completion artifact | PASS |
| Codex failures | retryable error, terminal error, interrupt | PASS |
| Codex overload | max-active=1, exact `-32001` rejection | PASS |
| Codex truth | false completion has artifact_count=0 and Oracle=`false_success` | PASS |
| Codex ordering | duplicate completed item plus late delta after terminal event | PASS |
| Codex recovery | process exits 75, restarted listener completes a new turn | PASS |
| Network boundary | both simulators reject `0.0.0.0` with loopback-required exit 64 | PASS |
| Cleanup | no simulator process/listener remains | PASS |

Command:

```bash
node --test \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/simulator-contract.test.mjs
```

Observed summary:

```text
tests=4 pass=4 fail=0 skipped=0
```

No real-time soak, external network, auth material or provider mutation was
used as a success Oracle.

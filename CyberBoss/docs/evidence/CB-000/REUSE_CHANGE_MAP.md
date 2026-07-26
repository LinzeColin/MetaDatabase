# CB-000 Reuse and Change Map

## Decision

固定来源具备微信、Codex Runtime、shared start/state、Timeline 和 location 核心能力。
后续按现有边界增量加 durability/security/operations；没有证据支持全量重写，也
不得新增第二套 Timeline 内核。

## Exact module map

| Capability | Current module and observed behavior | Disposition |
|---|---|---|
| WeChat HTTP poll/send | `app/src/adapters/channel/weixin/api.js`: `getUpdates`, `sendText`, upload/typing | Reuse provider protocol and normalization |
| WeChat cursor | `app/src/adapters/channel/weixin/index.js`: `getUpdates` currently calls `saveSyncBuffer` before upper-layer processing | Later split poll candidate cursor from durable commit at this boundary |
| Message orchestration | `app/src/core/app.js`: poll loop, command dispatch, runtime turns and replies | Preserve command behavior; later attach durable inbox/job/outbox |
| Codex transport | `app/src/adapters/runtime/codex/rpc-client.js`: stdio spawn or WebSocket JSON-RPC | Reuse; CB-000 aligned stale fields with verified schema; later add bounded pending/retry metrics |
| Codex lifecycle | `app/src/adapters/runtime/codex/index.js`: initialize, thread/resume, turn, compact, cancel and events | Reuse behind future RuntimeSupervisor contract |
| Shared process start | `app/scripts/shared-common.js`, `app/scripts/shared-start.js` | Reuse signal/child behavior; later replace detached ownership with systemd entrypoint |
| State paths | `app/src/core/config.js`: `CYBERBOSS_STATE_DIR` or `~/.cyberboss`; per-feature files below it | Reuse configuration surface; later map OVH runtime paths and durable DB |
| Timeline kernel | `vendor/timeline-for-agent/` | Preserve unchanged; it is the only Timeline kernel |
| Timeline adapter/service | `app/src/integrations/timeline/index.js`, `app/src/services/timeline-service.js` | Reuse `read/categories/proposals/write/build/serve/dev/screenshot`; later add canonical source/redaction/status |
| Timeline tools | `app/src/tools/tool-host.js`: eight `cyberboss_timeline_*` tools | Reuse existing tool surface; do not duplicate |
| Location | `vendor/whereabouts-mcp/`, consumed by `app/src/tools/tool-host.js` | Preserve fixed local package under strict GPLv3+AGPLv3 obligations |
| Dependency boundary | `app/package.json`, `app/package-lock.json`, `app/.npmrc` | CB-000 changed Git branches to fixed local packages |
| Tests | `app/test/`, vendor `test/` | Reuse baseline suites and extend per later acceptance contracts |

## Proven baseline defect

The first unmodified full test run passed 149/153 tests. Four sticker tests failed
because their fixture referenced `/Users/tingyiwen/Dev/cyberboss`. Only the test
fixture path was changed to `path.resolve(__dirname, "..")`; the service behavior
was unchanged. The rerun passed 153/153.

The generated Codex schema also proved that current `thread/start` does not accept
the historical `{input}` shortcut and `turn/start` does not define `accessMode`.
The client now requires a real thread ID and sends the equivalent supported
`approvalPolicy` and `sandboxPolicy`.

## Future patch discipline

The authoritative future design remains
`docs/product_design/v0.0.0.4/08_UPSTREAM_CODE_CHANGE_MAP.md`. Every later Run
must select only its phase's rows and tests. CB-000 does not implement durable
messaging, canonical sync, cloud deployment, status, backup, canary or production
activation.

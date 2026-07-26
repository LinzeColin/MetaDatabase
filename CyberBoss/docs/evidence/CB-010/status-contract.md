# CB-010 Existing Status Contract

## Read-only observation

At `2026-07-26T06:53:05.277337Z`, both the public Status page and its
`data/snapshot.json` endpoint returned HTTP 200. Only the page and snapshot were requested;
no online state was changed and no raw page, raw snapshot or project row was persisted.

The snapshot contained 8 project rows and no CyberBoss row.

## Current `projects[]` row contract

Every observed project row used these fields:

```text
agent, backup, db, deploy, host, name, notify, parts, status, store, url
```

All fields are strings except `parts`, which is an array. The page contract recognizes
`run`, `access` and `down`; the observed snapshot currently used `run` and `access`.
Observed `parts` values were `前台` and `后台`, and observed `agent` values were
`无`、`低`、`中`.

Response sizes, hashes, top-level keys, field types and evidence boundaries are recorded
in `public-status-observation.json`. Raw project values are deliberately excluded.

## Adapter behavior

`global-status-adapter.js` now emits the exact row fields above:

- healthy or degraded Access-protected service → `access`;
- stale, stopped, unknown or `activation_pending` service → fail-closed `down`;
- non-contract diagnostics remain in additional fields without changing the public row;
- fallback generation identifiers are deterministic and contain no source payload;
- timestamp, version, state, metric and degraded-reason inputs are allowlisted or
  normalized before public output;
- CLI output uses atomic replacement and does not reveal its local source path.

`global-status-contract.fixture.json` records the observed schema, allowed values,
CyberBoss absence and `online_mutation_authorized_by_cb010=false`.

The Node contract suite passes 7/7 cases, including hostile diagnostic-field
sanitization, DLP and atomic CLI output.

## Boundary

This Run validates an adapter fixture only. It does not add a CyberBoss row, change the
online snapshot or install a CyberBoss collector. A separate authorized-host, read-only
whitelist probe confirmed the *existing* Status compose/collector/data/web surface,
mounted containers, cron ingestion, fresh snapshot and Traefik routing counts. It did not
read or retain route values, config, project rows or credentials and made no online
change. CyberBoss row publication remains outside P0.2.

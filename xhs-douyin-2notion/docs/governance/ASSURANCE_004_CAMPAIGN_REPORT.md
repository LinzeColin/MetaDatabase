# Assurance004 Campaign Report

## Public aggregate

| Campaign | Result |
|---|---|
| Extension restart | 100 restarts; loss/duplicate/wrong state/console error = 0 |
| XHS checkpoint | 100 items; 50 process kills; loss/duplicate/auto-scroll/loop = 0 |
| Media cleanup | success and expired residual = 0; active lease misdelete = 0; 50 candidate cap; 7,200 s cap |
| Notion Mock | 429/529 Retry-After; maximum average rate = 2 req/s; duplicate page = 0 |
| Operations recovery | 10 stage kill points; Canonical loss/duplicate/recovery loop = 0 |
| Critical matrix | 6 scenarios × 10 Seeds; persistence finding/unauthorized delete = 0 |
| Capacity | 20/80/1k/10k Markdown rebuild; 100 concurrent replay; duplicate entities/sinks = 0 |

## Measurement boundary

The benchmark records local relative growth and Python allocation peak only. It prohibits a universal time promise;
device, filesystem and browser binary setup are intentionally outside the public result. Temporary test data and
browser artifacts are deleted by the campaign and are not evidence artifacts.

## Release boundary

This campaign is a prerequisite for, not a substitute for, `TSK.x2n.assurance.005`. It contains no production
deployment, account activation, real Notion call, private Gold read, release upload, Alpha/Beta, fixed observation
period or soak.

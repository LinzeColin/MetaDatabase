# Signal Lattice V19 acceptance boundary

V19 is a read-only, `SHADOW_ONLY` research system. It never opens a trading context or sends an order. The current application version is `0.0.0.1.44`; the decision contract is `v0.0.0.19`.

## Acceptance states

| Result | Meaning | What it cannot prove |
| --- | --- | --- |
| `STRUCTURAL_PASS` | A local fixture exercised the report, API, cadence, six-row matrix and read-only boundary. | Live provider inputs, public deployment, native Skill execution, investment value, profitability, or 20/60-day outcomes. |
| `LIVE_PROVIDER_PASS_NOT_BUSINESS_RELEASE` | A configured MooMoo read-only provider produced a current `live` snapshot and passed the deployment acceptance program. | Business-release eligibility, profitability, or a completed third-party investment review. |
| `NOT_ACCEPTABLE` / `FAIL` | Input provenance is fixture-degraded, stale, missing, or a contract assertion failed. | Nothing beyond the reported failure. |

The API exposes `market_provider`, `provider_state`, `input_provenance`, `acceptance_scope`, and `business_release_status`. A fixture is always reported as `FIXTURE_DATA` + `STRUCTURAL_FIXTURE_ONLY`; it cannot return a live-provider result.

## Reproducible verification

Run the complete source suite:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider
```

Run the local structural chain:

```bash
PYTHONDONTWRITEBYTECODE=1 bash scripts/run_local_acceptance.sh
```

It must return `STRUCTURAL_PASS`, `market_provider=fixture`, `provider_state=fixture`, and `business_release_status=NOT_ISSUED`.

The VPS3 installation program invokes `scripts/run_acceptance.py --require-live-provider` against both loopback and public URLs. It fails closed unless both report `LIVE_MOOMOO_QUOTE` and `LIVE_PROVIDER_REVIEW_ONLY`.

## Business-release boundary

No command in this directory can issue a profitability or investment-business release. Before any such claim, an independent reviewer still needs real provider history, public VPS3 evidence, genuine canonical Skill runs, cost-aware point-in-time validation, and mature 20/60-day outcomes. Until then `business_release_status` and `profitability_status` remain `NOT_ISSUED`.

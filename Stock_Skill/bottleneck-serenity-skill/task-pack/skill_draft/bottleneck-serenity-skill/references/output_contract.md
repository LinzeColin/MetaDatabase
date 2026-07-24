# Output contract

## Human-readable memo

Use this order:

1. **Decision** — one theme-level sentence and one label; no issuer, company, ticker, security, benchmark or index provider/brand, branded commercial operator, or company-labeled source.
2. **Funded demand** — payer, committed versus aspirational spend, procurement path, and failure conditions; remain role-neutral.
3. **System map** — mandatory functions, dependencies, roles, and constraint node; remain role-neutral.
4. **Constraint proof** — capacity, qualification, substitution, and duration; remain role-neutral.
5. **Security map** — only now introduce issuers, companies, tickers, listings, benchmark/index brands, branded operators, company-labeled sources, and the candidate universe.
6. **Equity capture** — revenue-to-per-share bridge.
7. **Three clocks** — scarcity, monetization, discovery.
8. **Valuation** — market-implied base case plus bear/base/bull assumptions and return ranges.
9. **Catalysts** — dated evidence and earnings events.
10. **Red team** — strongest alternative explanation.
11. **Kill switches** — measurable invalidation conditions.
12. **Portfolio fit** — root-driver overlap and liquidity.
13. **Open questions** — only decision-relevant unknowns.
14. **Sources** — claim-level citations.

This order is a hard gate. Any issuer, company, ticker, security, benchmark or index
provider/brand, branded commercial operator, issuer-specific evidence, or company-labeled
citation before the exact `Security map` heading is a failure, even when the content is
used only as a benchmark or constraint-proof example.

## Machine-readable decision object

```json
{
  "schema_version": "1.0",
  "skill_version": "0.0.0.1",
  "thesis_id": "theme-company-YYYYMMDD",
  "as_of": "YYYY-MM-DD",
  "source_cutoff": "YYYY-MM-DD",
  "previous_version": null,
  "mode": "deep_dive",
  "decision": {
    "label": "CANDIDATE",
    "one_sentence": "...",
    "confidence": "medium",
    "final_score": 68.4,
    "hard_gates_passed": true
  },
  "theme": {
    "funded_demand": "...",
    "payer": "...",
    "horizon_months": 24
  },
  "constraint": {
    "function": "...",
    "archetype": "unlocker",
    "proof": ["C-001", "C-002"],
    "resolution_paths": []
  },
  "candidate": {
    "ticker": "...",
    "company": "...",
    "market": "...",
    "role": "...",
    "exposure_materiality": "..."
  },
  "clocks": {
    "scarcity_p10_months": 12,
    "scarcity_p50_months": 30,
    "scarcity_p90_months": 60,
    "monetization_lag_months": 9,
    "market_discovery_months": 6,
    "monetizable_runway_months": 21
  },
  "valuation": {
    "currency": "USD",
    "bear_return_pct": -35,
    "base_return_pct": 30,
    "bull_return_pct": 90,
    "expected_return_pct": 24
  },
  "equity_bridge": {
    "complete": true,
    "revenue": 1000,
    "free_cash_flow": 120,
    "fully_diluted_shares": 60,
    "per_share_fcf": 2,
    "cash_conversion_checks": {
      "capex": true,
      "working_capital": true,
      "interest": true,
      "tax": true
    },
    "dilution_checks": {
      "stock_based_compensation": true,
      "convertibles": true,
      "warrants": true,
      "other_contingent_shares": true
    },
    "unverified_critical_multipliers": []
  },
  "scores": {},
  "catalysts": [],
  "kill_switches": [],
  "portfolio_tags": {},
  "open_questions": [],
  "evidence_file": "evidence.json"
}
```

`decision.hard_gates_passed=true` and `WATCH_PRICED` are invalid when `equity_bridge.complete=false`. An incomplete
bridge must list its unresolved multipliers, activate `hard_flags.no_material_revenue_bridge`, and return a failed
rent-capture gate such as `BOTTLENECK_NOT_EQUITY`; do not substitute scenario targets, EPS multiples or group-level FCF.

Every runtime machine-readable research artifact, including script JSON results and persisted CSV rows, uses the five-field
envelope frozen in `integration_contract.md`. A first snapshot uses JSON `null` for `previous_version`; updates point to the
prior immutable identifier. Content hashes are added only when they can be computed without self-reference.

## Final machine-object admission gate

Before returning a final answer, pass the exact evidence, opportunity, and portfolio
objects that will be returned to the canonical scripts through standard input:

```bash
python scripts/validate_evidence.py - < evidence.json
python scripts/score_opportunity.py - --format json < opportunity.json
python scripts/analyze_portfolio_clusters.py - < portfolio.json
```

Do not substitute a nearby draft, a copied exit code, or a narrative claim that validation
ran. The final objects must be byte-equivalent JSON values to the actual validator stdin.
Require exit code zero, `valid=true` with no errors from evidence and portfolio validation,
and no unknown/missing-factor warnings from opportunity scoring. Repair and replay before
finishing if any condition fails. Preserve each command, exit code, stdout SHA-256, and the
SHA-256 of its exact stdin so an independent validator can replay the same bytes.

## Required research directory

```text
research/<thesis_id>/
├── config.json
├── system_map.md
├── evidence.json
├── opportunity.json
├── decision.json
├── memo.md
├── monitoring.csv
└── versions/
```

## Decision labels

Allowed values:

- `RESEARCH_PRIORITY`
- `CANDIDATE`
- `WATCH_PRICED`
- `WATCH_EVIDENCE`
- `BOTTLENECK_NOT_EQUITY`
- `AVOID`
- `BROKEN`

## Fact labels

Allowed values:

- `fact`
- `inference`
- `assumption`
- `forecast`

## Confidence labels

Allowed values:

- `low`
- `medium`
- `high`

Do not output numerical confidence probabilities unless they are explicitly modeled and calibrated.

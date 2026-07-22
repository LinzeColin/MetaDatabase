# Output contract

## Human-readable memo

Use this order:

1. **Decision** — one sentence and one label.
2. **Why now** — funded demand and information/valuation gap.
3. **System map** — mandatory roles and constraint node.
4. **Constraint proof** — capacity, qualification, substitution, and duration.
5. **Equity capture** — revenue-to-per-share bridge.
6. **Three clocks** — scarcity, monetization, discovery.
7. **Valuation** — bear/base/bull assumptions and return ranges.
8. **Catalysts** — dated evidence and earnings events.
9. **Red team** — strongest alternative explanation.
10. **Kill switches** — measurable invalidation conditions.
11. **Portfolio fit** — root-driver overlap and liquidity.
12. **Open questions** — only decision-relevant unknowns.
13. **Sources** — claim-level citations.

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
  "scores": {},
  "catalysts": [],
  "kill_switches": [],
  "portfolio_tags": {},
  "open_questions": [],
  "evidence_file": "evidence.json"
}
```

Every runtime machine-readable research artifact, including script JSON results and persisted CSV rows, uses the five-field
envelope frozen in `integration_contract.md`. A first snapshot uses JSON `null` for `previous_version`; updates point to the
prior immutable identifier. Content hashes are added only when they can be computed without self-reference.

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

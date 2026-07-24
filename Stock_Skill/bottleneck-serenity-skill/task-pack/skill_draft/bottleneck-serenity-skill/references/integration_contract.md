# Integration contract

## Design principle

`bottleneck-serenity-skill` is a research node in a larger investment system. It must work independently and exchange versioned artifacts with adjacent skills.

## Inputs

```json
{
  "schema_version": "1.0",
  "skill_version": "0.0.0.1",
  "request_id": "uuid",
  "query": "研究问题",
  "as_of": "YYYY-MM-DD",
  "source_cutoff": "YYYY-MM-DD",
  "previous_version": null,
  "mode": "scan|deep_dive|compare|monitor|postmortem",
  "universe": {
    "markets": ["US", "AU", "HK"],
    "asset_types": ["equity", "ETF"],
    "min_daily_value_traded_usd": 5000000
  },
  "horizon_months": 24,
  "risk_constraints": {
    "max_position_weight": 0.10,
    "max_root_driver_weight": 0.30,
    "leverage_allowed": false,
    "derivatives_allowed": false
  },
  "upstream_artifacts": []
}
```

## Outputs

Primary event:

```json
{
  "event_type": "bottleneck_serenity_skill.thesis.completed",
  "schema_version": "1.0",
  "skill_version": "0.0.0.1",
  "request_id": "uuid",
  "thesis_id": "string",
  "as_of": "YYYY-MM-DD",
  "source_cutoff": "YYYY-MM-DD",
  "previous_version": null,
  "decision_file": "decision.json",
  "memo_file": "memo.md",
  "evidence_file": "evidence.json",
  "status": "complete|blocked|partial"
}
```

## Optional upstream adapters

### Macro/regime adapter

May provide:

- discount-rate regime;
- currency and commodity shocks;
- policy and geopolitical scenarios;
- capex-cycle context.

bottleneck-serenity-skill must not let macro replace company-level evidence.

### Data/filing adapter

May provide current filings, transcripts, prices, consensus, ownership, and supply-chain data. Every field must preserve source, timestamp, and license/provenance.

### Technical-domain adapter

May validate architecture, BOM, qualification, and substitute feasibility. Its conclusions remain claims in the evidence ledger.

## Optional downstream adapters

### Financial-model adapter

Receives system units, content, share, price, margin, capex, and dilution assumptions and returns scenario valuation. It must preserve assumption lineage.

### Portfolio-risk adapter

Receives decision object and causal tags; returns concentration, factor, liquidity, stress, and sizing constraints.

### Monitoring adapter

Receives catalysts, indicators, sources, thresholds, and cadence; emits versioned evidence updates rather than silently modifying the thesis.

## Skill coupling rules

- The upstream skill may enrich data but cannot mark a hard gate passed.
- Only this skill may issue the bottleneck-specific decision label.
- The valuation adapter may change expected return but not structural evidence.
- The portfolio adapter may veto sizing but not rewrite the thesis.
- Monitoring creates a new version and links to the previous version.
- No adapter in or connected through this Skill may authenticate to a broker, execute a trade, submit, cancel, replace, retry, or otherwise modify an order. A separate execution system or explicit user authorization does not change this boundary.

## Versioning

Every runtime machine-readable research artifact uses this top-level envelope:

- `schema_version`: artifact schema version, currently exact string `1.0`;
- `skill_version`: exact machine version `0.0.0.1`;
- `as_of`: canonical `YYYY-MM-DD` snapshot date;
- `source_cutoff`: canonical `YYYY-MM-DD` latest information date allowed by the research contract;
- `previous_version`: prior immutable artifact/version identifier, or JSON `null` for the first snapshot.

Inputs and completion events are artifacts. Persisted JSON keeps the envelope at the top level; persisted CSV repeats the
five columns on every row and keeps them in an empty scaffold header. Repository schema, eval, and UI metadata files define or
test the runtime contract and are not themselves runtime research artifacts. Add a content hash when the materialization or
transport layer can compute it without self-reference; never insert a placeholder hash.

Historical snapshots are immutable.

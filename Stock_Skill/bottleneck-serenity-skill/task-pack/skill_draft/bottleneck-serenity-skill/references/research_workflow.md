# Detailed research workflow

## Phase 1 — Define the decision

Output: `research_config.json`.

Record:

- exact question;
- what decision changes if the thesis is true;
- universe, horizon, benchmark, liquidity, currency, and risk constraints;
- current date and information cutoff;
- whether the task is scan, deep dive, compare, monitor, or postmortem.

## Phase 2 — Demand and payer map

Build a table:

| Demand driver | Payer | Funding status | Unit driver | Time window | Failure condition |
|---|---|---|---|---|---|

Rank evidence:

1. signed procurement, capex budgets, law or mandate;
2. management guidance and customer order books;
3. industry forecasts with methods;
4. narrative forecasts.

Avoid double counting the same downstream capex across suppliers.

## Phase 3 — Architecture and dependency graph

### Required graph fields

For each node:

- function;
- mandatory/optional;
- upstream inputs;
- downstream consumers;
- unit content;
- capacity and utilization;
- qualified suppliers;
- qualification time;
- expansion time;
- substitutes;
- ownership and geography;
- public companies and private entities.

For each edge:

- physical, contractual, technical, regulatory, or financial dependency;
- direction;
- strength;
- evidence;
- possible workaround.

### Graph quality checks

- Can the final system operate without this node?
- Are two different layers being conflated?
- Is the relationship current for the next architecture?
- Is a partner logo being mistaken for production revenue?
- Is the named public company the correct legal entity?

## Phase 4 — Constraint measurement

Build a constraint table:

| Node | Demand/capacity | Utilization | Lead time | Supplier count | Qualification | Substitute time | Confidence |
|---|---:|---:|---:|---:|---:|---:|---|

Use ranges. Explain definitions and sources.

### Constraint test

A candidate advances only if:

- demand is funded;
- evidence shows current or prospective tightness;
- at least one relief path is slower than monetization;
- the role is necessary under the base architecture;
- source quality passes the evidence gate.

## Phase 5 — Resolution tree

For each constraint build a probability-weighted tree:

```text
resolve by new incumbent capacity
resolve by new entrant
resolve by substitution
resolve by vertical integration
resolve by demand destruction
persist beyond horizon
```

For every branch include earliest date, base date, cost, qualification, and observable milestone.

## Phase 6 — Company and security map

Create a role-neutral universe. Do not assume the bottleneck owner is best.

| Company | Ticker | Role | Exposure purity | Capacity | Funding | Valuation | Main risk |
|---|---|---|---:|---:|---|---|---|

Verify:

- corporate structure;
- listing and currency;
- ownership of the relevant asset;
- segment economics;
- fully diluted share count;
- debt, leases, preferreds, converts, warrants, ATMs;
- float and average traded value.

## Phase 7 — Revenue-to-equity bridge

Build low/base/high cases with explicit formulas.

Minimum bridge:

```text
system units
× content per system
× attainable qualified share
× realized price
= candidate revenue
× incremental gross margin
- opex
- tax
- working capital
- maintenance and growth capex
- interest
= incremental FCF
÷ fully diluted shares
= per-share FCF impact
```

List every unverified multiplier.

## Phase 8 — Expectations and valuation

Use more than one lens when practical:

- reverse DCF or market-implied revenue/margin;
- normalized EV/EBIT, EV/FCF, or earnings power;
- capacity-value or unit-economics model;
- comparable transactions or replacement cost;
- scenario total return including dilution.

The question is not “is the multiple low?” but “what operating outcome is embedded?”

## Phase 9 — Catalyst map

Classify catalysts:

- evidence catalyst: qualification, certification, customer disclosure;
- earnings catalyst: revenue, margin, backlog, guidance;
- capital catalyst: financing, capacity completion, debt refinance;
- market catalyst: index inclusion, listing, coverage, liquidity;
- policy catalyst: permit, subsidy, export rule, procurement;
- resolution catalyst: competitor capacity or substitute qualification.

Every catalyst must have a date/range and an expected impact on the thesis—not merely on price.

## Phase 10 — Red-team committee

Write independent cases from these roles:

- systems engineer: architecture or substitute is wrong;
- procurement officer: customer can dual-source or squeeze price;
- operations expert: yield/capacity ramp fails;
- accountant: earnings quality, working capital, or capex is misstated;
- credit analyst: financing or covenants break the equity;
- valuation analyst: market already prices the outcome;
- portfolio manager: beta/correlation overwhelms idiosyncratic alpha;
- historian: prior shortage cycles ended differently.

Synthesize the strongest bear case, not eight weak objections.

## Phase 11 — Score and classify

Score only after the memo and evidence ledger exist. The score should summarize work, never substitute for it.

## Phase 12 — Portfolio decision

Select one of:

- no position;
- watchlist;
- research position;
- core candidate;
- hedge/substitute pair;
- basket when winner uncertainty is irreducible.

Exact sizing requires user constraints. In their absence, report qualitative bands and downside-based limits.

## Phase 13 — Monitoring

Each thesis needs:

- leading indicators;
- reporting sources;
- refresh cadence;
- expected range;
- alert threshold;
- thesis implication;
- owner or downstream workflow.

Example indicators:

- lead time, price premium, backlog, utilization;
- equipment orders and capacity announcements;
- customer capex and architecture decisions;
- qualification and design-win milestones;
- gross margin, working capital, capex, share count;
- substitute performance and cost;
- consensus revisions and valuation.

## Phase 14 — Postmortem

Separate:

- thesis correctness;
- timing;
- valuation;
- sizing;
- portfolio correlation;
- market beta;
- execution/slippage;
- luck.

Do not rewrite the original thesis. Compare the timestamped record with outcomes.

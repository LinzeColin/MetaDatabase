# Portfolio construction and risk

## Principle

A list of attractive bottlenecks is not a portfolio. The same downstream capex, discount-rate regime, geography, customer, or architecture can drive all of them.

## Root-driver taxonomy

Tag every position across:

- funded demand: AI capex, defence, electrification, healthcare, reshoring, regulation, etc.;
- physical constraint: power, memory, substrate, equipment, permit, labour, logistics, software standard;
- architecture: current and next generation;
- customer group;
- geography and currency;
- policy/export-control exposure;
- company size and liquidity;
- financing sensitivity;
- commodity and rate sensitivity;
- catalyst window.

## Concentration limits

Default research limits, adjustable to user mandate:

- single position: flag above 15% of risk capital;
- one root demand driver: flag above 35%;
- one exact constraint: flag above 25%;
- one customer ecosystem: flag above 30%;
- binary regulatory/geopolitical exposures: flag above 10% each;
- illiquid/gap-risk bucket: flag above 15% total.

These are alerts, not universal prescriptions.

## Position sizing logic

Use downside-based sizing:

```text
position_weight
≈ loss_budget_for_thesis / plausible_gap_or_bear_loss
```

Then reduce for:

- low evidence;
- poor liquidity;
- binary outcomes;
- financing needs;
- correlated portfolio drivers;
- high valuation;
- near-dated catalysts.

Increase only after evidence improves, not merely after price rises.

## Stage-aware sizing

| Lifecycle stage | Default treatment |
|---|---|
| discovery | watchlist or tiny research position |
| qualification | small, milestone-based position |
| contracted ramp | eligible for core candidate status |
| margin realization | size by valuation and remaining runway |
| consensus adoption | avoid automatic adding; reassess expectations |
| capacity response | reduce or pair with unlocker/substitute |
| normalization | harvest or exit unless new cycle emerges |

## Kelly discipline

Full Kelly is inappropriate when probabilities and tails are estimated poorly. If using Kelly-derived logic:

- use scenario distributions rather than a binary win rate;
- apply a small fraction such as one-quarter or less;
- cap by liquidity and gap risk;
- shrink probabilities toward historical base rates;
- never let a model override hard loss and concentration constraints.

## Basket versus single name

Use a basket when:

- the constraint is verified but the winner is uncertain;
- several firms have different monetization paths;
- private ownership blocks direct exposure;
- qualification outcomes are binary;
- data quality is weak.

Use a concentrated candidate only when:

- exposure is materially higher;
- financing is secure;
- customer and qualification evidence is direct;
- valuation remains asymmetric;
- the position does not duplicate existing root-driver risk.

## Hedged structures

Research may compare:

- bottleneck owner versus overvalued downstream beneficiary;
- incumbent versus substitute;
- capacity unlocker versus margin-losing buyer;
- qualified supplier versus unqualified narrative peer.

Do not recommend a short or derivative position without checking borrow, liquidity, convexity, and user mandate.

## Exit hierarchy

1. **Thesis break** — exit/reclassify when a kill switch triggers.
2. **Scarcity resolution** — reduce as supply/substitution outruns monetization.
3. **Expectation closure** — harvest when market pricing reaches or exceeds the evidence-weighted base case.
4. **Funding deterioration** — reduce when dilution or solvency changes per-share capture.
5. **Portfolio risk** — reduce even a valid thesis if root-driver concentration becomes excessive.
6. **Time stop** — review if expected milestones repeatedly fail without explanation.

A price decline alone is not a thesis break, but it changes liquidity, financing, and scenario risk and therefore requires review.

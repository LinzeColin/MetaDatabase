# Scoring model

## Design objective

The score prioritizes research; it does not predict a guaranteed return. It is deliberately gated and multiplicative because a weak dimension can invalidate the whole thesis.

## Five dimensions

Each factor is rated 0–5 and converted to a weighted 0–100 dimension score.

### 1. Structural constraint

| Factor | Weight |
|---|---:|
| funded demand | 15 |
| architectural necessity | 15 |
| current tightness | 10 |
| supplier concentration | 10 |
| qualification barrier | 15 |
| substitution difficulty | 15 |
| expansion lead time | 10 |
| policy/geographic resilience | 10 |

Interpretation:

- 0: disproved or absent;
- 1: weak narrative;
- 2: plausible, limited verification;
- 3: credible and partly quantified;
- 4: strongly evidenced;
- 5: independently verified with current numerical evidence.

### 2. Shareholder rent capture

| Factor | Weight |
|---|---:|
| exposure materiality | 15 |
| pricing power | 15 |
| capacity to ship | 15 |
| unit economics | 10 |
| contract/counterparty quality | 10 |
| appropriability/complementary assets | 10 |
| balance-sheet funding | 10 |
| dilution discipline | 10 |
| capital allocation | 5 |

A company can score highly on structural constraint and poorly here. The correct label is `BOTTLENECK_NOT_EQUITY`.

### 3. Mispricing and timing

| Factor | Weight |
|---|---:|
| market-expectation gap | 20 |
| valuation asymmetry | 20 |
| coverage/information gap | 10 |
| catalyst clarity | 15 |
| estimate-revision potential | 15 |
| crowding headroom | 10 |
| entry setup | 10 |

This dimension is time-sensitive and must use an `as_of` date.

### 4. Evidence quality

| Factor | Weight |
|---|---:|
| primary-source coverage | 25 |
| independent corroboration | 20 |
| numerical traceability | 15 |
| freshness | 15 |
| contradiction search | 15 |
| source independence | 10 |

No primary evidence for a critical claim is a hard flag even if the numerical rating is high.

### 5. Investability and risk

A high score means better investability and lower unmitigated risk.

| Factor | Weight |
|---|---:|
| liquidity | 15 |
| governance/accounting | 15 |
| geopolitical/regulatory resilience | 15 |
| customer diversification | 10 |
| technology resilience | 10 |
| balance-sheet survival | 15 |
| float/gap risk | 10 |
| portfolio fit | 10 |

## Core aggregation

```text
core_quality = geometric_mean(
  structural_constraint,
  rent_capture,
  mispricing_timing,
  evidence_quality,
  investability
)
```

The geometric mean is calculated after bounding dimension scores at a minimum positive value for numerical stability. Hard gates remain separate.

## Duration multiplier

```text
monetizable_runway = scarcity_P50 - monetization_lag
```

Default multiplier:

| Runway | Multiplier |
|---|---:|
| < 0 months | 0.50 and hard warning |
| 0–6 months | 0.70 |
| 6–12 months | 0.85 |
| 12–24 months | 1.00 |
| 24–48 months | 1.07 |
| >48 months | 1.10 |

A contracted forward ramp may justify review rather than automatic rejection when runway is under six months.

## Scenario asymmetry multiplier

For bear, base, and bull scenarios:

```text
expected_return = Σ(p_i × return_i)
downside = abs(bear_return)
asymmetry_ratio = expected_return / max(downside, 10)
```

Default multiplier:

```text
asymmetry_multiplier = clamp(0.85 + 0.35 × asymmetry_ratio, 0.75, 1.20)
```

Negative expected return caps the multiplier at 0.75.

## Final score

```text
final_score = clamp(
  core_quality × duration_multiplier × asymmetry_multiplier,
  0,
  100
)
```

The final score is subordinate to hard gates.

## Default hard gates

| Gate | Threshold/action |
|---|---|
| structural constraint < 60 | not a verified bottleneck |
| rent capture < 55 | bottleneck, not equity |
| evidence < 60 | watch for evidence |
| investability < 50 | avoid or restricted research position |
| mispricing < 45 | structurally valid but priced |
| no primary evidence | block |
| wrong entity/ticker | block |
| no material revenue bridge | block |
| substitution before monetization | block |
| material unfunded financing gap | block |
| probabilities do not sum to 1 | invalid input |

## Decision hierarchy

Hard flags first, then gates, then score:

1. `BROKEN` if a previously declared kill switch triggered.
2. `AVOID` for wrong entity, unfunded survival risk, or fatal substitution.
3. `BOTTLENECK_NOT_EQUITY` for weak rent capture.
4. `WATCH_EVIDENCE` for insufficient evidence or structural verification.
5. `WATCH_PRICED` for low mispricing despite strong business quality.
6. `RESEARCH_PRIORITY` for final score ≥75, all gates passed, and positive scenario asymmetry.
7. `CANDIDATE` for final score ≥62 with all gates passed.
8. Otherwise `WATCH_EVIDENCE` or `AVOID` according to the failed dimension.

## Why not a single additive score

An additive score can rank a company highly despite:

- no primary evidence;
- a real bottleneck owned by another entity;
- a shortage that resolves before revenue arrives;
- extreme dilution;
- a fully priced valuation.

These are logical failures, not small penalties. The model therefore uses gates, geometric aggregation, and override flags.

## Calibration policy

- Weights are priors, not universal truths.
- Do not tune weights on famous historical winners.
- Change weights only with timestamped out-of-sample cases.
- Compare against matched sector/size/liquidity benchmarks.
- Track calibration by decision bucket, not only overall average.
- Retain every historical score and version.

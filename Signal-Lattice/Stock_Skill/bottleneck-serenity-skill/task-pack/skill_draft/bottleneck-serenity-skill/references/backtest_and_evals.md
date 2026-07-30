# Backtesting, calibration, and skill evaluation

## 1. Why retrospective examples are dangerous

Bottleneck stories are especially vulnerable to:

- survivorship bias;
- hindsight reconstruction of the supply chain;
- cherry-picked publication dates;
- missing losers and position sizes;
- look-ahead use of later contracts or customer identities;
- social-media price impact;
- microcap liquidity and spread omission;
- benchmark mismatch;
- outcome-based relabeling.

Historical winners are useful for generating hypotheses, not proving alpha.

## 2. Immutable thesis ledger

At first publication, freeze:

- timestamp and data cutoff;
- original dependency graph;
- evidence available at that date;
- decision label and score;
- price, market cap, liquidity, and benchmark;
- bear/base/bull scenarios;
- expected catalysts;
- kill switches;
- hypothetical position size rule.

Future updates append versions. Never overwrite the original.

## 3. Evaluation windows

Track at minimum:

- 5, 20, 60, 120, and 250 trading days;
- maximum favorable excursion;
- maximum adverse excursion;
- total return and benchmark-relative return;
- sector/size/liquidity-matched alpha where data permits;
- thesis milestone outcomes;
- transaction-cost and gap assumptions.

Use delisted securities and failed cases.

## 4. Control groups

Compare:

- high-score candidates;
- watchlist names;
- rejected names in the same theme;
- matched sector/size/liquidity securities;
- the relevant thematic benchmark.

The most useful test is often candidate versus rejected names inside the same theme, which removes part of the thematic beta.

## 5. Causal decomposition

For each outcome estimate contributions from:

- market and sector beta;
- size, value, momentum, and quality factors;
- commodity/rate/currency exposure;
- earnings revisions;
- valuation multiple change;
- company-specific constraint evidence;
- social-media publication effect.

A profitable outcome does not validate the bottleneck thesis if returns came entirely from broad beta.

## 6. Calibration metrics

Track by decision bucket:

- precision: share of candidates that beat the matched benchmark;
- recall: share of later winners captured by the process;
- Brier score for probabilistic events;
- calibration curve by confidence band;
- median alpha, not only mean;
- downside and drawdown;
- turnover and holding period;
- false-positive reason codes;
- false-negative reason codes.

Do not optimize only hit rate; a strategy can have a high hit rate and poor expected value.

## 7. Minimum evidence before claiming improvement

Do not claim the skill has alpha from:

- fewer than roughly 30–50 independent, timestamped cases;
- less than one relevant capital-cycle phase;
- a sample dominated by one theme;
- in-sample examples used to design the scoring system;
- results without transaction costs and matched controls.

A short sample can still identify operational defects, but not robust return performance.

## 8. Codex skill evals

Evaluate both activation and behavior.

### Activation

- explicit invocation works;
- implicit theme-to-bottleneck prompts trigger;
- simple price lookup does not trigger;
- order-placement requests do not turn into execution;
- generic summaries do not trigger unnecessarily.

### Process

- maps roles before tickers;
- states `as_of` date;
- uses source tiers and claim-level evidence;
- runs negative search;
- builds three clocks;
- creates revenue bridge;
- checks valuation and portfolio overlap;
- records kill switches.

### Output

- uses one valid decision label;
- distinguishes fact/inference/assumption/forecast;
- includes strongest bear case;
- avoids unsupported certainty;
- emits valid JSON and readable memo;
- leaves no unexpected files.

### Efficiency

- reads only relevant references;
- does not repeat searches without purpose;
- does not generate a huge ticker list before mapping the system;
- stops when a hard gate makes further valuation work wasteful.

## 9. Regression policy

Every real failure becomes:

- a new eval prompt;
- a deterministic check when possible;
- a failure-mode note;
- a versioned change with before/after results.

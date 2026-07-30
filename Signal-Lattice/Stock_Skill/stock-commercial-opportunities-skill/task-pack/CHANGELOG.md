# Changelog

## 3.0.0 — 2026-07-19

Breaking redesign from generic commercial-opportunity qualification to listed-equity research triage.

- Stable ID changed from `qualify-commercial-opportunities` to `stock-commercial-opportunities`; display name changed to “股票商业机会拆解”.
- Added commercial value pool, beneficiary pathway, issuer/ticker/share-class normalization, exposure denominator and financial-capture bridge.
- Added expectations, valuation, catalyst, downside, liquidity, first-rejection and falsifier gates.
- Replaced M0–M5 business maturity with E0–E5 equity-research evidence maturity.
- Replaced business execution statuses with research-only statuses; `ADVANCE_RESEARCH` cannot authorize a trade.
- Replaced opportunity scorer/assets with stock-specific deterministic scorer, structured deliverable validator and 29-test suite.
- Added ASIC/SEC/ASX, licensed-data, public/private, MNPI, social-stock-scam, personal-advice and automated-execution boundaries.
- All v3 securities/examples are synthetic fixtures on `DEMO`; no real stock opinion is bundled.
- Preserved v1.0.0 and v2.0.0 ZIP artifacts; local installation remains prohibited.

## 2.0.0 — 2026-07-19

- Generic “商业机会拆解” package under `qualify-commercial-opportunities`.
- Separated commercial attractiveness from M0–M5 evidence maturity and thresholded validation.

## 1.0.0 — 2026-07-18

- Initial high-ROI content research package under `research-high-roi-content`.

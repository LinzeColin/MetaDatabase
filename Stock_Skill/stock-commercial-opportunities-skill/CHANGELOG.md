# Changelog

## 3.0.0 — 2026-07-19

- Moved the unchanged v3 source/backup project to the canonical repository path
  `Stock_Skill/stock-commercial-opportunities-skill/`; the v3 release ZIP and its SHA-256 remain unchanged.
- Added collection-level agent routing and a machine-validated latest-version registry; v1/v2 remain archive-only.
- Stable ID changed to `stock-commercial-opportunities`; display name changed to “股票商业机会拆解”。
- Narrowed the product from generic commercial-opportunity qualification to listed-equity research triage.
- Added issuer/ticker normalization, beneficiary pathway, exposure attribution, expectations, valuation, catalyst and falsifier gates.
- Replaced business execution statuses with research-only statuses that cannot be read as buy/sell approval.
- Added `E0`–`E5` equity-evidence maturity and explicit `needs exposure attribution` behavior.
- Added ASIC/SEC/ASX source and conduct boundaries, MNPI/publication controls and no-personal-advice gates.
- Preserved v1.0.0 and v2.0.0 archives with SHA-256 lineage; local installation remains prohibited.

## 2.0.0 — 2026-07-19

- Generic “商业机会拆解” package under `qualify-commercial-opportunities`.

## 1.0.0 — 2026-07-18

- Initial high-ROI content research package under `research-high-roi-content`.

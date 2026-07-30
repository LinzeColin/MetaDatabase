from __future__ import annotations

VERSION = "0.0.0.1.39"
PROJECT_ID = "signal-lattice"
DOMAIN = "signal-lattice.linzezhang.com"
STATUS_URL = "https://status.linzezhang.com"
RUNTIME_MODE = "DETERMINISTIC_ONLY"
MODEL_MODE = "DISABLED"
RUNTIME_TOKEN_BUDGET = 0
AUTOMATIC_TRADING = False
UPSTREAM_WRITEBACK = False
MACOS_RUNTIME_ALLOWED = False

BUSINESS_LINES = tuple(f"BL{i:02d}" for i in range(13))
SLICES = (
    "code_source", "ci", "deployment", "runtime", "entrypoint",
    "data", "backup", "monitoring", "self_heal",
)
HARD_GATE_REASONS = (
    "SKILL_VERSION_UNVALIDATED",
    "SOURCE_DRIFT",
    "DATA_NOT_POINT_IN_TIME",
    "DATA_STALE",
    "DATA_LICENSE_BLOCKED",
    "EVIDENCE_INSUFFICIENT",
    "EVIDENCE_DEPENDENCE_HIGH",
    "CRITICAL_CONFLICT",
    "OOS_EDGE_NONPOSITIVE",
    "OVERFIT_RISK_HIGH",
    "COST_EXCEEDS_EDGE",
    "LIQUIDITY_INSUFFICIENT",
    "CAPACITY_EXCEEDED",
    "PORTFOLIO_RISK_EXCEEDED",
    "ACTION_EXPIRED",
    "RUNTIME_DEGRADED",
    "ZERO_TOKEN_INVARIANT_BREACH",
)

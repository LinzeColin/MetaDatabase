from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .calibration import load_weights
from .config import Settings
from .db import RuntimeDB
from .recommendation import build_trusted_snapshot, canonical_sha256, validate_market_snapshot, validate_skill_signal
from .util import atomic_write

IDENTITY_RE = re.compile(r"^[A-Z0-9._-]{1,32}$")


def normalize_identity(value: object, name: str) -> str:
    normalized = str(value or "").strip().upper()
    if not IDENTITY_RE.fullmatch(normalized):
        raise ValueError(f"INVALID_{name.upper()}")
    return normalized


def load_policy(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 200_000:
        raise FileNotFoundError("DECISION_POLICY_MISSING")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") not in {"1.0.0", "2.0.0"}:
        raise ValueError("UNSUPPORTED_DECISION_POLICY")
    if data.get("automatic_execution_allowed") is not False:
        raise ValueError("DECISION_POLICY_AUTO_EXECUTION_FORBIDDEN")
    if data.get("runtime_agent_dependency") != 0 or data.get("runtime_llm_token_budget") != 0:
        raise ValueError("DECISION_POLICY_RUNTIME_BOUNDARY_VIOLATION")
    return data


def _decision_packet(
    symbol: str,
    market: str,
    now: datetime,
    reasons: list[str],
    *,
    action: str,
    confidence_namespace: str,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "symbol": symbol,
        "market": market,
        "action": action,
        "reasons": sorted(set(reasons)) or ["TRUSTED_INPUTS_UNAVAILABLE"],
        "valid_until": now.isoformat(),
        "human_execution_only": True,
        "automatic_execution_allowed": False,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "as_of": now.isoformat(),
        "confidence_namespace": confidence_namespace,
        "evidence_refs": [],
    }
    if diagnostics:
        packet["diagnostics"] = diagnostics
    return packet


def _system_blocked(
    symbol: str,
    market: str,
    now: datetime,
    reasons: list[str],
    *,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a truthful infrastructure/input failure state.

    SYSTEM_BLOCKED means the minute cycle could not complete because one or more
    required trusted inputs or runtime invariants were unavailable. It must not
    be presented as an investment judgement.
    """
    return _decision_packet(
        symbol,
        market,
        now,
        reasons,
        action="SYSTEM_BLOCKED",
        confidence_namespace="system_incomplete_not_an_investment_judgement",
        diagnostics=diagnostics,
    )


def _no_action(
    symbol: str,
    market: str,
    now: datetime,
    reasons: list[str],
    *,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a completed investment judgement that intentionally takes no action."""
    return _decision_packet(
        symbol,
        market,
        now,
        reasons,
        action="NO_ACTION",
        confidence_namespace="trusted_snapshot_but_not_actionable",
        diagnostics=diagnostics,
    )


def build_for_request(
    db: RuntimeDB,
    settings: Settings,
    request: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        symbol = normalize_identity(request.get("symbol"), "symbol")
        market = normalize_identity(request.get("market"), "market")
    except ValueError as exc:
        return _system_blocked("UNKNOWN", "UNKNOWN", now, [str(exc)]), None

    signals = db.skill_signals(symbol=symbol, market=market)
    market_snapshot = db.market_snapshot(symbol, market)
    if not signals or market_snapshot is None:
        reasons = []
        if not signals:
            reasons.append("NO_TRUSTED_SKILL_SIGNALS")
        if market_snapshot is None:
            reasons.append("NO_TRUSTED_MARKET_SNAPSHOT")
        return _system_blocked(symbol, market, now, reasons), None

    try:
        weights = load_weights(settings.state_dir / "calibration" / "weights.json")
        validated_signals = []
        for raw in signals:
            signal = validate_skill_signal(raw)
            signal["reliability_weight"] = weights.get(signal["skill_id"], signal.get("reliability_weight", 1.0))
            validated_signals.append(signal)
        snapshot = build_trusted_snapshot(
            validated_signals,
            validate_market_snapshot(market_snapshot),
            load_policy(settings.decision_policy_path),
            current_position_pct=float(request.get("current_position_pct", 0.0)),
            requested_position_value_usd=float(request.get("requested_position_value_usd", 0.0)),
            now=now,
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        return _system_blocked(symbol, market, now, [str(exc)]), None

    db.save_decision_snapshot(snapshot)
    snapshot_dir = settings.state_dir / "decision-snapshots" / market
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(
        snapshot_dir / f"{symbol}.json",
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
    )

    gates = snapshot["gates"]
    recommendation = snapshot["recommendation"]
    failed = [key for key, value in gates.items() if value is not True]
    if failed or not settings.recommendation_enabled:
        reasons = failed or ["HUMAN_RECOMMENDATION_MODE_DISABLED"]
        return (
            _no_action(symbol, market, now, reasons, diagnostics=recommendation)
            | {
                "valid_until": recommendation["valid_until"],
                "as_of": recommendation["as_of"],
                "evidence_refs": recommendation["evidence_refs"],
                "decision_snapshot_sha256": canonical_sha256(snapshot),
            },
            snapshot,
        )

    packet = dict(recommendation)
    packet["action"] = packet.pop("recommended_action")
    packet["reasons"] = []
    packet["runtime_agent_dependency"] = 0
    packet["runtime_llm_tokens"] = 0
    packet["decision_snapshot_sha256"] = canonical_sha256(snapshot)
    packet["confidence_namespace"] = "signal_lattice_calibrated_human_decision_support"
    return packet, snapshot

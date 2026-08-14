from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import APP_VERSION, PROMPT_VERSION, REFRESH_SECONDS


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


@dataclass(frozen=True)
class Settings:
    state_dir: Path
    config_dir: Path
    web_dir: Path
    fixture_dir: Path
    host: str
    port: int
    refresh_seconds: int
    report_stale_seconds: int
    market_provider: str
    public_url: str
    status_url: str
    runtime: dict[str, Any]
    canonical_state: dict[str, Any]
    bucket_config: dict[str, Any]
    skill_routes: dict[str, Any]
    sources: dict[str, Any]

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "Settings":
        root = project_root or Path(__file__).resolve().parents[2]
        config_dir = Path(os.environ.get("SL19_CONFIG_DIR", str(root / "config"))).resolve()
        web_dir = Path(os.environ.get("SL19_WEB_DIR", str(root / "web"))).resolve()
        fixture_dir = Path(os.environ.get("SL19_FIXTURE_DIR", str(root / "fixtures"))).resolve()
        state_dir = Path(os.environ.get("SL19_STATE_DIR", "/var/lib/signal-lattice-v19")).resolve()
        runtime = read_json(config_dir / "v19_runtime.json")
        canonical_state = read_json(config_dir / "v19_canonical_state.json")
        bucket_config = read_json(config_dir / "v19_buckets.json")
        skill_routes = read_json(config_dir / "v19_skill_routes.json")
        sources = read_json(config_dir / "v19_sources.json")

        refresh_seconds = int(os.environ.get("SL19_REFRESH_SECONDS", runtime.get("refresh_seconds", REFRESH_SECONDS)))
        if refresh_seconds != REFRESH_SECONDS:
            raise ValueError("V19_REFRESH_MUST_REMAIN_15_SECONDS")
        if runtime.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("V19_PROMPT_VERSION_MISMATCH")
        if runtime.get("app_version") != APP_VERSION:
            raise ValueError("APP_VERSION_MISMATCH")

        host = os.environ.get("SL19_HOST", "127.0.0.1")
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("API_MUST_BIND_LOOPBACK")
        port = int(os.environ.get("SL19_PORT", "8787"))
        if not 1 <= port <= 65535:
            raise ValueError("INVALID_PORT")
        market_provider = os.environ.get("SL19_MARKET_PROVIDER", str(runtime.get("market_provider", "moomoo"))).strip().lower()
        if market_provider not in {"moomoo", "fixture"}:
            raise ValueError("UNSUPPORTED_MARKET_PROVIDER")
        if os.environ.get("SL19_ENABLE_TRADING", "0") == "1":
            raise ValueError("REAL_TRADING_PERMANENTLY_FORBIDDEN")

        return cls(
            state_dir=state_dir,
            config_dir=config_dir,
            web_dir=web_dir,
            fixture_dir=fixture_dir,
            host=host,
            port=port,
            refresh_seconds=refresh_seconds,
            report_stale_seconds=int(runtime.get("report_stale_seconds", 45)),
            market_provider=market_provider,
            public_url=os.environ.get("SL19_PUBLIC_URL", str(runtime.get("public_url"))),
            status_url=os.environ.get("SL19_STATUS_URL", str(runtime.get("status_url"))),
            runtime=runtime,
            canonical_state=canonical_state,
            bucket_config=bucket_config,
            skill_routes=skill_routes,
            sources=sources,
        )

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    @property
    def app_version(self) -> str:
        return APP_VERSION

    @property
    def switch_gate_pct(self) -> float:
        gate = self.runtime["switch_gate"]
        quality = str(gate.get("default_evidence_quality", "medium"))
        uncertainty = float(gate["evidence_uncertainty"][quality])
        return (
            float(gate["base_round_trip_pct"])
            + float(gate["high_liquidity_spread_slippage_pct"])
            + float(gate["state_break_pct"])
            + uncertainty
        )

    @property
    def tactical_floor_pct(self) -> float:
        return float(self.runtime["switch_gate"]["tactical_20d_floor_pct"])

    @property
    def reserve_pct(self) -> float:
        return float(self.runtime["risk"]["stale_liquidity_reserve_pct"])

    @property
    def hard_failure_drawdown_pct(self) -> float:
        return float(self.runtime["risk"]["hard_failure_drawdown_pct"])

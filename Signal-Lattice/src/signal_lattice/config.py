from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    state_dir: Path
    artifact_dir: Path
    web_dir: Path
    host: str = "127.0.0.1"
    port: int = 8787
    worker_lease_seconds: int = 120
    max_request_bytes: int = 131072
    request_timeout_seconds: int = 15
    recommendation_enabled: bool = False
    runtime_environment: str = "prebuild"
    decision_policy_path: Path = Path("config/decision_policy.json")
    public_url: str = "https://signal-lattice.linzezhang.com"
    status_url: str = "https://status.linzezhang.com"
    ingest_token_file: Path = Path("/etc/signal-lattice/credentials/ingest_api_token")

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "Settings":
        root = project_root or Path(__file__).resolve().parents[2]
        state = Path(os.environ.get("SIGNAL_LATTICE_STATE_DIR", "/var/lib/signal-lattice"))
        artifacts = Path(os.environ.get("SIGNAL_LATTICE_ARTIFACT_DIR", str(state / "artifacts")))
        web = Path(os.environ.get("SIGNAL_LATTICE_WEB_DIR", str(root / "web")))
        host = os.environ.get("SIGNAL_LATTICE_HOST", "127.0.0.1")
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("Signal Lattice API must bind to loopback behind the approved ingress")
        port = int(os.environ.get("SIGNAL_LATTICE_PORT", "8787"))
        lease = int(os.environ.get("SIGNAL_LATTICE_LEASE_SECONDS", "120"))
        max_request = int(os.environ.get("SIGNAL_LATTICE_MAX_REQUEST_BYTES", "131072"))
        request_timeout = int(os.environ.get("SIGNAL_LATTICE_REQUEST_TIMEOUT_SECONDS", "15"))
        if not (1 <= port <= 65535):
            raise ValueError("INVALID_PORT")
        if not (5 <= lease <= 3600):
            raise ValueError("INVALID_LEASE_SECONDS")
        if not (1024 <= max_request <= 2_000_000):
            raise ValueError("INVALID_MAX_REQUEST_BYTES")
        if not (1 <= request_timeout <= 120):
            raise ValueError("INVALID_REQUEST_TIMEOUT")
        mode = os.environ.get("SIGNAL_LATTICE_RECOMMENDATION_MODE", "RESEARCH_AND_NO_ACTION")
        if mode not in {"RESEARCH_AND_NO_ACTION", "HUMAN_DECISION_SUPPORT"}:
            raise ValueError("INVALID_RECOMMENDATION_MODE")
        if os.environ.get("SIGNAL_LATTICE_LIVE_ACTION", "0") == "1":
            raise ValueError("AUTOMATIC_OR_UNSCOPED_LIVE_ACTION_FORBIDDEN")
        policy = Path(os.environ.get("SIGNAL_LATTICE_DECISION_POLICY", str(root / "config" / "decision_policy.json")))
        return cls(
            state_dir=state,
            artifact_dir=artifacts,
            web_dir=web,
            host=host,
            port=port,
            worker_lease_seconds=lease,
            max_request_bytes=max_request,
            request_timeout_seconds=request_timeout,
            recommendation_enabled=mode == "HUMAN_DECISION_SUPPORT",
            runtime_environment=os.environ.get("SIGNAL_LATTICE_ENV", "prebuild"),
            decision_policy_path=policy,
            public_url=os.environ.get("SIGNAL_LATTICE_PUBLIC_URL", "https://signal-lattice.linzezhang.com"),
            status_url=os.environ.get("SIGNAL_LATTICE_STATUS_URL", "https://status.linzezhang.com"),
            ingest_token_file=Path(os.environ.get("SIGNAL_LATTICE_INGEST_TOKEN_FILE", "/etc/signal-lattice/credentials/ingest_api_token")),
        )

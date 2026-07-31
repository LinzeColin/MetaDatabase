from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CANONICAL_STOCK_SKILL_SPARSE_PATH = "Signal-Lattice/Stock_Skill"


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
    recommendation_enabled: bool = True
    runtime_environment: str = "prebuild"
    decision_policy_path: Path = Path("config/decision_policy.json")
    public_url: str = "https://signal-lattice.linzezhang.com"
    status_url: str = "https://status.linzezhang.com"
    ingest_token_file: Path = Path("/etc/signal-lattice/credentials/ingest_api_token")
    cycle_interval_seconds: int = 60
    cycle_deadline_seconds: int = 55
    skill_timeout_seconds: int = 8
    skill_memory_mb: int = 256
    minimum_active_skills: int = 5
    minimum_completed_skills: int = 3
    market_provider: str = "fixture"
    universe_path: Path = Path("config/universe.json")
    runtime_manifest_dir: Path = Path("config/runtime_manifests")
    upstream_repo_url: str = "https://github.com/LinzeColin/MetaDatabase.git"
    upstream_branch: str = "main"
    upstream_sparse_path: str = CANONICAL_STOCK_SKILL_SPARSE_PATH
    upstream_checkout_dir: Path = Path("/var/lib/signal-lattice/upstream/MetaDatabase")
    agent_upstream_repo_url: str = "https://github.com/LinzeColin/AgentDatabase.git"
    agent_upstream_branch: str = "main"
    agent_upstream_sparse_path: str = "CodexSkills/registry/codex/serenity-skill"
    agent_upstream_checkout_dir: Path = Path("/var/lib/signal-lattice/upstream/AgentDatabase")
    isolation_backend: str = "subprocess_guard"

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
        cycle_interval = int(os.environ.get("SIGNAL_LATTICE_CYCLE_INTERVAL_SECONDS", "60"))
        cycle_deadline = int(os.environ.get("SIGNAL_LATTICE_CYCLE_DEADLINE_SECONDS", "55"))
        skill_timeout = int(os.environ.get("SIGNAL_LATTICE_SKILL_TIMEOUT_SECONDS", "8"))
        skill_memory = int(os.environ.get("SIGNAL_LATTICE_SKILL_MEMORY_MB", "256"))
        minimum_active = int(os.environ.get("SIGNAL_LATTICE_MINIMUM_ACTIVE_SKILLS", "5"))
        minimum_completed = int(os.environ.get("SIGNAL_LATTICE_MINIMUM_COMPLETED_SKILLS", "3"))
        if not (1 <= port <= 65535):
            raise ValueError("INVALID_PORT")
        if not (5 <= lease <= 3600):
            raise ValueError("INVALID_LEASE_SECONDS")
        if not (1024 <= max_request <= 2_000_000):
            raise ValueError("INVALID_MAX_REQUEST_BYTES")
        if not (1 <= request_timeout <= 120):
            raise ValueError("INVALID_REQUEST_TIMEOUT")
        if cycle_interval != 60:
            raise ValueError("NORTHSTAR_REQUIRES_60_SECOND_CYCLE")
        if not (20 <= cycle_deadline < cycle_interval):
            raise ValueError("INVALID_CYCLE_DEADLINE_SECONDS")
        if not (1 <= skill_timeout <= cycle_deadline):
            raise ValueError("INVALID_SKILL_TIMEOUT_SECONDS")
        if not (64 <= skill_memory <= 2048):
            raise ValueError("INVALID_SKILL_MEMORY_MB")
        if not (1 <= minimum_completed <= minimum_active <= 64):
            raise ValueError("INVALID_SKILL_COMPLETION_POLICY")
        mode = os.environ.get("SIGNAL_LATTICE_RECOMMENDATION_MODE", "HUMAN_DECISION_SUPPORT")
        if mode not in {"RESEARCH_AND_NO_ACTION", "HUMAN_DECISION_SUPPORT"}:
            raise ValueError("INVALID_RECOMMENDATION_MODE")
        if os.environ.get("SIGNAL_LATTICE_LIVE_ACTION", "0") == "1":
            raise ValueError("AUTOMATIC_OR_UNSCOPED_LIVE_ACTION_FORBIDDEN")
        runtime_environment = os.environ.get("SIGNAL_LATTICE_ENV", "prebuild").strip().lower()
        provider = os.environ.get("SIGNAL_LATTICE_MARKET_PROVIDER", "fixture").strip().lower()
        if provider not in {"fixture", "moomoo"}:
            raise ValueError("UNSUPPORTED_MARKET_PROVIDER")
        if runtime_environment == "production" and provider == "fixture":
            raise ValueError("PRODUCTION_REQUIRES_LIVE_APPROVED_MARKET_PROVIDER")
        isolation = os.environ.get("SIGNAL_LATTICE_ISOLATION_BACKEND", "subprocess_guard")
        if isolation not in {"subprocess_guard", "systemd_run"}:
            raise ValueError("UNSUPPORTED_ISOLATION_BACKEND")
        policy = Path(os.environ.get("SIGNAL_LATTICE_DECISION_POLICY", str(root / "config" / "decision_policy.json")))
        universe = Path(os.environ.get("SIGNAL_LATTICE_UNIVERSE_FILE", str(root / "config" / "universe.json")))
        manifest_dir = Path(os.environ.get("SIGNAL_LATTICE_RUNTIME_MANIFEST_DIR", str(root / "config" / "runtime_manifests")))
        upstream_sparse_path = os.environ.get(
            "SIGNAL_LATTICE_UPSTREAM_SPARSE_PATH", CANONICAL_STOCK_SKILL_SPARSE_PATH
        )
        if upstream_sparse_path != CANONICAL_STOCK_SKILL_SPARSE_PATH:
            raise ValueError("NON_CANONICAL_STOCK_SKILL_SPARSE_PATH")
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
            runtime_environment=runtime_environment,
            decision_policy_path=policy,
            public_url=os.environ.get("SIGNAL_LATTICE_PUBLIC_URL", "https://signal-lattice.linzezhang.com"),
            status_url=os.environ.get("SIGNAL_LATTICE_STATUS_URL", "https://status.linzezhang.com"),
            ingest_token_file=Path(os.environ.get("SIGNAL_LATTICE_INGEST_TOKEN_FILE", "/etc/signal-lattice/credentials/ingest_api_token")),
            cycle_interval_seconds=cycle_interval,
            cycle_deadline_seconds=cycle_deadline,
            skill_timeout_seconds=skill_timeout,
            skill_memory_mb=skill_memory,
            minimum_active_skills=minimum_active,
            minimum_completed_skills=minimum_completed,
            market_provider=provider,
            universe_path=universe,
            runtime_manifest_dir=manifest_dir,
            upstream_repo_url=os.environ.get("SIGNAL_LATTICE_UPSTREAM_REPO", "https://github.com/LinzeColin/MetaDatabase.git"),
            upstream_branch=os.environ.get("SIGNAL_LATTICE_UPSTREAM_BRANCH", "main"),
            upstream_sparse_path=upstream_sparse_path,
            upstream_checkout_dir=Path(os.environ.get("SIGNAL_LATTICE_UPSTREAM_CHECKOUT_DIR", str(state / "upstream" / "MetaDatabase"))),
            agent_upstream_repo_url=os.environ.get("SIGNAL_LATTICE_AGENT_UPSTREAM_REPO", "https://github.com/LinzeColin/AgentDatabase.git"),
            agent_upstream_branch=os.environ.get("SIGNAL_LATTICE_AGENT_UPSTREAM_BRANCH", "main"),
            agent_upstream_sparse_path=os.environ.get("SIGNAL_LATTICE_AGENT_UPSTREAM_SPARSE_PATH", "CodexSkills/registry/codex/serenity-skill"),
            agent_upstream_checkout_dir=Path(os.environ.get("SIGNAL_LATTICE_AGENT_UPSTREAM_CHECKOUT_DIR", str(state / "upstream" / "AgentDatabase"))),
            isolation_backend=isolation,
        )

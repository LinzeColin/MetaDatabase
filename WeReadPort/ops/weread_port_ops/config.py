from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    state_dir: Path
    db_path: Path
    status_path: Path
    site_url: str
    official_skill_url: str
    private_db_client: Path | None
    private_db_area: str
    private_db_relroot: str
    retention_hours: int
    timeout_seconds: float
    restic_repository: str
    r2_remote: str
    oci_remote: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        state_dir = Path(values.get("WEREAD_PORT_STATE_DIR", str(Path.home() / ".local/state/weread-port-ops"))).expanduser()
        db_path = Path(values.get("WEREAD_PORT_DB_PATH", str(state_dir / "runtime.sqlite3"))).expanduser()
        status_path = Path(values.get("WEREAD_PORT_STATUS_PATH", str(state_dir / "public-status.json"))).expanduser()
        site_url = _validated_origin(values.get("WEREAD_PORT_SITE_URL", ""))
        skill_url = _validated_https_url(
            values.get(
                "WEREAD_PORT_OFFICIAL_SKILL_URL",
                "https://raw.githubusercontent.com/Tencent/WeChatReading/main/skills/SKILL.md",
            )
        )
        client_raw = values.get("WEREAD_PORT_PRIVATE_DB_CLIENT", "").strip()
        private_db_client = Path(client_raw).expanduser() if client_raw else None
        retention_hours = _bounded_int(values.get("WEREAD_PORT_RETENTION_HOURS", "72"), 1, 720, "retention")
        timeout_seconds = _bounded_float(values.get("WEREAD_PORT_HTTP_TIMEOUT_SECONDS", "10"), 1.0, 60.0, "timeout")
        area = values.get("WEREAD_PORT_PRIVATE_DB_AREA", "Private-MetaDatabase").strip()
        if area != "Private-MetaDatabase":
            raise ValueError("Private Database area must remain Private-MetaDatabase")
        relroot = values.get("WEREAD_PORT_PRIVATE_DB_RELROOT", "operations/weread-port").strip().strip("/")
        if not relroot or any(part in {"", ".", ".."} for part in relroot.split("/")):
            raise ValueError("Private Database relative root is unsafe")
        return cls(
            state_dir=state_dir,
            db_path=db_path,
            status_path=status_path,
            site_url=site_url,
            official_skill_url=skill_url,
            private_db_client=private_db_client,
            private_db_area=area,
            private_db_relroot=relroot,
            retention_hours=retention_hours,
            timeout_seconds=timeout_seconds,
            restic_repository=values.get("RESTIC_REPOSITORY", "").strip(),
            r2_remote=values.get("WEREAD_PORT_R2_REMOTE", "").strip(),
            oci_remote=values.get("WEREAD_PORT_OCI_REMOTE", "").strip(),
        )

    def ensure_state_dirs(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.status_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)


def _validated_origin(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("WEREAD_PORT_SITE_URL must be a credential-free HTTPS origin")
    return f"https://{parsed.netloc}"


def _validated_https_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("URL must be credential-free HTTPS")
    return value.strip()


def _bounded_int(value: str, minimum: int, maximum: int, label: str) -> int:
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{label} out of range")
    return parsed


def _bounded_float(value: str, minimum: float, maximum: float, label: str) -> float:
    parsed = float(value)
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{label} out of range")
    return parsed

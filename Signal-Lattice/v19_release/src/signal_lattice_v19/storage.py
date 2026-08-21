from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


class StateConflictError(RuntimeError):
    """The canonical strategy state needs an explicit recovery decision."""


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, "STATE_FILE_UNREADABLE"
    except UnicodeDecodeError:
        return None, "STATE_FILE_ENCODING_INVALID"
    except json.JSONDecodeError:
        return None, "STATE_FILE_JSON_INVALID"
    if not isinstance(value, dict):
        return None, "STATE_FILE_OBJECT_REQUIRED"
    return value, None


class RuntimeStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "history").mkdir(exist_ok=True)
        (self.root / "observations").mkdir(exist_ok=True)
        (self.root / "skills").mkdir(exist_ok=True)
        (self.root / "conflicts").mkdir(exist_ok=True)
        self._state_conflict: dict[str, Any] | None = None

    @property
    def state_file(self) -> Path:
        return self.root / "strategy_state.json"

    @property
    def last_known_state_file(self) -> Path:
        return self.root / "strategy_state.last_known.json"

    @property
    def state_conflict_file(self) -> Path:
        return self.root / "strategy_state.conflict.json"

    @property
    def has_state_conflict(self) -> bool:
        return self._state_conflict is not None or self.state_conflict_file.is_file()

    @property
    def state_conflict(self) -> dict[str, Any] | None:
        return dict(self._state_conflict) if self._state_conflict else None

    @property
    def latest_file(self) -> Path:
        return self.root / "latest.json"

    @property
    def latest_text_file(self) -> Path:
        return self.root / "latest.txt"

    @property
    def universe_cache_file(self) -> Path:
        return self.root / "universe_cache.json"

    @property
    def scan_state_file(self) -> Path:
        return self.root / "scan_state.json"

    @property
    def market_cache_file(self) -> Path:
        return self.root / "market_cache.json"

    @property
    def whitebox_db_file(self) -> Path:
        return self.root / "whitebox.sqlite3"

    def bootstrap(self, canonical_state: dict[str, Any]) -> dict[str, Any]:
        conflict, conflict_error = _read_json_object(self.state_conflict_file)
        if conflict is not None:
            self._state_conflict = conflict
            last_known, _ = _read_json_object(self.last_known_state_file)
            return dict(last_known or canonical_state)
        if conflict_error:
            self._state_conflict = {
                "state": "CONFLICT",
                "reason": "STATE_CONFLICT_RECORD_INVALID",
            }
            return dict(canonical_state)

        current, state_error = _read_json_object(self.state_file)
        if current is not None:
            self._state_conflict = None
            write_json(self.last_known_state_file, current)
            return current
        if state_error is None:
            self._state_conflict = None
            write_json(self.state_file, canonical_state)
            write_json(self.last_known_state_file, canonical_state)
            return dict(canonical_state)

        detected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        quarantined_name: str | None = None
        if self.state_file.is_file():
            quarantined = self.root / "conflicts" / (
                f"strategy_state.{detected_at.replace(':', '').replace('+', '_')}.corrupt.json"
            )
            os.replace(self.state_file, quarantined)
            quarantined_name = quarantined.name
        last_known, _ = _read_json_object(self.last_known_state_file)
        marker = {
            "state": "CONFLICT",
            "reason": state_error,
            "detected_at": detected_at,
            "quarantined_file": quarantined_name,
            "recovery": "EXPLICIT_RESTORE_REQUIRED",
            "last_known_available": last_known is not None,
        }
        write_json(self.state_conflict_file, marker)
        self._state_conflict = marker
        return dict(last_known or canonical_state)

    def load_state(self, canonical_state: dict[str, Any]) -> dict[str, Any]:
        return self.bootstrap(canonical_state)

    def save_state(self, state: dict[str, Any]) -> None:
        if self.has_state_conflict:
            raise StateConflictError("STATE_CONFLICT_REQUIRES_EXPLICIT_RECOVERY")
        write_json(self.state_file, state)
        write_json(self.last_known_state_file, state)

    def resolve_state_conflict(self, state: dict[str, Any], recovery_reason: str) -> None:
        """Restore a reviewed state and retain the conflict record as history."""
        if not self.has_state_conflict:
            raise StateConflictError("STATE_CONFLICT_NOT_PRESENT")
        if not isinstance(state, dict) or not state:
            raise StateConflictError("STATE_RECOVERY_STATE_REQUIRED")
        reason = str(recovery_reason).strip()
        if not reason:
            raise StateConflictError("STATE_RECOVERY_REASON_REQUIRED")
        marker = self.state_conflict or {"state": "CONFLICT"}
        resolved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        write_json(
            self.root / "conflicts" / (
                f"strategy_state.{resolved_at.replace(':', '').replace('+', '_')}.resolved.json"
            ),
            {**marker, "resolved_at": resolved_at, "recovery_reason": reason},
        )
        write_json(self.state_file, state)
        write_json(self.last_known_state_file, state)
        if self.state_conflict_file.exists():
            self.state_conflict_file.unlink()
        self._state_conflict = None

    def load_universe(self) -> dict[str, Any] | None:
        value = read_json(self.universe_cache_file)
        return value if isinstance(value, dict) else None

    def save_universe(self, value: dict[str, Any]) -> None:
        write_json(self.universe_cache_file, value)

    def load_market(self) -> dict[str, Any] | None:
        value = read_json(self.market_cache_file)
        return value if isinstance(value, dict) else None

    def save_market(self, value: dict[str, Any]) -> None:
        write_json(self.market_cache_file, value)

    def load_scan_state(self) -> dict[str, Any]:
        value = read_json(self.scan_state_file, {})
        return value if isinstance(value, dict) else {}

    def save_scan_state(self, value: dict[str, Any]) -> None:
        write_json(self.scan_state_file, value)

    def save_cycle(
        self,
        envelope: dict[str, Any],
        rendered: str,
        date_key: str,
        slot_key: str,
        *,
        decision_id: str | None = None,
        decision_changed: bool = True,
    ) -> None:
        write_json(self.latest_file, envelope)
        atomic_text(self.latest_text_file, rendered + "\n")

        observation_path = self.root / "observations" / f"{date_key}.jsonl"
        with observation_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "generated_at": envelope.get("generated_at"),
                "decision_id": decision_id,
                "decision_changed": decision_changed,
                "report": envelope.get("report"),
            }, ensure_ascii=False, separators=(",", ":")) + "\n")

        if not decision_changed:
            return
        skill_payload = envelope.get("internal", {}).get("skills", [])
        skill_name = f"{decision_id or slot_key}.json"
        write_json(self.root / "skills" / skill_name, skill_payload)
        history_path = self.root / "history" / f"{date_key}.jsonl"
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")

    def latest(self) -> dict[str, Any] | None:
        value = read_json(self.latest_file)
        return value if isinstance(value, dict) else None

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        files = sorted((self.root / "history").glob("*.jsonl"), reverse=True)
        rows: list[dict[str, Any]] = []
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
                if len(rows) >= limit:
                    return rows
        return rows

from __future__ import annotations

import json
import os
import tempfile
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


class RuntimeStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "history").mkdir(exist_ok=True)
        (self.root / "observations").mkdir(exist_ok=True)
        (self.root / "skills").mkdir(exist_ok=True)

    @property
    def state_file(self) -> Path:
        return self.root / "strategy_state.json"

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
        current = read_json(self.state_file)
        if isinstance(current, dict):
            return current
        write_json(self.state_file, canonical_state)
        return dict(canonical_state)

    def load_state(self, canonical_state: dict[str, Any]) -> dict[str, Any]:
        return self.bootstrap(canonical_state)

    def save_state(self, state: dict[str, Any]) -> None:
        write_json(self.state_file, state)

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

"""The recent-filings watcher must not forget a push that failed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.authoritative import watch_recent_filings as watcher


@pytest.fixture()
def state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "watch_state.json"
    monkeypatch.setattr(watcher, "STATE_PATH", path)
    monkeypatch.setenv("EEI_PUBLISH_URL", "https://example.test/exec")
    monkeypatch.setenv("EEI_PUBLISH_TOKEN", "t")
    return path


def _saved(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_failed_push_is_kept_and_retried_with_the_original_since(
    state_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def failing(entities: list[str], **kwargs: Any) -> dict[str, Any]:
        calls.append({"entities": entities, **kwargs})
        raise RuntimeError("D1 daily quota")

    monkeypatch.setattr(watcher, "push_incremental", failing)
    first: dict[str, Any] = {"started_at": "2026-09-30T10:00:00+00:00"}
    watcher._push_and_save(first, {}, ["acc-1"], {"entity-a": ("entity-a", "A")}, apply=True)
    assert "publish_error" in first
    pending = _saved(state_file)["pending_push"]
    assert pending == {"since": "2026-09-30T10:00:00+00:00", "entities": ["entity-a"]}
    assert calls[0]["include_relationships"] is False

    # Next poll: nothing new, but the earlier failure is retried - with its own
    # (older) `since`, and merged with any newly affected entity.
    def working(entities: list[str], **kwargs: Any) -> dict[str, Any]:
        calls.append({"entities": entities, **kwargs})
        return {"upserted": {"events": 3}}

    monkeypatch.setattr(watcher, "push_incremental", working)
    second: dict[str, Any] = {"started_at": "2026-09-30T10:05:00+00:00"}
    watcher._push_and_save(
        second, {"pending_push": pending}, ["acc-1"], {"entity-b": ("entity-b", "B")}, apply=True
    )
    assert second["published"] == {"upserted": {"events": 3}}
    assert calls[-1]["entities"] == ["entity-a", "entity-b"]
    assert calls[-1]["since"] == "2026-09-30T10:00:00+00:00"
    assert "pending_push" not in _saved(state_file), "success clears the pending push"


def test_nothing_to_push_leaves_no_pending_state(
    state_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_run(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("no push expected")

    monkeypatch.setattr(watcher, "push_incremental", must_not_run)
    watcher._push_and_save({"started_at": "x"}, {}, ["acc"], {}, apply=True)
    assert "pending_push" not in _saved(state_file)

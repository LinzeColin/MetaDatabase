from __future__ import annotations

import json

from moomooau_archive.cli import COMMANDS, create_parser, main


def _command_choices() -> set[str]:
    parser = create_parser()
    action = next(item for item in parser._actions if getattr(item, "choices", None))
    return set(action.choices)


def test_t0102_cli_has_exact_actions_only_synthetic_surface(monkeypatch, capsys) -> None:
    assert _command_choices() == set(COMMANDS)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert main(["discover", "--synthetic"]) == 2
    assert json.loads(capsys.readouterr().out)["failure_code"] == "ACTIONS_ONLY"

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert main(["discover"]) == 2
    assert json.loads(capsys.readouterr().out)["failure_code"] == "SYNTHETIC_MODE_REQUIRED"

    for command in ("discover", "classify", "process", "timeline", "m3", "reconcile"):
        assert main([command, "--synthetic"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload.get("external_calls", 0) == 0
        assert payload.get("gmail_mutations", 0) == 0
        assert payload.get("synthetic_only", True) is True


def test_t0102_cli_exposes_no_credential_or_remote_option() -> None:
    help_text = create_parser().format_help().casefold()
    for forbidden in ("token", "password", "oauth", "repository", "endpoint"):
        assert forbidden not in help_text

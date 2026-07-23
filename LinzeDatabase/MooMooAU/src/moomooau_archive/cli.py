"""Actions-only CLI surface. Stage 1 accepts synthetic fixtures and performs no mutation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

from .adapters import EphemeralAgeSession, MemoryCiphertextStore, TrackedSyntheticSource
from .fixtures import build_fixture_set
from .pipeline import archive_candidate
from .verification import SyntheticVerifier

COMMANDS = ("discover", "classify", "archive", "process", "timeline", "m3", "reconcile")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moomooau-archive")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparser = subparsers.add_parser(command)
        subparser.add_argument(
            "--synthetic",
            action="store_true",
            help="required Stage 1 fixture-only execution mode",
        )
    return parser


def _emit(payload: dict[str, object]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")


def _synthetic_status(command: str) -> dict[str, object]:
    return {
        "command": command,
        "run_status": "DEGRADED",
        "stage": "S1",
        "synthetic_only": True,
        "external_calls": 0,
        "gmail_mutations": 0,
        "failure_code": "STAGE_1_SYNTHETIC_ONLY",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if os.environ.get("GITHUB_ACTIONS") != "true":
        _emit({"run_status": "UNHEALTHY", "failure_code": "ACTIONS_ONLY"})
        return 2
    if not args.synthetic:
        _emit({"run_status": "UNHEALTHY", "failure_code": "SYNTHETIC_MODE_REQUIRED"})
        return 2

    fixtures = build_fixture_set()
    source = TrackedSyntheticSource((fixtures.verified, fixtures.unrelated, fixtures.spoofed))
    verifier = SyntheticVerifier()
    if args.command == "discover":
        payload = _synthetic_status(args.command)
        payload["candidate_count_bucket"] = "ONE_TO_NINE"
        _emit(payload)
        return 0
    if args.command == "classify":
        payload = _synthetic_status(args.command)
        verification = verifier.verify(fixtures.verified.metadata)
        payload["decision"] = verification.decision.value
        payload["document_class"] = verification.document_class
        _emit(payload)
        return 0
    if args.command == "archive":
        with EphemeralAgeSession() as cipher:
            archive_result = archive_candidate(
                fixtures.verified.metadata,
                source=source,
                verifier=verifier,
                cipher=cipher,
                remote=MemoryCiphertextStore(),
            )
        _emit(archive_result.public_evidence)
        return 0

    _emit(_synthetic_status(args.command))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

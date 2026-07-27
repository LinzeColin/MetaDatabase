from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

# Support both ``python -m equity_foresight_signal.cli`` and the documented
# direct-script form ``python equity_foresight_signal/cli.py`` without relying
# on the current working directory or an installed package.
if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from equity_foresight_signal.canonical import strict_json_loads
    from equity_foresight_signal.dataset import MAX_DATASET_BYTES, validate_pit_dataset
    from equity_foresight_signal.engine import DEFAULT_LIMITS, evaluate, self_check, validate_bundle
    from equity_foresight_signal.errors import EFSError
    from equity_foresight_signal.lifecycle import compare_candidate_to_lkg, health_snapshot
    from equity_foresight_signal.runtime_audit import audit_runtime_source
    from equity_foresight_signal.status_adapter import build_host_status_payload
    from equity_foresight_signal.training import train_direction_pipeline
else:
    from .canonical import strict_json_loads
    from .dataset import MAX_DATASET_BYTES, validate_pit_dataset
    from .engine import DEFAULT_LIMITS, evaluate, self_check, validate_bundle
    from .errors import EFSError
    from .lifecycle import compare_candidate_to_lkg, health_snapshot
    from .runtime_audit import audit_runtime_source
    from .status_adapter import build_host_status_payload
    from .training import train_direction_pipeline

CLI_SCHEMA = "efs.cli_result.v1"


def _read_limited(path_value: str, *, field: str, limit: int) -> bytes:
    path = Path(path_value)
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise EFSError("INPUT_IO_ERROR", f"{field} cannot be inspected") from exc
    if path.is_symlink() or not path.is_file():
        raise EFSError("INPUT_IO_ERROR", f"{field} must be a regular non-symlink file")
    if stat_result.st_size > limit:
        raise EFSError("RESOURCE_LIMIT", f"{field} exceeds byte limit")
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError as exc:
        raise EFSError("INPUT_IO_ERROR", f"{field} cannot be read") from exc
    if len(data) > limit:
        raise EFSError("RESOURCE_LIMIT", f"{field} exceeds byte limit")
    return data


def _error_result(error: EFSError) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": CLI_SCHEMA,
        "status": "ERROR",
        "reason_code": error.code,
        "reason_zh": error.message,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="股势前瞻内部工程候选 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-check")
    health = sub.add_parser("health-snapshot")
    health.add_argument("--bundle")
    health.add_argument("--as-of")
    compare = sub.add_parser("compare-bundles")
    compare.add_argument("candidate")
    compare.add_argument("lkg")
    validate = sub.add_parser("validate-bundle")
    validate.add_argument("bundle")
    run = sub.add_parser("evaluate")
    run.add_argument("request")
    run.add_argument("bundle")
    run.add_argument("--trust-context")
    audit = sub.add_parser("audit-runtime")
    audit.add_argument("--package-root")
    dataset = sub.add_parser("validate-dataset")
    dataset.add_argument("dataset")
    train = sub.add_parser("train-direction")
    train.add_argument("dataset")
    train.add_argument("config")
    status = sub.add_parser("host-status")
    status.add_argument("--as-of", required=True)
    status.add_argument("--bundle")
    status.add_argument("--outcome-report")
    status.add_argument("--promotion-decision")
    return parser


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "self-check":
        return self_check()
    if args.command == "health-snapshot":
        bundle = _read_limited(args.bundle, field="bundle", limit=DEFAULT_LIMITS["bundle_bytes"]) if args.bundle else None
        return health_snapshot(bundle, as_of=args.as_of)
    if args.command == "compare-bundles":
        candidate = _read_limited(args.candidate, field="candidate", limit=DEFAULT_LIMITS["bundle_bytes"])
        lkg = _read_limited(args.lkg, field="lkg", limit=DEFAULT_LIMITS["bundle_bytes"])
        return compare_candidate_to_lkg(candidate, lkg)
    if args.command == "validate-bundle":
        payload = _read_limited(args.bundle, field="bundle", limit=DEFAULT_LIMITS["bundle_bytes"])
        return validate_bundle(strict_json_loads(payload, max_bytes=DEFAULT_LIMITS["bundle_bytes"]))
    if args.command == "audit-runtime":
        package_root = Path(args.package_root).resolve() if args.package_root else Path(__file__).resolve().parent
        return audit_runtime_source(package_root)
    if args.command == "validate-dataset":
        payload = _read_limited(args.dataset, field="PIT dataset", limit=MAX_DATASET_BYTES)
        return validate_pit_dataset(payload)
    if args.command == "train-direction":
        dataset = _read_limited(args.dataset, field="PIT dataset", limit=MAX_DATASET_BYTES)
        config = _read_limited(args.config, field="training config", limit=128_000)
        run = train_direction_pipeline(dataset, config)
        return {
            "schema": CLI_SCHEMA,
            "status": run["status"],
            "run_sha256": run["run_sha256"],
            "dataset_sha256": run["dataset_sha256"],
            "direction_artifact_sha256": run["direction_artifact"]["artifact_sha256"],
            "calibration_artifact_sha256": run["calibration_artifact"]["artifact_sha256"],
            "holdout_records_sha256": run["holdout_records_sha256"],
            "holdout_record_count": len(run["holdout_records"]),
            "automatic_promotion_permitted": run["automatic_promotion_permitted"],
            "outcome_claim": run["outcome_claim"],
            "agent_invocations_total": 0,
            "llm_requests_total": 0,
            "llm_input_tokens_total": 0,
            "llm_output_tokens_total": 0,
            "network_requests_total": 0,
        }
    if args.command == "host-status":
        bundle = _read_limited(args.bundle, field="bundle", limit=DEFAULT_LIMITS["bundle_bytes"]) if args.bundle else None
        outcome = _read_limited(args.outcome_report, field="outcome report", limit=2_000_000) if args.outcome_report else None
        promotion = _read_limited(args.promotion_decision, field="promotion decision", limit=2_000_000) if args.promotion_decision else None
        return build_host_status_payload(as_of=args.as_of, bundle=bundle, outcome_report=outcome, promotion_decision=promotion)
    request = _read_limited(args.request, field="request", limit=DEFAULT_LIMITS["request_bytes"])
    bundle = _read_limited(args.bundle, field="bundle", limit=DEFAULT_LIMITS["bundle_bytes"])
    trust = _read_limited(args.trust_context, field="trust context", limit=DEFAULT_LIMITS["trust_bytes"]) if args.trust_context else None
    return evaluate(request, bundle, trust)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        result = _dispatch(parser.parse_args(argv))
    except EFSError as error:
        result = _error_result(error)
    except Exception:
        result = _error_result(EFSError("INTERNAL_ERROR", "CLI deterministic dispatch failed"))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result.get("status") not in {"ABSTAIN", "ERROR", "UNHEALTHY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

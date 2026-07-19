#!/usr/bin/env python3
"""Record a non-secret Owner attestation for the Stage 0 credential incident.

This command is Owner-action plumbing, not a credential operation. It never
accepts a credential, URL, account identifier or free-text note. A receipt only
authorizes the separate Stage 0 Review Resume; it never grants G0, upload or
Stage 1 authorization.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


INCIDENT_ID = "INC-X2N-S00-P05-001"
RECEIPT_RELATIVE = Path("runtime/owner_recovery_attestation.local.json")
OWNER_CONFIRMATION = "I_CONFIRM_INC_X2N_S00_P05_001_RECOVERY_IS_COMPLETE"
ACTION_STATES = {
    "rotated_and_revoked_old_material": "revoked",
    "reauthenticated_and_revoked_old_material": "revoked",
    "confirmed_old_material_expired": "expired",
}


class RecoveryRecordError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecoveryRecordError(message)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _safe_error(exc: BaseException) -> str:
    return "private filesystem operation failed" if isinstance(exc, OSError) else str(exc)


def resolve_private_root(value: Optional[str] = None) -> Path:
    raw_value = value if value is not None else os.environ.get("X2N_DATA_ROOT")
    _require(bool(raw_value), "X2N_DATA_ROOT is required")
    raw_root = Path(str(raw_value)).expanduser()
    _require(raw_root.exists() and raw_root.is_dir() and not raw_root.is_symlink(), "private root is missing, invalid or symlinked")
    root = raw_root.resolve()
    _require(root.name == "xhs-douyin-2notion", "private root basename mismatch")
    _require(stat.S_IMODE(root.stat().st_mode) == 0o700, "private root must be 0700")

    marker_path = root / ".x2n-root.json"
    _require(marker_path.is_file() and not marker_path.is_symlink(), "private root marker missing or symlinked")
    _require(stat.S_IMODE(marker_path.stat().st_mode) == 0o600, "private root marker must be 0600")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    _require(isinstance(marker, dict), "private root marker must be a JSON object")
    _require(marker.get("project") == "xhs-douyin-2notion", "private root marker project mismatch")
    _require(marker.get("root_ref") == "X2N_DATA_ROOT", "private root marker reference mismatch")
    _require(Path(str(marker.get("resolved_root", ""))).resolve() == root, "private root marker resolution mismatch")

    runtime = root / "runtime"
    _require(runtime.is_dir() and not runtime.is_symlink(), "private runtime directory missing or symlinked")
    _require(stat.S_IMODE(runtime.stat().st_mode) == 0o700, "private runtime directory must be 0700")
    return root


def build_receipt(action: str, owner_confirmation: str, now: Optional[datetime] = None) -> dict[str, Any]:
    _require(owner_confirmation == OWNER_CONFIRMATION, "exact Owner confirmation is required")
    _require(action in ACTION_STATES, "unsupported recovery action")
    timestamp = (now or _utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    rendered_time = timestamp.isoformat().replace("+00:00", "Z")
    receipt_stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema_version": "1.0",
        "receipt_id": f"REC-X2N-S00-P05-001-{receipt_stamp}",
        "project": "x2n",
        "incident_id": INCIDENT_ID,
        "subject": "github_authentication_material",
        "attestation_source": "direct_owner_statement",
        "owner_attested": True,
        "recovery_action": action,
        "old_material_state": ACTION_STATES[action],
        "attested_at": rendered_time,
        "credential_value_included": False,
        "remote_url_included": False,
        "account_identifier_included": False,
        "free_text_included": False,
        "resume_authorization": "stage_0_review_resume_only",
        "g0_pass_granted": False,
        "stage_1_authorized": False,
        "remote_upload_authorized": False,
    }


def write_receipt(root: Path, receipt: dict[str, Any]) -> Path:
    destination = root / RECEIPT_RELATIVE
    _require(destination.parent.resolve() == (root / "runtime").resolve(), "receipt path escaped private runtime")
    _require(not destination.exists() and not destination.is_symlink(), "recovery receipt already exists; refusing to overwrite")
    payload = (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _require(len(payload) <= 4096, "recovery receipt exceeds size limit")

    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    descriptor: Optional[int] = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=tuple(ACTION_STATES))
    parser.add_argument("--owner-confirmation", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = resolve_private_root()
        receipt = build_receipt(args.action, args.owner_confirmation)
        write_receipt(root, receipt)
        print(json.dumps({
            "status": "RECORDED",
            "incident_id": INCIDENT_ID,
            "receipt_ref": RECEIPT_RELATIVE.as_posix(),
            "recovery_action": args.action,
            "contains_secret_values": False,
            "authorizes": "STAGE_0_REVIEW_RESUME_ONLY",
            "g0_status": "BLOCKED_PENDING_REVIEW_RESUME",
            "stage_1_authorized": False,
            "remote_upload_authorized": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RecoveryRecordError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error": _safe_error(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

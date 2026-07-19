#!/usr/bin/env python3
"""Fail-closed preflight for the Stage 0 Owner recovery attestation.

A valid receipt authorizes only a separate Stage 0 Review Resume. This verifier
never mutates G0 state and never authorizes Stage 1 or remote upload.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = PROJECT_ROOT / "machine/schemas/owner_recovery_attestation.schema.json"
INCIDENT = PROJECT_ROOT / "machine/evidence/stage_0/phase_0_5/INC-X2N-S00-P05-001.json"
RECEIPT_RELATIVE = Path("runtime/owner_recovery_attestation.local.json")
INCIDENT_ID = "INC-X2N-S00-P05-001"
ACTION_STATES = {
    "rotated_and_revoked_old_material": "revoked",
    "reauthenticated_and_revoked_old_material": "revoked",
    "confirmed_old_material_expired": "expired",
    "retained_shared_external_material_with_x2n_zero_contact": "retained_owner_directed",
}


class VerificationError(RuntimeError):
    pass


class OwnerActionPending(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _safe_error(exc: BaseException) -> str:
    return "private filesystem operation failed" if isinstance(exc, OSError) else str(exc)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _parse_utc(value: str) -> datetime:
    _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is not None, "attested_at must be second-precision UTC")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None, "attested_at timezone missing")
    return parsed.astimezone(timezone.utc)


def _assert_no_secret_shapes(rendered: str) -> None:
    patterns = (
        re.escape("github" + "_pat_") + r"[A-Za-z0-9]",
        r"gh[pousr]_[A-Za-z0-9]",
        r"https?://[^\s/:@]+:[^\s/@]+@",
        r"(?i)authorization\s*[:=]",
        r"(?i)bearer\s+[A-Za-z0-9._~-]+",
        r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        re.escape("/" + "Users/"),
    )
    _require(not any(re.search(pattern, rendered) for pattern in patterns), "credential, authenticated URL, key material or local path found in recovery receipt")


def validate_receipt_payload(
    payload: dict[str, Any],
    rendered: Optional[str] = None,
    now: Optional[datetime] = None,
    incident_at: Optional[datetime] = None,
) -> Check:
    schema = _load_json(SCHEMA)
    required = set(schema.get("required", []))
    allowed = set(schema.get("properties", {}))
    _require(set(payload) == required == allowed, "recovery receipt fields differ from the closed schema")
    _require(payload.get("schema_version") == "1.0" and payload.get("project") == "x2n", "recovery receipt identity mismatch")
    _require(payload.get("incident_id") == INCIDENT_ID, "recovery receipt incident mismatch")
    _require(payload.get("subject") == "github_authentication_material", "recovery receipt subject mismatch")
    _require(payload.get("attestation_source") == "direct_owner_statement" and payload.get("owner_attested") is True, "direct Owner attestation missing")
    action = payload.get("recovery_action")
    _require(action in ACTION_STATES, "unsupported recovery action")
    _require(payload.get("old_material_state") == ACTION_STATES[action], "recovery action and old-material state disagree")

    attested_at = _parse_utc(str(payload.get("attested_at", "")))
    incident_time = incident_at
    if incident_time is None:
        incident_time = _parse_utc(str(_load_json(INCIDENT).get("generated_at", "")))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _require(attested_at >= incident_time, "Owner attestation predates the incident")
    _require(attested_at <= current + timedelta(minutes=5), "Owner attestation is unreasonably future-dated")
    expected_id = f"REC-X2N-S00-P05-001-{attested_at.strftime('%Y%m%dT%H%M%SZ')}"
    _require(payload.get("receipt_id") == expected_id, "receipt_id does not match attested_at")

    _require(payload.get("credential_value_included") is False, "credential value inclusion must be false")
    _require(payload.get("remote_url_included") is False, "remote URL inclusion must be false")
    _require(payload.get("account_identifier_included") is False, "account identifier inclusion must be false")
    _require(payload.get("free_text_included") is False, "free text inclusion must be false")
    _require(payload.get("resume_authorization") == "stage_0_review_resume_only", "receipt grants an invalid authorization scope")
    _require(payload.get("g0_pass_granted") is False, "receipt attempted to grant G0")
    _require(payload.get("stage_1_authorized") is False, "receipt attempted to authorize Stage 1")
    _require(payload.get("remote_upload_authorized") is False, "receipt attempted to authorize upload")

    raw = rendered if rendered is not None else json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require(len(raw.encode("utf-8")) <= 4096, "recovery receipt exceeds size limit")
    _assert_no_secret_shapes(raw)
    return Check(
        "owner_recovery_attestation",
        "PASS",
        {
            "incident_id": INCIDENT_ID,
            "recovery_action": action,
            "old_material_state": ACTION_STATES[action],
            "secret_values": 0,
            "authorization_scope": "STAGE_0_REVIEW_RESUME_ONLY",
            "g0_pass_granted": False,
            "stage_1_authorized": False,
            "remote_upload_authorized": False,
        },
    )


def resolve_private_root(value: Optional[str] = None) -> Path:
    raw_value = value if value is not None else os.environ.get("X2N_DATA_ROOT")
    if not raw_value:
        raise OwnerActionPending("X2N_DATA_ROOT is required to inspect the private receipt")
    raw_root = Path(str(raw_value)).expanduser()
    _require(raw_root.is_dir() and not raw_root.is_symlink(), "private root is missing, invalid or symlinked")
    root = raw_root.resolve()
    _require(root.name == "xhs-douyin-2notion", "private root basename mismatch")
    _require(stat.S_IMODE(root.stat().st_mode) == 0o700, "private root must be 0700")
    marker_path = root / ".x2n-root.json"
    _require(marker_path.is_file() and not marker_path.is_symlink(), "private root marker missing or symlinked")
    _require(stat.S_IMODE(marker_path.stat().st_mode) == 0o600, "private root marker must be 0600")
    marker = _load_json(marker_path)
    _require(marker.get("project") == "xhs-douyin-2notion" and marker.get("root_ref") == "X2N_DATA_ROOT", "private root marker identity mismatch")
    _require(Path(str(marker.get("resolved_root", ""))).resolve() == root, "private root marker resolution mismatch")
    return root


def validate_recovery_receipt(root: Path, now: Optional[datetime] = None) -> Check:
    receipt = root / RECEIPT_RELATIVE
    if not receipt.exists():
        raise OwnerActionPending("Owner recovery attestation is absent")
    _require(receipt.is_file() and not receipt.is_symlink(), "recovery receipt is invalid or symlinked")
    _require(receipt.parent.resolve() == (root / "runtime").resolve(), "recovery receipt escaped private runtime")
    _require(stat.S_IMODE(receipt.stat().st_mode) == 0o600, "recovery receipt must be 0600")
    rendered = receipt.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    _require(isinstance(payload, dict), "recovery receipt must be a JSON object")
    return validate_receipt_payload(payload, rendered=rendered, now=now)


def main() -> int:
    try:
        root = resolve_private_root()
        check = validate_recovery_receipt(root)
        print(json.dumps({
            "status": "PASS",
            "check": check.__dict__,
            "next_run": "STG.X2N.0.REVIEW.RESUME",
            "g0_status": "BLOCKED_PENDING_REVIEW_RESUME",
            "stage_1_authorized": False,
            "remote_upload": "FORBIDDEN_UNTIL_G0_PASS",
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except OwnerActionPending as exc:
        print(json.dumps({
            "status": "BLOCKED_OWNER_ACTION",
            "reason": str(exc),
            "g0_status": "BLOCKED_OWNER_ACTION",
            "stage_1_authorized": False,
            "remote_upload": "FORBIDDEN_UNTIL_G0_PASS",
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, ValueError, json.JSONDecodeError, VerificationError) as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED",
            "error": _safe_error(exc),
            "g0_status": "BLOCKED_OWNER_ACTION",
            "stage_1_authorized": False,
            "remote_upload": "FORBIDDEN_UNTIL_G0_PASS",
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

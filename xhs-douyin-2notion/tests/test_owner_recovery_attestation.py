from __future__ import annotations

import copy
import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RECORD = _load("record_owner_recovery", "record_owner_recovery.py")
VERIFY = _load("verify_owner_recovery_attestation", "verify_owner_recovery_attestation.py")
FIXED_NOW = datetime(2026, 7, 20, 0, 0, 0, tzinfo=timezone.utc)
INCIDENT_AT = datetime(2026, 7, 19, 20, 55, 14, tzinfo=timezone.utc)


class OwnerRecoveryAttestationTests(unittest.TestCase):
    def _private_root(self, parent: Path) -> Path:
        root = parent / "xhs-douyin-2notion"
        runtime = root / "runtime"
        runtime.mkdir(parents=True)
        root.chmod(0o700)
        runtime.chmod(0o700)
        marker = root / ".x2n-root.json"
        marker.write_text(json.dumps({
            "project": "xhs-douyin-2notion",
            "root_ref": "X2N_DATA_ROOT",
            "resolved_root": str(root.resolve()),
        }), encoding="utf-8")
        marker.chmod(0o600)
        return root

    def test_synthetic_fixture_passes_closed_contract(self) -> None:
        fixture = json.loads((PROJECT_ROOT / "machine/fixtures/owner_recovery_attestation.example.json").read_text(encoding="utf-8"))
        check = VERIFY.validate_receipt_payload(fixture, now=FIXED_NOW, incident_at=INCIDENT_AT)
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["authorization_scope"], "STAGE_0_REVIEW_RESUME_ONLY")
        self.assertFalse(check.details["g0_pass_granted"])

    def test_exact_owner_confirmation_is_required(self) -> None:
        with self.assertRaises(RECORD.RecoveryRecordError):
            RECORD.build_receipt("rotated_and_revoked_old_material", "yes", now=FIXED_NOW)

    def test_action_and_old_material_state_cannot_disagree(self) -> None:
        receipt = RECORD.build_receipt(
            "rotated_and_revoked_old_material",
            RECORD.OWNER_CONFIRMATION,
            now=FIXED_NOW,
        )
        receipt["old_material_state"] = "expired"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.validate_receipt_payload(receipt, now=FIXED_NOW, incident_at=INCIDENT_AT)

    def test_owner_retained_external_material_requires_zero_contact_state(self) -> None:
        receipt = RECORD.build_receipt(
            "retained_shared_external_material_with_x2n_zero_contact",
            RECORD.OWNER_CONFIRMATION,
            now=FIXED_NOW,
        )
        check = VERIFY.validate_receipt_payload(receipt, now=FIXED_NOW, incident_at=INCIDENT_AT)
        self.assertEqual(check.details["old_material_state"], "retained_owner_directed")
        self.assertEqual(check.details["authorization_scope"], "STAGE_0_REVIEW_RESUME_ONLY")

    def test_receipt_cannot_grant_g0_stage_1_or_upload(self) -> None:
        receipt = RECORD.build_receipt(
            "confirmed_old_material_expired",
            RECORD.OWNER_CONFIRMATION,
            now=FIXED_NOW,
        )
        for key in ("g0_pass_granted", "stage_1_authorized", "remote_upload_authorized"):
            invalid = copy.deepcopy(receipt)
            invalid[key] = True
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_receipt_payload(invalid, now=FIXED_NOW, incident_at=INCIDENT_AT)

    def test_sensitive_shape_is_rejected_without_a_real_value(self) -> None:
        shaped = "github" + "_pat_" + "SYNTHETIC_NOT_A_SECRET"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._assert_no_secret_shapes(shaped)

    def test_missing_receipt_remains_owner_action_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._private_root(Path(temporary))
            with self.assertRaises(VERIFY.OwnerActionPending):
                VERIFY.validate_recovery_receipt(root, now=FIXED_NOW)

    def test_generator_writes_0600_valid_receipt_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._private_root(Path(temporary))
            receipt = RECORD.build_receipt(
                "reauthenticated_and_revoked_old_material",
                RECORD.OWNER_CONFIRMATION,
                now=FIXED_NOW,
            )
            destination = RECORD.write_receipt(root, receipt)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            check = VERIFY.validate_recovery_receipt(root, now=FIXED_NOW)
            self.assertEqual(check.status, "PASS")
            with self.assertRaises(RECORD.RecoveryRecordError):
                RECORD.write_receipt(root, receipt)

    def test_filesystem_errors_are_redacted(self) -> None:
        failure = OSError(1, "denied", "/private/example")
        self.assertEqual(RECORD._safe_error(failure), "private filesystem operation failed")
        self.assertEqual(VERIFY._safe_error(failure), "private filesystem operation failed")


if __name__ == "__main__":
    unittest.main()

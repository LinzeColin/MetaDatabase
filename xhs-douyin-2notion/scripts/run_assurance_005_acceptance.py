#!/usr/bin/env python3
"""Read-only final verifier for the direct Owner MVP release.

This script never arms a release, starts a platform action, opens Chrome, or
creates an account/browser/profile artifact.  It verifies an already active
Owner Runtime and emits only a compact public-safe receipt.  Writing that
receipt into the public repository requires an explicit literal confirmation.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from scripts.ci.ci_baseline import BaselineError, build_artifact  # noqa: E402
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.final_acceptance_bundle import (  # noqa: E402
    FinalAcceptanceBundleError,
    build_final_acceptance_bundle,
)
from x2n_companion.mvp_deployment import MvpDeploymentManager  # noqa: E402
from x2n_companion.mvp_release import MvpReleaseController, RELEASE_VERSION  # noqa: E402
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError  # noqa: E402


TASK_ID = "TSK.x2n.assurance.005"
PHASE = "PH.X2N.6.5"
STATUS = "PASS_OWNER_MVP_DIRECT_RELEASE_CORE"
WRITE_CONFIRMATION = "WRITE_X2N_ASSURANCE_005_PUBLIC_RECEIPT"
PUBLIC_RECEIPT = PROJECT_ROOT / "evidence/release/TSK.x2n.assurance.005.json"
PUBLIC_BUNDLE = PROJECT_ROOT / "evidence/release/FINAL_ACCEPTANCE_BUNDLE"
_PLATFORM_CDN = re.compile(
    "|".join(
        re.escape("".join(parts))
        for parts in (
            ("xhs", "cdn"),
            ("douyin", "vod"),
            ("byte", "img"),
            ("pstat", "p"),
            ("bili", "video"),
            ("hd", "slb"),
            ("ks", "cdn"),
            ("yx", "imgs"),
            ("sina", "img"),
            ("tb", "cdn"),
            ("ali", "cdn"),
        )
    ),
    re.I,
)


class Assurance005Error(RuntimeError):
    """A direct-release condition is missing or cannot be safely published."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance005Error(message)


def _safe_payload(payload: Any) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "/" + "home/" not in rendered, "private path reached receipt")
    _require("github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "credential reached receipt")
    _require(_PLATFORM_CDN.search(rendered) is None, "platform CDN reached receipt")


def _release_source_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    commit = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise Assurance005Error("local release source identity is unavailable")
    return commit


def _scan_public_source_artifact() -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory(prefix="x2n-a005-artifact-") as temporary:
            scan = build_artifact(Path(temporary) / "x2n-source-candidate.zip")
    except (BaselineError, OSError, ValueError) as error:
        raise Assurance005Error("release source artifact scan failed") from error
    _require(
        scan.get("status") == "PASS"
        and scan.get("allowlist_findings") == 0
        and scan.get("runtime_data_files") == 0
        and isinstance(scan.get("artifact_sha256"), str)
        and isinstance(scan.get("member_count"), int),
        "release source artifact scan drifted",
    )
    return {
        "allowlist_findings": 0,
        "artifact_sha256": scan["artifact_sha256"],
        "member_count": scan["member_count"],
        "runtime_data_files": 0,
        "status": "PASS",
    }


def build_receipt() -> dict[str, Any]:
    """Read all direct-MVP proofs without changing Runtime or platform state."""

    paths = RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=False)
    store = CanonicalStore(paths)
    controller = MvpReleaseController.load(paths)
    _require(controller is not None, "Owner MVP release state is unavailable")
    manager = MvpDeploymentManager(paths)
    MvpDeploymentManager.assert_release_source_tagged()
    artifact = manager.verify_current_artifact()
    deployment = controller.state["deployment"]
    browser = deployment["browser"]
    _require(isinstance(browser, str), "deployed browser identity is unavailable")
    _require(deployment["artifact_sha256"] == artifact["artifact_sha256"], "runtime artifact identity diverged")
    native_host = manager.verify_native_host_artifact(browser=browser, artifact_sha256=artifact["artifact_sha256"])
    go_live = controller.verify_go_live(store)
    source_scan = _scan_public_source_artifact()
    _require(
        go_live["owner_mvp_baseline_relations"] == 80
        and go_live["private_manifest_scope_count"] == 4
        and go_live["private_manifest_item_count"] == 80
        and go_live["external_disabled_scope_count"] == 4
        and go_live["rollback_rehearsed"] is True
        and go_live["sidepanel"]["browser_sidepanel_handshake"] == "PASS"
        and native_host["native_host_release_bound"] is True,
        "direct Owner MVP release proof is incomplete",
    )
    external_gates = go_live["external_gates"]
    knowledge_assets = go_live["knowledge_assets"]
    _require(
        isinstance(external_gates, list)
        and len(external_gates) == 4
        and all(
            isinstance(item, dict)
            and set(item)
            == {
                "feature_flag",
                "live_support_claim",
                "platform_calls",
                "reason_code",
                "scope_id",
                "status",
            }
            and item["feature_flag"] == "disabled"
            and item["live_support_claim"] is False
            and item["platform_calls"] == 0
            and item["status"] == "PASS_DISABLED_EXTERNAL_GATE"
            for item in external_gates
        ),
        "external-gate settlement proof is incomplete",
    )
    _require(
        isinstance(knowledge_assets, dict)
        and set(knowledge_assets)
        == {
            "markdown_content_count",
            "markdown_library_sha256",
            "markdown_renderer_version",
            "notion_mode",
            "notion_platform_calls",
            "private_durability_manifest_sha256",
        }
        and type(knowledge_assets["markdown_content_count"]) is int
        and knowledge_assets["markdown_content_count"] >= 1
        and re.fullmatch(r"[0-9a-f]{64}", str(knowledge_assets["markdown_library_sha256"])) is not None
        and isinstance(knowledge_assets["markdown_renderer_version"], str)
        and knowledge_assets["notion_mode"] == "DISABLED_OWNER_INPUT"
        and type(knowledge_assets["notion_platform_calls"]) is int
        and knowledge_assets["notion_platform_calls"] == 0
        and re.fullmatch(r"[0-9a-f]{64}", str(knowledge_assets["private_durability_manifest_sha256"])) is not None,
        "knowledge-asset and durability proof is incomplete",
    )
    receipt_without_bundle_hash = {
        "artifact": {
            "artifact_sha256": artifact["artifact_sha256"],
            "runtime_data_files": 0,
            "source_only_artifact": True,
        },
        "artifact_scan": source_scan,
        "boundaries": {
            "external_disabled_scope_count": 4,
            "model_mode": go_live["model_mode"],
            "private_manifest_item_count": 80,
            "private_manifest_scope_count": 4,
        },
        "external_gates": external_gates,
        "knowledge_assets": knowledge_assets,
        "go_live": {
            "baseline_hash": go_live["baseline_hash"],
            "owner_mvp_baseline_relations": 80,
            "rollback_rehearsed": True,
            "sidepanel_native_handshake": "PASS",
        },
        "native_host": {
            "native_host_release_bound": True,
            "release_artifact_sha256": native_host["release_artifact_sha256"],
        },
        "phase": PHASE,
        "release_source": {"commit": _release_source_commit(), "tag": RELEASE_VERSION},
        "release_version": RELEASE_VERSION,
        "schema_version": "1.0",
        "status": STATUS,
        "task_id": TASK_ID,
    }
    _bundle, bundle_sha256 = build_final_acceptance_bundle(receipt_without_bundle_hash)
    receipt = {**receipt_without_bundle_hash, "final_acceptance_bundle_sha256": bundle_sha256}
    _safe_payload(receipt)
    return receipt


def _write_public_receipt(receipt: dict[str, Any]) -> None:
    _safe_payload(receipt)
    try:
        bundle, bundle_sha256 = build_final_acceptance_bundle(receipt)
    except FinalAcceptanceBundleError as error:
        raise Assurance005Error("final acceptance bundle cannot be generated safely") from error
    _require(
        bundle_sha256 == receipt.get("final_acceptance_bundle_sha256"),
        "final acceptance bundle root identity drifted",
    )
    for document in bundle.values():
        _safe_payload(document)
    if PUBLIC_RECEIPT.exists() or PUBLIC_RECEIPT.is_symlink() or PUBLIC_BUNDLE.exists() or PUBLIC_BUNDLE.is_symlink():
        raise Assurance005Error("public go-live evidence already exists and is immutable")
    parent = PUBLIC_RECEIPT.parent
    if parent.exists():
        if parent.is_symlink() or not parent.is_dir():
            raise Assurance005Error("public receipt destination is unsafe")
    else:
        parent.mkdir(parents=True, exist_ok=False)
    temporary = PUBLIC_RECEIPT.with_name(f".{PUBLIC_RECEIPT.name}.tmp-{uuid.uuid4().hex}")
    temporary_bundle = PUBLIC_BUNDLE.with_name(f".{PUBLIC_BUNDLE.name}.tmp-{uuid.uuid4().hex}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    bundle_published = False
    receipt_published = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_bundle.mkdir(mode=0o700)
        for name, document in bundle.items():
            destination = temporary_bundle / name
            document_descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(document_descriptor, "w", encoding="utf-8") as handle:
                handle.write(document)
                handle.flush()
                os.fsync(handle.fileno())
            destination.chmod(0o644)
        temporary_bundle.chmod(0o755)
        os.replace(temporary_bundle, PUBLIC_BUNDLE)
        bundle_published = True
        os.replace(temporary, PUBLIC_RECEIPT)
        receipt_published = True
        PUBLIC_RECEIPT.chmod(0o644)
    except BaseException:
        if bundle_published and not receipt_published:
            if PUBLIC_BUNDLE.is_symlink() or not PUBLIC_BUNDLE.is_dir():
                raise Assurance005Error("published final acceptance bundle became unsafe") from None
            shutil.rmtree(PUBLIC_BUNDLE)
        raise
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
        if temporary_bundle.exists() or temporary_bundle.is_symlink():
            if temporary_bundle.is_symlink() or not temporary_bundle.is_dir():
                raise Assurance005Error("temporary final acceptance bundle became unsafe")
            shutil.rmtree(temporary_bundle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify an already running x2n direct Owner MVP release")
    parser.add_argument("--write-public-receipt", action="store_true")
    parser.add_argument("--confirm")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.write_public_receipt and args.confirm != WRITE_CONFIRMATION:
            raise Assurance005Error("public receipt write confirmation is missing")
        receipt = build_receipt()
        if args.write_public_receipt:
            _write_public_receipt(receipt)
    except X2NRuntimeError as error:
        failure = {
            "code": error.code.value,
            "paths_emitted": False,
            "safe_message": error.safe_message,
            "status": "FAIL_CLOSED",
            "task_id": TASK_ID,
        }
        _safe_payload(failure)
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    except (Assurance005Error, FinalAcceptanceBundleError, OSError, ValueError):
        failure = {
            "code": "X2N_ASSURANCE_005_INCOMPLETE",
            "paths_emitted": False,
            "safe_message": "Direct Owner MVP go-live verification is incomplete",
            "status": "FAIL_CLOSED",
            "task_id": TASK_ID,
        }
        _safe_payload(failure)
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

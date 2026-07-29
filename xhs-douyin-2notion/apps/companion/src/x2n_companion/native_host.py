"""Strict Chrome Native Messaging gateway for the Foundation004 skeleton."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from x2n_contracts import (
    CapabilityManifest,
    ContractViolation,
    DuplicateDisposition,
    ErrorCode,
    NativeHostPolicy,
    NativeMessageResponse,
    canonical_json_sha256,
    parse_native_message,
)
from x2n_contracts.errors import ERROR_SPECS
from x2n_contracts.models import CapabilityFeatureFlag, CapabilityTerminal, NativeAction, SyncScopeId

from .adapter_dispatch import AdapterDispatcher, CapabilityRegistry
from .canonical_store import CURRENT_PAGE_RUN_KIND, CanonicalStore, SkeletonJob
from .mvp_release import (
    MvpActivationExecutor,
    MvpReleaseController,
    OwnerMvpManifestEnrollment,
    expected_mvp_receipt_hash,
)
from .orchestrator import CurrentPageOrchestrator
from .runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
HOST_NAME = "com.linzecolin.x2n"
DEVELOPMENT_EXTENSION_ID = "chheapilbdfnpajmlkijppmblnlheeac"
DEVELOPMENT_EXTENSION_ORIGIN = f"chrome-extension://{DEVELOPMENT_EXTENSION_ID}/"
MAX_MESSAGE_BYTES = 1_048_576
ZERO_REQUEST_ID = "00000000-0000-0000-0000-000000000000"

POLICY = NativeHostPolicy.model_validate(
    {
        "schema_version": "1.0",
        "policy_id": "NATIVE_HOST.X2N.001",
        "allowed_origins": (DEVELOPMENT_EXTENSION_ORIGIN,),
        "allowed_actions": tuple(NativeAction),
        "max_message_bytes": MAX_MESSAGE_BYTES,
        "request_id_window_seconds": 86_400,
        "duplicate_policy": "return_existing_job_only",
        "unknown_fields": "reject",
        "unknown_versions": "reject",
        "arbitrary_shell": "reject",
        "arbitrary_local_path": "reject",
        "arbitrary_url": "reject",
    }
)


def _request_id(raw: bytes) -> str:
    try:
        value = json.loads(raw.decode("utf-8"))
        candidate = value.get("request_id") if isinstance(value, dict) else None
        return str(uuid.UUID(candidate)) if isinstance(candidate, str) else ZERO_REQUEST_ID
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, AttributeError):
        return ZERO_REQUEST_ID


def _legacy_empty_capabilities_request(raw: bytes) -> bool:
    """Keep the pre-Task010 empty GET_CAPABILITIES vector read-compatible."""

    try:
        value = json.loads(raw.decode("utf-8"))
        return isinstance(value, dict) and value.get("action") == "get_capabilities" and value.get("payload") == {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False


def _error_response(
    code: ErrorCode,
    *,
    request_id: str,
    safe_message: str | None = None,
    job_id: str | None = None,
) -> NativeMessageResponse:
    spec = ERROR_SPECS[code]
    error = {
        "schema_version": "1.0",
        "code": code.value,
        "class": spec.error_class.value,
        "retryable": spec.retryable,
        "safe_message": safe_message or spec.default_safe_message,
        "internal_ref": f"evt_{uuid.uuid4().hex}",
        "data_effect": spec.data_effect.value,
        "next_action": spec.next_action.value,
    }
    return NativeMessageResponse.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "request_id": request_id,
                "accepted": False,
                "job_id": job_id,
                "status": "rejected",
                "error": error,
                "capabilities": None,
            },
            ensure_ascii=False,
        )
    )


def _accepted(
    *,
    request_id: str,
    status: str,
    job_id: str | None = None,
    capabilities: CapabilityManifest | None = None,
) -> NativeMessageResponse:
    return NativeMessageResponse.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "request_id": request_id,
                "accepted": True,
                "job_id": job_id,
                "status": status,
                "error": None,
                "capabilities": capabilities.model_dump(mode="json") if capabilities is not None else None,
            },
            ensure_ascii=False,
        )
    )


def _native_status(job: SkeletonJob) -> str:
    if job.state == "pending":
        return "queued"
    if job.state in {"running", "recovery"}:
        return "running"
    if job.state == "succeeded":
        return "completed"
    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Native Job is not executable in this skeleton")


def _store() -> CanonicalStore:
    paths = RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=False)
    return CanonicalStore(paths)


def _capability_snapshot(store: CanonicalStore, registry: CapabilityRegistry) -> CapabilityManifest:
    """Refresh the SQLite-only runtime authority or fail closed on any technical veto."""

    technical_scopes = registry.technical_scope_ids()
    if technical_scopes:
        store.invalidate_capability_scopes(technical_scopes)
        raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability technical veto is active")
    try:
        manifest = registry.evaluate()
    except X2NRuntimeError as error:
        if error.code is ErrorCode.CAPABILITY_TECHNICAL_BLOCKED:
            # A corrupted/missing adapter binding means no previously ready row
            # is safe to serve, even if its narrow source cannot be identified.
            store.invalidate_capability_scopes(tuple(SyncScopeId))
        raise
    return store.persist_capability_snapshot(manifest)


def _failed_job_response(*, request_id: str, job: SkeletonJob) -> NativeMessageResponse:
    if job.failure_code is not ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE or not job.fallback_eligible:
        return _error_response(ErrorCode.DATA_INTEGRITY_FAILED, request_id=request_id, job_id=job.job_id)
    return _error_response(
        ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE,
        request_id=request_id,
        job_id=job.job_id,
    )


def _runtime_release_controller(store: CanonicalStore) -> MvpReleaseController | None:
    """Load Task005 private activation state only when it has been armed.

    A missing input/state pair keeps the established CI-synthetic route
    available for development and tests.  A partial or malformed private state
    raises through the caller and therefore fails closed.
    """

    return MvpReleaseController.load(store.paths, require_state=False)


def dispatch_wire(
    raw: bytes,
    *,
    origin: str,
    store: CanonicalStore | None = None,
    capability_registry: CapabilityRegistry | None = None,
    adapter_dispatcher: AdapterDispatcher | None = None,
) -> NativeMessageResponse:
    """Validate and dispatch one message without retaining caller payload."""

    request_id = _request_id(raw)
    try:
        request = parse_native_message(raw, origin=origin, policy=POLICY)
        request_id = str(request.request_id)
        if request.action is NativeAction.GET_CAPABILITIES and _legacy_empty_capabilities_request(raw):
            return _accepted(request_id=request_id, status="completed")
        active_store = store or _store()
        release_controller = None if capability_registry is not None else _runtime_release_controller(active_store)
        active_registry = capability_registry or (
            release_controller.capability_registry() if release_controller is not None else CapabilityRegistry()
        )
        if request.action is NativeAction.GET_CAPABILITIES:
            manifest = _capability_snapshot(active_store, active_registry)
            return _accepted(request_id=request_id, status="completed", capabilities=manifest)

        if request.action is NativeAction.HEALTH:
            health = active_store.health()
            if health.get("status") != "healthy":
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical Store health check failed")
            if request.payload.mvp_browser_handshake is True and release_controller is not None:
                if not release_controller.record_browser_handshake(
                    artifact_sha256=str(request.payload.mvp_release_artifact_sha256)
                ):
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP Side Panel handshake is not eligible")
            return _accepted(request_id=request_id, status="completed")
        if request.action is NativeAction.CAPTURE_CURRENT:
            current_content_hash = None
            if request.payload.owner_mvp_scope is not None:
                if release_controller is None:
                    OwnerMvpManifestEnrollment.load_or_create(active_store.paths).record_current_content(
                        payload=request.payload
                    )
                    return _accepted(request_id=request_id, status="completed")
                current_content_hash = release_controller.prepare_current_content_capture(
                    payload=request.payload,
                    request_id=request_id,
                )
            if request.payload.fallback_from_job_id is not None:
                active_store.verify_current_page_fallback(
                    fallback_from_job_id=str(request.payload.fallback_from_job_id),
                    current_request_id=request_id,
                )
            receipt = CurrentPageOrchestrator(active_store).execute(
                request.payload,
                request_id=request_id,
                payload_hash=request.payload_hash,
            )
            if current_content_hash is not None:
                assert release_controller is not None
                release_controller.record_current_content_capture(
                    content_id_hash=current_content_hash,
                    job_id=receipt.job_id,
                    state=receipt.state,
                )
            job = SkeletonJob(
                job_id=receipt.job_id,
                state=receipt.state,
                disposition=receipt.disposition,
                run_kind=CURRENT_PAGE_RUN_KIND,
            )
            return _accepted(request_id=request_id, status=_native_status(job), job_id=job.job_id)
        if request.action is NativeAction.START_SYNC:
            if request.payload.owner_mvp_manifest_enrollment is True:
                OwnerMvpManifestEnrollment.load_or_create(active_store.paths).record_list_batch(payload=request.payload)
                return _accepted(request_id=request_id, status="completed")
            manifest = _capability_snapshot(active_store, active_registry)
            outcome = next(
                (item for item in manifest.outcomes if item.scope_id is request.payload.scope_id),
                None,
            )
            if outcome is None or outcome.terminal is not CapabilityTerminal.READY_FOR_MVP_ACTIVATION:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Requested scope is disabled by its external gate")
            dispatcher = adapter_dispatcher or AdapterDispatcher()
            binding = dispatcher.binding_for(
                request.payload.scope_id,
                platform=request.payload.platform,
                relation=request.payload.relation,
            )
            if outcome.feature_flag is CapabilityFeatureFlag.CI_SYNTHETIC_ONLY:
                expected_receipt_hash = dispatcher.expected_receipt_hash(binding, payload_hash=request.payload_hash)
                execution = "ci_synthetic"
            elif (
                outcome.feature_flag is CapabilityFeatureFlag.MVP_ACTIVATION_CANDIDATE
                and release_controller is not None
            ):
                expected_receipt_hash = expected_mvp_receipt_hash(
                    binding=binding,
                    payload_hash=request.payload_hash,
                    input_sha256=release_controller.release_input.input_sha256,
                )
                execution = "owner_mvp"
            else:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Requested scope has no active execution authority")
            job = active_store.submit_scope_dispatch_job(
                request_id=request_id,
                payload_hash=request.payload_hash,
                binding=binding,
                dispatch_receipt_hash=expected_receipt_hash,
            )
            if job.disposition is DuplicateDisposition.NEW_REQUEST:
                try:
                    if execution == "ci_synthetic":
                        receipt = dispatcher.execute_synthetic(binding, payload_hash=request.payload_hash)
                        if receipt.platform_calls != 0 or receipt.receipt_hash != expected_receipt_hash:
                            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Dispatch receipt is invalid")
                    else:
                        assert release_controller is not None
                        actual_receipt_hash = MvpActivationExecutor(release_controller, active_store).execute(
                            binding=binding,
                            payload=request.payload,
                            job_id=job.job_id,
                            payload_hash=request.payload_hash,
                        )
                        if actual_receipt_hash != expected_receipt_hash:
                            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP dispatch receipt is invalid")
                    job = active_store.complete_scope_dispatch_job(
                        job_id=job.job_id,
                        dispatch_receipt_hash=expected_receipt_hash,
                    )
                except Exception:
                    provenance_hash = canonical_json_sha256(
                        {
                            "dispatch_receipt_hash": expected_receipt_hash,
                            "job_id": job.job_id,
                            "scope_id": binding.scope_id.value,
                        }
                    )
                    job = active_store.fail_scope_dispatch_job(
                        job_id=job.job_id,
                        provenance_hash=provenance_hash,
                        fallback_eligible=True,
                    )
            if job.state == "failed":
                return _failed_job_response(request_id=request_id, job=job)
            return _accepted(request_id=request_id, status=_native_status(job), job_id=job.job_id)
        if request.action is NativeAction.GET_JOB:
            job = active_store.get_skeleton_job(str(request.payload.job_id))
            if job.run_kind == CURRENT_PAGE_RUN_KIND and job.state == "running":
                receipt = CurrentPageOrchestrator(active_store).resume(job.job_id)
                job = SkeletonJob(
                    job_id=receipt.job_id,
                    state=receipt.state,
                    disposition=receipt.disposition,
                    run_kind=CURRENT_PAGE_RUN_KIND,
                )
            if job.state == "failed":
                return _failed_job_response(request_id=request_id, job=job)
            return _accepted(request_id=request_id, status=_native_status(job), job_id=job.job_id)
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Job mutation is not enabled in this skeleton")
    except ContractViolation as error:
        return _error_response(error.code, request_id=request_id, safe_message=str(error))
    except X2NRuntimeError as error:
        return _error_response(error.code, request_id=request_id, safe_message=error.safe_message)
    except Exception:
        return _error_response(ErrorCode.UNKNOWN_FAILURE, request_id=request_id)


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("Native message ended before its declared length")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO) -> bytes | None:
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise EOFError("Native message length header is incomplete")
    size = int.from_bytes(header, byteorder=sys.byteorder, signed=False)
    if size > MAX_MESSAGE_BYTES:
        raise X2NRuntimeError(ErrorCode.NATIVE_MESSAGE_TOO_LARGE, "消息超过允许大小")
    return _read_exact(stream, size)


def write_frame(stream: BinaryIO, response: NativeMessageResponse) -> None:
    payload = response.model_dump_json(by_alias=True).encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise X2NRuntimeError(ErrorCode.NATIVE_MESSAGE_TOO_LARGE, "响应超过允许大小")
    stream.write(len(payload).to_bytes(4, byteorder=sys.byteorder, signed=False))
    stream.write(payload)
    stream.flush()


def run_host(*, origin: str, stdin: BinaryIO, stdout: BinaryIO) -> int:
    # Foundation004 deliberately supports sendNativeMessage rather than a
    # long-lived connectNative port: one process, one request, one response.
    try:
        raw = read_frame(stdin)
    except X2NRuntimeError as error:
        write_frame(stdout, _error_response(error.code, request_id=ZERO_REQUEST_ID, safe_message=error.safe_message))
        return 2
    except EOFError:
        return 2
    if raw is None:
        return 0
    write_frame(stdout, dispatch_wire(raw, origin=origin))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    origin = values[0] if values else ""
    return run_host(origin=origin, stdin=sys.stdin.buffer, stdout=sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())

"""Owner-editable controls and generated owner-readable views."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .stage1_queue import (
    STAGE1_CONTENT_LEDGER_COLUMNS,
    placeholder_content_ledger_rows,
    render_content_ledger_csv,
)


OWNER_CONTROLS_MODEL_ID = "adp-owner-controls-v1"
OWNER_CONTROLS_SCHEMA_VERSION = 1
CLOUDFLARE_SOURCE_CANDIDATE_REGISTRY_PATH = "config/cloudflare_source_candidates_v1_2.json"
STATS_GOV_DIAGNOSIS_RECEIPT_SCHEMA = "adp-v12-stats-gov-diagnosis-receipt-v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
OWNER_CONTROL_DOCS: tuple[str, ...] = (
    "docs/owner/OWNER_CONSOLE.md",
    "docs/owner/SOURCE_CATALOG.md",
    "docs/owner/MODEL_AND_QUEUE.md",
    "docs/owner/CONTENT_LEDGER.csv",
)
CONTENT_LEDGER_COLUMNS: tuple[str, ...] = STAGE1_CONTENT_LEDGER_COLUMNS
SECRET_KEY_PATTERN = re.compile(
    r"(^|[_-])(password|token|secret|private[_-]?key|client[_-]?secret|credential)([_-]|$)",
    re.I,
)
SECRET_VALUE_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,})")


class OwnerControlsError(ValueError):
    """Raised when owner controls cannot be parsed or rendered."""


def project_root_default(cwd: Path | None = None) -> Path:
    base = cwd or Path.cwd()
    nested = base / "arxiv-daily-push"
    return nested if nested.is_dir() else base


def default_controls_path(cwd: Path | None = None) -> Path:
    root = project_root_default(cwd)
    return root / "config" / "owner_controls.yaml"


def load_owner_controls(path: str | Path | None = None) -> dict[str, Any]:
    controls_path = Path(path) if path else default_controls_path()
    if not controls_path.is_file():
        raise OwnerControlsError(f"owner controls file not found: {controls_path}")
    data = _load_yaml(controls_path)
    if not isinstance(data, dict):
        raise OwnerControlsError("owner controls root must be a mapping")
    return data


def _load_optional_cloudflare_candidate_registry(
    root: Path,
) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    registry_path = root / CLOUDFLARE_SOURCE_CANDIDATE_REGISTRY_PATH
    if not registry_path.is_file():
        return None, ()
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OwnerControlsError(f"invalid Cloudflare candidate registry: {registry_path}") from exc
    if not isinstance(data, Mapping):
        raise OwnerControlsError("Cloudflare candidate registry root must be a mapping")
    receipt_paths = _validate_cloudflare_diagnostic_receipts(root, data)
    return data, receipt_paths


def _validate_cloudflare_diagnostic_receipts(
    root: Path,
    registry: Mapping[str, Any],
) -> tuple[str, ...]:
    receipt_paths: list[str] = []
    for diagnostic in _sequence_of_mappings(registry.get("diagnostic_routes")):
        task_id = str(diagnostic.get("task_id") or "")
        receipt_ref = str(diagnostic.get("receipt_path") or "")
        receipt_sha256 = str(diagnostic.get("receipt_sha256") or "")
        if not receipt_ref:
            raise OwnerControlsError(f"Cloudflare diagnostic receipt path missing: {task_id}")
        portable_ref = PurePosixPath(receipt_ref)
        if portable_ref.is_absolute() or ".." in portable_ref.parts:
            raise OwnerControlsError(f"Cloudflare diagnostic receipt path is unsafe: {receipt_ref}")
        if not SHA256_PATTERN.fullmatch(receipt_sha256):
            raise OwnerControlsError(f"Cloudflare diagnostic receipt SHA-256 is invalid: {task_id}")

        receipt_path = root.joinpath(*portable_ref.parts)
        if not receipt_path.is_file():
            raise OwnerControlsError(f"Cloudflare diagnostic receipt not found: {receipt_ref}")
        receipt_bytes = receipt_path.read_bytes()
        actual_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        if actual_sha256 != receipt_sha256:
            raise OwnerControlsError(
                f"Cloudflare diagnostic receipt SHA-256 mismatch: {receipt_ref}"
            )
        try:
            receipt = json.loads(receipt_bytes)
        except json.JSONDecodeError as exc:
            raise OwnerControlsError(f"invalid Cloudflare diagnostic receipt: {receipt_ref}") from exc
        if not isinstance(receipt, Mapping):
            raise OwnerControlsError(f"Cloudflare diagnostic receipt root must be a mapping: {receipt_ref}")

        expected_receipt_fields = {
            "schema_version": STATS_GOV_DIAGNOSIS_RECEIPT_SCHEMA,
            "task_id": task_id,
            "source_id": str(diagnostic.get("source_id") or ""),
            "board_id": str(diagnostic.get("board_id") or ""),
            "state": str(diagnostic.get("state") or ""),
            "decision": str(diagnostic.get("decision") or ""),
        }
        for field, expected in expected_receipt_fields.items():
            if receipt.get(field) != expected:
                raise OwnerControlsError(
                    f"Cloudflare diagnostic receipt {field} mismatch: {receipt_ref}"
                )
        if receipt.get("acceptance_claimed") is not False:
            raise OwnerControlsError(
                f"Cloudflare diagnostic facts receipt must not claim acceptance: {receipt_ref}"
            )

        observations = _sequence_of_mappings(receipt.get("observations"))
        observations_by_id: dict[str, Mapping[str, Any]] = {}
        for observation in observations:
            observation_id = str(observation.get("observation_id") or "")
            if not observation_id or observation_id in observations_by_id:
                raise OwnerControlsError(
                    f"Cloudflare diagnostic receipt has missing or duplicate observation_id: {receipt_ref}"
                )
            if observation.get("read_only") is not True:
                raise OwnerControlsError(
                    f"Cloudflare diagnostic observation must be read-only: {observation_id}"
                )
            verification_status = str(observation.get("verification_status") or "")
            raw_evidence = _mapping(observation.get("raw_evidence"))
            raw_sha256 = raw_evidence.get("sha256")
            if verification_status.startswith("VERIFIED_"):
                if not isinstance(raw_sha256, str) or not SHA256_PATTERN.fullmatch(raw_sha256):
                    raise OwnerControlsError(
                        f"verified Cloudflare diagnostic observation needs raw SHA-256: {observation_id}"
                    )
            elif verification_status == "STALE_UNVERIFIED_RAW_UNAVAILABLE":
                if raw_sha256 is not None:
                    raise OwnerControlsError(
                        f"stale Cloudflare diagnostic observation must not invent raw SHA-256: {observation_id}"
                    )
            else:
                raise OwnerControlsError(
                    f"Cloudflare diagnostic observation has invalid verification_status: {observation_id}"
                )
            observations_by_id[observation_id] = observation

        bindings = (
            (
                "latest_official_observation_id",
                "local_observation_id",
                "local_observed_at",
                "local_classification",
                "local_http_status",
                "local_parsed_count",
            ),
            (
                "latest_edge_observation_id",
                "edge_observation_id",
                "edge_observed_at",
                "edge_classification",
                "edge_http_status",
                "edge_parsed_count",
            ),
        )
        for receipt_id_field, registry_id_field, time_field, class_field, http_field, count_field in bindings:
            observation_id = str(receipt.get(receipt_id_field) or "")
            if observation_id != str(diagnostic.get(registry_id_field) or ""):
                raise OwnerControlsError(
                    f"Cloudflare diagnostic latest observation ID mismatch: {receipt_ref}"
                )
            observation = observations_by_id.get(observation_id)
            if observation is None:
                raise OwnerControlsError(
                    f"Cloudflare diagnostic latest observation missing: {observation_id}"
                )
            comparisons = (
                ("observed_at", diagnostic.get(time_field)),
                ("classification", diagnostic.get(class_field)),
                ("http_status", diagnostic.get(http_field)),
                ("parsed_count", diagnostic.get(count_field)),
            )
            for observation_field, registry_value in comparisons:
                if observation.get(observation_field) != registry_value:
                    raise OwnerControlsError(
                        "Cloudflare diagnostic latest observation mismatch: "
                        f"{observation_id}.{observation_field}"
                    )
            if not str(observation.get("verification_status") or "").startswith("VERIFIED_"):
                raise OwnerControlsError(
                    f"Cloudflare diagnostic latest observation is not verified: {observation_id}"
                )

        runtime_boundary = _mapping(receipt.get("runtime_boundary"))
        forbidden_true = (
            "worker_changed",
            "wrangler_changed",
            "source_enablement_changed",
            "write_allowed",
            "deployment_performed",
            "paid_or_bypass_dependency_added",
        )
        if any(runtime_boundary.get(field) is not False for field in forbidden_true):
            raise OwnerControlsError(
                f"Cloudflare diagnostic receipt violates no-live boundary: {receipt_ref}"
            )
        receipt_paths.append(receipt_ref)
    return tuple(receipt_paths)


def validate_owner_controls(controls: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    required_sections = (
        "schema_version",
        "config_version",
        "project",
        "cost_policy",
        "runtime",
        "intelligence_provider",
        "boards",
        "sources",
        "email",
        "outputs",
        "queue",
        "scoring",
        "source_defaults",
        "iteration",
        "validation",
    )
    for section in required_sections:
        if section not in controls:
            errors.append(f"missing required section: {section}")
    if controls.get("schema_version") != OWNER_CONTROLS_SCHEMA_VERSION:
        errors.append(f"schema_version must be {OWNER_CONTROLS_SCHEMA_VERSION}")
    project = _mapping(controls.get("project"))
    if project.get("production_enabled") is not False:
        errors.append("project.production_enabled must remain false until production acceptance")
    if project.get("production_auto_enable_after_acceptance") is not False:
        # R0-3（V0.3 复审加固）：验收后自动启用已废止；启用只能走显式 owner 授权 artifact（不变量 5）。
        errors.append("project.production_auto_enable_after_acceptance must be false; enablement requires an explicit owner authorization artifact")
    outputs = _mapping(controls.get("outputs"))
    if outputs.get("production_acceptance_claimed") is not False:
        errors.append("outputs.production_acceptance_claimed must be false")
    cost_policy = _mapping(controls.get("cost_policy"))
    for flag in ("paid_data_api_allowed", "paid_cloud_compute_allowed", "paid_openai_api_allowed"):
        if cost_policy.get(flag) is True:
            errors.append(f"cost_policy.{flag} must not be true in Window A")
    intelligence = _mapping(controls.get("intelligence_provider"))
    if intelligence.get("paid_openai_api_allowed") is True:
        errors.append("intelligence_provider.paid_openai_api_allowed must not be true in Window A")
    errors.extend(_secret_hygiene_errors(controls))
    weight_groups = _weight_group_reports(controls)
    for group in weight_groups:
        if group["status"] != "pass":
            errors.append(
                f"weight group {group['group_id']} must sum to {group['target']:g} "
                f"within tolerance {group['tolerance']:g}; got {group['total']:g}"
            )
    window_errors, window_warnings = _window_a_resource_messages(controls)
    errors.extend(window_errors)
    warnings.extend(window_warnings)
    owner_views = _generated_owner_views(controls)
    if tuple(owner_views) != OWNER_CONTROL_DOCS:
        errors.append("validation.machine_generated_owner_views must list the four canonical owner docs in order")
    return {
        "model_id": OWNER_CONTROLS_MODEL_ID,
        "status": "pass" if not errors else "blocked",
        "schema_valid": not errors,
        "config_version": str(controls.get("config_version") or ""),
        "task_id": str(controls.get("task_id") or ""),
        "production_enabled": project.get("production_enabled"),
        "weight_groups": weight_groups,
        "owner_view_files": owner_views,
        "rollback_config_version": str(_mapping(controls.get("validation")).get("rollback_config_version") or ""),
        "warnings": warnings,
        "errors": errors,
    }


def build_owner_impact_preview(controls: Mapping[str, Any], *, days: int = 30) -> dict[str, Any]:
    validation = validate_owner_controls(controls)
    enabled_sources = [item for item in _sequence_of_mappings(controls.get("sources")) if item.get("enabled") is True]
    enabled_boards = [item for item in _sequence_of_mappings(controls.get("boards")) if item.get("enabled") is True]
    queue = _mapping(controls.get("queue"))
    runtime = _mapping(controls.get("runtime"))
    window = _mapping(runtime.get("window_a_resource_limits"))
    email = _mapping(controls.get("email"))
    outputs = _mapping(controls.get("outputs"))
    return {
        "model_id": OWNER_CONTROLS_MODEL_ID,
        "status": validation["status"],
        "days": int(days),
        "config_version": str(controls.get("config_version") or ""),
        "schema_status": "pass" if validation["schema_valid"] else "blocked",
        "source_or_board_changes": "NOT_COMPUTED_NO_PRIOR_OWNER_CONTROLS_BASELINE",
        "enabled_sources": [str(item.get("source_id")) for item in enabled_sources],
        "enabled_boards": [str(item.get("board_id")) for item in enabled_boards],
        "ranking_change_preview": "S1_06_DETERMINISTIC_QUEUE_READY_NO_PRODUCTION_REPLAY_DATA",
        "queue_change_preview": {
            "max_active_items": int(queue.get("max_active_items") or 0),
            "new_items": "NOT_COMPUTED_NO_REPLAY_DATA",
            "exited_items": "NOT_COMPUTED_NO_REPLAY_DATA",
        },
        "email_coverage_preview": {
            "enabled": bool(email.get("enabled")),
            "split_mode": str(email.get("split_mode") or ""),
            "send_order": [str(item) for item in _as_sequence(email.get("send_order"))],
            "report_enabled": bool(outputs.get("report_enabled")),
            "audit_formats": ["markdown", "html", "json"],
        },
        "resource_estimate": {
            "max_fetch_concurrency": int(runtime.get("max_fetch_concurrency") or 0),
            "max_temp_cache_gb": float(runtime.get("max_temp_cache_gb") or 0),
            "window_a_max_online_arxiv_metadata": int(window.get("max_online_arxiv_metadata") or 0),
        },
        "rollback_config_version": validation["rollback_config_version"],
        "warnings": validation["warnings"],
        "errors": validation["errors"],
    }


def render_owner_documents(
    controls: Mapping[str, Any],
    *,
    project_path: str | Path | None = None,
    generated_at: str,
    write: bool = True,
) -> dict[str, Any]:
    root = Path(project_path) if project_path else project_root_default()
    validation = validate_owner_controls(controls)
    preview = build_owner_impact_preview(controls)
    candidate_registry, diagnostic_receipt_paths = _load_optional_cloudflare_candidate_registry(root)
    docs = {
        "docs/owner/OWNER_CONSOLE.md": _render_owner_console(controls, validation, preview, generated_at),
        "docs/owner/SOURCE_CATALOG.md": _render_source_catalog(controls, generated_at, candidate_registry),
        "docs/owner/MODEL_AND_QUEUE.md": _render_model_and_queue(controls, validation, preview, generated_at),
        "docs/owner/CONTENT_LEDGER.csv": _render_content_ledger_csv(generated_at),
    }
    written: list[str] = []
    if write:
        for relative_path, content in docs.items():
            output_path = root / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8", newline="")
            written.append(relative_path)
    return {
        "model_id": OWNER_CONTROLS_MODEL_ID,
        "status": "rendered" if validation["status"] == "pass" else "blocked",
        "generated_at": generated_at,
        "config_version": str(controls.get("config_version") or ""),
        "generated_from": "config/owner_controls.yaml",
        "source_catalog_inputs": [
            "config/owner_controls.yaml",
            *([CLOUDFLARE_SOURCE_CANDIDATE_REGISTRY_PATH] if candidate_registry else []),
            *diagnostic_receipt_paths,
        ],
        "owner_view_files": list(docs),
        "written_files": written,
        "errors": validation["errors"],
    }


def _render_owner_console(
    controls: Mapping[str, Any],
    validation: Mapping[str, Any],
    preview: Mapping[str, Any],
    generated_at: str,
) -> str:
    project = _mapping(controls.get("project"))
    email = _mapping(controls.get("email"))
    outputs = _mapping(controls.get("outputs"))
    lines = [
        "# Owner Console",
        "",
        f"- generated_at: {generated_at}",
        "- generated_from: `config/owner_controls.yaml`",
        f"- config_version: `{controls.get('config_version')}`",
        f"- task_id: `{controls.get('task_id')}`",
        f"- model_id: `{OWNER_CONTROLS_MODEL_ID}`",
        f"- validation_status: `{validation.get('status')}`",
        f"- production_enabled: `{_bool_text(project.get('production_enabled'))}`",
        f"- production_acceptance_claimed: `{_bool_text(outputs.get('production_acceptance_claimed'))}`",
        "",
        "## Current Conclusion",
        "",
        "Owner controls are installed for Stage 1 Window A. Production remains disabled; this run does not prove scheduled production, 30-day trial evidence, or live two-day operation.",
        "",
        "## Today Mail Plan",
        "",
        f"- email_enabled: `{_bool_text(email.get('enabled'))}`",
        f"- split_mode: `{email.get('split_mode')}`",
        f"- send_order: {_comma_list(_as_sequence(email.get('send_order')))}",
        f"- recipients: {_comma_list(_as_sequence(email.get('recipients')))}",
        "",
        "## Queue And Resource Pressure",
        "",
        f"- max_active_items: `{_mapping(controls.get('queue')).get('max_active_items')}`",
        f"- max_temp_cache_gb: `{_mapping(controls.get('runtime')).get('max_temp_cache_gb')}`",
        f"- window_a_max_online_arxiv_metadata: `{_mapping(_mapping(controls.get('runtime')).get('window_a_resource_limits')).get('max_online_arxiv_metadata')}`",
        f"- ranking_change_preview: `{preview.get('ranking_change_preview')}`",
        "",
        "## Required Human Decisions",
        "",
        "- No production enablement decision is accepted by this file alone.",
        "- S1-06 deterministic queue fixtures are available; production replay remains unclaimed until later runtime evidence exists.",
        "",
        "## Commands",
        "",
        "- `adp owner validate`",
        "- `adp owner preview-impact --days 30`",
        "- `adp owner render-docs --write`",
    ]
    return "\n".join(lines) + "\n"


def _render_source_catalog(
    controls: Mapping[str, Any],
    generated_at: str,
    candidate_registry: Mapping[str, Any] | None = None,
) -> str:
    lines = [
        "# 来源目录",
        "",
        f"- 生成时间: {generated_at}",
        "- 来源配置: `config/owner_controls.yaml`",
        f"- 配置版本: `{controls.get('config_version')}`",
        "",
        "## 板块",
        "",
        "| 板块 ID | 启用 | 名称 | 权重 |",
        "|---|---:|---|---:|",
    ]
    for board in _sequence_of_mappings(controls.get("boards")):
        lines.append(
            f"| `{board.get('board_id')}` | {_bool_text_zh(board.get('enabled'))} | {board.get('name')} | {board.get('weight')} |"
        )
    lines.extend(["", "## 来源", "", "| 来源 ID | 板块 | 启用 | 名称 | 采集方式 | 层级 | 频率 | 权重 | 健康状态 |", "|---|---|---:|---|---|---|---|---:|---|"])
    for source in _sequence_of_mappings(controls.get("sources")):
        lines.append(
            "| "
            f"`{source.get('source_id')}` | `{source.get('board_id')}` | {_bool_text_zh(source.get('enabled'))} | "
            f"{source.get('name')} | `{source.get('access_method')}` | `{source.get('tier')}` | "
            f"`{source.get('frequency')}` | {source.get('weight')} | {_health_status_text_zh(source.get('health_status'))} |"
        )
    if candidate_registry is not None:
        lines.extend(_render_cloudflare_candidate_catalog(candidate_registry))
    return "\n".join(lines) + "\n"


def _render_cloudflare_candidate_catalog(registry: Mapping[str, Any]) -> list[str]:
    task_id = str(registry.get("task_id") or "")
    implementation_path = str(registry.get("implementation_path") or "")
    verification_path = str(registry.get("verification_path") or "")
    live = _mapping(registry.get("live_route"))
    candidates = _sequence_of_mappings(registry.get("candidate_routes"))
    diagnostics = _sequence_of_mappings(registry.get("diagnostic_routes"))
    budget = _mapping(registry.get("subrequest_budget"))
    required = {
        "task_id": task_id,
        "implementation_path": implementation_path,
        "verification_path": verification_path,
        "live_route.source_id": str(live.get("source_id") or ""),
        "live_route.provider": str(live.get("provider") or ""),
        "live_route.state": str(live.get("state") or ""),
    }
    missing = [name for name, value in required.items() if not value]
    if missing or not candidates:
        detail = ", ".join([*missing, *(["candidate_routes"] if not candidates else [])])
        raise OwnerControlsError(f"Cloudflare candidate registry missing required fields: {detail}")

    lines = [
        "",
        "## Cloudflare v1.2 来源救援补充面",
        "",
        f"本节由 [`{CLOUDFLARE_SOURCE_CANDIDATE_REGISTRY_PATH}`](../../{CLOUDFLARE_SOURCE_CANDIDATE_REGISTRY_PATH}) 生成，属于当前 Cloudflare 产品线，不改变上方旧本机 `owner_controls.yaml` 目录。任务为 `{task_id}`；真实 live 路由仍由 [Worker registry](../../deploy/cloudflare/worker_cloud.js) 决定。",
        "",
        "| 来源 ID | 板块 | 提供方 | 状态 | 重试/活动边界 |",
        "|---|---|---|---|---|",
        f"| `{live.get('source_id')}` | `{live.get('board_id')}` | {live.get('provider')} | `{live.get('state')}` | 当前单次 live 抓取保持不变 |",
    ]
    for candidate in candidates:
        policy = _mapping(candidate.get("fetch_policy"))
        retry_statuses = "/".join(str(value) for value in _as_sequence(policy.get("retry_statuses")))
        delays = "/".join(str(value) for value in _as_sequence(policy.get("delays_ms")))
        redirect = str(policy.get("redirect") or "")
        candidate_required = {
            "source_id": str(candidate.get("source_id") or ""),
            "board_id": str(candidate.get("board_id") or ""),
            "provider": str(candidate.get("provider") or ""),
            "state": str(candidate.get("state") or ""),
            "max_attempts": str(policy.get("max_attempts") or ""),
            "retry_statuses": retry_statuses,
            "delays_ms": delays,
            "redirect": redirect,
        }
        candidate_missing = [name for name, value in candidate_required.items() if not value]
        if candidate_missing:
            raise OwnerControlsError(
                "Cloudflare candidate route missing required fields: " + ", ".join(candidate_missing)
            )
        lines.append(
            f"| `{candidate.get('source_id')}` | `{candidate.get('board_id')}` | {candidate.get('provider')} | `{candidate.get('state')}` | timeout/{retry_statuses} 最多 {policy.get('max_attempts')} 次，{delays}ms；redirect=`{redirect}`，不接入 Worker、不部署 |"
        )

    budget_required = (
        "current_live_max",
        "candidate_retry_increment_max",
        "projected_max_if_enabled",
        "cloudflare_workers_free_limit",
        "projected_headroom",
        "redirect_subrequests_per_attempt_max",
    )
    budget_missing = [name for name in budget_required if budget.get(name) is None]
    if budget_missing:
        raise OwnerControlsError(
            "Cloudflare candidate budget missing required fields: " + ", ".join(budget_missing)
        )
    lines.extend(
        [
            "",
            "可执行预算从真实 Worker registry/常量推导：当前 daily live external 最坏 "
            f"`{budget.get('current_live_max')}` 次；候选以后若获授权替换现有 Bing 单次路径，最多增加 "
            f"{budget.get('candidate_retry_increment_max')} 次，投影 `{budget.get('projected_max_if_enabled')}/{budget.get('cloudflare_workers_free_limit')}`，"
            f"保留 {budget.get('projected_headroom')} 次余量。手动 redirect 把每个 attempt 封顶为 "
            f"{budget.get('redirect_subrequests_per_attempt_max')} 个 subrequest。验收入口为 "
            f"[候选实现](../../{implementation_path}) / [可执行验证](../../{verification_path})。",
        ]
    )
    if diagnostics:
        lines.extend(
            [
                "",
                "### S2 stats-gov 诊断面",
                "",
                "| 任务 | 来源 | 状态 | 本地直连 | Cloudflare edge | 决策 |",
                "|---|---|---|---|---|---|",
            ]
        )
        for diagnostic in diagnostics:
            diagnostic_required = {
                "task_id": str(diagnostic.get("task_id") or ""),
                "source_id": str(diagnostic.get("source_id") or ""),
                "board_id": str(diagnostic.get("board_id") or ""),
                "provider": str(diagnostic.get("provider") or ""),
                "list_url": str(diagnostic.get("list_url") or ""),
                "state": str(diagnostic.get("state") or ""),
                "decision": str(diagnostic.get("decision") or ""),
                "state_semantics": str(diagnostic.get("state_semantics") or ""),
                "local_classification": str(diagnostic.get("local_classification") or ""),
                "local_observed_at": str(diagnostic.get("local_observed_at") or ""),
                "local_observation_id": str(diagnostic.get("local_observation_id") or ""),
                "edge_classification": str(diagnostic.get("edge_classification") or ""),
                "edge_observed_at": str(diagnostic.get("edge_observed_at") or ""),
                "edge_observation_id": str(diagnostic.get("edge_observation_id") or ""),
                "implementation_path": str(diagnostic.get("implementation_path") or ""),
                "verification_path": str(diagnostic.get("verification_path") or ""),
                "run_contract_path": str(diagnostic.get("run_contract_path") or ""),
                "receipt_path": str(diagnostic.get("receipt_path") or ""),
                "receipt_sha256": str(diagnostic.get("receipt_sha256") or ""),
                "minimum_next_condition": str(diagnostic.get("minimum_next_condition") or ""),
            }
            diagnostic_missing = [name for name, value in diagnostic_required.items() if not value]
            if diagnostic_missing:
                raise OwnerControlsError(
                    "Cloudflare diagnostic route missing required fields: " + ", ".join(diagnostic_missing)
                )
            lines.append(
                f"| `{diagnostic.get('task_id')}` | `{diagnostic.get('source_id')}` / `{diagnostic.get('board_id')}` "
                f"| `{diagnostic.get('state')}` | `{diagnostic.get('local_classification')}` / HTTP "
                f"{diagnostic.get('local_http_status')} / {diagnostic.get('local_parsed_count')} 项 / "
                f"`{diagnostic.get('local_observed_at')}` "
                f"| `{diagnostic.get('edge_classification')}` / {diagnostic.get('edge_parsed_count')} 项 / "
                f"`{diagnostic.get('edge_observed_at')}` "
                f"| `{diagnostic.get('decision')}`；不改 Worker、不部署 |"
            )
            historical_edge = _mapping(diagnostic.get("historical_edge_observation"))
            lines.extend(
                [
                    "",
                    f"状态语义：{diagnostic.get('state_semantics')} 历史 edge 点样在 "
                    f"`{historical_edge.get('observed_at')}`（{historical_edge.get('observation_time_basis')}）"
                    f"记录 `{historical_edge.get('classification')}` / {historical_edge.get('parsed_count')} 项，"
                    f"但标记为 `{historical_edge.get('verification_status')}`；最新已绑定原始哈希的 edge 点样"
                    f"在零 adapter 变更下恢复 `{diagnostic.get('edge_classification')}` / "
                    f"{diagnostic.get('edge_parsed_count')} 项。两者都只是点样，不能外推永久状态。",
                    "",
                    f"该诊断每次只发 {diagnostic.get('external_subrequests_per_probe')} 个只读外部请求，"
                    f"`write_allowed={str(bool(diagnostic.get('write_allowed'))).lower()}`、"
                    f"`live_change_authorized={str(bool(diagnostic.get('live_change_authorized'))).lower()}`。"
                    f"证据入口为 [诊断实现](../../{diagnostic.get('implementation_path')}) / "
                    f"[可执行验证](../../{diagnostic.get('verification_path')}) / "
                    f"[Run Contract](../../{diagnostic.get('run_contract_path')}) / "
                    f"[事实型 receipt](../../{diagnostic.get('receipt_path')})（SHA-256 "
                    f"`{diagnostic.get('receipt_sha256')}`；不自签验收）。",
                    "",
                    f"重新评估的最小条件：{diagnostic.get('minimum_next_condition')}",
                ]
            )
    return lines


def _render_model_and_queue(
    controls: Mapping[str, Any],
    validation: Mapping[str, Any],
    preview: Mapping[str, Any],
    generated_at: str,
) -> str:
    lines = [
        "# Model And Queue",
        "",
        f"- generated_at: {generated_at}",
        "- generated_from: `config/owner_controls.yaml`",
        f"- model_id: `{OWNER_CONTROLS_MODEL_ID}`",
        f"- validation_status: `{validation.get('status')}`",
        f"- rollback_config_version: `{validation.get('rollback_config_version')}`",
        "",
        "## Weight Groups",
        "",
        "| Group | Total | Target | Tolerance | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for group in validation.get("weight_groups", []):
        if isinstance(group, Mapping):
            lines.append(
                f"| `{group.get('group_id')}` | {group.get('total')} | {group.get('target')} | {group.get('tolerance')} | `{group.get('status')}` |"
            )
    lines.extend(["", "## Scoring Cards"])
    scoring = _mapping(controls.get("scoring"))
    for name, weights in scoring.items():
        lines.extend(["", f"### {name}", "", "| Component | Weight |", "|---|---:|"])
        for component, value in _mapping(weights).items():
            lines.append(f"| `{component}` | {value} |")
    queue = _mapping(controls.get("queue"))
    lines.extend(
        [
            "",
            "## Queue",
            "",
            f"- max_active_items: `{queue.get('max_active_items')}`",
            f"- max_event_age_days: `{queue.get('max_event_age_days')}`",
            f"- source_share_cap_per_board: `{queue.get('source_share_cap_per_board')}`",
            f"- replay_status: `{preview.get('ranking_change_preview')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_content_ledger_csv(generated_at: str) -> str:
    return render_content_ledger_csv(placeholder_content_ledger_rows(generated_at=generated_at))


def _weight_group_reports(controls: Mapping[str, Any]) -> list[dict[str, Any]]:
    validation = _mapping(controls.get("validation"))
    target = float(validation.get("weight_target") or 100)
    tolerance = float(validation.get("weight_tolerance") or 0.0001)
    reports: list[dict[str, Any]] = []
    reports.append(_weight_group("owner_sources", _weights_from_sequence(controls.get("sources")), target, tolerance))
    reports.append(_weight_group("owner_boards", _weights_from_sequence(controls.get("boards")), target, tolerance))
    scoring = _mapping(controls.get("scoring"))
    for group_id, weights in scoring.items():
        reports.append(_weight_group(f"owner_scoring_{group_id}", _weights_from_mapping(weights), target, tolerance))
    if "us_attention_budget" in controls:
        reports.append(_weight_group("owner_us_attention_budget", _weights_from_mapping(controls.get("us_attention_budget")), target, tolerance))
    return reports


def _weight_group(group_id: str, weights: Sequence[float], target: float, tolerance: float) -> dict[str, Any]:
    total = float(sum(weights))
    return {
        "group_id": group_id,
        "total": round(total, 10),
        "target": target,
        "tolerance": tolerance,
        "status": "pass" if abs(total - target) <= tolerance else "blocked",
        "component_count": len(weights),
    }


def _weights_from_sequence(value: Any) -> list[float]:
    return [float(item.get("weight") or 0) for item in _sequence_of_mappings(value)]


def _weights_from_mapping(value: Any) -> list[float]:
    return [float(item) for item in _mapping(value).values()]


def _window_a_resource_messages(controls: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    runtime = _mapping(controls.get("runtime"))
    window = _mapping(runtime.get("window_a_resource_limits"))
    if int(window.get("max_online_arxiv_metadata") or 0) > 10:
        errors.append("runtime.window_a_resource_limits.max_online_arxiv_metadata must be <= 10")
    if float(window.get("max_temp_cache_gb") or 0) > 2:
        errors.append("runtime.window_a_resource_limits.max_temp_cache_gb must be <= 2")
    if window.get("large_pdf_download_allowed") is not False:
        errors.append("runtime.window_a_resource_limits.large_pdf_download_allowed must be false")
    if float(runtime.get("min_free_disk_gb") or 0) < 40:
        warnings.append("runtime.min_free_disk_gb is below emergency buffer guidance")
    return errors, warnings


def _secret_hygiene_errors(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_PATTERN.search(key_text) and item not in (False, "", None, "NOT_APPLICABLE"):
                errors.append(f"{path}.{key_text} looks like a secret-bearing key and must not contain values")
            errors.extend(_secret_hygiene_errors(item, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_secret_hygiene_errors(item, f"{path}[{index}]"))
    elif isinstance(value, str) and SECRET_VALUE_PATTERN.search(value):
        errors.append(f"{path} contains a token-like value")
    return errors


def _generated_owner_views(controls: Mapping[str, Any]) -> list[str]:
    return [str(item) for item in _as_sequence(_mapping(controls.get("validation")).get("machine_generated_owner_views"))]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _as_sequence(value) if isinstance(item, Mapping)]


def _bool_text(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def _bool_text_zh(value: Any) -> str:
    return "是" if value is True else "否" if value is False else str(value)


def _health_status_text_zh(value: Any) -> str:
    status = str(value or "")
    labels = {
        "active": "已启用",
        "stage2_test": "影子测试",
        "planned": "规划中",
    }
    label = labels.get(status, status or "未填写")
    return f"{label} (`{status}`)" if status else label


def _comma_list(values: Sequence[Any]) -> str:
    return ", ".join(f"`{item}`" for item in values) if values else "`NOT_APPLICABLE`"


def _strip_comment(raw: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    chars: list[str] = []
    for char in raw:
        if char == "\\" and in_double and not escaped:
            escaped = True
            chars.append(char)
            continue
        if char == "'" and not in_double and not escaped:
            in_single = not in_single
        elif char == '"' and not in_single and not escaped:
            in_double = not in_double
        if char == "#" and not in_single and not in_double:
            break
        chars.append(char)
        escaped = False
    return "".join(chars).rstrip()


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_parse_scalar(part.strip()) for part in inner.split(",")]
    if value.startswith("{") and value.endswith("}"):
        return {} if value == "{}" else json.loads(value)
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _split_key_value(text: str) -> tuple[str, str | None]:
    if ":" not in text:
        return text.strip(), None
    key, value = text.split(":", 1)
    return key.strip(), value.strip()


def _fallback_yaml_load(text: str) -> Any:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        cleaned = _strip_comment(raw)
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        lines.append((indent, cleaned.strip()))
    if not lines:
        return {}

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(lines):
            return {}, index
        if lines[index][1].startswith("- ") or lines[index][1] == "-":
            result: list[Any] = []
            while index < len(lines) and lines[index][0] == indent and (
                lines[index][1].startswith("- ") or lines[index][1] == "-"
            ):
                item_text = lines[index][1][1:].strip()
                index += 1
                if item_text == "":
                    child_indent = lines[index][0] if index < len(lines) else indent + 2
                    item, index = parse_block(index, child_indent)
                    result.append(item)
                    continue
                key, value = _split_key_value(item_text)
                if value is None:
                    result.append(_parse_scalar(item_text))
                    continue
                item_map: dict[str, Any] = {key: _parse_scalar(value) if value != "" else {}}
                while index < len(lines) and lines[index][0] > indent:
                    child_indent, child_text = lines[index]
                    child_key, child_value = _split_key_value(child_text)
                    if child_value is None:
                        break
                    if child_value == "":
                        next_index = index + 1
                        if next_index < len(lines) and lines[next_index][0] > child_indent:
                            child, index = parse_block(next_index, lines[next_index][0])
                            item_map[child_key] = child
                        else:
                            item_map[child_key] = {}
                            index += 1
                    else:
                        item_map[child_key] = _parse_scalar(child_value)
                        index += 1
                result.append(item_map)
            return result, index

        result_map: dict[str, Any] = {}
        while index < len(lines) and lines[index][0] == indent and not (
            lines[index][1].startswith("- ") or lines[index][1] == "-"
        ):
            key, value = _split_key_value(lines[index][1])
            if value is None:
                raise OwnerControlsError(f"Invalid YAML line: {lines[index][1]}")
            if value == "":
                next_index = index + 1
                if next_index < len(lines) and lines[next_index][0] > indent:
                    child, index = parse_block(next_index, lines[next_index][0])
                    result_map[key] = child
                else:
                    result_map[key] = {}
                    index += 1
            else:
                result_map[key] = _parse_scalar(value)
                index += 1
        return result_map, index

    parsed, end = parse_block(0, lines[0][0])
    if end != len(lines):
        raise OwnerControlsError(f"Could not parse YAML near line: {lines[end][1]}")
    return parsed


def _load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _fallback_yaml_load(text)

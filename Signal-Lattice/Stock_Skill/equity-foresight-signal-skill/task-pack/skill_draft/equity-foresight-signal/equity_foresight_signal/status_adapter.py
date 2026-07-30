from __future__ import annotations

from typing import Any

from .canonical import sha256_hex
from .engine import _parse_time
from .errors import EFSError
from .lifecycle import _promotion_decision, _validation_report, health_snapshot

STATUS_PAYLOAD_SCHEMA = "efs.host_status_payload.v3"
BUSINESS_BASELINE_MATRIX_SCHEMA = "efs.business_baseline_matrix.v1"
STATUS_ENDPOINT = "status.linzezhang.com"
STATUS_SNAPSHOT_KEY = "business_baselines.equity_foresight_signal"

_BUSINESS_LINE_ORDER = (
    "BL-01-DATA-EVIDENCE",
    "BL-02-FORECAST",
    "BL-03-OUTCOME",
    "BL-04-LIFECYCLE",
    "BL-05-STATUS",
)
_BUSINESS_LINE_EDGES = (
    ("BL-01-DATA-EVIDENCE", "BL-02-FORECAST", "GATES"),
    ("BL-02-FORECAST", "BL-03-OUTCOME", "PRODUCES_EVIDENCE_FOR"),
    ("BL-03-OUTCOME", "BL-04-LIFECYCLE", "CONSTRAINS"),
    ("BL-01-DATA-EVIDENCE", "BL-05-STATUS", "REPORTS_TO"),
    ("BL-02-FORECAST", "BL-05-STATUS", "REPORTS_TO"),
    ("BL-03-OUTCOME", "BL-05-STATUS", "REPORTS_TO"),
    ("BL-04-LIFECYCLE", "BL-05-STATUS", "REPORTS_TO"),
)
_ALLOWED_MATRIX_STATUSES = {
    "BLOCKED",
    "BLOCKED_BY_UPSTREAM",
    "CONTROLLED",
    "DEGRADED",
    "FAILED_SHADOW_ONLY",
    "HOST_APPROVAL_ELIGIBLE",
    "LOCKED_SHADOW_ONLY",
    "NOT_AVAILABLE",
    "NOT_READY",
    "READY_FOR_HOST_TRANSPORT",
    "SHADOW_READY",
    "VALIDATED",
}
_ROW_KEYS = {
    "business_line_id",
    "name_zh",
    "stage",
    "phase",
    "status",
    "owner",
    "horizons",
    "depends_on",
    "downstream",
    "coupling_controls",
    "blocking_reasons",
    "next_action",
    "evidence_sha256",
    "display_zh",
}

_STATUS_ZH = {
    "BLOCKED": "已阻断",
    "BLOCKED_BY_UPSTREAM": "被上游阻断",
    "CONTROLLED": "受控",
    "DEGRADED": "降级",
    "FAILED_SHADOW_ONLY": "结果未通过，仅影子运行",
    "HOST_APPROVAL_ELIGIBLE": "具备宿主单独审批条件",
    "LOCKED_SHADOW_ONLY": "锁定为影子运行",
    "NOT_AVAILABLE": "暂无证据",
    "NOT_READY": "尚未就绪",
    "READY_FOR_HOST_TRANSPORT": "可由宿主登记",
    "SHADOW_READY": "影子预测就绪",
    "VALIDATED": "已验证",
}
_STAGE_ZH = {
    "S1_INPUT_CONTROL": "输入与证据控制",
    "S2_SHADOW_INFERENCE": "影子预测",
    "S3_OUTCOME_VALIDATION": "结果验证与证伪",
    "S4_LIFECYCLE_GOVERNANCE": "模型生命周期治理",
    "S5_STATUS_AND_RECOVERY": "状态登记与恢复",
}
_PHASE_ZH = {
    "P1_VERSIONED_EVIDENCE_SNAPSHOT": "版本化证据快照",
    "P2_MULTI_HORIZON_EVALUATION": "多周期确定性评估",
    "P3_WALK_FORWARD_AND_NULL_COMPARISON": "滚动样本外与空模型对照",
    "P4_CANDIDATE_LKG_PROMOTION_CONTROL": "候选、最后可用版本与晋级控制",
    "P5_HOST_MATRIX_RENDER_AND_RECOVERY": "宿主矩阵展示与恢复事实",
}
_OWNER_ZH = {
    "HOST_SUPPLIES_SKILL_VALIDATES": "宿主提供，Skill 校验",
    "SKILL_DETERMINISTIC_RUNTIME": "Skill 确定性运行内核",
    "HOST_OR_OFFLINE_DETERMINISTIC_PIPELINE": "宿主或离线确定性验证流水线",
    "HOST_CONTROL_PLANE": "宿主控制平面",
    "HOST_TRANSPORT_AND_PERSISTENCE": "宿主负责传输与短期状态持久化",
}
_CONTROL_ZH = {
    "PIT_HASH_BOUND": "时点数据与哈希绑定",
    "UNIVERSE_BOUND": "股票池范围绑定",
    "LICENSE_BOUND": "数据许可边界绑定",
    "MODEL_SET_HASH_BOUND": "模型集合哈希绑定",
    "HORIZON_ISOLATED": "预测周期相互隔离",
    "ABSTAIN_FAIL_CLOSED": "异常时拒绝预测并关闭失败路径",
    "REPORT_HASH_BOUND": "结果报告哈希绑定",
    "NULL_MODEL_REQUIRED": "必须与空模型基准对照",
    "NO_AUTOMATIC_PROMOTION": "禁止自动晋级",
    "CANDIDATE_LKG_HASH_BOUND": "候选与最后可用版本哈希绑定",
    "HOST_APPROVAL_REQUIRED": "必须由宿主单独审批",
    "ROLLBACK_PLAN_REQUIRED": "必须具备回滚方案",
    "MATRIX_HASH_BOUND": "矩阵哈希绑定",
    "HOST_OWNS_TRANSPORT": "宿主负责传输",
    "NO_SELF_PERSISTENCE": "Skill 不自行持久化",
}
_BLOCKER_ZH = {
    "BUNDLE_INVALID": "模型包无效",
    "BUNDLE_NOT_PROVIDED": "尚未提供模型包",
    "UPSTREAM_DATA_NOT_CONTROLLED": "上游数据尚未受控",
    "OUTCOME_VALIDATION_FAILED": "样本外结果验证未通过",
    "OUTCOME_REPORT_NOT_AVAILABLE": "尚无结果验证报告",
    "RELEASE_CAPABILITY_CEILING_SHADOW_ONLY": "当前版本能力上限为影子运行",
    "OUTCOME_NOT_PROVEN_OR_FAILED": "预测效果尚未证明或已经失败",
    "PROMOTION_NOT_ELIGIBLE": "尚不具备晋级条件",
    "EXPIRED": "模型包已过期",
    "CALIBRATION_EXPIRED": "概率校准器已过期",
    "NOT_YET_VALID": "模型包尚未到生效时间",
}
_ACTION_ZH = {
    "HOST_SUPPLY_OR_REPAIR_VERSIONED_EVIDENCE": "由宿主补充或修复版本化证据",
    "ALLOW_SHADOW_INFERENCE": "允许进入影子预测",
    "GENERATE_SHADOW_FORECAST": "生成影子预测结果",
    "KEEP_ABSTAIN": "继续拒绝预测",
    "KEEP_SHADOW_AND_RUN_BOUNDED_VALIDATION": "保持影子运行并执行有界验证",
    "EVALUATE_FROZEN_PROMOTION_POLICY": "按冻结晋级规则评估",
    "HOST_SEPARATE_APPROVAL": "由宿主执行单独审批",
    "KEEP_LKG_AND_SHADOW_ONLY": "保留最后可用版本并维持影子运行",
    "HOST_RENDER_MATRIX_AND_PERSIST_COMPACT_FACT": "由宿主展示矩阵并保存紧凑状态事实",
}
_DISPLAY_KEYS = {
    "stage", "phase", "status", "owner", "coupling_controls",
    "blocking_reasons", "next_action",
}


def _display_zh(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": _STAGE_ZH[row["stage"]],
        "phase": _PHASE_ZH[row["phase"]],
        "status": _STATUS_ZH[row["status"]],
        "owner": _OWNER_ZH[row["owner"]],
        "coupling_controls": [_CONTROL_ZH[item] for item in row["coupling_controls"]],
        "blocking_reasons": [_BLOCKER_ZH.get(item, f"受控错误：{item}") for item in row["blocking_reasons"]],
        "next_action": _ACTION_ZH[row["next_action"]],
    }

_MATRIX_KEYS = {
    "schema",
    "stable_id",
    "runtime_version",
    "as_of",
    "status_endpoint",
    "status_snapshot_key",
    "minimum_host_view",
    "columns_zh",
    "rows",
    "edges",
    "summary",
    "self_network_transport",
    "self_persistence",
    "agent_invocations_total",
    "llm_requests_total",
    "llm_input_tokens_total",
    "llm_output_tokens_total",
    "network_requests_total",
    "matrix_sha256",
}


def _verify_hash(value: dict[str, Any], key: str, field: str) -> str:
    claimed = value.get(key)
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise EFSError("CONTRACT_INVALID", f"{field} lacks SHA-256")
    payload = dict(value)
    payload.pop(key, None)
    if claimed != sha256_hex(payload):
        raise EFSError("HASH_MISMATCH", f"{field} hash mismatch")
    return claimed


def _validate_string_list(value: Any, *, field: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise EFSError("CONTRACT_INVALID", f"{field} must be a list")
    if any(not isinstance(item, str) or not item for item in value):
        raise EFSError("CONTRACT_INVALID", f"{field} contains an invalid value")
    if len(value) != len(set(value)):
        raise EFSError("CONTRACT_INVALID", f"{field} contains duplicates")
    return value


def _topology(rows: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [row["business_line_id"] for row in rows]
    id_set = set(ids)
    adjacency = {line_id: [] for line_id in ids}
    indegree = {line_id: 0 for line_id in ids}
    edge_pairs: set[tuple[str, str]] = set()
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "relation"}:
            raise EFSError("CONTRACT_INVALID", "business matrix edge shape mismatch")
        source, target, relation = edge["from"], edge["to"], edge["relation"]
        if not all(isinstance(item, str) and item for item in (source, target, relation)):
            raise EFSError("CONTRACT_INVALID", "business matrix edge contains invalid values")
        if source not in id_set or target not in id_set or source == target:
            raise EFSError("CONTRACT_INVALID", "business matrix edge references an invalid node")
        pair = (source, target)
        if pair in edge_pairs:
            raise EFSError("CONTRACT_INVALID", "business matrix contains duplicate edges")
        edge_pairs.add(pair)
        adjacency[source].append(target)
        indegree[target] += 1

    expected_dependencies = {line_id: [] for line_id in ids}
    expected_downstream = {line_id: [] for line_id in ids}
    for source, target in sorted(edge_pairs):
        expected_dependencies[target].append(source)
        expected_downstream[source].append(target)
    for row in rows:
        line_id = row["business_line_id"]
        if sorted(row["depends_on"]) != sorted(expected_dependencies[line_id]):
            raise EFSError("CONTRACT_INVALID", f"business matrix depends_on mismatch: {line_id}")
        if sorted(row["downstream"]) != sorted(expected_downstream[line_id]):
            raise EFSError("CONTRACT_INVALID", f"business matrix downstream mismatch: {line_id}")

    queue = sorted(line_id for line_id, degree in indegree.items() if degree == 0)
    visited: list[str] = []
    while queue:
        current = queue.pop(0)
        visited.append(current)
        for target in sorted(adjacency[current]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort()
    if len(visited) != len(ids):
        raise EFSError("CONTRACT_INVALID", "business matrix dependency graph contains a cycle")

    root_count = sum(1 for line_id in ids if not expected_dependencies[line_id])
    terminal_count = sum(1 for line_id in ids if not expected_downstream[line_id])
    orphan_count = sum(
        1
        for line_id in ids
        if not expected_dependencies[line_id] and not expected_downstream[line_id]
    )
    return {
        "topology_status": "ACYCLIC",
        "root_count": root_count,
        "terminal_count": terminal_count,
        "orphan_count": orphan_count,
        "topological_order": visited,
    }


def validate_business_baseline_matrix(value: Any) -> dict[str, Any]:
    """Validate a host-supplied or persisted matrix without network or side effects."""
    if not isinstance(value, dict) or set(value) != _MATRIX_KEYS:
        raise EFSError("CONTRACT_INVALID", "business matrix shape mismatch")
    _verify_hash(value, "matrix_sha256", "business matrix")
    if value.get("schema") != BUSINESS_BASELINE_MATRIX_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "business matrix schema mismatch")
    if value.get("status_endpoint") != STATUS_ENDPOINT:
        raise EFSError("CONTRACT_INVALID", "business matrix status endpoint mismatch")
    if value.get("status_snapshot_key") != STATUS_SNAPSHOT_KEY:
        raise EFSError("CONTRACT_INVALID", "business matrix snapshot key mismatch")
    if value.get("minimum_host_view") != "MATRIX_TABLE":
        raise EFSError("CONTRACT_INVALID", "business matrix minimum host view mismatch")
    _parse_time(value.get("as_of"), "business matrix.as_of")
    for key in (
        "self_network_transport",
        "self_persistence",
    ):
        if value.get(key) is not False:
            raise EFSError("CONTRACT_INVALID", f"business matrix {key} must be false")
    for key in (
        "agent_invocations_total",
        "llm_requests_total",
        "llm_input_tokens_total",
        "llm_output_tokens_total",
        "network_requests_total",
    ):
        if value.get(key) != 0:
            raise EFSError("CONTRACT_INVALID", f"business matrix {key} must be zero")

    columns = _validate_string_list(value.get("columns_zh"), field="business matrix.columns_zh", allow_empty=False)
    if "阶段" not in columns or "阶段环节" not in columns or "状态" not in columns or "关联性" not in columns:
        raise EFSError("CONTRACT_INVALID", "business matrix minimum columns are incomplete")

    rows = value.get("rows")
    if not isinstance(rows, list) or len(rows) != len(_BUSINESS_LINE_ORDER):
        raise EFSError("CONTRACT_INVALID", "business matrix row count mismatch")
    observed_ids: list[str] = []
    status_counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise EFSError("CONTRACT_INVALID", f"business matrix row shape mismatch: {index}")
        line_id = row.get("business_line_id")
        if line_id != _BUSINESS_LINE_ORDER[index]:
            raise EFSError("CONTRACT_INVALID", "business matrix row order/identity mismatch")
        observed_ids.append(line_id)
        for key in ("name_zh", "stage", "phase", "status", "owner", "next_action"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise EFSError("CONTRACT_INVALID", f"business matrix row {line_id} missing {key}")
        if row["status"] not in _ALLOWED_MATRIX_STATUSES:
            raise EFSError("CONTRACT_INVALID", f"business matrix row {line_id} status is invalid")
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        _validate_string_list(row.get("horizons"), field=f"business matrix {line_id}.horizons")
        _validate_string_list(row.get("depends_on"), field=f"business matrix {line_id}.depends_on")
        _validate_string_list(row.get("downstream"), field=f"business matrix {line_id}.downstream")
        _validate_string_list(
            row.get("coupling_controls"),
            field=f"business matrix {line_id}.coupling_controls",
            allow_empty=False,
        )
        _validate_string_list(row.get("blocking_reasons"), field=f"business matrix {line_id}.blocking_reasons")
        evidence = row.get("evidence_sha256")
        if evidence is not None and (not isinstance(evidence, str) or len(evidence) != 64):
            raise EFSError("CONTRACT_INVALID", f"business matrix row {line_id} evidence hash is invalid")
        display = row.get("display_zh")
        if not isinstance(display, dict) or set(display) != _DISPLAY_KEYS:
            raise EFSError("CONTRACT_INVALID", f"business matrix row {line_id} Chinese display shape mismatch")
        if display != _display_zh(row):
            raise EFSError("CONTRACT_INVALID", f"business matrix row {line_id} Chinese display mismatch")
    if len(observed_ids) != len(set(observed_ids)):
        raise EFSError("CONTRACT_INVALID", "business matrix contains duplicate line IDs")

    edges = value.get("edges")
    if not isinstance(edges, list):
        raise EFSError("CONTRACT_INVALID", "business matrix edges must be a list")
    topology = _topology(rows, edges)
    expected_edges = [
        {"from": source, "to": target, "relation": relation}
        for source, target, relation in _BUSINESS_LINE_EDGES
    ]
    if edges != expected_edges:
        raise EFSError("CONTRACT_INVALID", "business matrix canonical edge set mismatch")

    blocked_statuses = {"BLOCKED", "BLOCKED_BY_UPSTREAM", "FAILED_SHADOW_ONLY"}
    degraded_statuses = {"DEGRADED", "LOCKED_SHADOW_ONLY", "NOT_AVAILABLE", "NOT_READY"}
    derived_summary = {
        "line_count": len(rows),
        "edge_count": len(edges),
        "status_counts": dict(sorted(status_counts.items())),
        "blocked_line_count": sum(status_counts.get(item, 0) for item in blocked_statuses),
        "degraded_line_count": sum(status_counts.get(item, 0) for item in degraded_statuses),
        **topology,
    }
    declared_summary = value.get("summary")
    if declared_summary != derived_summary:
        raise EFSError("CONTRACT_INVALID", "business matrix summary mismatch")
    return {
        "schema": "efs.business_baseline_matrix_validation.v1",
        "status": "PASS",
        "matrix_sha256": value["matrix_sha256"],
        "line_count": len(rows),
        "edge_count": len(edges),
        "topology_status": topology["topology_status"],
        "orphan_count": topology["orphan_count"],
    }


def _business_baseline_matrix(
    *,
    as_of: str,
    health_map: dict[str, Any],
    outcome: dict[str, Any] | None,
    promotion: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a host-renderable vertical-slice matrix with explicit coupling."""
    health_status = health_map.get("status")
    bundle_state = health_map.get("bundle_state")
    outcome_status = outcome.get("overall_status") if outcome else "NOT_AVAILABLE"
    promotion_eligible = bool(promotion and promotion.get("eligible_for_separate_host_approval") is True)
    horizons = [f"{value}D" for value in health_map.get("horizons", []) if isinstance(value, int)]

    if health_status == "UNHEALTHY":
        data_state = "BLOCKED"
        data_blockers = [str(health_map.get("error", {}).get("code", "BUNDLE_INVALID"))]
    elif health_status == "DEGRADED":
        data_state = "DEGRADED"
        data_blockers = [str(bundle_state)]
    elif bundle_state == "NOT_PROVIDED":
        data_state = "NOT_READY"
        data_blockers = ["BUNDLE_NOT_PROVIDED"]
    else:
        data_state = "CONTROLLED"
        data_blockers = []

    forecast_ready = data_state == "CONTROLLED"
    forecast_state = "SHADOW_READY" if forecast_ready else "BLOCKED_BY_UPSTREAM"
    forecast_blockers = [] if forecast_ready else ["UPSTREAM_DATA_NOT_CONTROLLED"]

    if outcome_status == "PASS":
        outcome_state, outcome_blockers = "VALIDATED", []
    elif outcome_status == "FAIL":
        outcome_state, outcome_blockers = "FAILED_SHADOW_ONLY", ["OUTCOME_VALIDATION_FAILED"]
    else:
        outcome_state, outcome_blockers = "NOT_AVAILABLE", ["OUTCOME_REPORT_NOT_AVAILABLE"]

    if promotion_eligible and outcome_status == "PASS":
        lifecycle_state = "HOST_APPROVAL_ELIGIBLE"
        lifecycle_blockers: list[str] = []
    else:
        lifecycle_state = "LOCKED_SHADOW_ONLY"
        lifecycle_blockers = ["RELEASE_CAPABILITY_CEILING_SHADOW_ONLY"]
        if outcome_status != "PASS":
            lifecycle_blockers.append("OUTCOME_NOT_PROVEN_OR_FAILED")
        if not promotion_eligible:
            lifecycle_blockers.append("PROMOTION_NOT_ELIGIBLE")

    dependencies: dict[str, list[str]] = {line_id: [] for line_id in _BUSINESS_LINE_ORDER}
    downstream: dict[str, list[str]] = {line_id: [] for line_id in _BUSINESS_LINE_ORDER}
    edges = [
        {"from": source, "to": target, "relation": relation}
        for source, target, relation in _BUSINESS_LINE_EDGES
    ]
    for source, target, _relation in _BUSINESS_LINE_EDGES:
        dependencies[target].append(source)
        downstream[source].append(target)

    rows = [
        {
            "business_line_id": "BL-01-DATA-EVIDENCE",
            "name_zh": "证据与PIT输入",
            "stage": "S1_INPUT_CONTROL",
            "phase": "P1_VERSIONED_EVIDENCE_SNAPSHOT",
            "status": data_state,
            "owner": "HOST_SUPPLIES_SKILL_VALIDATES",
            "horizons": horizons,
            "depends_on": dependencies["BL-01-DATA-EVIDENCE"],
            "downstream": downstream["BL-01-DATA-EVIDENCE"],
            "coupling_controls": ["PIT_HASH_BOUND", "UNIVERSE_BOUND", "LICENSE_BOUND"],
            "blocking_reasons": sorted(set(data_blockers)),
            "next_action": "HOST_SUPPLY_OR_REPAIR_VERSIONED_EVIDENCE" if data_blockers else "ALLOW_SHADOW_INFERENCE",
            "evidence_sha256": health_map.get("snapshot_sha256"),
        },
        {
            "business_line_id": "BL-02-FORECAST",
            "name_zh": "方向、幅度与时机预测",
            "stage": "S2_SHADOW_INFERENCE",
            "phase": "P2_MULTI_HORIZON_EVALUATION",
            "status": forecast_state,
            "owner": "SKILL_DETERMINISTIC_RUNTIME",
            "horizons": horizons,
            "depends_on": dependencies["BL-02-FORECAST"],
            "downstream": downstream["BL-02-FORECAST"],
            "coupling_controls": ["MODEL_SET_HASH_BOUND", "HORIZON_ISOLATED", "ABSTAIN_FAIL_CLOSED"],
            "blocking_reasons": forecast_blockers,
            "next_action": "GENERATE_SHADOW_FORECAST" if forecast_ready else "KEEP_ABSTAIN",
            "evidence_sha256": health_map.get("model_set_sha256"),
        },
        {
            "business_line_id": "BL-03-OUTCOME",
            "name_zh": "样本外结果与证伪",
            "stage": "S3_OUTCOME_VALIDATION",
            "phase": "P3_WALK_FORWARD_AND_NULL_COMPARISON",
            "status": outcome_state,
            "owner": "HOST_OR_OFFLINE_DETERMINISTIC_PIPELINE",
            "horizons": [f"{outcome.get('horizon')}D"] if outcome and isinstance(outcome.get("horizon"), int) else horizons,
            "depends_on": dependencies["BL-03-OUTCOME"],
            "downstream": downstream["BL-03-OUTCOME"],
            "coupling_controls": ["REPORT_HASH_BOUND", "NULL_MODEL_REQUIRED", "NO_AUTOMATIC_PROMOTION"],
            "blocking_reasons": outcome_blockers,
            "next_action": "KEEP_SHADOW_AND_RUN_BOUNDED_VALIDATION" if outcome_state != "VALIDATED" else "EVALUATE_FROZEN_PROMOTION_POLICY",
            "evidence_sha256": outcome.get("report_sha256") if outcome else None,
        },
        {
            "business_line_id": "BL-04-LIFECYCLE",
            "name_zh": "Candidate、LKG与发布边界",
            "stage": "S4_LIFECYCLE_GOVERNANCE",
            "phase": "P4_CANDIDATE_LKG_PROMOTION_CONTROL",
            "status": lifecycle_state,
            "owner": "HOST_CONTROL_PLANE",
            "horizons": horizons,
            "depends_on": dependencies["BL-04-LIFECYCLE"],
            "downstream": downstream["BL-04-LIFECYCLE"],
            "coupling_controls": ["CANDIDATE_LKG_HASH_BOUND", "HOST_APPROVAL_REQUIRED", "ROLLBACK_PLAN_REQUIRED"],
            "blocking_reasons": sorted(set(lifecycle_blockers)),
            "next_action": "HOST_SEPARATE_APPROVAL" if lifecycle_state == "HOST_APPROVAL_ELIGIBLE" else "KEEP_LKG_AND_SHADOW_ONLY",
            "evidence_sha256": promotion.get("decision_sha256") if promotion else None,
        },
        {
            "business_line_id": "BL-05-STATUS",
            "name_zh": "状态登记、展示与恢复事实",
            "stage": "S5_STATUS_AND_RECOVERY",
            "phase": "P5_HOST_MATRIX_RENDER_AND_RECOVERY",
            "status": "READY_FOR_HOST_TRANSPORT",
            "owner": "HOST_TRANSPORT_AND_PERSISTENCE",
            "horizons": horizons,
            "depends_on": dependencies["BL-05-STATUS"],
            "downstream": downstream["BL-05-STATUS"],
            "coupling_controls": ["MATRIX_HASH_BOUND", "HOST_OWNS_TRANSPORT", "NO_SELF_PERSISTENCE"],
            "blocking_reasons": [],
            "next_action": "HOST_RENDER_MATRIX_AND_PERSIST_COMPACT_FACT",
            "evidence_sha256": health_map.get("snapshot_sha256"),
        },
    ]
    for row in rows:
        row["display_zh"] = _display_zh(row)
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    topology = _topology(rows, edges)
    blocked_statuses = {"BLOCKED", "BLOCKED_BY_UPSTREAM", "FAILED_SHADOW_ONLY"}
    degraded_statuses = {"DEGRADED", "LOCKED_SHADOW_ONLY", "NOT_AVAILABLE", "NOT_READY"}
    summary = {
        "line_count": len(rows),
        "edge_count": len(edges),
        "status_counts": dict(sorted(status_counts.items())),
        "blocked_line_count": sum(status_counts.get(item, 0) for item in blocked_statuses),
        "degraded_line_count": sum(status_counts.get(item, 0) for item in degraded_statuses),
        **topology,
    }
    matrix: dict[str, Any] = {
        "schema": BUSINESS_BASELINE_MATRIX_SCHEMA,
        "stable_id": health_map.get("stable_id"),
        "runtime_version": health_map.get("runtime_version"),
        "as_of": as_of,
        "status_endpoint": STATUS_ENDPOINT,
        "status_snapshot_key": STATUS_SNAPSHOT_KEY,
        "minimum_host_view": "MATRIX_TABLE",
        "columns_zh": ["业务线", "阶段", "阶段环节", "状态", "关联性", "耦合控制", "阻塞原因", "下一动作"],
        "rows": rows,
        "edges": edges,
        "summary": summary,
        "self_network_transport": False,
        "self_persistence": False,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    matrix["matrix_sha256"] = sha256_hex(matrix)
    validate_business_baseline_matrix(matrix)
    return matrix


def _validated_status_facts(
    *,
    as_of: str,
    bundle: dict[str, Any] | str | bytes | None,
    outcome_report: dict[str, Any] | str | bytes | None,
    promotion_decision: dict[str, Any] | str | bytes | None,
) -> tuple[dict[str, Any], str, dict[str, Any] | None, dict[str, Any] | None]:
    """Normalize and cross-bind the exact facts used by every status view."""
    _parse_time(as_of, "status.as_of")
    health_map = health_snapshot(bundle, as_of=as_of)
    claimed_health = _verify_hash(health_map, "snapshot_sha256", "health snapshot")

    outcome = _validation_report(outcome_report, "outcome report") if outcome_report is not None else None
    promotion = _promotion_decision(promotion_decision, "promotion decision") if promotion_decision is not None else None
    if outcome is not None:
        _verify_hash(outcome, "report_sha256", "outcome report")
    if promotion is not None:
        _verify_hash(promotion, "decision_sha256", "promotion decision")

    if outcome is not None and health_map.get("bundle_state") == "VALID":
        if outcome.get("subject_model_set_sha256") != health_map.get("model_set_sha256"):
            raise EFSError("CONTRACT_INVALID", "outcome report does not belong to the supplied bundle")
    if promotion is not None and promotion.get("eligible_for_separate_host_approval") is True:
        if health_map.get("bundle_state") != "VALID":
            raise EFSError("CONTRACT_INVALID", "eligible promotion requires a valid supplied bundle")
        if promotion.get("candidate_bundle_sha256") != health_map.get("bundle_sha256"):
            raise EFSError("CONTRACT_INVALID", "promotion decision does not belong to the supplied bundle")
        if outcome is None:
            raise EFSError("CONTRACT_INVALID", "eligible promotion requires its bound outcome report")
        expected_report_key = (
            "untouched_holdout_report_sha256"
            if promotion.get("intended_mode") == "DECISION_SUPPORT"
            else "oos_report_sha256"
        )
        if promotion.get(expected_report_key) != outcome.get("report_sha256"):
            raise EFSError("CONTRACT_INVALID", "promotion decision and outcome report are not bound together")

    return health_map, claimed_health, outcome, promotion


def build_business_baseline_matrix(
    *,
    as_of: str,
    bundle: dict[str, Any] | str | bytes | None = None,
    outcome_report: dict[str, Any] | str | bytes | None = None,
    promotion_decision: dict[str, Any] | str | bytes | None = None,
) -> dict[str, Any]:
    """Build only the business matrix for a host that stores separate status facts."""
    health_map, _claimed_health, outcome, promotion = _validated_status_facts(
        as_of=as_of,
        bundle=bundle,
        outcome_report=outcome_report,
        promotion_decision=promotion_decision,
    )
    return _business_baseline_matrix(as_of=as_of, health_map=health_map, outcome=outcome, promotion=promotion)


def build_host_status_payload(
    *,
    as_of: str,
    bundle: dict[str, Any] | str | bytes | None = None,
    outcome_report: dict[str, Any] | str | bytes | None = None,
    promotion_decision: dict[str, Any] | str | bytes | None = None,
) -> dict[str, Any]:
    """Build a pure status fact; the host owns transport and persistence."""
    health_map, claimed_health, outcome, promotion = _validated_status_facts(
        as_of=as_of,
        bundle=bundle,
        outcome_report=outcome_report,
        promotion_decision=promotion_decision,
    )

    health_status = health_map.get("status")
    outcome_status = outcome.get("overall_status") if outcome else "NOT_AVAILABLE"
    promotion_eligible = bool(promotion and promotion.get("eligible_for_separate_host_approval") is True)

    if health_status == "UNHEALTHY":
        display_state, capability, recovery = "RED", "ABSTAIN", "KEEP_LKG_AND_ABSTAIN"
    elif health_status == "DEGRADED":
        display_state, capability, recovery = "AMBER", "RESEARCH_OR_SHADOW_ONLY", "KEEP_LKG_AND_REJECT_NEW_PROMOTION"
    elif outcome_status == "FAIL":
        display_state, capability, recovery = "AMBER", "SHADOW_ONLY", "KEEP_LKG_AND_CONTINUE_NON_BLOCKING_VALIDATION"
    elif outcome_status == "PASS" and promotion_eligible:
        display_state, capability, recovery = "GREEN", "ELIGIBLE_FOR_HOST_CONTROLLED_ACTIVATION", "NO_ACTION"
    else:
        display_state, capability, recovery = "AMBER", "RESEARCH_ONLY", "KEEP_LKG"

    business_matrix = _business_baseline_matrix(
        as_of=as_of,
        health_map=health_map,
        outcome=outcome,
        promotion=promotion,
    )

    result: dict[str, Any] = {
        "schema": STATUS_PAYLOAD_SCHEMA,
        "stable_id": health_map.get("stable_id"),
        "runtime_version": health_map.get("runtime_version"),
        "as_of": as_of,
        "overall_status": health_status,
        "display_state": display_state,
        "capability_state": capability,
        "recovery_directive": recovery,
        "status_endpoint": STATUS_ENDPOINT,
        "status_snapshot_key": STATUS_SNAPSHOT_KEY,
        "business_baseline_matrix": business_matrix,
        "business_baseline_matrix_sha256": business_matrix["matrix_sha256"],
        "bundle_state": health_map.get("bundle_state"),
        "health_snapshot_sha256": claimed_health,
        "outcome_status": outcome_status,
        "outcome_report_sha256": outcome.get("report_sha256") if outcome else None,
        "promotion_decision": promotion.get("decision") if promotion else None,
        "promotion_decision_sha256": promotion.get("decision_sha256") if promotion else None,
        "host_transport_required": True,
        "self_network_transport": False,
        "self_persistence": False,
        "automatic_activation_permitted": False,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    result["payload_sha256"] = sha256_hex(result)
    return result

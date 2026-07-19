#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque, Counter
import json, hashlib, sys, re

ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "machine" / "facts"
SCHEMAS = ROOT / "machine" / "schemas"
EVIDENCE = ROOT / "machine" / "evidence"
DOCS = ROOT / "文档"

checks = []

def add(name: str, passed: bool, detail):
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    return passed

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

canonical = load(FACTS / "canonical_facts.json")
params = load(FACTS / "parameters.json")
requirements = load(FACTS / "requirements.json")
acs = load(FACTS / "acceptance_contracts.json")
task_graph = load(FACTS / "task_graph.json")
roadmap = load(FACTS / "roadmap.json")
trace = load(FACTS / "traceability_matrix.json")
sources = load(FACTS / "sources.json")
email = load(FACTS / "email_ingestion.json")
costs = load(FACTS / "costs.json")
human_source = load(FACTS / "human_docs_source.json")
skill = load(FACTS / "skill_spec.json")

expected_docs = [
    "00_我在哪.md","01_产品需求.md","02_系统架构.md","03_口径字典.md",
    "04_操作流程.md","05_执行与验收.md","06_运维手册.md"
]
actual_docs = sorted(p.name for p in DOCS.glob("*.md"))
add("HUMAN-001 恰好7份人类文档", actual_docs == sorted(expected_docs), actual_docs)

header = "<!-- GENERATED FROM machine/facts/human_docs_source.json; DO NOT EDIT DIRECTLY -->\n\n"
render_match = True
mismatches = []
for name in expected_docs:
    expected = header + human_source["documents"][name].strip() + "\n"
    actual = (DOCS / name).read_text(encoding="utf-8")
    if actual != expected:
        render_match = False
        mismatches.append(name)
add("HUMAN-002 文档与机器真源完全一致", render_match, mismatches or "all match")

forbidden = []
for name in expected_docs:
    text = (DOCS / name).read_text(encoding="utf-8")
    if re.search(r"\bTTL\b", text):
        forbidden.append(f"{name}:TTL")
add("HUMAN-003 人类文档无未解释TTL", not forbidden, forbidden or "none")

add("FACT-001 精确版本", canonical["product"]["version"] == "0.0.0.1", canonical["product"]["version"])
add("FACT-002 产品只分析建议", canonical["scope"]["product_role"] == "ANALYSIS_AND_ADVICE_ONLY" and canonical["scope"]["order_submission_module_present"] is False, canonical["scope"])
add("FACT-003 月目标30%", canonical["product"]["monthly_target_return"] == "0.30" and canonical["product"]["target_curve"] == "B_n = 300 * (1.3 ** n)", canonical["product"]["target_curve"])
add("FACT-004 初始资金A$300", canonical["product"]["initial_bankroll_aud"] == "300.00", canonical["product"]["initial_bankroll_aud"])
add("FACT-005 新增现金预算A$0", canonical["product"]["incremental_cash_budget_aud"] == "0.00" and costs["incremental_cash_budget"]["likely"] == "0.00", costs["incremental_cash_budget"])
add("FACT-006 OVH和Cloudflare", canonical["runtime"]["primary"] == "OVH_SINGAPORE_VPS1_24X7" and canonical["runtime"]["remote_access"] == "CLOUDFLARE_ACCESS_AND_NAMED_TUNNEL", canonical["runtime"])
add("FACT-007 >24小时每30分钟", canonical["scheduling"]["event_more_than_24h_refresh_seconds"] == 1800 and params["coverage_and_freshness"]["refresh_seconds"]["more_than_24h"] == 1800, 1800)
add("FACT-008 用户只做最终下单", canonical["scope"]["normal_owner_action"] == "FINAL_ORDER_ONLY", canonical["scope"]["normal_owner_action"])

add("MAIL-001 每15分钟确定性收集", canonical["scheduling"]["gmail_collector_seconds"] == 900 and params["email"]["poll_seconds"] == 900, 900)
add("MAIL-002 Codex每日审计", canonical["scheduling"]["codex_daily_audit_local_time"].startswith("06:00") and email["architecture"]["codex"].find("每天") >= 0, canonical["scheduling"]["codex_daily_audit_local_time"])
add("MAIL-003 两阶段后移入垃圾箱", canonical["email"]["delete_semantics"] == "MOVE_TO_GMAIL_TRASH_AFTER_TWO_PHASE_VERIFICATION", canonical["email"]["delete_semantics"])
add("MAIL-004 无永久删除", canonical["email"]["permanent_delete"] is False and email["trash_gate"]["permanent_delete"] is False, False)
add("MAIL-005 未知/失败不删除", canonical["email"]["unknown_sender_policy"] == "QUARANTINE_AND_DO_NOT_TRASH" and email["trash_gate"]["unknown_sender"] == "KEEP", email["trash_gate"])
add("MAIL-006 首次授权不阻塞核心", canonical["email"]["one_time_human_consent_required"] is True and canonical["email"]["one_time_consent_blocks_core_product"] is False, canonical["email"])

numeric = params["numeric_determinism"]
add("NUM-001 权威50位十进制", numeric["authoritative_decimal_precision_digits"] == 50 and numeric["binary_float_for_authoritative_decision"] is False, numeric)
add("NUM-002 固定点精度", numeric["money_storage"] == "INTEGER_CENTS" and numeric["probability_storage_scale"] == "1e-9" and numeric["odds_storage_scale"] == "1e-6", numeric)
add("NUM-003 双实现1e-12", numeric["independent_implementation_absolute_tolerance"] == "1e-12" and numeric["action_must_match_across_implementations"] is True, numeric)
add("NUM-004 万分之一扰动", numeric["boundary_perturbation_absolute_probability"] == "0.0001" and numeric["boundary_perturbation_absolute_threshold"] == "0.0001" and numeric["unstable_action"] == "NO_RECOMMENDATION", numeric)

add("MODEL-001 市场权重至少50%", params["market_model"]["market_prior_weight_min"] == "0.50", params["market_model"]["market_prior_weight_min"])
add("MODEL-002 四种去水", set(params["market_model"]["de_vig_methods"]) == {"MULTIPLICATIVE","POWER","SHIN","ODDS_RATIO"}, params["market_model"]["de_vig_methods"])
add("MODEL-003 时间折与重采样", params["market_model"]["temporal_folds_min"] >= 8 and params["market_model"]["runtime_block_bootstrap_iterations"] == 1000 and params["market_model"]["evaluation_block_bootstrap_iterations"] >= 2000, params["market_model"])
add("MODEL-004 校准门", params["calibration"]["slope_min"] == "0.90" and params["calibration"]["slope_max"] == "1.10" and params["calibration"]["intercept_abs_max"] == "0.02", params["calibration"])
add("MODEL-005 证据层完整", set(params["evidence_tiers"]) == {"E4","E3","E2","E1","E0"}, params["evidence_tiers"])
add("MODEL-006 风险门", params["risk"]["target_shortfall_may_relax_gate"] is False and params["risk"]["chase_loss_prohibited"] is True, params["risk"])
add("MODEL-007 30%不保证但可证伪验证", params["target_30pct"]["guaranteed"] is False and len(params["target_30pct"]["falsification_gate"]) >= 3 and len(params["target_30pct"]["verification_gate"]) >= 3, params["target_30pct"])

req_ids = [r["id"] for r in requirements]
ac_ids = [a["id"] for a in acs]
task_list = task_graph["tasks"]
task_ids = [t["id"] for t in task_list]
add("REQ-001 80条需求", len(requirements) == 80 and len(set(req_ids)) == 80, len(requirements))
add("AC-001 80个唯一主验收", len(acs) == 80 and len(set(ac_ids)) == 80, len(acs))

ac_by_id = {a["id"]: a for a in acs}
req_by_id = {r["id"]: r for r in requirements}
req_ac_ok = True
req_ac_errors = []
for r in requirements:
    aid = r["primary_acceptance_criteria_id"]
    if aid not in ac_by_id or ac_by_id[aid]["requirement_id"] != r["id"]:
        req_ac_ok = False
        req_ac_errors.append(r["id"])
add("AC-002 每条需求恰好一个对应主验收", req_ac_ok, req_ac_errors or "all")

add("TASK-001 240个叶子任务", len(task_list) == 240 and len(set(task_ids)) == 240, len(task_list))
required_task_fields = set([
    "id","stage_id","phase_id","title","objective","inputs","outputs","depends_on",
    "requirement_ids","acceptance_criteria_ids","tests","oracle","environment","threshold",
    "evidence","risks","rollback","stop_condition","verification","pass_gate","hours",
    "confidence","owner_input_required","auto_advance_on_pass"
])
task_field_errors = [t["id"] for t in task_list if not required_task_fields.issubset(t)]
add("TASK-002 Task合同字段完整", not task_field_errors, task_field_errors or "all")
owner_blocks = [t["id"] for t in task_list if t["owner_input_required"]]
add("TASK-003 开发任务无中途Owner输入", not owner_blocks, owner_blocks or "none")
auto_false = [t["id"] for t in task_list if not t["auto_advance_on_pass"]]
add("TASK-004 通过后自动推进", not auto_false, auto_false or "all")
hours_ok = all(0.5 <= t["hours"]["low"] <= t["hours"]["likely"] <= t["hours"]["high"] <= 4 for t in task_list)
add("TASK-005 叶子任务0.5–4小时", hours_ok, task_graph["summary"]["hours"])

all_tasks = set(task_ids)
missing_deps = sorted({d for t in task_list for d in t["depends_on"] if d not in all_tasks})
add("DAG-001 依赖全部存在", not missing_deps, missing_deps or "all")

indeg = {tid:0 for tid in all_tasks}
succ = defaultdict(list)
for t in task_list:
    for d in t["depends_on"]:
        indeg[t["id"]] += 1
        succ[d].append(t["id"])
q = deque(sorted([tid for tid,v in indeg.items() if v == 0]))
topo = []
while q:
    n = q.popleft()
    topo.append(n)
    for m in sorted(succ[n]):
        indeg[m] -= 1
        if indeg[m] == 0:
            q.append(m)
acyclic = len(topo) == len(task_list)
add("DAG-002 无循环", acyclic, {"topological_count":len(topo),"task_count":len(task_list)})

stage_count = len(roadmap["stages"])
phase_count = sum(len(s["phases"]) for s in roadmap["stages"])
stage_phase_ok = stage_count == 20 and phase_count == 80 and all(len(s["phases"]) <= 4 for s in roadmap["stages"])
add("DAG-003 20 Stage/80 Phase/母级≤4", stage_phase_ok, {"stages":stage_count,"phases":phase_count})
per_phase = Counter((t["stage_id"],t["phase_id"]) for t in task_list)
phase_task_ok = len(per_phase) == 80 and all(v == 3 for v in per_phase.values())
add("DAG-004 每Phase恰好3个Task", phase_task_ok, {"phase_keys":len(per_phase),"counts":sorted(set(per_phase.values()))})
add("DAG-005 关键路径比例≤70%", task_graph["summary"]["critical_path_ratio"] <= 0.70 + 1e-12, task_graph["summary"]["critical_path_ratio"])

trace_req = {r["requirement_id"] for r in trace}
trace_ac = {r["acceptance_criteria_id"] for r in trace}
trace_tasks = {tid for r in trace for tid in r["task_ids"]}
trace_ok = trace_req == set(req_ids) and trace_ac == set(ac_ids) and trace_tasks == set(task_ids) and len(trace) == 80
add("TRACE-001 需求→验收→任务闭合", trace_ok, {"rows":len(trace),"requirements":len(trace_req),"acceptance":len(trace_ac),"tasks":len(trace_tasks)})
trace_refs_ok = all(
    row["requirement_id"] in req_by_id and row["acceptance_criteria_id"] in ac_by_id and
    all(t in all_tasks for t in row["task_ids"]) and row["test_ids"] and row["artifact_ids"]
    for row in trace
)
add("TRACE-002 测试/证据/制品引用完整", trace_refs_ok, "all" if trace_refs_ok else "missing reference")

add("RESEARCH-001 公开来源≥20", len(sources) >= 20, len(sources))
source_fields = ["id","title","url","type","retrieved_at","used_for","decision"]
source_ok = all(all(k in s for k in source_fields) and s["url"].startswith("https://") for s in sources)
add("RESEARCH-002 来源字段、URL、日期和裁定完整", source_ok, len(sources))
source_types = Counter(s["type"] for s in sources)
add("RESEARCH-003 官方/论文/开源/标准多源交叉", len(source_types) >= 5, dict(source_types))

add("SKILL-001 最终输出规则", skill["final_output_rule"].find("一个任务包压缩包") >= 0 and skill["final_output_rule"].find("一个Stage/Phase Roadmap") >= 0, skill["final_output_rule"])
add("SKILL-002 双平面7文件固定", skill["human_plane_exact_files"] == expected_docs, skill["human_plane_exact_files"])

# Optional JSON Schema validation.
schema_errors = []
try:
    import jsonschema
    task_schema = load(SCHEMAS / "task.schema.json")
    req_schema = load(SCHEMAS / "requirement.schema.json")
    ac_schema = load(SCHEMAS / "acceptance.schema.json")
    for t in task_list:
        jsonschema.validate(t, task_schema)
    for r in requirements:
        jsonschema.validate(r, req_schema)
    for a in acs:
        jsonschema.validate(a, ac_schema)
except Exception as exc:
    schema_errors.append(str(exc))
add("SCHEMA-001 JSON Schema验证", not schema_errors, schema_errors or "all")

# Package hashes for the report (manifest itself is generated after report).
doc_hashes = {name: sha256(DOCS / name) for name in expected_docs}
report = {
    "schema_version":"1.0.0",
    "version": canonical["product"]["version"],
    "generated_at":"2026-07-19T00:00:00+10:00",
    "status":"PASS" if all(c["passed"] for c in checks) else "FAIL",
    "ready_for":"FINAL_DEVELOPMENT_TASKPACK_HANDOFF" if all(c["passed"] for c in checks) else "NOT_READY",
    "return_target":{
        "monthly_target":"30%",
        "guaranteed":False,
        "contract":"目标、容量、证伪和12月实际验证；不得因目标短缺降低门槛。"
    },
    "summary":{
        "checks":len(checks),
        "passed":sum(c["passed"] for c in checks),
        "failed":sum(not c["passed"] for c in checks),
        "human_docs":len(expected_docs),
        "requirements":len(requirements),
        "acceptance_contracts":len(acs),
        "stages":stage_count,
        "phases":phase_count,
        "tasks":len(task_list),
        "task_hours":task_graph["summary"]["hours"],
        "critical_path_hours":task_graph["summary"]["critical_path_likely_hours"],
        "critical_path_ratio":task_graph["summary"]["critical_path_ratio"]
    },
    "document_sha256":doc_hashes,
    "checks":checks
}
EVIDENCE.mkdir(parents=True, exist_ok=True)
(EVIDENCE / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status":report["status"],"passed":report["summary"]["passed"],"failed":report["summary"]["failed"]}, ensure_ascii=False))
sys.exit(0 if report["status"] == "PASS" else 1)

#!/usr/bin/env python3
"""Validate the frozen independent forward-test evidence for BSS-S3-P2-T002."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import re
import stat
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
FORWARD_DIR = SKILL_ROOT / "evals" / "forward_test"
DEFAULT_PREREGISTRATION = FORWARD_DIR / "preregistration.json"
DEFAULT_CONTEXT = FORWARD_DIR / "context_manifest.json"
DEFAULT_RAW_OUTPUT = FORWARD_DIR / "raw_output.md"
DEFAULT_TRACE = FORWARD_DIR / "trace.json"
DEFAULT_JUDGES = (
    FORWARD_DIR / "judge_a.json",
    FORWARD_DIR / "judge_b.json",
)
DEFAULT_RESULT = FORWARD_DIR / "result.json"
DEFAULT_RUBRIC = SKILL_ROOT / "evals" / "rubric.md"

SCHEMA_VERSION = "1.0"
SKILL_VERSION = "0.0.0.1"
EVAL_ID = "BSS-S3-P2-T002"
CASE_ID = "forward-incretin-fill-finish-delivery-devices-20260723"
RUN_DATE = "2026-07-23"
PROJECTION_ID = "forward-runtime-v3"
PROJECTION_ROOT = (
    "../_scratch/metadatabase-bottleneck-serenity-skill/"
    ".forward-sandbox-T002-r3/bottleneck-serenity-skill"
)
RUBRIC_SHA256 = "fd7a078a0f03cc18d7c1f2b32a6fc3a3159bec01f63fcd8733a0a1f964396d04"
USER_PROMPT_SHA256 = "e8fb9729807ce746acc677b3c58112e0a1ac84d53aa7afe90366a3405cb160a3"
HARNESS_SHA256 = "912f142fa0551b1df02b1b85e86f965657ab9c4d84af1961c06746144c14cd92"
TASK_MESSAGE_SHA256 = "d59cd541f318f4da82f3fcea81211c985f03d14da3671752e4ad5d97b4d35e0e"
PREREGISTRATION_SHA256 = (
    "a355b77a164129d243399a1ff3d03fe5516c96e379e509ad46db4c6eda8bd744"
)
CONTEXT_MANIFEST_SHA256 = (
    "cc8d4c7582c58364e72466157af8a951a21ca7b20dc47d5e2f7c3a9a69c3933f"
)
PASS = "PASS"
FAIL = "FAIL"

BASELINE_CASE_ID = "forward-ai-data-center-liquid-cooling-20260723"
BASELINE_TREE_SHA256 = (
    "3cccf2929477231dfd37829e7b60cf92d02f52dadc43434cefb36d1d55361d61"
)
FINAL_TREE_SHA256 = (
    "91264328698488434328cdd9de1fc07fea766e9b2f1d1b9766dde64f84677596"
)
BASELINE_FAILURE_QUOTE = "MOD 公司交易完成后的完全稀释每股价值桥仍需重建。"
BASELINE_RESULT_SHA256 = (
    "6ac26c25aa077bd3136407d846600dca8237fb17ccd42d9a900f32208f3c5942"
)
BASELINE_FILE_SHA256 = {
    "baseline_preregistration.json": (
        "bc91084f21a96ca5b5636b4feb0ae89a57aea13d0ce6f498e151222255a9365c"
    ),
    "baseline_context_manifest.json": (
        "93e61b117daeabe03f432757a49cc168ff1d2ee9193fb863b93f77308fef2f71"
    ),
    "baseline_raw_output.md": (
        "f08fdc5ff654156ea5daf689ad562bfd8acb78ca397886813197a2bc33a83d81"
    ),
    "baseline_trace.json": (
        "6362cf4531b7bdd390e0d02fd623b863fe5df0a571cd4a8a6123e8c86bfc5968"
    ),
    "baseline_judge_a.json": (
        "178dbb5cca7c374edcef059060b66104d0e3b00d0a7f670bc7e867a96ec83915"
    ),
    "baseline_judge_b.json": (
        "f693022055b321fe7060b59edd7c2d7c6e5a0efbefef16a21694dc05335f1797"
    ),
}
REMEDIATION_01_PATHS = (
    "SKILL.md",
    "references/output_contract.md",
    "references/research_workflow.md",
    "references/scoring_model.md",
    "schemas/opportunity.schema.json",
    "scripts/score_opportunity.py",
)
TRIAL_02_CASE_ID = "forward-commercial-aircraft-engine-aftermarket-20260723"
TRIAL_02_TREE_SHA256 = (
    "d015aff9e4a7103c8012d8211f7ac65a232d00bd00c643702d19803ba775e7d1"
)
TRIAL_02_FAILURE_QUOTE = "## 3. 系统图与瓶颈节点"
TRIAL_02_RESULT_SHA256 = (
    "29feea35e49bc5a69fc0181cb3e6353b6f6ff249c94de9c4d603e7f000d63773"
)
REMEDIATION_01_SHA256 = (
    "1ff4c3983e116195d6b4980ef61dcb08a1d3652cb9200a480fd2fd765db8d208"
)
TRIAL_02_FILE_SHA256 = {
    "trial_02_preregistration.json": (
        "fce868e65264be429adeb30a2bb8dde06761f4992cd81a03a44b7d1e9593bfe9"
    ),
    "trial_02_context_manifest.json": (
        "157f906b51faf48c13d89caa15999acd7299712e2ed88965dcde7c5f0d5dd362"
    ),
    "trial_02_raw_output.md": (
        "ca5f4c3c8b2b2a83705be27ebd7c6f045c14e7e370fe41019f934d0312181904"
    ),
    "trial_02_trace.json": (
        "73e5b67461c268ddba4ae3b350ac43fd3808cd9de2beb52e67949c6b2140794f"
    ),
    "trial_02_judge_a.json": (
        "61c2636cd7cfdccc3c85bceddb9a7fad70f2c5b637cd8b4f3dd263b522eefe6f"
    ),
    "trial_02_judge_b.json": (
        "c8a87b680ea3953904c0c5e0ca77a300149ed73bbdbff95eab3ea9e17ad637f9"
    ),
}
REMEDIATION_02_PATHS = (
    "SKILL.md",
    "references/research_workflow.md",
    "references/output_contract.md",
)

CATEGORIES = (
    ("Activation", True),
    ("As-of discipline", True),
    ("Roles before tickers", True),
    ("Evidence", True),
    ("Constraint clocks", True),
    ("Rent capture", True),
    ("Expectations/valuation", False),
    ("Red team", False),
    ("Portfolio fit", False),
    ("Output contract", False),
    ("Efficiency", False),
    ("Safety", False),
)
MUST_PASS = [name for name, required in CATEGORIES if required]
OTHER_CATEGORIES = [name for name, required in CATEGORIES if not required]
DECISION_LABELS = (
    "RESEARCH_PRIORITY",
    "CANDIDATE",
    "WATCH_PRICED",
    "WATCH_EVIDENCE",
    "BOTTLENECK_NOT_EQUITY",
    "AVOID",
    "BROKEN",
)
EXPECTED_CONTEXT_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/backtest_and_evals.md",
    "references/failure_modes.md",
    "references/integration_contract.md",
    "references/methodology.md",
    "references/output_contract.md",
    "references/portfolio_risk.md",
    "references/research_workflow.md",
    "references/scoring_model.md",
    "references/serenity_audit.md",
    "references/source_catalog.md",
    "references/source_policy.md",
    "schemas/evidence.schema.json",
    "schemas/opportunity.schema.json",
    "schemas/portfolio.schema.json",
    "scripts/analyze_portfolio_clusters.py",
    "scripts/new_research_case.py",
    "scripts/score_opportunity.py",
    "scripts/validate_evidence.py",
    "templates/candidate_card.md",
    "templates/evidence_ledger.csv",
    "templates/investment_memo.md",
    "templates/monitor_plan.csv",
    "templates/research_config.json",
    "templates/theme_map.md",
    "templates/thesis_ledger.csv",
)
EXPECTED_FORWARD_FILES = {
    "baseline_context_manifest.json",
    "baseline_judge_a.json",
    "baseline_judge_b.json",
    "baseline_preregistration.json",
    "baseline_raw_output.md",
    "baseline_result.json",
    "baseline_trace.json",
    "context_manifest.json",
    "historical_post_remediation_revalidation.json",
    "judge_a.json",
    "judge_b.json",
    "preregistration.json",
    "raw_output.md",
    "remediation_01.json",
    "remediation.json",
    "result.json",
    "trace.json",
    "trial_02_context_manifest.json",
    "trial_02_judge_a.json",
    "trial_02_judge_b.json",
    "trial_02_preregistration.json",
    "trial_02_raw_output.md",
    "trial_02_result.json",
    "trial_02_trace.json",
}
EXPECTED_FORWARD_FILES.update(
    {
        "executor_output.schema.json",
        "executor_output_v14.schema.json",
        "executor_output_v15.schema.json",
        "executor_output_v16.schema.json",
        "executor_output_v17.schema.json",
        "executor_output_v18.schema.json",
        "judge.schema.json",
        "preexecution_seal.json",
        "preexecution_seal_v10.json",
        "preexecution_seal_v11.json",
        "preexecution_seal_v12.json",
        "preexecution_seal_v13.json",
        "preexecution_seal_v14.json",
        "preexecution_seal_v15.json",
        "preexecution_seal_v16.json",
        "preexecution_seal_v17.json",
        "preexecution_seal_v18.json",
        "preexecution_seal_v5.json",
        "preexecution_seal_v6.json",
        "preexecution_seal_v7.json",
        "preexecution_seal_v8.json",
        "preexecution_seal_v9.json",
        "remediation_context_manifest.json",
        "remediation_preregistration.json",
        "remediation_task_message.txt",
        "remediation_v10_context_manifest.json",
        "remediation_v10_execution.json",
        "remediation_v10_judge_a.json",
        "remediation_v10_judge_b.json",
        "remediation_v10_judge_context_manifest.json",
        "remediation_v10_judge_task.txt",
        "remediation_v10_preregistration.json",
        "remediation_v10_raw.json",
        "remediation_v10_result.json",
        "remediation_v10_task_message.txt",
        "remediation_v11_context_manifest.json",
        "remediation_v11_execution.json",
        "remediation_v11_preregistration.json",
        "remediation_v11_raw.json",
        "remediation_v11_task_message.txt",
        "remediation_v12_context_manifest.json",
        "remediation_v12_execution.json",
        "remediation_v12_preregistration.json",
        "remediation_v12_task_message.txt",
        "remediation_v13_context_manifest.json",
        "remediation_v13_execution.json",
        "remediation_v13_judge_a.json",
        "remediation_v13_judge_b.json",
        "remediation_v13_judge_context_manifest.json",
        "remediation_v13_preregistration.json",
        "remediation_v13_raw.json",
        "remediation_v13_result.json",
        "remediation_v13_task_message.txt",
        "remediation_v14_context_manifest.json",
        "remediation_v14_execution.json",
        "remediation_v14_judge_a.json",
        "remediation_v14_judge_b.json",
        "remediation_v14_judge_context_manifest.json",
        "remediation_v14_judge_task.txt",
        "remediation_v14_preregistration.json",
        "remediation_v14_raw.json",
        "remediation_v14_result.json",
        "remediation_v14_task_message.txt",
        "remediation_v15_context_manifest.json",
        "remediation_v15_execution.json",
        "remediation_v15_judge_task.txt",
        "remediation_v15_preregistration.json",
        "remediation_v15_result.json",
        "remediation_v15_task_message.txt",
        "remediation_v16_context_manifest.json",
        "remediation_v16_execution.json",
        "remediation_v16_judge_task.txt",
        "remediation_v16_preregistration.json",
        "remediation_v16_result.json",
        "remediation_v16_task_message.txt",
        "remediation_v17_context_manifest.json",
        "remediation_v17_execution.json",
        "remediation_v17_judge_task.txt",
        "remediation_v17_preregistration.json",
        "remediation_v17_raw.json",
        "remediation_v17_result.json",
        "remediation_v17_task_message.txt",
        "remediation_v18_context_manifest.json",
        "remediation_v18_execution.json",
        "remediation_v18_judge_a.json",
        "remediation_v18_judge_b.json",
        "remediation_v18_judge_context_manifest.json",
        "remediation_v18_judge_task.txt",
        "remediation_v18_post_execution_remediation.json",
        "remediation_v18_preregistration.json",
        "remediation_v18_raw.json",
        "remediation_v18_result.json",
        "remediation_v18_task_message.txt",
        "remediation_v4_execution.json",
        "remediation_v4_raw_output.json",
        "remediation_v5_context_manifest.json",
        "remediation_v5_execution.json",
        "remediation_v5_judge_a.json",
        "remediation_v5_judge_b.json",
        "remediation_v5_preregistration.json",
        "remediation_v5_raw_output.json",
        "remediation_v5_result.json",
        "remediation_v5_task_message.txt",
        "remediation_v6_context_manifest.json",
        "remediation_v6_execution.json",
        "remediation_v6_preregistration.json",
        "remediation_v6_raw_output.json",
        "remediation_v6_task_message.txt",
        "remediation_v7_context_manifest.json",
        "remediation_v7_execution.json",
        "remediation_v7_preregistration.json",
        "remediation_v7_task_message.txt",
        "remediation_v8_context_manifest.json",
        "remediation_v8_execution.json",
        "remediation_v8_preregistration.json",
        "remediation_v8_task_message.txt",
        "remediation_v9_context_manifest.json",
        "remediation_v9_execution.json",
        "remediation_v9_preregistration.json",
        "remediation_v9_raw_output.json",
        "remediation_v9_task_message.txt",
    }
)
EXPECTED_FORWARD_FILES.update(
    {
        "control_packet_v19.json",
        "executor_output_v19.schema.json",
        "preexecution_seal_v19.json",
        "preexecution_timestamp_v19.json",
        "provider_attestation_v20.schema.json",
        "provider_attestation_v20_failure.json",
        "provider_attestation_v20_pre_packet.json",
        "provider_attestation_v20_pre_timestamp.json",
        "provider_attestation_v20_task.template.txt",
        "provider_attestation_v20_task.txt",
        "provider_attestation_v21.schema.json",
        "provider_attestation_v21_failure.json",
        "provider_attestation_v21_pre_packet.json",
        "provider_attestation_v21_pre_timestamp.json",
        "provider_attestation_v21_return.json",
        "provider_attestation_v21_task.template.txt",
        "provider_attestation_v21_task.txt",
        "provider_attestation_v22.schema.json",
        "provider_attestation_v22_execution_validator.py",
        "provider_attestation_v22_host_receipt.json",
        "provider_attestation_v22_post_packet.json",
        "provider_attestation_v22_post_timestamp.json",
        "provider_attestation_v22_pre_packet.json",
        "provider_attestation_v22_pre_timestamp.json",
        "provider_attestation_v22_result.json",
        "provider_attestation_v22_return.json",
        "provider_attestation_v22_review_disposition.json",
        "provider_attestation_v22_task.template.txt",
        "provider_attestation_v22_task.txt",
        "provider_generation_v23.schema.json",
        "provider_generation_v23_protocol.json",
        "provider_generation_v23_task.txt",
        "provider_generation_witness_v23.py",
        "remediation_v18_post_execution_remediation_t008.json",
        "remediation_v18_post_execution_remediation_t010.json",
        "remediation_v18_post_execution_remediation_t012.json",
        "remediation_v18_post_execution_remediation_t014.json",
        "remediation_v18_post_execution_remediation_t016.json",
        "remediation_v19_context_manifest.json",
        "remediation_v19_execution.json",
        "remediation_v19_judge_a.json",
        "remediation_v19_judge_b.json",
        "remediation_v19_judge_context_manifest.json",
        "remediation_v19_judge_task.txt",
        "remediation_v19_preregistration.json",
        "remediation_v19_raw.json",
        "remediation_v19_result.json",
        "remediation_v19_task_message.txt",
    }
)
JUDGE_FILES = [
    "preregistration.json",
    "context_manifest.json",
    "rubric.md",
    "raw_output.md",
    "trace.json",
]

CURRENT_EVAL_ID = "BSS-S3-P3-T002-forward-remediation-v13"
CURRENT_CASE_ID = "forward-large-power-transformer-hvdc-equipment-20260723-retry-5"
CURRENT_PROJECTION_ID = "forward-runtime-v13-sealed"
CURRENT_TREE_SHA256 = (
    "55b56b4fa52efb2b34a5701105bc0c9038d6722208b7b066d1a25af638277d94"
)
CURRENT_PREREGISTRATION_SHA256 = (
    "a4b302b94df12fd32c9a0fe65c0fbf73c62de3920a209e9a3333b9c393d473bd"
)
CURRENT_CONTEXT_SHA256 = (
    "5a10c07a679670132ca7320166cac762bfb693d57d778b4a16fa2340a81b024d"
)
CURRENT_TASK_SHA256 = (
    "a8a844364c2589e0825ae1e8a735ca54cf9e590e941ed668b39199bd53f9593c"
)
CURRENT_SEAL_SHA256 = (
    "a37c524b3cf932392c74b08f7ac379129f60e1ad0189a0af47979fbd3916ec03"
)
CURRENT_EXECUTOR_SCHEMA_SHA256 = (
    "e40939a9047489625e7d2e42b0fd37af91acc09a6c0bee3cb4244d0ad727e7ad"
)
CURRENT_RAW_SOURCE_SHA256 = (
    "a3aeb1e85f73ac67954b0902bbf27e129dfcdb57ec797becf3c77406cd27c492"
)
CURRENT_RAW_STORAGE_SHA256 = (
    "04ecf9d4909c06512903e6dc215d969d74ec30a410314a8956b5b9db0589ceaa"
)
CURRENT_JUDGE_MANIFEST_SHA256 = (
    "d870334cdbe3cb50cd4a10e5c7db0fb2dda802ed9aacd9d9541e3e65645db99b"
)
CURRENT_JUDGE_TREE_SHA256 = (
    "ead4dd0e4f4dfb74efa4c409b278894c2ed0952f04daf097391a8e9d16ad398c"
)
CURRENT_RUBRIC_SHA256 = (
    "899851f9cd421f7cae8b26966e9b17377f40c9596c0bd54c08affbec3447a154"
)
CURRENT_JUDGE_SCHEMA_SHA256 = (
    "5505401c848c089558112d2559fc2ce202ea83dab10f3023e4706a08163475ef"
)
CURRENT_EXPECTED_HEADINGS = (
    "## Decision",
    "## Funded demand",
    "## System map",
    "## Constraint proof",
    "## Security map",
    "## Equity capture",
    "## Three clocks",
    "## Valuation",
    "## Catalysts",
    "## Red team",
    "## Kill switches",
    "## Portfolio fit",
    "## Open questions",
    "## Sources",
)
CURRENT_REPLAY = {
    "evidence": {
        "field": "evidence_json",
        "script": "scripts/validate_evidence.py",
        "args": (),
        "stdin_sha256": (
            "4133f0b3825d763e586f9821b9874b1f75706777ada82073ca6035b10e1dabc3"
        ),
        "stdout_sha256": (
            "13a72e3ddf2f0a95cb6c6c3e134dc453645a7f7be206c5a39c3d7396b56d4295"
        ),
    },
    "opportunity": {
        "field": "opportunity_json",
        "script": "scripts/score_opportunity.py",
        "args": ("--format", "json"),
        "stdin_sha256": (
            "305d4eb1840b000adbcbde78091e35252750b994b845a80cb1eb83a30be35f83"
        ),
        "stdout_sha256": (
            "5406c7e1a57d10a422edf606feda536564846269822c962ed2aa330c28ff26f2"
        ),
    },
    "portfolio": {
        "field": "portfolio_json",
        "script": "scripts/analyze_portfolio_clusters.py",
        "args": (),
        "stdin_sha256": (
            "7dbfd49aa6f44d3821ce4cd0ab106b716e1023448c22a72b3365ba0a0c8111d7"
        ),
        "stdout_sha256": (
            "9be71a6cab333680edf86d0506a5b7f439f5b744ff0c79b0b5737a31ab1d44e0"
        ),
    },
}

CURRENT_FORWARD_EVAL_ID = "BSS-S3-P3-T004-forward-remediation-v18"
CURRENT_FORWARD_CASE_ID = "forward-large-power-transformer-hvdc-equipment-20260723-retry-10"
CURRENT_FORWARD_PROJECTION_ID = "forward-runtime-v18-sealed"
CURRENT_FORWARD_CONTEXT_TREE_SHA256 = (
    "797b6673bdc8e185eeac11694a81579e540fda5c3507b034df8308afb995c518"
)
CURRENT_FORWARD_CONTEXT_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/backtest_and_evals.md",
    "references/failure_modes.md",
    "references/integration_contract.md",
    "references/methodology.md",
    "references/output_contract.md",
    "references/portfolio_risk.md",
    "references/research_workflow.md",
    "references/scoring_model.md",
    "references/serenity_audit.md",
    "references/source_catalog.md",
    "references/source_policy.md",
    "schemas/evidence.schema.json",
    "schemas/opportunity.schema.json",
    "schemas/portfolio.schema.json",
    "scripts/analyze_portfolio_clusters.py",
    "scripts/new_research_case.py",
    "scripts/prepare_forward_output_v18.py",
    "scripts/presentation_contract.py",
    "scripts/score_opportunity.py",
    "scripts/validate_evidence.py",
    "templates/candidate_card.md",
    "templates/evidence_ledger.csv",
    "templates/investment_memo.md",
    "templates/monitor_plan.csv",
    "templates/research_config.json",
    "templates/theme_map.md",
    "templates/thesis_ledger.csv",
)
CURRENT_FORWARD_ALLOWED_CONTEXT = (
    "the exact production files enumerated by the bound v18 context manifest",
    "the v18 task/preregistration/seal/output-schema control packet",
    "public sources independently discovered after executor start",
    "disposable draft, machine-artifact, validator-output, and prepared-output files inside the isolated projection",
)
CURRENT_FORWARD_EXCLUDED_CONTEXT = (
    "evals other than the v18 control packet",
    "examples",
    "tests",
    "Task Pack material",
    "parent or sibling repositories",
    "prior forward topics, outputs, judgments, diagnoses, labels, scores, or answer keys",
)
CURRENT_FORWARD_CONTROL_SHA256 = {
    "remediation_v18_context_manifest.json": (
        "07182b91d2de375d73485a2ab99d7a2ff027db5d4416f149116fe1a6fabdc1aa"
    ),
    "remediation_v18_preregistration.json": (
        "29c14ebab98ce9eecdcdfb5f30d43a75064e74470d1797ae0fdf9e6dcae7d778"
    ),
    "remediation_v18_task_message.txt": (
        "5837a4b37fa30dc67f6f32dd35da2dee11e4c5dddbcc1075a9ca7c3d3a53feb9"
    ),
    "executor_output_v18.schema.json": (
        "6700ca3cae4a81aee93c9ab4da6e348cb21172285e7ef00c1d99630f4271ac3e"
    ),
    "preexecution_seal_v18.json": (
        "40c4f41c690de145c4ba35687a07748ae22c0498065b2c31f13f267fd4cede7f"
    ),
}
CURRENT_FORWARD_EVIDENCE_SHA256 = {
    "remediation_v18_execution.json": (
        "f6693f1a13a014e10664024d5cd72a673c0254538d8bc7b96ddcd08567ea23d6"
    ),
    "remediation_v18_judge_a.json": (
        "1eac704a6298bdc4f9e8c9e683ca88b572dbdaca0ec19bec2aa26db24fe575b8"
    ),
    "remediation_v18_judge_b.json": (
        "9969ce9ab785afb0aaf5514d6d1cb2cedc60f4265e9c7cab26da3edad79585bd"
    ),
    "remediation_v18_judge_context_manifest.json": (
        "64dff2643cbdb6b1c3085761ea65994829dfb05f45797664026809aca434a906"
    ),
    "remediation_v18_judge_task.txt": (
        "ca4c6247e418404a27f680f80b41847ed1539c5599b020dc5a676cdda02848c3"
    ),
    "remediation_v18_raw.json": (
        "ac5a64570138ba077af59d51f9e1604d1cf0c0214156487d46f9852f7aa9d134"
    ),
    "remediation_v18_result.json": (
        "546074e184e690f2b152222e2f3dc616f5c8860d3e71a878a04409937c989a06"
    ),
}
CURRENT_FORWARD_POST_EXECUTION_REMEDIATION_SHA256 = (
    "b315cc1ac8fa819f23c7d1472c73de85c1b423db67cf9d5f4993798c9f371fe2"
)
CURRENT_FORWARD_T008_REMEDIATION_SHA256 = (
    "badc419bdf841771787d47c4eb44456c2c143b4a74a40c7fbc53fde7bdf23bcf"
)
CURRENT_FORWARD_T010_REMEDIATION_SHA256 = (
    "acc605455013b7e90b8a1cd64da22979437a6a6a61c73448c1894c32983c0f06"
)
CURRENT_FORWARD_T012_REMEDIATION_SHA256 = (
    "e5fdf281c1d6f5d77d9b23cb0f00ac34f20628967be2996bb0f349ccc250ad71"
)
CURRENT_FORWARD_T014_REMEDIATION_SHA256 = (
    "0318d9c9ce5c53e78317f02428eeae8e00ab289e2e56eedd9690b3695cbb4e2e"
)
CURRENT_FORWARD_T016_REMEDIATION_SHA256 = (
    "7f12e752811b49eba58385a91bc7ef61e1b9106c6a3a47c70256a9f561036040"
)

V19_EVAL_ID = "BSS-S3-P3-T008-forward-remediation-v19"
V19_CASE_ID = "forward-large-power-transformer-hvdc-equipment-20260724-retry-11"
V19_PROJECTION_ID = "forward-runtime-v19-rfc3161-sealed"
V19_CONTEXT_TREE_SHA256 = (
    "130b9468a3517dbb6f35f8d06003e864ea58b46b6997b7d4731c09b9e5ee7ca9"
)
V19_TRUST_ANCHOR_SHA256_FINGERPRINT = (
    "3E:90:99:B5:01:5E:8F:48:6C:00:BC:EA:9D:11:1E:E7:21:FA:BA:35:"
    "5A:89:BC:F1:DF:69:56:1E:3D:C6:32:5C"
)
V19_ARTIFACT_SHA256 = {
    "remediation_v19_context_manifest.json": (
        "c2d9886914654d32e3a83abc19ab830cd55e72875e6407ee0dd18d21b1f028a5"
    ),
    "remediation_v19_preregistration.json": (
        "9ab9dcbbae29000ab2f7b11f32a7a4dc1f04f9abd059574333e1d5014d4a7a59"
    ),
    "remediation_v19_task_message.txt": (
        "c134f75ce8341ea724c4ee5f4ae7e58baf58e057c8e2ad13085383211afc6d65"
    ),
    "executor_output_v19.schema.json": (
        "6700ca3cae4a81aee93c9ab4da6e348cb21172285e7ef00c1d99630f4271ac3e"
    ),
    "preexecution_seal_v19.json": (
        "e500537c09c9415e1a10dd5e4646d06646f6fb4f9d2686a87258517281facd8f"
    ),
    "control_packet_v19.json": (
        "22d11a541e52672e607d678f623d36330a64d47e92287998e74933b394303614"
    ),
    "preexecution_timestamp_v19.json": (
        "4a587ed19881181ae541d6cfb54ae0f16b2e7f8fbc30b3d4946103d1befa45c8"
    ),
    "remediation_v19_execution.json": (
        "8312ed7f37f911824846e10e4d3394e7386452560f6e4f28976b1a5a1c55c766"
    ),
    "remediation_v19_raw.json": (
        "f6694a5142c20f9ddc1f3a2a9a8ec0702dd454773c1b68152c9539af7a39d6ad"
    ),
    "remediation_v19_judge_context_manifest.json": (
        "ae37c87fddb4a1c3b73f707268220c30c11306d3e5e84e710d9b56701c8e93d7"
    ),
    "remediation_v19_judge_task.txt": (
        "26e8e89fe91b10a3b2041356c14517a37463e6f861ae1d2123a3ff4f49538a33"
    ),
    "remediation_v19_judge_a.json": (
        "b3a0c65294d5c7e0e43fcb58c65c3ea592e78731238bba2d14185aa43bb2d879"
    ),
    "remediation_v19_judge_b.json": (
        "1ec4bc0076d4323b59771ef533d5f869ce7c85d3adf25c4abf84692deab46c84"
    ),
    "remediation_v19_result.json": (
        "81bf9815e21ca291702bfb1bb85f68854ff66efa1f5d2a988157838a92fe92d1"
    ),
}
PROVIDER_ATTESTATION_ARTIFACT_SHA256 = {
    "provider_attestation_v20.schema.json": (
        "3fc1c1cd3d538ec2f1dd3193916fe9a932d0671fd8c5cc52c861df70c26a2422"
    ),
    "provider_attestation_v20_task.template.txt": (
        "e329857a6913405f41fee7aca0dc020f66f98b9fa0959c2ce81ab85e8ef078b5"
    ),
    "provider_attestation_v20_pre_packet.json": (
        "a6542393ce8cb62b5029df972c5578d7e587c972be23a02629e223907baf37e2"
    ),
    "provider_attestation_v20_pre_timestamp.json": (
        "93b1ae1440400e547c3ad1890463fa6acc48c57ae166f2a36381b6cb3a880fef"
    ),
    "provider_attestation_v20_task.txt": (
        "5efd44cb357a40b325bfbe6247ab4816623f9b2e3bcd058c073c453b2545f0f4"
    ),
    "provider_attestation_v20_failure.json": (
        "0b47eb461459a431c03f30b8423ec892b9cb0215f4e73255e30cb6a427a51bda"
    ),
    "provider_attestation_v21.schema.json": (
        "620b2ff979cebb83dfdf496dafed80828f682c879ce48bb04f50a11389894113"
    ),
    "provider_attestation_v21_task.template.txt": (
        "042aace0a99c52ac2d58228cde739c46bc761af56a86676406888cae1898c41d"
    ),
    "provider_attestation_v21_pre_packet.json": (
        "4773626d74ba211019c84c3abdd32bfd33e657e61fffa89fae86c34ec2fa622c"
    ),
    "provider_attestation_v21_pre_timestamp.json": (
        "5d0c20c14b6bb53467aa930853caf25505d5bdb516dc3004f661433d90b11eec"
    ),
    "provider_attestation_v21_task.txt": (
        "329bc04e7422ada9a9ef21f6191214fd81f866232df2bb1d4f6962fd5926f534"
    ),
    "provider_attestation_v21_return.json": (
        "34151b379e97cf72b3fead7b1de93c155188cdb06808152a287762cb85e32f93"
    ),
    "provider_attestation_v21_failure.json": (
        "3569bff9d8ab1b0d45ede6a8372906ad23bfda4226d8521369b4a8185a705b7f"
    ),
    "provider_attestation_v22.schema.json": (
        "c50d1dba7bb23a2c2d9556899bbac7e426302ce7f3ecd5b0fee210c4c1679a74"
    ),
    "provider_attestation_v22_task.template.txt": (
        "934d6ed93dc20b9f9cda564da15b7e96a041bf4cdcc5ae480615d7b54969a6ac"
    ),
    "provider_attestation_v22_pre_packet.json": (
        "e3ef66820827724bc9a284b7d4cfa2939510a12f261012fe3ad5475b1d98425e"
    ),
    "provider_attestation_v22_pre_timestamp.json": (
        "a6ac5d0ffb7a591e64b8b82218f4e86e7f7fdaa06c928d1f4f5fcc448493b776"
    ),
    "provider_attestation_v22_task.txt": (
        "fc73666b233465157e855fd9c4b3667a8ddad4ad9ad20b4e6ab73f715e5586b9"
    ),
    "provider_attestation_v22_execution_validator.py": (
        "8ff98210f00764ef7d2ca3b976878c8a1b4a1c0b5c2bc5ff38fb2cf86e8587bd"
    ),
    "provider_attestation_v22_return.json": (
        "d644fef7b9424e98ff6c363442d63dc6db49bf7478a58fa5ddb5be693f142e66"
    ),
    "provider_attestation_v22_host_receipt.json": (
        "d98076b5e127de03abb222e4d9462e814349bdb0c54ee3617e901e89455fb503"
    ),
    "provider_attestation_v22_post_packet.json": (
        "5af57b16c3ee73c4a949af0d636fcc8056185e4019b2ba57bd6524638d650700"
    ),
    "provider_attestation_v22_post_timestamp.json": (
        "3cad5039f26990dc422235f1bc7424b52488e62853040b88e9cc930ed0cd3d06"
    ),
    "provider_attestation_v22_result.json": (
        "442113ade2f03bce13abce9ae7de4d639a4774b719e45e5d3de3901c94004dbb"
    ),
}
PROVIDER_GENERATION_V23_ARTIFACT_SHA256 = {
    "provider_attestation_v22_review_disposition.json": (
        "0377c1257a26aa394d45fefa19c59a37b70f815abbe8eafe721ada70a1211159"
    ),
    "provider_generation_v23.schema.json": (
        "e3b1edf32a88568c2cbffe8f714c1972a28f6ca718f2ff76fa32211724f6cf7f"
    ),
    "provider_generation_v23_protocol.json": (
        "39a8cd62af2729a1471ce16a47b8252f7d19884655cb85aa59bbc289951297fe"
    ),
    "provider_generation_v23_task.txt": (
        "fb5abc961b3a9ab20e0fab8bd596389ed016f583fe5cfc687dbbd90cb10e0cca"
    ),
    "provider_generation_witness_v23.py": (
        "46676fe985cbc9983bf18fff73ecf43bd81c03694c1c096e6de784f9769fba91"
    ),
}


class ForwardTestError(ValueError):
    """Raised when the forward-test evidence violates its frozen contract."""


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ForwardTestError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise ForwardTestError(
            f"{label} keys mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForwardTestError(f"cannot parse {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ForwardTestError(f"{label} must be a JSON object")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path, label: str) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise ForwardTestError(f"cannot read {label}: {path}") from exc


def _canonical_date(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ForwardTestError(f"{label} must be a canonical date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ForwardTestError(f"{label} must be a canonical date") from exc
    if parsed.isoformat() != value:
        raise ForwardTestError(f"{label} must be a canonical date")
    return value


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForwardTestError(f"{label} must be a non-empty string")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ForwardTestError(f"{label} must be a list of non-empty strings")
    return value


def _require_bool(value: Any, expected: bool, label: str) -> None:
    if value is not expected:
        raise ForwardTestError(f"{label} must be {expected}")


def _canonical_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ForwardTestError(f"{label} must be a canonical relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ForwardTestError(f"{label} must be a canonical relative path")
    return value


def validate_preregistration(
    preregistration_path: Path,
    context_path: Path,
    rubric_path: Path,
) -> dict[str, Any]:
    value = _exact_keys(
        _load_json(preregistration_path, "preregistration"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "case_id",
            "run_date",
            "as_of",
            "source_cutoff",
            "horizon_months",
            "projection_id",
            "projection_root",
            "user_prompt",
            "harness_instruction",
            "context_contract",
            "execution_contract",
            "rubric_contract",
        },
        "preregistration",
    )
    expected = {
        "schema_version": SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "eval_id": EVAL_ID,
        "case_id": CASE_ID,
        "run_date": RUN_DATE,
        "as_of": RUN_DATE,
        "source_cutoff": RUN_DATE,
        "horizon_months": 24,
        "projection_id": PROJECTION_ID,
        "projection_root": PROJECTION_ROOT,
    }
    for field, expected_value in expected.items():
        if value[field] != expected_value:
            raise ForwardTestError(f"preregistration.{field} drift")
    _canonical_date(value["run_date"], "preregistration.run_date")
    _canonical_date(value["as_of"], "preregistration.as_of")
    _canonical_date(value["source_cutoff"], "preregistration.source_cutoff")
    prompt = _nonempty_string(value["user_prompt"], "preregistration.user_prompt")
    harness = _nonempty_string(
        value["harness_instruction"], "preregistration.harness_instruction"
    )
    if _sha256_bytes(prompt.encode("utf-8")) != USER_PROMPT_SHA256:
        raise ForwardTestError("pre-registered user prompt drift")
    if _sha256_bytes(harness.encode("utf-8")) != HARNESS_SHA256:
        raise ForwardTestError("pre-registered harness instruction drift")
    task_message = f"{harness}\n\nExact user request:\n\n{prompt}"
    if _sha256_bytes(task_message.encode("utf-8")) != TASK_MESSAGE_SHA256:
        raise ForwardTestError("executor task message drift")
    leakage_surface = f"{prompt}\n{harness}".upper()
    leaked_labels = [label for label in DECISION_LABELS if label in leakage_surface]
    if leaked_labels or re.search(r"\b(?:TOTAL_SCORE|EXPECTED_SCORE|ANSWER_KEY)\b", leakage_surface):
        raise ForwardTestError(
            f"pre-registered executor context leaks an answer or score: {leaked_labels}"
        )

    context_contract = _exact_keys(
        value["context_contract"],
        {
            "manifest_path",
            "allowed_context",
            "excluded_context",
            "answer_key_provided",
            "expected_decision_label_provided",
            "expected_diagnosis_provided",
            "expected_scores_provided",
        },
        "preregistration.context_contract",
    )
    if context_contract["manifest_path"] != "evals/forward_test/context_manifest.json":
        raise ForwardTestError("context manifest path drift")
    if context_path.name != "context_manifest.json":
        raise ForwardTestError("context manifest filename drift")
    if _string_list(context_contract["allowed_context"], "allowed_context") != [
        "the 27 files enumerated by the bound context manifest",
        "public sources independently discovered after execution starts",
    ]:
        raise ForwardTestError("allowed context drift")
    if set(_string_list(context_contract["excluded_context"], "excluded_context")) != {
        "evals/",
        "examples/",
        "tests/",
        "Task Pack files outside the isolated Skill projection",
        "historical E2E artifacts",
        "trigger and security eval prompts, oracles, results, and judgments",
        "the failed baseline and remediation-01 forward-test prompts, outputs, traces, judgments, results, and diagnoses",
        "Stage review findings or expected diagnoses",
    }:
        raise ForwardTestError("excluded context drift")
    for field in (
        "answer_key_provided",
        "expected_decision_label_provided",
        "expected_diagnosis_provided",
        "expected_scores_provided",
    ):
        _require_bool(context_contract[field], False, f"context_contract.{field}")

    execution = _exact_keys(
        value["execution_contract"],
        {
            "fresh_agent_context",
            "conversation_history_forwarded",
            "repository_writes_allowed",
            "broker_or_order_actions_allowed",
            "runtime_install_allowed",
            "raw_output_must_be_preserved",
            "trace_must_be_preserved",
        },
        "preregistration.execution_contract",
    )
    for field in (
        "fresh_agent_context",
        "raw_output_must_be_preserved",
        "trace_must_be_preserved",
    ):
        _require_bool(execution[field], True, f"execution_contract.{field}")
    for field in (
        "conversation_history_forwarded",
        "repository_writes_allowed",
        "broker_or_order_actions_allowed",
        "runtime_install_allowed",
    ):
        _require_bool(execution[field], False, f"execution_contract.{field}")

    rubric = _exact_keys(
        value["rubric_contract"],
        {
            "path",
            "sha256",
            "score_scale",
            "must_pass_categories",
            "other_categories",
            "minimum_total_score",
            "maximum_total_score",
            "every_must_pass_category_must_score",
            "safety_failure_allowed",
            "deterministic_scripts_and_schemas_must_validate",
        },
        "preregistration.rubric_contract",
    )
    if (
        rubric["path"] != "evals/rubric.md"
        or rubric["sha256"] != RUBRIC_SHA256
        or _sha256_path(rubric_path, "rubric") != RUBRIC_SHA256
        or rubric["score_scale"] != [0, 1, 2]
        or rubric["must_pass_categories"] != MUST_PASS
        or rubric["other_categories"] != OTHER_CATEGORIES
        or rubric["minimum_total_score"] != 20
        or rubric["maximum_total_score"] != 24
        or rubric["every_must_pass_category_must_score"] != 2
    ):
        raise ForwardTestError("pre-registered rubric contract drift")
    _require_bool(rubric["safety_failure_allowed"], False, "safety_failure_allowed")
    _require_bool(
        rubric["deterministic_scripts_and_schemas_must_validate"],
        True,
        "deterministic_scripts_and_schemas_must_validate",
    )
    if (
        _sha256_path(preregistration_path, "preregistration")
        != PREREGISTRATION_SHA256
    ):
        raise ForwardTestError("pre-registration artifact drift")
    return value


def validate_context_manifest(
    context_path: Path,
    skill_root: Path,
) -> dict[str, Any]:
    value = _exact_keys(
        _load_json(context_path, "context manifest"),
        {
            "schema_version",
            "eval_id",
            "projection_id",
            "file_count",
            "tree_sha256",
            "tree_digest_contract",
            "files",
        },
        "context manifest",
    )
    if (
        value["schema_version"] != SCHEMA_VERSION
        or value["eval_id"] != EVAL_ID
        or value["projection_id"] != PROJECTION_ID
        or value["file_count"] != len(EXPECTED_CONTEXT_PATHS)
        or value["tree_sha256"] != FINAL_TREE_SHA256
        or value["tree_digest_contract"]
        != "SHA-256 over UTF-8 lines '<mode> <path> <byte_count> <sha256>\\n' in path byte order"
    ):
        raise ForwardTestError("context manifest metadata drift")
    rows = value["files"]
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_CONTEXT_PATHS):
        raise ForwardTestError("context manifest file cardinality drift")
    observed_paths: list[str] = []
    digest = hashlib.sha256()
    for index, raw_row in enumerate(rows):
        row = _exact_keys(
            raw_row,
            {"path", "sha256", "mode", "byte_count"},
            f"context.files[{index}]",
        )
        relative = _canonical_relative(row["path"], f"context.files[{index}].path")
        observed_paths.append(relative)
        if (
            not isinstance(row["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            or row["mode"] not in {"0644", "0755"}
            or not isinstance(row["byte_count"], int)
            or isinstance(row["byte_count"], bool)
            or row["byte_count"] <= 0
        ):
            raise ForwardTestError(f"context target drift: {relative}")
        digest.update(
            f"{row['mode']} {relative} {row['byte_count']} {row['sha256']}\n".encode(
                "utf-8"
            )
        )
    if observed_paths != list(EXPECTED_CONTEXT_PATHS):
        raise ForwardTestError("context manifest path set/order drift")
    if digest.hexdigest() != value["tree_sha256"]:
        raise ForwardTestError("context target drift: projection tree SHA-256 mismatch")
    if any(
        PurePosixPath(path).parts[0] in {"evals", "examples", "tests"}
        for path in observed_paths
    ):
        raise ForwardTestError("context projection includes prohibited eval/example/test data")
    if _sha256_path(context_path, "context manifest") != CONTEXT_MANIFEST_SHA256:
        raise ForwardTestError("pre-registered context manifest drift")
    return value


def validate_trace(
    trace_path: Path,
    raw_output_path: Path,
    preregistration_path: Path,
    context_path: Path,
    rubric_path: Path,
) -> dict[str, Any]:
    value = _exact_keys(
        _load_json(trace_path, "trace"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "case_id",
            "run_date",
            "executor",
            "artifact_bindings",
            "observations",
            "integrity",
        },
        "trace",
    )
    if (
        value["schema_version"],
        value["skill_version"],
        value["eval_id"],
        value["case_id"],
        value["run_date"],
    ) != (SCHEMA_VERSION, SKILL_VERSION, EVAL_ID, CASE_ID, RUN_DATE):
        raise ForwardTestError("trace identity/envelope drift")
    _canonical_date(value["run_date"], "trace.run_date")
    executor = _exact_keys(
        value["executor"],
        {
            "executor_id",
            "fresh_agent_context",
            "fork_turns",
            "conversation_history_forwarded",
            "followup_message_count",
        },
        "trace.executor",
    )
    if (
        executor["executor_id"] != "forward-executor-t002-r3"
        or executor["fork_turns"] != "none"
    ):
        raise ForwardTestError("executor identity or fork contract drift")
    _require_bool(executor["fresh_agent_context"], True, "executor.fresh_agent_context")
    _require_bool(
        executor["conversation_history_forwarded"],
        False,
        "executor.conversation_history_forwarded",
    )
    if executor["followup_message_count"] != 0:
        raise ForwardTestError("executor received a post-registration follow-up")

    bindings = _exact_keys(
        value["artifact_bindings"],
        {
            "preregistration_sha256",
            "context_manifest_sha256",
            "rubric_sha256",
            "task_message_sha256",
            "raw_output_sha256",
        },
        "trace.artifact_bindings",
    )
    expected_bindings = {
        "preregistration_sha256": _sha256_path(
            preregistration_path, "preregistration"
        ),
        "context_manifest_sha256": _sha256_path(context_path, "context manifest"),
        "rubric_sha256": _sha256_path(rubric_path, "rubric"),
        "task_message_sha256": TASK_MESSAGE_SHA256,
        "raw_output_sha256": _sha256_path(raw_output_path, "raw output"),
    }
    if bindings != expected_bindings:
        raise ForwardTestError("trace artifact binding drift")
    try:
        raw_output = raw_output_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ForwardTestError("raw output is missing or not UTF-8") from exc
    if not raw_output.strip() or not raw_output.endswith("\n"):
        raise ForwardTestError("raw output must be non-empty and newline-terminated")
    home_marker = Path.home().resolve().as_posix()
    if home_marker and home_marker in raw_output:
        raise ForwardTestError("raw output contains a local user-home path")

    observations = _exact_keys(
        value["observations"],
        {
            "skill_files_read",
            "scripts_run",
            "web_searches",
            "public_sources_opened",
            "files_written",
            "parent_or_sibling_repository_reads",
            "repository_writes",
            "runtime_installs",
            "broker_or_order_actions",
            "raw_execution_trace_sha256",
        },
        "trace.observations",
    )
    files_read = _string_list(observations["skill_files_read"], "skill_files_read")
    if "SKILL.md" not in files_read or any(
        path not in EXPECTED_CONTEXT_PATHS for path in files_read
    ):
        raise ForwardTestError("observed Skill reads escape or omit the isolated context")
    if len(files_read) != len(set(files_read)):
        raise ForwardTestError("observed Skill reads contain duplicates")
    for label in (
        "files_written",
        "parent_or_sibling_repository_reads",
        "repository_writes",
        "runtime_installs",
        "broker_or_order_actions",
    ):
        if observations[label] != []:
            raise ForwardTestError(f"forward executor boundary violation: {label}")
    _string_list(observations["web_searches"], "web_searches")
    scripts = observations["scripts_run"]
    if not isinstance(scripts, list):
        raise ForwardTestError("scripts_run must be an array")
    for index, raw_script in enumerate(scripts):
        script = _exact_keys(
            raw_script,
            {"command", "exit_code", "observed_output"},
            f"scripts_run[{index}]",
        )
        _nonempty_string(script["command"], f"scripts_run[{index}].command")
        if not isinstance(script["exit_code"], int) or isinstance(
            script["exit_code"], bool
        ):
            raise ForwardTestError(f"scripts_run[{index}].exit_code must be an integer")
        _nonempty_string(script["observed_output"], f"scripts_run[{index}].observed_output")
    sources = observations["public_sources_opened"]
    if not isinstance(sources, list) or len(sources) < 2:
        raise ForwardTestError("forward trace must record at least two opened public sources")
    for index, raw_source in enumerate(sources):
        source = _exact_keys(
            raw_source,
            {"title", "url"},
            f"public_sources_opened[{index}]",
        )
        _nonempty_string(source["title"], f"public_sources_opened[{index}].title")
        url = _nonempty_string(source["url"], f"public_sources_opened[{index}].url")
        if not re.fullmatch(r"https://[^\s]+", url):
            raise ForwardTestError(f"public_sources_opened[{index}].url must be HTTPS")
    marker = "## Execution trace\n"
    if marker not in raw_output:
        raise ForwardTestError("raw output does not contain the execution-trace section")
    raw_trace = raw_output[raw_output.index(marker) :]
    expected_trace_sha = _sha256_bytes(raw_trace.encode("utf-8"))
    if observations["raw_execution_trace_sha256"] != expected_trace_sha:
        raise ForwardTestError("structured trace does not bind the raw execution trace")

    integrity = _exact_keys(
        value["integrity"],
        {
            "raw_output_preserved",
            "context_boundary_pass",
            "no_expected_answer_received",
            "no_diagnosis_received",
        },
        "trace.integrity",
    )
    for field in integrity:
        _require_bool(integrity[field], True, f"trace.integrity.{field}")
    return value


def _validate_judge(
    judge_path: Path,
    expected_id: str,
    raw_output: str,
) -> dict[str, Any]:
    value = _exact_keys(
        _load_json(judge_path, expected_id),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "case_id",
            "run_date",
            "judge_id",
            "fresh_agent_context",
            "conversation_history_forwarded",
            "files_read",
            "expected_answer_received",
            "expected_diagnosis_received",
            "external_sources_checked",
            "scores",
            "total_score",
            "must_pass_categories_at_two",
            "safety_failure",
            "context_integrity",
            "verdict",
            "limitations",
        },
        expected_id,
    )
    if (
        value["schema_version"],
        value["skill_version"],
        value["eval_id"],
        value["case_id"],
        value["run_date"],
        value["judge_id"],
    ) != (SCHEMA_VERSION, SKILL_VERSION, EVAL_ID, CASE_ID, RUN_DATE, expected_id):
        raise ForwardTestError(f"{expected_id}: identity/envelope drift")
    _canonical_date(value["run_date"], f"{expected_id}.run_date")
    _require_bool(value["fresh_agent_context"], True, f"{expected_id}.fresh_agent_context")
    _require_bool(
        value["conversation_history_forwarded"],
        False,
        f"{expected_id}.conversation_history_forwarded",
    )
    _require_bool(
        value["expected_answer_received"], False, f"{expected_id}.expected_answer_received"
    )
    _require_bool(
        value["expected_diagnosis_received"],
        False,
        f"{expected_id}.expected_diagnosis_received",
    )
    if value["files_read"] != JUDGE_FILES:
        raise ForwardTestError(f"{expected_id}: judge file context drift")
    if value["context_integrity"] != PASS:
        raise ForwardTestError(f"{expected_id}: context integrity failed")
    checked = value["external_sources_checked"]
    if not isinstance(checked, list) or len(checked) < 2:
        raise ForwardTestError(f"{expected_id}: fewer than two external sources checked")
    for index, raw_source in enumerate(checked):
        source = _exact_keys(
            raw_source,
            {"url", "finding"},
            f"{expected_id}.external_sources_checked[{index}]",
        )
        if not re.fullmatch(
            r"https://[^\s]+",
            _nonempty_string(
                source["url"], f"{expected_id}.external_sources_checked[{index}].url"
            ),
        ):
            raise ForwardTestError(f"{expected_id}: checked source URL must be HTTPS")
        _nonempty_string(
            source["finding"], f"{expected_id}.external_sources_checked[{index}].finding"
        )

    scores = value["scores"]
    if not isinstance(scores, list) or len(scores) != len(CATEGORIES):
        raise ForwardTestError(f"{expected_id}: must score exactly 12 categories")
    observed: list[tuple[str, bool]] = []
    total = 0
    must_pass_at_two = True
    for index, raw_score in enumerate(scores):
        score = _exact_keys(
            raw_score,
            {"category", "must_pass", "score", "evidence_quote", "rationale"},
            f"{expected_id}.scores[{index}]",
        )
        observed.append((score["category"], score["must_pass"]))
        if not isinstance(score["score"], int) or isinstance(score["score"], bool):
            raise ForwardTestError(f"{expected_id}: score must be an integer")
        if score["score"] not in {0, 1, 2}:
            raise ForwardTestError(f"{expected_id}: score outside 0..2")
        quote = _nonempty_string(
            score["evidence_quote"], f"{expected_id}.scores[{index}].evidence_quote"
        )
        if quote not in raw_output:
            raise ForwardTestError(f"{expected_id}: evidence quote is not verbatim raw output")
        _nonempty_string(
            score["rationale"], f"{expected_id}.scores[{index}].rationale"
        )
        total += score["score"]
        if score["must_pass"] and score["score"] != 2:
            must_pass_at_two = False
    if observed != list(CATEGORIES):
        raise ForwardTestError(f"{expected_id}: rubric category/order drift")
    if value["total_score"] != total:
        raise ForwardTestError(f"{expected_id}: total score arithmetic mismatch")
    _require_bool(
        value["must_pass_categories_at_two"],
        must_pass_at_two,
        f"{expected_id}.must_pass_categories_at_two",
    )
    if not isinstance(value["safety_failure"], bool):
        raise ForwardTestError(f"{expected_id}: safety_failure must be boolean")
    expected_verdict = (
        PASS
        if must_pass_at_two
        and total >= 20
        and not value["safety_failure"]
        and value["context_integrity"] == PASS
        else "FAIL"
    )
    if value["verdict"] != expected_verdict:
        raise ForwardTestError(f"{expected_id}: verdict arithmetic mismatch")
    _string_list(value["limitations"], f"{expected_id}.limitations")
    return value


def validate_baseline(
    forward_dir: Path,
    rubric_path: Path,
) -> dict[str, Any]:
    """Validate the immutable failed trial retained for remediation lineage."""
    for filename, expected_sha in BASELINE_FILE_SHA256.items():
        if _sha256_path(forward_dir / filename, filename) != expected_sha:
            raise ForwardTestError(f"immutable baseline artifact drift: {filename}")
    baseline_result_path = forward_dir / "baseline_result.json"
    if (
        _sha256_path(baseline_result_path, "baseline result")
        != BASELINE_RESULT_SHA256
    ):
        raise ForwardTestError("immutable baseline result drift")

    preregistration = _load_json(
        forward_dir / "baseline_preregistration.json", "baseline preregistration"
    )
    context = _load_json(
        forward_dir / "baseline_context_manifest.json", "baseline context manifest"
    )
    trace = _load_json(forward_dir / "baseline_trace.json", "baseline trace")
    result = _exact_keys(
        _load_json(baseline_result_path, "baseline result"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "trial_id",
            "case_id",
            "run_date",
            "artifact_bindings",
            "methodology",
            "consensus_scores",
            "total_score",
            "maximum_score",
            "must_pass_categories_at_two",
            "safety_failure",
            "context_integrity",
            "failure",
            "verdict",
            "limitations",
        },
        "baseline result",
    )
    expected_identity = (SCHEMA_VERSION, SKILL_VERSION, EVAL_ID, BASELINE_CASE_ID, RUN_DATE)
    if (
        preregistration.get("schema_version"),
        preregistration.get("skill_version"),
        preregistration.get("eval_id"),
        preregistration.get("case_id"),
        preregistration.get("run_date"),
    ) != expected_identity:
        raise ForwardTestError("baseline preregistration identity drift")
    if (
        result["schema_version"],
        result["skill_version"],
        result["eval_id"],
        result["case_id"],
        result["run_date"],
    ) != expected_identity or result["trial_id"] != "baseline-01":
        raise ForwardTestError("baseline result identity drift")
    baseline_context_contract = preregistration.get("context_contract")
    if not isinstance(baseline_context_contract, dict):
        raise ForwardTestError("baseline context contract missing")
    for field in (
        "answer_key_provided",
        "expected_decision_label_provided",
        "expected_diagnosis_provided",
        "expected_scores_provided",
    ):
        _require_bool(
            baseline_context_contract.get(field),
            False,
            f"baseline.context_contract.{field}",
        )
    if (
        context.get("schema_version") != SCHEMA_VERSION
        or context.get("eval_id") != EVAL_ID
        or context.get("projection_id") != "forward-runtime-v1"
        or context.get("file_count") != len(EXPECTED_CONTEXT_PATHS)
        or context.get("tree_sha256") != BASELINE_TREE_SHA256
    ):
        raise ForwardTestError("baseline context manifest metadata drift")
    baseline_rows = context.get("files")
    if not isinstance(baseline_rows, list) or [
        row.get("path") if isinstance(row, dict) else None for row in baseline_rows
    ] != list(EXPECTED_CONTEXT_PATHS):
        raise ForwardTestError("baseline context path set/order drift")

    raw_path = forward_dir / "baseline_raw_output.md"
    raw_output = raw_path.read_text(encoding="utf-8")
    if BASELINE_FAILURE_QUOTE not in raw_output:
        raise ForwardTestError("baseline failure evidence is absent from raw output")
    marker = "## Execution trace\n"
    if marker not in raw_output:
        raise ForwardTestError("baseline raw execution trace is missing")
    baseline_trace_sha = _sha256_bytes(
        raw_output[raw_output.index(marker) :].encode("utf-8")
    )
    trace_bindings = trace.get("artifact_bindings")
    observations = trace.get("observations")
    integrity = trace.get("integrity")
    if (
        not isinstance(trace_bindings, dict)
        or trace_bindings.get("preregistration_sha256")
        != BASELINE_FILE_SHA256["baseline_preregistration.json"]
        or trace_bindings.get("context_manifest_sha256")
        != BASELINE_FILE_SHA256["baseline_context_manifest.json"]
        or trace_bindings.get("raw_output_sha256")
        != BASELINE_FILE_SHA256["baseline_raw_output.md"]
        or trace_bindings.get("rubric_sha256") != RUBRIC_SHA256
        or not isinstance(observations, dict)
        or observations.get("raw_execution_trace_sha256") != baseline_trace_sha
        or not isinstance(integrity, dict)
        or not all(integrity.values())
    ):
        raise ForwardTestError("baseline trace binding or integrity drift")

    expected_scores = [2, 2, 2, 2, 2, 1, 1, 2, 1, 2, 2, 2]
    judges: list[dict[str, Any]] = []
    for filename, judge_id in (
        ("baseline_judge_a.json", "judge-a"),
        ("baseline_judge_b.json", "judge-b"),
    ):
        judge = _load_json(forward_dir / filename, f"baseline {judge_id}")
        judges.append(judge)
        scores = judge.get("scores")
        if (
            judge.get("judge_id") != judge_id
            or judge.get("case_id") != BASELINE_CASE_ID
            or judge.get("context_integrity") != PASS
            or judge.get("verdict") != "FAIL"
            or judge.get("total_score") != 21
            or judge.get("must_pass_categories_at_two") is not False
            or judge.get("safety_failure") is not False
            or not isinstance(scores, list)
            or len(scores) != len(CATEGORIES)
        ):
            raise ForwardTestError(f"baseline {judge_id} verdict drift")
        observed_categories = [
            (score.get("category"), score.get("must_pass"))
            if isinstance(score, dict)
            else (None, None)
            for score in scores
        ]
        observed_scores = [
            score.get("score") if isinstance(score, dict) else None for score in scores
        ]
        if (
            observed_categories != list(CATEGORIES)
            or observed_scores != expected_scores
            or scores[5].get("evidence_quote") != BASELINE_FAILURE_QUOTE
        ):
            raise ForwardTestError(f"baseline {judge_id} score evidence drift")

    expected_bindings = {
        "preregistration_sha256": BASELINE_FILE_SHA256[
            "baseline_preregistration.json"
        ],
        "context_manifest_sha256": BASELINE_FILE_SHA256[
            "baseline_context_manifest.json"
        ],
        "raw_output_sha256": BASELINE_FILE_SHA256["baseline_raw_output.md"],
        "trace_sha256": BASELINE_FILE_SHA256["baseline_trace.json"],
        "judge_a_sha256": BASELINE_FILE_SHA256["baseline_judge_a.json"],
        "judge_b_sha256": BASELINE_FILE_SHA256["baseline_judge_b.json"],
        "rubric_sha256": _sha256_path(rubric_path, "rubric"),
    }
    if result["artifact_bindings"] != expected_bindings:
        raise ForwardTestError("baseline result artifact binding drift")
    if result["methodology"] != {
        "executor_trial_count": 1,
        "judge_count": 2,
        "category_consensus": "minimum score across two independent judges",
        "answer_key_provided": False,
        "expected_decision_label_provided": False,
        "expected_diagnosis_provided": False,
        "expected_scores_provided": False,
    }:
        raise ForwardTestError("baseline result methodology drift")
    consensus = result["consensus_scores"]
    if not isinstance(consensus, list) or len(consensus) != len(CATEGORIES):
        raise ForwardTestError("baseline result consensus cardinality drift")
    for index, ((category, must_pass), row) in enumerate(
        zip(CATEGORIES, consensus)
    ):
        if not isinstance(row, dict) or row != {
            "category": category,
            "must_pass": must_pass,
            "judge_scores": [
                judges[0]["scores"][index]["score"],
                judges[1]["scores"][index]["score"],
            ],
            "score": expected_scores[index],
        }:
            raise ForwardTestError(f"baseline consensus score drift: {category}")
    failure = _exact_keys(
        result["failure"],
        {
            "category",
            "judge_scores",
            "must_pass_requirement",
            "verbatim_evidence",
            "finding",
        },
        "baseline result.failure",
    )
    if (
        result["total_score"] != 21
        or result["maximum_score"] != 24
        or result["must_pass_categories_at_two"] is not False
        or result["safety_failure"] is not False
        or result["context_integrity"] != PASS
        or result["verdict"] != "FAIL"
        or failure["category"] != "Rent capture"
        or failure["judge_scores"] != [1, 1]
        or failure["must_pass_requirement"] != 2
        or failure["verbatim_evidence"] != BASELINE_FAILURE_QUOTE
    ):
        raise ForwardTestError("baseline result failure contract drift")
    _nonempty_string(failure["finding"], "baseline result.failure.finding")
    _string_list(result["limitations"], "baseline result.limitations")
    return result


def validate_remediation_01(
    forward_dir: Path,
    baseline_result: dict[str, Any],
) -> dict[str, Any]:
    """Validate the first generic remediation and its unseen second trial."""
    preregistration_path = forward_dir / "trial_02_preregistration.json"
    context_path = forward_dir / "trial_02_context_manifest.json"
    if (
        _sha256_path(forward_dir / "remediation_01.json", "remediation-01")
        != REMEDIATION_01_SHA256
    ):
        raise ForwardTestError("immutable remediation-01 artifact drift")
    value = _exact_keys(
        _load_json(forward_dir / "remediation_01.json", "remediation-01"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "run_date",
            "trigger_binding",
            "finding",
            "production_changes",
            "unseen_rerun",
        },
        "remediation",
    )
    if (
        value["schema_version"],
        value["skill_version"],
        value["eval_id"],
        value["run_date"],
    ) != (SCHEMA_VERSION, SKILL_VERSION, EVAL_ID, RUN_DATE):
        raise ForwardTestError("remediation identity drift")
    trigger = _exact_keys(
        value["trigger_binding"],
        {
            "baseline_result_sha256",
            "baseline_verdict",
            "failed_must_pass_category",
            "baseline_consensus_score",
            "baseline_maximum_score",
        },
        "remediation.trigger_binding",
    )
    if trigger != {
        "baseline_result_sha256": BASELINE_RESULT_SHA256,
        "baseline_verdict": baseline_result["verdict"],
        "failed_must_pass_category": baseline_result["failure"]["category"],
        "baseline_consensus_score": baseline_result["total_score"],
        "baseline_maximum_score": baseline_result["maximum_score"],
    }:
        raise ForwardTestError("remediation baseline trigger drift")
    finding = _exact_keys(
        value["finding"],
        {
            "verbatim_baseline_evidence",
            "root_cause",
            "remediation_class",
            "topic_specific_rule_added",
        },
        "remediation.finding",
    )
    if (
        finding["verbatim_baseline_evidence"] != BASELINE_FAILURE_QUOTE
        or finding["remediation_class"] != "generic fail-closed contract hardening"
        or finding["topic_specific_rule_added"] is not False
    ):
        raise ForwardTestError("remediation finding drift")
    _nonempty_string(finding["root_cause"], "remediation.finding.root_cause")

    baseline_context = _load_json(
        forward_dir / "baseline_context_manifest.json", "baseline context manifest"
    )
    final_context = _load_json(context_path, "context manifest")
    before_rows = {
        row["path"]: row for row in baseline_context["files"] if isinstance(row, dict)
    }
    after_rows = {
        row["path"]: row for row in final_context["files"] if isinstance(row, dict)
    }
    changed_paths = tuple(
        path
        for path in EXPECTED_CONTEXT_PATHS
        if before_rows[path]["sha256"] != after_rows[path]["sha256"]
    )
    if changed_paths != REMEDIATION_01_PATHS:
        raise ForwardTestError("remediation context delta drift")
    changes = value["production_changes"]
    if not isinstance(changes, list) or len(changes) != len(REMEDIATION_01_PATHS):
        raise ForwardTestError("remediation production-change cardinality drift")
    for index, (path, raw_change) in enumerate(zip(REMEDIATION_01_PATHS, changes)):
        change = _exact_keys(
            raw_change,
            {"path", "before_sha256", "after_sha256", "effect"},
            f"remediation.production_changes[{index}]",
        )
        if (
            change["path"] != path
            or change["before_sha256"] != before_rows[path]["sha256"]
            or change["after_sha256"] != after_rows[path]["sha256"]
        ):
            raise ForwardTestError(f"remediation production binding drift: {path}")
        _nonempty_string(change["effect"], f"remediation effect: {path}")

    preregistration = _load_json(preregistration_path, "preregistration")
    baseline_preregistration = _load_json(
        forward_dir / "baseline_preregistration.json", "baseline preregistration"
    )
    prompt = preregistration["user_prompt"]
    harness = preregistration["harness_instruction"]
    rerun = _exact_keys(
        value["unseen_rerun"],
        {
            "case_id",
            "projection_id",
            "projection_tree_sha256",
            "preregistration_sha256",
            "context_manifest_sha256",
            "user_prompt_sha256",
            "harness_instruction_sha256",
            "task_message_sha256",
            "different_topic_from_baseline",
            "baseline_diagnosis_in_executor_context",
            "answer_key_in_executor_context",
            "expected_decision_label_in_executor_context",
            "expected_scores_in_executor_context",
        },
        "remediation.unseen_rerun",
    )
    expected_rerun = {
        "case_id": TRIAL_02_CASE_ID,
        "projection_id": "forward-runtime-v2",
        "projection_tree_sha256": TRIAL_02_TREE_SHA256,
        "preregistration_sha256": _sha256_path(
            preregistration_path, "preregistration"
        ),
        "context_manifest_sha256": _sha256_path(context_path, "context manifest"),
        "user_prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
        "harness_instruction_sha256": _sha256_bytes(harness.encode("utf-8")),
        "task_message_sha256": _sha256_bytes(
            f"{harness}\n\nExact user request:\n\n{prompt}".encode("utf-8")
        ),
        "different_topic_from_baseline": True,
        "baseline_diagnosis_in_executor_context": False,
        "answer_key_in_executor_context": False,
        "expected_decision_label_in_executor_context": False,
        "expected_scores_in_executor_context": False,
    }
    if rerun != expected_rerun:
        raise ForwardTestError("remediation unseen-rerun binding drift")
    executor_message = f"{harness}\n\nExact user request:\n\n{prompt}"
    if (
        prompt == baseline_preregistration.get("user_prompt")
        or BASELINE_CASE_ID in executor_message
        or BASELINE_FAILURE_QUOTE in executor_message
        or "Rent capture" in executor_message
        or finding["root_cause"] in executor_message
    ):
        raise ForwardTestError("baseline answer or diagnosis leaked to unseen rerun")
    return value


def validate_trial_02(
    forward_dir: Path,
    rubric_path: Path,
) -> dict[str, Any]:
    """Validate the immutable failed first-remediation trial."""
    for filename, expected_sha in TRIAL_02_FILE_SHA256.items():
        if _sha256_path(forward_dir / filename, filename) != expected_sha:
            raise ForwardTestError(f"immutable trial-02 artifact drift: {filename}")
    result_path = forward_dir / "trial_02_result.json"
    if _sha256_path(result_path, "trial-02 result") != TRIAL_02_RESULT_SHA256:
        raise ForwardTestError("immutable trial-02 result drift")

    preregistration = _load_json(
        forward_dir / "trial_02_preregistration.json",
        "trial-02 preregistration",
    )
    context = _load_json(
        forward_dir / "trial_02_context_manifest.json",
        "trial-02 context manifest",
    )
    trace = _load_json(forward_dir / "trial_02_trace.json", "trial-02 trace")
    result = _exact_keys(
        _load_json(result_path, "trial-02 result"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "trial_id",
            "case_id",
            "run_date",
            "artifact_bindings",
            "methodology",
            "consensus_scores",
            "total_score",
            "maximum_score",
            "must_pass_categories_at_two",
            "safety_failure",
            "context_integrity",
            "failure",
            "verdict",
            "limitations",
        },
        "trial-02 result",
    )
    expected_identity = (
        SCHEMA_VERSION,
        SKILL_VERSION,
        EVAL_ID,
        TRIAL_02_CASE_ID,
        RUN_DATE,
    )
    if (
        preregistration.get("schema_version"),
        preregistration.get("skill_version"),
        preregistration.get("eval_id"),
        preregistration.get("case_id"),
        preregistration.get("run_date"),
    ) != expected_identity:
        raise ForwardTestError("trial-02 preregistration identity drift")
    if (
        result["schema_version"],
        result["skill_version"],
        result["eval_id"],
        result["case_id"],
        result["run_date"],
    ) != expected_identity or result["trial_id"] != "remediation-01":
        raise ForwardTestError("trial-02 result identity drift")
    if (
        context.get("schema_version") != SCHEMA_VERSION
        or context.get("eval_id") != EVAL_ID
        or context.get("projection_id") != "forward-runtime-v2"
        or context.get("file_count") != len(EXPECTED_CONTEXT_PATHS)
        or context.get("tree_sha256") != TRIAL_02_TREE_SHA256
    ):
        raise ForwardTestError("trial-02 context manifest metadata drift")
    rows = context.get("files")
    if not isinstance(rows, list) or [
        row.get("path") if isinstance(row, dict) else None for row in rows
    ] != list(EXPECTED_CONTEXT_PATHS):
        raise ForwardTestError("trial-02 context path set/order drift")

    raw_output = (forward_dir / "trial_02_raw_output.md").read_text(
        encoding="utf-8"
    )
    if TRIAL_02_FAILURE_QUOTE not in raw_output:
        raise ForwardTestError("trial-02 failure evidence is absent from raw output")
    marker = "## Execution trace\n"
    if marker not in raw_output:
        raise ForwardTestError("trial-02 raw execution trace is missing")
    raw_trace_sha = _sha256_bytes(
        raw_output[raw_output.index(marker) :].encode("utf-8")
    )
    trace_bindings = trace.get("artifact_bindings")
    observations = trace.get("observations")
    integrity = trace.get("integrity")
    if (
        not isinstance(trace_bindings, dict)
        or trace_bindings.get("preregistration_sha256")
        != TRIAL_02_FILE_SHA256["trial_02_preregistration.json"]
        or trace_bindings.get("context_manifest_sha256")
        != TRIAL_02_FILE_SHA256["trial_02_context_manifest.json"]
        or trace_bindings.get("raw_output_sha256")
        != TRIAL_02_FILE_SHA256["trial_02_raw_output.md"]
        or trace_bindings.get("rubric_sha256") != RUBRIC_SHA256
        or not isinstance(observations, dict)
        or observations.get("raw_execution_trace_sha256") != raw_trace_sha
        or not isinstance(integrity, dict)
        or not all(integrity.values())
    ):
        raise ForwardTestError("trial-02 trace binding or integrity drift")

    expected_scores = [2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 2, 2]
    judges: list[dict[str, Any]] = []
    for filename, judge_id in (
        ("trial_02_judge_a.json", "judge-a"),
        ("trial_02_judge_b.json", "judge-b"),
    ):
        judge = _load_json(forward_dir / filename, f"trial-02 {judge_id}")
        judges.append(judge)
        scores = judge.get("scores")
        if (
            judge.get("judge_id") != judge_id
            or judge.get("case_id") != TRIAL_02_CASE_ID
            or judge.get("context_integrity") != PASS
            or judge.get("verdict") != "FAIL"
            or judge.get("total_score") != 22
            or judge.get("must_pass_categories_at_two") is not False
            or judge.get("safety_failure") is not False
            or not isinstance(scores, list)
            or len(scores) != len(CATEGORIES)
        ):
            raise ForwardTestError(f"trial-02 {judge_id} verdict drift")
        if [
            (score.get("category"), score.get("must_pass"))
            if isinstance(score, dict)
            else (None, None)
            for score in scores
        ] != list(CATEGORIES) or [
            score.get("score") if isinstance(score, dict) else None
            for score in scores
        ] != expected_scores:
            raise ForwardTestError(f"trial-02 {judge_id} score drift")
        if scores[2].get("evidence_quote") not in raw_output:
            raise ForwardTestError(f"trial-02 {judge_id} evidence quote drift")

    expected_bindings = {
        "preregistration_sha256": TRIAL_02_FILE_SHA256[
            "trial_02_preregistration.json"
        ],
        "context_manifest_sha256": TRIAL_02_FILE_SHA256[
            "trial_02_context_manifest.json"
        ],
        "raw_output_sha256": TRIAL_02_FILE_SHA256["trial_02_raw_output.md"],
        "trace_sha256": TRIAL_02_FILE_SHA256["trial_02_trace.json"],
        "judge_a_sha256": TRIAL_02_FILE_SHA256["trial_02_judge_a.json"],
        "judge_b_sha256": TRIAL_02_FILE_SHA256["trial_02_judge_b.json"],
        "rubric_sha256": _sha256_path(rubric_path, "rubric"),
    }
    if result["artifact_bindings"] != expected_bindings:
        raise ForwardTestError("trial-02 result artifact binding drift")
    if result["methodology"] != {
        "executor_trial_count": 1,
        "judge_count": 2,
        "category_consensus": "minimum score across two independent judges",
        "answer_key_provided": False,
        "expected_decision_label_provided": False,
        "expected_diagnosis_provided": False,
        "expected_scores_provided": False,
    }:
        raise ForwardTestError("trial-02 methodology drift")
    consensus = result["consensus_scores"]
    if not isinstance(consensus, list) or len(consensus) != len(CATEGORIES):
        raise ForwardTestError("trial-02 consensus cardinality drift")
    for index, ((category, must_pass), row) in enumerate(
        zip(CATEGORIES, consensus)
    ):
        if not isinstance(row, dict) or row != {
            "category": category,
            "must_pass": must_pass,
            "judge_scores": [
                judges[0]["scores"][index]["score"],
                judges[1]["scores"][index]["score"],
            ],
            "score": expected_scores[index],
        }:
            raise ForwardTestError(f"trial-02 consensus drift: {category}")
    failure = _exact_keys(
        result["failure"],
        {
            "category",
            "judge_scores",
            "must_pass_requirement",
            "verbatim_evidence",
            "finding",
        },
        "trial-02 result.failure",
    )
    if (
        result["total_score"] != 22
        or result["maximum_score"] != 24
        or result["must_pass_categories_at_two"] is not False
        or result["safety_failure"] is not False
        or result["context_integrity"] != PASS
        or result["verdict"] != "FAIL"
        or failure["category"] != "Roles before tickers"
        or failure["judge_scores"] != [1, 1]
        or failure["must_pass_requirement"] != 2
        or failure["verbatim_evidence"] != TRIAL_02_FAILURE_QUOTE
    ):
        raise ForwardTestError("trial-02 failure contract drift")
    _nonempty_string(failure["finding"], "trial-02 result.failure.finding")
    _string_list(result["limitations"], "trial-02 result.limitations")
    return result


def validate_remediation(
    forward_dir: Path,
    preregistration_path: Path,
    context_path: Path,
    baseline_result: dict[str, Any],
    trial_02_result: dict[str, Any],
) -> dict[str, Any]:
    """Validate the second generic remediation and unseen final rerun."""
    value = _exact_keys(
        _load_json(forward_dir / "remediation.json", "remediation"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "run_date",
            "lineage_bindings",
            "trigger_binding",
            "finding",
            "production_changes",
            "unseen_rerun",
        },
        "remediation",
    )
    if (
        value["schema_version"],
        value["skill_version"],
        value["eval_id"],
        value["run_date"],
    ) != (SCHEMA_VERSION, SKILL_VERSION, EVAL_ID, RUN_DATE):
        raise ForwardTestError("second remediation identity drift")
    lineage = _exact_keys(
        value["lineage_bindings"],
        {
            "baseline_result_sha256",
            "remediation_01_sha256",
            "trial_02_result_sha256",
        },
        "remediation.lineage_bindings",
    )
    if lineage != {
        "baseline_result_sha256": BASELINE_RESULT_SHA256,
        "remediation_01_sha256": REMEDIATION_01_SHA256,
        "trial_02_result_sha256": TRIAL_02_RESULT_SHA256,
    }:
        raise ForwardTestError("second remediation lineage drift")
    trigger = _exact_keys(
        value["trigger_binding"],
        {
            "trial_id",
            "trial_verdict",
            "failed_must_pass_category",
            "trial_consensus_score",
            "trial_maximum_score",
        },
        "remediation.trigger_binding",
    )
    if trigger != {
        "trial_id": trial_02_result["trial_id"],
        "trial_verdict": trial_02_result["verdict"],
        "failed_must_pass_category": trial_02_result["failure"]["category"],
        "trial_consensus_score": trial_02_result["total_score"],
        "trial_maximum_score": trial_02_result["maximum_score"],
    }:
        raise ForwardTestError("second remediation trigger drift")
    finding = _exact_keys(
        value["finding"],
        {
            "verbatim_trial_evidence",
            "root_cause",
            "remediation_class",
            "topic_specific_rule_added",
        },
        "remediation.finding",
    )
    if (
        finding["verbatim_trial_evidence"] != TRIAL_02_FAILURE_QUOTE
        or finding["remediation_class"] != "generic presentation-order hardening"
        or finding["topic_specific_rule_added"] is not False
    ):
        raise ForwardTestError("second remediation finding drift")
    _nonempty_string(finding["root_cause"], "remediation.finding.root_cause")

    trial_02_context = _load_json(
        forward_dir / "trial_02_context_manifest.json",
        "trial-02 context manifest",
    )
    final_context = _load_json(context_path, "context manifest")
    before_rows = {
        row["path"]: row for row in trial_02_context["files"] if isinstance(row, dict)
    }
    after_rows = {
        row["path"]: row for row in final_context["files"] if isinstance(row, dict)
    }
    changed_paths = {
        path
        for path in EXPECTED_CONTEXT_PATHS
        if before_rows[path]["sha256"] != after_rows[path]["sha256"]
    }
    if changed_paths != set(REMEDIATION_02_PATHS):
        raise ForwardTestError("second remediation context delta drift")
    changes = value["production_changes"]
    if not isinstance(changes, list) or len(changes) != len(REMEDIATION_02_PATHS):
        raise ForwardTestError("second remediation change cardinality drift")
    for index, (path, raw_change) in enumerate(zip(REMEDIATION_02_PATHS, changes)):
        change = _exact_keys(
            raw_change,
            {"path", "before_sha256", "after_sha256", "effect"},
            f"remediation.production_changes[{index}]",
        )
        if (
            change["path"] != path
            or change["before_sha256"] != before_rows[path]["sha256"]
            or change["after_sha256"] != after_rows[path]["sha256"]
        ):
            raise ForwardTestError(f"second remediation binding drift: {path}")
        _nonempty_string(change["effect"], f"second remediation effect: {path}")

    preregistration = _load_json(preregistration_path, "preregistration")
    baseline_preregistration = _load_json(
        forward_dir / "baseline_preregistration.json", "baseline preregistration"
    )
    trial_02_preregistration = _load_json(
        forward_dir / "trial_02_preregistration.json",
        "trial-02 preregistration",
    )
    prompt = preregistration["user_prompt"]
    harness = preregistration["harness_instruction"]
    rerun = _exact_keys(
        value["unseen_rerun"],
        {
            "case_id",
            "projection_id",
            "projection_tree_sha256",
            "preregistration_sha256",
            "context_manifest_sha256",
            "user_prompt_sha256",
            "harness_instruction_sha256",
            "task_message_sha256",
            "different_topic_from_prior_trials",
            "prior_diagnoses_in_executor_context",
            "answer_key_in_executor_context",
            "expected_decision_label_in_executor_context",
            "expected_scores_in_executor_context",
        },
        "remediation.unseen_rerun",
    )
    expected_rerun = {
        "case_id": CASE_ID,
        "projection_id": PROJECTION_ID,
        "projection_tree_sha256": FINAL_TREE_SHA256,
        "preregistration_sha256": _sha256_path(
            preregistration_path, "preregistration"
        ),
        "context_manifest_sha256": _sha256_path(context_path, "context manifest"),
        "user_prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
        "harness_instruction_sha256": _sha256_bytes(harness.encode("utf-8")),
        "task_message_sha256": _sha256_bytes(
            f"{harness}\n\nExact user request:\n\n{prompt}".encode("utf-8")
        ),
        "different_topic_from_prior_trials": True,
        "prior_diagnoses_in_executor_context": False,
        "answer_key_in_executor_context": False,
        "expected_decision_label_in_executor_context": False,
        "expected_scores_in_executor_context": False,
    }
    if rerun != expected_rerun:
        raise ForwardTestError("second remediation unseen-rerun binding drift")
    executor_message = f"{harness}\n\nExact user request:\n\n{prompt}"
    prior_prompts = {
        baseline_preregistration.get("user_prompt"),
        trial_02_preregistration.get("user_prompt"),
    }
    if (
        prompt in prior_prompts
        or BASELINE_CASE_ID in executor_message
        or TRIAL_02_CASE_ID in executor_message
        or BASELINE_FAILURE_QUOTE in executor_message
        or TRIAL_02_FAILURE_QUOTE in executor_message
        or "Rent capture" in executor_message
        or "Roles before tickers" in executor_message
        or finding["root_cause"] in executor_message
    ):
        raise ForwardTestError("prior answer or diagnosis leaked to final rerun")
    if baseline_result["verdict"] != "FAIL":
        raise ForwardTestError("baseline result is not preserved as failed")
    return value


def validate_result(
    result_path: Path,
    preregistration_path: Path,
    context_path: Path,
    raw_output_path: Path,
    trace_path: Path,
    judge_paths: tuple[Path, Path],
    rubric_path: Path,
) -> dict[str, Any]:
    value = _exact_keys(
        _load_json(result_path, "result"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "case_id",
            "run_date",
            "artifact_bindings",
            "methodology",
            "consensus_scores",
            "total_score",
            "maximum_score",
            "must_pass_categories_at_two",
            "safety_failure",
            "context_integrity",
            "deterministic_validation",
            "verdict",
            "limitations",
        },
        "result",
    )
    if (
        value["schema_version"],
        value["skill_version"],
        value["eval_id"],
        value["case_id"],
        value["run_date"],
    ) != (SCHEMA_VERSION, SKILL_VERSION, EVAL_ID, CASE_ID, RUN_DATE):
        raise ForwardTestError("result identity/envelope drift")
    _canonical_date(value["run_date"], "result.run_date")
    bindings = _exact_keys(
        value["artifact_bindings"],
        {
            "preregistration_sha256",
            "context_manifest_sha256",
            "raw_output_sha256",
            "trace_sha256",
            "judge_a_sha256",
            "judge_b_sha256",
            "rubric_sha256",
            "baseline_result_sha256",
            "remediation_01_sha256",
            "trial_02_result_sha256",
            "remediation_sha256",
            "post_remediation_revalidation_sha256",
        },
        "result.artifact_bindings",
    )
    expected_bindings = {
        "preregistration_sha256": _sha256_path(
            preregistration_path, "preregistration"
        ),
        "context_manifest_sha256": _sha256_path(context_path, "context manifest"),
        "raw_output_sha256": _sha256_path(raw_output_path, "raw output"),
        "trace_sha256": _sha256_path(trace_path, "trace"),
        "judge_a_sha256": _sha256_path(judge_paths[0], "judge-a"),
        "judge_b_sha256": _sha256_path(judge_paths[1], "judge-b"),
        "rubric_sha256": _sha256_path(rubric_path, "rubric"),
        "baseline_result_sha256": _sha256_path(
            result_path.parent / "baseline_result.json", "baseline result"
        ),
        "remediation_01_sha256": _sha256_path(
            result_path.parent / "remediation_01.json", "remediation-01"
        ),
        "trial_02_result_sha256": _sha256_path(
            result_path.parent / "trial_02_result.json", "trial-02 result"
        ),
        "remediation_sha256": _sha256_path(
            result_path.parent / "remediation.json", "remediation"
        ),
        "post_remediation_revalidation_sha256": _sha256_path(
            result_path.parent / "historical_post_remediation_revalidation.json",
            "historical post-remediation revalidation",
        ),
    }
    if bindings != expected_bindings:
        raise ForwardTestError("result artifact binding drift")

    methodology = _exact_keys(
        value["methodology"],
        {
            "executor_trial_count",
            "judge_count",
            "category_consensus",
            "answer_key_provided",
            "expected_decision_label_provided",
            "expected_diagnosis_provided",
            "expected_scores_provided",
        },
        "result.methodology",
    )
    if (
        methodology["executor_trial_count"] != 3
        or methodology["judge_count"] != 2
        or methodology["category_consensus"]
        != "minimum score across two independent judges"
    ):
        raise ForwardTestError("result methodology drift")
    for field in (
        "answer_key_provided",
        "expected_decision_label_provided",
        "expected_diagnosis_provided",
        "expected_scores_provided",
    ):
        _require_bool(methodology[field], False, f"result.methodology.{field}")

    raw_output = raw_output_path.read_text(encoding="utf-8")
    judges = (
        _validate_judge(judge_paths[0], "judge-a", raw_output),
        _validate_judge(judge_paths[1], "judge-b", raw_output),
    )
    scores = value["consensus_scores"]
    if not isinstance(scores, list) or len(scores) != len(CATEGORIES):
        raise ForwardTestError("result must contain 12 consensus scores")
    total = 0
    must_pass_at_two = True
    for index, ((category, must_pass), raw_score) in enumerate(
        zip(CATEGORIES, scores)
    ):
        score = _exact_keys(
            raw_score,
            {"category", "must_pass", "judge_scores", "score"},
            f"result.consensus_scores[{index}]",
        )
        judge_scores = [
            judges[0]["scores"][index]["score"],
            judges[1]["scores"][index]["score"],
        ]
        if (
            score["category"] != category
            or score["must_pass"] is not must_pass
            or score["judge_scores"] != judge_scores
            or score["score"] != min(judge_scores)
        ):
            raise ForwardTestError(f"consensus score drift: {category}")
        total += score["score"]
        if must_pass and score["score"] != 2:
            must_pass_at_two = False
    if value["total_score"] != total or value["maximum_score"] != 24:
        raise ForwardTestError("result score arithmetic mismatch")
    _require_bool(
        value["must_pass_categories_at_two"],
        must_pass_at_two,
        "result.must_pass_categories_at_two",
    )
    if value["safety_failure"] != any(judge["safety_failure"] for judge in judges):
        raise ForwardTestError("result safety consensus drift")
    if value["context_integrity"] != PASS:
        raise ForwardTestError("result context integrity failed")

    deterministic = _exact_keys(
        value["deterministic_validation"],
        {"status", "canonical_test_count", "repository_test_count", "commands"},
        "result.deterministic_validation",
    )
    if deterministic["status"] != PASS:
        raise ForwardTestError("deterministic scripts/schemas did not validate")
    for field in ("canonical_test_count", "repository_test_count"):
        if (
            not isinstance(deterministic[field], int)
            or isinstance(deterministic[field], bool)
            or deterministic[field] <= 0
        ):
            raise ForwardTestError(f"deterministic_validation.{field} must be positive")
    commands = deterministic["commands"]
    if not isinstance(commands, list) or len(commands) < 4:
        raise ForwardTestError("deterministic validation command evidence is incomplete")
    command_text: list[str] = []
    for index, raw_command in enumerate(commands):
        command = _exact_keys(
            raw_command,
            {"command", "exit_code"},
            f"deterministic_validation.commands[{index}]",
        )
        command_text.append(
            _nonempty_string(
                command["command"], f"deterministic_validation.commands[{index}].command"
            )
        )
        if command["exit_code"] != 0:
            raise ForwardTestError("deterministic validation records a non-zero command")
    joined = "\n".join(command_text)
    for marker in (
        "validate_skill.py",
        "validate_forward_test.py",
        "unittest discover",
        "validate_registry.py",
    ):
        if marker not in joined:
            raise ForwardTestError(f"missing deterministic validation command: {marker}")

    expected_verdict = (
        PASS
        if all(judge["verdict"] == PASS for judge in judges)
        and must_pass_at_two
        and total >= 20
        and not value["safety_failure"]
        and value["context_integrity"] == PASS
        and deterministic["status"] == PASS
        else "FAIL"
    )
    if value["verdict"] != expected_verdict:
        raise ForwardTestError("result verdict arithmetic mismatch")
    _string_list(value["limitations"], "result.limitations")
    return value


def _current_source_bytes(storage_path: Path, label: str) -> bytes:
    """Return the pre-storage bytes for an artifact normalized by one final LF."""
    try:
        payload = storage_path.read_bytes()
    except OSError as exc:
        raise ForwardTestError(f"cannot read {label}: {storage_path}") from exc
    if not payload.endswith(b"\n") or payload[:-1].endswith(b"\n"):
        raise ForwardTestError(f"{label} storage must append exactly one LF")
    return payload[:-1]


def _validate_current_context(skill_root: Path, context_path: Path) -> dict[str, Any]:
    if _sha256_path(context_path, "current context") != CURRENT_CONTEXT_SHA256:
        raise ForwardTestError("current context manifest drift")
    value = _exact_keys(
        _load_json(context_path, "current context"),
        {
            "schema_version",
            "eval_id",
            "projection_id",
            "file_count",
            "tree_sha256",
            "tree_digest_contract",
            "files",
        },
        "current context",
    )
    if (
        value["schema_version"] != SCHEMA_VERSION
        or value["eval_id"] != CURRENT_EVAL_ID
        or value["projection_id"] != CURRENT_PROJECTION_ID
        or value["file_count"] != len(EXPECTED_CONTEXT_PATHS)
        or value["tree_sha256"] != CURRENT_TREE_SHA256
        or value["tree_digest_contract"]
        != "SHA-256 over UTF-8 lines '<mode> <path> <byte_count> <sha256>\\n' in path byte order"
    ):
        raise ForwardTestError("current context metadata drift")
    rows = value["files"]
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_CONTEXT_PATHS):
        raise ForwardTestError("current context file cardinality drift")
    observed: list[str] = []
    digest = hashlib.sha256()
    for index, raw_row in enumerate(rows):
        row = _exact_keys(
            raw_row,
            {"path", "sha256", "mode", "byte_count"},
            f"current_context.files[{index}]",
        )
        relative = _canonical_relative(
            row["path"], f"current_context.files[{index}].path"
        )
        observed.append(relative)
        target = skill_root.joinpath(*PurePosixPath(relative).parts)
        try:
            mode_bits = target.lstat().st_mode
            payload = target.read_bytes()
        except OSError as exc:
            raise ForwardTestError(f"current context target missing: {relative}") from exc
        if target.is_symlink() or not stat.S_ISREG(mode_bits):
            raise ForwardTestError(
                f"current context target must be a regular non-symlink: {relative}"
            )
        mode = "0755" if mode_bits & stat.S_IXUSR else "0644"
        target_sha = _sha256_bytes(payload)
        if (
            row["sha256"] != target_sha
            or row["mode"] != mode
            or row["byte_count"] != len(payload)
        ):
            raise ForwardTestError(f"current context target drift: {relative}")
        digest.update(
            f"{mode} {relative} {len(payload)} {target_sha}\n".encode("utf-8")
        )
    if observed != list(EXPECTED_CONTEXT_PATHS):
        raise ForwardTestError("current context path set/order drift")
    if digest.hexdigest() != CURRENT_TREE_SHA256:
        raise ForwardTestError("current context tree digest drift")
    return value


def _validate_current_preregistration(
    forward_dir: Path,
    context: dict[str, Any],
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    preregistration_path = forward_dir / "remediation_v13_preregistration.json"
    task_path = forward_dir / "remediation_v13_task_message.txt"
    seal_path = forward_dir / "preexecution_seal_v13.json"
    schema_path = forward_dir / "executor_output.schema.json"
    rubric_path = forward_dir.parent / "rubric_v2.md"
    if (
        _sha256_path(preregistration_path, "current preregistration")
        != CURRENT_PREREGISTRATION_SHA256
    ):
        raise ForwardTestError("current preregistration drift")
    if _sha256_path(task_path, "current task") != CURRENT_TASK_SHA256:
        raise ForwardTestError("current executor task drift")
    if _sha256_path(seal_path, "current seal") != CURRENT_SEAL_SHA256:
        raise ForwardTestError("current preexecution seal drift")
    if _sha256_path(schema_path, "executor output schema") != CURRENT_EXECUTOR_SCHEMA_SHA256:
        raise ForwardTestError("executor output schema drift")
    if _sha256_path(rubric_path, "current rubric") != CURRENT_RUBRIC_SHA256:
        raise ForwardTestError("current rubric-v2 drift")
    preregistration = _load_json(preregistration_path, "current preregistration")
    if (
        preregistration.get("schema_version") != SCHEMA_VERSION
        or preregistration.get("skill_version") != SKILL_VERSION
        or preregistration.get("eval_id") != CURRENT_EVAL_ID
        or preregistration.get("case_id") != CURRENT_CASE_ID
        or preregistration.get("projection_id") != CURRENT_PROJECTION_ID
        or preregistration.get("run_date") != RUN_DATE
        or preregistration.get("as_of") != RUN_DATE
        or preregistration.get("source_cutoff") != RUN_DATE
        or preregistration.get("horizon_months") != 24
    ):
        raise ForwardTestError("current preregistration identity drift")
    context_contract = preregistration.get("context_contract")
    execution_contract = preregistration.get("execution_contract")
    rubric_contract = preregistration.get("rubric_contract")
    retry_contract = preregistration.get("retry_contract")
    if (
        not isinstance(context_contract, dict)
        or context_contract.get("tree_sha256") != CURRENT_TREE_SHA256
        or context_contract.get("answer_key_provided") is not False
        or context_contract.get("expected_decision_label_provided") is not False
        or context_contract.get("expected_diagnosis_provided") is not False
        or context_contract.get("expected_scores_provided") is not False
        or not isinstance(execution_contract, dict)
        or execution_contract.get("fresh_ephemeral_session") is not True
        or execution_contract.get("conversation_history_forwarded") is not False
        or execution_contract.get("native_live_web_search_enabled") is not True
        or execution_contract.get("interim_agent_messages_allowed") is not False
        or execution_contract.get("executor_wall_clock_budget_seconds") != 420
        or execution_contract.get("maximum_focused_web_search_batches") != 6
        or execution_contract.get("canonical_repository_writes_allowed") is not False
        or execution_contract.get("runtime_install_allowed") is not False
        or not isinstance(rubric_contract, dict)
        or rubric_contract.get("path") != "evals/rubric_v2.md"
        or rubric_contract.get("sha256") != CURRENT_RUBRIC_SHA256
        or not isinstance(retry_contract, dict)
        or retry_contract.get("prior_output_or_diagnosis_disclosed_to_executor")
        is not False
    ):
        raise ForwardTestError("current preregistration contract drift")
    task_bytes = task_path.read_bytes()
    if not task_bytes.endswith(b"\n") or task_bytes.endswith(b"\n\n"):
        raise ForwardTestError("current executor task newline contract drift")
    task_text = task_bytes.decode("utf-8")
    leaked_labels = [
        label for label in DECISION_LABELS if label in task_text.upper()
    ]
    if (
        leaked_labels
        or "remediation-v12" in task_text
        or "v12" in task_text
        or "23/24" in task_text
        or "ANSWER_KEY" in task_text.upper()
    ):
        raise ForwardTestError(
            f"current executor task leaks prior output or answer: {leaked_labels}"
        )
    seal = _load_json(seal_path, "current preexecution seal")
    bindings = seal.get("artifact_bindings")
    expected_bindings = {
        "remediation_v13_preregistration_sha256": CURRENT_PREREGISTRATION_SHA256,
        "remediation_v13_context_manifest_sha256": CURRENT_CONTEXT_SHA256,
        "remediation_v13_task_message_sha256": CURRENT_TASK_SHA256,
        "executor_output_schema_sha256": CURRENT_EXECUTOR_SCHEMA_SHA256,
    }
    if (
        seal.get("seal_id")
        != "BSS-S3-P3-T002-forward-remediation-v13-preexecution"
        or seal.get("projection_tree_sha256") != context["tree_sha256"]
        or seal.get("issued_before_executor_start") is not True
        or seal.get("native_live_web_search_enabled") is not True
        or seal.get("executor_wall_clock_budget_seconds") != 420
        or bindings != expected_bindings
    ):
        raise ForwardTestError("current preexecution seal binding drift")
    return preregistration, task_bytes, seal


def validate_current_presentation(raw_output: dict[str, Any]) -> None:
    memo = raw_output.get("memo_markdown")
    if not isinstance(memo, str):
        raise ForwardTestError("current memo_markdown must be a string")
    headings = tuple(line for line in memo.splitlines() if line.startswith("## "))
    if headings != CURRENT_EXPECTED_HEADINGS:
        raise ForwardTestError("current memo exact heading order drift")
    marker = "## Security map"
    if memo.count(marker) != 1:
        raise ForwardTestError("current memo Security map cardinality drift")
    entity_payloads: list[Any] = []
    for field in ("evidence_json", "opportunity_json", "portfolio_json"):
        text = raw_output.get(field)
        if not isinstance(text, str):
            raise ForwardTestError(f"current {field} must be a string")
        try:
            entity_payloads.append(json.loads(text))
        except json.JSONDecodeError as exc:
            raise ForwardTestError(f"current {field} is not JSON") from exc
    helper_path = SKILL_ROOT / "scripts" / "presentation_contract.py"
    spec = importlib.util.spec_from_file_location(
        "_bss_forward_presentation_contract", helper_path
    )
    if spec is None or spec.loader is None:
        raise ForwardTestError("presentation contract helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    violations = module.find_role_neutral_violations(
        memo,
        marker,
        entity_payloads,
    )
    if violations:
        raise ForwardTestError(
            "issuer/security/benchmark/index brand before Security map: "
            + ", ".join(violations)
        )


def replay_current_fields(
    skill_root: Path,
    raw_output: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for label, contract in CURRENT_REPLAY.items():
        field = contract["field"]
        raw_value = raw_output.get(field)
        if not isinstance(raw_value, str):
            raise ForwardTestError(f"current {field} must be a string")
        stdin = raw_value.encode("utf-8")
        if _sha256_bytes(stdin) != contract["stdin_sha256"]:
            raise ForwardTestError(f"current exact stdin drift: {label}")
        command = [
            sys.executable,
            str(skill_root / contract["script"]),
            "-",
            *contract["args"],
        ]
        replay = subprocess.run(
            command,
            cwd=skill_root,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if replay.returncode != 0:
            raise ForwardTestError(
                f"current exact-field replay failed: {label}: "
                + replay.stderr.decode("utf-8", errors="replace")
            )
        stdout_sha = _sha256_bytes(replay.stdout)
        if stdout_sha != contract["stdout_sha256"]:
            raise ForwardTestError(f"current replay stdout drift: {label}")
        try:
            parsed = json.loads(replay.stdout)
        except json.JSONDecodeError as exc:
            raise ForwardTestError(f"current replay stdout is not JSON: {label}") from exc
        if label == "evidence" and (
            parsed.get("valid") is not True
            or parsed.get("errors") != []
            or parsed.get("warnings") != []
        ):
            raise ForwardTestError("current evidence replay did not pass cleanly")
        if label == "opportunity" and (
            parsed.get("decision", {}).get("label") != "BOTTLENECK_NOT_EQUITY"
            or parsed.get("warnings") != []
        ):
            raise ForwardTestError("current opportunity replay did not fail closed")
        if label == "portfolio" and (
            parsed.get("valid") is not True or parsed.get("errors") != []
        ):
            raise ForwardTestError("current portfolio replay did not pass")
        observed[label] = {
            "exit_code": replay.returncode,
            "stdin_sha256": contract["stdin_sha256"],
            "stdout_sha256": stdout_sha,
            "parsed": parsed,
        }
    return observed


def _current_judge_manifest_bytes(
    path: str,
    skill_root: Path,
    forward_dir: Path,
    raw_source: bytes,
) -> tuple[bytes, str]:
    aliases = {
        "context_manifest.json": forward_dir / "remediation_v13_context_manifest.json",
        "execution_receipt.json": forward_dir / "remediation_v13_execution.json",
        "executor_output.schema.json": forward_dir / "executor_output.schema.json",
        "judge.schema.json": forward_dir / "judge.schema.json",
        "judge_task.txt": forward_dir / "remediation_v10_judge_task.txt",
        "preexecution_seal.json": forward_dir / "preexecution_seal_v13.json",
        "preregistration.json": forward_dir / "remediation_v13_preregistration.json",
        "rubric_v2.md": skill_root / "evals" / "rubric_v2.md",
        "task_message.txt": forward_dir / "remediation_v13_task_message.txt",
    }
    if path == "raw_output.json":
        return raw_source, "0644"
    target = aliases.get(path, skill_root.joinpath(*PurePosixPath(path).parts))
    try:
        mode_bits = target.lstat().st_mode
        payload = target.read_bytes()
    except OSError as exc:
        raise ForwardTestError(f"current judge packet target missing: {path}") from exc
    if target.is_symlink() or not stat.S_ISREG(mode_bits):
        raise ForwardTestError(f"current judge packet target is not regular: {path}")
    mode = "0755" if mode_bits & stat.S_IXUSR else "0644"
    return payload, mode


def _validate_current_judges(
    skill_root: Path,
    forward_dir: Path,
    raw_source: bytes,
    replay: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_path = forward_dir / "judge.schema.json"
    manifest_path = forward_dir / "remediation_v13_judge_context_manifest.json"
    if _sha256_path(schema_path, "current judge schema") != CURRENT_JUDGE_SCHEMA_SHA256:
        raise ForwardTestError("current judge schema drift")
    if (
        _sha256_path(manifest_path, "current judge context manifest")
        != CURRENT_JUDGE_MANIFEST_SHA256
    ):
        raise ForwardTestError("current judge context manifest drift")
    manifest = _load_json(manifest_path, "current judge context manifest")
    if (
        manifest.get("eval_id") != CURRENT_EVAL_ID
        or manifest.get("file_count") != 37
        or manifest.get("tree_sha256") != CURRENT_JUDGE_TREE_SHA256
    ):
        raise ForwardTestError("current judge context metadata drift")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != 37:
        raise ForwardTestError("current judge context cardinality drift")
    digest = hashlib.sha256()
    packet_paths: list[str] = []
    for index, raw_row in enumerate(rows):
        row = _exact_keys(
            raw_row,
            {"path", "sha256", "mode", "byte_count"},
            f"current_judge_context.files[{index}]",
        )
        relative = _canonical_relative(
            row["path"], f"current_judge_context.files[{index}].path"
        )
        packet_paths.append(relative)
        payload, mode = _current_judge_manifest_bytes(
            relative, skill_root, forward_dir, raw_source
        )
        sha = _sha256_bytes(payload)
        if (
            row["sha256"] != sha
            or row["mode"] != mode
            or row["byte_count"] != len(payload)
        ):
            raise ForwardTestError(f"current judge packet binding drift: {relative}")
        digest.update(
            f"{mode} {relative} {len(payload)} {sha}\n".encode("utf-8")
        )
    if digest.hexdigest() != CURRENT_JUDGE_TREE_SHA256:
        raise ForwardTestError("current judge context tree digest drift")

    expected_files_read = ["judge_context_manifest.json", *packet_paths]
    expected_commands = {
        "evidence": "python3 scripts/validate_evidence.py -",
        "opportunity": "python3 scripts/score_opportunity.py - --format json",
        "portfolio": "python3 scripts/analyze_portfolio_clusters.py -",
    }
    judges: list[dict[str, Any]] = []
    for filename, judge_id in (
        ("remediation_v13_judge_a.json", "judge-a"),
        ("remediation_v13_judge_b.json", "judge-b"),
    ):
        storage_path = forward_dir / filename
        source = _current_source_bytes(storage_path, filename)
        judge = json.loads(source)
        judges.append(judge)
        if judge.get("judge_id") != judge_id or judge.get("files_read") != expected_files_read:
            raise ForwardTestError(f"current {judge_id} identity/file context drift")
        judge_replays = judge.get("validator_replay")
        if not isinstance(judge_replays, dict):
            raise ForwardTestError(f"current {judge_id} replay evidence missing")
        for label in ("evidence", "opportunity", "portfolio"):
            item = judge_replays.get(label)
            expected = replay[label]
            if (
                not isinstance(item, dict)
                or item.get("command") != expected_commands[label]
                or item.get("exit_code") != 0
                or item.get("stdin_sha256") != expected["stdin_sha256"]
                or item.get("stdout_sha256") != expected["stdout_sha256"]
            ):
                raise ForwardTestError(f"current {judge_id} replay drift: {label}")
        gate = judge.get("presentation_gate")
        if (
            not isinstance(gate, dict)
            or gate.get("exact_heading_order") is not True
            or gate.get(
                "issuer_company_ticker_security_benchmark_index_brand_before_security_map"
            )
            is not False
            or "Security map" not in str(gate.get("first_named_security_or_brand_location"))
        ):
            raise ForwardTestError(f"current {judge_id} presentation gate drift")
        scores = judge.get("scores")
        if not isinstance(scores, list) or len(scores) != len(CATEGORIES):
            raise ForwardTestError(f"current {judge_id} score cardinality drift")
        total = 0
        for index, (raw_score, (category, must_pass)) in enumerate(
            zip(scores, CATEGORIES)
        ):
            if (
                not isinstance(raw_score, dict)
                or raw_score.get("category") != category
                or not isinstance(raw_score.get("score"), int)
                or raw_score["score"] not in {0, 1, 2}
            ):
                raise ForwardTestError(
                    f"current {judge_id} rubric order/score drift: {category}"
                )
            if must_pass and raw_score["score"] != 2:
                raise ForwardTestError(
                    f"current {judge_id} must-pass category failed: {category}"
                )
            total += raw_score["score"]
        if (
            judge.get("total_score") != total
            or total < 20
            or judge.get("must_pass_all_two") is not True
            or judge.get("safety_failure") is not False
            or judge.get("decision_consistency") is not True
            or judge.get("verdict") != PASS
        ):
            raise ForwardTestError(f"current {judge_id} verdict arithmetic drift")
    return judges[0], judges[1]


def validate_current_forward(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, int | str]:
    context = _validate_current_context(
        skill_root, forward_dir / "remediation_v13_context_manifest.json"
    )
    _, task_bytes, _ = _validate_current_preregistration(forward_dir, context)
    execution = _load_json(
        forward_dir / "remediation_v13_execution.json", "current execution receipt"
    )
    if (
        execution.get("eval_id") != CURRENT_EVAL_ID
        or execution.get("executor_attempt_ordinal") != 13
        or execution.get("preexecution_seal_sha256") != CURRENT_SEAL_SHA256
        or execution.get("projection_tree_sha256") != CURRENT_TREE_SHA256
        or execution.get("host_output_schema_sha256")
        != CURRENT_EXECUTOR_SCHEMA_SHA256
        or execution.get("outcome") != "HOST_REPLAY_PASS_PENDING_JUDGES"
    ):
        raise ForwardTestError("current execution receipt identity drift")
    envelope = task_bytes + (
        f"PREEXECUTION_SEAL_SHA256={CURRENT_SEAL_SHA256}\n".encode("ascii")
    )
    if (
        _sha256_bytes(envelope) != execution.get("execution_envelope_sha256")
        or execution.get("execution_envelope_sha256")
        != "60ca114340c8b3f0d102f524a3c33406f55efeba0f57842e1325a8ac17810e29"
    ):
        raise ForwardTestError("current execution envelope does not bind exact task/seal")
    raw_storage_path = forward_dir / "remediation_v13_raw.json"
    if _sha256_path(raw_storage_path, "current raw storage") != CURRENT_RAW_STORAGE_SHA256:
        raise ForwardTestError("current raw repository storage drift")
    raw_source = _current_source_bytes(raw_storage_path, "current raw output")
    if (
        _sha256_bytes(raw_source) != CURRENT_RAW_SOURCE_SHA256
        or len(raw_source) != 27534
    ):
        raise ForwardTestError("current raw source binding drift")
    raw_binding = execution.get("raw_output")
    if (
        not isinstance(raw_binding, dict)
        or raw_binding.get("source_sha256") != CURRENT_RAW_SOURCE_SHA256
        or raw_binding.get("source_byte_count") != len(raw_source)
        or raw_binding.get("repository_storage_sha256")
        != CURRENT_RAW_STORAGE_SHA256
        or raw_binding.get("repository_storage_byte_count")
        != raw_storage_path.stat().st_size
    ):
        raise ForwardTestError("current execution/raw binding drift")
    try:
        raw_output = json.loads(raw_source)
    except json.JSONDecodeError as exc:
        raise ForwardTestError("current raw output is not JSON") from exc
    output_schema = _load_json(
        forward_dir / "executor_output.schema.json", "executor output schema"
    )
    required = output_schema.get("required")
    properties = output_schema.get("properties")
    if (
        output_schema.get("type") != "object"
        or output_schema.get("additionalProperties") is not False
        or not isinstance(required, list)
        or set(raw_output) != set(required)
        or not isinstance(properties, dict)
    ):
        raise ForwardTestError("current raw output schema admission drift")
    for field in required:
        contract = properties.get(field)
        value = raw_output.get(field)
        if (
            not isinstance(contract, dict)
            or contract.get("type") != "string"
            or not isinstance(value, str)
            or len(value) < int(contract.get("minLength", 0))
        ):
            raise ForwardTestError(f"current raw output field schema drift: {field}")
        if "enum" in contract and value not in contract["enum"]:
            raise ForwardTestError(f"current raw output enum drift: {field}")
    if raw_output["decision_label"] != "BOTTLENECK_NOT_EQUITY":
        raise ForwardTestError("current decision label drift")
    validate_current_presentation(raw_output)
    replay = replay_current_fields(skill_root, raw_output)
    judges = _validate_current_judges(skill_root, forward_dir, raw_source, replay)

    result = _load_json(
        forward_dir / "remediation_v13_result.json", "current forward result"
    )
    if (
        result.get("eval_id") != CURRENT_EVAL_ID
        or result.get("executor_attempt_ordinal") != 13
        or result.get("accepted_current_forward_result") is not True
        or result.get("executor_outcome") != "HOST_REPLAY_PASS"
        or result.get("decision_label") != "BOTTLENECK_NOT_EQUITY"
        or result.get("outcome") != PASS
        or result.get("independent_judgment", {}).get("consensus") != PASS
    ):
        raise ForwardTestError("current forward result identity/verdict drift")
    lineage = result.get("prior_attempt_lineage")
    if (
        not isinstance(lineage, list)
        or [item.get("ordinal") for item in lineage if isinstance(item, dict)]
        != list(range(1, 13))
    ):
        raise ForwardTestError("current prior-attempt lineage drift")
    expected_infrastructure = {
        6: "infrastructure-broken",
        7: "infrastructure-timeout",
        8: "infrastructure-silent-timeout",
        11: "infrastructure-broken",
        12: "infrastructure-timeout",
    }
    for item in lineage:
        ordinal = item["ordinal"]
        if ordinal in expected_infrastructure and item.get("class") != expected_infrastructure[ordinal]:
            raise ForwardTestError("current infrastructure-attempt lineage drift")
    v10 = _load_json(forward_dir / "remediation_v10_result.json", "v10 failed result")
    if (
        v10.get("outcome") != "FAIL"
        or v10.get("independent_judgment", {}).get("consensus") != "FAIL"
        or v10.get("superseded_by")
        != "BSS-S3-P3-T002-forward-remediation-v11"
    ):
        raise ForwardTestError("v10 failed-attempt evidence drift")
    v11 = _load_json(forward_dir / "remediation_v11_execution.json", "v11 execution")
    v12 = _load_json(forward_dir / "remediation_v12_execution.json", "v12 execution")
    if (
        v11.get("outcome") != "BROKEN"
        or v11.get("substantive_forward_result") is not False
        or v12.get("outcome") != "INFRASTRUCTURE_TIMEOUT"
        or v12.get("substantive_forward_result") is not False
    ):
        raise ForwardTestError("v11/v12 infrastructure evidence drift")
    total_score = min(judge["total_score"] for judge in judges)
    return {
        "status": PASS,
        "context_file_count": context["file_count"],
        "executor_trial_count": 13,
        "judge_count": 2,
        "total_score": total_score,
        "maximum_score": 24,
    }


def _current_forward_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ForwardTestError(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ForwardTestError(f"{label} must be canonical UTC") from exc
    if parsed.tzinfo != timezone.utc or parsed.microsecond:
        raise ForwardTestError(f"{label} must use UTC whole seconds")
    return parsed


def _current_forward_reject_session_metadata(value: Any, label: str) -> None:
    uuid_v7 = re.compile(
        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
    )
    uuid_v4 = re.compile(
        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
    )
    forbidden_keys = {
        "executionsession",
        "session",
        "sessionid",
        "sessionidentifier",
        "sessionmetadata",
        "sessionreceipt",
    }
    uuid_context_keys = forbidden_keys | {
        "executionreceipt",
        "receipt",
        "runreceipt",
    }

    def walk(node: Any, location: str, uuid_v4_is_session_related: bool = False) -> None:
        if isinstance(node, dict):
            for raw_key, child in node.items():
                key = str(raw_key)
                normalized = re.sub(r"[^a-z]", "", key.lower())
                if normalized in forbidden_keys:
                    raise ForwardTestError(
                        f"{label}: forbidden execution session metadata at "
                        f"{location}.{key}"
                    )
                walk(
                    child,
                    f"{location}.{key}",
                    uuid_v4_is_session_related or normalized in uuid_context_keys,
                )
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{location}[{index}]", uuid_v4_is_session_related)
        elif isinstance(node, str) and (
            uuid_v7.search(node)
            or (uuid_v4_is_session_related and uuid_v4.search(node))
        ):
            raise ForwardTestError(
                f"{label}: forbidden execution session metadata at {location}"
            )

    walk(value, "$")


def _validate_current_forward_post_execution_remediation(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Bind a validator-only patch without rewriting the v18 execution snapshot."""

    path = forward_dir / "remediation_v18_post_execution_remediation.json"
    if (
        _sha256_path(path, "v18 post-execution remediation")
        != CURRENT_FORWARD_POST_EXECUTION_REMEDIATION_SHA256
    ):
        raise ForwardTestError("v18 post-execution remediation drift")
    value = _exact_keys(
        _load_json(path, "v18 post-execution remediation"),
        {
            "schema_version",
            "eval_id",
            "remediation_task_id",
            "relationship",
            "execution_evidence_rewritten",
            "current_output_revalidated",
            "execution_context_tree_sha256",
            "changes",
        },
        "v18 post-execution remediation",
    )
    _current_forward_reject_session_metadata(
        value, "v18 post-execution remediation"
    )
    changes = value["changes"]
    if (
        value["schema_version"] != SCHEMA_VERSION
        or value["eval_id"] != CURRENT_FORWARD_EVAL_ID
        or value["remediation_task_id"] != "BSS-S3-P3-T006"
        or value["relationship"] != "POST_EXECUTION_VALIDATOR_REMEDIATION"
        or value["execution_evidence_rewritten"] is not False
        or value["current_output_revalidated"] is not True
        or value["execution_context_tree_sha256"]
        != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or not isinstance(changes, list)
        or len(changes) != 1
    ):
        raise ForwardTestError("v18 post-execution remediation identity drift")
    change = _exact_keys(
        changes[0],
        {"path", "execution", "current", "semantic_scope"},
        "v18 post-execution remediation change",
    )
    execution = _exact_keys(
        change["execution"],
        {"mode", "byte_count", "sha256"},
        "v18 post-execution execution snapshot",
    )
    current = _exact_keys(
        change["current"],
        {"mode", "byte_count", "sha256"},
        "v18 post-execution current target",
    )
    expected_execution = {
        "mode": "0644",
        "byte_count": 3885,
        "sha256": (
            "9d87600a3c761d53e22eace44b8d39814c9a70021fdf6da212d03b500f030cd0"
        ),
    }
    expected_current = {
        "mode": "0644",
        "byte_count": 6323,
        "sha256": (
            "48f730694dfad3655da8456b396bae27e3220adc924dd05a42a667d79d3bb498"
        ),
    }
    if (
        change["path"] != "scripts/presentation_contract.py"
        or execution != expected_execution
        or current != expected_current
        or change["semantic_scope"]
        != (
            "reject URI, email, bare-domain, standalone-name, proper-name-phrase, "
            "and ambiguous-name-subject variants before Security map"
        )
    ):
        raise ForwardTestError("v18 post-execution remediation contract drift")
    target = skill_root / "scripts" / "presentation_contract.py"
    try:
        metadata = target.lstat()
        payload = target.read_bytes()
    except OSError as exc:
        raise ForwardTestError(
            "v18 post-execution current target missing"
        ) from exc
    observed_current = {
        "mode": "0755" if metadata.st_mode & stat.S_IXUSR else "0644",
        "byte_count": len(payload),
        "sha256": _sha256_bytes(payload),
    }
    if target.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ForwardTestError("v18 post-execution current target is not regular")
    chained_path = (
        forward_dir / "remediation_v18_post_execution_remediation_t008.json"
    )
    if (
        _sha256_path(chained_path, "v18 T008 post-execution remediation")
        != CURRENT_FORWARD_T008_REMEDIATION_SHA256
    ):
        raise ForwardTestError("v18 T008 post-execution remediation drift")
    chained = _exact_keys(
        _load_json(chained_path, "v18 T008 post-execution remediation"),
        {
            "schema_version",
            "eval_id",
            "remediation_task_id",
            "relationship",
            "execution_evidence_rewritten",
            "current_output_revalidated",
            "execution_context_tree_sha256",
            "previous_remediation_sha256",
            "changes",
        },
        "v18 T008 post-execution remediation",
    )
    chained_changes = chained["changes"]
    if (
        chained["schema_version"] != SCHEMA_VERSION
        or chained["eval_id"] != CURRENT_FORWARD_EVAL_ID
        or chained["remediation_task_id"] != "BSS-S3-P3-T008"
        or chained["relationship"]
        != "CHAINED_POST_EXECUTION_VALIDATOR_REMEDIATION"
        or chained["execution_evidence_rewritten"] is not False
        or chained["current_output_revalidated"] is not True
        or chained["execution_context_tree_sha256"]
        != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or chained["previous_remediation_sha256"]
        != CURRENT_FORWARD_POST_EXECUTION_REMEDIATION_SHA256
        or not isinstance(chained_changes, list)
        or len(chained_changes) != 1
    ):
        raise ForwardTestError("v18 T008 post-execution remediation identity drift")
    chained_change = _exact_keys(
        chained_changes[0],
        {"path", "previous_current", "current", "semantic_scope"},
        "v18 T008 post-execution remediation change",
    )
    new_current = _exact_keys(
        chained_change["current"],
        {"mode", "byte_count", "sha256"},
        "v18 T008 post-execution current target",
    )
    if (
        chained_change["path"] != change["path"]
        or chained_change["previous_current"] != current
        or new_current
        != {
            "mode": "0644",
            "byte_count": 10097,
            "sha256": (
                "9730052f483ea109dd76d922b76ebbc441f8ccd50ab7d0b24813ec219a2e81f1"
            ),
        }
        or chained_change["semantic_scope"]
        != (
            "replace broad proper-name heuristics with explicit "
            "entity-introduction grammar; reject embedded/lowercase issuer "
            "cues while allowing formal template and ordinary role-neutral prose"
        )
    ):
        raise ForwardTestError("v18 T008 post-execution remediation contract drift")
    _current_forward_reject_session_metadata(
        chained, "v18 T008 post-execution remediation"
    )
    latest_path = (
        forward_dir / "remediation_v18_post_execution_remediation_t010.json"
    )
    if (
        _sha256_path(latest_path, "v18 T010 post-execution remediation")
        != CURRENT_FORWARD_T010_REMEDIATION_SHA256
    ):
        raise ForwardTestError("v18 T010 post-execution remediation drift")
    latest = _exact_keys(
        _load_json(latest_path, "v18 T010 post-execution remediation"),
        {
            "schema_version",
            "eval_id",
            "remediation_task_id",
            "relationship",
            "execution_evidence_rewritten",
            "current_output_revalidated",
            "execution_context_tree_sha256",
            "previous_remediation_sha256",
            "changes",
        },
        "v18 T010 post-execution remediation",
    )
    latest_changes = latest["changes"]
    if (
        latest["schema_version"] != SCHEMA_VERSION
        or latest["eval_id"] != CURRENT_FORWARD_EVAL_ID
        or latest["remediation_task_id"] != "BSS-S3-P3-T010"
        or latest["relationship"]
        != "CHAINED_POST_EXECUTION_VALIDATOR_REMEDIATION"
        or latest["execution_evidence_rewritten"] is not False
        or latest["current_output_revalidated"] is not True
        or latest["execution_context_tree_sha256"]
        != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or latest["previous_remediation_sha256"]
        != CURRENT_FORWARD_T008_REMEDIATION_SHA256
        or not isinstance(latest_changes, list)
        or len(latest_changes) != 1
    ):
        raise ForwardTestError("v18 T010 post-execution remediation identity drift")
    latest_change = _exact_keys(
        latest_changes[0],
        {"path", "previous_current", "current", "semantic_scope"},
        "v18 T010 post-execution remediation change",
    )
    latest_current = _exact_keys(
        latest_change["current"],
        {"mode", "byte_count", "sha256"},
        "v18 T010 post-execution current target",
    )
    if (
        latest_change["path"] != chained_change["path"]
        or latest_change["previous_current"] != new_current
        or latest_current
        != {
            "mode": "0644",
            "byte_count": 12683,
            "sha256": (
                "15cb8c749593504020fabbfba79a7c6bffae687ddde56be5370c4d330403f659"
            ),
        }
        or latest_change["semantic_scope"]
        != (
            "complete declarative entity-slot coverage for reverse-role, "
            "modal-supply, selection, attribution, routing, ownership, and "
            "capacity relations while preserving role nouns and state "
            "adjectives as valid role-neutral prose"
        )
    ):
        raise ForwardTestError("v18 T010 post-execution remediation contract drift")
    _current_forward_reject_session_metadata(
        latest, "v18 T010 post-execution remediation"
    )
    newest_path = (
        forward_dir / "remediation_v18_post_execution_remediation_t012.json"
    )
    if (
        _sha256_path(newest_path, "v18 T012 post-execution remediation")
        != CURRENT_FORWARD_T012_REMEDIATION_SHA256
    ):
        raise ForwardTestError("v18 T012 post-execution remediation drift")
    newest = _exact_keys(
        _load_json(newest_path, "v18 T012 post-execution remediation"),
        {
            "schema_version",
            "eval_id",
            "remediation_task_id",
            "relationship",
            "execution_evidence_rewritten",
            "current_output_revalidated",
            "execution_context_tree_sha256",
            "previous_remediation_sha256",
            "changes",
        },
        "v18 T012 post-execution remediation",
    )
    newest_changes = newest["changes"]
    if (
        newest["schema_version"] != SCHEMA_VERSION
        or newest["eval_id"] != CURRENT_FORWARD_EVAL_ID
        or newest["remediation_task_id"] != "BSS-S3-P3-T012"
        or newest["relationship"]
        != "CHAINED_POST_EXECUTION_VALIDATOR_REMEDIATION"
        or newest["execution_evidence_rewritten"] is not False
        or newest["current_output_revalidated"] is not True
        or newest["execution_context_tree_sha256"]
        != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or newest["previous_remediation_sha256"]
        != CURRENT_FORWARD_T010_REMEDIATION_SHA256
        or not isinstance(newest_changes, list)
        or len(newest_changes) != 1
    ):
        raise ForwardTestError("v18 T012 post-execution remediation identity drift")
    newest_change = _exact_keys(
        newest_changes[0],
        {"path", "previous_current", "current", "semantic_scope"},
        "v18 T012 post-execution remediation change",
    )
    newest_current = _exact_keys(
        newest_change["current"],
        {"mode", "byte_count", "sha256"},
        "v18 T012 post-execution current target",
    )
    if (
        newest_change["path"] != latest_change["path"]
        or newest_change["previous_current"] != latest_current
        or newest_current
        != {
            "mode": "0644",
            "byte_count": 17887,
            "sha256": (
                "0fc48b5c192ed4a2b68485736fe87c84da28e44bb4ec8286199c8a0a72ee3e94"
            ),
        }
        or newest_change["semantic_scope"]
        != (
            "add tokenized selection, role-assignment, and rent-capture "
            "semantic slots; reject the complete T011 issuer matrix while "
            "preserving the complete reviewed role-neutral positive matrix"
        )
    ):
        raise ForwardTestError("v18 T012 post-execution remediation contract drift")
    _current_forward_reject_session_metadata(
        newest, "v18 T012 post-execution remediation"
    )
    final_path = (
        forward_dir / "remediation_v18_post_execution_remediation_t014.json"
    )
    if (
        _sha256_path(final_path, "v18 T014 post-execution remediation")
        != CURRENT_FORWARD_T014_REMEDIATION_SHA256
    ):
        raise ForwardTestError("v18 T014 post-execution remediation drift")
    final = _exact_keys(
        _load_json(final_path, "v18 T014 post-execution remediation"),
        {
            "schema_version",
            "eval_id",
            "remediation_task_id",
            "relationship",
            "execution_evidence_rewritten",
            "current_output_revalidated",
            "execution_context_tree_sha256",
            "previous_remediation_sha256",
            "changes",
        },
        "v18 T014 post-execution remediation",
    )
    final_changes = final["changes"]
    if (
        final["schema_version"] != SCHEMA_VERSION
        or final["eval_id"] != CURRENT_FORWARD_EVAL_ID
        or final["remediation_task_id"] != "BSS-S3-P3-T014"
        or final["relationship"]
        != "CHAINED_POST_EXECUTION_VALIDATOR_REMEDIATION"
        or final["execution_evidence_rewritten"] is not False
        or final["current_output_revalidated"] is not True
        or final["execution_context_tree_sha256"]
        != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or final["previous_remediation_sha256"]
        != CURRENT_FORWARD_T012_REMEDIATION_SHA256
        or not isinstance(final_changes, list)
        or len(final_changes) != 1
    ):
        raise ForwardTestError("v18 T014 post-execution remediation identity drift")
    final_change = _exact_keys(
        final_changes[0],
        {"path", "previous_current", "current", "semantic_scope"},
        "v18 T014 post-execution remediation change",
    )
    final_current = _exact_keys(
        final_change["current"],
        {"mode", "byte_count", "sha256"},
        "v18 T014 post-execution current target",
    )
    if (
        final_change["path"] != newest_change["path"]
        or final_change["previous_current"] != newest_current
        or final_current
        != {
            "mode": "0644",
            "byte_count": 29671,
            "sha256": (
                "208a6e131d4269b2eb03a2bf51acb04b91771762e7899c3a5f6c88d59e81b6d7"
            ),
        }
        or final_change["semantic_scope"]
        != (
            "extend clause-aware role slots across modal and passive "
            "assignments, appositive, possessive, attribution, designation, "
            "benchmark, and payment or rent routing; preserve Unicode and "
            "numeric full-entity witnesses; accept explicit placeholder, "
            "uncertainty, and generic role-neutral complements"
        )
    ):
        raise ForwardTestError("v18 T014 post-execution remediation contract drift")
    _current_forward_reject_session_metadata(
        final, "v18 T014 post-execution remediation"
    )
    remediation_path = (
        forward_dir / "remediation_v18_post_execution_remediation_t016.json"
    )
    if (
        _sha256_path(remediation_path, "v18 T016 post-execution remediation")
        != CURRENT_FORWARD_T016_REMEDIATION_SHA256
    ):
        raise ForwardTestError("v18 T016 post-execution remediation drift")
    remediation = _exact_keys(
        _load_json(remediation_path, "v18 T016 post-execution remediation"),
        {
            "schema_version",
            "eval_id",
            "remediation_task_id",
            "relationship",
            "execution_evidence_rewritten",
            "current_output_revalidated",
            "execution_context_tree_sha256",
            "previous_remediation_sha256",
            "changes",
        },
        "v18 T016 post-execution remediation",
    )
    remediation_changes = remediation["changes"]
    if (
        remediation["schema_version"] != SCHEMA_VERSION
        or remediation["eval_id"] != CURRENT_FORWARD_EVAL_ID
        or remediation["remediation_task_id"] != "BSS-S3-P3-T016"
        or remediation["relationship"]
        != "CHAINED_POST_EXECUTION_VALIDATOR_REMEDIATION"
        or remediation["execution_evidence_rewritten"] is not False
        or remediation["current_output_revalidated"] is not True
        or remediation["execution_context_tree_sha256"]
        != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or remediation["previous_remediation_sha256"]
        != CURRENT_FORWARD_T014_REMEDIATION_SHA256
        or not isinstance(remediation_changes, list)
        or len(remediation_changes) != 1
    ):
        raise ForwardTestError("v18 T016 post-execution remediation identity drift")
    remediation_change = _exact_keys(
        remediation_changes[0],
        {"path", "previous_current", "current", "semantic_scope"},
        "v18 T016 post-execution remediation change",
    )
    remediation_current = _exact_keys(
        remediation_change["current"],
        {"mode", "byte_count", "sha256"},
        "v18 T016 post-execution current target",
    )
    if (
        remediation_change["path"] != final_change["path"]
        or remediation_change["previous_current"] != final_current
        or remediation_current
        != {
            "mode": "0644",
            "byte_count": 30959,
            "sha256": (
                "f822e97ee72acce5e9c03887979b44e605ab1af086470344f78dd47d3db821a2"
            ),
        }
        or remediation_change["semantic_scope"]
        != (
            "replace the overbroad arbitrary modal-subject fallback with "
            "bounded role, outcome, selection, attribution, benchmark, "
            "payment, routing, and transfer slots; preserve complete Unicode "
            "entity witnesses; accept generic, negated, unresolved, and "
            "placeholder role prose"
        )
    ):
        raise ForwardTestError("v18 T016 post-execution remediation contract drift")
    _current_forward_reject_session_metadata(
        remediation, "v18 T016 post-execution remediation"
    )
    if observed_current != remediation_current:
        raise ForwardTestError("v18 post-execution current target drift")
    return {
        change["path"]: {
            "execution": execution,
            "current": remediation_current,
        }
    }


def _validate_current_forward_context(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, Any]:
    remediations = _validate_current_forward_post_execution_remediation(
        skill_root,
        forward_dir,
    )
    path = forward_dir / "remediation_v18_context_manifest.json"
    if _sha256_path(path, "v18 context") != CURRENT_FORWARD_CONTROL_SHA256[path.name]:
        raise ForwardTestError("v18 context manifest drift")
    value = _exact_keys(
        _load_json(path, "v18 context"),
        {
            "schema_version",
            "eval_id",
            "projection_id",
            "file_count",
            "tree_sha256",
            "tree_digest_contract",
            "files",
        },
        "v18 context",
    )
    if (
        value["schema_version"] != SCHEMA_VERSION
        or value["eval_id"] != CURRENT_FORWARD_EVAL_ID
        or value["projection_id"] != CURRENT_FORWARD_PROJECTION_ID
        or value["file_count"] != len(CURRENT_FORWARD_CONTEXT_PATHS)
        or value["tree_sha256"] != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or value["tree_digest_contract"]
        != "SHA-256 over UTF-8 lines '<mode> <path> <byte_count> <sha256>\\n' in path byte order"
    ):
        raise ForwardTestError("v18 context identity drift")
    rows = value["files"]
    if not isinstance(rows, list) or len(rows) != len(CURRENT_FORWARD_CONTEXT_PATHS):
        raise ForwardTestError("v18 context file cardinality drift")
    observed_paths: list[str] = []
    tree = hashlib.sha256()
    for index, raw_row in enumerate(rows):
        row = _exact_keys(
            raw_row,
            {"path", "sha256", "mode", "byte_count"},
            f"v18_context.files[{index}]",
        )
        relative = _canonical_relative(
            row["path"], f"v18_context.files[{index}].path"
        )
        observed_paths.append(relative)
        target = skill_root.joinpath(*PurePosixPath(relative).parts)
        try:
            metadata = target.lstat()
            payload = target.read_bytes()
        except OSError as exc:
            raise ForwardTestError(f"v18 context target missing: {relative}") from exc
        if target.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ForwardTestError(f"v18 context target is not regular: {relative}")
        mode = "0755" if metadata.st_mode & stat.S_IXUSR else "0644"
        digest = _sha256_bytes(payload)
        remediation = remediations.get(relative)
        if remediation is None:
            if (
                row["mode"] != mode
                or row["byte_count"] != len(payload)
                or row["sha256"] != digest
            ):
                raise ForwardTestError(f"v18 context target drift: {relative}")
        else:
            if {
                "mode": row["mode"],
                "byte_count": row["byte_count"],
                "sha256": row["sha256"],
            } != remediation["execution"]:
                raise ForwardTestError(
                    f"v18 context execution snapshot drift: {relative}"
                )
            if {
                "mode": mode,
                "byte_count": len(payload),
                "sha256": digest,
            } != remediation["current"]:
                raise ForwardTestError(
                    f"v18 post-execution current target drift: {relative}"
                )
        tree.update(
            (
                f"{row['mode']} {relative} {row['byte_count']} "
                f"{row['sha256']}\n"
            ).encode("utf-8")
        )
    if tuple(observed_paths) != CURRENT_FORWARD_CONTEXT_PATHS:
        raise ForwardTestError("v18 context path identity/order drift")
    if tree.hexdigest() != CURRENT_FORWARD_CONTEXT_TREE_SHA256:
        raise ForwardTestError("v18 context tree digest drift")
    if set(remediations) != {
        row["path"] for row in rows if row["path"] in remediations
    }:
        raise ForwardTestError("v18 post-execution remediation path drift")
    return value


def _current_forward_replay_fields(
    skill_root: Path,
    raw_output: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    contracts = {
        "evidence": (
            "evidence_json",
            ("scripts/validate_evidence.py", "-"),
        ),
        "opportunity": (
            "opportunity_json",
            ("scripts/score_opportunity.py", "-", "--format", "json"),
        ),
        "portfolio": (
            "portfolio_json",
            ("scripts/analyze_portfolio_clusters.py", "-"),
        ),
    }
    trace = raw_output.get("execution_trace")
    if not isinstance(trace, dict):
        raise ForwardTestError("v18 execution_trace must be structured")
    replay_contract = trace.get("validator_replay")
    if not isinstance(replay_contract, dict) or set(replay_contract) != set(contracts):
        raise ForwardTestError("v18 execution_trace replay cardinality drift")
    observed: dict[str, dict[str, Any]] = {}
    for label, (field, argv) in contracts.items():
        value = raw_output.get(field)
        if not isinstance(value, str):
            raise ForwardTestError(f"v18 {field} must be a string")
        stdin = value.encode("utf-8")
        completed = subprocess.run(
            [sys.executable, *argv],
            cwd=skill_root,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ForwardTestError(f"v18 replay stdout is not JSON: {label}") from exc
        expected_trace = {
            "field": field,
            "command": "python3 " + " ".join(argv),
            "exit_code": completed.returncode,
            "stdin_sha256": _sha256_bytes(stdin),
            "stdout_sha256": _sha256_bytes(completed.stdout),
        }
        if replay_contract[label] != expected_trace:
            raise ForwardTestError(
                f"v18 exact-returned-field trace mismatch: {label}"
            )
        if completed.returncode != 0:
            raise ForwardTestError(
                f"v18 exact-returned-field replay failed: {label}: "
                + completed.stderr.decode("utf-8", errors="replace")
            )
        observed[label] = {**expected_trace, "result": parsed}
    if (
        observed["evidence"]["result"].get("valid") is not True
        or observed["evidence"]["result"].get("errors") != []
        or observed["evidence"]["result"].get("warnings") != []
        or observed["opportunity"]["result"].get("warnings") != []
        or observed["opportunity"]["result"].get("decision", {}).get("label")
        != raw_output.get("decision_label")
        or observed["portfolio"]["result"].get("valid") is not True
        or observed["portfolio"]["result"].get("errors") != []
    ):
        raise ForwardTestError("v18 exact-returned-field admission gate failed")
    return observed


def _validate_current_forward_judge(
    path: Path,
    judge_id: str,
    raw_text: str,
    replay: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    value = _load_json(path, f"v18 {judge_id}")
    _current_forward_reject_session_metadata(value, f"v18 {judge_id}")
    expected_replay = {}
    for label, item in replay.items():
        result = item["result"]
        expected_replay[label] = {
            "command": item["command"],
            "exit_code": item["exit_code"],
            "stdin_sha256": item["stdin_sha256"],
            "stdout_sha256": item["stdout_sha256"],
            "valid": result.get("valid"),
            "errors": result.get("errors"),
            "warnings": result.get("warnings"),
            "decision_label": result.get("decision", {}).get("label")
            if label == "opportunity"
            else None,
        }
    judge_replay = value.get("validator_replay")
    if isinstance(judge_replay, dict):
        normalized_judge_replay = {
            label: {
                **row,
                "errors": row.get("errors") or [],
                "warnings": row.get("warnings") or [],
            }
            for label, row in judge_replay.items()
            if isinstance(row, dict)
        }
    else:
        normalized_judge_replay = None
    normalized_expected_replay = {
        label: {
            **row,
            "errors": row.get("errors") or [],
            "warnings": row.get("warnings") or [],
        }
        for label, row in expected_replay.items()
    }
    scores = value.get("scores")
    if (
        value.get("judge_id") != judge_id
        or normalized_judge_replay != normalized_expected_replay
        or not isinstance(value.get("files_read"), list)
        or not isinstance(scores, list)
        or len(scores) != len(CATEGORIES)
    ):
        raise ForwardTestError(f"v18 {judge_id} identity/replay drift")
    categories = []
    total = 0
    for index, (item, expected_category) in enumerate(zip(scores, CATEGORIES)):
        if not isinstance(item, dict):
            raise ForwardTestError(f"v18 {judge_id} score[{index}] must be object")
        category, must_pass = expected_category
        score = item.get("score")
        quote = item.get("evidence_quote")
        if (
            item.get("category") != category
            or not isinstance(score, int)
            or isinstance(score, bool)
            or score not in {0, 1, 2}
            or not isinstance(quote, str)
            or (quote and quote.strip("“”\"'") not in raw_text)
        ):
            raise ForwardTestError(f"v18 {judge_id} score/evidence drift: {category}")
        if must_pass and score != 2:
            raise ForwardTestError(f"v18 {judge_id} must-pass category failed")
        categories.append(category)
        total += score
    if (
        categories != [category for category, _ in CATEGORIES]
        or value.get("total_score") != total
        or total < 20
        or value.get("must_pass_all_two") is not True
        or value.get("safety_failure") is not False
        or value.get("decision_consistency") is not True
        or value.get("verdict") != PASS
        or value.get("presentation_gate", {}).get("exact_heading_order") is not True
        or value.get("presentation_gate", {}).get(
            "issuer_company_ticker_security_benchmark_index_brand_before_security_map"
        )
        is not False
    ):
        raise ForwardTestError(f"v18 {judge_id} verdict arithmetic drift")
    return value


def validate_current_forward_preregistration_contract(prereg: dict[str, Any]) -> None:
    """Semantic mutation oracle for the v18 context and execution contract."""

    context_contract = prereg.get("context_contract")
    execution_contract = prereg.get("execution_contract")
    expected_context_keys = {
        "manifest_path",
        "manifest_sha256",
        "manifest_eval_id",
        "manifest_projection_id",
        "file_count",
        "tree_sha256",
        "allowed_paths",
        "allowed_context",
        "excluded_context",
        "answer_key_provided",
        "expected_decision_label_provided",
        "expected_diagnosis_provided",
        "expected_scores_provided",
    }
    expected_execution_keys = {
        "fresh_execution_context",
        "context_fork",
        "conversation_history_forwarded",
        "user_config_loaded",
        "project_rules_loaded",
        "sandbox",
        "canonical_repository_writes_allowed",
        "projection_scratch_writes_allowed",
        "skill_source_edits_allowed",
        "broker_or_order_actions_allowed",
        "runtime_install_allowed",
        "native_live_web_search_enabled",
        "interim_agent_messages_allowed",
        "maximum_focused_web_search_batches",
        "executor_wall_clock_budget_seconds",
        "required_exit_code",
    }
    if (
        prereg.get("eval_id") != CURRENT_FORWARD_EVAL_ID
        or prereg.get("projection_id") != CURRENT_FORWARD_PROJECTION_ID
        or not isinstance(context_contract, dict)
        or set(context_contract) != expected_context_keys
        or context_contract.get("manifest_path")
        != "evals/forward_test/remediation_v18_context_manifest.json"
        or context_contract.get("manifest_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["remediation_v18_context_manifest.json"]
        or context_contract.get("manifest_eval_id") != CURRENT_FORWARD_EVAL_ID
        or context_contract.get("manifest_projection_id") != CURRENT_FORWARD_PROJECTION_ID
        or context_contract.get("file_count") != len(CURRENT_FORWARD_CONTEXT_PATHS)
        or context_contract.get("tree_sha256") != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or context_contract.get("allowed_paths") != list(CURRENT_FORWARD_CONTEXT_PATHS)
        or _string_list(
            context_contract.get("allowed_context"),
            "v18 context_contract.allowed_context",
        )
        != list(CURRENT_FORWARD_ALLOWED_CONTEXT)
        or _string_list(
            context_contract.get("excluded_context"),
            "v18 context_contract.excluded_context",
        )
        != list(CURRENT_FORWARD_EXCLUDED_CONTEXT)
        or any(
            context_contract.get(field) is not False
            for field in (
                "answer_key_provided",
                "expected_decision_label_provided",
                "expected_diagnosis_provided",
                "expected_scores_provided",
            )
        )
        or not isinstance(execution_contract, dict)
        or set(execution_contract) != expected_execution_keys
        or execution_contract.get("fresh_execution_context") is not True
        or execution_contract.get("context_fork") != "none"
        or execution_contract.get("conversation_history_forwarded") is not False
        or execution_contract.get("user_config_loaded") is not False
        or execution_contract.get("project_rules_loaded") is not False
        or execution_contract.get("sandbox") != "workspace-write isolated projection"
        or execution_contract.get("canonical_repository_writes_allowed") is not False
        or execution_contract.get("projection_scratch_writes_allowed") is not True
        or execution_contract.get("skill_source_edits_allowed") is not False
        or execution_contract.get("broker_or_order_actions_allowed") is not False
        or execution_contract.get("runtime_install_allowed") is not False
        or execution_contract.get("native_live_web_search_enabled") is not True
        or execution_contract.get("interim_agent_messages_allowed") is not False
        or type(execution_contract.get("maximum_focused_web_search_batches")) is not int
        or execution_contract.get("maximum_focused_web_search_batches") != 6
        or type(execution_contract.get("executor_wall_clock_budget_seconds")) is not int
        or execution_contract.get("executor_wall_clock_budget_seconds") != 900
        or type(execution_contract.get("required_exit_code")) is not int
        or execution_contract.get("required_exit_code") != 0
    ):
        raise ForwardTestError("v18 preregistration identity/contract drift")


def validate_current_forward_schema_contract(schema: dict[str, Any]) -> None:
    """Reject open or internally unsatisfiable current response schemas."""

    replay = schema.get("definitions", {}).get("replay")
    properties = replay.get("properties") if isinstance(replay, dict) else None
    if (
        not isinstance(replay, dict)
        or replay.get("type") != "object"
        or replay.get("additionalProperties") is not False
        or not isinstance(properties, dict)
        or set(properties)
        != {
            "field",
            "command",
            "exit_code",
            "stdin_sha256",
            "stdout_sha256",
        }
        or set(replay.get("required", [])) != set(properties)
        or "result" in properties
        or "result_json" in properties
    ):
        raise ForwardTestError("v18 response schema is not a closed replay envelope")


def validate_failed_schema_lineage(forward_dir: Path) -> None:
    """Keep v14-v17 failed forward attempts immutable and non-promotable."""

    v14_result_path = forward_dir / "remediation_v14_result.json"
    if _sha256_path(v14_result_path, "v14 failure result") != (
        "df7560bd8262d202005b241944681e29e79da97a622ca29a946eb5f01cb3b799"
    ):
        raise ForwardTestError("v14 immutable failure result drift")
    v14 = _load_json(v14_result_path, "v14 failure result")
    _current_forward_reject_session_metadata(v14, "v14 failure result")
    for name, digest in v14.get("artifact_bindings", {}).items():
        if _sha256_path(forward_dir / name, f"v14 lineage {name}") != digest:
            raise ForwardTestError(f"v14 immutable failure artifact drift: {name}")
    v14_schema = _load_json(
        forward_dir / "executor_output_v14.schema.json",
        "v14 response schema",
    )
    v14_replay = (
        v14_schema.get("properties", {})
        .get("execution_trace", {})
        .get("properties", {})
        .get("validator_replay", {})
    )
    v14_judges = [
        _load_json(forward_dir / f"remediation_v14_judge_{letter}.json", "v14 judge")
        for letter in ("a", "b")
    ]
    if (
        v14.get("accepted_current_forward_result") is not False
        or v14.get("executor_outcome") != "HOST_SCHEMA_FAIL"
        or v14.get("judge_verdicts") != [FAIL, FAIL]
        or v14.get("judge_scores") != [22, 22]
        or v14.get("outcome") != FAIL
        or v14_replay.get("additionalProperties") is not False
        or set(v14_replay.get("required", []))
        != {"evidence", "opportunity", "portfolio"}
        or v14_replay.get("properties") not in (None, {})
        or [judge.get("verdict") for judge in v14_judges] != [FAIL, FAIL]
    ):
        raise ForwardTestError("v14 host-schema failure was promoted or rewritten")

    v15_result_path = forward_dir / "remediation_v15_result.json"
    if _sha256_path(v15_result_path, "v15 failure result") != (
        "8e38c4d079a14d03637f41eca01c48a4a5875c9615ece805c03cac3b864d30fb"
    ):
        raise ForwardTestError("v15 immutable failure result drift")
    v15 = _load_json(v15_result_path, "v15 failure result")
    execution = _load_json(
        forward_dir / "remediation_v15_execution.json",
        "v15 failure execution",
    )
    _current_forward_reject_session_metadata(v15, "v15 failure result")
    _current_forward_reject_session_metadata(execution, "v15 failure execution")
    for name, digest in v15.get("artifact_bindings", {}).items():
        if _sha256_path(forward_dir / name, f"v15 lineage {name}") != digest:
            raise ForwardTestError(f"v15 immutable failure artifact drift: {name}")
    v15_schema = _load_json(
        forward_dir / "executor_output_v15.schema.json",
        "v15 response schema",
    )
    v15_result_object = (
        v15_schema.get("definitions", {})
        .get("replay", {})
        .get("properties", {})
        .get("result", {})
    )
    if (
        v15.get("accepted_current_forward_result") is not False
        or v15.get("executor_outcome") != "HOST_SCHEMA_REJECTED"
        or v15.get("judge_consensus") != "NOT_RUN"
        or v15.get("judge_verdicts") != []
        or v15.get("outcome") != FAIL
        or [row.get("ordinal") for row in v15.get("prior_attempt_lineage", [])]
        != list(range(1, 15))
        or execution.get("exit_code") != 1
        or execution.get("outcome") != "HOST_RESPONSE_SCHEMA_REJECTED"
        or execution.get("raw_output") is not None
        or v15_result_object.get("type") != "object"
        or v15_result_object.get("additionalProperties") is False
    ):
        raise ForwardTestError("v15 host-schema failure was promoted or rewritten")

    v16_result_path = forward_dir / "remediation_v16_result.json"
    if _sha256_path(v16_result_path, "v16 failure result") != (
        "8a320c67e4aad8ca3527b00385d57b7dfe338293d4d245c76e3bedd337374f36"
    ):
        raise ForwardTestError("v16 immutable failure result drift")
    v16 = _load_json(v16_result_path, "v16 failure result")
    execution = _load_json(
        forward_dir / "remediation_v16_execution.json",
        "v16 failure execution",
    )
    _current_forward_reject_session_metadata(v16, "v16 failure result")
    _current_forward_reject_session_metadata(execution, "v16 failure execution")
    for name, digest in v16.get("artifact_bindings", {}).items():
        if _sha256_path(forward_dir / name, f"v16 lineage {name}") != digest:
            raise ForwardTestError(f"v16 immutable failure artifact drift: {name}")
    v16_schema = _load_json(
        forward_dir / "executor_output_v16.schema.json",
        "v16 response schema",
    )
    trace_version = (
        v16_schema.get("properties", {})
        .get("execution_trace", {})
        .get("properties", {})
        .get("trace_version", {})
    )
    if (
        v16.get("accepted_current_forward_result") is not False
        or v16.get("executor_outcome") != "HOST_SCHEMA_REJECTED"
        or v16.get("judge_consensus") != "NOT_RUN"
        or v16.get("judge_verdicts") != []
        or v16.get("outcome") != FAIL
        or [row.get("ordinal") for row in v16.get("prior_attempt_lineage", [])]
        != list(range(1, 16))
        or execution.get("exit_code") != 1
        or execution.get("outcome") != "HOST_RESPONSE_SCHEMA_REJECTED"
        or execution.get("raw_output") is not None
        or trace_version.get("const") != "1.0"
        or "type" in trace_version
    ):
        raise ForwardTestError("v16 host-schema failure was promoted or rewritten")

    v17_result_path = forward_dir / "remediation_v17_result.json"
    if _sha256_path(v17_result_path, "v17 failure result") != (
        "faf496b344d4c2d4edf9d33c438479588c0ca2685196b471275ecb60b6cc3116"
    ):
        raise ForwardTestError("v17 immutable failure result drift")
    v17 = _load_json(v17_result_path, "v17 failure result")
    execution = _load_json(
        forward_dir / "remediation_v17_execution.json",
        "v17 failure execution",
    )
    raw = _load_json(forward_dir / "remediation_v17_raw.json", "v17 raw output")
    _current_forward_reject_session_metadata(v17, "v17 failure result")
    _current_forward_reject_session_metadata(execution, "v17 failure execution")
    _current_forward_reject_session_metadata(raw, "v17 raw output")
    for name, digest in v17.get("artifact_bindings", {}).items():
        if _sha256_path(forward_dir / name, f"v17 lineage {name}") != digest:
            raise ForwardTestError(f"v17 immutable failure artifact drift: {name}")
    mismatches = []
    for label, replay in raw.get("execution_trace", {}).get(
        "validator_replay", {}
    ).items():
        result_json = replay.get("result_json")
        if (
            isinstance(result_json, str)
            and _sha256_bytes(result_json.encode("utf-8"))
            != replay.get("stdout_sha256")
        ):
            mismatches.append(label)
    if (
        v17.get("accepted_current_forward_result") is not False
        or v17.get("executor_outcome") != "HOST_EXACT_TRACE_FAIL"
        or v17.get("judge_consensus") != "NOT_RUN"
        or v17.get("judge_verdicts") != []
        or v17.get("outcome") != FAIL
        or [row.get("ordinal") for row in v17.get("prior_attempt_lineage", [])]
        != list(range(1, 17))
        or execution.get("exit_code") != 0
        or execution.get("outcome") != "HOST_EXACT_TRACE_FAIL"
        or mismatches != ["evidence", "opportunity", "portfolio"]
    ):
        raise ForwardTestError("v17 exact-trace failure was promoted or rewritten")


def validate_current_forward_execution_receipt_contract(
    prereg: dict[str, Any],
    seal: dict[str, Any],
    execution: dict[str, Any],
) -> None:
    """Semantic mutation oracle for v18 controls and time ordering."""

    controls = prereg.get("execution_contract")
    if (
        not isinstance(controls, dict)
        or execution.get("schema_version") != SCHEMA_VERSION
        or execution.get("eval_id") != CURRENT_FORWARD_EVAL_ID
        or execution.get("executor_attempt_ordinal") != 18
        or execution.get("projection_id") != CURRENT_FORWARD_PROJECTION_ID
        or execution.get("preexecution_seal_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["preexecution_seal_v18.json"]
        or execution.get("preregistration_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["remediation_v18_preregistration.json"]
        or execution.get("projection_tree_sha256") != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or execution.get("output_schema_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["executor_output_v18.schema.json"]
        or execution.get("execution_controls") != controls
        or execution.get("exit_code") != 0
        or controls.get("required_exit_code") != 0
        or execution.get("outcome") != "HOST_REPLAY_PASS_PENDING_JUDGES"
    ):
        raise ForwardTestError("v18 execution receipt identity/controls drift")
    times = [
        _current_forward_utc(prereg.get("issued_at_utc"), "v18 prereg issued_at"),
        _current_forward_utc(seal.get("issued_at_utc"), "v18 seal issued_at"),
        _current_forward_utc(execution.get("started_at_utc"), "v18 execution started_at"),
        _current_forward_utc(execution.get("finished_at_utc"), "v18 execution finished_at"),
        _current_forward_utc(execution.get("recorded_at_utc"), "v18 execution recorded_at"),
    ]
    if times != sorted(times):
        raise ForwardTestError("v18 preregistration/seal/execution time ordering drift")


def validate_current_forward(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, int | str]:
    """Validate the v18 preregistered subject and exact returned-field trace."""

    if not CURRENT_FORWARD_EVIDENCE_SHA256:
        raise ForwardTestError("v18 frozen evidence hashes are not configured")
    for name, expected_sha in {**CURRENT_FORWARD_CONTROL_SHA256, **CURRENT_FORWARD_EVIDENCE_SHA256}.items():
        if _sha256_path(forward_dir / name, f"v18 {name}") != expected_sha:
            raise ForwardTestError(f"v18 frozen artifact drift: {name}")

    context = _validate_current_forward_context(skill_root, forward_dir)
    prereg = _load_json(
        forward_dir / "remediation_v18_preregistration.json",
        "v18 preregistration",
    )
    _current_forward_reject_session_metadata(prereg, "v18 preregistration")
    context_contract = prereg.get("context_contract")
    execution_contract = prereg.get("execution_contract")
    output_contract = prereg.get("output_contract")
    validate_current_forward_preregistration_contract(prereg)
    output_schema = _load_json(
        forward_dir / "executor_output_v18.schema.json",
        "v18 response schema",
    )
    validate_current_forward_schema_contract(output_schema)
    if (
        prereg.get("schema_version") != SCHEMA_VERSION
        or prereg.get("skill_version") != SKILL_VERSION
        or prereg.get("eval_id") != CURRENT_FORWARD_EVAL_ID
        or prereg.get("case_id") != CURRENT_FORWARD_CASE_ID
        or prereg.get("projection_id") != CURRENT_FORWARD_PROJECTION_ID
        or prereg.get("run_date") != RUN_DATE
        or prereg.get("as_of") != RUN_DATE
        or prereg.get("source_cutoff") != RUN_DATE
        or prereg.get("horizon_months") != 24
        or not isinstance(context_contract, dict)
        or context_contract.get("manifest_path")
        != "evals/forward_test/remediation_v18_context_manifest.json"
        or context_contract.get("manifest_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["remediation_v18_context_manifest.json"]
        or context_contract.get("manifest_eval_id") != CURRENT_FORWARD_EVAL_ID
        or context_contract.get("manifest_projection_id") != CURRENT_FORWARD_PROJECTION_ID
        or context_contract.get("file_count") != len(CURRENT_FORWARD_CONTEXT_PATHS)
        or context_contract.get("tree_sha256") != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or context_contract.get("allowed_paths") != list(CURRENT_FORWARD_CONTEXT_PATHS)
        or context_contract.get("allowed_context")
        != list(CURRENT_FORWARD_ALLOWED_CONTEXT)
        or context_contract.get("excluded_context")
        != list(CURRENT_FORWARD_EXCLUDED_CONTEXT)
        or context_contract.get("answer_key_provided") is not False
        or context_contract.get("expected_decision_label_provided") is not False
        or context_contract.get("expected_diagnosis_provided") is not False
        or context_contract.get("expected_scores_provided") is not False
        or not isinstance(context_contract.get("allowed_context"), list)
        or not isinstance(context_contract.get("excluded_context"), list)
        or not isinstance(execution_contract, dict)
        or execution_contract.get("fresh_execution_context") is not True
        or execution_contract.get("context_fork") != "none"
        or execution_contract.get("conversation_history_forwarded") is not False
        or execution_contract.get("user_config_loaded") is not False
        or execution_contract.get("project_rules_loaded") is not False
        or execution_contract.get("canonical_repository_writes_allowed") is not False
        or execution_contract.get("runtime_install_allowed") is not False
        or execution_contract.get("native_live_web_search_enabled") is not True
        or execution_contract.get("required_exit_code") != 0
        or not isinstance(output_contract, dict)
        or output_contract.get("schema_path")
        != "evals/forward_test/executor_output_v18.schema.json"
        or output_contract.get("schema_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["executor_output_v18.schema.json"]
        or output_contract.get("structured_trace_required") is not True
        or output_contract.get("exact_returned_field_replay_required") is not True
        or prereg.get("retry_contract", {}).get(
            "prior_output_or_diagnosis_disclosed_to_executor"
        )
        is not False
    ):
        raise ForwardTestError("v18 preregistration identity/contract drift")

    task_path = forward_dir / "remediation_v18_task_message.txt"
    task_bytes = task_path.read_bytes()
    if not task_bytes.endswith(b"\n") or task_bytes.endswith(b"\n\n"):
        raise ForwardTestError("v18 task newline contract drift")
    task_text = task_bytes.decode("utf-8")
    leaked_labels = [
        label for label in DECISION_LABELS if label in task_text.upper()
    ]
    if (
        leaked_labels
        or "23/24" in task_text
        or re.search(
            r"\bEXPECTED (?:DECISION )?LABEL\s*[:=]",
            task_text.upper(),
        )
    ):
        raise ForwardTestError(f"v18 task leaks prior answer: {leaked_labels}")

    seal_path = forward_dir / "preexecution_seal_v18.json"
    seal = _load_json(seal_path, "v18 seal")
    _current_forward_reject_session_metadata(seal, "v18 seal")
    seal_sha = CURRENT_FORWARD_CONTROL_SHA256[seal_path.name]
    expected_bindings = {
        "remediation_v18_preregistration_sha256": CURRENT_FORWARD_CONTROL_SHA256[
            "remediation_v18_preregistration.json"
        ],
        "remediation_v18_context_manifest_sha256": CURRENT_FORWARD_CONTROL_SHA256[
            "remediation_v18_context_manifest.json"
        ],
        "remediation_v18_task_message_sha256": CURRENT_FORWARD_CONTROL_SHA256[
            "remediation_v18_task_message.txt"
        ],
        "executor_output_v18_schema_sha256": CURRENT_FORWARD_CONTROL_SHA256[
            "executor_output_v18.schema.json"
        ],
        "prepare_forward_output_v18_sha256": output_contract[
            "preparation_harness_sha256"
        ],
        "rubric_v2_sha256": prereg["rubric_contract"]["sha256"],
    }
    if (
        seal.get("seal_id")
        != "BSS-S3-P3-T004-forward-remediation-v18-preexecution"
        or seal.get("eval_id") != CURRENT_FORWARD_EVAL_ID
        or seal.get("projection_id") != CURRENT_FORWARD_PROJECTION_ID
        or seal.get("issued_before_executor_start") is not True
        or seal.get("projection_tree_sha256") != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or seal.get("artifact_bindings") != expected_bindings
        or seal.get("execution_controls") != execution_contract
    ):
        raise ForwardTestError("v18 preexecution seal drift")

    execution = _load_json(
        forward_dir / "remediation_v18_execution.json", "v18 execution"
    )
    _current_forward_reject_session_metadata(execution, "v18 execution")
    validate_current_forward_execution_receipt_contract(prereg, seal, execution)
    raw_path = forward_dir / "remediation_v18_raw.json"
    raw_bytes = raw_path.read_bytes()
    envelope = task_bytes + f"PREEXECUTION_SEAL_SHA256={seal_sha}\n".encode("ascii")
    if (
        execution.get("schema_version") != SCHEMA_VERSION
        or execution.get("eval_id") != CURRENT_FORWARD_EVAL_ID
        or execution.get("executor_attempt_ordinal") != 18
        or execution.get("projection_id") != CURRENT_FORWARD_PROJECTION_ID
        or execution.get("preexecution_seal_sha256") != seal_sha
        or execution.get("preregistration_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["remediation_v18_preregistration.json"]
        or execution.get("projection_tree_sha256") != CURRENT_FORWARD_CONTEXT_TREE_SHA256
        or execution.get("output_schema_sha256")
        != CURRENT_FORWARD_CONTROL_SHA256["executor_output_v18.schema.json"]
        or execution.get("execution_controls") != execution_contract
        or execution.get("execution_envelope_sha256") != _sha256_bytes(envelope)
        or execution.get("exit_code") != 0
        or execution.get("outcome") != "HOST_REPLAY_PASS_PENDING_JUDGES"
        or execution.get("raw_output")
        != {
            "path": "evals/forward_test/remediation_v18_raw.json",
            "sha256": _sha256_bytes(raw_bytes),
            "byte_count": len(raw_bytes),
        }
    ):
        raise ForwardTestError("v18 execution receipt identity/binding drift")
    raw_output = _load_json(raw_path, "v18 raw output")
    _current_forward_reject_session_metadata(raw_output, "v18 raw output")
    if set(raw_output) != {
        "memo_markdown",
        "evidence_json",
        "opportunity_json",
        "portfolio_json",
        "decision_label",
        "execution_trace",
    }:
        raise ForwardTestError("v18 raw output field set drift")
    for field, minimum in (
        ("memo_markdown", 1000),
        ("evidence_json", 500),
        ("opportunity_json", 500),
        ("portfolio_json", 300),
    ):
        if not isinstance(raw_output.get(field), str) or len(raw_output[field]) < minimum:
            raise ForwardTestError(f"v18 raw output field schema drift: {field}")
    trace = _exact_keys(
        raw_output.get("execution_trace"),
        {
            "trace_version",
            "preexecution_seal_sha256",
            "files_read",
            "web_searches",
            "pages_opened",
            "files_written",
            "validator_replay",
            "limitations",
        },
        "v18 execution_trace",
    )
    if (
        trace["trace_version"] != "1.0"
        or trace["preexecution_seal_sha256"] != seal_sha
        or not all(
            isinstance(trace[field], list)
            and trace[field]
            and all(isinstance(item, str) and item.strip() for item in trace[field])
            for field in (
                "files_read",
                "web_searches",
                "pages_opened",
                "files_written",
                "limitations",
            )
        )
    ):
        raise ForwardTestError("v18 structured execution trace drift")
    validate_current_presentation(raw_output)
    replay = _current_forward_replay_fields(skill_root, raw_output)

    judge_manifest = _load_json(
        forward_dir / "remediation_v18_judge_context_manifest.json",
        "v18 judge context",
    )
    _current_forward_reject_session_metadata(judge_manifest, "v18 judge context")
    aliases = {
        "context_manifest.json": forward_dir
        / "remediation_v18_context_manifest.json",
        "execution_receipt.json": forward_dir / "remediation_v18_execution.json",
        "executor_output.schema.json": forward_dir
        / "executor_output_v18.schema.json",
        "judge.schema.json": forward_dir / "judge.schema.json",
        "judge_task.txt": forward_dir / "remediation_v18_judge_task.txt",
        "preexecution_seal.json": forward_dir / "preexecution_seal_v18.json",
        "preregistration.json": forward_dir
        / "remediation_v18_preregistration.json",
        "raw_output.json": raw_path,
        "rubric_v2.md": skill_root / "evals" / "rubric_v2.md",
        "task_message.txt": task_path,
    }
    rows = judge_manifest.get("files")
    expected_rows = [
        {
            "path": name,
            "sha256": _sha256_path(path, f"v18 judge context {name}"),
            "byte_count": path.stat().st_size,
        }
        for name, path in sorted(aliases.items())
    ]
    tree = hashlib.sha256(
        "".join(
            f"{row['path']} {row['byte_count']} {row['sha256']}\n"
            for row in expected_rows
        ).encode("utf-8")
    ).hexdigest()
    if (
        judge_manifest.get("schema_version") != SCHEMA_VERSION
        or judge_manifest.get("eval_id") != CURRENT_FORWARD_EVAL_ID
        or judge_manifest.get("file_count") != len(expected_rows)
        or rows != expected_rows
        or judge_manifest.get("tree_sha256") != tree
    ):
        raise ForwardTestError("v18 judge context manifest drift")

    raw_text = raw_bytes.decode("utf-8")
    judges = [
        _validate_current_forward_judge(
            forward_dir / f"remediation_v18_judge_{letter}.json",
            f"judge-{letter}",
            raw_text,
            replay,
        )
        for letter in ("a", "b")
    ]
    result = _load_json(forward_dir / "remediation_v18_result.json", "v18 result")
    _current_forward_reject_session_metadata(result, "v18 result")
    expected_artifacts = {
        name: digest for name, digest in {**CURRENT_FORWARD_CONTROL_SHA256, **CURRENT_FORWARD_EVIDENCE_SHA256}.items()
        if name != "remediation_v18_result.json"
    }
    if (
        result.get("schema_version") != SCHEMA_VERSION
        or result.get("eval_id") != CURRENT_FORWARD_EVAL_ID
        or result.get("executor_attempt_ordinal") != 18
        or result.get("accepted_current_forward_result") is not True
        or result.get("executor_outcome") != "HOST_REPLAY_PASS"
        or result.get("artifact_bindings") != expected_artifacts
        or result.get("decision_label") != raw_output["decision_label"]
        or result.get("judge_consensus") != PASS
        or result.get("judge_verdicts") != [PASS, PASS]
        or result.get("outcome") != PASS
        or [item.get("ordinal") for item in result.get("prior_attempt_lineage", [])]
        != list(range(1, 18))
    ):
        raise ForwardTestError("v18 result identity/verdict/lineage drift")
    total_score = min(judge["total_score"] for judge in judges)
    return {
        "status": PASS,
        "context_file_count": context["file_count"],
        "executor_trial_count": 18,
        "judge_count": 2,
        "maximum_score": 24,
        "total_score": total_score,
    }


def _v19_file_row(path: Path, relative: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError as exc:
        raise ForwardTestError(f"v19 artifact missing: {relative}") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ForwardTestError(f"v19 artifact is not regular: {relative}")
    return {
        "path": relative,
        "sha256": _sha256_bytes(payload),
        "mode": "0755" if metadata.st_mode & stat.S_IXUSR else "0644",
        "byte_count": len(payload),
    }


def _v19_validate_context(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, Any]:
    manifest = _load_json(
        forward_dir / "remediation_v19_context_manifest.json",
        "v19 context manifest",
    )
    _current_forward_reject_session_metadata(manifest, "v19 context manifest")
    rows = manifest.get("files")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("eval_id") != V19_EVAL_ID
        or manifest.get("projection_id") != V19_PROJECTION_ID
        or manifest.get("file_count") != 30
        or manifest.get("tree_sha256") != V19_CONTEXT_TREE_SHA256
        or not isinstance(rows, list)
        or len(rows) != 30
    ):
        raise ForwardTestError("v19 context identity drift")
    observed: list[dict[str, Any]] = []
    paths: list[str] = []
    for index, row in enumerate(rows):
        item = _exact_keys(
            row,
            {"path", "sha256", "mode", "byte_count"},
            f"v19 context files[{index}]",
        )
        relative = _canonical_relative(
            item["path"], f"v19 context files[{index}].path"
        )
        paths.append(relative)
        current = _v19_file_row(skill_root / relative, relative)
        if relative == "scripts/presentation_contract.py":
            if current != {
                "path": relative,
                "sha256": (
                    "f822e97ee72acce5e9c03887979b44e605ab1af086470344f78dd47d3db821a2"
                ),
                "mode": "0644",
                "byte_count": 30959,
            }:
                raise ForwardTestError(
                    "v19 remediated presentation target drift"
                )
            observed.append(item)
        else:
            observed.append(current)
    if paths != sorted(paths, key=lambda value: value.encode("utf-8")):
        raise ForwardTestError("v19 context paths are not byte-sorted")
    if observed != rows:
        raise ForwardTestError("v19 context target drift")
    tree = hashlib.sha256(
        "".join(
            f"{row['mode']} {row['path']} {row['byte_count']} {row['sha256']}\n"
            for row in observed
        ).encode("utf-8")
    ).hexdigest()
    if tree != V19_CONTEXT_TREE_SHA256:
        raise ForwardTestError("v19 context tree digest drift")
    return manifest


def _v19_validate_control_packet(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, Any]:
    packet = _load_json(
        forward_dir / "control_packet_v19.json", "v19 control packet"
    )
    _current_forward_reject_session_metadata(packet, "v19 control packet")
    rows = packet.get("artifacts")
    if (
        packet.get("schema_version") != SCHEMA_VERSION
        or packet.get("packet_id")
        != "BSS-S3-P3-T008-forward-remediation-v19-control-packet"
        or packet.get("eval_id") != V19_EVAL_ID
        or packet.get("projection_id") != V19_PROJECTION_ID
        or packet.get("projection_tree_sha256") != V19_CONTEXT_TREE_SHA256
        or packet.get("artifact_count") != 8
        or not isinstance(rows, list)
        or len(rows) != 8
    ):
        raise ForwardTestError("v19 control packet identity drift")
    observed: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = _exact_keys(
            row,
            {"path", "sha256", "mode", "byte_count"},
            f"v19 control packet artifacts[{index}]",
        )
        relative = _canonical_relative(
            item["path"], f"v19 control packet artifacts[{index}].path"
        )
        observed.append(_v19_file_row(skill_root / relative, relative))
    if observed != rows:
        raise ForwardTestError("v19 control packet artifact binding drift")
    return packet


def _v19_message_imprint(query_text: str) -> str:
    capture = False
    octets: list[str] = []
    for line in query_text.splitlines():
        if line.strip() == "Message data:":
            capture = True
            continue
        if capture and re.match(r"^\s*[0-9a-fA-F]{4}\s+-\s+", line):
            hexadecimal = line.split("-", 1)[1].split("   ", 1)[0]
            octets.extend(re.findall(r"[0-9a-fA-F]{2}", hexadecimal))
        elif capture:
            break
    return "".join(octets).lower()


def _rfc3161_sha256_imprint(request: bytes) -> str:
    """Extract the exact SHA-256 MessageImprint from a strict DER request."""

    def tlv(data: bytes, offset: int) -> tuple[int, int, int]:
        if offset + 2 > len(data):
            raise ForwardTestError("RFC3161 request DER is truncated")
        tag = data[offset]
        length_octet = data[offset + 1]
        cursor = offset + 2
        if length_octet & 0x80:
            width = length_octet & 0x7F
            if width == 0 or width > 4 or cursor + width > len(data):
                raise ForwardTestError("RFC3161 request DER length is invalid")
            length = int.from_bytes(data[cursor : cursor + width], "big")
            cursor += width
        else:
            length = length_octet
        end = cursor + length
        if end > len(data):
            raise ForwardTestError("RFC3161 request DER value is truncated")
        return tag, cursor, end

    root_tag, root_start, root_end = tlv(request, 0)
    if root_tag != 0x30 or root_end != len(request):
        raise ForwardTestError("RFC3161 request root must be one DER sequence")
    version_tag, _, version_end = tlv(request, root_start)
    if version_tag != 0x02:
        raise ForwardTestError("RFC3161 request version is missing")
    imprint_tag, imprint_start, imprint_end = tlv(request, version_end)
    if imprint_tag != 0x30:
        raise ForwardTestError("RFC3161 MessageImprint is missing")
    algorithm_tag, algorithm_start, algorithm_end = tlv(
        request, imprint_start
    )
    if algorithm_tag != 0x30:
        raise ForwardTestError("RFC3161 MessageImprint algorithm is invalid")
    oid_tag, oid_start, oid_end = tlv(request, algorithm_start)
    sha256_oid = bytes.fromhex("608648016503040201")
    if (
        oid_tag != 0x06
        or request[oid_start:oid_end] != sha256_oid
        or algorithm_end > imprint_end
    ):
        raise ForwardTestError("RFC3161 MessageImprint is not SHA-256")
    digest_tag, digest_start, digest_end = tlv(request, algorithm_end)
    digest = request[digest_start:digest_end]
    if digest_tag != 0x04 or len(digest) != 32 or digest_end != imprint_end:
        raise ForwardTestError("RFC3161 SHA-256 MessageImprint is invalid")
    return digest.hex()


def validate_v19_timestamp_contract(
    forward_dir: Path,
    evidence: dict[str, Any],
) -> datetime:
    """Cryptographically verify the external pre-execution timestamp."""

    _current_forward_reject_session_metadata(
        evidence, "v19 preexecution timestamp"
    )
    authority = evidence.get("authority")
    packet_binding = evidence.get("control_packet")
    request_binding = evidence.get("request")
    response_binding = evidence.get("response")
    trust_anchor = evidence.get("trust_anchor")
    verification = evidence.get("verification")
    if (
        evidence.get("schema_version") != SCHEMA_VERSION
        or evidence.get("evidence_id")
        != "BSS-S3-P3-T008-forward-remediation-v19-rfc3161-preexecution"
        or evidence.get("eval_id") != V19_EVAL_ID
        or not isinstance(authority, dict)
        or authority.get("protocol") != "RFC3161"
        or authority.get("url") != "http://timestamp.digicert.com"
        or authority.get("provider") != "DigiCert"
        or not isinstance(packet_binding, dict)
        or not isinstance(request_binding, dict)
        or not isinstance(response_binding, dict)
        or not isinstance(trust_anchor, dict)
        or not isinstance(verification, dict)
        or verification.get("status") != PASS
        or verification.get("query_binds_exact_control_packet_bytes") is not True
        or verification.get("response_verified_before_executor_start") is not True
    ):
        raise ForwardTestError("v19 preexecution timestamp identity drift")
    packet_path = forward_dir / "control_packet_v19.json"
    packet_bytes = packet_path.read_bytes()
    if packet_binding != {
        "path": "evals/forward_test/control_packet_v19.json",
        "sha256": _sha256_bytes(packet_bytes),
        "byte_count": len(packet_bytes),
        "message_imprint_algorithm": "sha256",
    }:
        raise ForwardTestError("v19 timestamp control-packet binding drift")
    try:
        request = base64.b64decode(
            request_binding["payload_base64"], validate=True
        )
        response = base64.b64decode(
            response_binding["payload_base64"], validate=True
        )
        root_pem = trust_anchor["pem"].encode("ascii")
    except (KeyError, UnicodeError, ValueError) as exc:
        raise ForwardTestError("v19 timestamp payload encoding drift") from exc
    for label, payload, binding in (
        ("request", request, request_binding),
        ("response", response, response_binding),
    ):
        if (
            binding.get("encoding") != "base64-der"
            or binding.get("sha256") != _sha256_bytes(payload)
            or binding.get("byte_count") != len(payload)
        ):
            raise ForwardTestError(f"v19 timestamp {label} binding drift")
    if (
        trust_anchor.get("subject") != "DigiCert Assured ID Root CA"
        or trust_anchor.get("encoding") != "pem"
        or trust_anchor.get("sha256_fingerprint")
        != V19_TRUST_ANCHOR_SHA256_FINGERPRINT
    ):
        raise ForwardTestError("v19 timestamp trust anchor metadata drift")

    with tempfile.TemporaryDirectory(prefix="bss-v19-ts-verify-") as raw:
        root = Path(raw)
        request_path = root / "request.tsq"
        response_path = root / "response.tsr"
        root_path = root / "root.pem"
        token_path = root / "token.der"
        chain_path = root / "chain.pem"
        request_path.write_bytes(request)
        response_path.write_bytes(response)
        root_path.write_bytes(root_pem)

        def run(*argv: str) -> subprocess.CompletedProcess[str]:
            completed = subprocess.run(
                ["openssl", *argv],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                raise ForwardTestError(
                    "v19 RFC3161 verification failed: "
                    + completed.stderr.strip()
                )
            return completed

        certificate = run(
            "x509",
            "-in",
            str(root_path),
            "-noout",
            "-fingerprint",
            "-sha256",
        ).stdout
        observed_fingerprint = certificate.split("=", 1)[-1].strip().upper()
        if observed_fingerprint != V19_TRUST_ANCHOR_SHA256_FINGERPRINT:
            raise ForwardTestError("v19 timestamp trust anchor fingerprint drift")
        query_text = run(
            "ts", "-query", "-in", str(request_path), "-text"
        ).stdout
        if (
            "Hash Algorithm: sha256" not in query_text
            or _rfc3161_sha256_imprint(request)
            != _sha256_bytes(packet_bytes)
        ):
            raise ForwardTestError("v19 RFC3161 query message imprint drift")
        run(
            "ts",
            "-reply",
            "-in",
            str(response_path),
            "-token_out",
            "-out",
            str(token_path),
        )
        run(
            "pkcs7",
            "-inform",
            "DER",
            "-in",
            str(token_path),
            "-print_certs",
            "-out",
            str(chain_path),
        )
        run(
            "ts",
            "-verify",
            "-queryfile",
            str(request_path),
            "-in",
            str(response_path),
            "-CAfile",
            str(root_path),
            "-untrusted",
            str(chain_path),
        )
        reply_text = run(
            "ts", "-reply", "-in", str(response_path), "-text"
        ).stdout
    if "Status: Granted." not in reply_text:
        raise ForwardTestError("v19 RFC3161 response is not granted")
    time_match = re.search(r"^Time stamp:\s*(.+)$", reply_text, flags=re.MULTILINE)
    if time_match is None:
        raise ForwardTestError("v19 RFC3161 response time is missing")
    try:
        observed_time = datetime.strptime(
            time_match.group(1), "%b %d %H:%M:%S %Y GMT"
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ForwardTestError("v19 RFC3161 response time is invalid") from exc
    declared_time = _current_forward_utc(
        response_binding.get("gen_time_utc"), "v19 RFC3161 gen_time"
    )
    if (
        observed_time != declared_time
        or response_binding.get("status") != "GRANTED"
        or response_binding.get("policy_oid") != "2.16.840.1.114412.7.1"
    ):
        raise ForwardTestError("v19 RFC3161 response metadata drift")
    return observed_time


def validate_v19_execution_ordering(
    preregistration: dict[str, Any],
    timestamp: dict[str, Any],
    execution: dict[str, Any],
) -> None:
    timestamp_time = _current_forward_utc(
        timestamp.get("response", {}).get("gen_time_utc"),
        "v19 RFC3161 gen_time",
    )
    prereg_time = _current_forward_utc(
        preregistration.get("issued_at_utc"), "v19 prereg issued_at"
    )
    started = _current_forward_utc(
        execution.get("started_at_utc"), "v19 execution started_at"
    )
    finished = _current_forward_utc(
        execution.get("finished_at_utc"), "v19 execution finished_at"
    )
    recorded = _current_forward_utc(
        execution.get("recorded_at_utc"), "v19 execution recorded_at"
    )
    lead = int((started - timestamp_time).total_seconds())
    ordering = execution.get("independent_preexecution_ordering")
    if (
        not prereg_time <= timestamp_time < started <= finished <= recorded
        or lead < 1
        or not isinstance(ordering, dict)
        or ordering.get("protocol") != "RFC3161"
        or ordering.get("authority") != "DigiCert"
        or ordering.get("gen_time_utc")
        != timestamp["response"]["gen_time_utc"]
        or ordering.get("verified_before_start") is not True
        or ordering.get("minimum_observed_lead_seconds") != lead
    ):
        raise ForwardTestError("v19 independent preexecution ordering drift")


def _v19_validate_judge_manifest(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, Any]:
    manifest = _load_json(
        forward_dir / "remediation_v19_judge_context_manifest.json",
        "v19 judge context",
    )
    aliases = {
        "context_manifest.json": forward_dir
        / "remediation_v19_context_manifest.json",
        "control_packet.json": forward_dir / "control_packet_v19.json",
        "execution_receipt.json": forward_dir / "remediation_v19_execution.json",
        "executor_output.schema.json": forward_dir
        / "executor_output_v19.schema.json",
        "judge.schema.json": forward_dir / "judge.schema.json",
        "judge_task.txt": forward_dir / "remediation_v19_judge_task.txt",
        "preexecution_seal.json": forward_dir / "preexecution_seal_v19.json",
        "preexecution_timestamp.json": forward_dir
        / "preexecution_timestamp_v19.json",
        "preregistration.json": forward_dir
        / "remediation_v19_preregistration.json",
        "raw_output.json": forward_dir / "remediation_v19_raw.json",
        "rubric_v2.md": skill_root / "evals" / "rubric_v2.md",
        "task_message.txt": forward_dir / "remediation_v19_task_message.txt",
    }
    expected = [
        _v19_file_row(path, name)
        for name, path in sorted(
            aliases.items(), key=lambda item: item[0].encode("utf-8")
        )
    ]
    tree = hashlib.sha256(
        "".join(
            f"{row['mode']} {row['path']} {row['byte_count']} {row['sha256']}\n"
            for row in expected
        ).encode("utf-8")
    ).hexdigest()
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("eval_id") != V19_EVAL_ID
        or manifest.get("file_count") != 12
        or manifest.get("files") != expected
        or manifest.get("tree_sha256") != tree
        or tree
        != "0c1b9c526d41151654c6f4d1d7b33fe8ef3368e7a8c63906e95ff4474416a62b"
    ):
        raise ForwardTestError("v19 judge context manifest drift")
    return manifest


def validate_v19_forward(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, int | str]:
    for name, expected in V19_ARTIFACT_SHA256.items():
        if _sha256_path(forward_dir / name, f"v19 {name}") != expected:
            raise ForwardTestError(f"v19 frozen artifact drift: {name}")
    context = _v19_validate_context(skill_root, forward_dir)
    _v19_validate_control_packet(skill_root, forward_dir)
    preregistration = _load_json(
        forward_dir / "remediation_v19_preregistration.json",
        "v19 preregistration",
    )
    context_contract = preregistration.get("context_contract")
    execution_contract = preregistration.get("execution_contract")
    output_contract = preregistration.get("output_contract")
    if (
        preregistration.get("schema_version") != SCHEMA_VERSION
        or preregistration.get("skill_version") != SKILL_VERSION
        or preregistration.get("eval_id") != V19_EVAL_ID
        or preregistration.get("case_id") != V19_CASE_ID
        or preregistration.get("projection_id") != V19_PROJECTION_ID
        or preregistration.get("run_date") != "2026-07-24"
        or preregistration.get("as_of") != "2026-07-24"
        or preregistration.get("source_cutoff") != "2026-07-24"
        or not isinstance(context_contract, dict)
        or context_contract.get("manifest_sha256")
        != V19_ARTIFACT_SHA256["remediation_v19_context_manifest.json"]
        or context_contract.get("tree_sha256") != V19_CONTEXT_TREE_SHA256
        or context_contract.get("allowed_paths")
        != [row["path"] for row in context["files"]]
        or context_contract.get("answer_key_provided") is not False
        or context_contract.get("expected_decision_label_provided") is not False
        or context_contract.get("expected_diagnosis_provided") is not False
        or context_contract.get("expected_scores_provided") is not False
        or not isinstance(execution_contract, dict)
        or execution_contract.get("fresh_execution_context") is not True
        or execution_contract.get("context_fork") != "none"
        or execution_contract.get("conversation_history_forwarded") is not False
        or execution_contract.get("user_config_loaded") is not False
        or execution_contract.get("project_rules_loaded") is not False
        or execution_contract.get("canonical_repository_writes_allowed") is not False
        or execution_contract.get("runtime_install_allowed") is not False
        or execution_contract.get(
            "independent_rfc3161_timestamp_required_before_start"
        )
        is not True
        or not isinstance(output_contract, dict)
        or output_contract.get("schema_sha256")
        != V19_ARTIFACT_SHA256["executor_output_v19.schema.json"]
    ):
        raise ForwardTestError("v19 preregistration identity/contract drift")
    schema = _load_json(
        forward_dir / "executor_output_v19.schema.json", "v19 output schema"
    )
    validate_current_forward_schema_contract(schema)
    seal = _load_json(
        forward_dir / "preexecution_seal_v19.json", "v19 seal"
    )
    if (
        seal.get("seal_id")
        != "BSS-S3-P3-T008-forward-remediation-v19-preexecution"
        or seal.get("eval_id") != V19_EVAL_ID
        or seal.get("projection_id") != V19_PROJECTION_ID
        or seal.get("issued_before_executor_start") is not True
        or seal.get("projection_tree_sha256") != V19_CONTEXT_TREE_SHA256
        or seal.get("execution_controls") != execution_contract
        or seal.get("timestamp_contract", {}).get("authority_protocol")
        != "RFC3161"
        or seal.get("timestamp_contract", {}).get("required_before_executor_start")
        is not True
    ):
        raise ForwardTestError("v19 preexecution seal drift")
    timestamp = _load_json(
        forward_dir / "preexecution_timestamp_v19.json",
        "v19 preexecution timestamp",
    )
    validate_v19_timestamp_contract(forward_dir, timestamp)
    execution = _load_json(
        forward_dir / "remediation_v19_execution.json", "v19 execution"
    )
    _current_forward_reject_session_metadata(execution, "v19 execution")
    if (
        execution.get("schema_version") != SCHEMA_VERSION
        or execution.get("eval_id") != V19_EVAL_ID
        or execution.get("executor_attempt_ordinal") != 19
        or execution.get("projection_id") != V19_PROJECTION_ID
        or execution.get("preexecution_seal_sha256")
        != V19_ARTIFACT_SHA256["preexecution_seal_v19.json"]
        or execution.get("preexecution_timestamp_evidence_sha256")
        != V19_ARTIFACT_SHA256["preexecution_timestamp_v19.json"]
        or execution.get("control_packet_sha256")
        != V19_ARTIFACT_SHA256["control_packet_v19.json"]
        or execution.get("projection_tree_sha256") != V19_CONTEXT_TREE_SHA256
        or execution.get("execution_controls") != execution_contract
        or execution.get("exit_code") != 0
        or execution.get("outcome") != "HOST_REPLAY_PASS_PENDING_JUDGES"
    ):
        raise ForwardTestError("v19 execution identity/binding drift")
    task_bytes = (forward_dir / "remediation_v19_task_message.txt").read_bytes()
    envelope = task_bytes + (
        "PREEXECUTION_SEAL_SHA256="
        + V19_ARTIFACT_SHA256["preexecution_seal_v19.json"]
        + "\n"
    ).encode("ascii")
    if execution.get("execution_envelope_sha256") != _sha256_bytes(envelope):
        raise ForwardTestError("v19 execution envelope drift")
    validate_v19_execution_ordering(preregistration, timestamp, execution)
    raw_path = forward_dir / "remediation_v19_raw.json"
    raw_bytes = raw_path.read_bytes()
    raw_binding = execution.get("raw_output")
    if raw_binding != {
        "path": "evals/forward_test/remediation_v19_raw.json",
        "sha256": _sha256_bytes(raw_bytes),
        "byte_count": len(raw_bytes),
        "exact_host_return_bytes": True,
    }:
        raise ForwardTestError("v19 raw output binding drift")
    raw_output = _load_json(raw_path, "v19 raw output")
    _current_forward_reject_session_metadata(raw_output, "v19 raw output")
    validate_current_presentation(raw_output)
    replay = _current_forward_replay_fields(skill_root, raw_output)
    _v19_validate_judge_manifest(skill_root, forward_dir)
    raw_text = raw_bytes.decode("utf-8")
    judges = [
        _validate_current_forward_judge(
            forward_dir / f"remediation_v19_judge_{letter}.json",
            f"judge-{letter}",
            raw_text,
            replay,
        )
        for letter in ("a", "b")
    ]
    result = _load_json(
        forward_dir / "remediation_v19_result.json", "v19 result"
    )
    _current_forward_reject_session_metadata(result, "v19 result")
    expected_bindings = {
        name: digest
        for name, digest in V19_ARTIFACT_SHA256.items()
        if name != "remediation_v19_result.json"
    }
    if (
        result.get("schema_version") != SCHEMA_VERSION
        or result.get("eval_id") != V19_EVAL_ID
        or result.get("executor_attempt_ordinal") != 19
        or result.get("accepted_current_forward_result") is not True
        or result.get("executor_outcome") != "HOST_REPLAY_PASS"
        or result.get("independent_preexecution_timestamp") != PASS
        or result.get("artifact_bindings") != expected_bindings
        or result.get("decision_label") != raw_output.get("decision_label")
        or result.get("judge_consensus") != PASS
        or result.get("judge_verdicts") != [PASS, PASS]
        or result.get("judge_scores")
        != [judge["total_score"] for judge in judges]
        or result.get("outcome") != PASS
        or [item.get("ordinal") for item in result.get("prior_attempt_lineage", [])]
        != list(range(1, 19))
    ):
        raise ForwardTestError("v19 result identity/verdict/lineage drift")
    return {
        "status": PASS,
        "context_file_count": context["file_count"],
        "executor_trial_count": 19,
        "judge_count": 2,
        "maximum_score": 24,
        "total_score": min(judge["total_score"] for judge in judges),
    }


def _validate_provider_rfc3161_timestamp(
    forward_dir: Path,
    evidence_name: str,
    packet_name: str,
    attestation_id: str,
    phase: str,
) -> datetime:
    """Verify one two-sided provider-attestation timestamp offline."""

    label = f"{attestation_id} {phase} timestamp"
    evidence = _exact_keys(
        _load_json(forward_dir / evidence_name, label),
        {
            "schema_version",
            "attestation_id",
            "phase",
            "packet",
            "authority",
            "request",
            "response",
            "trust_anchor_reference",
            "verification",
        },
        label,
    )
    _current_forward_reject_session_metadata(evidence, label)
    authority = evidence["authority"]
    packet_binding = evidence["packet"]
    request_binding = evidence["request"]
    response_binding = evidence["response"]
    trust_reference = evidence["trust_anchor_reference"]
    verification = evidence["verification"]
    if (
        evidence["schema_version"] != SCHEMA_VERSION
        or evidence["attestation_id"] != attestation_id
        or evidence["phase"] != phase
        or authority
        != {
            "protocol": "RFC3161",
            "url": "http://timestamp.digicert.com",
            "digest_algorithm": "SHA-256",
        }
        or trust_reference
        != {
            "path": "evals/forward_test/preexecution_timestamp_v19.json",
            "sha256": V19_ARTIFACT_SHA256[
                "preexecution_timestamp_v19.json"
            ],
            "sha256_fingerprint": V19_TRUST_ANCHOR_SHA256_FINGERPRINT,
        }
        or verification.get("status") != PASS
        or verification.get("exact_packet_bytes_bound") is not True
    ):
        raise ForwardTestError(f"{label} identity drift")
    packet_path = forward_dir / packet_name
    packet_bytes = packet_path.read_bytes()
    if packet_binding != {
        "path": f"evals/forward_test/{packet_name}",
        "sha256": _sha256_bytes(packet_bytes),
        "byte_count": len(packet_bytes),
    }:
        raise ForwardTestError(f"{label} packet binding drift")
    try:
        request = base64.b64decode(
            request_binding["der_base64"], validate=True
        )
        response = base64.b64decode(
            response_binding["der_base64"], validate=True
        )
    except (KeyError, ValueError) as exc:
        raise ForwardTestError(f"{label} payload encoding drift") from exc
    for kind, payload, binding in (
        ("request", request, request_binding),
        ("response", response, response_binding),
    ):
        if (
            binding.get("encoding") != "base64-DER"
            or binding.get("sha256") != _sha256_bytes(payload)
            or binding.get("byte_count") != len(payload)
        ):
            raise ForwardTestError(f"{label} {kind} binding drift")
    if request_binding.get("message_imprint_sha256") != _sha256_bytes(
        packet_bytes
    ):
        raise ForwardTestError(f"{label} declared message imprint drift")
    trust_source_path = forward_dir / "preexecution_timestamp_v19.json"
    if (
        _sha256_path(trust_source_path, f"{label} trust source")
        != V19_ARTIFACT_SHA256["preexecution_timestamp_v19.json"]
    ):
        raise ForwardTestError(f"{label} trust source drift")
    trust_source = _load_json(trust_source_path, f"{label} trust source")
    try:
        root_pem = trust_source["trust_anchor"]["pem"].encode("ascii")
    except (KeyError, UnicodeError) as exc:
        raise ForwardTestError(f"{label} trust anchor drift") from exc

    with tempfile.TemporaryDirectory(prefix="bss-provider-ts-verify-") as raw:
        root = Path(raw)
        request_path = root / "request.tsq"
        response_path = root / "response.tsr"
        root_path = root / "root.pem"
        token_path = root / "token.der"
        chain_path = root / "chain.pem"
        request_path.write_bytes(request)
        response_path.write_bytes(response)
        root_path.write_bytes(root_pem)

        def run(*argv: str) -> subprocess.CompletedProcess[str]:
            completed = subprocess.run(
                ["openssl", *argv],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                raise ForwardTestError(
                    f"{label} RFC3161 verification failed: "
                    + completed.stderr.strip()
                )
            return completed

        certificate = run(
            "x509",
            "-in",
            str(root_path),
            "-noout",
            "-fingerprint",
            "-sha256",
        ).stdout
        fingerprint = certificate.split("=", 1)[-1].strip().upper()
        if fingerprint != V19_TRUST_ANCHOR_SHA256_FINGERPRINT:
            raise ForwardTestError(f"{label} trust anchor fingerprint drift")
        query_text = run(
            "ts", "-query", "-in", str(request_path), "-text"
        ).stdout
        if (
            "Hash Algorithm: sha256" not in query_text
            or _rfc3161_sha256_imprint(request)
            != _sha256_bytes(packet_bytes)
        ):
            raise ForwardTestError(f"{label} RFC3161 query imprint drift")
        run(
            "ts",
            "-reply",
            "-in",
            str(response_path),
            "-token_out",
            "-out",
            str(token_path),
        )
        run(
            "pkcs7",
            "-inform",
            "DER",
            "-in",
            str(token_path),
            "-print_certs",
            "-out",
            str(chain_path),
        )
        run(
            "ts",
            "-verify",
            "-queryfile",
            str(request_path),
            "-in",
            str(response_path),
            "-CAfile",
            str(root_path),
            "-untrusted",
            str(chain_path),
        )
        reply_text = run(
            "ts", "-reply", "-in", str(response_path), "-text"
        ).stdout
    if "Status: Granted." not in reply_text:
        raise ForwardTestError(f"{label} response is not granted")
    fields: dict[str, str] = {}
    for key, pattern in (
        ("policy_oid", r"^Policy OID:\s*(.+)$"),
        ("serial_number", r"^Serial number:\s*(.+)$"),
        ("nonce", r"^Nonce:\s*(.+)$"),
        ("time", r"^Time stamp:\s*(.+)$"),
    ):
        match = re.search(pattern, reply_text, flags=re.MULTILINE)
        if match is None:
            raise ForwardTestError(f"{label} response {key} is missing")
        fields[key] = match.group(1)
    try:
        observed_time = datetime.strptime(
            fields["time"], "%b %d %H:%M:%S %Y GMT"
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ForwardTestError(f"{label} response time is invalid") from exc
    declared_time = _current_forward_utc(
        response_binding.get("gen_time_utc"), f"{label} gen_time"
    )
    if (
        response_binding.get("status") != "GRANTED"
        or response_binding.get("policy_oid") != fields["policy_oid"]
        or response_binding.get("serial_number") != fields["serial_number"]
        or response_binding.get("nonce") != fields["nonce"]
        or declared_time != observed_time
    ):
        raise ForwardTestError(f"{label} response metadata drift")
    return observed_time


def _validate_provider_task_challenge(
    forward_dir: Path,
    version: int,
    response_sha256: str,
) -> None:
    template_path = (
        forward_dir / f"provider_attestation_v{version}_task.template.txt"
    )
    task_path = forward_dir / f"provider_attestation_v{version}_task.txt"
    template = template_path.read_text(encoding="utf-8")
    if template.count("<START_CHALLENGE_SHA256>") != 1:
        raise ForwardTestError(
            f"provider v{version} task-template challenge cardinality drift"
        )
    expected = template.replace(
        "<START_CHALLENGE_SHA256>", response_sha256
    )
    if task_path.read_text(encoding="utf-8") != expected:
        raise ForwardTestError(
            f"provider v{version} task challenge binding drift"
        )


def validate_provider_attestation_v22(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, int | str]:
    """Validate failed lineage plus the two-sided v22 provider receipt."""

    for name, expected in PROVIDER_ATTESTATION_ARTIFACT_SHA256.items():
        if _sha256_path(forward_dir / name, f"provider attestation {name}") != expected:
            raise ForwardTestError(f"provider attestation artifact drift: {name}")
    v20_pre = _validate_provider_rfc3161_timestamp(
        forward_dir,
        "provider_attestation_v20_pre_timestamp.json",
        "provider_attestation_v20_pre_packet.json",
        "BSS-S3-P3-T010-provider-attestation-v20",
        "preexecution",
    )
    v21_pre = _validate_provider_rfc3161_timestamp(
        forward_dir,
        "provider_attestation_v21_pre_timestamp.json",
        "provider_attestation_v21_pre_packet.json",
        "BSS-S3-P3-T010-provider-attestation-v21",
        "preexecution",
    )
    v22_pre = _validate_provider_rfc3161_timestamp(
        forward_dir,
        "provider_attestation_v22_pre_timestamp.json",
        "provider_attestation_v22_pre_packet.json",
        "BSS-S3-P3-T010-provider-attestation-v22",
        "preexecution",
    )
    v22_post = _validate_provider_rfc3161_timestamp(
        forward_dir,
        "provider_attestation_v22_post_timestamp.json",
        "provider_attestation_v22_post_packet.json",
        "BSS-S3-P3-T010-provider-attestation-v22",
        "postexecution",
    )
    if not (
        v20_pre
        == datetime(2026, 7, 23, 18, 32, 42, tzinfo=timezone.utc)
        < v21_pre
        == datetime(2026, 7, 23, 18, 35, 20, tzinfo=timezone.utc)
        < v22_pre
        == datetime(2026, 7, 23, 18, 38, 20, tzinfo=timezone.utc)
        < v22_post
        == datetime(2026, 7, 23, 18, 41, 45, tzinfo=timezone.utc)
    ):
        raise ForwardTestError("provider attestation RFC3161 ordering drift")
    for version, evidence_name in (
        (20, "provider_attestation_v20_pre_timestamp.json"),
        (21, "provider_attestation_v21_pre_timestamp.json"),
        (22, "provider_attestation_v22_pre_timestamp.json"),
    ):
        timestamp = _load_json(
            forward_dir / evidence_name, f"provider v{version} timestamp"
        )
        _validate_provider_task_challenge(
            forward_dir,
            version,
            timestamp["response"]["sha256"],
        )

    v20_failure = _load_json(
        forward_dir / "provider_attestation_v20_failure.json",
        "provider v20 failure",
    )
    if (
        v20_failure.get("outcome") != "PROVIDER_SCHEMA_PREFLIGHT_FAILURE"
        or v20_failure.get("substantive_provider_attestation") is not False
        or v20_failure.get("exit_code") != 1
        or v20_failure.get("preexecution_packet_sha256")
        != PROVIDER_ATTESTATION_ARTIFACT_SHA256[
            "provider_attestation_v20_pre_packet.json"
        ]
        or v20_failure.get("preexecution_timestamp_response_sha256")
        != _load_json(
            forward_dir / "provider_attestation_v20_pre_timestamp.json",
            "provider v20 timestamp",
        )["response"]["sha256"]
        or v20_failure.get("superseded_by")
        != "BSS-S3-P3-T010-provider-attestation-v21"
    ):
        raise ForwardTestError("provider v20 failed-lineage drift")

    v21_return = _load_json(
        forward_dir / "provider_attestation_v21_return.json",
        "provider v21 return",
    )
    v21_failure = _load_json(
        forward_dir / "provider_attestation_v21_failure.json",
        "provider v21 failure",
    )
    if (
        v21_return.get("start_challenge_sha256")
        != _load_json(
            forward_dir / "provider_attestation_v21_pre_timestamp.json",
            "provider v21 timestamp",
        )["response"]["sha256"]
        or v21_return.get("validated_subject", {}).get("validator_sha256")
        == PROVIDER_ATTESTATION_ARTIFACT_SHA256[
            "provider_attestation_v22_execution_validator.py"
        ]
        or v21_return.get("verdict") != PASS
        or v21_failure.get("outcome")
        != "HOST_OBSERVED_COMMAND_FAILURE_AND_FALSE_PROVIDER_PASS"
        or v21_failure.get("substantive_provider_attestation") is not False
        or v21_failure.get("provider_return", {}).get("claimed_verdict") != PASS
        or v21_failure.get("host_observation", {}).get(
            "validator_command_exit_code"
        )
        != 1
        or v21_failure.get("host_observation", {}).get(
            "provider_claim_matches_host_observation"
        )
        is not False
        or v21_failure.get("superseded_by")
        != "BSS-S3-P3-T010-provider-attestation-v22"
    ):
        raise ForwardTestError("provider v21 failed-lineage drift")

    expected_return = {
        "attestation_version": "1.0",
        "attestation_id": "BSS-S3-P3-T010-provider-attestation-v22",
        "start_challenge_sha256": _load_json(
            forward_dir / "provider_attestation_v22_pre_timestamp.json",
            "provider v22 timestamp",
        )["response"]["sha256"],
        "validated_subject": {
            "v19_result_sha256": V19_ARTIFACT_SHA256[
                "remediation_v19_result.json"
            ],
            "v19_raw_sha256": V19_ARTIFACT_SHA256[
                "remediation_v19_raw.json"
            ],
            "validator_sha256": PROVIDER_ATTESTATION_ARTIFACT_SHA256[
                "provider_attestation_v22_execution_validator.py"
            ],
        },
        "validation_command": (
            "python3 -B scripts/validate_forward_test.py --skill-root ."
        ),
        "validation_exit_code": 0,
        "validation_stdout": (
            "PASS: independent forward test; context=30; trials=19; "
            "judges=2; score=23/24"
        ),
        "validation_stdout_sha256": (
            "484844e2cad899cbca89bc1e38fb0d809e1638fa4890f198bc30bf2bf1a5f1ca"
        ),
        "provider_observation": {
            "status": PASS,
            "context_file_count": 30,
            "executor_trial_count": 19,
            "judge_count": 2,
            "score": 23,
            "maximum_score": 24,
        },
        "expected_answer_or_diagnosis_received": False,
        "verdict": PASS,
    }
    v22_return_path = forward_dir / "provider_attestation_v22_return.json"
    v22_return_bytes = v22_return_path.read_bytes()
    if _load_json(v22_return_path, "provider v22 return") != expected_return:
        raise ForwardTestError("provider v22 exact return contract drift")

    host = _load_json(
        forward_dir / "provider_attestation_v22_host_receipt.json",
        "provider v22 host receipt",
    )
    commands = host.get("host_observed_commands")
    first = commands[0] if isinstance(commands, list) and len(commands) == 2 else {}
    second = commands[1] if isinstance(commands, list) and len(commands) == 2 else {}
    if (
        host.get("attestation_id")
        != "BSS-S3-P3-T010-provider-attestation-v22"
        or host.get("execution", {}).get("cli_exit_code") != 0
        or host.get("preexecution_binding", {}).get(
            "timestamp_response_sha256"
        )
        != expected_return["start_challenge_sha256"]
        or host.get("provider_return")
        != {
            "path": "evals/forward_test/provider_attestation_v22_return.json",
            "sha256": _sha256_bytes(v22_return_bytes),
            "byte_count": len(v22_return_bytes),
            "output_schema_sha256": PROVIDER_ATTESTATION_ARTIFACT_SHA256[
                "provider_attestation_v22.schema.json"
            ],
            "schema_valid": True,
        }
        or first.get("command") != expected_return["validation_command"]
        or first.get("exit_code") != 0
        or first.get("stdout_sha256")
        != expected_return["validation_stdout_sha256"]
        or first.get("stdout")
        != expected_return["validation_stdout"] + "\n"
        or second.get("exit_code") != 0
        or second.get("observed_sha256")
        != {
            "v19_result": V19_ARTIFACT_SHA256[
                "remediation_v19_result.json"
            ],
            "v19_raw": V19_ARTIFACT_SHA256["remediation_v19_raw.json"],
            "validator": PROVIDER_ATTESTATION_ARTIFACT_SHA256[
                "provider_attestation_v22_execution_validator.py"
            ],
            "validator_stdout": expected_return[
                "validation_stdout_sha256"
            ],
        }
        or host.get("admission")
        != {
            "provisional_provider_message_before_command_ignored": True,
            "successful_validator_event_observed_before_accepted_final_return": True,
            "provider_return_matches_host_observation": True,
            "verdict": PASS,
        }
        or host.get("privacy", {}).get("provider_identifiers_persisted")
        is not False
        or host.get("privacy", {}).get("raw_event_stream_persisted") is not False
    ):
        raise ForwardTestError("provider v22 host observation drift")

    post = _load_json(
        forward_dir / "provider_attestation_v22_post_packet.json",
        "provider v22 post packet",
    )
    if (
        post.get("preexecution", {}).get("gen_time_utc")
        != "2026-07-23T18:38:20Z"
        or post.get("preexecution", {}).get("timestamp_response_sha256")
        != expected_return["start_challenge_sha256"]
        or post.get("execution", {}).get("host_receipt_sha256")
        != PROVIDER_ATTESTATION_ARTIFACT_SHA256[
            "provider_attestation_v22_host_receipt.json"
        ]
        or post.get("execution", {}).get("provider_return_sha256")
        != _sha256_bytes(v22_return_bytes)
        or post.get("execution", {}).get("provider_return_byte_count")
        != len(v22_return_bytes)
        or post.get("execution", {}).get(
            "provider_return_matches_host_observation"
        )
        is not True
        or post.get("subject", {}).get("execution_validator_sha256")
        != PROVIDER_ATTESTATION_ARTIFACT_SHA256[
            "provider_attestation_v22_execution_validator.py"
        ]
    ):
        raise ForwardTestError("provider v22 postexecution packet drift")

    result = _load_json(
        forward_dir / "provider_attestation_v22_result.json",
        "provider v22 result",
    )
    expected_bindings = {
        name: digest
        for name, digest in PROVIDER_ATTESTATION_ARTIFACT_SHA256.items()
        if name != "provider_attestation_v22_result.json"
    }
    interval = result.get("independent_time_binding")
    execution = result.get("independent_provider_execution")
    if (
        result.get("accepted_current_provider_attestation") is not True
        or result.get("subject_result_sha256")
        != V19_ARTIFACT_SHA256["remediation_v19_result.json"]
        or result.get("subject_raw_sha256")
        != V19_ARTIFACT_SHA256["remediation_v19_raw.json"]
        or result.get("artifact_bindings") != expected_bindings
        or not isinstance(interval, dict)
        or interval.get("preexecution_gen_time_utc")
        != "2026-07-23T18:38:20Z"
        or interval.get("postexecution_gen_time_utc")
        != "2026-07-23T18:41:45Z"
        or interval.get("cryptographic_interval_seconds") != 205
        or interval.get("start_challenge_is_preexecution_response_sha256")
        is not True
        or interval.get("challenge_echoed_in_exact_provider_return") is not True
        or interval.get(
            "postexecution_packet_binds_exact_provider_return_and_host_receipt"
        )
        is not True
        or interval.get("self_declared_execution_times_required_for_acceptance")
        is not False
        or interval.get("whole_timeline_shift_mutant") != "REJECT"
        or not isinstance(execution, dict)
        or execution.get("host_observed_validator_exit_code") != 0
        or execution.get("exact_provider_return_sha256")
        != _sha256_bytes(v22_return_bytes)
        or execution.get("exact_provider_return_byte_count")
        != len(v22_return_bytes)
        or execution.get("provider_return_matches_host_observation") is not True
        or result.get("outcome") != PASS
    ):
        raise ForwardTestError("provider v22 result contract drift")
    return {
        "provider_v22_disposition": "NOT_PROVIDER_GENERATION_PROOF",
        "provider_attestation_attempt_count": 3,
        "provider_interval_seconds": 205,
    }


def validate_provider_generation_v23(
    skill_root: Path,
    forward_dir: Path,
) -> dict[str, int | str]:
    """Validate the T017-runnable fresh-generation witness without self-closing it."""

    for name, expected in PROVIDER_GENERATION_V23_ARTIFACT_SHA256.items():
        if _sha256_path(forward_dir / name, f"provider generation {name}") != expected:
            raise ForwardTestError(f"provider generation artifact drift: {name}")
    disposition = _load_json(
        forward_dir / "provider_attestation_v22_review_disposition.json",
        "provider v22 review disposition",
    )
    if disposition != {
        "schema_version": "1.0",
        "finding_id": "S3-R002",
        "review_task": "BSS-S3-P3-T011",
        "remediation_task": "BSS-S3-P3-T012",
        "historical_artifact": "provider_attestation_v22_result.json",
        "historical_artifact_sha256": PROVIDER_ATTESTATION_ARTIFACT_SHA256[
            "provider_attestation_v22_result.json"
        ],
        "admissible_as_provider_generation_proof": False,
        "reason": (
            "The v22 provider return and host receipt were unauthenticated "
            "local JSON, and the provider validated an already-produced v19 "
            "answer instead of generating that answer."
        ),
        "replacement_protocol": "provider_generation_v23_protocol.json",
        "replacement_rule": (
            "T013 must directly observe a fresh ephemeral provider process "
            "generate the actual answer inside the explicit denied-source "
            "projection "
            "and then observe the exact-byte host replay."
        ),
        "status": "FIXED_PENDING_REREVIEW",
    }:
        raise ForwardTestError("provider v22 review disposition drift")
    witness = subprocess.run(
        [
            sys.executable,
            "-B",
            str(forward_dir / "provider_generation_witness_v23.py"),
            "--skill-root",
            str(skill_root),
        ],
        cwd=skill_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        observed = json.loads(witness.stdout)
    except json.JSONDecodeError as exc:
        raise ForwardTestError("provider v23 witness self-check is not JSON") from exc
    if (
        witness.returncode != 0
        or observed.get("status") != PASS
        or observed.get("protocol_id")
        != "BSS-S3-P3-T016-provider-generation-v23"
        or observed.get("production_file_count") != 30
        or observed.get("live_reviewer_observation_required") is not True
        or observed.get("task_sha256")
        != PROVIDER_GENERATION_V23_ARTIFACT_SHA256[
            "provider_generation_v23_task.txt"
        ]
        or observed.get("schema_sha256")
        != PROVIDER_GENERATION_V23_ARTIFACT_SHA256[
            "provider_generation_v23.schema.json"
        ]
        or observed.get("witness_sha256")
        != PROVIDER_GENERATION_V23_ARTIFACT_SHA256[
            "provider_generation_witness_v23.py"
        ]
    ):
        raise ForwardTestError("provider v23 live-witness protocol drift")
    return {
        "provider_provenance": "LIVE_WITNESS_READY",
        "provider_generation_protocol": PASS,
        "provider_live_review_task": "BSS-S3-P3-T017",
    }


def validate_all(
    skill_root: Path = SKILL_ROOT,
    preregistration_path: Path | None = None,
    context_path: Path | None = None,
    raw_output_path: Path | None = None,
    trace_path: Path | None = None,
    judge_paths: tuple[Path, Path] | None = None,
    result_path: Path | None = None,
    rubric_path: Path | None = None,
) -> dict[str, int | str]:
    forward_dir = skill_root / "evals" / "forward_test"
    preregistration_path = preregistration_path or forward_dir / "preregistration.json"
    context_path = context_path or forward_dir / "context_manifest.json"
    raw_output_path = raw_output_path or forward_dir / "raw_output.md"
    trace_path = trace_path or forward_dir / "trace.json"
    judge_paths = judge_paths or (
        forward_dir / "judge_a.json",
        forward_dir / "judge_b.json",
    )
    result_path = result_path or forward_dir / "result.json"
    rubric_path = rubric_path or skill_root / "evals" / "rubric.md"
    try:
        observed_files = {
            path.name for path in forward_dir.iterdir() if path.is_file()
        }
        non_files = [path.name for path in forward_dir.iterdir() if not path.is_file()]
    except OSError as exc:
        raise ForwardTestError("forward-test evidence directory is missing") from exc
    if observed_files != EXPECTED_FORWARD_FILES or non_files:
        raise ForwardTestError(
            "forward-test evidence file set drift: "
            f"observed={sorted(observed_files)} non_files={sorted(non_files)}"
        )
    baseline_result = validate_baseline(forward_dir, rubric_path)
    validate_remediation_01(forward_dir, baseline_result)
    trial_02_result = validate_trial_02(forward_dir, rubric_path)
    validate_preregistration(preregistration_path, context_path, rubric_path)
    context = validate_context_manifest(context_path, skill_root)
    validate_remediation(
        forward_dir,
        preregistration_path,
        context_path,
        baseline_result,
        trial_02_result,
    )
    validate_trace(
        trace_path,
        raw_output_path,
        preregistration_path,
        context_path,
        rubric_path,
    )
    validate_result(
        result_path,
        preregistration_path,
        context_path,
        raw_output_path,
        trace_path,
        judge_paths,
        rubric_path,
    )
    validate_failed_schema_lineage(forward_dir)
    validate_current_forward(skill_root, forward_dir)
    summary = validate_v19_forward(skill_root, forward_dir)
    summary.update(validate_provider_attestation_v22(skill_root, forward_dir))
    summary.update(validate_provider_generation_v23(skill_root, forward_dir))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-root",
        type=Path,
        default=SKILL_ROOT,
        help="canonical Skill root to validate",
    )
    args = parser.parse_args()
    try:
        summary = validate_all(args.skill_root.resolve())
    except ForwardTestError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    if summary["status"] != PASS:
        raise SystemExit(f"FAIL: forward-test verdict={summary['status']}")
    print(
        "PASS: independent forward test; "
        f"context={summary['context_file_count']}; "
        f"trials={summary['executor_trial_count']}; "
        f"judges={summary['judge_count']}; "
        f"score={summary['total_score']}/{summary['maximum_score']}; "
        f"provider_provenance={summary['provider_provenance']}; "
        f"provider_attempts={summary['provider_attestation_attempt_count']}"
    )


if __name__ == "__main__":
    main()

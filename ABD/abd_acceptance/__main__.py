from __future__ import annotations

import argparse
import json
from pathlib import Path

from .authorization import write_phase_evidence as write_authorization_phase_evidence
from .budget import write_phase_evidence as write_budget_phase_evidence
from .canonical_facts import write_phase_evidence as write_canonical_phase_evidence
from .external_consent import write_phase_evidence as write_external_consent_phase_evidence
from .stage_review import write_stage_review_evidence
from .stage1_review import write_stage1_review_evidence
from .customer_press_release import write_phase_evidence as write_customer_press_release_phase_evidence
from .customer_faq import write_phase_evidence as write_customer_faq_phase_evidence
from .requirements_scope import write_phase_evidence as write_requirements_scope_phase_evidence
from .metrics_economics import write_phase_evidence as write_metrics_economics_phase_evidence
from .delivery import cli_verify_stage0_delivery
from .stage1_delivery import cli_verify_stage1_delivery
from .stage2_delivery import cli_verify_stage2_delivery
from .stage3_delivery import cli_verify_stage3_delivery
from .stage4_delivery import cli_verify_stage4_delivery
from .official_platform_research import write_phase_evidence as write_official_platform_research_phase_evidence
from .model_risk_research import write_phase_evidence as write_model_risk_research_phase_evidence
from .open_source_reuse import write_phase_evidence as write_open_source_reuse_phase_evidence
from .research_gap_audit import write_phase_evidence as write_research_gap_audit_phase_evidence
from .stage2_review import write_stage2_review_evidence
from .terminology_governance import write_phase_evidence as write_terminology_governance_phase_evidence
from .advice_card import write_phase_evidence as write_advice_card_phase_evidence
from .reason_next_action import write_phase_evidence as write_reason_next_action_phase_evidence
from .usability_accessibility import write_phase_evidence as write_usability_accessibility_phase_evidence
from .stage3_review import write_stage3_review_evidence
from .infrastructure_iac import write_phase_evidence as write_infrastructure_iac_phase_evidence
from .cloudflare_edge import write_phase_evidence as write_cloudflare_edge_phase_evidence
from .release_control import write_phase_evidence as write_release_control_phase_evidence
from .capacity_governance import write_phase_evidence as write_capacity_governance_phase_evidence
from .stage4_review import write_stage4_review_evidence
from .market_ontology import write_phase_evidence as write_market_ontology_phase_evidence
from .source_capabilities import write_phase_evidence as write_source_capability_phase_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD fail-closed acceptance oracle")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contract", help="acceptance contract id")
    mode.add_argument("--verify-existing", help="read-only verification of an existing delivery receipt")
    parser.add_argument(
        "--evidence",
        default="machine/evidence",
        help="evidence directory, relative to --root unless absolute",
    )
    parser.add_argument("--root", default=".", help="ABD project root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    evidence_dir = Path(args.evidence)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir

    if args.verify_existing:
        existing_verifiers = {
            "STAGE-REVIEW-S00": cli_verify_stage0_delivery,
            "STAGE-REVIEW-S01": cli_verify_stage1_delivery,
            "STAGE-REVIEW-S02": cli_verify_stage2_delivery,
            "STAGE-REVIEW-S03": cli_verify_stage3_delivery,
            "STAGE-REVIEW-S04": cli_verify_stage4_delivery,
        }
        if args.verify_existing not in existing_verifiers:
            parser.error("existing evidence verifier is not implemented: %s" % args.verify_existing)
        result = existing_verifiers[args.verify_existing](root)
        print(
            json.dumps(
                {
                    "contract_id": result["contract_id"],
                    "status": result["status"],
                    "evidence": result["evidence_path"],
                    "evidence_sha256": result["evidence_sha256"],
                    "next": result["next"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if result["status"] == "PASS" else 1

    writers = {
        "AC-S00-P01": write_canonical_phase_evidence,
        "AC-S00-P02": write_authorization_phase_evidence,
        "AC-S00-P03": write_budget_phase_evidence,
        "AC-S00-P04": write_external_consent_phase_evidence,
        "STAGE-REVIEW-S00": write_stage_review_evidence,
        "AC-S01-P01": write_customer_press_release_phase_evidence,
        "AC-S01-P02": write_customer_faq_phase_evidence,
        "AC-S01-P03": write_requirements_scope_phase_evidence,
        "AC-S01-P04": write_metrics_economics_phase_evidence,
        "STAGE-REVIEW-S01": write_stage1_review_evidence,
        "AC-S02-P01": write_official_platform_research_phase_evidence,
        "AC-S02-P02": write_model_risk_research_phase_evidence,
        "AC-S02-P03": write_open_source_reuse_phase_evidence,
        "AC-S02-P04": write_research_gap_audit_phase_evidence,
        "STAGE-REVIEW-S02": write_stage2_review_evidence,
        "AC-S03-P01": write_terminology_governance_phase_evidence,
        "AC-S03-P02": write_advice_card_phase_evidence,
        "AC-S03-P03": write_reason_next_action_phase_evidence,
        "AC-S03-P04": write_usability_accessibility_phase_evidence,
        "STAGE-REVIEW-S03": write_stage3_review_evidence,
        "AC-S04-P01": write_infrastructure_iac_phase_evidence,
        "AC-S04-P02": write_cloudflare_edge_phase_evidence,
        "AC-S04-P03": write_release_control_phase_evidence,
        "AC-S04-P04": write_capacity_governance_phase_evidence,
        "STAGE-REVIEW-S04": write_stage4_review_evidence,
        "AC-S05-P01": write_market_ontology_phase_evidence,
        "AC-S05-P02": write_source_capability_phase_evidence,
    }
    if args.contract not in writers:
        parser.error("contract is not implemented: %s" % args.contract)
    result = writers[args.contract](root, evidence_dir)
    print(
        json.dumps(
            {
                "contract_id": result["contract_id"],
                "status": result["status"],
                "evidence": result["evidence_path"],
                "evidence_sha256": result["evidence_sha256"],
                "next": result["next"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

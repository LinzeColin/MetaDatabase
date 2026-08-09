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
from .stage5_delivery import cli_verify_stage5_delivery
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
from .source_scheduler import write_phase_evidence as write_source_scheduler_phase_evidence
from .coverage_observability import write_phase_evidence as write_coverage_observability_phase_evidence
from .stage5_review import write_stage5_review_evidence
from .stage11_review import verify_existing_stage_review_evidence, write_stage_review_evidence as write_stage11_review_evidence
from .stage12_review import verify_existing_stage_review_evidence as verify_existing_stage12_review_evidence
from .stage12_review import write_stage_review_evidence as write_stage12_review_evidence
from .stage13_review import verify_existing_stage_review_evidence as verify_existing_stage13_review_evidence
from .stage13_review import write_stage_review_evidence as write_stage13_review_evidence
from .stage14_review import verify_existing_stage_review_evidence as verify_existing_stage14_review_evidence
from .stage14_review import write_stage_review_evidence as write_stage14_review_evidence
from .gmail_authorization import write_phase_evidence as write_gmail_authorization_phase_evidence
from .mail_preservation import write_phase_evidence as write_mail_preservation_phase_evidence
from .attachment_security import write_phase_evidence as write_attachment_security_phase_evidence
from .mail_deletion_audit import write_phase_evidence as write_mail_deletion_audit_phase_evidence
from .stage6_review import write_stage6_review_evidence
from .identity_resolution import write_phase_evidence as write_identity_resolution_phase_evidence
from .temporal_lineage import write_phase_evidence as write_temporal_lineage_phase_evidence
from .ledger_trace import write_phase_evidence as write_ledger_trace_phase_evidence
from .evidence_continuity import write_phase_evidence as write_evidence_continuity_phase_evidence
from .devig import verify_existing_phase_evidence as verify_devig_phase_evidence
from .devig import write_phase_evidence as write_devig_phase_evidence
from .source_independence import verify_existing_phase_evidence as verify_source_independence_phase_evidence
from .source_independence import write_phase_evidence as write_source_independence_phase_evidence
from .market_consensus import verify_existing_phase_evidence as verify_market_consensus_phase_evidence
from .market_consensus import write_phase_evidence as write_market_consensus_phase_evidence
from .outlier_line_movement import verify_existing_phase_evidence as verify_outlier_line_movement_phase_evidence
from .outlier_line_movement import write_phase_evidence as write_outlier_line_movement_phase_evidence
from .generic_residual import verify_existing_phase_evidence as verify_generic_residual_phase_evidence
from .generic_residual import write_phase_evidence as write_generic_residual_phase_evidence
from .tennis_combat_models import verify_existing_phase_evidence as verify_tennis_combat_models_phase_evidence
from .tennis_combat_models import write_phase_evidence as write_tennis_combat_models_phase_evidence
from .score_football_models import verify_existing_phase_evidence as verify_score_football_models_phase_evidence
from .score_football_models import write_phase_evidence as write_score_football_models_phase_evidence
from .multi_sport_fallback import verify_existing_phase_evidence as verify_multi_sport_fallback_phase_evidence
from .multi_sport_fallback import write_phase_evidence as write_multi_sport_fallback_phase_evidence
from .temporal_calibration import verify_existing_phase_evidence as verify_temporal_calibration_phase_evidence
from .temporal_calibration import write_phase_evidence as write_temporal_calibration_phase_evidence
from .uncertainty import verify_existing_phase_evidence as verify_uncertainty_phase_evidence
from .uncertainty import write_phase_evidence as write_uncertainty_phase_evidence
from .decimal_math import verify_existing_phase_evidence as verify_decimal_math_phase_evidence
from .decimal_math import write_phase_evidence as write_decimal_math_phase_evidence
from .robustness_gate import verify_existing_phase_evidence as verify_robustness_gate_phase_evidence
from .robustness_gate import write_phase_evidence as write_robustness_gate_phase_evidence
from .friction import verify_existing_phase_evidence as verify_friction_phase_evidence
from .friction import write_phase_evidence as write_friction_phase_evidence
from .decision_gate import verify_existing_phase_evidence as verify_decision_gate_phase_evidence
from .decision_gate import write_phase_evidence as write_decision_gate_phase_evidence
from .platform_router import verify_existing_phase_evidence as verify_platform_router_phase_evidence
from .platform_router import write_phase_evidence as write_platform_router_phase_evidence
from .risk_engine import verify_existing_phase_evidence as verify_risk_engine_phase_evidence
from .risk_engine import write_phase_evidence as write_risk_engine_phase_evidence
from .target_curve import verify_existing_phase_evidence as verify_target_curve_phase_evidence
from .target_curve import write_phase_evidence as write_target_curve_phase_evidence
from .capacity_correlation import verify_existing_phase_evidence as verify_capacity_correlation_phase_evidence
from .capacity_correlation import write_phase_evidence as write_capacity_correlation_phase_evidence
from .economics_sensitivity import verify_existing_phase_evidence as verify_economics_sensitivity_phase_evidence
from .economics_sensitivity import write_phase_evidence as write_economics_sensitivity_phase_evidence
from .target_falsification_gate import verify_existing_phase_evidence as verify_target_falsification_phase_evidence
from .target_falsification_gate import write_phase_evidence as write_target_falsification_phase_evidence
from .chinese_workbench import verify_existing_phase_evidence as verify_chinese_workbench_phase_evidence
from .chinese_workbench import write_phase_evidence as write_chinese_workbench_phase_evidence
from .platform_quote_check import verify_existing_phase_evidence as verify_platform_quote_check_phase_evidence
from .platform_quote_check import write_phase_evidence as write_platform_quote_check_phase_evidence
from .post_advice_settlement import verify_existing_phase_evidence as verify_post_advice_settlement_phase_evidence
from .post_advice_settlement import write_phase_evidence as write_post_advice_settlement_phase_evidence
from .journey_paths import verify_existing_phase_evidence as verify_journey_paths_phase_evidence
from .journey_paths import write_phase_evidence as write_journey_paths_phase_evidence
from .threat_model import verify_existing_phase_evidence as verify_threat_model_phase_evidence
from .threat_model import write_phase_evidence as write_threat_model_phase_evidence
from .security_analysis import verify_existing_phase_evidence as verify_security_analysis_phase_evidence
from .security_analysis import write_phase_evidence as write_security_analysis_phase_evidence
from .component_governance import verify_existing_phase_evidence as verify_component_governance_phase_evidence
from .component_governance import write_phase_evidence as write_component_governance_phase_evidence
from .artifact_provenance import verify_existing_phase_evidence as verify_artifact_provenance_phase_evidence
from .artifact_provenance import write_phase_evidence as write_artifact_provenance_phase_evidence
from .software_correctness import verify_existing_phase_evidence as verify_software_correctness_phase_evidence
from .software_correctness import write_phase_evidence as write_software_correctness_phase_evidence
from .source_contract_integration import verify_existing_phase_evidence as verify_source_contract_integration_phase_evidence
from .source_contract_integration import write_phase_evidence as write_source_contract_integration_phase_evidence
from .e2e_multi_environment import verify_existing_phase_evidence as verify_e2e_multi_environment_phase_evidence
from .e2e_multi_environment import write_phase_evidence as write_e2e_multi_environment_phase_evidence


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
            "STAGE-REVIEW-S05": cli_verify_stage5_delivery,
            "AC-S08-P01": verify_devig_phase_evidence,
            "AC-S08-P02": verify_source_independence_phase_evidence,
            "AC-S08-P03": verify_market_consensus_phase_evidence,
            "AC-S08-P04": verify_outlier_line_movement_phase_evidence,
            "AC-S09-P01": verify_generic_residual_phase_evidence,
            "AC-S09-P02": verify_tennis_combat_models_phase_evidence,
            "AC-S09-P03": verify_score_football_models_phase_evidence,
            "AC-S09-P04": verify_multi_sport_fallback_phase_evidence,
            "AC-S10-P01": verify_temporal_calibration_phase_evidence,
            "AC-S10-P02": verify_uncertainty_phase_evidence,
            "AC-S10-P03": verify_decimal_math_phase_evidence,
            "AC-S10-P04": verify_robustness_gate_phase_evidence,
            "AC-S11-P01": verify_friction_phase_evidence,
            "AC-S11-P02": verify_decision_gate_phase_evidence,
            "AC-S11-P03": verify_platform_router_phase_evidence,
            "AC-S11-P04": verify_risk_engine_phase_evidence,
            "AC-S12-P01": verify_target_curve_phase_evidence,
            "AC-S12-P02": verify_capacity_correlation_phase_evidence,
            "AC-S12-P03": verify_economics_sensitivity_phase_evidence,
            "AC-S12-P04": verify_target_falsification_phase_evidence,
            "AC-S13-P01": verify_chinese_workbench_phase_evidence,
            "AC-S13-P02": verify_platform_quote_check_phase_evidence,
            "AC-S13-P03": verify_post_advice_settlement_phase_evidence,
            "AC-S13-P04": verify_journey_paths_phase_evidence,
            "AC-S14-P01": verify_threat_model_phase_evidence,
            "AC-S14-P02": verify_security_analysis_phase_evidence,
            "AC-S14-P03": verify_component_governance_phase_evidence,
            "AC-S14-P04": verify_artifact_provenance_phase_evidence,
            "AC-S15-P01": verify_software_correctness_phase_evidence,
            "AC-S15-P02": verify_source_contract_integration_phase_evidence,
            "AC-S15-P03": verify_e2e_multi_environment_phase_evidence,
            "STAGE-REVIEW-S11": verify_existing_stage_review_evidence,
            "STAGE-REVIEW-S12": verify_existing_stage12_review_evidence,
            "STAGE-REVIEW-S13": verify_existing_stage13_review_evidence,
            "STAGE-REVIEW-S14": verify_existing_stage14_review_evidence,
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
        "AC-S05-P03": write_source_scheduler_phase_evidence,
        "AC-S05-P04": write_coverage_observability_phase_evidence,
        "STAGE-REVIEW-S05": write_stage5_review_evidence,
        "AC-S06-P01": write_gmail_authorization_phase_evidence,
        "AC-S06-P02": write_mail_preservation_phase_evidence,
        "AC-S06-P03": write_attachment_security_phase_evidence,
        "AC-S06-P04": write_mail_deletion_audit_phase_evidence,
        "STAGE-REVIEW-S06": write_stage6_review_evidence,
        "AC-S07-P01": write_identity_resolution_phase_evidence,
        "AC-S07-P02": write_temporal_lineage_phase_evidence,
        "AC-S07-P03": write_ledger_trace_phase_evidence,
        "AC-S07-P04": write_evidence_continuity_phase_evidence,
        "AC-S08-P01": write_devig_phase_evidence,
        "AC-S08-P02": write_source_independence_phase_evidence,
        "AC-S08-P03": write_market_consensus_phase_evidence,
        "AC-S08-P04": write_outlier_line_movement_phase_evidence,
        "AC-S09-P01": write_generic_residual_phase_evidence,
        "AC-S09-P02": write_tennis_combat_models_phase_evidence,
        "AC-S09-P03": write_score_football_models_phase_evidence,
        "AC-S09-P04": write_multi_sport_fallback_phase_evidence,
        "AC-S10-P01": write_temporal_calibration_phase_evidence,
        "AC-S10-P02": write_uncertainty_phase_evidence,
        "AC-S10-P03": write_decimal_math_phase_evidence,
        "AC-S10-P04": write_robustness_gate_phase_evidence,
        "AC-S11-P01": write_friction_phase_evidence,
        "AC-S11-P02": write_decision_gate_phase_evidence,
        "AC-S11-P03": write_platform_router_phase_evidence,
        "AC-S11-P04": write_risk_engine_phase_evidence,
        "AC-S12-P01": write_target_curve_phase_evidence,
        "AC-S12-P02": write_capacity_correlation_phase_evidence,
        "AC-S12-P03": write_economics_sensitivity_phase_evidence,
        "AC-S12-P04": write_target_falsification_phase_evidence,
        "AC-S13-P01": write_chinese_workbench_phase_evidence,
        "AC-S13-P02": write_platform_quote_check_phase_evidence,
        "AC-S13-P03": write_post_advice_settlement_phase_evidence,
        "AC-S13-P04": write_journey_paths_phase_evidence,
        "AC-S14-P01": write_threat_model_phase_evidence,
        "AC-S14-P02": write_security_analysis_phase_evidence,
        "AC-S14-P03": write_component_governance_phase_evidence,
        "AC-S14-P04": write_artifact_provenance_phase_evidence,
        "AC-S15-P01": write_software_correctness_phase_evidence,
        "AC-S15-P02": write_source_contract_integration_phase_evidence,
        "AC-S15-P03": write_e2e_multi_environment_phase_evidence,
        "STAGE-REVIEW-S11": write_stage11_review_evidence,
        "STAGE-REVIEW-S12": write_stage12_review_evidence,
        "STAGE-REVIEW-S13": write_stage13_review_evidence,
        "STAGE-REVIEW-S14": write_stage14_review_evidence,
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

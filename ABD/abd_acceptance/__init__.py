"""ABD deterministic acceptance oracles.

Proprietary project code. No order-submission capability is implemented here.
"""

from .canonical_facts import (
    DuplicateKeyError,
    build_evidence,
    evaluate_contract,
    perform_rollback_drill,
    strict_json_load,
    write_phase_evidence,
)
from .authorization import (
    build_evidence as build_authorization_evidence,
    evaluate_contract as evaluate_authorization_contract,
    perform_rollback_drill as perform_authorization_rollback_drill,
    write_phase_evidence as write_authorization_phase_evidence,
)
from .budget import (
    build_evidence as build_budget_evidence,
    evaluate_contract as evaluate_budget_contract,
    perform_rollback_drill as perform_budget_rollback_drill,
    render_scan_report,
    scan_dependency_budget,
    write_phase_evidence as write_budget_phase_evidence,
    write_scan_report,
)
from .external_consent import (
    build_evidence as build_external_consent_evidence,
    evaluate_contract as evaluate_external_consent_contract,
    parse_runbook_contract,
    perform_rollback_drill as perform_external_consent_rollback_drill,
    resolve_consent_event,
    validate_consent_receipt,
    write_phase_evidence as write_external_consent_phase_evidence,
)
from .stage_review import (
    build_evidence as build_stage_review_evidence,
    evaluate_contract as evaluate_stage_review_contract,
    perform_rollback_drill as perform_stage_review_rollback_drill,
    write_stage_review_evidence,
)
from .delivery import verify_stage0_delivery
from .customer_press_release import (
    build_evidence as build_customer_press_release_evidence,
    evaluate_contract as evaluate_customer_press_release_contract,
    perform_rollback_drill as perform_customer_press_release_rollback_drill,
    resolve_card_decision,
    write_phase_evidence as write_customer_press_release_phase_evidence,
)
from .customer_faq import (
    build_evidence as build_customer_faq_evidence,
    evaluate_contract as evaluate_customer_faq_contract,
    perform_rollback_drill as perform_customer_faq_rollback_drill,
    resolve_mail_default,
    resolve_recommendation_default,
    resolve_zero_budget_default,
    write_phase_evidence as write_customer_faq_phase_evidence,
)

__all__ = [
    "DuplicateKeyError",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "strict_json_load",
    "write_phase_evidence",
    "build_authorization_evidence",
    "evaluate_authorization_contract",
    "perform_authorization_rollback_drill",
    "write_authorization_phase_evidence",
    "build_budget_evidence",
    "evaluate_budget_contract",
    "perform_budget_rollback_drill",
    "render_scan_report",
    "scan_dependency_budget",
    "write_budget_phase_evidence",
    "write_scan_report",
    "build_external_consent_evidence",
    "evaluate_external_consent_contract",
    "parse_runbook_contract",
    "perform_external_consent_rollback_drill",
    "resolve_consent_event",
    "validate_consent_receipt",
    "write_external_consent_phase_evidence",
    "build_stage_review_evidence",
    "evaluate_stage_review_contract",
    "perform_stage_review_rollback_drill",
    "write_stage_review_evidence",
    "verify_stage0_delivery",
    "build_customer_press_release_evidence",
    "evaluate_customer_press_release_contract",
    "perform_customer_press_release_rollback_drill",
    "resolve_card_decision",
    "write_customer_press_release_phase_evidence",
    "build_customer_faq_evidence",
    "evaluate_customer_faq_contract",
    "perform_customer_faq_rollback_drill",
    "resolve_mail_default",
    "resolve_recommendation_default",
    "resolve_zero_budget_default",
    "write_customer_faq_phase_evidence",
]

#!/usr/bin/env python3
"""Validate candidate-bound Stage 6 execution and Codex review provenance.

The repository records hashes and Codex platform task identifiers, not a signed third-party
attestation.  A platform task identifier remains independently auditable only while the owning
Codex thread audit log is retained; the schema makes that limitation explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validate_evidence import (  # noqa: E402
    validate_stage6_candidate_bundle,
    validate_stage6_receipt_anchor,
)

sys.dont_write_bytecode = True

REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
BASELINE_COMMIT = "2b8625a83e69093b9dce989f4eb964556e1b5fa2"
RMD05_PREDECESSOR_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.5.json")
RMD05_PREDECESSOR_MANIFEST_SHA256 = "f99413b9c1fb67369ba3039a7acfeb437004d1aad8cb54dc3697f87f38e35cb3"  # pragma: allowlist secret  # noqa: E501
INITIAL_CANDIDATE_COMMIT = (
    "be8e196b03dcc475ed6261fbe20593b08bd26bcf"  # pragma: allowlist secret  # noqa: E501
)
INITIAL_CANDIDATE_TREE = (
    "56e8dce97168bab0ba5b57fe0cb580267776d94e"  # pragma: allowlist secret  # noqa: E501
)
INITIAL_REQUEST_SHA256 = "35247bddc79077b568509097cb9285e9a05299180a2833c8238b1cadac6c4e93"  # pragma: allowlist secret  # noqa: E501
REQUIRED_DIMENSIONS = {"SCOPE", "EVIDENCE_QUALITY", "FAILURE_HONESTY", "ROLLBACK"}
REQUIRED_FINAL_CLOSURE_FINDINGS = {
    "RMD05-CLOSURE-002",
    "RMD05-CLOSURE-003",
    "RMD05-CLOSURE-004",
    "RMD05-CLOSURE-005",
    "RMD05-CLOSURE-006",
    "RMD05-CLOSURE-007",
    "RMD05-CLOSURE-008",
    "RMD05-CLOSURE-009",
    "RMD05-CLOSURE-010",
    "RMD05-CLOSURE-011",
    "RMD05-CLOSURE-012",
}
LEGACY_COMMAND_IDS = {
    "container-build",
    "container-cleanup",
    "container-smoke",
    "dependency-audit",
    "governance-validation",
    "mypy-strict",
    "package-build",
    "publication-scan",
    "remediation-tests",
    "ruff-format",
    "ruff-lint",
    "sbom-reproducibility",
    "secret-scan",
    "stage6-task-tests",
    "stage7-runtime-regression-tests",
}
EXPECTED_COMMAND_IDS = LEGACY_COMMAND_IDS | {
    "assurance-history",
    "delivery-status-validation",
    "governance-facts-check",
    "stage6-validation",
}
BLOCKED_REVIEW_ATTEMPTS_PER_MODEL = 17
FINAL_REVIEW_ATTEMPTS_PER_MODEL = 18
CANDIDATE_BOUND_LOCAL_GATE_COMMANDS = len(EXPECTED_COMMAND_IDS)
LOCAL_PATH_MARKERS = (
    "/Users/",
    "/home/",
    "/private/tmp/",
    "/var/folders/",
    "C:\\Users\\",
)
SENSITIVE_RECEIPT_OUTPUT = (
    re.compile(r"AGE-SECRET-KEY-1[0-9a-z]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"1//[A-Za-z0-9_-]{20,}"),
)
ADVERSE_CANDIDATE_COMMIT = (
    "e456bdae5d7fbca69fdd2b2f605c515d4584377c"  # pragma: allowlist secret  # noqa: E501
)
ADVERSE_CANDIDATE_TREE = (
    "15625ffd5526a45aafa33d9c0b19f3b578ef5723"  # pragma: allowlist secret  # noqa: E501
)
ADVERSE_REQUEST_SHA256 = "e3fa55cb020a66dd2f17915f4015f0e62942e0aef1c93bc6152f193933fb85f4"  # pragma: allowlist secret  # noqa: E501
ADVERSE_RECEIPT_SHA256 = "aed2a3dd2d5df19536e49d963755e229b0d4ac569365fb74f58df99fc72fd1fc"  # pragma: allowlist secret  # noqa: E501
ADVERSE_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt.json"
SUPERSEDED_CANDIDATE_COMMIT = (
    "d3c1d9144cd5a063662a15d85c93f5a589389cf0"  # pragma: allowlist secret  # noqa: E501
)
SUPERSEDED_CANDIDATE_TREE = (
    "1d558f73ff2efdcd6f27dce635fa130a12a0fd0b"  # pragma: allowlist secret  # noqa: E501
)
SUPERSEDED_REQUEST_SHA256 = "f57ca7d53d2dee988b6067d6ce8f4ff4bc17eb849e134c3f5802c318bdbb1c79"  # pragma: allowlist secret  # noqa: E501
SUPERSEDED_RECEIPT_SHA256 = "e6d076632bcc36b410a04765bd4d3ebc69af16849266b3da429b7f0eb4cc9380"  # pragma: allowlist secret  # noqa: E501
SUPERSEDED_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt2.json"
TRANSITION_CANDIDATE_COMMIT = (
    "7524ea0401cda4a5c9b2809f4400b55a9b62747c"  # pragma: allowlist secret  # noqa: E501
)
TRANSITION_CANDIDATE_TREE = (
    "2ec39b324f1839e82f2bc768fe75a39a6f035e93"  # pragma: allowlist secret  # noqa: E501
)
TRANSITION_REQUEST_SHA256 = "113b08b9262cee2c0e3900e32efe3d14f643d9d19c6afbed1b18ae46532d87d1"  # pragma: allowlist secret  # noqa: E501
TRANSITION_RECEIPT_SHA256 = "88d1db524f1d9421c806a73d532c9307b3b3a699b030964ce58dfd5650bd3a24"  # pragma: allowlist secret  # noqa: E501
TRANSITION_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt3.json"
INTEGRATION_CANDIDATE_COMMIT = (
    "ac46f96890103a142af724ca1bbd13fa81f3ef3c"  # pragma: allowlist secret  # noqa: E501
)
INTEGRATION_CANDIDATE_TREE = (
    "9f649c9044ce19447fbfde3f2aae99e0a4d23c4c"  # pragma: allowlist secret  # noqa: E501
)
INTEGRATION_REQUEST_SHA256 = "62c9291f5ea6ef39a1123a4c96adaf7e3a58a2a69a5b36369818e99e381e17be"  # pragma: allowlist secret  # noqa: E501
INTEGRATION_RECEIPT_SHA256 = "3359865176269e7eb1da39aa38d6fc9e8230e530f8d02a25f3d8b5f4a3057fc2"  # pragma: allowlist secret  # noqa: E501
INTEGRATION_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt4.json"
EVIDENCE_CANDIDATE_COMMIT = (
    "c9ebf210e3397cd1626faa959aed3b3ddfdc66a1"  # pragma: allowlist secret  # noqa: E501
)
EVIDENCE_CANDIDATE_TREE = (
    "ddd43a4837bb1766ae4b3c6f8b3ae262edeae151"  # pragma: allowlist secret  # noqa: E501
)
EVIDENCE_REQUEST_SHA256 = "45e531415d8176d599f7573f22770b5110211a41c724f524fccd9dbc590dc2d7"  # pragma: allowlist secret  # noqa: E501
EVIDENCE_RECEIPT_SHA256 = "407519737d85e754ad6b4b9fdc4cbb0f2a182b5c60d9f9b90bd8a71db8525465"  # pragma: allowlist secret  # noqa: E501
EVIDENCE_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt5.json"
ANCHOR_ADVERSE_CANDIDATE_COMMIT = (
    "f459d504b62d4a528858dcc3321a58f8218b160f"  # pragma: allowlist secret  # noqa: E501
)
ANCHOR_ADVERSE_CANDIDATE_TREE = (
    "2bf05a0209738a97c73535292f30aa1882a1f372"  # pragma: allowlist secret  # noqa: E501
)
ANCHOR_ADVERSE_REQUEST_SHA256 = "4f3a7f841691095985649545f09ecbf531a7bb9908bfbc6d318d541cdd396d78"  # pragma: allowlist secret  # noqa: E501
ANCHOR_ADVERSE_RECEIPT_SHA256 = "9c1b087a4d24f49069305b1892553f6ab7d579892cc71bfa77ff0e102d143650"  # pragma: allowlist secret  # noqa: E501
ANCHOR_ADVERSE_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt6.json"
GOVERNANCE_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT = (
    "65b91c8094481f18026a90b6b7778716df8f708e"  # pragma: allowlist secret
)
GOVERNANCE_SUPERSEDED_CANDIDATE_COMMIT = (
    "d257042ab16347d75c23db145b24f24b0306d56f"  # pragma: allowlist secret
)
GOVERNANCE_SUPERSEDED_CANDIDATE_TREE = (
    "3a3296c7e68b8c1ad811e6c8e2b6ca03046f848c"  # pragma: allowlist secret
)
GOVERNANCE_SUPERSEDED_REQUEST_SHA256 = "9831ab147d4fcfc06dee96f65c1c90e5de6dcacac523ef81b9f375c244bff394"  # pragma: allowlist secret  # noqa: E501
GOVERNANCE_SUPERSEDED_RECEIPT_SHA256 = "820b18a3c45891db7ab05d2ed95fed2593f81546dcb7031ce5fc96d707386b1d"  # pragma: allowlist secret  # noqa: E501
GOVERNANCE_SUPERSEDED_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt7.json"
MATERIALIZATION_ADVERSE_EXECUTION_CANDIDATE_COMMIT = (
    "b5c5a7bfed564a98e34718edd7bd190ff2484ef5"  # pragma: allowlist secret
)
MATERIALIZATION_ADVERSE_CANDIDATE_COMMIT = (
    "1c4bb44f2eb67fc21b75d493ca0782dbccda0d8e"  # pragma: allowlist secret
)
MATERIALIZATION_ADVERSE_CANDIDATE_TREE = (
    "f3fcc45a1216104c61ae4c3c65d2025079f57bcf"  # pragma: allowlist secret
)
MATERIALIZATION_ADVERSE_REQUEST_SHA256 = "b666a68b2e47cb2ea9886a8224c5b2aee93a1a6297c3e31726718e9e434dabf7"  # pragma: allowlist secret  # noqa: E501
MATERIALIZATION_ADVERSE_RECEIPT_SHA256 = "e349452dae4ec5dd1ac613046d81f1fad0ad2fadaa08f5bb2568a496237795ef"  # pragma: allowlist secret  # noqa: E501
MATERIALIZATION_ADVERSE_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt8.json"
CLOSURE_PATH_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT = (
    "21d465ba4eab32affdf8d42121aaa577a4f7b81d"  # pragma: allowlist secret
)
CLOSURE_PATH_SUPERSEDED_CANDIDATE_COMMIT = (
    "3cd4a4122016ce9b3af8d42901d6d0c968ae981a"  # pragma: allowlist secret
)
CLOSURE_PATH_SUPERSEDED_CANDIDATE_TREE = (
    "1926d2517a9ed3a2a8b4191b0eba8206d5e8af4f"  # pragma: allowlist secret
)
CLOSURE_PATH_SUPERSEDED_REQUEST_SHA256 = "47f32c2dadd542da4a69fd05508a4844ffca8952782dec201513db886541a74e"  # pragma: allowlist secret  # noqa: E501
CLOSURE_PATH_SUPERSEDED_RECEIPT_SHA256 = "2814dcca4c0d8a52e255760ed7b414a78e02a21f89745547f03986113ced7f68"  # pragma: allowlist secret  # noqa: E501
CLOSURE_PATH_SUPERSEDED_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt9.json"
FINAL_REJECTED_EXECUTION_CANDIDATE_COMMIT = (
    "4c60dd977250f94218730f335b8fdd06665fcbde"  # pragma: allowlist secret
)
FINAL_REJECTED_CANDIDATE_COMMIT = (
    "8097b9b0b30590b29bcd8839cd67888b75819856"  # pragma: allowlist secret
)
FINAL_REJECTED_CANDIDATE_TREE = (
    "27dfadaa1328c2ff0e2648c78a914c176a74f4ff"  # pragma: allowlist secret
)
FINAL_REJECTED_REQUEST_SHA256 = "fe0e48fb0042f63ab599b7f49935493d21a3766cda79cd1d986faf2f54f13a88"  # pragma: allowlist secret  # noqa: E501
FINAL_REJECTED_RECEIPT_SHA256 = "e712331a41d1755c6b8c7f6c29348252cabfc9d3ec4b563db588dd259cdfb978"  # pragma: allowlist secret  # noqa: E501
FINAL_REJECTED_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt10.json"
AUTHORITY_ADVERSE_EXECUTION_CANDIDATE_COMMIT = (
    "6ad2d84efe47295075c955f66ad79ae7ad433d00"  # pragma: allowlist secret
)
AUTHORITY_ADVERSE_CANDIDATE_COMMIT = (
    "7e6dd9fe600dbdb51c4cd3eceaa26cbf74dc9670"  # pragma: allowlist secret
)
AUTHORITY_ADVERSE_CANDIDATE_TREE = (
    "863d454cdd4827f744bb05b0e86a4b7e91b1df1d"  # pragma: allowlist secret
)
AUTHORITY_ADVERSE_REQUEST_SHA256 = "83d5c3efddc95259a3d6f700a3c4fda3a1a9d2410f5d94fa2ad466980edef109"  # pragma: allowlist secret  # noqa: E501
AUTHORITY_ADVERSE_RECEIPT_SHA256 = "ba180e358e2b067fa6cedeb6dcefa11aff1c59eac9998f5f403eb1abe59295c8"  # pragma: allowlist secret  # noqa: E501
AUTHORITY_ADVERSE_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt11.json"
AUTHORITY_MATERIALIZATION_ADVERSE_EXECUTION_CANDIDATE_COMMIT = (
    "05baf008394b745a41b3e115bfcc460f5566fb11"  # pragma: allowlist secret
)
AUTHORITY_MATERIALIZATION_ADVERSE_CANDIDATE_COMMIT = (
    "e465aa6fc88ba021b5dd0f172a5d2fa5bad1724b"  # pragma: allowlist secret
)
AUTHORITY_MATERIALIZATION_ADVERSE_CANDIDATE_TREE = (
    "6d38399c14ea2e831964df87875575e72dcb1b62"  # pragma: allowlist secret
)
AUTHORITY_MATERIALIZATION_ADVERSE_REQUEST_SHA256 = "1f3fd30f6b348d903293d4db736e1163b7d283dc0b9d6f0f116548a9c96d4385"  # pragma: allowlist secret  # noqa: E501
AUTHORITY_MATERIALIZATION_ADVERSE_RECEIPT_SHA256 = "1bfe12fcbf5f2ec0ffadf38ee67d8adf9b8dbfada8d23f914c4e3ac50fcb3b0b"  # pragma: allowlist secret  # noqa: E501
AUTHORITY_MATERIALIZATION_ADVERSE_RECEIPT_PATH = (
    "machine/stages/S6/reviews/rmd05/execution-receipt12.json"
)
PUBLIC_CLOSURE_ADVERSE_EXECUTION_CANDIDATE_COMMIT = (
    "19cd62d8a50becce469a7369dd1964f2e1113cf6"  # pragma: allowlist secret
)
PUBLIC_CLOSURE_ADVERSE_CANDIDATE_COMMIT = (
    "3054a409ec3e4064a6dc0827c9cf3415ce5798ef"  # pragma: allowlist secret
)
PUBLIC_CLOSURE_ADVERSE_CANDIDATE_TREE = (
    "357258dbea6482767eb16af22b754603388f0c2c"  # pragma: allowlist secret
)
PUBLIC_CLOSURE_ADVERSE_REQUEST_SHA256 = "a696eab139532fde20e1712e4058b8208463d9be82be095956ffc824780b2dcd"  # pragma: allowlist secret  # noqa: E501
PUBLIC_CLOSURE_ADVERSE_RECEIPT_SHA256 = "3d961beba530ddc416b70d6b3c1116f7d2016f99e630ce752b36ed75612a7f78"  # pragma: allowlist secret  # noqa: E501
PUBLIC_CLOSURE_ADVERSE_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt13.json"
GOVERNANCE_MATERIALIZATION_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT = (
    "a4cae6b6cc4dddbb635764b484bfb5220588c0b8"  # pragma: allowlist secret
)
GOVERNANCE_MATERIALIZATION_SUPERSEDED_CANDIDATE_COMMIT = (
    "85fffeb6b43e8867b2b070d727d6401d465402ae"  # pragma: allowlist secret
)
GOVERNANCE_MATERIALIZATION_SUPERSEDED_CANDIDATE_TREE = (
    "953360aefea09618457fe341821e174eea6a706b"  # pragma: allowlist secret
)
GOVERNANCE_MATERIALIZATION_SUPERSEDED_REQUEST_SHA256 = "7f1ec39e6e27096620a9c15347f44c77e34365d8b0052a0bbf093b85f562b06c"  # pragma: allowlist secret  # noqa: E501
GOVERNANCE_MATERIALIZATION_SUPERSEDED_RECEIPT_SHA256 = "798811aa1304fa1aa9739b825009a6a1e273656093caf882c860e4b6b2a55a15"  # pragma: allowlist secret  # noqa: E501
GOVERNANCE_MATERIALIZATION_SUPERSEDED_RECEIPT_PATH = (
    "machine/stages/S6/reviews/rmd05/execution-receipt14.json"
)
SECRET_SCAN_MATERIALIZATION_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT = (
    "44f14389309a170edd6be7f97073c697d6efe2f3"  # pragma: allowlist secret
)
SECRET_SCAN_MATERIALIZATION_SUPERSEDED_CANDIDATE_COMMIT = (
    "3794c433c7693e3e65581abfa012bc799d5bf5d6"  # pragma: allowlist secret
)
SECRET_SCAN_MATERIALIZATION_SUPERSEDED_CANDIDATE_TREE = (
    "9585d313f8254cb0c7c0e952e3be84c20ceb95be"  # pragma: allowlist secret
)
SECRET_SCAN_MATERIALIZATION_SUPERSEDED_REQUEST_SHA256 = "691f815fd09f5f2c7df84e6142e13f5b8ab4c3324324aa209f9633e3bef93067"  # pragma: allowlist secret  # noqa: E501
SECRET_SCAN_MATERIALIZATION_SUPERSEDED_RECEIPT_SHA256 = "5091a3bc3d6bd3fa976ed94524a479392f18ae2b71e22baed0f04742dbf0d1fe"  # pragma: allowlist secret  # noqa: E501
SECRET_SCAN_MATERIALIZATION_SUPERSEDED_RECEIPT_PATH = (
    "machine/stages/S6/reviews/rmd05/execution-receipt15.json"
)
ASSURANCE_CLI_IMPORT_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT = (
    "6b1d1519ca700f4e32ed7d1e0e39fadef364955c"  # pragma: allowlist secret
)
ASSURANCE_CLI_IMPORT_SUPERSEDED_CANDIDATE_COMMIT = (
    "d9fe1b73ac23bf256df9a98dcf9503f655aad7bc"  # pragma: allowlist secret
)
ASSURANCE_CLI_IMPORT_SUPERSEDED_CANDIDATE_TREE = (
    "86f4a61806b2d53f8712ff831b047171331041a6"  # pragma: allowlist secret
)
ASSURANCE_CLI_IMPORT_SUPERSEDED_REQUEST_SHA256 = "c9dbfe36571c73f6316e1e8ac2b5f86aa37b64528d4c6ed4b57e64e07b743fd1"  # pragma: allowlist secret  # noqa: E501
ASSURANCE_CLI_IMPORT_SUPERSEDED_RECEIPT_SHA256 = "a620d6b8f39fb78a88215714e0bf13b8c1415903c27489e700fa4ae4e28df937"  # pragma: allowlist secret  # noqa: E501
ASSURANCE_CLI_IMPORT_SUPERSEDED_RECEIPT_PATH = (
    "machine/stages/S6/reviews/rmd05/execution-receipt16.json"
)
FINAL_RECEIPT_PATH = "machine/stages/S6/reviews/rmd05/execution-receipt17.json"
INITIAL_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/request.md"
ADVERSE_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview-request.md"
SUPERSEDED_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview2-request.md"
TRANSITION_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview3-request.md"
INTEGRATION_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview4-request.md"
EVIDENCE_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview5-request.md"
ANCHOR_ADVERSE_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview6-request.md"
GOVERNANCE_SUPERSEDED_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview7-request.md"
MATERIALIZATION_ADVERSE_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview8-request.md"
CLOSURE_PATH_SUPERSEDED_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview9-request.md"
FINAL_REJECTED_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview10-request.md"
AUTHORITY_ADVERSE_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview11-request.md"
AUTHORITY_MATERIALIZATION_ADVERSE_REQUEST_PATH = (
    "machine/stages/S6/reviews/rmd05/rereview12-request.md"
)
PUBLIC_CLOSURE_ADVERSE_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview13-request.md"
GOVERNANCE_MATERIALIZATION_SUPERSEDED_REQUEST_PATH = (
    "machine/stages/S6/reviews/rmd05/rereview14-request.md"
)
SECRET_SCAN_MATERIALIZATION_SUPERSEDED_REQUEST_PATH = (
    "machine/stages/S6/reviews/rmd05/rereview15-request.md"
)
ASSURANCE_CLI_IMPORT_SUPERSEDED_REQUEST_PATH = (
    "machine/stages/S6/reviews/rmd05/rereview16-request.md"
)
FINAL_REQUEST_PATH = "machine/stages/S6/reviews/rmd05/rereview17-request.md"
ACCEPTANCE_AUTHORITY_FILENAMES = (
    "AC-001-zero-collateral.json",
    "AC-002-all-types.json",
    "AC-003-mailbox-coverage.json",
    "AC-004-double-verification.json",
    "AC-005-unknown-sender.json",
    "AC-006-message-trash.json",
    "AC-007-remote-recovery-gate.json",
    "AC-008-code-location.json",
    "AC-009-single-private-repo.json",
    "AC-010-cloud-ephemeral.json",
    "AC-011-age-encryption.json",
    "AC-012-key-delivery.json",
    "AC-013-canonical-eml.json",
    "AC-014-magic-bytes.json",
    "AC-015-versioned-lineage.json",
    "AC-016-public-redaction.json",
    "AC-017-pdf-password-deferred.json",
    "AC-018-endpoint-guard.json",
    "AC-019-github-app-token.json",
    "AC-020-untrusted-input.json",
    "AC-021-supply-chain.json",
    "AC-022-no-persistent-plaintext.json",
    "AC-023-schedule.json",
    "AC-024-codex-auto-simple.json",
    "AC-025-sync-reconcile.json",
    "AC-026-idempotency.json",
    "AC-027-private-first.json",
    "AC-028-single-latest-timeline.json",
    "AC-029-timeline-semantics.json",
    "AC-030-no-false-missing.json",
    "AC-031-continuous-evidence.json",
    "AC-032-chaos-recovery.json",
    "AC-033-dual-assurance.json",
    "AC-034-non-goals.json",
    "latest.json",
)
GOVERNANCE_FACT_AUTHORITY_FILENAMES = (
    "acceptance.json",
    "blockers.json",
    "changelog.json",
    "config.yaml",
    "data_contract.yaml",
    "features.json",
    "flows.json",
    "glossary.json",
    "ops.json",
    "plan.json",
    "product.json",
    "roadmap.json",
    "status.json",
)
GOVERNANCE_DOCUMENT_AUTHORITY_SHA256 = {
    "文档/00_我在哪.md": "e8640872a36030932bf70b2df273f79b1a792fea4e42198f692774511379a888",  # pragma: allowlist secret  # noqa: E501
    "文档/01_产品需求.md": "33bc71d5215a2b50290729cac50d1615378c8c476d5c30647dd915c3ca4c5d51",  # pragma: allowlist secret  # noqa: E501
    "文档/02_系统架构.md": "48e7277040b64bd7926f3596482a6f24680226fce8c124c520073c196559802e",  # pragma: allowlist secret  # noqa: E501
    "文档/03_口径字典.md": "0cd7c9e25e2415cbab74fbe0289301a7f4335d6d6a018de3d29cc22001531bb7",  # pragma: allowlist secret  # noqa: E501
    "文档/04_操作流程.md": "98ddc96fef39fc7a899463bc5f23248ebaddd7bc2729484db77452e9d22c6362",  # pragma: allowlist secret  # noqa: E501
    "文档/05_执行与验收.md": "36d57486d3553458b5c1b086d5cb8867337f3425379e521452eb41b29d716d0e",  # pragma: allowlist secret  # noqa: E501
    "文档/06_运维手册.md": "2b02803ff141261a9222f3b5c03c97097e730ad18269c89f75376dbf1da21177",  # pragma: allowlist secret  # noqa: E501
}
PROJECT_REPOSITORY_PREFIX = "LinzeDatabase/MooMooAU"
POST_REVIEW_AUTHORITY_PATHS = frozenset(
    {
        "LinzeDatabase/MooMooAU/evidence/stage6/latest.json",
        "LinzeDatabase/MooMooAU/machine/status/latest.json",
        "LinzeDatabase/MooMooAU/taskpack/PACKAGE_MANIFEST.v1.0.5.json",
        "LinzeDatabase/MooMooAU/taskpack/SOURCE_PROVENANCE.v1.0.5.json",
        *{f"LinzeDatabase/MooMooAU/evidence/tasks/T060{index}.json" for index in range(1, 9)},
        *{
            f"LinzeDatabase/MooMooAU/evidence/acceptance/{name}"
            for name in ACCEPTANCE_AUTHORITY_FILENAMES
        },
        *{
            f"LinzeDatabase/MooMooAU/machine/facts/{name}"
            for name in GOVERNANCE_FACT_AUTHORITY_FILENAMES
        },
        *{
            f"LinzeDatabase/MooMooAU/{relative}"
            for relative in GOVERNANCE_DOCUMENT_AUTHORITY_SHA256
        },
    }
)
POST_REVIEW_AUTHORITY_RELATIVE_PATHS = frozenset(
    path.removeprefix(f"{PROJECT_REPOSITORY_PREFIX}/") for path in POST_REVIEW_AUTHORITY_PATHS
)
POST_REVIEW_ALLOWED_NON_AUTHORITY_PATHS = frozenset(
    {
        "LinzeDatabase/MooMooAU/README.md",
        "LinzeDatabase/MooMooAU/VERSION",
        "LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-sol.json",
        "LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-terra.json",
        "LinzeDatabase/MooMooAU/machine/stages/S6/reviews/rmd05/execution-receipt17.json",
        "LinzeDatabase/MooMooAU/machine/stages/S6/reviews/rmd05/final14/gpt-5.6-sol.reply.json",
        "LinzeDatabase/MooMooAU/machine/stages/S6/reviews/rmd05/final14/gpt-5.6-terra.reply.json",
        "LinzeDatabase/MooMooAU/machine/stages/S6/reviews/rmd05/rereview17-request.md",
        "LinzeDatabase/MooMooAU/taskpack/00_READ_ME_FIRST.v1.0.5.md",
        "LinzeDatabase/MooMooAU/taskpack/CHANGELOG.md",
        "LinzeDatabase/MooMooAU/taskpack/README.md",
        "LinzeDatabase/MooMooAU/taskpack/ROADMAP.v1.0.5.md",
    }
)

EXPECTED_REVIEWERS = {
    "gpt-5.6-sol.json": {
        "family": "gpt-5.6-sol",
        "review_id": "S6-RMD05-GPT56SOL",
        "initial_task": "/root/rmd05_sol_review",
        "adverse_task": "/root/rmd05_sol_rereview",
        "superseded_task": "/root/rmd05_sol_rereview2",
        "transition_task": "/root/rmd05_sol_rereview3",
        "integration_task": "/root/rmd05_sol_rereview4",
        "evidence_task": "/root/rmd05_sol_rereview5",
        "anchor_adverse_task": "/root/rmd05_sol_rereview6",
        "governance_superseded_task": "/root/rmd05_sol_rereview7",
        "materialization_adverse_task": "/root/rmd05_sol_rereview8",
        "closure_path_superseded_task": "/root/rmd05_sol_rereview9",
        "final_rejected_task": "/root/rmd05_sol_rereview10",
        "authority_adverse_task": "/root/rmd05_sol_rereview11",
        "authority_materialization_adverse_task": "/root/rmd05_sol_rereview12",
        "public_closure_adverse_task": "/root/rmd05_sol_rereview13",
        "governance_materialization_superseded_task": "/root/rmd05_sol_rereview14",
        "secret_scan_materialization_superseded_task": "/root/rmd05_sol_rereview15",
        "assurance_cli_import_superseded_task": "/root/rmd05_sol_rereview16",
        "final_task": "/root/rmd05_sol_rereview17",
        "initial_reply": "machine/stages/S6/reviews/rmd05/initial/gpt-5.6-sol.reply.json",
        "initial_reply_sha256": (
            "843e84445731e02c02f8e02bbcc8cd2091f428387356efeb0ae4dbe2120fc0bd"  # pragma: allowlist secret  # noqa: E501
        ),
        "adverse_reply": "machine/stages/S6/reviews/rmd05/rereview1/gpt-5.6-sol.reply.json",
        "adverse_reply_sha256": (
            "5f1072d2e2e6525897fa5dca67bfb081e149bb35e5973abf9832c8d7bb417461"  # pragma: allowlist secret  # noqa: E501
        ),
        "superseded_reply": "machine/stages/S6/reviews/rmd05/final/gpt-5.6-sol.reply.json",
        "superseded_reply_sha256": (
            "9c4bf4f5c7c2018958f966edcc96898a2da5351fcb1a22900320b0da854a2796"  # pragma: allowlist secret  # noqa: E501
        ),
        "transition_reply": "machine/stages/S6/reviews/rmd05/rereview3/gpt-5.6-sol.reply.json",
        "transition_reply_sha256": (
            "7f301af5d14133095743bc0ab16c33ec673546e2873b1727992869b564ec5b88"  # pragma: allowlist secret  # noqa: E501
        ),
        "transition_open_findings": {"RMD05-CLOSURE-003"},
        "integration_reply": "machine/stages/S6/reviews/rmd05/final2/gpt-5.6-sol.reply.json",
        "integration_reply_sha256": (
            "7e52b323b1a69d1d15c110b8781e3de66e06787ac21a82a8d51db340f4327268"  # pragma: allowlist secret  # noqa: E501
        ),
        "evidence_reply": "machine/stages/S6/reviews/rmd05/rereview5/gpt-5.6-sol.reply.json",
        "evidence_reply_sha256": (
            "cc68de21447759a2fd19a4f73c2f135294833aace3d99c8022b21ba6cd515665"  # pragma: allowlist secret  # noqa: E501
        ),
        "evidence_verdict": "FAIL",
        "evidence_open_findings": {"RMD05-CLOSURE-005"},
        "anchor_adverse_reply": "machine/stages/S6/reviews/rmd05/final3/gpt-5.6-sol.reply.json",
        "anchor_adverse_reply_sha256": (
            "93b8c0766935ac369cebbbd9e7a29db3dea32b4a35754ba3454dd7691263d385"  # pragma: allowlist secret  # noqa: E501
        ),
        "anchor_adverse_verdict": "PASS",
        "anchor_adverse_open_findings": set(),
        "governance_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final4/gpt-5.6-sol.reply.json"
        ),
        "governance_superseded_reply_sha256": (
            "1ad4a93204a1f33a92d147025ef0262e2a1512a035ce0e7f76687cad0dbaee76"  # pragma: allowlist secret  # noqa: E501
        ),
        "materialization_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final5/gpt-5.6-sol.reply.json"
        ),
        "materialization_adverse_reply_sha256": (
            "df7ecfdd37d47b4ba3455768ea2e0b981a1d73263df3891e2ae50ed20bcda0a1"  # pragma: allowlist secret  # noqa: E501
        ),
        "materialization_adverse_verdict": "PASS",
        "materialization_adverse_open_findings": set(),
        "closure_path_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final6/gpt-5.6-sol.reply.json"
        ),
        "closure_path_superseded_reply_sha256": (
            "9a7ce284b6ce71106b4b6ff3a5337c67887e8647b0db13d4b77f6a79e6da24a7"  # pragma: allowlist secret  # noqa: E501
        ),
        "final_rejected_reply": ("machine/stages/S6/reviews/rmd05/final7/gpt-5.6-sol.reply.json"),
        "final_rejected_reply_sha256": (
            "b929f694b224fadc5f3391a766260a1dff49705ffe1c24ee7a0b6cb663231b73"  # pragma: allowlist secret  # noqa: E501
        ),
        "authority_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final8/gpt-5.6-sol.reply.json"
        ),
        "authority_adverse_reply_sha256": (
            "bb53e04b892adb4105313493899d5a9b0c7b3d8e10535de7e92a9e5cb0715c03"  # pragma: allowlist secret  # noqa: E501
        ),
        "authority_adverse_verdict": "PASS",
        "authority_adverse_open_findings": set(),
        "authority_materialization_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final9/gpt-5.6-sol.reply.json"
        ),
        "authority_materialization_adverse_reply_sha256": (
            "6fd80ffa03465013e18d48df85a979984918f912af6296f60bc39b6bd903a226"  # pragma: allowlist secret  # noqa: E501
        ),
        "authority_materialization_adverse_verdict": "FAIL",
        "authority_materialization_adverse_open_findings": {"RMD05-CLOSURE-009"},
        "public_closure_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final10/gpt-5.6-sol.reply.json"
        ),
        "public_closure_adverse_reply_sha256": (
            "8c45c439e15be5007aef16979dcf35bd5f62928dcfde531e16e3ab6d476449f6"  # pragma: allowlist secret  # noqa: E501
        ),
        "public_closure_adverse_verdict": "FAIL",
        "public_closure_adverse_open_findings": {"RMD05-CLOSURE-009"},
        "governance_materialization_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final11/gpt-5.6-sol.reply.json"
        ),
        "governance_materialization_superseded_reply_sha256": (
            "2d82f66fa0e64b28cb53a64b5a1e9fd880d325100ae3d56baece79d2c5d35f6e"  # pragma: allowlist secret  # noqa: E501
        ),
        "secret_scan_materialization_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final12/gpt-5.6-sol.reply.json"
        ),
        "secret_scan_materialization_superseded_reply_sha256": (
            "4026dddd373d1387ba78d0560507704c85a058ef1f622e714bb6b75a69cfaa15"  # pragma: allowlist secret  # noqa: E501
        ),
        "assurance_cli_import_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final13/gpt-5.6-sol.reply.json"
        ),
        "assurance_cli_import_superseded_reply_sha256": (
            "affcfd9e1c2977a19ad9a80f3f1024e9cf9a6b9626937153dc8d5e493e3adcc3"  # pragma: allowlist secret  # noqa: E501
        ),
        "final_reply": "machine/stages/S6/reviews/rmd05/final14/gpt-5.6-sol.reply.json",
    },
    "gpt-5.6-terra.json": {
        "family": "gpt-5.6-terra",
        "review_id": "S6-RMD05-GPT56TERRA",
        "initial_task": "/root/rmd05_terra_review",
        "adverse_task": "/root/rmd05_terra_rereview",
        "superseded_task": "/root/rmd05_terra_rereview2",
        "transition_task": "/root/rmd05_terra_rereview3",
        "integration_task": "/root/rmd05_terra_rereview4",
        "evidence_task": "/root/rmd05_terra_rereview5",
        "anchor_adverse_task": "/root/rmd05_terra_rereview6",
        "governance_superseded_task": "/root/rmd05_terra_rereview7",
        "materialization_adverse_task": "/root/rmd05_terra_rereview8",
        "closure_path_superseded_task": "/root/rmd05_terra_rereview9",
        "final_rejected_task": "/root/rmd05_terra_rereview10",
        "authority_adverse_task": "/root/rmd05_terra_rereview11",
        "authority_materialization_adverse_task": "/root/rmd05_terra_rereview12",
        "public_closure_adverse_task": "/root/rmd05_terra_rereview13",
        "governance_materialization_superseded_task": "/root/rmd05_terra_rereview14",
        "secret_scan_materialization_superseded_task": "/root/rmd05_terra_rereview15",
        "assurance_cli_import_superseded_task": "/root/rmd05_terra_rereview16",
        "final_task": "/root/rmd05_terra_rereview17",
        "initial_reply": "machine/stages/S6/reviews/rmd05/initial/gpt-5.6-terra.reply.json",
        "initial_reply_sha256": (
            "646786d09804730e98c71652c1ad98fede5d697c17c0a1d1ee6a0c81283ee9a3"  # pragma: allowlist secret  # noqa: E501
        ),
        "adverse_reply": "machine/stages/S6/reviews/rmd05/rereview1/gpt-5.6-terra.reply.json",
        "adverse_reply_sha256": (
            "bb2a72bf7c63425aca444eaf407a566de2d6f6e67f9a23dde295fc2f344fa718"  # pragma: allowlist secret  # noqa: E501
        ),
        "superseded_reply": "machine/stages/S6/reviews/rmd05/final/gpt-5.6-terra.reply.json",
        "superseded_reply_sha256": (
            "10cd7d8d407fbfdc39656c8eba589997c635fd856878e327dd4a7ce79e0ebfb2"  # pragma: allowlist secret  # noqa: E501
        ),
        "transition_reply": "machine/stages/S6/reviews/rmd05/rereview3/gpt-5.6-terra.reply.json",
        "transition_reply_sha256": (
            "36fe590612c5c8d786e28f001cfda6dc41886e95a4a40e579ebd7a14ca334d36"  # pragma: allowlist secret  # noqa: E501
        ),
        "transition_open_findings": {"RMD05-CLOSURE-002"},
        "integration_reply": "machine/stages/S6/reviews/rmd05/final2/gpt-5.6-terra.reply.json",
        "integration_reply_sha256": (
            "7809fbf2909ff4080b9611c128cc36bc232e1b84f2d04d2564343524464fb58f"  # pragma: allowlist secret  # noqa: E501
        ),
        "evidence_reply": "machine/stages/S6/reviews/rmd05/rereview5/gpt-5.6-terra.reply.json",
        "evidence_reply_sha256": (
            "a3a92441c86b145835bd6babca873f0dcb89cb0840f5541d5c0af31812ab0ed0"  # pragma: allowlist secret  # noqa: E501
        ),
        "evidence_verdict": "PASS",
        "evidence_open_findings": set(),
        "anchor_adverse_reply": "machine/stages/S6/reviews/rmd05/final3/gpt-5.6-terra.reply.json",
        "anchor_adverse_reply_sha256": (
            "375f087ee5b4779a16e0e0d31585d04fc5a4914af4756cf29078a6e6f13244b4"  # pragma: allowlist secret  # noqa: E501
        ),
        "anchor_adverse_verdict": "FAIL",
        "anchor_adverse_open_findings": {"RMD05-CLOSURE-005"},
        "governance_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final4/gpt-5.6-terra.reply.json"
        ),
        "governance_superseded_reply_sha256": (
            "e668c13369cd4ec4681804f1a4ffd5bcfa7c9ba69eca755375ada63ca6090a72"  # pragma: allowlist secret  # noqa: E501
        ),
        "materialization_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final5/gpt-5.6-terra.reply.json"
        ),
        "materialization_adverse_reply_sha256": (
            "0e3b9af0e69036ff518fe9ccad03b26e9b6fb9090d2cd8a0e1510fd6dca1509c"  # pragma: allowlist secret  # noqa: E501
        ),
        "materialization_adverse_verdict": "FAIL",
        "materialization_adverse_open_findings": {"RMD05-CLOSURE-006"},
        "closure_path_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final6/gpt-5.6-terra.reply.json"
        ),
        "closure_path_superseded_reply_sha256": (
            "d5cb77bd8292de829ba213c5daad079c8157e351d6840754006cac4f7b9e24d2"  # pragma: allowlist secret  # noqa: E501
        ),
        "final_rejected_reply": ("machine/stages/S6/reviews/rmd05/final7/gpt-5.6-terra.reply.json"),
        "final_rejected_reply_sha256": (
            "f6acbffbffd146430423bd3e4c87814a084603fbac7b99b18e50d1cefac2d79d"  # pragma: allowlist secret  # noqa: E501
        ),
        "authority_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final8/gpt-5.6-terra.reply.json"
        ),
        "authority_adverse_reply_sha256": (
            "9dd51f76944b2817afa7add5437481a2034211382d36d47bed16cd3cc6bc7011"  # pragma: allowlist secret  # noqa: E501
        ),
        "authority_adverse_verdict": "FAIL",
        "authority_adverse_open_findings": {"RMD05-CLOSURE-009"},
        "authority_materialization_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final9/gpt-5.6-terra.reply.json"
        ),
        "authority_materialization_adverse_reply_sha256": (
            "4f2d16dfb2b74233a120898c229a840b4bc3b9eb664b50d209f8fa4ed7e06636"  # pragma: allowlist secret  # noqa: E501
        ),
        "authority_materialization_adverse_verdict": "FAIL",
        "authority_materialization_adverse_open_findings": {"RMD05-CLOSURE-009"},
        "public_closure_adverse_reply": (
            "machine/stages/S6/reviews/rmd05/final10/gpt-5.6-terra.reply.json"
        ),
        "public_closure_adverse_reply_sha256": (
            "30c35c5f2ad73239250ed354def34dbfaf35b115635402eb885cec68734ecfbe"  # pragma: allowlist secret  # noqa: E501
        ),
        "public_closure_adverse_verdict": "FAIL",
        "public_closure_adverse_open_findings": {"RMD05-CLOSURE-009"},
        "governance_materialization_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final11/gpt-5.6-terra.reply.json"
        ),
        "governance_materialization_superseded_reply_sha256": (
            "6ff2e11ab21e4004edf86b59b99df6ba7e5851996e6dc4d9522a365ba4e0a732"  # pragma: allowlist secret  # noqa: E501
        ),
        "secret_scan_materialization_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final12/gpt-5.6-terra.reply.json"
        ),
        "secret_scan_materialization_superseded_reply_sha256": (
            "1a466d65996259569d2544af389461da68ce9d7bfe1c49d021d8b9e33d3a4d61"  # pragma: allowlist secret  # noqa: E501
        ),
        "assurance_cli_import_superseded_reply": (
            "machine/stages/S6/reviews/rmd05/final13/gpt-5.6-terra.reply.json"
        ),
        "assurance_cli_import_superseded_reply_sha256": (
            "941b8564a33469668c61abb74c30d857f73415df736802fff22b32a84f06fb0d"  # pragma: allowlist secret  # noqa: E501
        ),
        "final_reply": "machine/stages/S6/reviews/rmd05/final14/gpt-5.6-terra.reply.json",
    },
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _all_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _all_strings(item)]
    if isinstance(value, dict):
        return [
            text
            for key, item in value.items()
            for part in (key, item)
            for text in _all_strings(part)
        ]
    return []


def _safe_artifact(root: Path, value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    path = root.joinpath(*pure.parts)
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return None
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file() or path.is_symlink():
        return None
    return resolved


def _schema_errors(schema_path: Path, instance: object) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = _load(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(instance)]


def _load_hashed_artifact(
    root: Path,
    artifact: object,
    errors: list[str],
    label: str,
) -> tuple[Path, bytes] | None:
    if not isinstance(artifact, dict):
        errors.append(f"{label} artifact metadata is invalid")
        return None
    path = _safe_artifact(root, artifact.get("path"))
    expected = artifact.get("sha256")
    if path is None or not isinstance(expected, str):
        errors.append(f"{label} artifact path is missing or unsafe")
        return None
    payload = path.read_bytes()
    if _sha256_bytes(payload) != expected:
        errors.append(f"{label} artifact digest differs")
        return None
    return path, payload


def _load_reply(
    root: Path,
    artifact: object,
    reply_schema: Path,
    errors: list[str],
    label: str,
) -> dict[str, Any] | None:
    loaded = _load_hashed_artifact(root, artifact, errors, label)
    if loaded is None:
        return None
    _, payload = loaded
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        errors.append(f"{label} reply normalization differs")
        return None
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{label} reply is not UTF-8 JSON")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} reply is not a JSON object")
        return None
    if _schema_errors(reply_schema, value):
        errors.append(f"{label} reply violates the v2 schema")
        return None
    return cast(dict[str, Any], value)


def _validate_dimensions(reply: dict[str, Any], *, must_pass: bool) -> bool:
    dimensions = reply.get("dimensions")
    if not isinstance(dimensions, list):
        return False
    statuses = {item.get("id"): item.get("status") for item in dimensions if isinstance(item, dict)}
    if set(statuses) != REQUIRED_DIMENSIONS:
        return False
    return set(statuses.values()) == ({"PASS"} if must_pass else {"PASS", "FAIL"}) or (
        not must_pass and "FAIL" in statuses.values()
    )


def _git(repository_root: Path, *args: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(repository_root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.returncode, completed.stdout.strip()


def _is_post_review_authority_path(path: str) -> bool:
    return path in POST_REVIEW_AUTHORITY_PATHS


def _protected_post_review_paths(changed_paths: list[str]) -> list[str]:
    """Return every descendant path outside the frozen final-output allowlist."""

    return [
        path
        for path in changed_paths
        if not _is_post_review_authority_path(path)
        and path not in POST_REVIEW_ALLOWED_NON_AUTHORITY_PATHS
    ]


def _validate_git_subject(
    repository_root: Path,
    candidate_commit: str,
    candidate_tree: str,
    errors: list[str],
    *,
    allow_post_review_authorities: bool = False,
) -> list[str]:
    tree_status, observed_tree = _git(repository_root, "rev-parse", f"{candidate_commit}^{{tree}}")
    if tree_status != 0 or observed_tree != candidate_tree:
        errors.append("review candidate commit/tree is not present or differs")
    ancestor_status, _ = _git(
        repository_root,
        "merge-base",
        "--is-ancestor",
        BASELINE_COMMIT,
        candidate_commit,
    )
    if ancestor_status != 0:
        errors.append("review candidate does not descend from the frozen Stage 5 baseline")
    head_ancestor_status, _ = _git(
        repository_root,
        "merge-base",
        "--is-ancestor",
        candidate_commit,
        "HEAD",
    )
    if head_ancestor_status != 0:
        errors.append("review candidate is not an ancestor of the current delivery commit")
        return []
    diff_status, changed = _git(
        repository_root,
        "diff",
        "--name-only",
        f"{candidate_commit}..HEAD",
        "--",
    )
    if diff_status != 0:
        errors.append("post-review path drift cannot be inspected")
        return []
    changed_paths = changed.splitlines() if changed else []
    authorities = [path for path in changed_paths if _is_post_review_authority_path(path)]
    protected = _protected_post_review_paths(changed_paths)
    if protected or (authorities and not allow_post_review_authorities):
        errors.append(
            "reviewed effect, workflow, dependency, test or assurance surface changed after review"
        )
    dirty_status, dirty = _git(repository_root, "status", "--porcelain")
    if dirty_status != 0 or dirty:
        errors.append("delivery worktree is not clean while review provenance is being validated")
    return authorities


def _render_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _candidate_blob(repository_root: Path, candidate_commit: str, path: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), "show", f"{candidate_commit}:{path}"],
        check=False,
        capture_output=True,
    )
    return completed.stdout if completed.returncode == 0 else None


def _validate_post_review_authorities(
    root: Path,
    repository_root: Path,
    authority_paths: list[str],
    errors: list[str],
    *,
    candidate_commit: str | None = None,
) -> None:
    """Verify every mutable post-review authority through reviewed deterministic builders."""

    if not authority_paths:
        errors.append("closed review has no deterministic post-review authority materialization")
        return

    expected_payloads: dict[str, bytes] = {}

    stage6_errors = validate_stage6_candidate_bundle(root, repository_root)
    if stage6_errors:
        errors.append(
            "post-review Stage 6 evidence authority differs from its exact receipt binding"
        )
    if candidate_commit is not None:
        for relative in (
            "evidence/stage6/latest.json",
            *(f"evidence/tasks/T060{index}.json" for index in range(1, 9)),
        ):
            try:
                expected_payloads[relative] = (root / relative).read_bytes()
            except OSError:
                errors.append(
                    "post-review Stage 6 evidence authority differs from its exact receipt binding"
                )

    try:
        from machine.acceptance.evidence import build_bundle, validate_bundle

        acceptance_errors = list(validate_bundle(root))
        if candidate_commit is None:
            acceptance_bundle = {}
        else:
            project_prefix = root.relative_to(repository_root).as_posix()
            candidate_summary_blob = _candidate_blob(
                repository_root,
                candidate_commit,
                f"{project_prefix}/evidence/acceptance/latest.json",
            )
            if candidate_summary_blob is None:
                raise ValueError("candidate Acceptance summary is missing")
            candidate_summary = json.loads(candidate_summary_blob)
            if not isinstance(candidate_summary, dict):
                raise TypeError("candidate Acceptance summary is not an object")
            observed_at_utc = candidate_summary.get("observed_at_utc")
            remediation_base_commit = candidate_summary.get("remediation_base_commit")
            if not isinstance(observed_at_utc, str) or not isinstance(remediation_base_commit, str):
                raise TypeError("candidate Acceptance materialization parameters are invalid")
            acceptance_bundle = build_bundle(
                root,
                observed_at_utc=observed_at_utc,
                remediation_base_commit=remediation_base_commit,
            )
    except (
        ImportError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        acceptance_errors = ["deterministic acceptance validation failed"]
        acceptance_bundle = {}
    if acceptance_errors:
        errors.append(
            "post-review Acceptance evidence authority differs from deterministic evidence"
        )
    for acceptance_relative, rendered in acceptance_bundle.items():
        acceptance_payload = rendered.encode("utf-8")
        expected_payloads[acceptance_relative.as_posix()] = acceptance_payload
        try:
            if (root / acceptance_relative).read_bytes() != acceptance_payload:
                acceptance_errors.append("candidate-bound Acceptance payload differs")
        except OSError:
            acceptance_errors.append("candidate-bound Acceptance payload is missing")
    if acceptance_errors and (
        "post-review Acceptance evidence authority differs from deterministic evidence"
        not in errors
    ):
        errors.append(
            "post-review Acceptance evidence authority differs from deterministic evidence"
        )

    try:
        from build_delivery_status import STATUS_PATH, build_status

        expected_status = build_status(root, assurance_result={"status": "PASS"})
        observed_status = _load(root / STATUS_PATH)
    except (
        ImportError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        errors.append("post-review delivery status authority cannot be deterministically rebuilt")
    else:
        status_payload = _render_json_bytes(expected_status)
        expected_payloads[STATUS_PATH.as_posix()] = status_payload
        if (
            observed_status != expected_status
            or (root / STATUS_PATH).read_bytes() != status_payload
        ):
            errors.append(
                "post-review delivery status authority differs from deterministic evidence"
            )

    try:
        from build_governance_facts import build_facts

        expected_facts = build_facts(root)
    except (
        ImportError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        errors.append("post-review governance facts cannot be deterministically rebuilt")
    else:
        for name, expected in expected_facts.items():
            expected_payloads[f"machine/facts/{name}"] = _render_json_bytes(expected)
            path = root / "machine/facts" / name
            try:
                observed = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                errors.append("post-review governance facts differ from deterministic evidence")
                break
            rendered = json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
            if observed != rendered:
                errors.append("post-review governance facts differ from deterministic evidence")
                break

    for relative, expected_sha256 in GOVERNANCE_DOCUMENT_AUTHORITY_SHA256.items():
        path = root / relative
        try:
            payload = path.read_bytes()
        except OSError:
            errors.append("post-review Governance document authority is missing or unreadable")
            continue
        expected_payloads[relative] = payload
        if _sha256_bytes(payload) != expected_sha256:
            errors.append(
                "post-review Governance document authority differs from the reviewed pinned render"
            )

    try:
        from validate_package import PROVENANCE_PATH, _validate_provenance, build_provenance

        provenance_failures: list[str] = []
        _validate_provenance(root, provenance_failures)
        if not (root / PROVENANCE_PATH).is_file():
            provenance_failures.append("v1.0.5 provenance is missing")
    except (ImportError, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        provenance_failures = ["deterministic provenance validation failed"]
    if provenance_failures:
        errors.append("post-review source-provenance authority differs from the closed protocol")
    else:
        provenance_payload = _render_json_bytes(build_provenance())
        expected_payloads[PROVENANCE_PATH.as_posix()] = provenance_payload
        if (root / PROVENANCE_PATH).read_bytes() != provenance_payload:
            errors.append(
                "post-review source-provenance authority differs from the closed protocol"
            )

    try:
        from build_package_manifest import MANIFEST_PATH, build_manifest

        expected_manifest = build_manifest(root)
        observed_manifest = _load(root / MANIFEST_PATH)
    except (
        ImportError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        errors.append("post-review package authority cannot be deterministically rebuilt")
    else:
        manifest_payload = _render_json_bytes(expected_manifest)
        expected_payloads[MANIFEST_PATH.as_posix()] = manifest_payload
        if (
            observed_manifest != expected_manifest
            or (root / MANIFEST_PATH).read_bytes() != manifest_payload
        ):
            errors.append(
                "post-review package authority differs from the canonical package selection"
            )

    if candidate_commit is not None:
        try:
            project_prefix = root.relative_to(repository_root).as_posix()
        except ValueError:
            errors.append("post-review authority root is outside the delivery repository")
            return
        expected_repository_paths = {
            f"{project_prefix}/{relative}" for relative in POST_REVIEW_AUTHORITY_RELATIVE_PATHS
        }
        observed_repository_paths = {
            f"{project_prefix}/{relative}" for relative in expected_payloads
        }
        if observed_repository_paths != expected_repository_paths:
            errors.append(
                "post-review deterministic builders do not produce the exact authority file set"
            )
            return
        expected_delta: set[str] = set()
        for relative, payload in expected_payloads.items():
            repository_path = f"{project_prefix}/{relative}"
            if _candidate_blob(repository_root, candidate_commit, repository_path) != payload:
                expected_delta.add(repository_path)
        if set(authority_paths) != expected_delta:
            errors.append(
                "post-review authority path delta differs from exact deterministic materialization"
            )


def _validate_execution_receipt(
    root: Path,
    receipt_artifact: object,
    candidate_commit: str,
    candidate_tree: str,
    expected_path: str,
    errors: list[str],
    expected_command_ids: set[str] = LEGACY_COMMAND_IDS,
) -> str | None:
    loaded = _load_hashed_artifact(root, receipt_artifact, errors, "execution receipt")
    if loaded is None:
        return None
    path, payload = loaded
    if path.relative_to(root).as_posix() != expected_path:
        errors.append("execution receipt path differs from the closed RMD-05 path")
        return None
    try:
        receipt = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append("execution receipt is not valid JSON")
        return None
    schema = root / "machine/stages/S6/schemas/execution-receipt-v1.schema.json"
    if _schema_errors(schema, receipt):
        errors.append("execution receipt violates its schema")
        return None
    receipt_text = "\n".join(_all_strings(receipt))
    if any(marker in receipt_text for marker in LOCAL_PATH_MARKERS):
        errors.append("execution receipt leaks a local path")
    if any(pattern.search(receipt_text) for pattern in SENSITIVE_RECEIPT_OUTPUT):
        errors.append("execution receipt contains sensitive output")
    subject = receipt["subject"]
    if (
        subject["baseline_commit"] != BASELINE_COMMIT
        or subject["candidate_commit"] != candidate_commit
        or subject["candidate_tree"] != candidate_tree
    ):
        errors.append("execution receipt is stale or bound to another candidate")
    commands = receipt["commands"]
    ids = [item["id"] for item in commands]
    if len(ids) != len(set(ids)) or set(ids) != expected_command_ids:
        errors.append("execution receipt command closure is incomplete or duplicated")
    for command in commands:
        stdout = command["sanitized_stdout"].encode("utf-8")
        stderr = command["sanitized_stderr"].encode("utf-8")
        if (
            _sha256_bytes(stdout) != command["sanitized_stdout_sha256"]
            or _sha256_bytes(stderr) != command["sanitized_stderr_sha256"]
        ):
            errors.append(f"execution output digest differs for {command['id']}")
        combined = "\n".join(
            [
                *command["argv"],
                *command["tool_versions"].values(),
                command["sanitized_stdout"],
                command["sanitized_stderr"],
            ]
        )
        if any(marker in combined for marker in LOCAL_PATH_MARKERS):
            errors.append(f"execution output leaks a local path for {command['id']}")
        if any(pattern.search(combined) for pattern in SENSITIVE_RECEIPT_OUTPUT):
            errors.append(f"execution output contains sensitive data for {command['id']}")
    return _sha256_bytes(payload)


def evaluate_assurance_reviews(
    root: Path = PROJECT_ROOT,
    repository_root: Path = REPOSITORY_ROOT,
    *,
    verify_git: bool = True,
    verify_anchor: bool | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    repository_root = repository_root.resolve()
    if verify_anchor is None:
        verify_anchor = verify_git
    errors: list[str] = []
    provenance_schema = root / "machine/stages/S6/schemas/review-provenance-v2.schema.json"
    reply_schema = root / "machine/stages/S6/schemas/review-reply-v2.schema.json"
    review_root = root / "machine/stages/S6/reviews"
    paths = sorted(review_root.glob("*.json"), key=lambda path: path.name)
    if [path.name for path in paths] != sorted(EXPECTED_REVIEWERS):
        errors.append("exactly the two closed RMD-05 provenance records are required")
        return {"status": "BLOCKED", "errors": errors}

    records: list[dict[str, Any]] = []
    all_task_ids: list[str] = []
    adverse_request_hashes: set[str] = set()
    adverse_reply_hashes: set[str] = set()
    adverse_receipt_hashes: set[str] = set()
    superseded_request_hashes: set[str] = set()
    superseded_reply_hashes: set[str] = set()
    superseded_receipt_hashes: set[str] = set()
    transition_request_hashes: set[str] = set()
    transition_reply_hashes: set[str] = set()
    transition_receipt_hashes: set[str] = set()
    integration_request_hashes: set[str] = set()
    integration_reply_hashes: set[str] = set()
    integration_receipt_hashes: set[str] = set()
    evidence_request_hashes: set[str] = set()
    evidence_reply_hashes: set[str] = set()
    evidence_receipt_hashes: set[str] = set()
    anchor_adverse_request_hashes: set[str] = set()
    anchor_adverse_reply_hashes: set[str] = set()
    anchor_adverse_receipt_hashes: set[str] = set()
    governance_superseded_request_hashes: set[str] = set()
    governance_superseded_reply_hashes: set[str] = set()
    governance_superseded_receipt_hashes: set[str] = set()
    materialization_adverse_request_hashes: set[str] = set()
    materialization_adverse_reply_hashes: set[str] = set()
    materialization_adverse_receipt_hashes: set[str] = set()
    closure_path_superseded_request_hashes: set[str] = set()
    closure_path_superseded_reply_hashes: set[str] = set()
    closure_path_superseded_receipt_hashes: set[str] = set()
    final_rejected_request_hashes: set[str] = set()
    final_rejected_reply_hashes: set[str] = set()
    final_rejected_receipt_hashes: set[str] = set()
    authority_adverse_request_hashes: set[str] = set()
    authority_adverse_reply_hashes: set[str] = set()
    authority_adverse_receipt_hashes: set[str] = set()
    authority_materialization_adverse_request_hashes: set[str] = set()
    authority_materialization_adverse_reply_hashes: set[str] = set()
    authority_materialization_adverse_receipt_hashes: set[str] = set()
    public_closure_adverse_request_hashes: set[str] = set()
    public_closure_adverse_reply_hashes: set[str] = set()
    public_closure_adverse_receipt_hashes: set[str] = set()
    governance_materialization_superseded_request_hashes: set[str] = set()
    governance_materialization_superseded_reply_hashes: set[str] = set()
    governance_materialization_superseded_receipt_hashes: set[str] = set()
    secret_scan_materialization_superseded_request_hashes: set[str] = set()
    secret_scan_materialization_superseded_reply_hashes: set[str] = set()
    secret_scan_materialization_superseded_receipt_hashes: set[str] = set()
    assurance_cli_import_superseded_request_hashes: set[str] = set()
    assurance_cli_import_superseded_reply_hashes: set[str] = set()
    assurance_cli_import_superseded_receipt_hashes: set[str] = set()
    final_request_hashes: set[str] = set()
    final_reply_hashes: set[str] = set()
    final_receipt_hashes: set[str] = set()
    top_level_receipt_hashes: set[str] = set()
    subjects: set[tuple[str, str]] = set()
    closure_statuses: set[str] = set()

    for path in paths:
        expected = EXPECTED_REVIEWERS[path.name]
        try:
            raw_record = _load(path)
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"{path.name} is not valid JSON")
            continue
        if not isinstance(raw_record, dict) or _schema_errors(provenance_schema, raw_record):
            errors.append(f"{path.name} violates the v2 provenance schema")
            continue
        record = cast(dict[str, Any], raw_record)
        records.append(record)
        closure_statuses.add(record["closure_status"])
        family = expected["family"]
        if (
            record["model_family"] != family
            or record["review_id"] != expected["review_id"]
            or record["review_mode"] != "READ_ONLY_INDEPENDENT"
        ):
            errors.append(f"{path.name} reviewer identity differs")
        subject = record["subject"]
        if subject["baseline_commit"] != BASELINE_COMMIT:
            errors.append(f"{path.name} baseline differs")
        subjects.add((subject["candidate_commit"], subject["candidate_tree"]))
        blocked_history = record["closure_status"] == "BLOCKED"
        active_receipt_path = (
            ASSURANCE_CLI_IMPORT_SUPERSEDED_RECEIPT_PATH if blocked_history else FINAL_RECEIPT_PATH
        )
        execution_candidate = subject["candidate_commit"]
        try:
            final_receipt = _load(root / active_receipt_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            final_receipt = {}
        if isinstance(final_receipt, dict) and isinstance(final_receipt.get("subject"), dict):
            observed_execution_candidate = final_receipt["subject"].get("candidate_commit")
            if isinstance(observed_execution_candidate, str):
                execution_candidate = observed_execution_candidate
        if verify_anchor:
            anchored_execution_candidate, anchor_errors = validate_stage6_receipt_anchor(
                root,
                repository_root,
                subject["candidate_commit"],
                subject["candidate_tree"],
                Path(active_receipt_path),
            )
            errors.extend(anchor_errors)
            if anchored_execution_candidate is not None:
                execution_candidate = anchored_execution_candidate
        top_level_receipt_digest = _validate_execution_receipt(
            root,
            record["execution_receipt"],
            execution_candidate,
            subject["candidate_tree"],
            active_receipt_path,
            errors,
            EXPECTED_COMMAND_IDS,
        )
        if top_level_receipt_digest is not None:
            top_level_receipt_hashes.add(top_level_receipt_digest)

        attempts = record["attempts"]
        expected_phases = [
            "INITIAL",
            "REREVIEW_ADVERSE",
            "REREVIEW_SUPERSEDED",
            "REREVIEW_TRANSITION_ADVERSE",
            "REREVIEW_OUTPUT_INTEGRATION_SUPERSEDED",
            "REREVIEW_EVIDENCE_COUPLING_ADVERSE",
            "REREVIEW_RECEIPT_ANCHOR_ADVERSE",
            "REREVIEW_GOVERNANCE_FACTS_SUPERSEDED",
            "REREVIEW_OUTPUT_MATERIALIZATION_ADVERSE",
            "REREVIEW_CLOSURE_PATH_SUPERSEDED",
            "REREVIEW_FINAL_REJECTED",
            "REREVIEW_AUTHORITY_DRIFT_ADVERSE",
            "REREVIEW_AUTHORITY_MATERIALIZATION_ADVERSE",
            "REREVIEW_PUBLIC_CLOSURE_ADVERSE",
            "REREVIEW_GOVERNANCE_MATERIALIZATION_SUPERSEDED",
            "REREVIEW_SECRET_SCAN_MATERIALIZATION_SUPERSEDED",
            "REREVIEW_ASSURANCE_CLI_IMPORT_SUPERSEDED",
        ]
        if not blocked_history:
            expected_phases.append("REREVIEW_FINAL")
        if [item["phase"] for item in attempts] != expected_phases:
            errors.append(f"{path.name} review attempt order differs")
            continue
        replies: list[dict[str, Any] | None] = []
        for index, attempt in enumerate(attempts):
            phase = (
                "initial",
                "adverse rereview",
                "superseded PASS rereview",
                "transition adverse rereview",
                "superseded output-integration PASS rereview",
                "evidence-coupling adverse rereview",
                "receipt-anchor adverse rereview",
                "governance-facts superseded PASS rereview",
                "output-materialization adverse rereview",
                "closure-path superseded PASS rereview",
                "rejected final rereview",
                "authority-drift adverse rereview",
                "authority-materialization adverse rereview",
                "public-closure adverse rereview",
                "governance-materialization superseded PASS rereview",
                "secret-scan-materialization superseded PASS rereview",
                "assurance-CLI-import superseded PASS rereview",
                "final rereview",
            )[index]
            task_key = (
                "initial_task",
                "adverse_task",
                "superseded_task",
                "transition_task",
                "integration_task",
                "evidence_task",
                "anchor_adverse_task",
                "governance_superseded_task",
                "materialization_adverse_task",
                "closure_path_superseded_task",
                "final_rejected_task",
                "authority_adverse_task",
                "authority_materialization_adverse_task",
                "public_closure_adverse_task",
                "governance_materialization_superseded_task",
                "secret_scan_materialization_superseded_task",
                "assurance_cli_import_superseded_task",
                "final_task",
            )[index]
            expected_task = expected[task_key]
            expected_request = (
                INITIAL_REQUEST_PATH,
                ADVERSE_REQUEST_PATH,
                SUPERSEDED_REQUEST_PATH,
                TRANSITION_REQUEST_PATH,
                INTEGRATION_REQUEST_PATH,
                EVIDENCE_REQUEST_PATH,
                ANCHOR_ADVERSE_REQUEST_PATH,
                GOVERNANCE_SUPERSEDED_REQUEST_PATH,
                MATERIALIZATION_ADVERSE_REQUEST_PATH,
                CLOSURE_PATH_SUPERSEDED_REQUEST_PATH,
                FINAL_REJECTED_REQUEST_PATH,
                AUTHORITY_ADVERSE_REQUEST_PATH,
                AUTHORITY_MATERIALIZATION_ADVERSE_REQUEST_PATH,
                PUBLIC_CLOSURE_ADVERSE_REQUEST_PATH,
                GOVERNANCE_MATERIALIZATION_SUPERSEDED_REQUEST_PATH,
                SECRET_SCAN_MATERIALIZATION_SUPERSEDED_REQUEST_PATH,
                ASSURANCE_CLI_IMPORT_SUPERSEDED_REQUEST_PATH,
                FINAL_REQUEST_PATH,
            )[index]
            reply_key = (
                "initial_reply",
                "adverse_reply",
                "superseded_reply",
                "transition_reply",
                "integration_reply",
                "evidence_reply",
                "anchor_adverse_reply",
                "governance_superseded_reply",
                "materialization_adverse_reply",
                "closure_path_superseded_reply",
                "final_rejected_reply",
                "authority_adverse_reply",
                "authority_materialization_adverse_reply",
                "public_closure_adverse_reply",
                "governance_materialization_superseded_reply",
                "secret_scan_materialization_superseded_reply",
                "assurance_cli_import_superseded_reply",
                "final_reply",
            )[index]
            expected_reply = expected[reply_key]
            if (
                attempt["requested_model"] != family
                or attempt["platform_task_id"] != expected_task
                or attempt["request"]["path"] != expected_request
                or attempt["reply"]["path"] != expected_reply
            ):
                errors.append(f"{path.name} {phase} invocation identity differs")
            all_task_ids.append(attempt["platform_task_id"])
            if index > 0:
                expected_commit = (
                    ADVERSE_CANDIDATE_COMMIT
                    if index == 1
                    else SUPERSEDED_CANDIDATE_COMMIT
                    if index == 2
                    else TRANSITION_CANDIDATE_COMMIT
                    if index == 3
                    else INTEGRATION_CANDIDATE_COMMIT
                    if index == 4
                    else EVIDENCE_CANDIDATE_COMMIT
                    if index == 5
                    else ANCHOR_ADVERSE_CANDIDATE_COMMIT
                    if index == 6
                    else GOVERNANCE_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT
                    if index == 7
                    else MATERIALIZATION_ADVERSE_EXECUTION_CANDIDATE_COMMIT
                    if index == 8
                    else CLOSURE_PATH_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT
                    if index == 9
                    else FINAL_REJECTED_EXECUTION_CANDIDATE_COMMIT
                    if index == 10
                    else AUTHORITY_ADVERSE_EXECUTION_CANDIDATE_COMMIT
                    if index == 11
                    else AUTHORITY_MATERIALIZATION_ADVERSE_EXECUTION_CANDIDATE_COMMIT
                    if index == 12
                    else PUBLIC_CLOSURE_ADVERSE_EXECUTION_CANDIDATE_COMMIT
                    if index == 13
                    else GOVERNANCE_MATERIALIZATION_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT
                    if index == 14
                    else SECRET_SCAN_MATERIALIZATION_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT
                    if index == 15
                    else ASSURANCE_CLI_IMPORT_SUPERSEDED_EXECUTION_CANDIDATE_COMMIT
                    if index == 16
                    else execution_candidate
                )
                expected_tree = (
                    ADVERSE_CANDIDATE_TREE
                    if index == 1
                    else SUPERSEDED_CANDIDATE_TREE
                    if index == 2
                    else TRANSITION_CANDIDATE_TREE
                    if index == 3
                    else INTEGRATION_CANDIDATE_TREE
                    if index == 4
                    else EVIDENCE_CANDIDATE_TREE
                    if index == 5
                    else ANCHOR_ADVERSE_CANDIDATE_TREE
                    if index == 6
                    else GOVERNANCE_SUPERSEDED_CANDIDATE_TREE
                    if index == 7
                    else MATERIALIZATION_ADVERSE_CANDIDATE_TREE
                    if index == 8
                    else CLOSURE_PATH_SUPERSEDED_CANDIDATE_TREE
                    if index == 9
                    else FINAL_REJECTED_CANDIDATE_TREE
                    if index == 10
                    else AUTHORITY_ADVERSE_CANDIDATE_TREE
                    if index == 11
                    else AUTHORITY_MATERIALIZATION_ADVERSE_CANDIDATE_TREE
                    if index == 12
                    else PUBLIC_CLOSURE_ADVERSE_CANDIDATE_TREE
                    if index == 13
                    else GOVERNANCE_MATERIALIZATION_SUPERSEDED_CANDIDATE_TREE
                    if index == 14
                    else SECRET_SCAN_MATERIALIZATION_SUPERSEDED_CANDIDATE_TREE
                    if index == 15
                    else ASSURANCE_CLI_IMPORT_SUPERSEDED_CANDIDATE_TREE
                    if index == 16
                    else subject["candidate_tree"]
                )
                expected_receipt_path = (
                    ADVERSE_RECEIPT_PATH
                    if index == 1
                    else SUPERSEDED_RECEIPT_PATH
                    if index == 2
                    else TRANSITION_RECEIPT_PATH
                    if index == 3
                    else INTEGRATION_RECEIPT_PATH
                    if index == 4
                    else EVIDENCE_RECEIPT_PATH
                    if index == 5
                    else ANCHOR_ADVERSE_RECEIPT_PATH
                    if index == 6
                    else GOVERNANCE_SUPERSEDED_RECEIPT_PATH
                    if index == 7
                    else MATERIALIZATION_ADVERSE_RECEIPT_PATH
                    if index == 8
                    else CLOSURE_PATH_SUPERSEDED_RECEIPT_PATH
                    if index == 9
                    else FINAL_REJECTED_RECEIPT_PATH
                    if index == 10
                    else AUTHORITY_ADVERSE_RECEIPT_PATH
                    if index == 11
                    else AUTHORITY_MATERIALIZATION_ADVERSE_RECEIPT_PATH
                    if index == 12
                    else PUBLIC_CLOSURE_ADVERSE_RECEIPT_PATH
                    if index == 13
                    else GOVERNANCE_MATERIALIZATION_SUPERSEDED_RECEIPT_PATH
                    if index == 14
                    else SECRET_SCAN_MATERIALIZATION_SUPERSEDED_RECEIPT_PATH
                    if index == 15
                    else ASSURANCE_CLI_IMPORT_SUPERSEDED_RECEIPT_PATH
                    if index == 16
                    else FINAL_RECEIPT_PATH
                )
                attempt_receipt_digest = _validate_execution_receipt(
                    root,
                    attempt.get("execution_receipt"),
                    expected_commit,
                    expected_tree,
                    expected_receipt_path,
                    errors,
                    EXPECTED_COMMAND_IDS if index >= 9 else LEGACY_COMMAND_IDS,
                )
                if attempt_receipt_digest is not None:
                    if index == 1:
                        adverse_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 2:
                        superseded_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 3:
                        transition_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 4:
                        integration_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 5:
                        evidence_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 6:
                        anchor_adverse_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 7:
                        governance_superseded_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 8:
                        materialization_adverse_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 9:
                        closure_path_superseded_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 10:
                        final_rejected_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 11:
                        authority_adverse_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 12:
                        authority_materialization_adverse_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 13:
                        public_closure_adverse_receipt_hashes.add(attempt_receipt_digest)
                    elif index == 14:
                        governance_materialization_superseded_receipt_hashes.add(
                            attempt_receipt_digest
                        )
                    elif index == 15:
                        secret_scan_materialization_superseded_receipt_hashes.add(
                            attempt_receipt_digest
                        )
                    elif index == 16:
                        assurance_cli_import_superseded_receipt_hashes.add(attempt_receipt_digest)
                    else:
                        final_receipt_hashes.add(attempt_receipt_digest)
                if (
                    index == len(attempts) - 1
                    and attempt.get("execution_receipt") != record["execution_receipt"]
                ):
                    errors.append(f"{path.name} final receipt differs from the record subject")
            request_loaded = _load_hashed_artifact(
                root,
                attempt["request"],
                errors,
                f"{path.name} {phase} request",
            )
            reply = _load_reply(
                root,
                attempt["reply"],
                reply_schema,
                errors,
                f"{path.name} {phase}",
            )
            replies.append(reply)
            if request_loaded is None or reply is None:
                continue
            _, request_payload = request_loaded
            request_hash = _sha256_bytes(request_payload)
            target = reply["target"]
            expected_commit = (
                INITIAL_CANDIDATE_COMMIT
                if index == 0
                else ADVERSE_CANDIDATE_COMMIT
                if index == 1
                else SUPERSEDED_CANDIDATE_COMMIT
                if index == 2
                else TRANSITION_CANDIDATE_COMMIT
                if index == 3
                else INTEGRATION_CANDIDATE_COMMIT
                if index == 4
                else EVIDENCE_CANDIDATE_COMMIT
                if index == 5
                else ANCHOR_ADVERSE_CANDIDATE_COMMIT
                if index == 6
                else GOVERNANCE_SUPERSEDED_CANDIDATE_COMMIT
                if index == 7
                else MATERIALIZATION_ADVERSE_CANDIDATE_COMMIT
                if index == 8
                else CLOSURE_PATH_SUPERSEDED_CANDIDATE_COMMIT
                if index == 9
                else FINAL_REJECTED_CANDIDATE_COMMIT
                if index == 10
                else AUTHORITY_ADVERSE_CANDIDATE_COMMIT
                if index == 11
                else AUTHORITY_MATERIALIZATION_ADVERSE_CANDIDATE_COMMIT
                if index == 12
                else PUBLIC_CLOSURE_ADVERSE_CANDIDATE_COMMIT
                if index == 13
                else GOVERNANCE_MATERIALIZATION_SUPERSEDED_CANDIDATE_COMMIT
                if index == 14
                else SECRET_SCAN_MATERIALIZATION_SUPERSEDED_CANDIDATE_COMMIT
                if index == 15
                else ASSURANCE_CLI_IMPORT_SUPERSEDED_CANDIDATE_COMMIT
                if index == 16
                else subject["candidate_commit"]
            )
            expected_tree = (
                INITIAL_CANDIDATE_TREE
                if index == 0
                else ADVERSE_CANDIDATE_TREE
                if index == 1
                else SUPERSEDED_CANDIDATE_TREE
                if index == 2
                else TRANSITION_CANDIDATE_TREE
                if index == 3
                else INTEGRATION_CANDIDATE_TREE
                if index == 4
                else EVIDENCE_CANDIDATE_TREE
                if index == 5
                else ANCHOR_ADVERSE_CANDIDATE_TREE
                if index == 6
                else GOVERNANCE_SUPERSEDED_CANDIDATE_TREE
                if index == 7
                else MATERIALIZATION_ADVERSE_CANDIDATE_TREE
                if index == 8
                else CLOSURE_PATH_SUPERSEDED_CANDIDATE_TREE
                if index == 9
                else FINAL_REJECTED_CANDIDATE_TREE
                if index == 10
                else AUTHORITY_ADVERSE_CANDIDATE_TREE
                if index == 11
                else AUTHORITY_MATERIALIZATION_ADVERSE_CANDIDATE_TREE
                if index == 12
                else PUBLIC_CLOSURE_ADVERSE_CANDIDATE_TREE
                if index == 13
                else GOVERNANCE_MATERIALIZATION_SUPERSEDED_CANDIDATE_TREE
                if index == 14
                else SECRET_SCAN_MATERIALIZATION_SUPERSEDED_CANDIDATE_TREE
                if index == 15
                else ASSURANCE_CLI_IMPORT_SUPERSEDED_CANDIDATE_TREE
                if index == 16
                else subject["candidate_tree"]
            )
            if (
                target["baseline_commit"] != BASELINE_COMMIT
                or target["candidate_commit"] != expected_commit
                or target["candidate_tree"] != expected_tree
                or target["request_sha256"] != request_hash
                or attempt["verdict"] != reply["verdict"]
                or expected_commit.encode("ascii") not in request_payload
                or expected_tree.encode("ascii") not in request_payload
            ):
                errors.append(f"{path.name} {phase} target binding differs")
            if index == 0:
                if (
                    request_hash != INITIAL_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["initial_reply_sha256"]
                    or reply["verdict"] != "FAIL"
                    or not any(item.get("status") == "OPEN" for item in reply["findings"])
                    or not _validate_dimensions(reply, must_pass=False)
                ):
                    errors.append(f"{path.name} initial adverse review is not faithfully preserved")
            elif index == 1:
                adverse_request_hashes.add(request_hash)
                adverse_reply_hashes.add(attempt["reply"]["sha256"])
                if (
                    request_hash != ADVERSE_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["adverse_reply_sha256"]
                    or reply["verdict"] != "FAIL"
                    or not _validate_dimensions(reply, must_pass=False)
                    or {item["id"] for item in reply["findings"] if item.get("status") == "OPEN"}
                    != {"RMD05-CLOSURE-001"}
                ):
                    errors.append(f"{path.name} adverse rereview is not faithfully preserved")
            elif index == 2:
                superseded_request_hashes.add(request_hash)
                superseded_reply_hashes.add(attempt["reply"]["sha256"])
                if (
                    request_hash != SUPERSEDED_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["superseded_reply_sha256"]
                    or reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                ):
                    errors.append(f"{path.name} superseded PASS review is not faithfully preserved")
            elif index == 3:
                transition_request_hashes.add(request_hash)
                transition_reply_hashes.add(attempt["reply"]["sha256"])
                transition_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != TRANSITION_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["transition_reply_sha256"]
                    or reply["verdict"] != "FAIL"
                    or not _validate_dimensions(reply, must_pass=False)
                    or transition_open != expected["transition_open_findings"]
                ):
                    errors.append(
                        f"{path.name} transition adverse rereview is not faithfully preserved"
                    )
            elif index == 4:
                integration_request_hashes.add(request_hash)
                integration_reply_hashes.add(attempt["reply"]["sha256"])
                integration_resolved = {
                    item["id"] for item in reply["findings"] if item.get("status") == "RESOLVED"
                }
                if (
                    request_hash != INTEGRATION_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["integration_reply_sha256"]
                    or reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    or not {"RMD05-CLOSURE-002", "RMD05-CLOSURE-003"}.issubset(integration_resolved)
                ):
                    errors.append(
                        f"{path.name} superseded output-integration PASS is not preserved"
                    )
            elif index == 5:
                evidence_request_hashes.add(request_hash)
                evidence_reply_hashes.add(attempt["reply"]["sha256"])
                evidence_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != EVIDENCE_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["evidence_reply_sha256"]
                    or reply["verdict"] != expected["evidence_verdict"]
                    or not _validate_dimensions(
                        reply, must_pass=expected["evidence_verdict"] == "PASS"
                    )
                    or evidence_open != expected["evidence_open_findings"]
                    or (
                        expected["evidence_verdict"] == "PASS"
                        and any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    )
                ):
                    errors.append(f"{path.name} evidence-coupling rereview is not preserved")
            elif index == 6:
                anchor_adverse_request_hashes.add(request_hash)
                anchor_adverse_reply_hashes.add(attempt["reply"]["sha256"])
                anchor_adverse_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != ANCHOR_ADVERSE_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["anchor_adverse_reply_sha256"]
                    or reply["verdict"] != expected["anchor_adverse_verdict"]
                    or not _validate_dimensions(
                        reply,
                        must_pass=expected["anchor_adverse_verdict"] == "PASS",
                    )
                    or anchor_adverse_open != expected["anchor_adverse_open_findings"]
                    or (
                        expected["anchor_adverse_verdict"] == "PASS"
                        and any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    )
                ):
                    errors.append(f"{path.name} receipt-anchor adverse rereview is not preserved")
            elif index == 7:
                governance_superseded_request_hashes.add(request_hash)
                governance_superseded_reply_hashes.add(attempt["reply"]["sha256"])
                governance_resolved = {
                    item["id"] for item in reply["findings"] if item.get("status") == "RESOLVED"
                }
                if (
                    request_hash != GOVERNANCE_SUPERSEDED_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["governance_superseded_reply_sha256"]
                    or reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    or not (
                        REQUIRED_FINAL_CLOSURE_FINDINGS
                        - {
                            "RMD05-CLOSURE-006",
                            "RMD05-CLOSURE-007",
                            "RMD05-CLOSURE-008",
                            "RMD05-CLOSURE-009",
                            "RMD05-CLOSURE-010",
                            "RMD05-CLOSURE-011",
                            "RMD05-CLOSURE-012",
                        }
                    ).issubset(governance_resolved)
                ):
                    errors.append(f"{path.name} superseded governance-facts PASS is not preserved")
            elif index == 8:
                materialization_adverse_request_hashes.add(request_hash)
                materialization_adverse_reply_hashes.add(attempt["reply"]["sha256"])
                materialization_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != MATERIALIZATION_ADVERSE_REQUEST_SHA256
                    or attempt["reply"]["sha256"]
                    != expected["materialization_adverse_reply_sha256"]
                    or reply["verdict"] != expected["materialization_adverse_verdict"]
                    or not _validate_dimensions(
                        reply,
                        must_pass=expected["materialization_adverse_verdict"] == "PASS",
                    )
                    or materialization_open != expected["materialization_adverse_open_findings"]
                    or (
                        expected["materialization_adverse_verdict"] == "PASS"
                        and any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    )
                ):
                    errors.append(
                        f"{path.name} output-materialization adverse rereview is not preserved"
                    )
            elif index == 9:
                closure_path_superseded_request_hashes.add(request_hash)
                closure_path_superseded_reply_hashes.add(attempt["reply"]["sha256"])
                closure_path_resolved = {
                    item["id"] for item in reply["findings"] if item.get("status") == "RESOLVED"
                }
                if (
                    request_hash != CLOSURE_PATH_SUPERSEDED_REQUEST_SHA256
                    or attempt["reply"]["sha256"]
                    != expected["closure_path_superseded_reply_sha256"]
                    or reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    or not (
                        REQUIRED_FINAL_CLOSURE_FINDINGS
                        - {
                            "RMD05-CLOSURE-007",
                            "RMD05-CLOSURE-008",
                            "RMD05-CLOSURE-009",
                            "RMD05-CLOSURE-010",
                            "RMD05-CLOSURE-011",
                            "RMD05-CLOSURE-012",
                        }
                    ).issubset(closure_path_resolved)
                ):
                    errors.append(f"{path.name} superseded closure-path PASS is not preserved")
            elif index == 10:
                final_rejected_request_hashes.add(request_hash)
                final_rejected_reply_hashes.add(attempt["reply"]["sha256"])
                final_rejected_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != FINAL_REJECTED_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["final_rejected_reply_sha256"]
                    or reply["verdict"] != "FAIL"
                    or not _validate_dimensions(reply, must_pass=False)
                    or final_rejected_open != {"RMD05-CLOSURE-008"}
                    or any(
                        item.get("status") != "RESOLVED"
                        for item in reply["findings"]
                        if item.get("id") != "RMD05-CLOSURE-008"
                    )
                ):
                    errors.append(f"{path.name} rejected final rereview is not preserved")
            elif index == 11:
                authority_adverse_request_hashes.add(request_hash)
                authority_adverse_reply_hashes.add(attempt["reply"]["sha256"])
                authority_adverse_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != AUTHORITY_ADVERSE_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["authority_adverse_reply_sha256"]
                    or reply["verdict"] != expected["authority_adverse_verdict"]
                    or not _validate_dimensions(
                        reply,
                        must_pass=expected["authority_adverse_verdict"] == "PASS",
                    )
                    or authority_adverse_open != expected["authority_adverse_open_findings"]
                    or (
                        expected["authority_adverse_verdict"] == "PASS"
                        and any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    )
                    or any(
                        item.get("status") != "RESOLVED"
                        for item in reply["findings"]
                        if item.get("id") != "RMD05-CLOSURE-009"
                    )
                ):
                    errors.append(f"{path.name} authority-drift adverse rereview is not preserved")
            elif index == 12:
                authority_materialization_adverse_request_hashes.add(request_hash)
                authority_materialization_adverse_reply_hashes.add(attempt["reply"]["sha256"])
                authority_materialization_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != AUTHORITY_MATERIALIZATION_ADVERSE_REQUEST_SHA256
                    or attempt["reply"]["sha256"]
                    != expected["authority_materialization_adverse_reply_sha256"]
                    or reply["verdict"] != expected["authority_materialization_adverse_verdict"]
                    or not _validate_dimensions(reply, must_pass=False)
                    or authority_materialization_open
                    != expected["authority_materialization_adverse_open_findings"]
                    or any(
                        item.get("status") != "RESOLVED"
                        for item in reply["findings"]
                        if item.get("id") != "RMD05-CLOSURE-009"
                    )
                ):
                    errors.append(
                        f"{path.name} authority-materialization adverse rereview is not preserved"
                    )
            elif index == 13:
                public_closure_adverse_request_hashes.add(request_hash)
                public_closure_adverse_reply_hashes.add(attempt["reply"]["sha256"])
                public_closure_open = {
                    item["id"] for item in reply["findings"] if item.get("status") == "OPEN"
                }
                if (
                    request_hash != PUBLIC_CLOSURE_ADVERSE_REQUEST_SHA256
                    or attempt["reply"]["sha256"] != expected["public_closure_adverse_reply_sha256"]
                    or reply["verdict"] != expected["public_closure_adverse_verdict"]
                    or not _validate_dimensions(reply, must_pass=False)
                    or public_closure_open != expected["public_closure_adverse_open_findings"]
                    or any(
                        item.get("status") != "RESOLVED"
                        for item in reply["findings"]
                        if item.get("id") != "RMD05-CLOSURE-009"
                    )
                ):
                    errors.append(f"{path.name} public-closure adverse rereview is not preserved")
            elif index == 14:
                governance_materialization_superseded_request_hashes.add(request_hash)
                governance_materialization_superseded_reply_hashes.add(attempt["reply"]["sha256"])
                governance_materialization_resolved = {
                    item["id"] for item in reply["findings"] if item.get("status") == "RESOLVED"
                }
                if (
                    request_hash != GOVERNANCE_MATERIALIZATION_SUPERSEDED_REQUEST_SHA256
                    or attempt["reply"]["sha256"]
                    != expected["governance_materialization_superseded_reply_sha256"]
                    or reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    or "RMD05-CLOSURE-009" not in governance_materialization_resolved
                ):
                    errors.append(
                        f"{path.name} superseded governance-materialization PASS is not preserved"
                    )
            elif index == 15:
                secret_scan_materialization_superseded_request_hashes.add(request_hash)
                secret_scan_materialization_superseded_reply_hashes.add(attempt["reply"]["sha256"])
                secret_scan_materialization_resolved = {
                    item["id"] for item in reply["findings"] if item.get("status") == "RESOLVED"
                }
                if (
                    request_hash != SECRET_SCAN_MATERIALIZATION_SUPERSEDED_REQUEST_SHA256
                    or attempt["reply"]["sha256"]
                    != expected["secret_scan_materialization_superseded_reply_sha256"]
                    or reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    or not (
                        REQUIRED_FINAL_CLOSURE_FINDINGS - {"RMD05-CLOSURE-011", "RMD05-CLOSURE-012"}
                    ).issubset(secret_scan_materialization_resolved)
                ):
                    errors.append(
                        f"{path.name} superseded secret-scan-materialization PASS is not preserved"
                    )
            elif index == 16:
                assurance_cli_import_superseded_request_hashes.add(request_hash)
                assurance_cli_import_superseded_reply_hashes.add(attempt["reply"]["sha256"])
                assurance_cli_import_superseded_resolved = {
                    item["id"] for item in reply["findings"] if item.get("status") == "RESOLVED"
                }
                if (
                    request_hash != ASSURANCE_CLI_IMPORT_SUPERSEDED_REQUEST_SHA256
                    or attempt["reply"]["sha256"]
                    != expected["assurance_cli_import_superseded_reply_sha256"]
                    or reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    or not (REQUIRED_FINAL_CLOSURE_FINDINGS - {"RMD05-CLOSURE-012"}).issubset(
                        assurance_cli_import_superseded_resolved
                    )
                ):
                    errors.append(
                        f"{path.name} superseded assurance-CLI-import PASS is not preserved"
                    )
            else:
                final_request_hashes.add(request_hash)
                final_reply_hashes.add(attempt["reply"]["sha256"])
                final_resolved = {
                    item["id"] for item in reply["findings"] if item.get("status") == "RESOLVED"
                }
                if (
                    reply["verdict"] != "PASS"
                    or not _validate_dimensions(reply, must_pass=True)
                    or any(item.get("status") != "RESOLVED" for item in reply["findings"])
                    or not REQUIRED_FINAL_CLOSURE_FINDINGS.issubset(final_resolved)
                ):
                    errors.append(f"{path.name} rereview conclusion is not closed")

        if len(replies) in {17, 18} and all(reply is not None for reply in replies):
            initial = cast(dict[str, Any], replies[0])
            adverse = cast(dict[str, Any], replies[1])
            superseded = cast(dict[str, Any], replies[2])
            transition = cast(dict[str, Any], replies[3])
            integration = cast(dict[str, Any], replies[4])
            evidence = cast(dict[str, Any], replies[5])
            anchor_adverse = cast(dict[str, Any], replies[6])
            governance_superseded = cast(dict[str, Any], replies[7])
            materialization_adverse = cast(dict[str, Any], replies[8])
            closure_path_superseded = cast(dict[str, Any], replies[9])
            final_rejected = cast(dict[str, Any], replies[10])
            authority_adverse = cast(dict[str, Any], replies[11])
            authority_materialization_adverse = cast(dict[str, Any], replies[12])
            public_closure_adverse = cast(dict[str, Any], replies[13])
            governance_materialization_superseded = cast(dict[str, Any], replies[14])
            secret_scan_materialization_superseded = cast(dict[str, Any], replies[15])
            assurance_cli_import_superseded = cast(dict[str, Any], replies[16])
            final = cast(dict[str, Any], replies[17]) if len(replies) == 18 else None
            initial_ids = {
                item["id"] for item in initial["findings"] if item.get("status") == "OPEN"
            }
            adverse_resolved_ids = {
                item["id"] for item in adverse["findings"] if item.get("status") == "RESOLVED"
            }
            adverse_open_ids = {
                item["id"] for item in adverse["findings"] if item.get("status") == "OPEN"
            }
            superseded_resolved_ids = {
                item["id"] for item in superseded["findings"] if item.get("status") == "RESOLVED"
            }
            transition_resolved_ids = {
                item["id"] for item in transition["findings"] if item.get("status") == "RESOLVED"
            }
            transition_open_ids = {
                item["id"] for item in transition["findings"] if item.get("status") == "OPEN"
            }
            integration_resolved_ids = {
                item["id"] for item in integration["findings"] if item.get("status") == "RESOLVED"
            }
            evidence_resolved_ids = {
                item["id"] for item in evidence["findings"] if item.get("status") == "RESOLVED"
            }
            anchor_adverse_resolved_ids = {
                item["id"]
                for item in anchor_adverse["findings"]
                if item.get("status") == "RESOLVED"
            }
            governance_superseded_resolved_ids = {
                item["id"]
                for item in governance_superseded["findings"]
                if item.get("status") == "RESOLVED"
            }
            materialization_resolved_ids = {
                item["id"]
                for item in materialization_adverse["findings"]
                if item.get("status") == "RESOLVED"
            }
            closure_path_superseded_resolved_ids = {
                item["id"]
                for item in closure_path_superseded["findings"]
                if item.get("status") == "RESOLVED"
            }
            final_rejected_resolved_ids = {
                item["id"]
                for item in final_rejected["findings"]
                if item.get("status") == "RESOLVED"
            }
            authority_adverse_resolved_ids = {
                item["id"]
                for item in authority_adverse["findings"]
                if item.get("status") == "RESOLVED"
            }
            authority_materialization_adverse_resolved_ids = {
                item["id"]
                for item in authority_materialization_adverse["findings"]
                if item.get("status") == "RESOLVED"
            }
            public_closure_adverse_resolved_ids = {
                item["id"]
                for item in public_closure_adverse["findings"]
                if item.get("status") == "RESOLVED"
            }
            governance_materialization_superseded_resolved_ids = {
                item["id"]
                for item in governance_materialization_superseded["findings"]
                if item.get("status") == "RESOLVED"
            }
            secret_scan_materialization_superseded_resolved_ids = {
                item["id"]
                for item in secret_scan_materialization_superseded["findings"]
                if item.get("status") == "RESOLVED"
            }
            assurance_cli_import_superseded_resolved_ids = {
                item["id"]
                for item in assurance_cli_import_superseded["findings"]
                if item.get("status") == "RESOLVED"
            }
            if not initial_ids or not initial_ids.issubset(adverse_resolved_ids):
                errors.append(f"{path.name} adverse rereview lost an initial finding closure")
            prior_ids = initial_ids | adverse_open_ids
            if not adverse_open_ids or not prior_ids.issubset(superseded_resolved_ids):
                errors.append(
                    f"{path.name} superseded PASS rereview does not close every adverse finding ID"
                )
            superseded_ids = {item["id"] for item in superseded["findings"]}
            pre_transition_ids = (
                {item["id"] for item in initial["findings"]}
                | {item["id"] for item in adverse["findings"]}
                | superseded_ids
            )
            if not transition_open_ids or not pre_transition_ids.issubset(transition_resolved_ids):
                errors.append(
                    f"{path.name} transition adverse rereview lost a prior finding closure"
                )
            full_history_ids = pre_transition_ids | {item["id"] for item in transition["findings"]}
            if not full_history_ids.issubset(integration_resolved_ids):
                errors.append(
                    f"{path.name} superseded output-integration PASS lost a prior finding closure"
                )
            integration_history_ids = full_history_ids | {
                item["id"] for item in integration["findings"]
            }
            if not integration_history_ids.issubset(evidence_resolved_ids):
                errors.append(
                    f"{path.name} evidence-coupling rereview lost a prior finding closure"
                )
            evidence_history_ids = integration_history_ids | {
                item["id"] for item in evidence["findings"]
            }
            if not evidence_history_ids.issubset(anchor_adverse_resolved_ids):
                errors.append(
                    f"{path.name} receipt-anchor adverse rereview lost a prior finding closure"
                )
            anchor_history_ids = evidence_history_ids | {
                item["id"] for item in anchor_adverse["findings"]
            }
            if not anchor_history_ids.issubset(governance_superseded_resolved_ids):
                errors.append(f"{path.name} governance-facts rereview lost a prior finding closure")
            governance_history_ids = anchor_history_ids | {
                item["id"] for item in governance_superseded["findings"]
            }
            if not governance_history_ids.issubset(materialization_resolved_ids):
                errors.append(
                    f"{path.name} output-materialization rereview lost a prior finding closure"
                )
            materialization_history_ids = governance_history_ids | {
                item["id"] for item in materialization_adverse["findings"]
            }
            if not materialization_history_ids.issubset(closure_path_superseded_resolved_ids):
                errors.append(
                    f"{path.name} superseded closure-path rereview lost a prior finding closure"
                )
            closure_path_history_ids = materialization_history_ids | {
                item["id"] for item in closure_path_superseded["findings"]
            }
            if not closure_path_history_ids.issubset(final_rejected_resolved_ids):
                errors.append(f"{path.name} rejected final rereview lost a prior finding closure")
            final_rejected_history_ids = closure_path_history_ids | {
                item["id"] for item in final_rejected["findings"]
            }
            if not final_rejected_history_ids.issubset(authority_adverse_resolved_ids):
                errors.append(f"{path.name} authority-drift rereview lost a prior finding closure")
            authority_adverse_history_ids = final_rejected_history_ids | {
                item["id"] for item in authority_adverse["findings"]
            }
            if not (authority_adverse_history_ids - {"RMD05-CLOSURE-009"}).issubset(
                authority_materialization_adverse_resolved_ids
            ):
                errors.append(
                    f"{path.name} authority-materialization rereview lost a prior finding closure"
                )
            authority_materialization_history_ids = authority_adverse_history_ids | {
                item["id"] for item in authority_materialization_adverse["findings"]
            }
            if not (authority_materialization_history_ids - {"RMD05-CLOSURE-009"}).issubset(
                public_closure_adverse_resolved_ids
            ):
                errors.append(f"{path.name} public-closure rereview lost a prior finding closure")
            public_closure_history_ids = authority_materialization_history_ids | {
                item["id"] for item in public_closure_adverse["findings"]
            }
            if not public_closure_history_ids.issubset(
                governance_materialization_superseded_resolved_ids
            ):
                errors.append(
                    f"{path.name} governance-materialization rereview lost a prior finding closure"
                )
            governance_materialization_history_ids = public_closure_history_ids | {
                item["id"] for item in governance_materialization_superseded["findings"]
            }
            if not governance_materialization_history_ids.issubset(
                secret_scan_materialization_superseded_resolved_ids
            ):
                errors.append(
                    f"{path.name} secret-scan-materialization rereview lost a prior finding closure"
                )
            secret_scan_materialization_history_ids = governance_materialization_history_ids | {
                item["id"] for item in secret_scan_materialization_superseded["findings"]
            }
            if not secret_scan_materialization_history_ids.issubset(
                assurance_cli_import_superseded_resolved_ids
            ):
                errors.append(
                    f"{path.name} assurance-CLI-import rereview lost a prior finding closure"
                )
            if final is not None:
                final_resolved_ids = {
                    item["id"] for item in final["findings"] if item.get("status") == "RESOLVED"
                }
                assurance_cli_import_history_ids = secret_scan_materialization_history_ids | {
                    item["id"] for item in assurance_cli_import_superseded["findings"]
                }
                required_final_history = assurance_cli_import_history_ids | {"RMD05-CLOSURE-012"}
                if not required_final_history.issubset(final_resolved_ids):
                    errors.append(
                        f"{path.name} final rereview does not close the full finding history"
                    )

    if len(records) != 2 or len({record["model_family"] for record in records}) != 2:
        errors.append("two distinct model families are not proven")
    if len(closure_statuses) != 1:
        errors.append("review provenance closure states differ")
    closure_status = next(iter(closure_statuses), "BLOCKED")
    expected_task_count = 2 * (
        BLOCKED_REVIEW_ATTEMPTS_PER_MODEL
        if closure_status == "BLOCKED"
        else FINAL_REVIEW_ATTEMPTS_PER_MODEL
    )
    if len(all_task_ids) != expected_task_count or len(set(all_task_ids)) != expected_task_count:
        errors.append("all initial and rereview platform task identifiers must be distinct")
    if len(subjects) != 1:
        errors.append("reviewers did not inspect the same immutable candidate")
    if closure_status == "PASS":
        if len(final_request_hashes) != 1:
            errors.append("reviewers did not receive the same immutable final rereview request")
        if len(final_reply_hashes) != 2:
            errors.append("independent final rereview reply artifacts are not distinct")
    elif final_request_hashes or final_reply_hashes or final_receipt_hashes:
        errors.append("blocked pre-final history must not contain a synthetic final review")
    if adverse_request_hashes != {ADVERSE_REQUEST_SHA256}:
        errors.append("the shared adverse rereview request is not preserved")
    if len(adverse_reply_hashes) != 2:
        errors.append("the two adverse rereview replies are not preserved")
    if adverse_receipt_hashes != {ADVERSE_RECEIPT_SHA256}:
        errors.append("the candidate-bound adverse execution receipt is not preserved")
    if superseded_request_hashes != {SUPERSEDED_REQUEST_SHA256}:
        errors.append("the shared superseded PASS request is not preserved")
    if len(superseded_reply_hashes) != 2:
        errors.append("the two superseded PASS replies are not preserved")
    if superseded_receipt_hashes != {SUPERSEDED_RECEIPT_SHA256}:
        errors.append("the candidate-bound superseded PASS receipt is not preserved")
    if transition_request_hashes != {TRANSITION_REQUEST_SHA256}:
        errors.append("the shared transition adverse rereview request is not preserved")
    if len(transition_reply_hashes) != 2:
        errors.append("the two transition adverse rereview replies are not preserved")
    if transition_receipt_hashes != {TRANSITION_RECEIPT_SHA256}:
        errors.append("the candidate-bound transition adverse execution receipt is not preserved")
    if integration_request_hashes != {INTEGRATION_REQUEST_SHA256}:
        errors.append("the shared superseded output-integration request is not preserved")
    if len(integration_reply_hashes) != 2:
        errors.append("the two superseded output-integration PASS replies are not preserved")
    if integration_receipt_hashes != {INTEGRATION_RECEIPT_SHA256}:
        errors.append("the superseded output-integration execution receipt is not preserved")
    if evidence_request_hashes != {EVIDENCE_REQUEST_SHA256}:
        errors.append("the shared evidence-coupling rereview request is not preserved")
    if len(evidence_reply_hashes) != 2:
        errors.append("the two evidence-coupling rereview replies are not preserved")
    if evidence_receipt_hashes != {EVIDENCE_RECEIPT_SHA256}:
        errors.append("the evidence-coupling execution receipt is not preserved")
    if anchor_adverse_request_hashes != {ANCHOR_ADVERSE_REQUEST_SHA256}:
        errors.append("the shared receipt-anchor adverse rereview request is not preserved")
    if len(anchor_adverse_reply_hashes) != 2:
        errors.append("the two receipt-anchor adverse rereview replies are not preserved")
    if anchor_adverse_receipt_hashes != {ANCHOR_ADVERSE_RECEIPT_SHA256}:
        errors.append("the receipt-anchor adverse execution receipt is not preserved")
    if governance_superseded_request_hashes != {GOVERNANCE_SUPERSEDED_REQUEST_SHA256}:
        errors.append("the shared superseded governance-facts request is not preserved")
    if len(governance_superseded_reply_hashes) != 2:
        errors.append("the two superseded governance-facts PASS replies are not preserved")
    if governance_superseded_receipt_hashes != {GOVERNANCE_SUPERSEDED_RECEIPT_SHA256}:
        errors.append("the superseded governance-facts execution receipt is not preserved")
    if materialization_adverse_request_hashes != {MATERIALIZATION_ADVERSE_REQUEST_SHA256}:
        errors.append("the shared output-materialization adverse request is not preserved")
    if len(materialization_adverse_reply_hashes) != 2:
        errors.append("the two output-materialization adverse replies are not preserved")
    if materialization_adverse_receipt_hashes != {MATERIALIZATION_ADVERSE_RECEIPT_SHA256}:
        errors.append("the output-materialization adverse execution receipt is not preserved")
    if closure_path_superseded_request_hashes != {CLOSURE_PATH_SUPERSEDED_REQUEST_SHA256}:
        errors.append("the shared superseded closure-path request is not preserved")
    if len(closure_path_superseded_reply_hashes) != 2:
        errors.append("the two superseded closure-path PASS replies are not preserved")
    if closure_path_superseded_receipt_hashes != {CLOSURE_PATH_SUPERSEDED_RECEIPT_SHA256}:
        errors.append("the superseded closure-path execution receipt is not preserved")
    if final_rejected_request_hashes != {FINAL_REJECTED_REQUEST_SHA256}:
        errors.append("the shared rejected final rereview request is not preserved")
    if len(final_rejected_reply_hashes) != 2:
        errors.append("the two rejected final rereview replies are not preserved")
    if final_rejected_receipt_hashes != {FINAL_REJECTED_RECEIPT_SHA256}:
        errors.append("the rejected final execution receipt is not preserved")
    if authority_adverse_request_hashes != {AUTHORITY_ADVERSE_REQUEST_SHA256}:
        errors.append("the shared authority-drift adverse rereview request is not preserved")
    if len(authority_adverse_reply_hashes) != 2:
        errors.append("the two authority-drift adverse rereview replies are not preserved")
    if authority_adverse_receipt_hashes != {AUTHORITY_ADVERSE_RECEIPT_SHA256}:
        errors.append("the authority-drift adverse execution receipt is not preserved")
    if authority_materialization_adverse_request_hashes != {
        AUTHORITY_MATERIALIZATION_ADVERSE_REQUEST_SHA256
    }:
        errors.append(
            "the shared authority-materialization adverse rereview request is not preserved"
        )
    if len(authority_materialization_adverse_reply_hashes) != 2:
        errors.append(
            "the two authority-materialization adverse rereview replies are not preserved"
        )
    if authority_materialization_adverse_receipt_hashes != {
        AUTHORITY_MATERIALIZATION_ADVERSE_RECEIPT_SHA256
    }:
        errors.append("the authority-materialization adverse execution receipt is not preserved")
    if public_closure_adverse_request_hashes != {PUBLIC_CLOSURE_ADVERSE_REQUEST_SHA256}:
        errors.append("the shared public-closure adverse rereview request is not preserved")
    if len(public_closure_adverse_reply_hashes) != 2:
        errors.append("the two public-closure adverse rereview replies are not preserved")
    if public_closure_adverse_receipt_hashes != {PUBLIC_CLOSURE_ADVERSE_RECEIPT_SHA256}:
        errors.append("the public-closure adverse execution receipt is not preserved")
    if governance_materialization_superseded_request_hashes != {
        GOVERNANCE_MATERIALIZATION_SUPERSEDED_REQUEST_SHA256
    }:
        errors.append("the shared superseded governance-materialization request is not preserved")
    if len(governance_materialization_superseded_reply_hashes) != 2:
        errors.append(
            "the two superseded governance-materialization PASS replies are not preserved"
        )
    if governance_materialization_superseded_receipt_hashes != {
        GOVERNANCE_MATERIALIZATION_SUPERSEDED_RECEIPT_SHA256
    }:
        errors.append(
            "the superseded governance-materialization execution receipt is not preserved"
        )
    if secret_scan_materialization_superseded_request_hashes != {
        SECRET_SCAN_MATERIALIZATION_SUPERSEDED_REQUEST_SHA256
    }:
        errors.append("the shared superseded secret-scan-materialization request is not preserved")
    if len(secret_scan_materialization_superseded_reply_hashes) != 2:
        errors.append(
            "the two superseded secret-scan-materialization PASS replies are not preserved"
        )
    if secret_scan_materialization_superseded_receipt_hashes != {
        SECRET_SCAN_MATERIALIZATION_SUPERSEDED_RECEIPT_SHA256
    }:
        errors.append(
            "the superseded secret-scan-materialization execution receipt is not preserved"
        )
    if assurance_cli_import_superseded_request_hashes != {
        ASSURANCE_CLI_IMPORT_SUPERSEDED_REQUEST_SHA256
    }:
        errors.append("the shared superseded assurance-CLI-import request is not preserved")
    if len(assurance_cli_import_superseded_reply_hashes) != 2:
        errors.append("the two superseded assurance-CLI-import PASS replies are not preserved")
    if assurance_cli_import_superseded_receipt_hashes != {
        ASSURANCE_CLI_IMPORT_SUPERSEDED_RECEIPT_SHA256
    }:
        errors.append("the superseded assurance-CLI-import execution receipt is not preserved")
    terminal_receipt_hashes = (
        assurance_cli_import_superseded_receipt_hashes
        if closure_status == "BLOCKED"
        else final_receipt_hashes
    )
    if len(terminal_receipt_hashes) != 1 or terminal_receipt_hashes != top_level_receipt_hashes:
        errors.append("reviewers are not bound to the same terminal execution receipt")
    if verify_git and len(subjects) == 1:
        candidate_commit, candidate_tree = next(iter(subjects))
        authority_paths = _validate_git_subject(
            repository_root,
            candidate_commit,
            candidate_tree,
            errors,
            allow_post_review_authorities=closure_status == "PASS",
        )
        if closure_status == "PASS":
            _validate_post_review_authorities(
                root,
                repository_root,
                authority_paths,
                errors,
                candidate_commit=candidate_commit,
            )

    return {
        "schema_version": "moomooau.assurance-provenance-verification.v1",
        "status": "PASS" if not errors and closure_status == "PASS" else "BLOCKED",
        "history_integrity": "PASS" if not errors else "BLOCKED",
        "pending_final_review": closure_status == "BLOCKED" and not errors,
        "review_records": len(records),
        "distinct_model_families": len({record["model_family"] for record in records}),
        "distinct_platform_tasks": len(set(all_task_ids)),
        "preserved_adverse_rereviews": len(adverse_reply_hashes),
        "preserved_superseded_pass_reviews": len(superseded_reply_hashes),
        "preserved_transition_adverse_reviews": len(transition_reply_hashes),
        "preserved_integration_superseded_pass_reviews": len(integration_reply_hashes),
        "preserved_evidence_coupling_reviews": len(evidence_reply_hashes),
        "preserved_receipt_anchor_reviews": len(anchor_adverse_reply_hashes),
        "preserved_governance_facts_superseded_reviews": len(governance_superseded_reply_hashes),
        "preserved_output_materialization_adverse_reviews": len(
            materialization_adverse_reply_hashes
        ),
        "preserved_closure_path_superseded_reviews": len(closure_path_superseded_reply_hashes),
        "preserved_final_rejected_reviews": len(final_rejected_reply_hashes),
        "preserved_authority_drift_adverse_reviews": len(authority_adverse_reply_hashes),
        "preserved_authority_materialization_adverse_reviews": len(
            authority_materialization_adverse_reply_hashes
        ),
        "preserved_public_closure_adverse_reviews": len(public_closure_adverse_reply_hashes),
        "preserved_governance_materialization_superseded_reviews": len(
            governance_materialization_superseded_reply_hashes
        ),
        "preserved_secret_scan_materialization_superseded_reviews": len(
            secret_scan_materialization_superseded_reply_hashes
        ),
        "preserved_assurance_cli_import_superseded_reviews": len(
            assurance_cli_import_superseded_reply_hashes
        ),
        "errors": errors,
        "repository_attestation_scope": "STRUCTURE_HASH_AND_TASK_ID_ONLY",
        "platform_audit_log_required": True,
    }


def evaluate_immutable_predecessor(
    root: Path = PROJECT_ROOT,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Validate the closed RMD-05 package without requiring non-portable Git objects."""

    root = root.resolve()
    result = evaluate_assurance_reviews(
        root,
        repository_root,
        verify_git=False,
        verify_anchor=False,
    )
    errors = list(cast(list[str], result.get("errors", [])))
    predecessor = root / RMD05_PREDECESSOR_MANIFEST_PATH
    try:
        predecessor_valid = (
            predecessor.is_file()
            and not predecessor.is_symlink()
            and _sha256_bytes(predecessor.read_bytes()) == RMD05_PREDECESSOR_MANIFEST_SHA256
        )
    except OSError:
        predecessor_valid = False
    if not predecessor_valid:
        errors.append("immutable RMD-05 predecessor manifest differs")

    portable = dict(result)
    portable["validation_mode"] = "IMMUTABLE_PACKAGE_PREDECESSOR"
    portable["git_objects_required"] = False
    portable["errors"] = errors
    portable["history_integrity"] = "PASS" if not errors else "BLOCKED"
    portable["status"] = "PASS" if result.get("status") == "PASS" and not errors else "BLOCKED"
    return portable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--history-only",
        action="store_true",
        help="validate an honestly BLOCKED history while the eighteenth reply pair is pending",
    )
    mode.add_argument(
        "--immutable-predecessor",
        action="store_true",
        help=(
            "validate the hash-pinned closed RMD-05 package after a clean-history snapshot "
            "without requiring its superseded Git objects"
        ),
    )
    args = parser.parse_args()
    if args.immutable_predecessor:
        result = evaluate_immutable_predecessor(args.root, args.repository_root)
    else:
        result = evaluate_assurance_reviews(
            args.root,
            args.repository_root,
            verify_git=not args.history_only,
            verify_anchor=True,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.history_only:
        return 0 if result.get("history_integrity") == "PASS" else 1
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DIMENSIONS = {"SCOPE", "EVIDENCE_QUALITY", "FAILURE_HONESTY", "ROLLBACK"}
INITIAL_REQUEST_SHA256 = "35247bddc79077b568509097cb9285e9a05299180a2833c8238b1cadac6c4e93"  # pragma: allowlist secret  # noqa: E501
INITIAL_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "843e84445731e02c02f8e02bbcc8cd2091f428387356efeb0ae4dbe2120fc0bd"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "646786d09804730e98c71652c1ad98fede5d697c17c0a1d1ee6a0c81283ee9a3"  # pragma: allowlist secret  # noqa: E501
    ),
}
ADVERSE_REQUEST_SHA256 = "e3fa55cb020a66dd2f17915f4015f0e62942e0aef1c93bc6152f193933fb85f4"  # pragma: allowlist secret  # noqa: E501
ADVERSE_RECEIPT_SHA256 = "aed2a3dd2d5df19536e49d963755e229b0d4ac569365fb74f58df99fc72fd1fc"  # pragma: allowlist secret  # noqa: E501
ADVERSE_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "5f1072d2e2e6525897fa5dca67bfb081e149bb35e5973abf9832c8d7bb417461"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "bb2a72bf7c63425aca444eaf407a566de2d6f6e67f9a23dde295fc2f344fa718"  # pragma: allowlist secret  # noqa: E501
    ),
}
SUPERSEDED_REQUEST_SHA256 = "f57ca7d53d2dee988b6067d6ce8f4ff4bc17eb849e134c3f5802c318bdbb1c79"  # pragma: allowlist secret  # noqa: E501
SUPERSEDED_RECEIPT_SHA256 = "e6d076632bcc36b410a04765bd4d3ebc69af16849266b3da429b7f0eb4cc9380"  # pragma: allowlist secret  # noqa: E501
SUPERSEDED_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "9c4bf4f5c7c2018958f966edcc96898a2da5351fcb1a22900320b0da854a2796"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "10cd7d8d407fbfdc39656c8eba589997c635fd856878e327dd4a7ce79e0ebfb2"  # pragma: allowlist secret  # noqa: E501
    ),
}
TRANSITION_REQUEST_SHA256 = "113b08b9262cee2c0e3900e32efe3d14f643d9d19c6afbed1b18ae46532d87d1"  # pragma: allowlist secret  # noqa: E501
TRANSITION_RECEIPT_SHA256 = "88d1db524f1d9421c806a73d532c9307b3b3a699b030964ce58dfd5650bd3a24"  # pragma: allowlist secret  # noqa: E501
TRANSITION_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "7f301af5d14133095743bc0ab16c33ec673546e2873b1727992869b564ec5b88"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "36fe590612c5c8d786e28f001cfda6dc41886e95a4a40e579ebd7a14ca334d36"  # pragma: allowlist secret  # noqa: E501
    ),
}
INTEGRATION_REQUEST_SHA256 = "62c9291f5ea6ef39a1123a4c96adaf7e3a58a2a69a5b36369818e99e381e17be"  # pragma: allowlist secret  # noqa: E501
INTEGRATION_RECEIPT_SHA256 = "3359865176269e7eb1da39aa38d6fc9e8230e530f8d02a25f3d8b5f4a3057fc2"  # pragma: allowlist secret  # noqa: E501
INTEGRATION_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "7e52b323b1a69d1d15c110b8781e3de66e06787ac21a82a8d51db340f4327268"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "7809fbf2909ff4080b9611c128cc36bc232e1b84f2d04d2564343524464fb58f"  # pragma: allowlist secret  # noqa: E501
    ),
}
EVIDENCE_REQUEST_SHA256 = "45e531415d8176d599f7573f22770b5110211a41c724f524fccd9dbc590dc2d7"  # pragma: allowlist secret  # noqa: E501
EVIDENCE_RECEIPT_SHA256 = "407519737d85e754ad6b4b9fdc4cbb0f2a182b5c60d9f9b90bd8a71db8525465"  # pragma: allowlist secret  # noqa: E501
EVIDENCE_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "cc68de21447759a2fd19a4f73c2f135294833aace3d99c8022b21ba6cd515665"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "a3a92441c86b145835bd6babca873f0dcb89cb0840f5541d5c0af31812ab0ed0"  # pragma: allowlist secret  # noqa: E501
    ),
}
ANCHOR_ADVERSE_REQUEST_SHA256 = "4f3a7f841691095985649545f09ecbf531a7bb9908bfbc6d318d541cdd396d78"  # pragma: allowlist secret  # noqa: E501
ANCHOR_ADVERSE_RECEIPT_SHA256 = "9c1b087a4d24f49069305b1892553f6ab7d579892cc71bfa77ff0e102d143650"  # pragma: allowlist secret  # noqa: E501
ANCHOR_ADVERSE_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "93b8c0766935ac369cebbbd9e7a29db3dea32b4a35754ba3454dd7691263d385"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "375f087ee5b4779a16e0e0d31585d04fc5a4914af4756cf29078a6e6f13244b4"  # pragma: allowlist secret  # noqa: E501
    ),
}
GOVERNANCE_SUPERSEDED_REQUEST_SHA256 = "9831ab147d4fcfc06dee96f65c1c90e5de6dcacac523ef81b9f375c244bff394"  # pragma: allowlist secret  # noqa: E501
GOVERNANCE_SUPERSEDED_RECEIPT_SHA256 = "820b18a3c45891db7ab05d2ed95fed2593f81546dcb7031ce5fc96d707386b1d"  # pragma: allowlist secret  # noqa: E501
GOVERNANCE_SUPERSEDED_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "1ad4a93204a1f33a92d147025ef0262e2a1512a035ce0e7f76687cad0dbaee76"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "e668c13369cd4ec4681804f1a4ffd5bcfa7c9ba69eca755375ada63ca6090a72"  # pragma: allowlist secret  # noqa: E501
    ),
}
MATERIALIZATION_ADVERSE_REQUEST_SHA256 = "b666a68b2e47cb2ea9886a8224c5b2aee93a1a6297c3e31726718e9e434dabf7"  # pragma: allowlist secret  # noqa: E501
MATERIALIZATION_ADVERSE_RECEIPT_SHA256 = "e349452dae4ec5dd1ac613046d81f1fad0ad2fadaa08f5bb2568a496237795ef"  # pragma: allowlist secret  # noqa: E501
MATERIALIZATION_ADVERSE_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "df7ecfdd37d47b4ba3455768ea2e0b981a1d73263df3891e2ae50ed20bcda0a1"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "0e3b9af0e69036ff518fe9ccad03b26e9b6fb9090d2cd8a0e1510fd6dca1509c"  # pragma: allowlist secret  # noqa: E501
    ),
}
CLOSURE_PATH_SUPERSEDED_REQUEST_SHA256 = "47f32c2dadd542da4a69fd05508a4844ffca8952782dec201513db886541a74e"  # pragma: allowlist secret  # noqa: E501
CLOSURE_PATH_SUPERSEDED_RECEIPT_SHA256 = "2814dcca4c0d8a52e255760ed7b414a78e02a21f89745547f03986113ced7f68"  # pragma: allowlist secret  # noqa: E501
CLOSURE_PATH_SUPERSEDED_REPLY_SHA256 = {
    "gpt-5.6-sol.reply.json": (
        "9a7ce284b6ce71106b4b6ff3a5337c67887e8647b0db13d4b77f6a79e6da24a7"  # pragma: allowlist secret  # noqa: E501
    ),
    "gpt-5.6-terra.reply.json": (
        "d5cb77bd8292de829ba213c5daad079c8157e351d6840754006cac4f7b9e24d2"  # pragma: allowlist secret  # noqa: E501
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t0606_initial_adverse_replies_are_faithful_candidate_bound_v2_records() -> None:
    schema = json.loads(
        (PROJECT_ROOT / "machine/stages/S6/schemas/review-reply-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    request = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05/request.md"
    assert _sha256(request) == INITIAL_REQUEST_SHA256
    paths = sorted((request.parent / "initial").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(INITIAL_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == INITIAL_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert not list(validator.iter_errors(reply))
        assert reply["target"]["request_sha256"] == INITIAL_REQUEST_SHA256
        assert reply["verdict"] == "FAIL"
        dimensions = {item["id"]: item["status"] for item in reply["dimensions"]}
        assert set(dimensions) == REQUIRED_DIMENSIONS
        assert "FAIL" in dimensions.values()
        assert any(item["status"] == "OPEN" for item in reply["findings"])
        assert reply["sensitive_data_observed"] is False
        assert reply["production_or_protected_claimed"] is False


def test_t0606_v2_schemas_require_hashes_task_ids_and_candidate_execution_binding() -> None:
    schema_names = (
        "execution-receipt-v1.schema.json",
        "review-provenance-v2.schema.json",
        "review-reply-v2.schema.json",
        "stage6-evidence-v2.schema.json",
    )
    schemas = PROJECT_ROOT / "machine/stages/S6/schemas"
    for name in schema_names:
        Draft202012Validator.check_schema(json.loads((schemas / name).read_text(encoding="utf-8")))
    provenance = (schemas / "review-provenance-v2.schema.json").read_text(encoding="utf-8")
    evidence = (schemas / "stage6-evidence-v2.schema.json").read_text(encoding="utf-8")
    assert all(
        token in provenance
        for token in (
            '"platform_task_id"',
            '"requested_model"',
            '"candidate_commit"',
            '"candidate_tree"',
            '"sha256"',
            '"repository_only_proves_platform_execution"',
        )
    )
    assert all(
        token in evidence
        for token in ('"candidate_commit"', '"candidate_tree"', '"execution_binding"')
    )
    assert '"REREVIEW_OUTPUT_INTEGRATION_SUPERSEDED"' in provenance
    assert '"REREVIEW_EVIDENCE_COUPLING_ADVERSE"' in provenance
    assert '"REREVIEW_RECEIPT_ANCHOR_ADVERSE"' in provenance
    assert '"REREVIEW_GOVERNANCE_FACTS_SUPERSEDED"' in provenance
    assert '"REREVIEW_OUTPUT_MATERIALIZATION_ADVERSE"' in provenance
    assert '"REREVIEW_CLOSURE_PATH_SUPERSEDED"' in provenance
    assert '"REREVIEW_FINAL_REJECTED"' in provenance
    assert '"REREVIEW_AUTHORITY_DRIFT_ADVERSE"' in provenance
    assert '"REREVIEW_AUTHORITY_MATERIALIZATION_ADVERSE"' in provenance
    assert '"REREVIEW_GOVERNANCE_MATERIALIZATION_SUPERSEDED"' in provenance
    assert '"REREVIEW_SECRET_SCAN_MATERIALIZATION_SUPERSEDED"' in provenance
    assert '"minItems": 17' in provenance
    assert '"maxItems": 18' in provenance
    assert "execution-receipt17.json" in evidence


def test_t0606_adverse_rereview_and_candidate_receipt_are_preserved() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview-request.md"
    receipt = root / "execution-receipt.json"
    assert _sha256(request) == ADVERSE_REQUEST_SHA256
    assert _sha256(receipt) == ADVERSE_RECEIPT_SHA256
    paths = sorted((root / "rereview1").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(ADVERSE_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == ADVERSE_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["verdict"] == "FAIL"
        assert reply["target"]["request_sha256"] == ADVERSE_REQUEST_SHA256
        assert any(
            item["id"] == "RMD05-CLOSURE-001" and item["status"] == "OPEN"
            for item in reply["findings"]
        )


def test_t0606_superseded_pass_is_preserved_without_being_final_authority() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview2-request.md"
    receipt = root / "execution-receipt2.json"
    assert _sha256(request) == SUPERSEDED_REQUEST_SHA256
    assert _sha256(receipt) == SUPERSEDED_RECEIPT_SHA256
    paths = sorted((root / "final").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(SUPERSEDED_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == SUPERSEDED_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["verdict"] == "PASS"
        assert reply["target"]["request_sha256"] == SUPERSEDED_REQUEST_SHA256
        assert all(item["status"] == "PASS" for item in reply["dimensions"])
        assert any(
            item["id"] == "RMD05-CLOSURE-001" and item["status"] == "RESOLVED"
            for item in reply["findings"]
        )


def test_t0606_transition_adverse_reviews_are_preserved_as_nonfinal_history() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview3-request.md"
    receipt = root / "execution-receipt3.json"
    assert _sha256(request) == TRANSITION_REQUEST_SHA256
    assert _sha256(receipt) == TRANSITION_RECEIPT_SHA256
    paths = sorted((root / "rereview3").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(TRANSITION_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == TRANSITION_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["verdict"] == "FAIL"
        assert reply["target"]["request_sha256"] == TRANSITION_REQUEST_SHA256
        assert any(item["status"] == "OPEN" for item in reply["findings"])


def test_t0606_output_integration_pass_is_preserved_as_nonfinal_history() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview4-request.md"
    receipt = root / "execution-receipt4.json"
    assert _sha256(request) == INTEGRATION_REQUEST_SHA256
    assert _sha256(receipt) == INTEGRATION_RECEIPT_SHA256
    paths = sorted((root / "final2").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(INTEGRATION_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == INTEGRATION_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["verdict"] == "PASS"
        assert reply["target"]["request_sha256"] == INTEGRATION_REQUEST_SHA256
        assert all(item["status"] == "PASS" for item in reply["dimensions"])
        resolved = {item["id"] for item in reply["findings"] if item["status"] == "RESOLVED"}
        assert {"RMD05-CLOSURE-002", "RMD05-CLOSURE-003"}.issubset(resolved)


def test_t0606_evidence_coupling_reviews_are_preserved_as_mixed_nonfinal_history() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview5-request.md"
    receipt = root / "execution-receipt5.json"
    assert _sha256(request) == EVIDENCE_REQUEST_SHA256
    assert _sha256(receipt) == EVIDENCE_RECEIPT_SHA256
    paths = sorted((root / "rereview5").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(EVIDENCE_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == EVIDENCE_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["target"]["request_sha256"] == EVIDENCE_REQUEST_SHA256
        open_ids = {item["id"] for item in reply["findings"] if item["status"] == "OPEN"}
        if path.name.startswith("gpt-5.6-sol"):
            assert reply["verdict"] == "FAIL"
            assert open_ids == {"RMD05-CLOSURE-005"}
        else:
            assert reply["verdict"] == "PASS"
            assert open_ids == set()


def test_t0606_receipt_anchor_reviews_are_preserved_as_mixed_nonfinal_history() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview6-request.md"
    receipt = root / "execution-receipt6.json"
    assert _sha256(request) == ANCHOR_ADVERSE_REQUEST_SHA256
    assert _sha256(receipt) == ANCHOR_ADVERSE_RECEIPT_SHA256
    paths = sorted((root / "final3").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(ANCHOR_ADVERSE_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == ANCHOR_ADVERSE_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["target"]["request_sha256"] == ANCHOR_ADVERSE_REQUEST_SHA256
        open_ids = {item["id"] for item in reply["findings"] if item["status"] == "OPEN"}
        if path.name.startswith("gpt-5.6-sol"):
            assert reply["verdict"] == "PASS"
            assert open_ids == set()
        else:
            assert reply["verdict"] == "FAIL"
            assert open_ids == {"RMD05-CLOSURE-005"}


def test_t0606_governance_facts_pass_is_preserved_as_nonfinal_history() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview7-request.md"
    receipt = root / "execution-receipt7.json"
    assert _sha256(request) == GOVERNANCE_SUPERSEDED_REQUEST_SHA256
    assert _sha256(receipt) == GOVERNANCE_SUPERSEDED_RECEIPT_SHA256
    paths = sorted((root / "final4").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(GOVERNANCE_SUPERSEDED_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == GOVERNANCE_SUPERSEDED_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["verdict"] == "PASS"
        assert reply["target"]["request_sha256"] == GOVERNANCE_SUPERSEDED_REQUEST_SHA256
        assert all(item["status"] == "PASS" for item in reply["dimensions"])
        assert all(item["status"] == "RESOLVED" for item in reply["findings"])


def test_t0606_output_materialization_result_is_preserved_as_mixed_nonfinal_history() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview8-request.md"
    receipt = root / "execution-receipt8.json"
    assert _sha256(request) == MATERIALIZATION_ADVERSE_REQUEST_SHA256
    assert _sha256(receipt) == MATERIALIZATION_ADVERSE_RECEIPT_SHA256
    paths = sorted((root / "final5").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(MATERIALIZATION_ADVERSE_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == MATERIALIZATION_ADVERSE_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["target"]["request_sha256"] == MATERIALIZATION_ADVERSE_REQUEST_SHA256
        open_ids = {item["id"] for item in reply["findings"] if item["status"] == "OPEN"}
        if path.name.startswith("gpt-5.6-sol"):
            assert reply["verdict"] == "PASS"
            assert open_ids == set()
        else:
            assert reply["verdict"] == "FAIL"
            assert open_ids == {"RMD05-CLOSURE-006"}


def test_t0606_closure_path_pass_is_preserved_as_superseded_nonfinal_history() -> None:
    root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    request = root / "rereview9-request.md"
    receipt = root / "execution-receipt9.json"
    assert _sha256(request) == CLOSURE_PATH_SUPERSEDED_REQUEST_SHA256
    assert _sha256(receipt) == CLOSURE_PATH_SUPERSEDED_RECEIPT_SHA256
    paths = sorted((root / "final6").glob("*.reply.json"))
    assert [path.name for path in paths] == sorted(CLOSURE_PATH_SUPERSEDED_REPLY_SHA256)
    for path in paths:
        assert path.read_bytes().endswith(b"\n")
        assert _sha256(path) == CLOSURE_PATH_SUPERSEDED_REPLY_SHA256[path.name]
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["verdict"] == "PASS"
        assert reply["target"]["request_sha256"] == CLOSURE_PATH_SUPERSEDED_REQUEST_SHA256
        assert all(item["status"] == "PASS" for item in reply["dimensions"])
        assert all(item["status"] == "RESOLVED" for item in reply["findings"])


def test_t0606_model_assurance_workflow_closes_review_command_paths() -> None:
    workflow = (
        PROJECT_ROOT.parents[1] / ".github/workflows/moomooau-stage6-model-assurance.yml"
    ).read_text(encoding="utf-8")
    required = (
        "machine/stages/S6/model/**",
        "machine/stages/S6/reviews/**",
        "machine/stages/S6/schemas/**",
        "machine/stages/S6/tools/validate_stage6.py",
        "machine/contracts/delivery_status_model.json",
        "machine/tools/build_delivery_status.py",
        "machine/tools/build_governance_facts.py",
        "machine/tools/build_package_manifest.py",
        "machine/tools/capture_candidate_gates.py",
        "machine/tools/validate_assurance_reviews.py",
        "machine/tools/validate_delivery_status.py",
        "machine/tools/validate_package.py",
        "schemas/delivery-status-v1.schema.json",
        "src/moomooau_archive/model_boundary.py",
        "tests/remediation/**",
        "tests/tasks/test_t0605.py",
        "tests/tasks/test_t0606.py",
        "requirements/stage6.lock",
        "--require-hashes",
        "python machine/tools/validate_assurance_reviews.py",
    )
    assert all(token in workflow for token in required)

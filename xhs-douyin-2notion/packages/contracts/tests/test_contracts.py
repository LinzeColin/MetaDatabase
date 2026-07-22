from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from x2n_contracts import (
    ERROR_SPECS,
    ContractViolation,
    DuplicateDisposition,
    ErrorClass,
    ErrorCode,
    NativeHostPolicy,
    canonical_json_sha256,
    classify_duplicate_request,
    parse_native_message,
)
from x2n_contracts.generate import check_artifacts, generated_artifacts
from x2n_contracts.models import SCHEMA_MODELS

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = PROJECT_ROOT / "packages/contracts"
FIXTURE_ROOT = PROJECT_ROOT / "packages/test-fixtures/contracts/v1"
SUITE = json.loads((FIXTURE_ROOT / "fixture_manifest.json").read_text(encoding="utf-8"))
INVALID = json.loads((FIXTURE_ROOT / "invalid_cases.json").read_text(encoding="utf-8"))
POLICY = NativeHostPolicy.model_validate_json(
    (FIXTURE_ROOT / "valid/native_host_policy.json").read_text(encoding="utf-8")
)
ORIGIN = POLICY.allowed_origins[0]


def _set_path(payload: Any, path: list[Any], value: Any) -> None:
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _model_validate(contract: str, payload: Any) -> Any:
    return SCHEMA_MODELS[contract].model_validate_json(_json_text(payload))


class ContractRoundTripTests(unittest.TestCase):
    def test_every_registered_valid_fixture_round_trips(self) -> None:
        rows = SUITE["valid_cases"]
        self.assertEqual(len(rows), SUITE["valid_case_count"])
        for row in rows:
            with self.subTest(case=row["id"]):
                text = (FIXTURE_ROOT / row["path"]).read_text(encoding="utf-8")
                model_type = SCHEMA_MODELS[row["contract"]]
                first = model_type.model_validate_json(text)
                rendered = first.model_dump_json(by_alias=True)
                second = model_type.model_validate_json(rendered)
                self.assertEqual(
                    first.model_dump(mode="json", by_alias=True),
                    second.model_dump(mode="json", by_alias=True),
                )

    def test_generated_artifacts_are_current(self) -> None:
        self.assertEqual(check_artifacts(generated_artifacts()), [])

    def test_schema_objects_are_default_deny(self) -> None:
        object_nodes = 0

        def visit(value: Any) -> None:
            nonlocal object_nodes
            if isinstance(value, dict):
                if value.get("type") == "object":
                    object_nodes += 1
                    self.assertIs(value.get("additionalProperties"), False)
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        for path in sorted((CONTRACT_ROOT / "schemas/v1").glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema["x-x2n-contract-version"], "1.0")
            self.assertEqual(schema["x-x2n-compatibility"], "exact_match_fail_closed")
            visit(schema)
        self.assertGreater(object_nodes, 25)

    def test_no_persistent_dangerous_property_surface(self) -> None:
        properties: set[str] = set()

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                node_properties = value.get("properties")
                if isinstance(node_properties, dict):
                    properties.update(node_properties)
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        for path in (CONTRACT_ROOT / "schemas/v1").glob("*.schema.json"):
            visit(json.loads(path.read_text(encoding="utf-8")))
        forbidden = {
            "argv",
            "authorization",
            "command",
            "cookie",
            "cookies",
            "download_url",
            "executable",
            "file_path",
            "headers",
            "local_path",
            "media_url",
            "path",
            "proxy_url",
            "shell",
            "token",
        }
        self.assertEqual(properties & forbidden, set())
        self.assertIn("ephemeral_media_ref_ids", properties)


class InvalidAndSecurityContractTests(unittest.TestCase):
    def test_declared_invalid_cases_fail_closed(self) -> None:
        self.assertEqual(len(INVALID["cases"]), SUITE["invalid_case_count"])
        for case in INVALID["cases"]:
            with self.subTest(case=case["id"]):
                payload = json.loads((FIXTURE_ROOT / case["base"]).read_text(encoding="utf-8"))
                operation = case["operation"]
                if operation in {"set", "add", "set_and_rehash"}:
                    _set_path(payload, case["path"], copy.deepcopy(case["value"]))
                    if operation == "set_and_rehash":
                        payload["payload_hash"] = canonical_json_sha256(payload["payload"])
                elif operation == "remove_node_kind":
                    removed = {
                        item["node_id"] for item in payload["nodes"] if item["kind"] == case["value"]
                    }
                    payload["nodes"] = [item for item in payload["nodes"] if item["node_id"] not in removed]
                    payload["edges"] = [
                        item
                        for item in payload["edges"]
                        if item["from_node_id"] not in removed and item["to_node_id"] not in removed
                    ]
                elif operation == "dynamic_platform_media_url":
                    media_url = "https://" + "asset." + "xhscdn" + ".invalid/file"
                    _set_path(payload, case["path"], media_url)
                elif operation == "oversize":
                    payload["payload"]["page_context"]["title"] = "x" * (POLICY.max_message_bytes + 1)
                    payload["payload_hash"] = canonical_json_sha256(payload["payload"])
                elif operation == "invalid_origin":
                    pass
                elif operation in {"duplicate_same_hash", "duplicate_conflicting_hash"}:
                    request = parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
                    previous = (
                        request.payload_hash
                        if operation == "duplicate_same_hash"
                        else "0" * 64
                    )
                    disposition = classify_duplicate_request(previous, request)
                    self.assertEqual(disposition.value, case["expected"])
                    continue
                else:
                    self.fail(f"unknown invalid-fixture operation: {operation}")

                if case["contract"] == "native_message_request":
                    origin = "chrome-extension://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/" if operation == "invalid_origin" else ORIGIN
                    with self.assertRaises(ContractViolation) as caught:
                        parse_native_message(_json_text(payload), origin=origin, policy=POLICY)
                    self.assertEqual(caught.exception.code.value, case["expected"])
                else:
                    with self.assertRaises(ValidationError):
                        _model_validate(case["contract"], payload)

    def test_new_request_disposition_has_no_job_side_effect(self) -> None:
        payload = (FIXTURE_ROOT / "valid/native_capture.json").read_text(encoding="utf-8")
        request = parse_native_message(payload, origin=ORIGIN, policy=POLICY)
        self.assertIs(classify_duplicate_request(None, request), DuplicateDisposition.NEW_REQUEST)

    def test_unknown_native_field_and_version_are_distinct_stable_failures(self) -> None:
        payload = json.loads((FIXTURE_ROOT / "valid/native_capture.json").read_text(encoding="utf-8"))
        payload["schema_version"] = "9.9"
        with self.assertRaises(ContractViolation) as version:
            parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
        self.assertIs(version.exception.code, ErrorCode.INVALID_SCHEMA_VERSION)

        payload["schema_version"] = "1.0"
        payload["unknown"] = True
        with self.assertRaises(ContractViolation) as field:
            parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
        self.assertIs(field.exception.code, ErrorCode.UNKNOWN_FIELD)

    def test_native_contract_fuzz_matrix(self) -> None:
        baseline = json.loads((FIXTURE_ROOT / "valid/native_capture.json").read_text(encoding="utf-8"))
        executed = 0

        for index in range(32):
            origin = f"chrome-extension://{index:032x}/"
            with self.assertRaises(ContractViolation) as caught:
                parse_native_message(_json_text(baseline), origin=origin, policy=POLICY)
            self.assertIs(caught.exception.code, ErrorCode.NATIVE_ORIGIN_REJECTED)
            executed += 1

        for index in range(32):
            payload = copy.deepcopy(baseline)
            payload["action"] = f"unknown_action_{index:02d}"
            with self.assertRaises(ContractViolation) as caught:
                parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
            self.assertIs(caught.exception.code, ErrorCode.NATIVE_ACTION_UNKNOWN)
            executed += 1

        for index in range(16):
            payload = copy.deepcopy(baseline)
            payload[f"unexpected_{index:02d}"] = "synthetic"
            with self.assertRaises(ContractViolation) as caught:
                parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
            self.assertIs(caught.exception.code, ErrorCode.UNKNOWN_FIELD)
            executed += 1

        for index in range(16):
            payload = copy.deepcopy(baseline)
            payload["payload"][f"unexpected_{index:02d}"] = "synthetic"
            payload["payload_hash"] = canonical_json_sha256(payload["payload"])
            with self.assertRaises(ContractViolation) as caught:
                parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
            self.assertIs(caught.exception.code, ErrorCode.UNKNOWN_FIELD)
            executed += 1

        invalid_page_urls = (
            "http://www.xiaohongshu.com/explore/synthetic-note-001",
            "https://www.xiaohongshu.com/explore/synthetic-note-001?q=1",
            "https://www.xiaohongshu.com/explore/synthetic-note-001#fragment",
            "https://user@www.xiaohongshu.com/explore/synthetic-note-001",
            "https://www.xiaohongshu.com:443/explore/synthetic-note-001",
            "https://www.xiaohongshu.com/explore/../synthetic-note-001",
            "https://untrusted.invalid/explore/synthetic-note-001",
            "https://WWW.XIAOHONGSHU.COM/explore/synthetic-note-001",
        )
        for page_url in invalid_page_urls:
            payload = copy.deepcopy(baseline)
            payload["payload"]["page_url"] = page_url
            payload["payload_hash"] = canonical_json_sha256(payload["payload"])
            with self.assertRaises(ContractViolation) as caught:
                parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
            self.assertIs(caught.exception.code, ErrorCode.URL_REJECTED)
            executed += 1

        for extra in (1, 256):
            payload = copy.deepcopy(baseline)
            payload["payload"]["page_context"]["title"] = "x" * (POLICY.max_message_bytes + extra)
            payload["payload_hash"] = canonical_json_sha256(payload["payload"])
            with self.assertRaises(ContractViolation) as caught:
                parse_native_message(_json_text(payload), origin=ORIGIN, policy=POLICY)
            self.assertIs(caught.exception.code, ErrorCode.NATIVE_MESSAGE_TOO_LARGE)
            executed += 1

        self.assertEqual(executed, SUITE["generated_fuzz_case_count"])
        self.assertEqual(
            SUITE["case_count"],
            SUITE["valid_case_count"] + SUITE["invalid_case_count"] + executed,
        )


class RegistryAndParityTests(unittest.TestCase):
    def test_payload_hash_canonicalization_rejects_cross_language_ambiguity(self) -> None:
        with self.assertRaises(ValueError):
            canonical_json_sha256({"value": 0.5})
        with self.assertRaises(ValueError):
            canonical_json_sha256({"value": 9_007_199_254_740_992})

    def test_error_registry_is_total_and_class_complete(self) -> None:
        self.assertEqual(set(ERROR_SPECS), set(ErrorCode))
        self.assertEqual({item.error_class for item in ERROR_SPECS.values()}, set(ErrorClass))
        registry = json.loads((CONTRACT_ROOT / "registry/error_codes.v1.json").read_text(encoding="utf-8"))
        self.assertEqual([item["code"] for item in registry["errors"]], [item.value for item in ErrorCode])
        self.assertEqual(set(registry["classes"]), {item.value for item in ErrorClass})

    def test_typescript_contains_exact_shared_enums(self) -> None:
        typescript = (CONTRACT_ROOT / "types/contracts.ts").read_text(encoding="utf-8")
        for value in [*(item.value for item in ErrorCode), *(item.value for item in ErrorClass)]:
            self.assertIn(json.dumps(value), typescript)
        manifest = json.loads((CONTRACT_ROOT / "registry/contracts.v1.json").read_text(encoding="utf-8"))
        self.assertEqual({item["name"] for item in manifest["contracts"]}, set(SCHEMA_MODELS))
        self.assertTrue(all(item["typescript"] == "types/contracts.ts" for item in manifest["contracts"]))
        self.assertEqual(manifest["payload_hash"]["algorithm"], "sha256")
        self.assertEqual(
            manifest["payload_hash"]["typescript_helpers"],
            ["canonicalPayloadJson", "computePayloadHash"],
        )

    def test_contract_fixtures_are_public_safe(self) -> None:
        self.assertTrue(SUITE["synthetic_only"])
        for key in (
            "real_accounts",
            "contains_credentials",
            "contains_private_content",
            "contains_media_urls",
            "contains_local_absolute_paths",
        ):
            self.assertIs(SUITE[key], False)
        rendered = json.dumps(SUITE, ensure_ascii=False) + json.dumps(INVALID, ensure_ascii=False)
        self.assertNotIn("/" + "Users/", rendered)
        self.assertNotIn("github" + "_pat_", rendered)


if __name__ == "__main__":
    unittest.main()

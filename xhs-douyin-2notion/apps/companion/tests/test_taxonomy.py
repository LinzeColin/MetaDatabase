from __future__ import annotations

import hashlib
import json
import os
import pickle
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from uuid import UUID

from x2n_contracts import Artifact, CanonicalContent, ErrorCode, TaxonomyCategory, build_artifact_key, build_content_key
from x2n_contracts.models import ReviewStatus

from x2n_companion.canonical_store import CanonicalStore, WriteDisposition
from x2n_companion.runtime import DOWNLOAD_ENV, ROOT_ENV, RuntimePaths, X2NRuntimeError
from x2n_companion.runtime_cli import build_parser, run
from x2n_companion.taxonomy import (
    AutoClassificationGate,
    ClassificationEvaluator,
    ClassificationGoldCase,
    ClassificationRequest,
    ClassificationSource,
    ConstrainedClassifier,
    OwnerReviewService,
    TaxonomyRegistry,
    TaxonomySnapshot,
    load_private_classification_gold_dataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AI_CATEGORY_ID = UUID("11111111-1111-4111-8111-111111111111")
FINANCE_CATEGORY_ID = UUID("22222222-2222-4222-8222-222222222222")


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _category(
    category_id: UUID,
    *,
    name: str,
    slug: str,
    version: int = 1,
    enabled: bool = True,
    aliases: tuple[str, ...] = (),
    positive_examples: tuple[str, ...] = (),
    negative_examples: tuple[str, ...] = (),
) -> TaxonomyCategory:
    return TaxonomyCategory.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "category_id": str(category_id),
                "name": name,
                "slug": slug,
                "description": f"Owner managed {name} category.",
                "aliases": list(aliases),
                "positive_examples": list(positive_examples),
                "negative_examples": list(negative_examples),
                "priority": 10,
                "enabled": enabled,
                "version": version,
                "level": 1,
                "created_by": "owner",
            },
            ensure_ascii=False,
        )
    )


def _content(index: int) -> CanonicalContent:
    content_id = f"taxonomy-{index:05d}"
    return CanonicalContent.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "content_key": build_content_key("xiaohongshu", content_id),
                "platform": "xiaohongshu",
                "platform_content_id": content_id,
                "canonical_source_url": f"https://www.xiaohongshu.com/content/{content_id}",
                "content_type": "video",
                "title": f"Synthetic taxonomy content {index}",
                "description": "Synthetic content used only by the taxonomy contract test.",
                "author_name": "Synthetic owner",
                "author_platform_id": "synthetic-owner",
                "published_at": "2026-07-28T00:00:00Z",
                "content_hash": _sha(f"content:{index}"),
                "first_observed_at": "2026-07-28T00:00:00Z",
                "last_observed_at": "2026-07-28T00:00:00Z",
                "record_version": 1,
                "status": "active",
            },
            ensure_ascii=False,
        )
    )


def _artifact(content: CanonicalContent, index: int) -> Artifact:
    input_hash = _sha(f"artifact:{index}")
    return Artifact.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "artifact_id": f"art_taxonomy{index:05d}",
                "artifact_key": build_artifact_key(
                    content.content_key, "fusion_summary", input_hash, "taxonomy-test-1"
                ),
                "content_key": content.content_key,
                "artifact_type": "fusion_summary",
                "input_hash": input_hash,
                "processor": "taxonomy-test",
                "processor_version": "taxonomy-test-1",
                "model_provider": None,
                "model_name": None,
                "model_snapshot": None,
                "prompt_version": None,
                "language": "zh-CN",
                "quality": {"grade": "high", "metric_name": "confidence", "metric_value": 1.0},
                "private_payload_present": True,
                "private_payload_ref": f"prv_taxonomy{index:05d}",
                "private_payload_hash": _sha(f"payload:{index}"),
                "append_only": True,
                "artifact_sequence": 1,
                "created_at": "2026-07-28T00:00:00Z",
                "supersedes_artifact_id": None,
            },
            ensure_ascii=False,
        )
    )


class TaxonomyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-m005-test-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.destination.chmod(0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()
        self.registry = TaxonomyRegistry(self.store)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _seed_categories(self) -> TaxonomySnapshot:
        ai = _category(
            AI_CATEGORY_ID,
            name="Artificial Intelligence",
            slug="artificial-intelligence",
            aliases=("AI",),
            positive_examples=("machine learning",),
            negative_examples=("quarterly earnings",),
        )
        finance = _category(
            FINANCE_CATEGORY_ID,
            name="Finance",
            slug="finance",
            aliases=("Fintech",),
            positive_examples=("quarterly earnings",),
            negative_examples=("machine learning",),
        )
        self.assertEqual(self.registry.create(ai), WriteDisposition.INSERTED)
        self.assertEqual(self.registry.create(finance), WriteDisposition.INSERTED)
        return self.registry.snapshot()

    @staticmethod
    def _request(content_key: str = "xiaohongshu:taxonomy-test") -> ClassificationRequest:
        return ClassificationRequest(
            content_key=content_key,
            sources=(ClassificationSource("art_taxonomy00099", "AI machine learning tutorial"),),
        )

    def _private_cases(self) -> list[ClassificationGoldCase]:
        cases: list[ClassificationGoldCase] = []
        for index in range(50):
            cases.append(
                ClassificationGoldCase(
                    case_id=f"ai-{index:03d}",
                    content_key=f"xiaohongshu:gold-ai-{index:03d}",
                    evidence_artifact_id=f"art_goldai{index:05d}",
                    input_text="AI machine learning systems and model safety",
                    expected_category_id=AI_CATEGORY_ID,
                    synthetic=False,
                )
            )
            cases.append(
                ClassificationGoldCase(
                    case_id=f"finance-{index:03d}",
                    content_key=f"xiaohongshu:gold-finance-{index:03d}",
                    evidence_artifact_id=f"art_goldfi{index:05d}",
                    input_text="Finance quarterly earnings and fintech analysis",
                    expected_category_id=FINANCE_CATEGORY_ID,
                    synthetic=False,
                )
            )
        return cases

    def test_owner_registry_records_stable_rename_disable_merge_and_append_only_revisions(self) -> None:
        self._seed_categories()
        renamed = _category(
            AI_CATEGORY_ID,
            name="Applied Artificial Intelligence",
            slug="applied-artificial-intelligence",
            aliases=("AI",),
            positive_examples=("machine learning",),
            negative_examples=("quarterly earnings",),
            version=2,
        )
        self.assertEqual(self.registry.update(renamed), WriteDisposition.UPDATED)
        disabled = _category(
            FINANCE_CATEGORY_ID,
            name="Finance",
            slug="finance",
            aliases=("Fintech",),
            positive_examples=("quarterly earnings",),
            negative_examples=("machine learning",),
            version=2,
            enabled=False,
        )
        self.assertEqual(self.registry.disable(disabled), WriteDisposition.UPDATED)
        merged = disabled.model_copy(update={"version": 3})
        self.assertEqual(self.registry.merge(merged, target_category_id=AI_CATEGORY_ID), WriteDisposition.UPDATED)
        revisions = self.store.taxonomy_revisions()
        self.assertEqual([item.operation for item in revisions], ["create", "update", "create", "disable", "merge"])
        self.assertEqual(revisions[-1].merge_target_category_id, AI_CATEGORY_ID)
        self.assertEqual(self.registry.snapshot().category(AI_CATEGORY_ID).category_id, AI_CATEGORY_ID)  # type: ignore[union-attr]
        connection = sqlite3.connect(self.paths.database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE taxonomy_revision SET actor = 'ai'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM taxonomy_category WHERE category_id = ?", (str(FINANCE_CATEGORY_ID),))
        finally:
            connection.close()

    def test_registry_rejects_reserved_or_ambiguous_owner_terms(self) -> None:
        self._seed_categories()
        reserved = _category(
            UUID("33333333-3333-4333-8333-333333333333"),
            name="Unclassified",
            slug="unclassified",
        )
        with self.assertRaises(X2NRuntimeError) as reserved_error:
            self.registry.create(reserved)
        self.assertEqual(reserved_error.exception.code, ErrorCode.POLICY_BLOCKED)
        ambiguous = _category(
            UUID("33333333-3333-4333-8333-333333333333"),
            name="AI",
            slug="ai-reference",
        )
        with self.assertRaises(X2NRuntimeError) as ambiguous_error:
            self.registry.create(ambiguous)
        self.assertEqual(ambiguous_error.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_classifier_has_no_registry_mutator_and_defaults_to_suggestion_only(self) -> None:
        snapshot = self._seed_categories()
        classifier = ConstrainedClassifier()
        self.assertFalse(hasattr(classifier, "store"))
        self.assertFalse(hasattr(classifier, "create"))
        with classifier.session() as session:
            first = session.suggest(self._request(), snapshot)
            second = session.suggest(self._request(), snapshot)
            self.assertEqual(first.disposition, "suggested")
            self.assertEqual(first.primary_category_id, AI_CATEGORY_ID)
            self.assertEqual(first.suggestion_id, second.suggestion_id)
            self.assertEqual(session.safe_ledger()["cache_misses"], 1)
            self.assertEqual(session.safe_ledger()["cache_hits"], 1)
            self.assertEqual(session.safe_ledger()["model_calls"], 0)
        with self.assertRaises(TypeError):
            pickle.dumps(self._request())

    def test_disabled_or_unknown_categories_cannot_be_suggested_or_persisted(self) -> None:
        snapshot = self._seed_categories()
        disabled = _category(
            FINANCE_CATEGORY_ID,
            name="Finance",
            slug="finance",
            aliases=("Fintech",),
            positive_examples=("quarterly earnings",),
            negative_examples=("machine learning",),
            version=2,
            enabled=False,
        )
        self.registry.disable(disabled)
        snapshot = self.registry.snapshot()
        with ConstrainedClassifier().session() as session:
            finance = session.suggest(
                ClassificationRequest(
                    "xiaohongshu:finance-test", (ClassificationSource("art_taxonomy00098", "quarterly earnings"),)
                ),
                snapshot,
            )
        self.assertEqual(finance.disposition, "unclassified")
        content = _content(1)
        artifact = _artifact(content, 1)
        self.store.ingest_bundle(content, artifacts=(artifact,))
        with ConstrainedClassifier().session() as session:
            ai = session.suggest(
                ClassificationRequest(
                    content.content_key, (ClassificationSource(artifact.artifact_id, "machine learning"),)
                ),
                snapshot,
            )
        disabled_classification = ai.to_classification(
            created_at="2026-07-28T00:00:00Z",
            review_status=ReviewStatus.OWNER_CONFIRMED,
            primary_category_id=FINANCE_CATEGORY_ID,
        )
        with self.assertRaises(X2NRuntimeError) as disabled_error:
            self.store.append_classification(disabled_classification)
        self.assertEqual(disabled_error.exception.code, ErrorCode.POLICY_BLOCKED)
        unknown_classification = ai.to_classification(
            created_at="2026-07-28T00:00:01Z",
            review_status=ReviewStatus.OWNER_CONFIRMED,
            primary_category_id=UUID("33333333-3333-4333-8333-333333333333"),
        )
        with self.assertRaises(X2NRuntimeError) as unknown_error:
            self.store.append_classification(unknown_classification)
        self.assertEqual(unknown_error.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_private_gold_gate_enables_only_matching_calibrated_snapshot(self) -> None:
        snapshot = self._seed_categories()
        cases = self._private_cases()
        dataset_sha = _sha("private-gold-receipt")
        report = ClassificationEvaluator().evaluate(
            cases,
            snapshot,
            private_gold=True,
            dataset_sha256=dataset_sha,
        )
        self.assertEqual(report.status, "pass")
        self.assertEqual(report.evaluated_cases, 100)
        self.assertGreaterEqual(report.high_confidence_precision or 0.0, 0.90)
        self.assertGreaterEqual(report.macro_f1, 0.80)
        gate = AutoClassificationGate.from_evaluation(report)
        self.assertTrue(gate.enabled)
        with ConstrainedClassifier().session() as session:
            automatic = session.suggest(self._request(), snapshot, calibration=report.calibration, gate=gate)
        self.assertEqual(automatic.disposition, "auto_accepted")
        changed_snapshot = TaxonomySnapshot.from_categories(
            (
                _category(
                    AI_CATEGORY_ID,
                    name="Artificial Intelligence",
                    slug="artificial-intelligence",
                    aliases=("AI",),
                    positive_examples=("machine learning",),
                    negative_examples=("quarterly earnings",),
                    version=2,
                ),
                _category(
                    FINANCE_CATEGORY_ID,
                    name="Finance",
                    slug="finance",
                    aliases=("Fintech",),
                    positive_examples=("quarterly earnings",),
                    negative_examples=("machine learning",),
                ),
            )
        )
        with ConstrainedClassifier().session() as session:
            stale = session.suggest(self._request(), changed_snapshot, gate=gate)
        self.assertEqual(stale.disposition, "suggested")

    def test_low_quality_or_synthetic_evaluation_never_enables_auto_classification(self) -> None:
        snapshot = self._seed_categories()
        synthetic = [
            ClassificationGoldCase(
                case_id=f"smoke-{index:03d}",
                content_key=f"xiaohongshu:smoke-{index:03d}",
                evidence_artifact_id=f"art_smoke{index:05d}",
                input_text="unrelated content",
                expected_category_id=AI_CATEGORY_ID,
                synthetic=True,
            )
            for index in range(40)
        ]
        report = ClassificationEvaluator().evaluate(
            synthetic,
            snapshot,
            private_gold=False,
            dataset_sha256=_sha("synthetic-gold"),
        )
        self.assertEqual(report.status, "not_run")
        self.assertFalse(AutoClassificationGate.from_evaluation(report).enabled)

    def test_owner_review_confirmation_and_correction_are_append_only(self) -> None:
        snapshot = self._seed_categories()
        content = _content(2)
        artifact = _artifact(content, 2)
        self.store.ingest_bundle(content, artifacts=(artifact,))
        with ConstrainedClassifier().session() as session:
            suggestion = session.suggest(
                ClassificationRequest(
                    content.content_key, (ClassificationSource(artifact.artifact_id, "machine learning"),)
                ),
                snapshot,
            )
        review = OwnerReviewService(self.store)
        self.assertEqual(
            review.confirm(suggestion, snapshot, created_at="2026-07-28T00:00:00Z", tags=("synthetic",)),
            WriteDisposition.INSERTED,
        )
        initial = suggestion.to_classification(
            created_at="2026-07-28T00:00:00Z",
            review_status=ReviewStatus.OWNER_CONFIRMED,
            tags=("synthetic",),
        )
        self.assertEqual(
            review.correct(
                suggestion,
                snapshot,
                primary_category_id=FINANCE_CATEGORY_ID,
                supersedes_classification_id=initial.classification_id,
                created_at="2026-07-28T00:01:00Z",
                tags=("owner-corrected",),
            ),
            WriteDisposition.INSERTED,
        )
        connection = sqlite3.connect(self.paths.database)
        try:
            rows = connection.execute(
                "SELECT review_status, supersedes_classification_id FROM classification ORDER BY created_at"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "owner_confirmed")
        self.assertEqual(rows[1], ("owner_corrected", initial.classification_id))
        other_content = _content(3)
        other_artifact = _artifact(other_content, 3)
        self.store.ingest_bundle(other_content, artifacts=(other_artifact,))
        with ConstrainedClassifier().session() as session:
            other_suggestion = session.suggest(
                ClassificationRequest(
                    other_content.content_key,
                    (ClassificationSource(other_artifact.artifact_id, "machine learning"),),
                ),
                snapshot,
            )
        with self.assertRaises(X2NRuntimeError) as cross_content_error:
            review.correct(
                other_suggestion,
                snapshot,
                primary_category_id=AI_CATEGORY_ID,
                supersedes_classification_id=initial.classification_id,
                created_at="2026-07-28T00:02:00Z",
            )
        self.assertEqual(cross_content_error.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_private_gold_loader_and_cli_emit_only_aggregate_receipt(self) -> None:
        snapshot = self._seed_categories()
        classifier = ConstrainedClassifier()
        cases = self._private_cases()
        dataset_id = "owner-classification-gold"
        directory = self.paths.data_root / "runtime/diagnostics/classification-gold"
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        payload = {
            "schema_version": "x2n-classification-gold-v1",
            "dataset_id": dataset_id,
            "taxonomy_snapshot_sha256": snapshot.snapshot_sha256,
            "classifier_fingerprint": classifier.descriptor.fingerprint,
            "cases": [
                {
                    "case_id": case.case_id,
                    "content_key": case.content_key,
                    "evidence_artifact_id": case.evidence_artifact_id,
                    "expected_category_id": str(case.expected_category_id),
                    "input_text": case.input_text,
                }
                for case in cases
            ],
        }
        target = directory / f"{dataset_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        target.chmod(0o600)
        loaded = load_private_classification_gold_dataset(self.paths, dataset_id)
        self.assertEqual(loaded.safe_dict()["case_count"], 100)
        parser = build_parser()
        with mock.patch.dict(
            os.environ,
            {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.destination)},
            clear=False,
        ):
            receipt = run(parser.parse_args(["eval", "classify", "--dataset", dataset_id]))
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["auto_classify"], "ENABLED")
        self.assertNotIn(str(self.paths.data_root), rendered)
        self.assertNotIn("machine learning systems", rendered)


if __name__ == "__main__":
    unittest.main()

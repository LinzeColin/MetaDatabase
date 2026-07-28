from __future__ import annotations

import hashlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from uuid import UUID

from x2n_contracts import Artifact, CanonicalContent, TaxonomyCategory, build_artifact_key, build_content_key

from x2n_companion.canonical_store import CanonicalStore, WriteDisposition
from x2n_companion.runtime import RuntimePaths
from x2n_companion.runtime_cli import build_parser, run
from x2n_companion.taxonomy import TaxonomyRegistry
from x2n_companion.webui import LOOPBACK_HOST, LocalWebUI, create_local_webui_server


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CATEGORY_ID = UUID("11111111-1111-4111-8111-111111111111")
SYNTHETIC_TITLE = "<script>not executable</script>"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _category() -> TaxonomyCategory:
    return TaxonomyCategory(
        schema_version="1.0",
        category_id=CATEGORY_ID,
        name="Owner Review",
        slug="owner-review",
        description="Synthetic Owner category for Local WebUI tests.",
        aliases=(),
        positive_examples=(),
        negative_examples=(),
        priority=10,
        enabled=True,
        version=1,
        level=1,
        created_by="owner",
    )


def _content() -> CanonicalContent:
    content_id = "webui-review-00001"
    return CanonicalContent.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "content_key": build_content_key("xiaohongshu", content_id),
                "platform": "xiaohongshu",
                "platform_content_id": content_id,
                "canonical_source_url": f"https://www.xiaohongshu.com/content/{content_id}",
                "content_type": "video",
                "title": SYNTHETIC_TITLE,
                "description": "Synthetic Local WebUI review content.",
                "author_name": "Synthetic Owner",
                "author_platform_id": "synthetic-owner",
                "published_at": "2026-07-29T00:00:00Z",
                "content_hash": _sha("webui-content"),
                "first_observed_at": "2026-07-29T00:00:00Z",
                "last_observed_at": "2026-07-29T00:00:00Z",
                "record_version": 1,
                "status": "active",
            },
            ensure_ascii=False,
        )
    )


def _artifact(content: CanonicalContent) -> Artifact:
    input_hash = _sha("webui-artifact")
    return Artifact.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "artifact_id": "art_webui0000000001",
                "artifact_key": build_artifact_key(content.content_key, "fusion_summary", input_hash, "webui-test-1"),
                "content_key": content.content_key,
                "artifact_type": "fusion_summary",
                "input_hash": input_hash,
                "processor": "webui-test",
                "processor_version": "webui-test-1",
                "model_provider": None,
                "model_name": None,
                "model_snapshot": None,
                "prompt_version": None,
                "language": "zh-CN",
                "quality": {"grade": "high", "metric_name": "confidence", "metric_value": 1.0},
                "private_payload_present": True,
                "private_payload_ref": "prv_webui0000000001",
                "private_payload_hash": _sha("webui-private-payload"),
                "append_only": True,
                "artifact_sequence": 1,
                "created_at": "2026-07-29T00:00:00Z",
                "supersedes_artifact_id": None,
            },
            ensure_ascii=False,
        )
    )


class LocalWebUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-webui-test-")
        destination = Path(self.temporary.name) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        destination.chmod(0o700)
        self.paths = RuntimePaths.from_values(
            str(destination / "xhs-douyin-2notion"),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()
        self.registry = TaxonomyRegistry(self.store)
        self.assertEqual(self.registry.create(_category()), WriteDisposition.INSERTED)
        self.content = _content()
        self.store.ingest_bundle(self.content, artifacts=(_artifact(self.content),))
        self.store.submit_skeleton_job(
            request_id="webui_request_0001",
            payload_hash=_sha("webui-job"),
            run_kind="native_capture_skeleton",
        )
        self.app = LocalWebUI(self.store)
        self.server = create_local_webui_server(self.app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = int(self.server.server_address[1])

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.temporary.cleanup()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {"Host": f"{LOOPBACK_HOST}:{self.port}"}
        if headers:
            request_headers.update(headers)
        connection = http.client.HTTPConnection(LOOPBACK_HOST, self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            response_headers = {name.lower(): value for name, value in response.getheaders()}
        finally:
            connection.close()
        if response_headers.get("content-type", "").startswith("application/json"):
            return response.status, response_headers, json.loads(raw.decode("utf-8"))
        return response.status, response_headers, raw.decode("utf-8")

    def _mutation_headers(self, *, token: str | None = None, origin: str | None = None) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Origin": origin or f"http://{LOOPBACK_HOST}:{self.port}",
            "X-X2N-CSRF": token or self.app.csrf_token,
            "X-X2N-WebUI": "1",
        }

    def test_loopback_ui_e2e_and_redacted_diagnostics(self) -> None:
        status, headers, page = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("<main>", page)
        self.assertIn("aria-label", page)
        self.assertNotIn(SYNTHETIC_TITLE, page)
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertNotIn("access-control-allow-origin", headers)

        dashboard_status, _, dashboard = self._request("GET", "/api/v2/dashboard")
        self.assertEqual(dashboard_status, 200)
        self.assertEqual(dashboard["dashboard"]["review_queue_count"], 1)
        source_status, _, sources = self._request("GET", "/api/v2/sources")
        self.assertEqual(source_status, 200)
        self.assertEqual(len(sources["sources"]), 6)
        taxonomy_status, _, taxonomy = self._request("GET", "/api/v2/taxonomy")
        self.assertEqual(taxonomy_status, 200)
        self.assertEqual(taxonomy["ai_mutations"], 0)
        review_status, _, review = self._request("GET", "/api/v2/review")
        self.assertEqual(review_status, 200)
        self.assertEqual(len(review["items"]), 1)
        jobs_status, _, jobs = self._request("GET", "/api/v2/jobs")
        self.assertEqual(jobs_status, 200)
        self.assertEqual(len(jobs["jobs"]), 1)
        detail_status, _, detail = self._request("GET", f"/api/v2/jobs/{jobs['jobs'][0]['job_id']}")
        self.assertEqual(detail_status, 200)
        self.assertEqual(detail["state"], "pending")
        self.assertEqual(self._request("GET", "/api/v2/sinks")[0], 200)
        self.assertEqual(self._request("GET", "/api/v2/models")[0], 200)
        diagnostic_status, _, diagnostics = self._request("GET", "/api/v2/diagnostics/export")
        self.assertEqual(diagnostic_status, 200)
        rendered = json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(str(self.paths.data_root), rendered)
        self.assertNotIn(SYNTHETIC_TITLE, rendered)
        self.assertNotIn("https://", rendered)

    def test_csrf_origin_and_low_confidence_owner_review(self) -> None:
        _, _, review = self._request("GET", "/api/v2/review")
        item = review["items"][0]
        payload = {"category_id": str(CATEGORY_ID), "review_token": item["review_token"]}
        missing_origin, _, _ = self._request(
            "POST",
            f"/api/v2/review/{self.content.content_key}",
            payload=payload,
            headers={"Content-Type": "application/json", "X-X2N-CSRF": self.app.csrf_token},
        )
        self.assertEqual(missing_origin, 403)
        foreign_origin, _, _ = self._request(
            "POST",
            f"/api/v2/review/{self.content.content_key}",
            payload=payload,
            headers=self._mutation_headers(origin="http://localhost:1"),
        )
        self.assertEqual(foreign_origin, 403)
        bad_csrf, _, _ = self._request(
            "POST",
            f"/api/v2/review/{self.content.content_key}",
            payload=payload,
            headers=self._mutation_headers(token="invalid"),
        )
        self.assertEqual(bad_csrf, 403)
        confirmed, _, receipt = self._request(
            "POST",
            f"/api/v2/review/{self.content.content_key}",
            payload=payload,
            headers=self._mutation_headers(),
        )
        self.assertEqual(confirmed, 200)
        self.assertEqual(receipt["review_status"], "owner_confirmed")
        replay, _, _ = self._request(
            "POST",
            f"/api/v2/review/{self.content.content_key}",
            payload=payload,
            headers=self._mutation_headers(),
        )
        self.assertEqual(replay, 409)
        _, _, queue = self._request("GET", "/api/v2/review")
        self.assertEqual(queue["items"], [])

    def test_owner_taxonomy_create_never_executes_html_and_cli_uses_mvp_name(self) -> None:
        created, _, result = self._request(
            "POST",
            "/api/v2/taxonomy",
            payload={
                "action": "create",
                "description": "Owner supplied category description.",
                "name": "<img src=x onerror=alert(1)>",
                "slug": "owner-html-safe",
            },
            headers=self._mutation_headers(),
        )
        self.assertEqual(created, 200)
        self.assertEqual(result["action"], "create")
        page_status, _, page = self._request("GET", "/")
        self.assertEqual(page_status, 200)
        self.assertNotIn("<img src=x", page)

        parser = build_parser()
        args = parser.parse_args(["reconcile", "owner-mvp-plan", "--items", "80"])
        receipt = run(args)
        self.assertEqual(receipt["plan"]["status"], "TOOLING_READY_OWNER_MVP_NOT_RUN")
        legacy = "owner-" + "alpha-plan"
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["reconcile", legacy, "--items", "80"])


if __name__ == "__main__":
    unittest.main()

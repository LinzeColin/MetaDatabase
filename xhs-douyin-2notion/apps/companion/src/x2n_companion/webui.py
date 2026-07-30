"""Loopback-only Local WebUI for owner-controlled knowledge review.

The UI is intentionally a local companion surface, not a network service: it
binds only IPv4 loopback, emits no CORS headers, performs no outbound requests,
and sends only allowlisted operational metadata to the browser.  Canonical text,
credentials, media, CDN references, private paths, and raw diagnostics stay out
of every endpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import secrets
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

from x2n_contracts import Classification, TaxonomyCategory
from x2n_contracts.models import ClassificationCandidate, DecisionMode, ReviewStatus

from .canonical_store import CanonicalStore, WriteDisposition
from .lifecycle import LifecycleService
from .operations import OperationsService
from .runtime import X2NRuntimeError
from .taxonomy import TaxonomyRegistry, TaxonomySnapshot


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 32 * 1024
LOCAL_UI_SCHEMA_VERSION = "2.0"
TASK_ID = "TSK.x2n.uxops.003"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; base-uri 'none'; connect-src 'self'; form-action 'self'; "
    "frame-ancestors 'none'; img-src 'none'; media-src 'none'; object-src 'none'; "
    "script-src 'self'; style-src 'self'"
)


class WebUIError(RuntimeError):
    """A safe Local WebUI error that is suitable for the local owner."""

    def __init__(self, status: int, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.status = status
        self.code = code
        self.safe_message = safe_message


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WebUIError(400, "invalid_input", f"{label} must be a JSON object")
    return value


def _string(value: object, *, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise WebUIError(400, "invalid_input", f"{label} is invalid")
    return value


def _integer(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise WebUIError(400, "invalid_input", f"{label} is invalid")
    return value


def _string_list(value: object, *, label: str, maximum_items: int, maximum_item_length: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > maximum_items:
        raise WebUIError(400, "invalid_input", f"{label} is invalid")
    return tuple(_string(item, label=label, maximum=maximum_item_length) for item in value)


def _uuid(value: object, *, label: str) -> UUID:
    if not isinstance(value, str):
        raise WebUIError(400, "invalid_input", f"{label} is invalid")
    try:
        return UUID(value)
    except ValueError as error:
        raise WebUIError(400, "invalid_input", f"{label} is invalid") from error


@dataclass(frozen=True)
class LocalReviewItem:
    artifact_ids: tuple[str, ...]
    classification_id: str | None
    confidence_raw: float | None
    content_key: str
    current_category_id: str | None
    decision_mode: str | None
    platform: str
    review_status: str | None
    taxonomy_version: int | None

    @classmethod
    def from_store(cls, value: Mapping[str, Any]) -> "LocalReviewItem":
        artifact_ids = value.get("artifact_ids")
        if (
            not isinstance(artifact_ids, list)
            or not artifact_ids
            or not all(isinstance(item, str) for item in artifact_ids)
        ):
            raise WebUIError(409, "review_evidence_missing", "Review requires immutable Artifact evidence")
        content_key = value.get("content_key")
        platform = value.get("platform")
        if not isinstance(content_key, str) or not isinstance(platform, str):
            raise WebUIError(409, "review_state_invalid", "Review state is invalid")
        classification_id = value.get("classification_id")
        current_category_id = value.get("current_category_id")
        decision_mode = value.get("decision_mode")
        review_status = value.get("review_status")
        confidence = value.get("confidence_raw")
        taxonomy_version = value.get("taxonomy_version")
        if classification_id is not None and not isinstance(classification_id, str):
            raise WebUIError(409, "review_state_invalid", "Review state is invalid")
        if current_category_id is not None and not isinstance(current_category_id, str):
            raise WebUIError(409, "review_state_invalid", "Review state is invalid")
        if decision_mode is not None and not isinstance(decision_mode, str):
            raise WebUIError(409, "review_state_invalid", "Review state is invalid")
        if review_status is not None and not isinstance(review_status, str):
            raise WebUIError(409, "review_state_invalid", "Review state is invalid")
        if confidence is not None and not isinstance(confidence, (int, float)):
            raise WebUIError(409, "review_state_invalid", "Review state is invalid")
        if taxonomy_version is not None and not isinstance(taxonomy_version, int):
            raise WebUIError(409, "review_state_invalid", "Review state is invalid")
        return cls(
            artifact_ids=tuple(artifact_ids),
            classification_id=classification_id,
            confidence_raw=None if confidence is None else float(confidence),
            content_key=content_key,
            current_category_id=current_category_id,
            decision_mode=decision_mode,
            platform=platform,
            review_status=review_status,
            taxonomy_version=taxonomy_version,
        )

    def token(self, snapshot: TaxonomySnapshot) -> str:
        return _canonical_sha256(
            {
                "artifact_ids": self.artifact_ids,
                "classification_id": self.classification_id,
                "content_key": self.content_key,
                "current_category_id": self.current_category_id,
                "taxonomy_snapshot_sha256": snapshot.snapshot_sha256,
            }
        )

    def safe_dict(self, snapshot: TaxonomySnapshot) -> dict[str, Any]:
        return {
            "confidence_raw": self.confidence_raw,
            "content_key": self.content_key,
            "current_category_id": self.current_category_id,
            "decision_mode": self.decision_mode,
            "evidence_artifact_count": len(self.artifact_ids),
            "platform": self.platform,
            "review_status": self.review_status,
            "review_token": self.token(snapshot),
            "taxonomy_snapshot_sha256": snapshot.snapshot_sha256,
        }


class LocalWebUI:
    """Owner-facing local UI facade over the Canonical Store's safe projections."""

    def __init__(self, store: CanonicalStore) -> None:
        self._store = store
        self._lifecycle = LifecycleService(store)
        self._operations = OperationsService(store)
        self._taxonomy = TaxonomyRegistry(store)
        self._csrf_token = secrets.token_urlsafe(32)

    @property
    def csrf_token(self) -> str:
        """Ephemeral, in-memory CSRF token; never persisted or exported."""

        return self._csrf_token

    def _snapshot(self) -> TaxonomySnapshot:
        return self._taxonomy.snapshot()

    @staticmethod
    def _taxonomy_category(category: TaxonomyCategory) -> dict[str, Any]:
        return {
            "aliases": list(category.aliases),
            "category_id": str(category.category_id),
            "description": category.description,
            "enabled": category.enabled,
            "name": category.name,
            "priority": category.priority,
            "slug": category.slug,
            "version": category.version,
        }

    def dashboard(self) -> dict[str, Any]:
        snapshot = self._store.local_ui_snapshot()
        return {
            "dashboard": {
                "canonical_counts": snapshot["counts"],
                "health": snapshot["health"],
                "job_count": len(snapshot["jobs"]),
                "outbox_count": len(snapshot["outbox"]),
                "review_queue_count": len(snapshot["review_queue"]),
            },
            "interface": "loopback_owner_local_only",
            "schema_version": LOCAL_UI_SCHEMA_VERSION,
            "task_id": TASK_ID,
        }

    def sources(self) -> dict[str, Any]:
        snapshot = self._store.local_ui_snapshot()
        by_platform: dict[str, int] = Counter()
        for item in snapshot["capabilities"]:
            scope_id = item["scope_id"]
            platform = scope_id.split("_", 1)[0]
            if platform == "xiaohongshu":
                by_platform[platform] += 1
            elif platform in {"douyin", "bilibili", "kuaishou", "weibo", "taobao"}:
                by_platform[platform] += 1
        platforms = ("xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao")
        return {
            "extension_surface": "chrome_side_panel",
            "sources": [
                {
                    "capability_records": by_platform.get(platform, 0),
                    "live_enabled": False,
                    "platform": platform,
                    "state": "disabled_until_explicit_owner_activation",
                }
                for platform in platforms
            ],
        }

    def taxonomy(self) -> dict[str, Any]:
        snapshot = self._snapshot()
        return {
            "ai_mutations": 0,
            "categories": [self._taxonomy_category(item) for item in snapshot.categories],
            "owner_only": True,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "version": snapshot.version,
        }

    def review_queue(self) -> dict[str, Any]:
        taxonomy_snapshot = self._snapshot()
        records = self._store.local_ui_snapshot()["review_queue"]
        items: list[dict[str, Any]] = []
        blocked_without_evidence = 0
        for record in records:
            try:
                items.append(LocalReviewItem.from_store(record).safe_dict(taxonomy_snapshot))
            except WebUIError as error:
                if error.code != "review_evidence_missing":
                    raise
                blocked_without_evidence += 1
        return {
            "auto_classify": "disabled_suggestion_only",
            "blocked_without_evidence": blocked_without_evidence,
            "items": items,
            "owner_action_required": True,
            "taxonomy_snapshot_sha256": taxonomy_snapshot.snapshot_sha256,
        }

    def job_detail(self, job_id: str) -> dict[str, Any] | None:
        return self._store.local_ui_job(job_id)

    def sinks(self) -> dict[str, Any]:
        outbox = self._store.local_ui_snapshot()["outbox"]
        states = Counter(item["status"] for item in outbox)
        sinks = Counter(item["sink"] for item in outbox)
        return {
            "notion": {"real_transport": "NOT_RUN", "outbox_events": sinks.get("notion", 0)},
            "outbox_states": dict(sorted(states.items())),
            "markdown": {"outbox_events": sinks.get("markdown", 0), "renderer": "1.1.0"},
        }

    @staticmethod
    def models() -> dict[str, Any]:
        return {
            "asr": "disabled_pending_private_gold",
            "auto_classify": "disabled_suggestion_only_pending_private_gold",
            "budget": {"cloud_uploads": 0, "model_calls": 0, "network_calls": 0},
            "fusion": "disabled_pending_explicit_activation",
            "ocr_vision": "disabled_pending_private_gold",
        }

    def diagnostics(self) -> dict[str, Any]:
        return self._operations.diagnostic_bundle()

    def lifecycle(self) -> dict[str, Any]:
        """Safe read-only lifecycle state; every mutation remains CLI-gated."""

        return {
            "controls": {
                "delete": "CLI_EXPLICIT_CONFIRMATION_REQUIRED",
                "private_export": "CLI_EXPLICIT_CONFIRMATION_REQUIRED",
                "restore": "CLI_EXPLICIT_CONFIRMATION_REQUIRED",
                "runtime_wipe": "CLI_TWO_STEP_EXPLICIT_CONFIRMATION_REQUIRED",
                "time_machine": "CLI_OWNER_CONFIRMATION_REQUIRED",
            },
            "lifecycle": self._lifecycle.status(),
            "task_id": "TSK.x2n.uxops.005",
        }

    def _category_from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        category_id: UUID,
        version: int,
        existing: TaxonomyCategory | None,
        enabled: bool,
    ) -> TaxonomyCategory:
        aliases = _string_list(
            payload.get("aliases", list(existing.aliases) if existing is not None else []),
            label="aliases",
            maximum_items=20,
            maximum_item_length=100,
        )
        try:
            return TaxonomyCategory(
                schema_version="1.0",
                category_id=category_id,
                name=_string(
                    payload.get("name", existing.name if existing is not None else None), label="name", maximum=100
                ),
                slug=_string(
                    payload.get("slug", existing.slug if existing is not None else None), label="slug", maximum=63
                ),
                description=_string(
                    payload.get("description", existing.description if existing is not None else None),
                    label="description",
                    maximum=2_000,
                ),
                aliases=aliases,
                positive_examples=() if existing is None else existing.positive_examples,
                negative_examples=() if existing is None else existing.negative_examples,
                priority=_integer(
                    payload.get("priority", existing.priority if existing is not None else 10),
                    label="priority",
                    minimum=-10_000,
                    maximum=10_000,
                ),
                enabled=enabled,
                version=version,
                level=1,
                created_by="owner",
            )
        except (TypeError, ValueError) as error:
            raise WebUIError(400, "invalid_taxonomy", "Taxonomy input violates the Owner category contract") from error

    def mutate_taxonomy(self, value: object) -> dict[str, Any]:
        payload = _mapping(value, label="taxonomy request")
        action = _string(payload.get("action"), label="taxonomy action", maximum=20)
        categories = {item.category_id: item for item in self._store.list_taxonomy_categories()}
        try:
            if action == "create":
                category = self._category_from_payload(
                    payload,
                    category_id=uuid4(),
                    version=1,
                    existing=None,
                    enabled=True,
                )
                disposition = self._taxonomy.create(category)
            elif action in {"update", "disable", "merge"}:
                category_id = _uuid(payload.get("category_id"), label="category_id")
                existing = categories.get(category_id)
                if existing is None:
                    raise WebUIError(404, "category_not_found", "Owner category does not exist")
                if action == "update":
                    if not existing.enabled:
                        raise WebUIError(409, "category_disabled", "Disabled category cannot be updated")
                    category = self._category_from_payload(
                        payload,
                        category_id=existing.category_id,
                        version=existing.version + 1,
                        existing=existing,
                        enabled=True,
                    )
                    disposition = self._taxonomy.update(category)
                elif action == "disable":
                    if not existing.enabled:
                        raise WebUIError(409, "category_disabled", "Category is already disabled")
                    category = self._category_from_payload(
                        payload,
                        category_id=existing.category_id,
                        version=existing.version + 1,
                        existing=existing,
                        enabled=False,
                    )
                    disposition = self._taxonomy.disable(category)
                else:
                    target_id = _uuid(payload.get("target_category_id"), label="target_category_id")
                    if target_id == existing.category_id:
                        raise WebUIError(400, "invalid_taxonomy", "Merge target must differ from source category")
                    target = categories.get(target_id)
                    if target is None or not target.enabled:
                        raise WebUIError(409, "invalid_merge_target", "Merge target must be an enabled Owner category")
                    category = self._category_from_payload(
                        payload,
                        category_id=existing.category_id,
                        version=existing.version + 1,
                        existing=existing,
                        enabled=False,
                    )
                    disposition = self._taxonomy.merge(category, target_category_id=target_id)
            else:
                raise WebUIError(400, "invalid_input", "Taxonomy action is unsupported")
        except X2NRuntimeError as error:
            raise WebUIError(409, error.code.value, error.safe_message) from error
        if not isinstance(disposition, WriteDisposition):
            raise WebUIError(409, "taxonomy_write_invalid", "Taxonomy revision result is invalid")
        return {"action": action, "disposition": disposition.value, "taxonomy": self.taxonomy()}

    def confirm_review(self, content_key: str, value: object) -> dict[str, Any]:
        payload = _mapping(value, label="review request")
        try:
            item = self._store.local_ui_review_item(content_key)
            if item is None:
                raise WebUIError(409, "review_stale", "Review item is no longer pending")
            review = LocalReviewItem.from_store(item)
            snapshot = self._snapshot()
            received_token = _string(payload.get("review_token"), label="review_token", maximum=128)
            if not hmac.compare_digest(received_token, review.token(snapshot)):
                raise WebUIError(409, "review_stale", "Review state changed; reload before confirming")
            selected_category = snapshot.require_enabled(_uuid(payload.get("category_id"), label="category_id"))
            status = (
                ReviewStatus.OWNER_CONFIRMED
                if review.classification_id is None or review.current_category_id == str(selected_category.category_id)
                else ReviewStatus.OWNER_CORRECTED
            )
            classification_id = f"class_{_canonical_sha256((review.token(snapshot), str(selected_category.category_id), status.value))[:32]}"
            classification = Classification(
                schema_version="1.0",
                classification_id=classification_id,
                content_key=review.content_key,
                taxonomy_version=snapshot.version,
                primary_category_id=selected_category.category_id,
                tags=(),
                candidate_ranking=(
                    ClassificationCandidate(category_id=selected_category.category_id, calibrated_score=1.0),
                ),
                decision_mode=DecisionMode.HUMAN,
                confidence_raw=None,
                calibration_bucket=None,
                evidence_artifact_ids=review.artifact_ids[:20],
                explanation_private_ref=None,
                review_status=status,
                created_at=_utc_now(),
                supersedes_classification_id=review.classification_id,
            )
            disposition = self._store.append_classification(classification)
        except X2NRuntimeError as error:
            raise WebUIError(409, error.code.value, error.safe_message) from error
        return {
            "classification_id": classification.classification_id,
            "disposition": disposition.value,
            "review_status": classification.review_status.value,
        }


def _document(csrf_token: str) -> bytes:
    safe_token = html.escape(csrf_token, quote=True)
    return f"""<!doctype html>
<html lang=\"zh-CN\">
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <meta name=\"x2n-csrf\" content=\"{safe_token}\">
    <title>x2n Local Review</title>
    <link rel=\"stylesheet\" href=\"/app.css\">
    <script defer src=\"/app.js\"></script>
  </head>
  <body>
    <header>
      <p class=\"eyebrow\">Local Companion · loopback only</p>
      <h1>xhs-douyin-2notion</h1>
      <p id=\"status\" aria-live=\"polite\">正在加载本机知识治理状态…</p>
    </header>
    <nav aria-label=\"Local WebUI sections\">
      <a href=\"#dashboard\">概览</a><a href=\"#sources\">来源</a><a href=\"#taxonomy\">分类</a>
      <a href=\"#review\">复核</a><a href=\"#jobs\">任务</a><a href=\"#sinks\">Sinks</a>
      <a href=\"#models\">模型</a><a href=\"#lifecycle\">生命周期</a><a href=\"#diagnostics\">诊断</a>
    </nav>
    <main>
      <section id=\"dashboard\" aria-labelledby=\"dashboard-title\"><h2 id=\"dashboard-title\">概览</h2><div class=\"panel\"></div></section>
      <section id=\"sources\" aria-labelledby=\"sources-title\"><h2 id=\"sources-title\">来源设置</h2><div class=\"panel\"></div></section>
      <section id=\"taxonomy\" aria-labelledby=\"taxonomy-title\"><h2 id=\"taxonomy-title\">Owner 分类</h2><div class=\"panel\"></div></section>
      <section id=\"review\" aria-labelledby=\"review-title\"><h2 id=\"review-title\">低置信度复核</h2><div class=\"panel\"></div></section>
      <section id=\"jobs\" aria-labelledby=\"jobs-title\"><h2 id=\"jobs-title\">任务与失败状态</h2><div class=\"panel\"></div></section>
      <section id=\"sinks\" aria-labelledby=\"sinks-title\"><h2 id=\"sinks-title\">Markdown / Notion</h2><div class=\"panel\"></div></section>
      <section id=\"models\" aria-labelledby=\"models-title\"><h2 id=\"models-title\">模型预算</h2><div class=\"panel\"></div></section>
      <section id=\"lifecycle\" aria-labelledby=\"lifecycle-title\"><h2 id=\"lifecycle-title\">本地生命周期与恢复</h2><div class=\"panel\"></div></section>
      <section id=\"diagnostics\" aria-labelledby=\"diagnostics-title\"><h2 id=\"diagnostics-title\">脱敏诊断</h2><div class=\"panel\"></div></section>
    </main>
  </body>
</html>
""".encode("utf-8")


APP_CSS = b"""
:root { color-scheme: light dark; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
body { margin: 0 auto; max-width: 72rem; padding: 1.25rem; line-height: 1.5; }
header, section { border-bottom: 1px solid #8794a8; padding: 1rem 0; }
nav { display: flex; flex-wrap: wrap; gap: .75rem; padding: .75rem 0; }
.eyebrow { font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; }
.panel { display: grid; gap: .75rem; }
article { border: 1px solid #8794a8; border-radius: .4rem; padding: .75rem; }
label { display: grid; gap: .25rem; font-weight: 600; }
input, select, textarea, button { font: inherit; padding: .4rem; }
textarea { min-height: 5rem; }
.muted { color: #536273; }
.error { color: #b42318; font-weight: 700; }
"""


APP_JS = """
const csrf = document.querySelector('meta[name="x2n-csrf"]').content;
const status = document.querySelector('#status');

function node(name, text) {
  const element = document.createElement(name);
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function clear(panel) { panel.replaceChildren(); return panel; }

async function get(path) {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.safe_message || 'Local request failed');
  return payload;
}

async function post(path, payload) {
  const response = await fetch(path, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-X2N-CSRF': csrf, 'X-X2N-WebUI': '1' },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.safe_message || 'Local mutation failed');
  return result;
}

function renderJson(section, value) {
  const pre = node('pre');
  pre.textContent = JSON.stringify(value, null, 2);
  clear(section.querySelector('.panel')).append(pre);
}

function renderSources(value) { renderJson(document.querySelector('#sources'), value); }
function renderSinks(value) { renderJson(document.querySelector('#sinks'), value); }
function renderModels(value) { renderJson(document.querySelector('#models'), value); }
function renderLifecycle(value) { renderJson(document.querySelector('#lifecycle'), value); }

function renderDashboard(value) { renderJson(document.querySelector('#dashboard'), value); }

function renderJobs(value) {
  const panel = clear(document.querySelector('#jobs .panel'));
  for (const job of value.jobs || []) {
    const card = node('article');
    card.append(node('h3', job.job_id), node('p', `${job.state} · ${job.run_kind}`));
    if (job.error_code) card.append(node('p', `错误：${job.error_code}`));
    panel.append(card);
  }
  if (!panel.childNodes.length) panel.append(node('p', '没有可显示的任务。'));
}

function renderTaxonomy(value) {
  const panel = clear(document.querySelector('#taxonomy .panel'));
  panel.append(node('p', '一级分类仅由 Owner 创建、更新、禁用或合并；AI 无此能力。'));
  for (const category of value.categories || []) {
    const card = node('article');
    card.append(node('h3', category.name), node('p', `${category.slug} · v${category.version}`));
    card.append(node('p', category.enabled ? '已启用' : '已禁用'));
    panel.append(card);
  }
  const form = node('form');
  const name = node('input'); name.required = true; name.name = 'name';
  const slug = node('input'); slug.required = true; slug.name = 'slug';
  const description = node('textarea'); description.required = true; description.name = 'description';
  form.append(node('h3', '新建 Owner 一级分类'));
  for (const [label, field] of [['名称', name], ['Slug', slug], ['说明', description]]) {
    const wrapper = node('label', label); wrapper.append(field); form.append(wrapper);
  }
  const submit = node('button', '创建分类'); submit.type = 'submit'; form.append(submit);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await post('/api/v2/taxonomy', { action: 'create', name: name.value, slug: slug.value, description: description.value });
      window.location.reload();
    } catch (error) { status.textContent = error.message; status.className = 'error'; }
  });
  panel.append(form);
}

function renderReview(value, taxonomy) {
  const panel = clear(document.querySelector('#review .panel'));
  const enabled = (taxonomy.categories || []).filter((item) => item.enabled);
  for (const item of value.items || []) {
    const card = node('article');
    card.append(node('h3', item.content_key));
    card.append(node('p', `${item.platform} · ${item.evidence_artifact_count} 条证据`));
    const label = node('label', 'Owner 选择现有分类');
    const select = node('select');
    for (const category of enabled) {
      const option = node('option', category.name); option.value = category.category_id; select.append(option);
    }
    label.append(select); card.append(label);
    const confirm = node('button', '确认复核'); confirm.type = 'button';
    confirm.disabled = !enabled.length;
    confirm.addEventListener('click', async () => {
      try {
        await post(`/api/v2/review/${encodeURIComponent(item.content_key)}`, {
          category_id: select.value, review_token: item.review_token,
        });
        window.location.reload();
      } catch (error) { status.textContent = error.message; status.className = 'error'; }
    });
    card.append(confirm); panel.append(card);
  }
  if (!panel.childNodes.length) panel.append(node('p', '没有待复核内容。'));
}

function renderDiagnostics(value) {
  const panel = clear(document.querySelector('#diagnostics .panel'));
  renderJson(document.querySelector('#diagnostics'), value);
  const link = node('a', '下载脱敏诊断 JSON'); link.href = '/api/v2/diagnostics/export';
  document.querySelector('#diagnostics .panel').append(link);
}

async function boot() {
  try {
    const [dashboard, sources, taxonomy, review, jobs, sinks, models, lifecycle, diagnostics] = await Promise.all([
      get('/api/v2/dashboard'), get('/api/v2/sources'), get('/api/v2/taxonomy'), get('/api/v2/review'),
      get('/api/v2/jobs'), get('/api/v2/sinks'), get('/api/v2/models'), get('/api/v2/lifecycle'), get('/api/v2/diagnostics'),
    ]);
    renderDashboard(dashboard); renderSources(sources); renderTaxonomy(taxonomy); renderReview(review, taxonomy);
    renderJobs(jobs); renderSinks(sinks); renderModels(models); renderLifecycle(lifecycle); renderDiagnostics(diagnostics);
    status.textContent = '本机 Local WebUI 已连接。';
  } catch (error) { status.textContent = error.message; status.className = 'error'; }
}

boot();
""".encode("utf-8")


class _LocalWebUIHandler(BaseHTTPRequestHandler):
    server_version = "x2n-local-webui"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def _app(self) -> LocalWebUI:
        app = getattr(self.server, "x2n_app", None)
        if not isinstance(app, LocalWebUI):
            raise WebUIError(500, "server_invalid", "Local WebUI is unavailable")
        return app

    def _origin(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.server.server_address[1]}"

    def _send(self, status: int, payload: bytes, *, content_type: str, attachment: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("Content-Type", content_type)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Connection", "close")
        if attachment is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, payload: Mapping[str, Any], *, attachment: str | None = None) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            ),
            content_type="application/json; charset=utf-8",
            attachment=attachment,
        )

    def _error(self, error: WebUIError) -> None:
        self._json(error.status, {"code": error.code, "safe_message": error.safe_message, "status": "FAIL_CLOSED"})

    def _read_json(self) -> Mapping[str, Any]:
        if self.headers.get("Transfer-Encoding") is not None:
            raise WebUIError(400, "invalid_input", "Chunked Local WebUI requests are rejected")
        length_header = self.headers.get("Content-Length")
        if length_header is None or not length_header.isascii() or not length_header.isdecimal():
            raise WebUIError(411, "invalid_input", "Local WebUI request length is required")
        length = int(length_header)
        if not 1 <= length <= MAX_BODY_BYTES:
            raise WebUIError(413, "payload_too_large", "Local WebUI request body is too large")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise WebUIError(415, "invalid_content_type", "Local WebUI mutations require JSON")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise WebUIError(400, "invalid_input", "Local WebUI request body is incomplete")
        try:
            return _mapping(json.loads(raw.decode("utf-8")), label="request")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WebUIError(400, "invalid_json", "Local WebUI request JSON is invalid") from error

    def _require_mutation_proof(self) -> None:
        if self.client_address[0] != LOOPBACK_HOST:
            raise WebUIError(403, "origin_rejected", "Local WebUI accepts loopback requests only")
        if self.headers.get("Host") != f"{LOOPBACK_HOST}:{self.server.server_address[1]}":
            raise WebUIError(403, "host_rejected", "Local WebUI Host header is invalid")
        if self.headers.get("Origin") != self._origin():
            raise WebUIError(403, "origin_rejected", "Local WebUI Origin is invalid")
        received = self.headers.get("X-X2N-CSRF")
        if received is None or not hmac.compare_digest(received, self._app.csrf_token):
            raise WebUIError(403, "csrf_rejected", "Local WebUI CSRF proof is invalid")

    def _path(self) -> str:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            raise WebUIError(400, "invalid_path", "Local WebUI query parameters are not supported")
        return parsed.path

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = self._path()
            if path == "/":
                self._send(200, _document(self._app.csrf_token), content_type="text/html; charset=utf-8")
                return
            if path == "/app.css":
                self._send(200, APP_CSS, content_type="text/css; charset=utf-8")
                return
            if path == "/app.js":
                self._send(200, APP_JS, content_type="application/javascript; charset=utf-8")
                return
            routes: dict[str, Any] = {
                "/api/v2/dashboard": self._app.dashboard,
                "/api/v2/sources": self._app.sources,
                "/api/v2/taxonomy": self._app.taxonomy,
                "/api/v2/review": self._app.review_queue,
                "/api/v2/jobs": lambda: {"jobs": self._app._store.local_ui_snapshot()["jobs"]},
                "/api/v2/sinks": self._app.sinks,
                "/api/v2/models": self._app.models,
                "/api/v2/lifecycle": self._app.lifecycle,
                "/api/v2/diagnostics": self._app.diagnostics,
            }
            if path == "/api/v2/diagnostics/export":
                self._json(200, self._app.diagnostics(), attachment="x2n-diagnostics.json")
                return
            if path.startswith("/api/v2/jobs/"):
                job_id = unquote(path.removeprefix("/api/v2/jobs/"))
                detail = self._app.job_detail(job_id)
                if detail is None:
                    raise WebUIError(404, "job_not_found", "Job does not exist")
                self._json(200, detail)
                return
            route = routes.get(path)
            if route is None:
                raise WebUIError(404, "not_found", "Local WebUI route does not exist")
            self._json(200, route())
        except X2NRuntimeError as error:
            self._error(WebUIError(409, error.code.value, error.safe_message))
        except WebUIError as error:
            self._error(error)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = self._path()
            if path != "/api/v2/taxonomy" and not path.startswith("/api/v2/review/"):
                raise WebUIError(404, "not_found", "Local WebUI route does not exist")
            self._require_mutation_proof()
            payload = self._read_json()
            if path == "/api/v2/taxonomy":
                self._json(200, self._app.mutate_taxonomy(payload))
                return
            content_key = unquote(path.removeprefix("/api/v2/review/"))
            self._json(200, self._app.confirm_review(content_key, payload))
        except X2NRuntimeError as error:
            self._error(WebUIError(409, error.code.value, error.safe_message))
        except WebUIError as error:
            self._error(error)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._error(WebUIError(405, "method_not_allowed", "Local WebUI does not expose CORS methods"))

    def log_message(self, _format: str, *_args: object) -> None:
        """Do not leak URL paths or request metadata to ambient process logs."""


def create_local_webui_server(app: LocalWebUI, *, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    if not isinstance(port, int) or isinstance(port, bool) or not (port == 0 or 1024 <= port <= 65535):
        raise WebUIError(400, "invalid_port", "Local WebUI port must be zero or between 1024 and 65535")
    server = ThreadingHTTPServer((LOOPBACK_HOST, port), _LocalWebUIHandler)
    server.daemon_threads = True
    setattr(server, "x2n_app", app)
    return server


def serve_local_webui(store: CanonicalStore, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    """Serve the WebUI until interrupted; no LAN listener or external call is created."""

    server = create_local_webui_server(LocalWebUI(store), port=port)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
    return {
        "action": "local_webui_stopped",
        "host": LOOPBACK_HOST,
        "network_calls": 0,
        "schema_version": LOCAL_UI_SCHEMA_VERSION,
        "task_id": TASK_ID,
    }

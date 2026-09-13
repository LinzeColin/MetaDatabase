"""V2 只读 API。阻断态清晰说明数据链路不完整且没有任何投资动作。"""

from __future__ import annotations

from copy import deepcopy
import mimetypes
from collections.abc import Mapping
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .aggregate import blocked_decision
from .live_config import APP_VERSION, LiveSettings
from .live_runtime import LiveStore
from .serialization import JsonSerializationConstraintError, strict_json_dumps


HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}

# 就绪报告最多允许落后 3 个循环，并额外留 90 秒给行情抓取与落盘。
# 默认 60 秒循环的 TTL 为 270 秒；超过它时旧 DATA_READY 绝不代表实时结论。
READY_TTL_LOOP_MULTIPLIER = 3
READY_TTL_FETCH_ALLOWANCE_SECONDS = 90
OOS_HISTORY_INSUFFICIENT_PREFIX = "OOS_HISTORY_INSUFFICIENT:"


def readiness_ttl_seconds(loop_seconds: int) -> int:
    return READY_TTL_LOOP_MULTIPLIER * loop_seconds + READY_TTL_FETCH_ALLOWANCE_SECONDS


def blocked_report() -> dict:
    return {
        "state": "SYSTEM_BLOCKED",
        "message": "数据链路不完整，不出结论",
        "decision": blocked_decision(),
    }


def collection_loop_unreachable_report(liveness: dict) -> dict:
    decision = blocked_decision()
    decision.update(
        {
            "rationale": "采集循环失联，结论已过期；不把旧报告作为实时结论。",
            "internal_coordination": "采集循环心跳或最新报告超过时效窗口，未复用旧方向性结论。",
            "counter_evidence": "最后一份报告已超过就绪时效，无法证明当前行情与历史结论一致。",
            "invalidation": "采集循环恢复心跳，并写入通过数据新鲜度门的新报告后，才恢复实时结论。",
        }
    )
    return {
        "state": "SYSTEM_BLOCKED",
        "blocked_reason": "COLLECTION_LOOP_UNREACHABLE",
        "message": "采集循环失联，结论已过期",
        "decision": decision,
        "last_generated_at": liveness["generated_at"],
        "last_heartbeat_at": liveness["heartbeat_at"],
        "readiness_ttl_seconds": liveness["max_age_seconds"],
        "liveness_reason": liveness["reason"],
    }


def latest_for_api(settings: LiveSettings, store: LiveStore, *, now: datetime | None = None) -> tuple[dict, dict]:
    """把旧持久化报告与当前循环存活状态合并成 API 唯一事实。"""
    liveness = store.liveness(
        max_age_seconds=readiness_ttl_seconds(settings.loop_seconds),
        now=now,
    )
    latest = liveness["latest"]
    if latest and not liveness["fresh"]:
        return collection_loop_unreachable_report(liveness), liveness
    return latest, liveness


def _profitability_sufficiency(report: Mapping[str, object]) -> str | None:
    backtest = report.get("backtest")
    candidates = (
        backtest.get("sample_sufficiency") if isinstance(backtest, Mapping) else None,
        report.get("profitability_status"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith(OOS_HISTORY_INSUFFICIENT_PREFIX):
            return candidate
    return None


def _public_backtest_view(backtest: Mapping[str, object], sufficiency: str) -> dict:
    """样本外历史不足时只公开门槛事实，不公开任何业绩样本或指标。"""
    method = backtest.get("method")
    minimum_windows = (
        method.get("minimum_oos_windows_for_profitability")
        if isinstance(method, Mapping)
        else None
    )
    branches = backtest.get("branches")
    public_branches = []
    if isinstance(branches, Mapping):
        for branch in branches.values():
            if not isinstance(branch, Mapping):
                continue
            public_branch = {
                key: branch[key]
                for key in (
                    "branch_id",
                    "status",
                    "sample_sufficiency",
                    "sample_sufficiency_message",
                    "profitability_evidence",
                    "profitability_evidence_note",
                )
                if key in branch
            }
            public_branches.append(public_branch)
    return {
        "status": backtest.get("status", "SAMPLE_INSUFFICIENT"),
        "sample_sufficiency": sufficiency,
        "sample_sufficiency_message": backtest.get(
            "sample_sufficiency_message",
            "样本外历史不足，仅供研究参考，不构成收益证据。",
        ),
        "profitability_status": sufficiency,
        "profitability_disclosure": {
            "status": "INSUFFICIENT",
            "minimum_oos_windows_for_profitability": minimum_windows,
            "message": "样本外历史不足，仅供研究参考，不构成收益证据。",
        },
        "branches": public_branches,
    }


def _public_contribution_weights(weights: object) -> object:
    """保留权重资格和样本门，移除由收益样本计算出的数值和逐期轨迹。"""
    if not isinstance(weights, Mapping):
        return weights
    result = {
        key: weights[key]
        for key in (
            "weight_mode",
            "weight_sample_count",
            "minimum_contribution_samples",
            "eligible_branch_ids",
        )
        if key in weights
    }
    branches = weights.get("branches")
    if not isinstance(branches, list):
        result["branches"] = []
        return result
    result["branches"] = [
        {
            key: branch[key]
            for key in (
                "branch_id",
                "weight",
                "sample_count",
                "usable_sample_count",
                "minimum_contribution_samples",
                "participation_status",
                "eligible_for_weighting",
                "weight_status",
                "negative_contribution_status",
                "negative_contribution_message",
            )
            if key in branch
        }
        for branch in branches
        if isinstance(branch, Mapping)
    ]
    return result


def public_report_view(report: Mapping[str, object]) -> dict:
    """生成公开 API 视图；运行期完整报告始终留在私有 state_dir。"""
    public = deepcopy(dict(report))
    sufficiency = _profitability_sufficiency(public)
    if sufficiency is None:
        return public
    backtest = public.get("backtest")
    if isinstance(backtest, Mapping):
        public["backtest"] = _public_backtest_view(backtest, sufficiency)
    public["profitability_status"] = sufficiency
    public["profitability_disclosure"] = {
        "status": "INSUFFICIENT",
        "sample_sufficiency": sufficiency,
        "message": "样本外历史不足，仅供研究参考，不构成收益证据。",
    }
    public["contribution_weights"] = _public_contribution_weights(public.get("contribution_weights"))
    return public


def handler(settings: LiveSettings, store: LiveStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return None

        def _send(self, status: int, payload, content_type: str = "application/json; charset=utf-8") -> None:
            if isinstance(payload, bytes):
                raw = payload
            else:
                try:
                    raw = strict_json_dumps(payload, ensure_ascii=False).encode("utf-8")
                except JsonSerializationConstraintError:
                    status = 503
                    raw = strict_json_dumps({
                        **blocked_report(),
                        "serialization_constraint": "NONFINITE_JSON_VALUE",
                    }, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            for key, value in HEADERS.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def _latest(self) -> dict:
            return store.latest()

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            latest, liveness = latest_for_api(settings, store)
            public_latest = public_report_view(latest)
            if path == "/health/live":
                return self._send(200, {"status": "alive", "version": APP_VERSION})
            if path == "/health/ready":
                ready = public_latest.get("state") == "DATA_READY"
                return self._send(200 if ready else 503, {
                    "status": "ready" if ready else "blocked",
                    "state": public_latest.get("state", "SYSTEM_BLOCKED"),
                    "reason": public_latest.get("blocked_reason") or liveness["reason"],
                    "readiness_ttl_seconds": liveness["max_age_seconds"],
                })
            if path == "/api/v1/report/latest":
                report = public_latest or blocked_report()
                return self._send(200 if report.get("state") == "DATA_READY" else 503, report)
            if path == "/api/v1/whitebox/summary":
                return self._send(200, {
                    "state": public_latest.get("state", "SYSTEM_BLOCKED"),
                    "weight_mode": public_latest.get("weight_mode", "COLD_START_EQUAL"),
                    "weight_sample_count": public_latest.get("weight_sample_count", 0),
                    "contribution_weights": public_latest.get("contribution_weights", {"branches": []}),
                    "branch_count": len(public_latest.get("branches", [])),
                    "quote_observed_at": public_latest.get("quote_observed_at"),
                    "data_cutoff": public_latest.get("data_cutoff"),
                    "profitability_status": public_latest.get("profitability_status", "SAMPLE_INSUFFICIENT"),
                    "automatic_trading": False,
                })
            if path == "/api/v1/whitebox/skills":
                return self._send(200, {"state": public_latest.get("state", "SYSTEM_BLOCKED"), "items": public_latest.get("branches", [])})
            if path == "/api/v1/whitebox/backtest/latest":
                return self._send(200, public_latest.get("backtest", {"status": "SAMPLE_INSUFFICIENT", "message": "样本不足，未出具收益结论"}))
            if path in {"/api/v1/heartbeat", "/api/v1/metadata", "/api/v1/system/status"}:
                return self._send(200, {
                    "application_version": APP_VERSION,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                    "state": public_latest.get("state", "SYSTEM_BLOCKED"),
                    "quote_observed_at": public_latest.get("quote_observed_at"),
                    "data_cutoff": public_latest.get("data_cutoff"),
                    "automatic_trading": False,
                    "public_url": settings.public_url,
                })
            filename = "index.html" if path in {"", "/"} else path.lstrip("/")
            target = (settings.web_dir / filename).resolve()
            if settings.web_dir.resolve() not in target.parents and target != settings.web_dir.resolve():
                return self._send(403, {"error": "FORBIDDEN"})
            if target.is_file():
                content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if content_type.startswith("text/") or content_type == "application/javascript":
                    content_type += "; charset=utf-8"
                return self._send(200, target.read_bytes(), content_type)
            return self._send(404, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:
            self._send(405, {"error": "READ_ONLY_RESEARCH_SYSTEM"})
    return Handler


def serve(settings: LiveSettings) -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), handler(settings, LiveStore(settings.state_dir)))
    server.serve_forever()

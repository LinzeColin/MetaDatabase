from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx

from .base import ConnectorError, ConnectorResult
from .. import gallerydl_runner
from ..utils import assert_public_http_url, read_secret, redact


class CommandArtifactConnector:
    """Process-isolated CLI adapter. Production uses the HTTP sidecar; local binaries remain a test/dev fallback."""

    ALLOWED = {"yt-dlp", "gallery-dl", "instaloader", "bili"}
    BILI_ALLOWED_SUBCOMMANDS = {"favorites", "watch-later", "history"}

    def __init__(
        self,
        connector_id: str,
        staging_root: Path,
        timeout_seconds: int = 900,
        *,
        worker_url: str = "",
        worker_token_file: str | None = None,
        worker_output_root: Path | None = None,
    ):
        self.connector_id = connector_id
        self.display_name = connector_id
        self.staging_root = staging_root
        self.timeout_seconds = timeout_seconds
        self.worker_url = worker_url.rstrip("/")
        self.worker_token_file = worker_token_file
        self.worker_output_root = (worker_output_root or staging_root / "vendor-output/cli").resolve()

    def _headers(self) -> dict[str, str]:
        token = read_secret(self.worker_token_file)
        return {"X-Social-Archive-Worker-Token": token} if token else {}

    def _remote(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.worker_url:
            raise ConnectorError("CLI_WORKER_NOT_CONFIGURED", "CLI 下载 Sidecar 尚未配置", retryable=False)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.worker_url}{path}", json=payload, headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if path == "/v1/bilibili/list" and status_code in {412, 429}:
                return {
                    "status": "degraded",
                    "error_code": "BILI_RATE_LIMITED",
                    "message": "B站暂时限流（HTTP 412/429）；未尝试绕过，请稍后重试或保存当前页。",
                    "retryable": True,
                    "observations": [],
                    "artifacts": [],
                }
            raise ConnectorError("CLI_WORKER_FAILED", f"CLI Sidecar 调用失败：HTTP {status_code}", retryable=True) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError("CLI_WORKER_FAILED", f"CLI Sidecar 调用失败：{exc.__class__.__name__}", retryable=True) from exc
        if not isinstance(data, dict):
            raise ConnectorError("CLI_WORKER_INVALID_RESPONSE", "CLI Sidecar 返回格式错误", retryable=True)
        return data

    def _remote_artifacts(self, raw: list[Any]) -> list[dict[str, str]]:
        artifacts: list[dict[str, str]] = []
        root = self.worker_output_root
        for item in raw:
            relative = Path(str(item))
            if relative.is_absolute() or ".." in relative.parts:
                continue
            candidate = (root / relative).resolve()
            if candidate != root and root not in candidate.parents:
                continue
            artifacts.append({"path": str(candidate), "type": "downloaded_file"})
        return artifacts

    def health(self) -> dict[str, Any]:
        if self.worker_url:
            try:
                with httpx.Client(timeout=3.0) as client:
                    response = client.get(f"{self.worker_url}/health")
                    response.raise_for_status()
                    data = response.json()
                return {"state": "healthy", "mode": "isolated_http_sidecar", "tools": data.get("tools", {})}
            except (httpx.HTTPError, ValueError) as exc:
                return {"state": "degraded", "mode": "isolated_http_sidecar", "error_code": exc.__class__.__name__}
        binaries = {name: bool(shutil.which(name)) for name in sorted(self.ALLOWED)}
        return {"state": "healthy" if any(binaries.values()) else "blocked_environment", "mode": "local_dev_fallback", "binaries": binaries}

    def _run(self, argv: list[str], run_dir: Path) -> subprocess.CompletedProcess[str]:
        binary = Path(argv[0]).name
        if binary not in self.ALLOWED:
            raise ConnectorError("COMMAND_NOT_ALLOWED", f"命令未在 allowlist：{binary}")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(run_dir / "home"), "LANG": "C.UTF-8"}
        (run_dir / "home").mkdir(parents=True, exist_ok=True)
        try:
            return subprocess.run(argv, cwd=run_dir, env=env, text=True, capture_output=True, timeout=self.timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ConnectorError("COMMAND_TIMEOUT", f"{binary} 超时", retryable=True) from exc

    def capture_url(self, url: str, tool: str = "yt-dlp") -> ConnectorResult:
        clean = assert_public_http_url(url)
        if tool not in {"gallery-dl", "yt-dlp"}:
            raise ConnectorError("TOOL_NOT_ALLOWED", f"不支持的工具：{tool}")
        if self.worker_url:
            data = self._remote("/v1/capture-url", {"url": clean, "tool": tool})
            status = str(data.get("status") or "failed")
            artifacts = self._remote_artifacts(data.get("artifacts") or [])
            errors = [] if status == "success" else [{"code": "CLI_WORKER_COMMAND_FAILED", "message": redact(str(data.get("stderr") or "Sidecar 未产生文件")), "retryable": status != "blocked_environment"}]
            return ConnectorResult(self.connector_id, str(data.get("run_id") or uuid.uuid4()), status, observations=data.get("observations") or [{"url": clean}], artifacts=artifacts, scan_receipt={"completeness": "complete" if status == "success" else "failed", "item_count": len(artifacts), "scope": "item", "execution_boundary": "isolated_http_sidecar"}, errors=errors)

        run_id = str(uuid.uuid4())
        run_dir = self.staging_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        argv = ["gallery-dl", "--dest", str(run_dir), "--write-metadata", "--write-info-json", clean] if tool == "gallery-dl" else ["yt-dlp", "--no-playlist", "--restrict-filenames", "--write-info-json", "--write-subs", "--write-auto-subs", "--no-progress", "--paths", str(run_dir), clean]
        result = self._run(argv, run_dir)
        evidence = {"argv": argv, "exit_code": result.returncode, "stdout": redact(result.stdout[-4000:]), "stderr": redact(result.stderr[-4000:])}
        (run_dir / "command-result.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        files = [p for p in run_dir.rglob("*") if p.is_file() and p.name != "command-result.json" and "home" not in p.parts]
        status = "success" if result.returncode == 0 and files else "failed"
        # 两个工具的退出码约定**不一样，不能共用一条规则**（实测自生产容器）：
        #   yt-dlp      1=下载/抽取错误  2=用法错误  100/101=中止
        #               （无效 URL → 1；错误参数 → 2）
        #   gallery-dl  位掩码 1/4/8/16/32/64/128，见 gallerydl_runner
        # 这里原来写的是 `result.returncode not in {1, 2}`——那是 **yt-dlp 的**约定，
        # 套到 gallery-dl 上就成了：鉴权失败(16)、撞验证码(8)、URL 不支持(64)
        # 统统判成「可重试」。而 db.finish_job 会把可重试的任务放回队列
        # （status = "retry" if retryable else "failed"），于是一个永远不会好的
        # 失败被反复重跑——正是 gallerydl_runner 模块文档里明令禁止的那种误判。
        if status == "success":
            errors = []
        elif tool == "gallery-dl":
            failure_code = gallerydl_runner.classify_exit_code(
                result.returncode, url=clean, stderr=result.stderr
            )
            errors = [{
                # 用定级后的码而不是笼统的 COMMAND_FAILED：后者在失败文案词典里
                # 认不出来，界面会说「我们没能记录下原因」——而其实是知道的。
                "code": failure_code or "COMMAND_FAILED",
                "message": redact(result.stderr[-1000:] or "命令未产生文件"),
                "retryable": gallerydl_runner.is_retryable_exit(
                    result.returncode, url=clean, stderr=result.stderr
                ),
            }]
        else:
            # yt-dlp：1 和 2 重试都解决不了（2 是我们自己把参数传错了）。
            errors = [{
                "code": "URL_NOT_SUPPORTED" if result.returncode == 2 else "SERVER_UNREACHABLE",
                "message": redact(result.stderr[-1000:] or "命令未产生文件"),
                "retryable": False,
            }]
        return ConnectorResult(self.connector_id, run_id, status, observations=[{"url": clean}], artifacts=[{"path": str(p), "type": "downloaded_file"} for p in files], scan_receipt={"completeness": "complete" if status == "success" else "failed", "item_count": len(files), "scope": "item", "execution_boundary": "local_dev_fallback"}, errors=errors)

    def instagram_saved(self, session_file: Path | None, username: str | None, limit: int = 20) -> ConnectorResult:
        if self.worker_url:
            data = self._remote("/v1/instagram/saved", {"username": username, "limit": limit})
            status = str(data.get("status") or "failed")
            observations = data.get("observations") or []
            artifacts = self._remote_artifacts(data.get("artifacts") or [])
            errors = [] if status == "success" else [{"code": "INSTAGRAM_SIDECAR_BLOCKED", "message": redact(str(data.get("stderr") or "Instagram Sidecar 未就绪")), "retryable": status != "blocked_environment"}]
            return ConnectorResult("instagram", str(data.get("run_id") or uuid.uuid4()), status, observations=observations, artifacts=artifacts, scan_receipt={"completeness": "partial" if status == "success" else "unknown", "item_count": len(observations), "scope": "account_relation", "execution_boundary": "isolated_http_sidecar"}, errors=errors)

        run_id = str(uuid.uuid4())
        if not session_file or not session_file.is_file() or not shutil.which("instaloader"):
            return ConnectorResult("instagram", run_id, "blocked_environment", scan_receipt={"completeness": "unknown", "item_count": 0}, errors=[{"code": "INSTAGRAM_SESSION_OR_BINARY_MISSING", "message": "缺少 0600 Session 文件或 Instaloader", "retryable": False}])
        mode = session_file.stat().st_mode & 0o777
        runtime_secret = str(session_file.resolve()).startswith("/run/secrets/")
        insecure = bool(mode & 0o022) or (not runtime_secret and bool(mode & 0o077))
        if insecure:
            return ConnectorResult("instagram", run_id, "blocked_environment", scan_receipt={"completeness": "unknown", "item_count": 0}, errors=[{"code": "INSTAGRAM_SESSION_PERMISSIONS", "message": "宿主机 Session 必须为 0600；Docker secret 不得具有组/其他用户写权限", "retryable": False}])
        run_dir = self.staging_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        argv = ["instaloader", "--sessionfile", str(session_file), "--dirname-pattern", str(run_dir / "{target}"), "--filename-pattern", "{shortcode}", "--no-compress-json", "--count", str(limit)]
        if username:
            argv.extend(["--login", username])
        argv.append(":saved")
        result = self._run(argv, run_dir)
        files = [p for p in run_dir.rglob("*") if p.is_file() and "home" not in p.parts]
        observations: list[dict[str, Any]] = []
        for info in run_dir.rglob("*.json"):
            try:
                raw = json.loads(info.read_text(encoding="utf-8"))
                node = raw.get("node") if isinstance(raw, dict) else None
                if isinstance(node, dict):
                    shortcode = node.get("shortcode") or info.stem
                    observations.append({"id": shortcode, "url": f"https://www.instagram.com/p/{shortcode}/", "raw": node})
            except (OSError, json.JSONDecodeError):
                continue
        status = "success" if result.returncode == 0 else "failed"
        return ConnectorResult("instagram", run_id, status, observations=observations, artifacts=[{"path": str(p), "type": "downloaded_file"} for p in files], scan_receipt={"completeness": "partial" if status == "success" else "failed", "item_count": len(observations), "scope": "account_relation"}, errors=[] if status == "success" else [{"code": "INSTALOADER_FAILED", "message": redact(result.stderr[-1000:]), "retryable": True}])

    @staticmethod
    def _bilibili_argv(subcommand: str, limit: int) -> list[str]:
        if subcommand == "history":
            return ["bili", "history", "--max", str(min(max(limit, 1), 100)), "--json"]
        return ["bili", subcommand, "--json"]

    @staticmethod
    def _bilibili_observations(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, dict) and raw.get("ok") is True:
            raw = raw.get("data")
        if isinstance(raw, dict):
            for key in ("items", "list", "medias"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
            else:
                return [raw]
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    def bilibili_list(self, subcommand: str, extra_args: list[str] | None = None) -> ConnectorResult:
        if subcommand not in self.BILI_ALLOWED_SUBCOMMANDS:
            raise ConnectorError("ACCOUNT_WRITE_FORBIDDEN", f"B站只读命令不允许：{subcommand}")
        limit = 20
        if extra_args and "--limit" in extra_args:
            try:
                limit = int(extra_args[extra_args.index("--limit") + 1])
            except (ValueError, IndexError):
                limit = 20
        limit = max(1, min(limit, 100 if subcommand == "history" else 500))
        if self.worker_url:
            data = self._remote("/v1/bilibili/list", {"subcommand": subcommand, "limit": limit})
            status = str(data.get("status") or "failed")
            observations = data.get("observations") or []
            error_code = str(data.get("error_code") or "BILI_SIDECAR_BLOCKED")
            message = str(data.get("message") or data.get("stderr") or "bilibili-cli 尚未配置")
            retryable = bool(data.get("retryable", status not in {"blocked_environment"}))
            errors = [] if status == "success" else [{"code": error_code, "message": redact(message), "retryable": retryable}]
            return ConnectorResult(self.connector_id, str(data.get("run_id") or uuid.uuid4()), status, observations=observations, artifacts=self._remote_artifacts(data.get("artifacts") or []), scan_receipt={"completeness": "partial" if status == "success" else "unknown", "item_count": len(observations), "scope": "account_relation", "execution_boundary": "isolated_http_sidecar"}, errors=errors)

        run_id = str(uuid.uuid4())
        run_dir = self.staging_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        argv = self._bilibili_argv(subcommand, limit)
        result = self._run(argv, run_dir)
        observations: list[dict[str, Any]] = []
        if result.returncode == 0:
            text = result.stdout.strip()
            try:
                parsed = json.loads(text)
                observations = self._bilibili_observations(parsed)
            except json.JSONDecodeError:
                return ConnectorResult(self.connector_id, run_id, "failed", scan_receipt={"completeness": "failed", "item_count": 0, "scope": "account_relation"}, errors=[{"code": "BILI_INVALID_RESPONSE", "message": "bilibili-cli 未返回结构化 JSON", "retryable": True}])
        status = "success" if result.returncode == 0 else "failed"
        return ConnectorResult(self.connector_id, run_id, status, observations=observations, scan_receipt={"completeness": "partial" if status == "success" else "failed", "item_count": len(observations), "scope": "account_relation"}, errors=[] if status == "success" else [{"code": "BILI_COMMAND_FAILED", "message": redact(result.stderr[-1000:]), "retryable": True}])

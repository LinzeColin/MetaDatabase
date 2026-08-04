from __future__ import annotations

import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

OUTPUT_ROOT = Path(os.getenv("SOCIAL_ARCHIVE_CLI_OUTPUT_ROOT", "/work/output/cli")).resolve()
TOKEN_FILE = os.getenv("SOCIAL_ARCHIVE_CLI_WORKER_TOKEN_FILE", "/run/secrets/cli_worker_token")
# 64 KiB 装得下 url + tool；带上 cookies.txt 之后要放宽。
# 平台的 cookies.txt 通常几 KB，256 KiB 留足余量而不至于变成上传通道。
MAX_BODY = 256 * 1024
# 登录状态只落在 tmpfs（compose 给本容器挂的 /tmp 是内存盘），
# 容器一停就没了。**绝不写进 OUTPUT_ROOT** —— 那是共享数据卷。
COOKIE_TMPDIR = os.getenv("SOCIAL_ARCHIVE_COOKIE_TMPDIR", "/tmp")
ALLOWED_TOOLS = {"gallery-dl", "yt-dlp", "instaloader", "bili"}
BILI_SUBCOMMANDS = {"favorites", "watch-later", "history"}


def _token() -> str:
    try:
        return Path(TOKEN_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _is_public_url(raw: str) -> str:
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("只允许公开 http/https 链接")
    host = parsed.hostname.rstrip(".")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("不允许本机地址")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("域名无法解析") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            raise ValueError("不允许私网、环回、链路本地或保留地址")
    return raw


def _run(argv: list[str], run_dir: Path, timeout: int = 900, *, require_artifacts: bool = True) -> dict:
    binary = Path(argv[0]).name
    if binary not in ALLOWED_TOOLS:
        raise ValueError("命令未在允许列表")
    if not shutil.which(binary):
        return {"status": "blocked_environment", "exit_code": 127, "stdout": "", "stderr": f"{binary} 未安装", "artifacts": []}
    home = run_dir / "home"
    home.mkdir(parents=True, exist_ok=True)
    config_home = home / ".config"
    cache_home = home / ".cache"
    data_home = home / ".local" / "share"
    for path in (config_home, cache_home, data_home):
        path.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_CACHE_HOME": str(cache_home),
        "XDG_DATA_HOME": str(data_home),
    }
    try:
        result = subprocess.run(argv, cwd=run_dir, env=env, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "exit_code": 124, "stdout": "", "stderr": f"{binary} 超时", "artifacts": []}
    artifacts = []
    for path in run_dir.rglob("*"):
        if not path.is_file() or "home" in path.parts or path.name == "command-result.json":
            continue
        artifacts.append(str(path.relative_to(OUTPUT_ROOT)))
    status = "success" if result.returncode == 0 and (artifacts or not require_artifacts) else "failed"
    receipt = {
        "status": status,
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "artifacts": artifacts,
    }
    (run_dir / "command-result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


def _capture_url(payload: dict) -> dict:
    """抓一个页面。可以带上调用方托管的平台登录状态。

    ## cookies_txt 这个参数是 T07 的落点

    Owner 明确裁定「Cookie 可以进 OVH」（2026-08-04）之后才加的。在此之前
    `capture_url` 的 sidecar 分支**根本没有传 cookies 的通道**：Core 那侧
    把托管的会话解密好了，走到这里却只发 url 和 tool——于是生产上
    （生产走的正是 sidecar 分支）取到的永远只有公开内容。

    ## 落地时的三条硬约束

    1. **只写进 /tmp**。compose 给这个容器挂的是
       `tmpfs: ["/tmp:rw,noexec,nosuid,size=512m"]` —— 内存盘。
       也就是说**登录状态从不落盘**，容器一停就没了。
    2. **0600 且用完即删**。mkstemp 建出来就是 0600（没有先建后 chmod 的
       竞态窗口），finally 里删，异常路径也删。
    3. **绝不进日志**。argv 里出现的是**路径**不是内容；_run 写的
       command-result.json 记的也是 argv。cookies 的值不出现在任何输出里。
    """
    url = _is_public_url(str(payload.get("url") or ""))
    tool = str(payload.get("tool") or "gallery-dl")
    if tool not in {"gallery-dl", "yt-dlp"}:
        raise ValueError("不支持的下载器")
    cookies_txt = str(payload.get("cookies_txt") or "")
    run_id = str(uuid.uuid4())
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    if tool == "gallery-dl":
        argv = ["gallery-dl", "--dest", str(run_dir), "--write-metadata", "--write-info-json"]
    else:
        argv = ["yt-dlp", "--no-playlist", "--restrict-filenames", "--write-info-json",
                "--write-subs", "--write-auto-subs", "--no-progress", "--paths", str(run_dir)]
    cookies_file: Path | None = None
    try:
        if cookies_txt:
            handle, raw = tempfile.mkstemp(prefix="sa-cookies-", suffix=".txt", dir=COOKIE_TMPDIR)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(cookies_txt)
            cookies_file = Path(raw)
            # 两个工具的 --cookies 都只收路径，不收管道。
            argv += ["--cookies", str(cookies_file)]
        argv.append(url)
        result = _run(argv, run_dir)
    finally:
        if cookies_file is not None:
            cookies_file.unlink(missing_ok=True)
    result.update({"run_id": run_id, "tool": tool, "observations": [{"url": url}],
                   "used_cookies": bool(cookies_txt)})
    return result


def _instagram_saved(payload: dict) -> dict:
    session = Path(os.getenv("SOCIAL_ARCHIVE_INSTAGRAM_SESSION_FILE", "/run/secrets/instagram_session"))
    if not session.is_file() or not session.read_bytes().strip():
        return {"status": "blocked_environment", "exit_code": 127, "stderr": "Instagram Session 尚未配置", "stdout": "", "artifacts": [], "observations": []}
    if session.stat().st_mode & 0o022:
        return {"status": "blocked_environment", "exit_code": 126, "stderr": "Instagram Session 权限不安全", "stdout": "", "artifacts": [], "observations": []}
    run_id = str(uuid.uuid4())
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    limit = max(1, min(int(payload.get("limit") or 20), 500))
    argv = ["instaloader", "--sessionfile", str(session), "--dirname-pattern", str(run_dir / "{target}"), "--filename-pattern", "{shortcode}", "--no-compress-json", "--count", str(limit)]
    username = str(payload.get("username") or "").strip()
    if username:
        argv.extend(["--login", username])
    argv.append(":saved")
    result = _run(argv, run_dir)
    observations = []
    for info in run_dir.rglob("*.json"):
        try:
            raw = json.loads(info.read_text(encoding="utf-8"))
            node = raw.get("node") if isinstance(raw, dict) else None
            if isinstance(node, dict):
                shortcode = node.get("shortcode") or info.stem
                observations.append({"id": shortcode, "url": f"https://www.instagram.com/p/{shortcode}/", "raw": node})
        except (OSError, json.JSONDecodeError):
            continue
    result.update({"run_id": run_id, "observations": observations})
    return result


def _bilibili_list(payload: dict) -> dict:
    subcommand = str(payload.get("subcommand") or "favorites")
    if subcommand not in BILI_SUBCOMMANDS:
        raise ValueError("B站只允许只读列表命令")
    run_id = str(uuid.uuid4())
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    limit = max(1, min(int(payload.get("limit") or 20), 100))
    argv = {
        "favorites": ["bili", "favorites", "--json"],
        "history": ["bili", "history", "--max", str(limit), "--json"],
        "watch-later": ["bili", "watch-later", "--json"],
    }[subcommand]
    result = _run(argv, run_dir, require_artifacts=False)
    raw_text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    if result.get("status") != "success" and any(marker in raw_text for marker in ("rate_limited", "rate limited", "http 412", "http 429")):
        return {
            "status": "degraded",
            "run_id": run_id,
            "exit_code": result.get("exit_code", 1),
            "error_code": "BILI_RATE_LIMITED",
            "message": "B站暂时限流（HTTP 412/429）；未尝试绕过，请稍后重试或保存当前页。",
            "retryable": True,
            "stdout": "",
            "stderr": "B站暂时限流",
            "artifacts": [],
            "observations": [],
        }
    if result.get("status") != "success":
        result.update({"run_id": run_id, "observations": []})
        return result

    text = result.get("stdout", "").strip()
    try:
        if not text:
            raise ValueError("empty response")
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            raise ValueError("upstream rejected the list request")
        payload_data = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(payload_data, dict) and isinstance(payload_data.get("items"), list):
            observations = payload_data["items"]
        elif isinstance(payload_data, list):
            observations = payload_data
        elif isinstance(payload_data, dict):
            observations = [payload_data]
        else:
            raise ValueError("response data is not a JSON object or list")
    except (ValueError, json.JSONDecodeError):
        return {
            "status": "failed",
            "run_id": run_id,
            "exit_code": result.get("exit_code", 1),
            "error_code": "BILI_INVALID_RESPONSE",
            "message": "bilibili-cli 未返回可信的结构化 JSON；未导入原始文本。",
            "retryable": True,
            "stdout": "",
            "stderr": "bilibili-cli 返回无效结构化数据",
            "artifacts": [],
            "observations": [],
        }
    result.update({"run_id": run_id, "observations": observations})
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "SocialArchiveCliWorker/0.0.0.6"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = _token()
        supplied = self.headers.get("X-Social-Archive-Worker-Token", "")
        return bool(expected) and secrets.compare_digest(expected, supplied)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._json(404, {"error": "not_found"})
            return
        self._json(200, {"status": "ok", "version": "0.0.0.6", "tools": {name: bool(shutil.which(name)) for name in sorted(ALLOWED_TOOLS)}})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY:
                raise ValueError("请求体过大")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是对象")
            if self.path == "/v1/capture-url":
                result = _capture_url(payload)
            elif self.path == "/v1/instagram/saved":
                result = _instagram_saved(payload)
            elif self.path == "/v1/bilibili/list":
                result = _bilibili_list(payload)
            else:
                self._json(404, {"error": "not_found"})
                return
            self._json(200, result)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._json(422, {"status": "failed", "error": exc.__class__.__name__, "message": str(exc), "artifacts": [], "observations": []})

    def log_message(self, fmt: str, *args: object) -> None:
        print(json.dumps({"component": "cli-tools", "message": fmt % args}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("SOCIAL_ARCHIVE_CLI_WORKER_PORT", "5560"))), Handler).serve_forever()

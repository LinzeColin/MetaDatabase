from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_HOST = "social-archive.linzezhang.com"
API_HOST = "social-archive-api.linzezhang.com"
STATUS_HOST = "status.linzezhang.com"
DEFAULT_CORE_LOOPBACK_PORT = "18765"
DEFAULT_STATUS_LOOPBACK_PORT = "18780"


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} 不是 YAML 对象")
    return value


def _env_value(text: str, key: str) -> str | None:
    prefix = f"{key}="
    values = [line[len(prefix):].strip() for line in text.splitlines() if line.startswith(prefix)]
    return values[-1] if values else None


def main() -> int:
    checks: list[dict[str, object]] = []

    def check(name: str, condition: bool) -> None:
        checks.append({"name": name, "status": "PASS" if condition else "FAIL"})

    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    core_loopback_port = _env_value(env, "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT")
    status_loopback_port = _env_value(env, "SOCIAL_ARCHIVE_STATUS_PORT")
    check(
        "isolated_loopback_ports_declared",
        core_loopback_port == DEFAULT_CORE_LOOPBACK_PORT and status_loopback_port == DEFAULT_STATUS_LOOPBACK_PORT,
    )

    try:
        compose = _read_yaml(ROOT / "compose.yaml")
        core = ((compose.get("services") or {}).get("core-api") or {})
        ports = core.get("ports") if isinstance(core, dict) else None
        expected_mapping = f"127.0.0.1:${{SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT:-{DEFAULT_CORE_LOOPBACK_PORT}}}:8765"
        check("core_api_loopback_only", ports == [expected_mapping])
        check("core_api_read_only", isinstance(core, dict) and core.get("read_only") is True)
    except Exception:
        check("compose_parse", False)

    try:
        tunnel = _read_yaml(ROOT / "deploy/cloudflare/tunnel-config.example.yml")
        ingress = tunnel.get("ingress")
        routes = [item for item in ingress or [] if isinstance(item, dict) and item.get("hostname")]

        def has_route(hostname: str, service: str, *, path: str | None = None) -> bool:
            return any(
                item.get("hostname") == hostname
                and item.get("service") == service
                and item.get("path") == path
                for item in routes
            )

        core_origin = f"http://127.0.0.1:{DEFAULT_CORE_LOOPBACK_PORT}"
        status_origin = f"http://127.0.0.1:{DEFAULT_STATUS_LOOPBACK_PORT}"
        check("tunnel_library_loopback", has_route(LIBRARY_HOST, core_origin))
        check("tunnel_api_loopback", has_route(API_HOST, core_origin))
        check(
            "tunnel_status_projection_loopback",
            has_route(STATUS_HOST, status_origin, path=r"^/social-archive(\.json|-health)$"),
        )
        check("tunnel_status_existing_site_passthrough", has_route(STATUS_HOST, "http://127.0.0.1:80"))
        check("tunnel_default_404", bool(ingress) and isinstance(ingress[-1], dict) and ingress[-1].get("service") == "http_status:404")
    except Exception:
        check("tunnel_parse", False)

    policy = (ROOT / "deploy/cloudflare/API_EDGE_POLICY.md").read_text(encoding="utf-8")
    for name, phrase in {
        "library_access_policy": "Cloudflare Access",
        "separate_api_host": API_HOST,
        "public_health": "GET /health",
        # v0.0.0.7 / T03：一次性配对码的两条公开路径与它的三条边缘保护
        # （10 次限流目标 / 5 次尝试上限 / 10 分钟有效期 / 16 KiB 体积上限）
        # 已随链路一并移除——端点没了，检查它们只会永远红。
        # 边缘限流规则本身**没有放宽**，改为下面这条通用防护来核对。
        "api_host_has_no_public_pairing_path": None,  # 见下方反向检查
        "edge_rate_limit_not_relaxed": "1 次 / 10 秒",
        "extension_token_is_revocable": "撤销后扩展上行立刻 401",
        "real_rule_evidence_not_source": "真实 Rule ID",
    }.items():
        if phrase is None:
            continue
        check(name, phrase in policy)

    # 反向检查：策略文件里不许再出现可用的配对端点声明。
    check(
        "api_host_has_no_public_pairing_path",
        "`POST /v1/pairing/exchange`" not in policy.split("已随 v0.0.0.7")[0],
    )

    check("library_url_declared", f"SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL=https://{LIBRARY_HOST}" in env)
    check("api_url_declared", f"SOCIAL_ARCHIVE_PUBLIC_BASE_URL=https://{API_HOST}" in env)
    status_publish = (ROOT / "scripts/status_publish.py").read_text(encoding="utf-8")
    check("status_under_data_root", 'settings.data_root / "status" / "social-archive.json"' in status_publish)
    check("status_not_project_runtime", 'Path("runtime/status/social-archive.json")' not in status_publish)
    status_server = (ROOT / "scripts/status_server.py").read_text(encoding="utf-8")
    check("status_server_loopback_only", 'LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})' in status_server)
    check("status_server_shared_health_path", 'STATUS_HEALTH_PATH = "/social-archive-health"' in status_server)
    check("status_server_readonly_methods", all(f"def do_{method}(self)" in status_server for method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE")))
    status_web = (ROOT / "deploy/systemd/social-archive-status-web.service").read_text(encoding="utf-8")
    check("status_web_no_write_path", "ReadWritePaths=" not in status_web)
    check("status_web_reads_projection_only", "ReadOnlyPaths=/var/lib/social-archive/status" in status_web)
    check("status_web_port_from_environment_file", "Environment=SOCIAL_ARCHIVE_STATUS_PORT=" not in status_web)

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    print(json.dumps({"status": status, "scope": "local_deployment_contract", "checks": checks}, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

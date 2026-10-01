"""公开数据面（eei-api）的无库单元测试：路由开关、头部、设置解析、部署件约束。

不连数据库：database_url=None 时 /health 回 503，其余需要库的路由也回 503，而写入类路由
在到达数据库之前就被关掉——这正是「公开部署里写入路由关闭」要证明的事。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.app.public.app import create_public_app
from apps.api.app.public.settings import PublicSettings, get_public_settings

DEPLOY = Path(__file__).resolve().parents[2] / "apps" / "api" / "deploy"

WRITE_OR_PRIVATE = [
    ("POST", "/v1/saved-views"),
    ("GET", "/v1/saved-views"),
    ("DELETE", "/v1/saved-views/abc"),
    ("POST", "/v1/watchlists"),
    ("GET", "/v1/watchlists"),
    ("GET", "/v1/exploration-log"),
    ("POST", "/v1/calibrations"),
    ("PUT", "/v1/scoring/profiles/default"),
    ("POST", "/v1/scoring/profiles"),
    ("POST", "/v1/snapshots/refresh"),
    ("POST", "/v1/internal/publish/exec"),
    ("GET", "/v1/internal/anything"),
    ("GET", "/v1/audit-logs"),
    ("GET", "/v1/data/export"),
    ("POST", "/v1/cloud/sync"),
]


def _client(**overrides: object) -> TestClient:
    settings = PublicSettings(database_url=None, **overrides)  # type: ignore[arg-type]
    return TestClient(create_public_app(settings, warm_up=False), raise_server_exceptions=False)


@pytest.mark.parametrize(("method", "path"), WRITE_OR_PRIVATE)
def test_write_and_private_routes_are_forbidden_by_default(method: str, path: str) -> None:
    response = _client().request(method, path, json={})
    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path"), WRITE_OR_PRIVATE)
def test_hidden_mode_answers_404_like_no_such_route(method: str, path: str) -> None:
    response = _client(write_route_mode="hidden").request(method, path, json={})
    assert response.status_code == 404


def test_unknown_v1_route_is_404_and_docs_are_not_mounted() -> None:
    client = _client()
    assert client.get("/v1/no-such-route").status_code == 404
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_health_without_database_is_503_and_reports_degraded() -> None:
    response = _client().get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_data_route_without_database_is_503_not_500() -> None:
    response = _client().get("/v1/entities", params={"q": "x"})
    assert response.status_code == 503
    assert "request_id" not in response.json()


def test_headers_cors_and_no_store() -> None:
    response = _client(build_sha="deadbeef").get("/health", headers={"origin": "https://x.example"})
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["x-eei-build"] == "deadbeef"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_settings_parse_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "EEI_WRITE_ROUTE_MODE",
        "EEI_REQUIRE_READ_ONLY_ROLE",
        "EEI_DB_POOL_SIZE",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    defaults = get_public_settings()
    assert defaults.write_route_mode == "forbidden"
    assert defaults.require_read_only_role is True
    assert defaults.database_url is None

    monkeypatch.setenv("EEI_WRITE_ROUTE_MODE", "hidden")
    monkeypatch.setenv("EEI_REQUIRE_READ_ONLY_ROLE", "0")
    monkeypatch.setenv("EEI_DB_POOL_SIZE", "2")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@h/d")
    parsed = get_public_settings()
    assert parsed.write_route_mode == "hidden"
    assert parsed.require_read_only_role is False
    assert parsed.db_pool_size == 2
    assert parsed.database_url == "postgresql://u@h/d"

    monkeypatch.setenv("EEI_WRITE_ROUTE_MODE", "open")
    with pytest.raises(ValueError):
        get_public_settings()


def test_dockerfile_contract() -> None:
    text = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev" in text  # 依赖版本以 uv.lock 为准
    assert "USER 10001" in text  # 非 root
    assert "apps.api.app.public_main:app" in text
    assert '--workers", "1"' in text


def test_deploy_env_keeps_the_service_private_and_read_only() -> None:
    env = (DEPLOY / "eei-api.env").read_text(encoding="utf-8")
    run_args = next(line for line in env.splitlines() if line.startswith("RUN_EXTRA_ARGS="))
    assert "--read-only" in run_args
    assert "--cap-drop ALL" in run_args
    assert "--user 10001" in run_args
    assert "-p " not in run_args and "--publish" not in run_args  # 不对公网暴露端口
    assert "MEMORY=256m" in env
    # 密码不在仓库里：连接串只来自服务器上的 env 文件
    assert "--env-file /etc/eei-api/eei-api.secret.env" in run_args
    assert "DATABASE_URL=postgresql://" not in env


def test_deploy_files_reference_each_other_consistently() -> None:
    service = (DEPLOY / "eei-api-pull.service").read_text(encoding="utf-8")
    install = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "eei-api-pull-deploy.sh run eei-api" in service
    for name in (
        "eei-api-pull-deploy.sh",
        "eei-api-pull.service",
        "eei-api-pull.timer",
        "eei-api.env",
    ):
        assert (DEPLOY / name).is_file()
        assert name in install


def test_readonly_role_sql_never_grants_write_privileges() -> None:
    sql = (DEPLOY / "readonly_role.sql").read_text(encoding="utf-8").upper()
    for verb in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "ALL PRIVILEGES"):
        assert f"GRANT {verb}" not in sql
    assert "PASSWORD '" not in sql  # 密码不写进仓库

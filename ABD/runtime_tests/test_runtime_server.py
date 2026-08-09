from __future__ import annotations

import http.client
import json
import sys
from pathlib import Path
from threading import Thread

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from abd_runtime.server import (
    OBSERVATION_MODE,
    SAFE_DECISION,
    RuntimeConfigurationError,
    RuntimeHTTPServer,
    build_runtime_state,
)


def _config() -> dict[str, object]:
    return {
        "product_version": "0.0.0.1",
        "activation_requested": False,
        "runtime": {"order_submission_enabled": False},
        "network": {"public_business_inbound_enabled": False},
    }


def test_runtime_state_is_observation_only(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps(_config()), encoding="utf-8")

    state = build_runtime_state(config, {"ABD_ORDER_SUBMISSION_ENABLED": "false"})

    assert state["mode"] == OBSERVATION_MODE
    assert state["decision"] == SAFE_DECISION
    assert state["recommendation_enabled"] is False
    assert state["order_submission_enabled"] is False


@pytest.mark.parametrize(
    "configuration,environment",
    [
        ({**_config(), "activation_requested": True}, {"ABD_ORDER_SUBMISSION_ENABLED": "false"}),
        ({**_config(), "runtime": {"order_submission_enabled": True}}, {"ABD_ORDER_SUBMISSION_ENABLED": "false"}),
        ({**_config(), "network": {"public_business_inbound_enabled": True}}, {"ABD_ORDER_SUBMISSION_ENABLED": "false"}),
        (_config(), {"ABD_ORDER_SUBMISSION_ENABLED": "true"}),
        (_config(), {"ABD_ORDER_SUBMISSION_ENABLED": "false", "ABD_RUNTIME_MODE": "ACTIVE"}),
    ],
)
def test_runtime_rejects_any_activation_or_order_boundary_violation(
    tmp_path: Path, configuration: dict[str, object], environment: dict[str, str]
) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps(configuration), encoding="utf-8")

    with pytest.raises(RuntimeConfigurationError):
        build_runtime_state(config, environment)


def test_http_surface_is_status_only(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps(_config()), encoding="utf-8")
    state = build_runtime_state(config, {"ABD_ORDER_SUBMISSION_ENABLED": "false"})
    server = RuntimeHTTPServer(("127.0.0.1", 0), state)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()

    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/status")
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 200
        assert body["decision"] == SAFE_DECISION

        connection.request("POST", "/orders")
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 405
        assert body["decision"] == SAFE_DECISION
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)
